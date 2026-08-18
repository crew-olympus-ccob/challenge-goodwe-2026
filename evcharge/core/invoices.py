"""Geração das faturas mensais (automática no início do mês ou pelo painel)."""

from __future__ import annotations

from datetime import tzinfo

from evcharge.db import Database, iso, now_utc

from .billing import limites_competencia, montar_faturas
from .repo import sessao_de


def gerar_faturas(db: Database, competencia: str, tz: tzinfo) -> int:
    """Gera ou atualiza as faturas da competência. Faturas já pagas não mudam. Retorna a quantidade."""
    inicio, fim = limites_competencia(competencia, tz)
    rows = db.query(
        "SELECT * FROM sessoes WHERE inicio >= ? AND inicio < ? AND status IN ('FINALIZADA','FALHA')",
        (iso(inicio), iso(fim)),
    )
    rascunhos = montar_faturas([sessao_de(r) for r in rows], competencia, tz)
    with db.transaction() as c:
        for f in rascunhos:
            atual = c.execute("SELECT id, status FROM faturas WHERE usuario_id=? AND competencia=?", (f.usuario_id, competencia)).fetchone()
            if atual and atual["status"] == "paga":
                continue
            valores = (float(f.total_kwh), str(f.valor_energia), str(f.valor_ociosidade), str(f.valor_total), iso(now_utc()))
            if atual:
                fid = atual["id"]
                c.execute("DELETE FROM itens_fatura WHERE fatura_id=?", (fid,))
                c.execute(
                    """UPDATE faturas SET total_kwh=?, valor_energia=?, valor_ociosidade=?, valor_total=?, emitida_em=?,
                              status='emitida' WHERE id=?""",
                    (*valores, fid),
                )
            else:
                fid = c.execute(
                    """INSERT INTO faturas (usuario_id, competencia, total_kwh, valor_energia, valor_ociosidade, valor_total, emitida_em)
                       VALUES (?,?,?,?,?,?,?)""",
                    (f.usuario_id, competencia, *valores),
                ).lastrowid
            c.executemany(
                "INSERT INTO itens_fatura (fatura_id, sessao_id, kwh, valor_energia, valor_ociosidade) VALUES (?,?,?,?,?)",
                [(fid, i.sessao_id, float(i.kwh), str(i.valor_energia), str(i.valor_ociosidade)) for i in f.itens],
            )
    return len(rascunhos)
