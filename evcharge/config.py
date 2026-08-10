"""Configurações gerais do EV ChargeHub.

Tudo que é ajustável fica aqui: tarifa padrão, carregadores simulados,
regras de detecção, caminhos de arquivos. Nenhuma dependência externa.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "evcharge.db"

APP_NAME = "EV ChargeHub"
TIMEZONE = "America/Sao_Paulo"


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(TIMEZONE)
    except Exception:  # Windows sem a base de fusos (pacote tzdata) → UTC-3 fixo
        from datetime import timedelta, timezone

        return timezone(timedelta(hours=-3), "BRT")  # type: ignore[return-value]


# ---------------------------------------------------------------- tarifa padrão (D4/D5)
TARIFA_PADRAO = {
    "valor_kwh": Decimal("0.95"),            # R$ por kWh
    "taxa_ociosidade_min": Decimal("0.50"),  # R$ por minuto após a carência
    "carencia_min": 15,                      # minutos livres após a carga completa
    "teto_ociosidade": Decimal("60.00"),     # máximo de taxa por recarga
}


# ---------------------------------------------------------------- carregadores
@dataclass(frozen=True)
class ChargerSpec:
    codigo: str
    porta: int
    potencia_kw: float
    fases: int
    localizacao: str


CARREGADORES = [
    ChargerSpec("CH-01", 5020, 11.0, 3, "Garagem G1 — vaga 12"),
    ChargerSpec("CH-02", 5021, 11.0, 3, "Garagem G1 — vaga 13"),
    ChargerSpec("CH-03", 5022, 7.4, 1, "Garagem G2 — vaga 40"),
]
MODBUS_HOST = "127.0.0.1"


# ---------------------------------------------------------------- regras de sessão (D6)
CORRENTE_MINIMA_A = 0.5            # abaixo disso o carro não está carregando
CONFIRMA_CARGA_COMPLETA_MIN = 2    # corrente ~0 por 2 min = carga completa
TIMEOUT_AUTORIZACAO_MIN = 5        # cartão aceito mas carro não conectou
INTERVALO_POLL_S = 1.0             # leitura dos carregadores
INTERVALO_GRAVA_LEITURA_S = 60     # grava série temporal a cada N s (ou quando muda o estado)

# ---------------------------------------------------------------- IA
OCIOSIDADE_ALERTA_MIN = 60
TOLERANCIA_POTENCIA = 1.10
TOLERANCIA_ENERGIA = 1.05
TOLERANCIA_MEDIDOR = 1.15
SESSAO_LONGA_H = 12
LIMIAR_CAPACIDADE = 0.70           # previsão acima de 70% da capacidade → sugerir limite

# ---------------------------------------------------------------- demonstração
VELOCIDADE_DEMO = 60               # 1 h simulada por minuto real
