"""Motor de rateio.

    custo_energia    = kWh × tarifa
    min_cobráveis    = max(0, minutos ociosos − carência)
    custo_ociosidade = min_cobráveis × taxa por minuto   (limitado ao teto)
    custo_sessão     = custo_energia + custo_ociosidade

* A tarifa usada é a vigente no INÍCIO da recarga.
* Cálculo em Decimal com 4 casas; arredondamento para centavos só na fatura.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
from decimal import ROUND_HALF_UP, Decimal

Q4, Q2 = Decimal("0.0001"), Decimal("0.01")


def q4(v) -> Decimal:
    return Decimal(str(v)).quantize(Q4, rounding=ROUND_HALF_UP)


def q2(v) -> Decimal:
    return Decimal(str(v)).quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass
class Tarifa:
    id: int
    valor_kwh: Decimal
    taxa_ociosidade_min: Decimal
    carencia_min: int
    vigencia_inicio: datetime
    vigencia_fim: datetime | None = None
    teto_ociosidade: Decimal | None = None

    def vigente_em(self, ts: datetime) -> bool:
        return self.vigencia_inicio <= ts and (self.vigencia_fim is None or ts < self.vigencia_fim)


class TarifaNaoEncontrada(LookupError):
    pass


def tarifa_em(tarifas: list[Tarifa], ts: datetime) -> Tarifa:
    validas = [t for t in tarifas if t.vigente_em(ts)]
    if not validas:
        raise TarifaNaoEncontrada(f"nenhuma tarifa vigente em {ts.isoformat()}")
    return max(validas, key=lambda t: t.vigencia_inicio)


@dataclass(frozen=True)
class Custo:
    kwh: Decimal
    min_cobraveis: Decimal
    energia: Decimal
    ociosidade: Decimal

    @property
    def total(self) -> Decimal:
        return self.energia + self.ociosidade


def calcular_custo(kwh, min_ociosos, tarifa: Tarifa) -> Custo:
    kwh = max(Decimal(0), Decimal(str(kwh)))
    cobraveis = max(Decimal(0), Decimal(str(min_ociosos)) - Decimal(tarifa.carencia_min))
    energia = q4(kwh * tarifa.valor_kwh)
    ociosidade = q4(cobraveis * tarifa.taxa_ociosidade_min)
    if tarifa.teto_ociosidade is not None:
        ociosidade = min(ociosidade, q4(tarifa.teto_ociosidade))
    return Custo(q4(kwh), q4(cobraveis), energia, ociosidade)


# ---------------------------------------------------------------- faturas
def competencia_de(ts: datetime, tz: tzinfo | None = None) -> str:
    ts = ts.astimezone(tz) if tz else ts
    return f"{ts.year:04d}-{ts.month:02d}"


def limites_competencia(competencia: str, tz: tzinfo = UTC) -> tuple[datetime, datetime]:
    ano, mes = (int(p) for p in competencia.split("-"))
    if not 1 <= mes <= 12:
        raise ValueError("competência inválida, use AAAA-MM")
    return datetime(ano, mes, 1, tzinfo=tz), datetime(ano + (mes == 12), mes % 12 + 1, 1, tzinfo=tz)


def competencia_anterior(competencia: str) -> str:
    ano, mes = (int(p) for p in competencia.split("-"))
    return f"{ano - (mes == 1):04d}-{(mes - 2) % 12 + 1:02d}"


@dataclass
class ItemFatura:
    sessao_id: int | None
    kwh: Decimal
    valor_energia: Decimal
    valor_ociosidade: Decimal


@dataclass
class RascunhoFatura:
    usuario_id: int
    competencia: str
    itens: list[ItemFatura] = field(default_factory=list)

    @property
    def total_kwh(self) -> Decimal:
        return q4(sum((i.kwh for i in self.itens), Decimal(0)))

    @property
    def valor_energia(self) -> Decimal:
        return q2(sum((i.valor_energia for i in self.itens), Decimal(0)))

    @property
    def valor_ociosidade(self) -> Decimal:
        return q2(sum((i.valor_ociosidade for i in self.itens), Decimal(0)))

    @property
    def valor_total(self) -> Decimal:
        return self.valor_energia + self.valor_ociosidade


def montar_faturas(sessoes: list[dict], competencia: str, tz: tzinfo = UTC) -> list[RascunhoFatura]:
    """sessoes: dicts com id, usuario_id, inicio (datetime), status, kwh_total, custo_energia, custo_ociosidade."""
    inicio, fim = limites_competencia(competencia, tz)
    por_usuario: dict[int, RascunhoFatura] = {}
    for s in sessoes:
        if s["status"] not in ("FINALIZADA", "FALHA") or not (inicio <= s["inicio"] < fim):
            continue
        f = por_usuario.setdefault(s["usuario_id"], RascunhoFatura(s["usuario_id"], competencia))
        f.itens.append(ItemFatura(s["id"], q4(s["kwh_total"]), q4(s["custo_energia"]), q4(s["custo_ociosidade"])))
    return sorted(por_usuario.values(), key=lambda f: f.usuario_id)
