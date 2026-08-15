"""Acesso a dados usado pela lógica de sessões (camada fina sobre o SQLite)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from evcharge.db import Database, dec, iso, now_utc, parse

from .billing import Tarifa, TarifaNaoEncontrada

ATIVAS = ("AUTORIZADA", "CARREGANDO", "CARGA_COMPLETA")
_DATAS = ("inicio", "inicio_carga", "fim_carga", "desconexao")
_DINHEIRO = ("custo_energia", "custo_ociosidade", "custo_total")


def sessao_de(row) -> dict | None:
    if row is None:
        return None
    s = dict(row)
    for k in _DATAS:
        s[k] = parse(s.get(k))
    for k in _DINHEIRO:
        s[k] = dec(s.get(k))
    return s


def tarifa_de(row) -> Tarifa:
    return Tarifa(
        id=row["id"],
        valor_kwh=dec(row["valor_kwh"]),
        taxa_ociosidade_min=dec(row["taxa_ociosidade_min"]),
        carencia_min=row["carencia_min"],
        vigencia_inicio=parse(row["vigencia_inicio"]),
        vigencia_fim=parse(row["vigencia_fim"]),
        teto_ociosidade=dec(row["teto_ociosidade"]) if row["teto_ociosidade"] not in (None, "") else None,
    )


class Repo:
    def __init__(self, db: Database):
        self.db = db

    def carregador(self, codigo: str):
        return self.db.one("SELECT * FROM carregadores WHERE codigo = ?", (codigo,))

    def cartao(self, uid: str):
        return self.db.one(
            """SELECT c.uid, c.usuario_id, (c.ativo AND u.ativo) AS ativo,
                      (SELECT v.id FROM veiculos v WHERE v.usuario_id = c.usuario_id ORDER BY v.id LIMIT 1) AS veiculo_id
               FROM cartoes_rfid c JOIN usuarios u ON u.id = c.usuario_id WHERE c.uid = ?""",
            (uid.upper(),),
        )

    def sessao_ativa(self, carregador_id: int) -> dict | None:
        return sessao_de(self.db.one(
            f"SELECT * FROM sessoes WHERE carregador_id = ? AND status IN {ATIVAS} ORDER BY id DESC LIMIT 1", (carregador_id,)))

    def sessao_ativa_usuario(self, usuario_id: int) -> dict | None:
        return sessao_de(self.db.one(
            f"SELECT * FROM sessoes WHERE usuario_id = ? AND status IN {ATIVAS} ORDER BY id DESC LIMIT 1", (usuario_id,)))

    def criar_sessao(self, s: dict) -> int:
        return self.db.execute(
            """INSERT INTO sessoes (carregador_id, usuario_id, veiculo_id, tarifa_id, rfid_uid, status, inicio, kwh_inicio)
               VALUES (?, ?, ?, ?, ?, 'AUTORIZADA', ?, ?)""",
            (s["carregador_id"], s["usuario_id"], s.get("veiculo_id"), s.get("tarifa_id"), s["rfid_uid"], iso(s["inicio"]), s["kwh_inicio"]),
        )

    def salvar_sessao(self, s: dict) -> None:
        self.db.execute(
            """UPDATE sessoes SET status=?, inicio_carga=?, fim_carga=?, desconexao=?, kwh_total=?, min_ociosos=?,
                      potencia_max_kw=?, custo_energia=?, custo_ociosidade=?, custo_total=?, tarifa_id=? WHERE id=?""",
            (s["status"], iso(s["inicio_carga"]), iso(s["fim_carga"]), iso(s["desconexao"]), round(s["kwh_total"], 4),
             round(s["min_ociosos"], 2), s["potencia_max_kw"], str(s["custo_energia"]), str(s["custo_ociosidade"]),
             str(s["custo_total"]), s.get("tarifa_id"), s["id"]),
        )

    def gravar_leitura(self, carregador_id: int, sessao_id: int | None, r) -> None:
        self.db.execute(
            """INSERT INTO leituras (carregador_id, sessao_id, ts, status, conectado, potencia_kw, corrente_a, energia_kwh)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (carregador_id, sessao_id, iso(r.ts), r.status, int(r.conectado), r.potencia_kw, r.corrente_a, r.energia_kwh),
        )

    def atualizar_carregador(self, carregador_id: int, status: str, ts: datetime, potencia_kw: float = 0.0) -> None:
        self.db.execute(
            "UPDATE carregadores SET status=?, ultima_leitura=?, potencia_atual_kw=? WHERE id=?",
            (status, iso(ts), potencia_kw, carregador_id),
        )

    def alerta(self, tipo: str, severidade: str, descricao: str, carregador_id=None, sessao_id=None, regra=None, criado_em=None) -> int:
        return self.db.execute(
            "INSERT INTO alertas (tipo, severidade, regra, carregador_id, sessao_id, descricao, criado_em) VALUES (?,?,?,?,?,?,?)",
            (tipo, severidade, regra, carregador_id, sessao_id, descricao, iso(criado_em or now_utc())),
        )

    def tem_alerta(self, sessao_id: int | None, regra: str) -> bool:
        return self.db.scalar("SELECT 1 FROM alertas WHERE sessao_id IS ? AND regra = ? LIMIT 1", (sessao_id, regra)) is not None

    def tarifas(self) -> list[Tarifa]:
        return [tarifa_de(r) for r in self.db.query("SELECT * FROM tarifas")]

    def tarifa_em(self, ts: datetime) -> Tarifa:
        row = self.db.one(
            """SELECT * FROM tarifas WHERE vigencia_inicio <= ? AND (vigencia_fim IS NULL OR vigencia_fim > ?)
               ORDER BY vigencia_inicio DESC LIMIT 1""",
            (iso(ts), iso(ts)),
        )
        if row is None:
            raise TarifaNaoEncontrada(f"nenhuma tarifa vigente em {ts.isoformat()}")
        return tarifa_de(row)


__all__ = ["Repo", "sessao_de", "tarifa_de", "ATIVAS", "Decimal"]
