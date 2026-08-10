"""Banco de dados SQLite (biblioteca padrão).

* Um arquivo só (data/evcharge.db), modo WAL para leitura e escrita simultâneas.
* Cada thread usa sua própria conexão (interface, leitura dos carregadores, IA).
* Datas em texto ISO-8601 UTC; valores em dinheiro em texto (Decimal, sem float).
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL DEFAULT 'usuario',      -- usuario | admin
    unidade TEXT,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS cartoes_rfid (
    id INTEGER PRIMARY KEY,
    uid TEXT NOT NULL UNIQUE,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    apelido TEXT,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS veiculos (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    modelo TEXT NOT NULL,
    placa TEXT UNIQUE,
    capacidade_kwh REAL,
    potencia_ac_kw REAL
);
CREATE TABLE IF NOT EXISTS carregadores (
    id INTEGER PRIMARY KEY,
    codigo TEXT NOT NULL UNIQUE,
    host TEXT NOT NULL,
    porta INTEGER NOT NULL,
    potencia_max_kw REAL NOT NULL,
    localizacao TEXT,
    status TEXT NOT NULL DEFAULT 'DESCONHECIDO',
    ultima_leitura TEXT,
    potencia_atual_kw REAL NOT NULL DEFAULT 0,
    limite_corrente_a INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS tarifas (
    id INTEGER PRIMARY KEY,
    valor_kwh TEXT NOT NULL,
    taxa_ociosidade_min TEXT NOT NULL,
    carencia_min INTEGER NOT NULL,
    teto_ociosidade TEXT,
    vigencia_inicio TEXT NOT NULL,
    vigencia_fim TEXT
);
CREATE TABLE IF NOT EXISTS sessoes (
    id INTEGER PRIMARY KEY,
    carregador_id INTEGER NOT NULL REFERENCES carregadores(id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    veiculo_id INTEGER REFERENCES veiculos(id),
    tarifa_id INTEGER REFERENCES tarifas(id),
    rfid_uid TEXT NOT NULL,
    status TEXT NOT NULL,
    inicio TEXT NOT NULL,
    inicio_carga TEXT,
    fim_carga TEXT,
    desconexao TEXT,
    kwh_inicio REAL NOT NULL,
    kwh_total REAL NOT NULL DEFAULT 0,
    min_ociosos REAL NOT NULL DEFAULT 0,
    potencia_max_kw REAL NOT NULL DEFAULT 0,
    custo_energia TEXT NOT NULL DEFAULT '0',
    custo_ociosidade TEXT NOT NULL DEFAULT '0',
    custo_total TEXT NOT NULL DEFAULT '0',
    origem TEXT NOT NULL DEFAULT 'carregador',   -- carregador | historico
    anomalia_injetada TEXT                        -- só no histórico simulado (gabarito da IA)
);
CREATE INDEX IF NOT EXISTS ix_sessoes_carregador_status ON sessoes(carregador_id, status);
CREATE INDEX IF NOT EXISTS ix_sessoes_usuario_inicio ON sessoes(usuario_id, inicio);
CREATE INDEX IF NOT EXISTS ix_sessoes_inicio ON sessoes(inicio);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sessao_ativa ON sessoes(carregador_id)
    WHERE status IN ('AUTORIZADA', 'CARREGANDO', 'CARGA_COMPLETA');
CREATE TABLE IF NOT EXISTS leituras (
    id INTEGER PRIMARY KEY,
    carregador_id INTEGER NOT NULL REFERENCES carregadores(id),
    sessao_id INTEGER REFERENCES sessoes(id),
    ts TEXT NOT NULL,
    status TEXT NOT NULL,
    conectado INTEGER NOT NULL,
    potencia_kw REAL NOT NULL,
    corrente_a REAL NOT NULL,
    energia_kwh REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_leituras_carregador_ts ON leituras(carregador_id, ts);
CREATE INDEX IF NOT EXISTS ix_leituras_ts ON leituras(ts);
CREATE TABLE IF NOT EXISTS faturas (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    competencia TEXT NOT NULL,                  -- AAAA-MM
    total_kwh REAL NOT NULL,
    valor_energia TEXT NOT NULL,
    valor_ociosidade TEXT NOT NULL,
    valor_total TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'emitida',     -- emitida | paga
    emitida_em TEXT NOT NULL,
    UNIQUE (usuario_id, competencia)
);
CREATE TABLE IF NOT EXISTS itens_fatura (
    id INTEGER PRIMARY KEY,
    fatura_id INTEGER NOT NULL REFERENCES faturas(id) ON DELETE CASCADE,
    sessao_id INTEGER REFERENCES sessoes(id),
    kwh REAL NOT NULL,
    valor_energia TEXT NOT NULL,
    valor_ociosidade TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY,
    tipo TEXT NOT NULL,          -- ocioso | anomalia | falha | rfid_negado | comunicacao
    severidade TEXT NOT NULL,    -- baixa | media | alta
    regra TEXT,
    carregador_id INTEGER REFERENCES carregadores(id),
    sessao_id INTEGER REFERENCES sessoes(id),
    descricao TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    resolvido_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_alertas_criado ON alertas(criado_em);
CREATE TABLE IF NOT EXISTS previsoes (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    kw REAL NOT NULL,
    modelo TEXT NOT NULL,
    gerado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS execucoes_ia (
    id INTEGER PRIMARY KEY,
    tipo TEXT NOT NULL,          -- previsao | anomalia
    modelo TEXT NOT NULL,
    metricas TEXT NOT NULL,      -- JSON
    executado_em TEXT NOT NULL
);
"""


# ---------------------------------------------------------------- conversões
def now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def dec(value) -> Decimal:
    if value is None or value == "":
        return Decimal(0)
    return value if isinstance(value, Decimal) else Decimal(str(value))


# ---------------------------------------------------------------- banco
class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self.conn().executescript(SCHEMA)

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
        return c

    @contextmanager
    def transaction(self):
        """Bloco atômico. Escritas são serializadas entre threads (lock + BEGIN IMMEDIATE)."""
        with self._write_lock:
            c = self.conn()
            if c.in_transaction:  # transação aninhada: reaproveita a externa
                yield c
                return
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise

    def execute(self, sql: str, params: tuple | list | dict = ()) -> int:
        with self.transaction() as c:
            cur = c.execute(sql, params)
            return cur.lastrowid if cur.lastrowid else cur.rowcount

    def executemany(self, sql: str, rows) -> None:
        with self.transaction() as c:
            c.executemany(sql, rows)

    def query(self, sql: str, params: tuple | list | dict = ()) -> list[sqlite3.Row]:
        return self.conn().execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | list | dict = ()) -> sqlite3.Row | None:
        return self.conn().execute(sql, params).fetchone()

    def scalar(self, sql: str, params: tuple | list | dict = ()):
        row = self.conn().execute(sql, params).fetchone()
        return row[0] if row else None

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None
