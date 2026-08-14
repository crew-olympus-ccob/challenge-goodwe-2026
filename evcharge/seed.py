"""Dados iniciais (idempotente) + histórico simulado na primeira execução.

Usuários de demonstração:
    admin@condominio.local / admin123
    morador1@condominio.local ... morador10@condominio.local / morador123
Cartões RFID: AB120001 ... AB120010 (morador1 ... morador10)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from evcharge import config
from evcharge.ai import history, service
from evcharge.core.auth import hash_senha
from evcharge.core.billing import competencia_de
from evcharge.core.invoices import gerar_faturas
from evcharge.core.repo import Repo
from evcharge.db import Database, iso, now_utc

# nome, unidade, modelo, placa, bateria kWh, potência AC kW
MORADORES = [
    ("Ana Souza", "101", "BYD Dolphin", "RIO2A19", 44.9, 6.6),
    ("Bruno Lima", "102", "Tesla Model Y", "TES1A23", 75.0, 11.0),
    ("Carla Mendes", "201", "Volvo EX30", "VLV3B45", 64.0, 11.0),
    ("Diego Rocha", "202", "BYD Seal", "SEA4C67", 82.5, 7.0),
    ("Elisa Prado", "301", "GWM Ora 03", "ORA5D89", 48.0, 6.6),
    ("Felipe Araújo", "302", "BMW iX1", "BMW6E01", 64.7, 11.0),
    ("Gabriela Nunes", "401", "Renault Kwid E-Tech", "KWD7F23", 26.8, 6.6),
    ("Henrique Dias", "402", "Chevrolet Bolt EUV", "BLT8G45", 65.0, 11.0),
    ("Isabela Castro", "501", "Peugeot e-2008", "PEU9H67", 50.0, 7.4),
    ("João Ferreira", "502", "BYD Yuan Plus", "YUA0J89", 60.5, 7.0),
]


def popular(db: Database) -> None:
    """Cria usuários, cartões, veículos, carregadores e tarifa (se ainda não existirem)."""
    if db.scalar("SELECT COUNT(*) FROM usuarios"):
        return
    senha_morador = hash_senha("morador123")
    with db.transaction() as c:
        c.execute("INSERT INTO usuarios (nome, email, senha_hash, perfil, unidade) VALUES (?,?,?,?,?)",
                  ("Administração", "admin@condominio.local", hash_senha("admin123"), "admin", "ADM"))
        for i, (nome, unidade, modelo, placa, bateria, ac) in enumerate(MORADORES, start=1):
            uid = c.execute("INSERT INTO usuarios (nome, email, senha_hash, perfil, unidade) VALUES (?,?,?,?,?)",
                            (nome, f"morador{i}@condominio.local", senha_morador, "usuario", unidade)).lastrowid
            c.execute("INSERT INTO cartoes_rfid (uid, usuario_id, apelido) VALUES (?,?,?)", (f"AB12{i:04d}", uid, "Cartão principal"))
            c.execute("INSERT INTO veiculos (usuario_id, modelo, placa, capacidade_kwh, potencia_ac_kw) VALUES (?,?,?,?,?)",
                      (uid, modelo, placa, bateria, ac))
        for ch in config.CARREGADORES:
            c.execute("INSERT INTO carregadores (codigo, host, porta, potencia_max_kw, localizacao) VALUES (?,?,?,?,?)",
                      (ch.codigo, config.MODBUS_HOST, ch.porta, ch.potencia_kw, ch.localizacao))
        t = config.TARIFA_PADRAO
        c.execute("INSERT INTO tarifas (valor_kwh, taxa_ociosidade_min, carencia_min, teto_ociosidade, vigencia_inicio) VALUES (?,?,?,?,?)",
                  (str(t["valor_kwh"]), str(t["taxa_ociosidade_min"]), t["carencia_min"], str(t["teto_ociosidade"]),
                   iso(datetime(2025, 1, 1, tzinfo=config.tz()).astimezone(UTC))))


def gerar_historico(db: Database, dias: int = 90, agora: datetime | None = None) -> dict:
    """Gera o histórico simulado, fecha as faturas dos meses anteriores e roda a IA."""
    if db.scalar("SELECT COUNT(*) FROM sessoes WHERE origem='historico'"):
        return {"sessoes": 0}
    agora = agora or now_utc()
    tz = config.tz()
    carregadores = [dict(r) for r in db.query("SELECT id, potencia_max_kw FROM carregadores ORDER BY id")]
    usuarios = [
        {"usuario_id": r["uid"], "uid": r["cartao"], "veiculo_id": r["vid"], "potencia_ac_kw": r["ac"] or 7.4, "bateria_kwh": r["bat"] or 60.0}
        for r in db.query("""SELECT u.id AS uid, c.uid AS cartao, v.id AS vid, v.potencia_ac_kw AS ac, v.capacidade_kwh AS bat
                             FROM usuarios u JOIN cartoes_rfid c ON c.usuario_id = u.id
                             LEFT JOIN veiculos v ON v.usuario_id = u.id WHERE u.perfil = 'usuario' GROUP BY u.id""")
    ]
    sessoes, leituras = history.gerar(carregadores, usuarios, Repo(db).tarifas(), agora, tz, dias=dias)
    with db.transaction() as c:
        ids = []
        for s in sessoes:
            ids.append(c.execute(
                """INSERT INTO sessoes (carregador_id, usuario_id, veiculo_id, tarifa_id, rfid_uid, status, inicio, inicio_carga,
                       fim_carga, desconexao, kwh_inicio, kwh_total, min_ociosos, potencia_max_kw, custo_energia,
                       custo_ociosidade, custo_total, origem, anomalia_injetada)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'historico',?)""",
                (s["carregador_id"], s["usuario_id"], s["veiculo_id"], s["tarifa_id"], s["rfid_uid"], s["status"], iso(s["inicio"]),
                 iso(s["inicio_carga"]), iso(s["fim_carga"]), iso(s["desconexao"]), s["kwh_inicio"], s["kwh_total"], s["min_ociosos"],
                 s["potencia_max_kw"], str(s["custo_energia"]), str(s["custo_ociosidade"]), str(s["custo_total"]), s["anomalia_injetada"]),
            ).lastrowid)
        c.executemany(
            "INSERT INTO leituras (carregador_id, sessao_id, ts, status, conectado, potencia_kw, corrente_a, energia_kwh) VALUES (?,?,?,?,?,?,?,?)",
            [(cid, ids[idx], iso(ts), st, con, kw, a, kwh) for idx, cid, ts, st, con, kw, a, kwh in leituras],
        )
    atual = competencia_de(agora, tz)
    meses = sorted({competencia_de(s["inicio"], tz) for s in sessoes} - {atual})
    for m in meses:
        gerar_faturas(db, m, tz)
    anomalias = service.executar_anomalias(db, desde=agora - timedelta(days=dias + 1))
    prev = service.executar_previsao(db, agora)
    return {"sessoes": len(sessoes), "leituras": len(leituras), "faturas_meses": meses,
            "deteccao": anomalias.get("taxa_deteccao_simulada"), "modelo_previsao": prev.modelo}
