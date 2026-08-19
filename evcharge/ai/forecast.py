"""IA 1: previsão de pico de demanda (Python puro).

Série: carga média por hora (kW) do condomínio, calculada pela diferença do
medidor de energia entre leituras (funciona com qualquer frequência de leitura).

Modelos:
  * media-v1   média por (dia da semana × hora) nas últimas semanas
  * regressao-v2 regressão linear (mínimos quadrados, Python puro) usando
                 a média dia×hora e os valores de 24 h e 168 h atrás
O melhor modelo nos últimos 14 dias (menor erro médio) prevê as próximas 24 h.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

MEDIA = "media-v1"
REGRESSAO = "regressao-v2"


def _hora(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def carga_horaria(leituras, inicio: datetime, fim: datetime) -> dict[datetime, float]:
    """leituras: (ts, carregador_id, energia_kwh). Retorna {hora UTC: kW médio}, com zeros."""
    serie: dict[datetime, float] = {}
    h = _hora(inicio)
    while h < fim:
        serie[h] = 0.0
        h += timedelta(hours=1)
    ultimo: dict[int, float] = {}
    for ts, cid, energia in sorted(leituras, key=lambda r: (r[1], r[0])):
        if cid in ultimo:
            delta = energia - ultimo[cid]
            hora = _hora(ts)
            if delta > 0 and hora in serie:
                serie[hora] += delta
        ultimo[cid] = energia
    return serie


class ModeloMedia:
    nome = MEDIA

    def __init__(self, tz: tzinfo, semanas: int = 8):
        self.tz, self.semanas = tz, semanas
        self.tabela: dict[tuple[int, int], float] = {}
        self.geral = 0.0

    def treinar(self, serie: dict[datetime, float]) -> ModeloMedia:
        if not serie:
            return self
        limite = max(serie) - timedelta(weeks=self.semanas)
        soma, cont = defaultdict(float), defaultdict(int)
        for ts, kw in serie.items():
            if ts >= limite:
                local = ts.astimezone(self.tz)
                soma[(local.weekday(), local.hour)] += kw
                cont[(local.weekday(), local.hour)] += 1
        self.tabela = {k: soma[k] / cont[k] for k in soma}
        self.geral = sum(soma.values()) / max(1, sum(cont.values()))
        return self

    def prever_hora(self, ts: datetime, historico: dict[datetime, float] | None = None) -> float:
        local = ts.astimezone(self.tz)
        return self.tabela.get((local.weekday(), local.hour), self.geral)


def _resolver(A: list[list[float]], b: list[float]) -> list[float]:
    """Resolve A·x = b por eliminação de Gauss com pivotamento."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        if abs(M[col][col]) < 1e-12:
            continue
        for r in range(n):
            if r != col:
                f = M[r][col] / M[col][col]
                for c in range(col, n + 1):
                    M[r][c] -= f * M[col][c]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]


class ModeloRegressao:
    """kW = a + b·média(dia,hora) + c·kW(24 h antes) + d·kW(168 h antes), com regularização leve."""

    nome = REGRESSAO

    def __init__(self, tz: tzinfo, alpha: float = 1.0):
        self.tz, self.alpha = tz, alpha
        self.base = ModeloMedia(tz)
        self.coef = [0.0, 1.0, 0.0, 0.0]

    def _x(self, ts: datetime, hist: dict[datetime, float]) -> list[float]:
        m = self.base.prever_hora(ts)
        return [1.0, m, hist.get(ts - timedelta(hours=24), m), hist.get(ts - timedelta(hours=168), m)]

    def treinar(self, serie: dict[datetime, float]) -> ModeloRegressao:
        self.base.treinar(serie)
        inicio = min(serie) + timedelta(hours=168)
        dados = [(self._x(ts, serie), kw) for ts, kw in serie.items() if ts >= inicio]
        if len(dados) < 24 * 7:
            raise ValueError("histórico insuficiente para a regressão (mínimo 2 semanas)")
        k = 4
        XtX = [[sum(x[i] * x[j] for x, _ in dados) + (self.alpha if i == j and i > 0 else 0) for j in range(k)] for i in range(k)]
        Xty = [sum(x[i] * y for x, y in dados) for i in range(k)]
        self.coef = _resolver(XtX, Xty)
        return self

    def prever_hora(self, ts: datetime, hist: dict[datetime, float]) -> float:
        return max(0.0, sum(c * v for c, v in zip(self.coef, self._x(ts, hist))))


