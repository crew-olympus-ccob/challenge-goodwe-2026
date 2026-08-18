"""Leitura periódica dos carregadores (thread de fundo).

* Lê cada carregador a cada segundo e entrega a leitura ao processador de sessões.
* Responde à autorização do cartão (escreve no carregador).
* Se um carregador parar de responder: tenta de novo com espera crescente,
  marca OFFLINE e gera alerta de comunicação.
* Aplica o limite de corrente definido no painel (controle de carga).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from evcharge import config

from .gateway import GatewayError, ModbusGateway
from .repo import Repo
from .sessions import ProcessadorSessoes

log = logging.getLogger(__name__)


@dataclass
class _Saude:
    falhas: int = 0
    proxima: float = 0.0
    offline: bool = False


class Poller:
    def __init__(self, repo: Repo, intervalo: float = config.INTERVALO_POLL_S, alerta_apos: int = 3, max_espera: float = 15.0):
        self.repo = repo
        self.processador = ProcessadorSessoes(repo)
        self.intervalo = intervalo
        self.alerta_apos = alerta_apos
        self.max_espera = max_espera
        self.gateways: dict[str, ModbusGateway] = {}
        self.saude: dict[str, _Saude] = {}
        self._limites: dict[str, int] = {}
        self._assinatura: list | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.ultimos_eventos: list[str] = []

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        for g in self.gateways.values():
            g.fechar()

    # ------------------------------------------------------------------ laço
    def _loop(self) -> None:
        ultimo_config = 0.0
        while not self._stop.is_set():
            inicio = time.monotonic()
            if inicio - ultimo_config > 5:
                self._recarregar_config()
                ultimo_config = inicio
            self.ciclo()
            self._stop.wait(max(0.0, self.intervalo - (time.monotonic() - inicio)))

    def _recarregar_config(self) -> None:
        """Cadastros/edições feitos no painel entram sem reiniciar."""
        rows = self.repo.db.query("SELECT codigo, host, porta, limite_corrente_a FROM carregadores WHERE ativo = 1 ORDER BY codigo")
        assinatura = [(r["codigo"], r["host"], r["porta"]) for r in rows]
        if assinatura != self._assinatura:
            for g in self.gateways.values():
                g.fechar()
            self.gateways = {c: ModbusGateway(c, h, p) for c, h, p in assinatura}
            self.saude = {c: _Saude() for c in self.gateways}
            self._limites = {}
            self._assinatura = assinatura
        for r in rows:
            if self._limites.get(r["codigo"]) != r["limite_corrente_a"] and not self.saude[r["codigo"]].offline:
                try:
                    self.gateways[r["codigo"]].limitar_corrente(r["limite_corrente_a"])
                    self._limites[r["codigo"]] = r["limite_corrente_a"]
                except GatewayError:
                    pass

    def ciclo(self) -> None:
        agora = time.monotonic()
        for codigo, gw in list(self.gateways.items()):
            saude = self.saude[codigo]
            if saude.proxima > agora:
                continue
            try:
                leitura = gw.ler()
            except GatewayError as exc:
                self._falha(codigo, saude, str(exc))
                continue
            saude.falhas, saude.offline, saude.proxima = 0, False, 0.0
            try:
                res = self.processador.processar(leitura)
            except Exception:  # noqa: BLE001 — uma leitura ruim não derruba o sistema
                log.exception("erro processando leitura de %s", codigo)
                continue
            for cmd in res.comandos:
                try:
                    gw.autorizar(cmd.rfid_seq, cmd.aceito)
                except GatewayError as exc:
                    log.warning("autorização não enviada para %s: %s", codigo, exc)
            if res.eventos:
                self.ultimos_eventos = (self.ultimos_eventos + res.eventos)[-50:]

    def _falha(self, codigo: str, saude: _Saude, erro: str) -> None:
        saude.falhas += 1
        saude.proxima = time.monotonic() + min(self.max_espera, 2 ** (saude.falhas - 1) * 0.5)
        if saude.falhas == self.alerta_apos and not saude.offline:
            saude.offline = True
            ch = self.repo.carregador(codigo)
            if ch:
                from evcharge.db import now_utc

                self.repo.atualizar_carregador(ch["id"], "OFFLINE", now_utc())
                self.repo.alerta("comunicacao", "alta", f"{codigo} sem comunicação Modbus ({erro})", ch["id"], None, "carregador_offline")
