"""Senhas com PBKDF2-SHA256 (hashlib, biblioteca padrão) e login."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from evcharge.db import Database

ITERACOES = 200_000


def hash_senha(senha: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, ITERACOES)
    return f"pbkdf2${ITERACOES}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        _, it, salt, dk = armazenado.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", senha.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def autenticar(db: Database, email: str, senha: str) -> dict | None:
    row = db.one("SELECT * FROM usuarios WHERE email = ? AND ativo = 1", (email.strip().lower(),))
    if row is None or not verificar_senha(senha, row["senha_hash"]):
        return None
    return dict(row)
