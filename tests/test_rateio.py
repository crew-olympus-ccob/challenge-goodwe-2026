import unittest
from datetime import UTC, datetime
from decimal import Decimal as D

from evcharge.core.billing import Tarifa, TarifaNaoEncontrada, calcular_custo, limites_competencia, montar_faturas, tarifa_em


def tarifa(**kw):
    dados = dict(id=1, valor_kwh=D("0.95"), taxa_ociosidade_min=D("0.50"), carencia_min=15,
                 vigencia_inicio=datetime(2026, 1, 1, tzinfo=UTC), teto_ociosidade=D("60"))
    dados.update(kw)
    return Tarifa(**dados)


class TestRateio(unittest.TestCase):
    def test_dentro_da_carencia(self):
        c = calcular_custo(40, 15, tarifa())
        self.assertEqual((c.energia, c.ociosidade, c.total), (D("38.0000"), D("0"), D("38.0000")))

    def test_multa_apos_carencia(self):
        c = calcular_custo(10, D("45.5"), tarifa())
        self.assertEqual(c.ociosidade, D("15.2500"))
        self.assertEqual(c.total, D("24.7500"))

    def test_teto(self):
        self.assertEqual(calcular_custo(10, 600, tarifa()).ociosidade, D("60.0000"))
        self.assertEqual(calcular_custo(0, 615, tarifa(teto_ociosidade=None)).ociosidade, D("300.0000"))

    def test_troca_de_tarifa_no_meio_do_mes(self):
        antiga = tarifa(id=1, vigencia_fim=datetime(2026, 6, 15, tzinfo=UTC))
        nova = tarifa(id=2, valor_kwh=D("1.10"), vigencia_inicio=datetime(2026, 6, 15, tzinfo=UTC))
        s1, s2 = datetime(2026, 6, 14, 23, 30, tzinfo=UTC), datetime(2026, 6, 20, tzinfo=UTC)
        self.assertEqual(tarifa_em([antiga, nova], s1).id, 1)
        self.assertEqual(tarifa_em([antiga, nova], s2).id, 2)
        with self.assertRaises(TarifaNaoEncontrada):
            tarifa_em([antiga, nova], datetime(2025, 1, 1, tzinfo=UTC))
        c1 = calcular_custo(20, 0, tarifa_em([antiga, nova], s1))
        c2 = calcular_custo(20, 0, tarifa_em([antiga, nova], s2))
        sessoes = [dict(id=1, usuario_id=7, inicio=s1, status="FINALIZADA", kwh_total=20, custo_energia=c1.energia, custo_ociosidade=0),
                   dict(id=2, usuario_id=7, inicio=s2, status="FINALIZADA", kwh_total=20, custo_energia=c2.energia, custo_ociosidade=0)]
        [fatura] = montar_faturas(sessoes, "2026-06")
        self.assertEqual(fatura.valor_total, D("41.00"))

    def test_fatura_arredonda_so_no_total_e_filtra(self):
        jun = datetime(2026, 6, 3, tzinfo=UTC)
        sessoes = [
            dict(id=1, usuario_id=1, inicio=jun, status="FINALIZADA", kwh_total=10, custo_energia=D("9.8166"), custo_ociosidade=0),
            dict(id=2, usuario_id=1, inicio=jun, status="FINALIZADA", kwh_total=5, custo_energia=D("4.8555"), custo_ociosidade=D("2.5")),
            dict(id=3, usuario_id=2, inicio=jun, status="FALHA", kwh_total=7, custo_energia=D("6.65"), custo_ociosidade=0),
            dict(id=4, usuario_id=2, inicio=jun, status="CANCELADA", kwh_total=7, custo_energia=D("6.65"), custo_ociosidade=0),
            dict(id=5, usuario_id=3, inicio=datetime(2026, 7, 1, tzinfo=UTC), status="FINALIZADA", kwh_total=7, custo_energia=D("1"), custo_ociosidade=0),
        ]
        f1, f2 = montar_faturas(sessoes, "2026-06")
        self.assertEqual((f1.valor_energia, f1.valor_ociosidade, f1.valor_total), (D("14.67"), D("2.50"), D("17.17")))
        self.assertEqual(f2.valor_total, D("6.65"))

    def test_competencia(self):
        self.assertEqual(limites_competencia("2026-12")[1], datetime(2027, 1, 1, tzinfo=UTC))
        with self.assertRaises(ValueError):
            limites_competencia("2026-13")


if __name__ == "__main__":
    unittest.main()