def _metricas(reais: list[float], prev: list[float]) -> dict:
    mae = sum(abs(a - b) for a, b in zip(reais, prev)) / max(1, len(reais))
    rel = [abs(a - b) / a for a, b in zip(reais, prev) if a >= 1.0]
    return {"mae_kw": round(mae, 3), "mape_pct": round(sum(rel) / len(rel) * 100, 1) if rel else None, "horas": len(reais)}


def avaliar(serie: dict[datetime, float], tz: tzinfo, dias: int = 14) -> dict[str, dict]:
    corte = max(serie) + timedelta(hours=1) - timedelta(days=dias)
    treino = {k: v for k, v in serie.items() if k < corte}
    teste = sorted((k, v) for k, v in serie.items() if k >= corte)
    out = {}
    for modelo in (ModeloMedia(tz), ModeloRegressao(tz)):
        try:
            modelo.treinar(treino)
        except ValueError as exc:
            out[modelo.nome] = {"erro": str(exc)}
            continue
        out[modelo.nome] = _metricas([v for _, v in teste], [modelo.prever_hora(k, serie) for k, _ in teste])
    return out


@dataclass
class Previsao:
    modelo: str
    pontos: list[tuple[datetime, float]]
    metricas: dict = field(default_factory=dict)

    @property
    def pico(self) -> tuple[datetime, float] | None:
        return max(self.pontos, key=lambda p: p[1]) if self.pontos else None


def prever_24h(serie: dict[datetime, float], agora: datetime, tz: tzinfo) -> Previsao:
    metricas = avaliar(serie, tz) if len(serie) >= 24 * 21 else {}
    validos = {k: v for k, v in metricas.items() if "mae_kw" in v}
    melhor = min(validos, key=lambda k: validos[k]["mae_kw"]) if validos else MEDIA
    modelo = ModeloRegressao(tz) if melhor == REGRESSAO else ModeloMedia(tz)
    try:
        modelo.treinar(serie)
    except ValueError:
        modelo, melhor = ModeloMedia(tz).treinar(serie), MEDIA
    inicio = _hora(agora) + timedelta(hours=1)
    pontos = [(inicio + timedelta(hours=i), round(modelo.prever_hora(inicio + timedelta(hours=i), serie), 2)) for i in range(24)]
    return Previsao(melhor, pontos, metricas)


@dataclass
class Sugestao:
    inicio: datetime
    fim: datetime
    kw_max: float
    limite_kw: float
    limite_a: int
    mensagem: str


def sugerir_controle(pontos, capacidade_kw: float, n_carregadores: int, limiar: float, tz: tzinfo) -> list[Sugestao]:
    """Janelas com previsão acima de `limiar` × capacidade → limite sugerido por carregador."""
    if capacidade_kw <= 0 or n_carregadores <= 0:
        return []
    alvo = capacidade_kw * limiar
    janelas: list[list[tuple[datetime, float]]] = []
    for ts, kw in pontos:
        if kw > alvo:
            if janelas and ts - janelas[-1][-1][0] == timedelta(hours=1):
                janelas[-1].append((ts, kw))
            else:
                janelas.append([(ts, kw)])
    out = []
    for j in janelas:
        kw_max = max(kw for _, kw in j)
        por_carregador = round(alvo / n_carregadores, 1)
        amps = max(6, int(por_carregador * 1000 / (230 * 3)))
        ini, fim = j[0][0], j[-1][0] + timedelta(hours=1)
        out.append(Sugestao(ini, fim, kw_max, por_carregador, amps,
                            f"Pico previsto de {kw_max:.1f} kW entre {ini.astimezone(tz):%H:%M} e {fim.astimezone(tz):%H:%M} "
                            f"({kw_max / capacidade_kw:.0%} da capacidade). Sugestão: limitar cada carregador a "
                            f"~{por_carregador:.1f} kW ({amps} A) nessa janela."))
    return out
