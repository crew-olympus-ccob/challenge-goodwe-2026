"""Sobe o sistema inteiro em segundo plano (threads), por trás da interface.

    banco SQLite  ←  poller (Modbus)  ←  simulador dos carregadores
                  ←  agendador da IA e das faturas
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

from evcharge import config, seed
from evcharge.ai import service as ia
from evcharge.core.billing import competencia_anterior
from evcharge.core.invoices import gerar_faturas
from evcharge.core.poller import Poller
from evcharge.core.repo import Repo
from evcharge.db import Database, now_utc
from evcharge.hardware.scenarios import ScenarioRunner
from evcharge.hardware.simulator import Simulator
from evcharge.services.queries import Consultas

log = logging.getLogger(__name__)


class Sistema:
    def __init__(self, db_path=config.DB_PATH, com_simulador: bool = True):
        self.db = Database(db_path)
        self.consultas = Consultas(self.db)
        self.simulador: Simulator | None = None
        self.cenarios: ScenarioRunner | None = None
        self.poller: Poller | None = None
        self.com_simulador = com_simulador
        self._stop = threading.Event()

    def preparar(self, progresso=lambda msg: None) -> None:
        """Primeira execução: cria dados e gera 90 dias de histórico simulado."""
        seed.popular(self.db)
        if not self.db.scalar("SELECT COUNT(*) FROM sessoes WHERE origem='historico'"):
            progresso("Gerando 90 dias de histórico e treinando a IA…")
            seed.gerar_historico(self.db)

    def iniciar(self) -> None:
        if self.com_simulador:
            self.simulador = Simulator(config.CARREGADORES, config.MODBUS_HOST)
            # carregadores virtuais criados pelo síndico em execuções anteriores
            # (todo carregador cadastrado em 127.0.0.1 é simulado)
            for c in self.db.query("SELECT codigo, potencia_max_kw FROM carregadores WHERE host = ?", (config.MODBUS_HOST,)):
                self.simulador.adicionar(c["codigo"], c["potencia_max_kw"])
            self.simulador.start()
            self.cenarios = ScenarioRunner(self.simulador)
            # aponta os carregadores cadastrados para as portas efetivas do simulador
            for codigo, porta in self.simulador.ports.items():
                self.db.execute("UPDATE carregadores SET host = ?, porta = ? WHERE codigo = ?", (config.MODBUS_HOST, porta, codigo))
        self.poller = Poller(Repo(self.db))
        self.poller.start()
        threading.Thread(target=self._agendador, name="agendador", daemon=True).start()

    def criar_carregador_simulado(self, codigo: str, potencia_kw: float, localizacao: str) -> None:
        """Cadastra um carregador e já sobe um equipamento virtual para ele (fica Disponível em segundos)."""
        if self.simulador is None:
            raise ValueError("O simulador está desativado nesta execução.")
        codigo = codigo.strip().upper()
        if not codigo:
            raise ValueError("Informe o código do carregador.")
        if self.db.scalar("SELECT 1 FROM carregadores WHERE codigo = ?", (codigo,)):
            raise ValueError(f"Já existe um carregador {codigo}.")
        if not 1.4 <= potencia_kw <= 22:
            raise ValueError("Potência deve ficar entre 1,4 e 22 kW (carregadores AC).")
        porta = self.simulador.adicionar(codigo, potencia_kw, porta=max(self.simulador.ports.values(), default=5019) + 1)
        self.consultas.novo_carregador(codigo, config.MODBUS_HOST, porta, potencia_kw, localizacao)

    def _agendador(self) -> None:
        """De hora em hora: previsão de pico e varredura de anomalias. No início do mês: faturas."""
        while not self._stop.wait(5):
            agora = now_utc()
            try:
                ultima = self.db.scalar("SELECT MAX(executado_em) FROM execucoes_ia WHERE tipo='previsao'")
                if ultima is None or ultima < (agora - timedelta(hours=1)).isoformat():
                    ia.executar_anomalias(self.db, desde=agora - timedelta(hours=2))
                    ia.executar_previsao(self.db, agora)
                anterior = competencia_anterior(self.consultas.competencia_atual())
                if not self.db.scalar("SELECT 1 FROM faturas WHERE competencia = ?", (anterior,)):
                    gerar_faturas(self.db, anterior, config.tz())
            except Exception:  # noqa: BLE001
                log.exception("erro no agendador")
            self._stop.wait(55)

    def parar(self) -> None:
        self._stop.set()
        if self.cenarios:
            self.cenarios.stop()
        if self.poller:
            self.poller.stop()
        if self.simulador:
            self.simulador.stop()
