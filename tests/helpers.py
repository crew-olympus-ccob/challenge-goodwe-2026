"""Utilidades compartilhadas pelos testes."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from evcharge import seed
from evcharge.core.gateway import Leitura
from evcharge.db import Database

T0 = datetime(2026, 6, 10, 19, 0, tzinfo=UTC)


def banco_temporario() -> tuple[Database, tempfile.TemporaryDirectory]:
    pasta = tempfile.TemporaryDirectory()
    db = Database(Path(pasta.name) / "teste.db")
    seed.popular(db)
    return db, pasta


class SequenciaLeituras:
    """Gera leituras de um carregador com o medidor acumulando."""

    def __init__(self, codigo="CH-01", inicio=T0, medidor=1000.0):
        self.codigo, self.ts, self.medidor, self.seq, self.uid = codigo, inicio, medidor, 0, ""

    def cartao(self, uid: str) -> Leitura:
        self.seq += 1
        self.uid = uid
        return self.r("AGUARDANDO_AUTORIZACAO", conectado=False)

    def r(self, status, conectado=True, kw=0.0, avanca_min=0.0, kwh=0.0, erro=0) -> Leitura:
        self.ts += timedelta(minutes=avanca_min)
        self.medidor = round(self.medidor + kwh, 3)
        return Leitura(self.codigo, self.ts, status, conectado, kw, round(kw * 1000 / 690, 2), self.medidor, self.seq, self.uid, erro)

    def carregar(self, horas: float, kw: float = 11.0, passo_min: int = 15) -> list[Leitura]:
        passos = int(horas * 60 / passo_min)
        return [self.r("CARREGANDO", kw=kw, avanca_min=passo_min, kwh=round(kw * passo_min / 60, 3)) for _ in range(passos)]
