import unittest
from datetime import UTC, datetime, timedelta

from evcharge import config
from evcharge.ai import anomaly, forecast, history
from evcharge.core.billing import Tarifa
from decimal import Decimal as D

FIM = datetime(2026, 9, 30, 12, tzinfo=UTC)
CARREGADORES = [{"id": 1, "potencia_max_kw": 11.0}, {"id": 2, "potencia_max_kw": 11.0}, {"id": 3, "potencia_max_kw": 7.4}]
USUARIOS = [{"usuario_id": i, "uid": f"AB12{i:04d}", "veiculo_id": i, "potencia_ac_kw": [6.6, 7.4, 11.0][i % 3],
             "bateria_kwh": [44.9, 60.0, 75.0][i % 3]} for i in range(1, 11)]
TARIFAS = [Tarifa(1, D("0.95"), D("0.50"), 15, datetime(2025, 1, 1, tzinfo=UTC), teto_ociosidade=D("60"))]


def historico():
    return history.gerar(CARREGADORES, USUARIOS, TARIFAS, FIM, config.tz())


class TestIA(unittest.TestCase):
    def test_historico_plausivel(self):
        sessoes, leituras = historico()
        self.assertTrue(250 < len(sessoes) < 600)
        self.assertEqual({s["anomalia_injetada"] for s in sessoes} - {None}, set(history.TIPOS_ANOMALIA))
        por_carregador = {}
        for s in sessoes:
            por_carregador.setdefault(s["carregador_id"], []).append(s)
        for lista in por_carregador.values():
            lista.sort(key=lambda s: s["inicio"])
            for a, b in zip(lista, lista[1:]):
                self.assertLessEqual(a["desconexao"], b["inicio"])

    def test_deteccao_de_anomalias_acima_de_90(self):
        sessoes, _ = historico()
        for i, s in enumerate(sessoes):
            s["id"] = i
        feats = [anomaly.extrair(s, CARREGADORES[s["carregador_id"] - 1]["potencia_max_kw"]) for s in sessoes]
        floresta = anomaly.IsolationForest().fit([f.vetor() for f in feats])
        regras = {}
        for a in anomaly.detectar(feats, floresta):
            regras.setdefault(a.sessao_id, set()).add(a.regra)
        injetadas = [s for s in sessoes if s["anomalia_injetada"]]
        acertos = sum(history.REGRA_ESPERADA[s["anomalia_injetada"]] in regras.get(s["id"], set()) for s in injetadas)
        self.assertGreaterEqual(acertos / len(injetadas), 0.9)
        normais = [s for s in sessoes if not s["anomalia_injetada"]]
        falsos = sum(1 for s in normais if regras.get(s["id"], set()) - {"isolation_forest"})
        self.assertLess(falsos / len(normais), 0.02)

    def test_carga_horaria_pelo_medidor(self):
        t = datetime(2026, 9, 1, 19, tzinfo=UTC)
        leituras = [(t, 1, 100.0), (t + timedelta(minutes=30), 1, 105.5), (t + timedelta(minutes=70), 1, 111.0),
                    (t + timedelta(minutes=10), 2, 50.0), (t + timedelta(minutes=50), 2, 57.0)]
        serie = forecast.carga_horaria(leituras, t, t + timedelta(hours=3))
        self.assertEqual([round(v, 2) for v in serie.values()], [12.5, 5.5, 0.0])

    def test_previsao_24h_com_pico_a_noite(self):
        _, leituras = historico()
        serie = forecast.carga_horaria(((ts, cid, kwh) for _, cid, ts, _, _, _, _, kwh in leituras), FIM - timedelta(days=90), FIM)
        prev = forecast.prever_24h(serie, FIM, config.tz())
        self.assertEqual(len(prev.pontos), 24)
        self.assertIn(forecast.MEDIA, prev.metricas)
        self.assertIn(forecast.REGRESSAO, prev.metricas)
        hora_pico = prev.pico[0].astimezone(config.tz()).hour
        self.assertTrue(18 <= hora_pico <= 23, hora_pico)

    def test_sugestao_de_controle_de_carga(self):
        t = datetime(2026, 10, 1, 21, tzinfo=UTC)
        pts = [(t + timedelta(hours=i), kw) for i, kw in enumerate([5, 22, 25, 8, 24])]
        s = forecast.sugerir_controle(pts, 29.4, 3, 0.7, config.tz())
        self.assertEqual(len(s), 2)
        self.assertEqual(s[0].kw_max, 25)
        self.assertGreaterEqual(s[0].limite_a, 6)


if __name__ == "__main__":
    unittest.main()
