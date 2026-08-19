"""Execução da IA sobre o banco (agendada pelo sistema e pelo botão do painel)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from evcharge import config
from evcharge.db import Database, iso, now_utc, parse

from . import anomaly, forecast


def executar_previsao(db: Database, agora: datetime | None = None) -> forecast.Previsao:
    agora = agora or now_utc()
    inicio = agora - timedelta(days=90)
    rows = db.query("SELECT ts, carregador_id, energia_kwh FROM leituras WHERE ts >= ? AND ts < ?", (iso(inicio), iso(agora)))
    serie = forecast.carga_horaria(((parse(r["ts"]), r["carregador_id"], r["energia_kwh"]) for r in rows), inicio, agora)
    prev = forecast.prever_24h(serie, agora, config.tz())
    gerado = iso(now_utc())
    with db.transaction() as c:
        c.execute("DELETE FROM previsoes")
        c.executemany("INSERT INTO previsoes (ts, kw, modelo, gerado_em) VALUES (?,?,?,?)",
                      [(iso(ts), kw, prev.modelo, gerado) for ts, kw in prev.pontos])
        c.execute("INSERT INTO execucoes_ia (tipo, modelo, metricas, executado_em) VALUES ('previsao', ?, ?, ?)",
                  (prev.modelo, json.dumps({"avaliacao": prev.metricas, "horas_historico": len(serie)}), gerado))
    return prev


def executar_anomalias(db: Database, desde: datetime | None = None) -> dict:
    """Treina o Isolation Forest com 90 dias e avalia as sessões encerradas desde `desde`."""
    agora = now_utc()
    desde = desde or agora - timedelta(days=1)
    nominal = {r["id"]: r["potencia_max_kw"] for r in db.query("SELECT id, potencia_max_kw FROM carregadores")}
    rows = db.query("SELECT * FROM sessoes WHERE inicio >= ? AND status IN ('FINALIZADA','FALHA')", (iso(agora - timedelta(days=90)),))
    sessoes = []
    for r in rows:
        s = dict(r)
        for k in ("inicio", "inicio_carga", "fim_carga", "desconexao"):
            s[k] = parse(s[k])
        sessoes.append(s)
    feats = [anomaly.extrair(s, nominal.get(s["carregador_id"], 11.0)) for s in sessoes]
    floresta = anomaly.IsolationForest()
    treinado = len(feats) >= floresta.MIN_AMOSTRAS
    if treinado:
        floresta.fit([f.vetor() for f in feats])
    por_id = {s["id"]: s for s in sessoes}
    alvo = [f for f in feats if por_id[f.sessao_id]["desconexao"] and por_id[f.sessao_id]["desconexao"] >= desde]
    achados = anomaly.detectar(alvo, floresta if treinado else None)
    criados = 0
    with db.transaction() as c:
        for a in achados:
            if c.execute("SELECT 1 FROM alertas WHERE sessao_id=? AND regra=?", (a.sessao_id, a.regra)).fetchone():
                continue
            s = por_id[a.sessao_id]
            c.execute("INSERT INTO alertas (tipo, severidade, regra, carregador_id, sessao_id, descricao, criado_em) VALUES (?,?,?,?,?,?,?)",
                      (a.tipo, a.severidade, a.regra, s["carregador_id"], s["id"], a.descricao, iso(s["desconexao"] or agora)))
            criados += 1
    metricas = {"sessoes_treino": len(feats), "sessoes_avaliadas": len(alvo), "isolation_forest": treinado,
                "achados": len(achados), "alertas_criados": criados}
    injetadas = [s for s in sessoes if s.get("anomalia_injetada")]
    if injetadas:
        todos = anomaly.detectar(feats, floresta if treinado else None)
        regras_por_sessao: dict[int, set[str]] = {}
        for a in todos:
            regras_por_sessao.setdefault(a.sessao_id, set()).add(a.regra)
        from .history import REGRA_ESPERADA

        acertos = sum(REGRA_ESPERADA[s["anomalia_injetada"]] in regras_por_sessao.get(s["id"], set()) for s in injetadas)
        metricas["taxa_deteccao_simulada"] = round(acertos / len(injetadas), 3)
    db.execute("INSERT INTO execucoes_ia (tipo, modelo, metricas, executado_em) VALUES ('anomalia', ?, ?, ?)",
               ("regras-v1 + isolation-forest-v2" if treinado else "regras-v1", json.dumps(metricas), iso(agora)))
    return metricas
