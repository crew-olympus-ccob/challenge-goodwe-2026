"""Integração real via TCP: simulador ⇄ Modbus ⇄ poller ⇄ sessões ⇄ SQLite.

Roda o roteiro da apresentação com o relógio muito acelerado e confere o
resultado no banco (recarga normal, multa por ociosidade, cartão negado,
anomalia) e a recuperação quando o simulador cai.
"""

import time
import unittest
from decimal import Decimal as D

from evcharge import config
from evcharge.core.poller import Poller
from evcharge.core.repo import Repo
from evcharge.hardware.scenarios import ScenarioRunner
from evcharge.hardware.simulator import Simulator
from tests.helpers import banco_temporario


def esperar(cond, timeout=60.0):
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.05)
    return False


class TestIntegracao(unittest.TestCase):
    def setUp(self):
        self.db, self._pasta = banco_temporario()
        self.sim = Simulator(config.CARREGADORES, "127.0.0.1", tick_s=0.02)
        self.sim._wanted_ports = {c: 0 for c in self.sim._wanted_ports}  # portas livres
        self.sim.start()
        for codigo, porta in self.sim.ports.items():
            self.db.execute("UPDATE carregadores SET porta = ? WHERE codigo = ?", (porta, codigo))
        self.poller = Poller(Repo(self.db), intervalo=0.05, max_espera=0.2)
        self.poller.start()

    def tearDown(self):
        self.poller.stop()
        self.sim.stop()
        self.db.close()
        self._pasta.cleanup()

    def sessao(self, codigo):
        return self.db.one("SELECT s.* FROM sessoes s JOIN carregadores c ON c.id = s.carregador_id WHERE c.codigo = ? ORDER BY s.id DESC", (codigo,))

    def test_roteiro_da_apresentacao(self):
        runner = ScenarioRunner(self.sim, resync_delay_s=0.5)
        run = runner.start("apresentacao", velocidade=300)
        run.thread.join(120)
        self.assertEqual(run.status, "concluido", run.log)
        self.assertTrue(esperar(lambda: not self.db.scalar(
            "SELECT COUNT(*) FROM sessoes WHERE status IN ('AUTORIZADA','CARREGANDO','CARGA_COMPLETA')"), 10))
        normal, ocioso, anomalia = self.sessao("CH-01"), self.sessao("CH-02"), self.sessao("CH-03")
        self.assertEqual((normal["status"], ocioso["status"], anomalia["status"]), ("FINALIZADA",) * 3)
        self.assertAlmostEqual(normal["kwh_total"], 30.0, delta=0.05)
        self.assertEqual(D(normal["custo_ociosidade"]), 0)
        self.assertGreater(D(ocioso["custo_ociosidade"]), 0)
        regras = {r["regra"] for r in self.db.query("SELECT regra FROM alertas")}
        self.assertTrue({"rfid_invalido", "ocioso_em_andamento", "potencia_acima_nominal"} <= regras, regras)
        self.assertGreater(self.db.scalar("SELECT COUNT(*) FROM leituras"), 20)
        time.sleep(1.0)
        self.assertEqual(self.sim.clock.speed, 1.0)  # relógio voltou ao normal
        self.assertLess(abs(self.sim.clock.offset_seconds()), 5)

    def test_limite_de_corrente_chega_ao_carregador(self):
        self.db.execute("UPDATE carregadores SET limite_corrente_a = 16 WHERE codigo = 'CH-01'")
        self.assertTrue(esperar(lambda: self.sim.chargers["CH-01"].current_limit_a == 16, 10))

    def test_queda_e_retorno_do_simulador(self):
        self.assertTrue(esperar(lambda: self.db.scalar("SELECT COUNT(*) FROM leituras") > 0, 5))
        portas = dict(self.sim.ports)
        for s in self.sim.servers.values():
            s.stop()
        self.assertTrue(esperar(lambda: self.db.scalar("SELECT COUNT(*) FROM alertas WHERE regra='carregador_offline'") == 3, 15))
        self.assertEqual(self.db.scalar("SELECT status FROM carregadores WHERE codigo='CH-01'"), "OFFLINE")
        from evcharge.hardware.modbus import ModbusServer

        for codigo, porta in portas.items():
            srv = ModbusServer(self.sim.banks[codigo], "127.0.0.1", porta)
            srv.start()
            self.sim.servers[codigo] = srv
        self.assertTrue(esperar(lambda: self.db.scalar("SELECT status FROM carregadores WHERE codigo='CH-01'") == "DISPONIVEL", 15))


if __name__ == "__main__":
    unittest.main()


class TestCarregadorSimuladoNovo(unittest.TestCase):
    """Carregador criado pelo síndico em Carregadores → Novo carregador → Simulado."""

    def test_fica_disponivel_carrega_e_volta_apos_reiniciar(self):
        import tempfile
        from pathlib import Path

        from evcharge.runtime import Sistema

        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "sis.db"
            sis = Sistema(caminho)
            sis.preparar()
            sis.iniciar()
            try:
                sis.criar_carregador_simulado("ch-04", 7.4, "Garagem G2 — vaga 41")
                with self.assertRaises(ValueError):
                    sis.criar_carregador_simulado("CH-04", 7.4, "")
                status = lambda: sis.db.scalar("SELECT status FROM carregadores WHERE codigo='CH-04'")
                self.assertTrue(esperar(lambda: status() == "DISPONIVEL", 15), status())
                self.assertIn("CH-04", sis.simulador.chargers)

                sis.simulador.tap("CH-04", "AB120004")
                self.assertTrue(esperar(lambda: sis.simulador.chargers["CH-04"].authorized, 15))
                sis.simulador.plug("CH-04", 5.0, 7.4)
                self.assertTrue(esperar(lambda: status() == "CARREGANDO", 15), status())
                sessao = sis.db.one("SELECT s.status FROM sessoes s JOIN carregadores c ON c.id=s.carregador_id WHERE c.codigo='CH-04'")
                self.assertEqual(sessao["status"], "CARREGANDO")
                sis.simulador.unplug("CH-04")
                self.assertTrue(esperar(lambda: status() == "DISPONIVEL", 15), status())
            finally:
                sis.parar()
                sis.db.close()

            outra = Sistema(caminho)
            outra.iniciar()
            try:
                self.assertIn("CH-04", outra.simulador.chargers)
                self.assertTrue(esperar(lambda: outra.db.scalar("SELECT status FROM carregadores WHERE codigo='CH-04'") == "DISPONIVEL", 15))
            finally:
                outra.parar()
                outra.db.close()
