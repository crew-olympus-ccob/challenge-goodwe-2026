"""IA 2: detecção de anomalias.

v1: regras heurísticas (explicáveis). Rodam ao fechar cada sessão.
v2: Isolation Forest implementado em Python puro (sem bibliotecas externas).
    Roda em lote sobre o histórico e aponta padrões atípicos que as regras
    não cobrem.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime

from evcharge import config


@dataclass(frozen=True)
class Features:
    sessao_id: int | None
    kwh: float
    horas_carga: float
    kw_medio: float
    kw_max: float
    min_ociosos: float
    hora: int
    nominal_kw: float

    def vetor(self) -> list[float]:
        n = self.nominal_kw or 1.0
        ang = 2 * math.pi * self.hora / 24
        return [self.kwh, self.horas_carga, self.kw_medio / n, self.kw_max / n, math.log1p(max(0.0, self.min_ociosos)), math.sin(ang), math.cos(ang)]


def _horas(a: datetime | None, b: datetime | None) -> float:
    return max(0.0, (b - a).total_seconds() / 3600) if a and b else 0.0


def extrair(sessao: dict, nominal_kw: float) -> Features:
    """sessao: dict com inicio, inicio_carga, fim_carga, desconexao (datetime), kwh_total, potencia_max_kw, min_ociosos."""
    fim = sessao.get("fim_carga") or sessao.get("desconexao")
    horas = _horas(sessao.get("inicio_carga") or sessao["inicio"], fim)
    kwh = float(sessao["kwh_total"])
    return Features(
        sessao_id=sessao.get("id"),
        kwh=kwh,
        horas_carga=horas,
        kw_medio=kwh / horas if horas > 0 else 0.0,
        kw_max=float(sessao.get("potencia_max_kw") or 0),
        min_ociosos=float(sessao.get("min_ociosos") or 0),
        hora=sessao["inicio"].hour,
        nominal_kw=float(nominal_kw),
    )


@dataclass(frozen=True)
class Achado:
    sessao_id: int | None
    tipo: str          # anomalia | ocioso
    severidade: str    # baixa | media | alta
    regra: str
    descricao: str


def regras(f: Features) -> list[Achado]:
    out: list[Achado] = []
    n = f.nominal_kw
    if f.min_ociosos > config.OCIOSIDADE_ALERTA_MIN:
        out.append(Achado(f.sessao_id, "ocioso", "media", "ociosidade_excessiva",
                          f"Veículo ficou {f.min_ociosos:.0f} min conectado após a carga completa"))
    if n and f.kw_max > n * config.TOLERANCIA_POTENCIA:
        out.append(Achado(f.sessao_id, "anomalia", "alta", "potencia_acima_nominal",
                          f"Potência máxima {f.kw_max:.1f} kW acima do nominal ({n:.1f} kW)"))
    acima_nominal = n and f.kw_medio > n * config.TOLERANCIA_ENERGIA
    acima_medida = f.kw_max > 0 and f.kw_medio > f.kw_max * config.TOLERANCIA_MEDIDOR
    if f.horas_carga >= 0.1 and (acima_nominal or acima_medida):
        ref = f"{n:.1f} kW nominais" if acima_nominal else f"{f.kw_max:.1f} kW medidos"
        out.append(Achado(f.sessao_id, "anomalia", "alta", "energia_incompativel",
                          f"{f.kwh:.1f} kWh em {f.horas_carga:.1f} h é incompatível com {ref}"))
    if f.horas_carga > config.SESSAO_LONGA_H:
        out.append(Achado(f.sessao_id, "anomalia", "media", "sessao_longa",
                          f"Recarga durou {f.horas_carga:.1f} h (limite {config.SESSAO_LONGA_H} h)"))
    return out


# ---------------------------------------------------------------- Isolation Forest (Python puro)
def _c(n: int) -> float:
    """Comprimento médio de caminho de uma busca malsucedida numa árvore binária."""
    if n <= 1:
        return 0.0
    return 2 * (math.log(n - 1) + 0.5772156649) - 2 * (n - 1) / n


class _Tree:
    __slots__ = ("feature", "split", "left", "right", "size")

    def __init__(self, data: list[list[float]], depth: int, limit: int, rng: random.Random):
        self.size = len(data)
        self.feature = self.split = None
        self.left = self.right = None
        if depth >= limit or len(data) <= 1:
            return
        dims = [d for d in range(len(data[0])) if min(r[d] for r in data) < max(r[d] for r in data)]
        if not dims:
            return
        self.feature = rng.choice(dims)
        lo = min(r[self.feature] for r in data)
        hi = max(r[self.feature] for r in data)
        self.split = rng.uniform(lo, hi)
        self.left = _Tree([r for r in data if r[self.feature] < self.split], depth + 1, limit, rng)
        self.right = _Tree([r for r in data if r[self.feature] >= self.split], depth + 1, limit, rng)

    def path(self, x: list[float], depth: int = 0) -> float:
        if self.feature is None:
            return depth + _c(self.size)
        nxt = self.left if x[self.feature] < self.split else self.right
        return nxt.path(x, depth + 1)


class IsolationForest:
    MIN_AMOSTRAS = 50

    def __init__(self, arvores: int = 100, amostra: int = 128, contaminacao: float = 0.05, seed: int = 42):
        self.arvores, self.amostra, self.contaminacao, self.seed = arvores, amostra, contaminacao, seed
        self._trees: list[_Tree] = []
        self._limiar = 1.0
        self._n = 0

    @property
    def treinado(self) -> bool:
        return bool(self._trees)

    def fit(self, X: list[list[float]]) -> IsolationForest:
        if len(X) < self.MIN_AMOSTRAS:
            raise ValueError(f"amostras insuficientes ({len(X)} < {self.MIN_AMOSTRAS})")
        rng = random.Random(self.seed)
        self._n = min(self.amostra, len(X))
        limit = math.ceil(math.log2(self._n))
        self._trees = [_Tree(rng.sample(X, self._n), 0, limit, rng) for _ in range(self.arvores)]
        scores = sorted(self.score(X), reverse=True)
        self._limiar = scores[max(0, int(len(scores) * self.contaminacao) - 1)]
        return self

    def score(self, X: list[list[float]]) -> list[float]:
        """0..1 — quanto mais perto de 1, mais anômalo."""
        cn = _c(self._n)
        return [2 ** (-(sum(t.path(x) for t in self._trees) / len(self._trees)) / cn) for x in X]

    def predict(self, X: list[list[float]]) -> list[bool]:
        return [s >= self._limiar for s in self.score(X)]


def detectar(features: list[Features], floresta: IsolationForest | None = None) -> list[Achado]:
    """Regras + Isolation Forest (este só reporta o que as regras não pegaram)."""
    achados: list[Achado] = []
    marcados = set()
    for f in features:
        r = regras(f)
        achados.extend(r)
        if r:
            marcados.add(f.sessao_id)
    if floresta is not None and floresta.treinado and features:
        X = [f.vetor() for f in features]
        for f, flag, s in zip(features, floresta.predict(X), floresta.score(X)):
            if flag and f.sessao_id not in marcados:
                achados.append(Achado(f.sessao_id, "anomalia", "baixa", "isolation_forest", f"Padrão de consumo atípico (score {s:.2f})"))
    return achados
