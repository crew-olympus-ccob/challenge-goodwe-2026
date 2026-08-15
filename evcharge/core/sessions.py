"""Processamento das sessões de recarga (máquina de estados).

    DISPONÍVEL ─(cartão válido)─► AUTORIZADA ─(conectado e puxando corrente)─► CARREGANDO
    CARREGANDO ─(corrente ≈ 0 por 2 min, ainda conectado)─► CARGA_COMPLETA (começa a ociosidade)
    CARGA_COMPLETA ─(desconectou)─► FINALIZADA
    CARREGANDO ─(desconectou)─► FINALIZADA
    qualquer ─(falha no carregador)─► FALHA
    AUTORIZADA ─(5 min sem carregar)─► CANCELADA

Recebe leituras do gateway e devolve comandos de autorização para o cartão.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from evcharge import config
from evcharge.ai.anomaly import extrair, regras

from .billing import TarifaNaoEncontrada, calcular_custo
from .gateway import Leitura
from .repo import Repo

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComandoAutorizacao:
    carregador: str
    rfid_seq: int
    aceito: bool


@dataclass
class Resultado:
    comandos: list[ComandoAutorizacao] = field(default_factory=list)
    eventos: list[str] = field(default_factory=list)


@dataclass
class _Estado:
    ultimo_seq: int | None = None
    corrente_zero_desde: datetime | None = None
    ultimo_status: str | None = None
    alertou_sem_sessao: bool = False
    gravado_em: datetime | None = None
    gravado_chave: tuple | None = None


class ProcessadorSessoes:
    def __init__(self, repo: Repo):
        self.repo = repo
        self._estado: dict[str, _Estado] = {}

    # ------------------------------------------------------------------ entrada
    def processar(self, r: Leitura) -> Resultado:
        res = Resultado()
        ch = self.repo.carregador(r.carregador)
        if ch is None:
            return res
        st = self._estado.setdefault(r.carregador, _Estado())
        self.repo.atualizar_carregador(ch["id"], r.status, r.ts, r.potencia_kw)

        # 1) cartão novo aproximado?
        if st.ultimo_seq is None:
            novo = r.status == "AGUARDANDO_AUTORIZACAO" and bool(r.rfid_uid)
        else:
            novo = r.rfid_seq != st.ultimo_seq and bool(r.rfid_uid)
        st.ultimo_seq = r.rfid_seq
        if novo:
            self._cartao(ch, r, res)

        # 2) transições da sessão ativa
        sessao = self.repo.sessao_ativa(ch["id"])
        if sessao is not None:
            self._avancar(ch, sessao, r, st, res)
        elif r.status == "CARREGANDO" and r.corrente_a > config.CORRENTE_MINIMA_A:
            if not st.alertou_sem_sessao:
                st.alertou_sem_sessao = True
                self._alerta(res, "anomalia", "alta", f"{ch['codigo']} fornecendo energia sem sessão autorizada",
                             ch["id"], None, "recarga_sem_sessao", r.ts)
        else:
            st.alertou_sem_sessao = False

        if r.status == "FALHA" and st.ultimo_status != "FALHA" and sessao is None:
            self._alerta(res, "falha", "alta", f"{ch['codigo']} reportou falha (código {r.erro:#04x})", ch["id"], None, "falha_carregador", r.ts)
        st.ultimo_status = r.status

        # 3) série temporal (não grava 1 linha por segundo)
        ativa = self.repo.sessao_ativa(ch["id"])
        sid = ativa["id"] if ativa else None
        chave = (r.status, r.conectado, sid, ativa["status"] if ativa else None)
        if chave != st.gravado_chave or st.gravado_em is None or abs((r.ts - st.gravado_em).total_seconds()) >= config.INTERVALO_GRAVA_LEITURA_S:
            self.repo.gravar_leitura(ch["id"], sid, r)
            st.gravado_chave, st.gravado_em = chave, r.ts
        return res

    # ------------------------------------------------------------------ RFID
    def _cartao(self, ch, r: Leitura, res: Resultado) -> None:
        uid = r.rfid_uid
        cartao = self.repo.cartao(uid)
        aceito = False
        if cartao is None or not cartao["ativo"]:
            motivo = "inativo" if cartao else "não cadastrado"
            self._alerta(res, "rfid_negado", "baixa", f"Cartão {uid} {motivo} negado em {ch['codigo']}", ch["id"], None, "rfid_invalido", r.ts)
        elif self.repo.sessao_ativa(ch["id"]) is not None:
            res.eventos.append(f"{ch['codigo']}: cartão {uid} ignorado, já existe sessão ativa")
        elif (outra := self.repo.sessao_ativa_usuario(cartao["usuario_id"])) is not None:
            self._alerta(res, "anomalia", "media", f"Cartão {uid} usado em {ch['codigo']} com sessão {outra['id']} ainda ativa em outro carregador",
                         ch["id"], outra["id"], "rfid_uso_simultaneo", r.ts)
        else:
            try:
                tarifa_id = self.repo.tarifa_em(r.ts).id
            except TarifaNaoEncontrada:
                tarifa_id = None
            sid = self.repo.criar_sessao({
                "carregador_id": ch["id"], "usuario_id": cartao["usuario_id"], "veiculo_id": cartao["veiculo_id"],
                "tarifa_id": tarifa_id, "rfid_uid": uid, "inicio": r.ts, "kwh_inicio": r.energia_kwh,
            })
            aceito = True
            res.eventos.append(f"{ch['codigo']}: sessão {sid} autorizada")
        res.comandos.append(ComandoAutorizacao(ch["codigo"], r.rfid_seq, aceito))

    # ------------------------------------------------------------------ estados
    def _avancar(self, ch, s: dict, r: Leitura, st: _Estado, res: Resultado) -> None:
        puxando = r.corrente_a > config.CORRENTE_MINIMA_A
        if r.energia_kwh >= s["kwh_inicio"]:
            s["kwh_total"] = round(r.energia_kwh - s["kwh_inicio"], 4)
        s["potencia_max_kw"] = max(s["potencia_max_kw"], r.potencia_kw)

        if r.status == "FALHA":
            self._fechar(ch, s, r, "FALHA", res)
            self._alerta(res, "falha", "alta", f"Falha {r.erro:#04x} em {ch['codigo']} durante a sessão {s['id']}",
                         ch["id"], s["id"], "falha_carregador", r.ts)
            st.corrente_zero_desde = None
            return

        if s["status"] == "AUTORIZADA":
            if r.conectado and puxando:
                s["status"], s["inicio_carga"] = "CARREGANDO", r.ts
                st.corrente_zero_desde = None
            elif r.ts - s["inicio"] > timedelta(minutes=config.TIMEOUT_AUTORIZACAO_MIN):
                s["status"], s["desconexao"], s["kwh_total"] = "CANCELADA", r.ts, 0.0

        elif s["status"] == "CARREGANDO":
            if not r.conectado:
                self._fechar(ch, s, r, "FINALIZADA", res)
                st.corrente_zero_desde = None
                return
            if puxando:
                st.corrente_zero_desde = None
            else:
                st.corrente_zero_desde = st.corrente_zero_desde or r.ts
                if r.ts - st.corrente_zero_desde >= timedelta(minutes=config.CONFIRMA_CARGA_COMPLETA_MIN):
                    s["status"], s["fim_carga"] = "CARGA_COMPLETA", st.corrente_zero_desde
                    res.eventos.append(f"{ch['codigo']}: carga completa, ociosidade iniciada")

        elif s["status"] == "CARGA_COMPLETA":
            s["min_ociosos"] = self._minutos(s["fim_carga"], r.ts)
            if not r.conectado:
                self._fechar(ch, s, r, "FINALIZADA", res)
                st.corrente_zero_desde = None
                return
            try:
                carencia = self.repo.tarifa_em(s["inicio"]).carencia_min
            except TarifaNaoEncontrada:
                carencia = 15
            if s["min_ociosos"] > carencia and not self.repo.tem_alerta(s["id"], "ocioso_em_andamento"):
                self._alerta(res, "ocioso", "media",
                             f"Veículo ocioso em {ch['codigo']} há {s['min_ociosos']:.0f} min (carência de {carencia} min encerrada)",
                             ch["id"], s["id"], "ocioso_em_andamento", r.ts)

        self.repo.salvar_sessao(s)

    def _fechar(self, ch, s: dict, r: Leitura, status: str, res: Resultado) -> None:
        s["status"], s["desconexao"] = status, r.ts
        if s["fim_carga"] is not None:
            s["min_ociosos"] = self._minutos(s["fim_carga"], r.ts)
        try:
            tarifa = self.repo.tarifa_em(s["inicio"])
            c = calcular_custo(s["kwh_total"], s["min_ociosos"], tarifa)
            s["tarifa_id"], s["custo_energia"], s["custo_ociosidade"], s["custo_total"] = tarifa.id, c.energia, c.ociosidade, c.total
        except TarifaNaoEncontrada:
            log.error("sessão %s sem tarifa vigente", s["id"])
        self.repo.salvar_sessao(s)
        res.eventos.append(f"{ch['codigo']}: sessão {s['id']} {status}: {s['kwh_total']:.2f} kWh, R$ {s['custo_total']:.2f}")
        # IA 2 (regras) a cada sessão encerrada
        for a in regras(extrair(s, ch["potencia_max_kw"])):
            if not self.repo.tem_alerta(s["id"], a.regra):
                self._alerta(res, a.tipo, a.severidade, a.descricao, ch["id"], s["id"], a.regra, r.ts)

    # ------------------------------------------------------------------ utilidades
    def _alerta(self, res: Resultado, tipo, severidade, descricao, carregador_id, sessao_id, regra, ts) -> None:
        self.repo.alerta(tipo, severidade, descricao, carregador_id, sessao_id, regra, ts)
        res.eventos.append(f"ALERTA [{severidade}] {descricao}")

    @staticmethod
    def _minutos(a: datetime | None, b: datetime) -> float:
        return round(max(0.0, (b - a).total_seconds()) / 60, 2) if a else 0.0


__all__ = ["ProcessadorSessoes", "ComandoAutorizacao", "Resultado", "Decimal"]
