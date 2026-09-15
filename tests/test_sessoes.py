import unittest
from decimal import Decimal as D

from evcharge.core.repo import Repo
from evcharge.core.sessions import ProcessadorSessoes
from tests.helpers import SequenciaLeituras, banco_temporario


class TestSessoes(unittest.TestCase):
    def setUp(self):
        self.db, self._pasta = banco_temporario()
        self.repo = Repo(self.db)
        self.proc = ProcessadorSessoes(self.repo)
        self.seq = SequenciaLeituras("CH-01")

    def tearDown(self):
        self.db.close()
        self._pasta.cleanup()

    def feed(self, *leituras):
        out = None
        for item in leituras:
            for r in item if isinstance(item, list) else [item]:
                out = self.proc.processar(r)
        return out

    def sessoes(self):
        return self.db.query("SELECT * FROM sessoes ORDER BY id")

    def alertas(self):
        return [r["regra"] for r in self.db.query("SELECT regra FROM alertas")]

    def test_fluxo_completo_com_ociosidade(self):
        s = self.seq
        self.assertFalse(self.feed(s.r("DISPONIVEL", conectado=False)).comandos)
        res = self.feed(s.cartao("AB120001"))
        self.assertTrue(res.comandos[0].aceito)
        self.feed(s.r("CARREGANDO", kw=11, avanca_min=1), s.carregar(2))  # 22 kWh
        self.feed([s.r("CARGA_SUSPENSA", avanca_min=1) for _ in range(3)])
        self.assertEqual(self.sessoes()[0]["status"], "CARGA_COMPLETA")
        self.feed([s.r("CARGA_SUSPENSA", avanca_min=5) for _ in range(9)])
        self.assertIn("ocioso_em_andamento", self.alertas())
        self.feed(s.r("DISPONIVEL", conectado=False, avanca_min=1))
        [sessao] = self.sessoes()
        self.assertEqual(sessao["status"], "FINALIZADA")
        self.assertAlmostEqual(sessao["kwh_total"], 22.0)
        self.assertEqual(sessao["min_ociosos"], 48.0)  # 2 de confirmação + 45 + 1
        self.assertEqual(D(sessao["custo_energia"]), D("20.9000"))
        self.assertEqual(D(sessao["custo_ociosidade"]), D("16.5000"))  # (48 − 15) × 0,50
        self.assertEqual(D(sessao["custo_total"]), D("37.4000"))

    def test_cartoes_invalidos(self):
        self.assertFalse(self.feed(self.seq.cartao("FFFFFFFF")).comandos[0].aceito)
        self.db.execute("UPDATE cartoes_rfid SET ativo = 0 WHERE uid = 'AB120002'")
        self.assertFalse(self.feed(self.seq.cartao("AB120002")).comandos[0].aceito)
        self.assertEqual(self.alertas(), ["rfid_invalido", "rfid_invalido"])
        self.assertFalse(self.sessoes())

    def test_autorizacao_expira(self):
        self.feed(self.seq.cartao("AB120001"), self.seq.r("AUTORIZADO", conectado=False, avanca_min=6))
        self.assertEqual(self.sessoes()[0]["status"], "CANCELADA")

    def test_falha_encerra_e_cobra_energia(self):
        s = self.seq
        self.feed(s.cartao("AB120001"), s.r("CARREGANDO", kw=11, avanca_min=1), s.carregar(0.5), s.r("FALHA", avanca_min=1, erro=0x21))
        self.assertEqual(self.sessoes()[0]["status"], "FALHA")
        self.assertGreater(D(self.sessoes()[0]["custo_energia"]), 0)
        self.feed(s.r("FALHA", avanca_min=1, erro=0x21))
        self.assertEqual(self.alertas().count("falha_carregador"), 1)

    def test_mesmo_cartao_em_dois_carregadores(self):
        self.feed(self.seq.cartao("AB120001"))
        res = self.feed(SequenciaLeituras("CH-02").cartao("AB120001"))
        self.assertFalse(res.comandos[0].aceito)
        self.assertIn("rfid_uso_simultaneo", self.alertas())

    def test_anomalia_de_potencia(self):
        s = self.seq
        self.feed(s.cartao("AB120002"), s.r("CARREGANDO", kw=14.85, avanca_min=1), s.carregar(1, kw=14.85), s.r("DISPONIVEL", conectado=False, avanca_min=1))
        self.assertTrue({"potencia_acima_nominal", "energia_incompativel"} <= set(self.alertas()))


if __name__ == "__main__":
    unittest.main()
