"""Histórico SIMULADO de 90 dias, para a IA e os gráficos já nascerem com dados.

Padrões de condomínio: dias úteis com pico entre 18h e 23h, fins de semana
espalhados, ociosidade curta na maioria das vezes. Cerca de 6% das sessões
recebem uma anomalia injetada (com gabarito, para medir a taxa de detecção).

Atenção: métricas calculadas sobre estes dados são de dados simulados.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, tzinfo

from evcharge.core.billing import Tarifa, calcular_custo, tarifa_em

TIPOS_ANOMALIA = ("potencia_excessiva", "energia_incompativel", "sessao_longa", "ociosidade_excessiva")
REGRA_ESPERADA = {
    "potencia_excessiva": "potencia_acima_nominal",
    "energia_incompativel": "energia_incompativel",
    "sessao_longa": "sessao_longa",
    "ociosidade_excessiva": "ociosidade_excessiva",
}


def gerar(carregadores: list[dict], usuarios: list[dict], tarifas: list[Tarifa], fim: datetime, tz: tzinfo,
          dias: int = 90, seed: int = 42, taxa_anomalia: float = 0.06, passo_min: int = 5):
    """carregadores: {id, potencia_max_kw}; usuarios: {usuario_id, uid, veiculo_id, potencia_ac_kw, bateria_kwh}.

    Retorna (sessoes, leituras); cada leitura referencia o índice da sessão.
    """
    rng = random.Random(seed)
    medidor = {c["id"]: 1000 + rng.uniform(0, 500) for c in carregadores}
    livre_em = {c["id"]: fim - timedelta(days=dias + 1) for c in carregadores}
    dia0 = (fim.astimezone(tz) - timedelta(days=dias)).date()

    chegadas = []
    for d in range(dias):
        dia = dia0 + timedelta(days=d)
        fds = dia.weekday() >= 5
        for u in usuarios:
            if rng.random() > (0.25 if fds else 0.38):
                continue
            if fds:
                h = min(23.5, max(7.0, rng.gauss(14, 3.5)))
            else:
                x = rng.random()
                h = min(23.7, max(17.0, rng.gauss(20.2, 1.4))) if x < 0.72 else (min(10.5, max(6.0, rng.gauss(8, 1))) if x < 0.9 else rng.uniform(10, 17))
            local = datetime(dia.year, dia.month, dia.day, tzinfo=tz) + timedelta(hours=h)
            chegadas.append((local.astimezone(fim.tzinfo), u))
    chegadas.sort(key=lambda c: c[0])

    sessoes, leituras = [], []
    for chegada, u in chegadas:
        if chegada >= fim - timedelta(hours=16):
            continue
        livres = [c for c in carregadores if livre_em[c["id"]] <= chegada]
        if not livres:
            continue
        c = rng.choice(livres)
        nominal = c["potencia_max_kw"]
        anomalia = rng.choice(TIPOS_ANOMALIA) if rng.random() < taxa_anomalia else None
        precisa = round(u["bateria_kwh"] * rng.uniform(0.15, 0.6), 2)
        pot = min(nominal, u["potencia_ac_kw"])
        mult_pot = mult_med = 1.0
        if anomalia == "sessao_longa":
            pot = rng.uniform(1.2, 1.8)
            precisa = round(pot * rng.uniform(13, 16) / 1.05, 2)
        elif anomalia == "potencia_excessiva":
            mult_pot = mult_med = nominal * 1.3 / pot
        elif anomalia == "energia_incompativel":
            mult_med = 2.0

        idx = len(sessoes)
        inicio_carga = chegada + timedelta(seconds=rng.randint(30, 150))
        kwh_inicio = medidor[c["id"]]
        t, entregue = inicio_carga, 0.0
        while entregue < precisa - 1e-6:
            prog = entregue / precisa
            p = pot * (1.0 if prog < 0.85 else max(0.05, (1 - prog) / 0.15))
            passo = min(p * passo_min / 60, precisa - entregue)
            entregue += passo
            medidor[c["id"]] += passo * mult_med
            t += timedelta(minutes=passo_min)
            leituras.append((idx, c["id"], t, "CARREGANDO", 1, round(p * mult_pot, 3), round(p * mult_pot * 1000 / 690, 2), round(medidor[c["id"]], 3)))
        fim_carga = t
        ocioso = rng.uniform(180, 480) if anomalia == "ociosidade_excessiva" else min(50.0, rng.expovariate(1 / 12))
        desconexao = fim_carga + timedelta(minutes=ocioso)
        leituras.append((idx, c["id"], fim_carga + timedelta(minutes=2), "CARGA_SUSPENSA", 1, 0.0, 0.0, round(medidor[c["id"]], 3)))
        leituras.append((idx, c["id"], desconexao, "DISPONIVEL", 0, 0.0, 0.0, round(medidor[c["id"]], 3)))
        livre_em[c["id"]] = desconexao + timedelta(minutes=rng.randint(1, 20))

        tarifa = tarifa_em(tarifas, chegada)
        kwh = round(medidor[c["id"]] - kwh_inicio, 4)
        custo = calcular_custo(kwh, round(ocioso, 2), tarifa)
        sessoes.append({
            "carregador_id": c["id"], "usuario_id": u["usuario_id"], "veiculo_id": u["veiculo_id"], "tarifa_id": tarifa.id,
            "rfid_uid": u["uid"], "status": "FINALIZADA", "inicio": chegada, "inicio_carga": inicio_carga, "fim_carga": fim_carga,
            "desconexao": desconexao, "kwh_inicio": round(kwh_inicio, 3), "kwh_total": kwh, "min_ociosos": round(ocioso, 2),
            "potencia_max_kw": round(pot * mult_pot, 3), "custo_energia": custo.energia, "custo_ociosidade": custo.ociosidade,
            "custo_total": custo.total, "anomalia_injetada": anomalia,
        })
    return sessoes, leituras
