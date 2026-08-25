"""Gráficos desenhados no Canvas do tkinter (linha, barras e área), com dica ao passar o mouse."""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable

from . import theme as T


def _escala_max(v: float) -> float:
    if v <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * mag:
            return m * mag
    return 10 * mag


def curva_suave(pts: list[tuple[float, float]], passos: int = 10) -> list[float]:
    """Curva cúbica monotônica (Fritsch–Carlson) que PASSA por todos os pontos.

    O `smooth=True` do Canvas usa splines que não passam pelos pontos (as bolinhas
    ficavam fora da linha) e ainda podiam descer abaixo de zero. Esta curva
    passa exatamente por cada ponto e não cria picos/vales que não existem nos dados.
    """
    n = len(pts)
    if n < 3:
        return [c for p in pts for c in p]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] if h[i] else 0.0 for i in range(n - 1)]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)] + [d[-1]]
    for i in range(n - 1):  # limita as tangentes para não ultrapassar os pontos vizinhos
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        if a * a + b * b > 9:
            t = 3 / math.sqrt(a * a + b * b)
            m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    out = [xs[0], ys[0]]
    for i in range(n - 1):
        for k in range(1, passos + 1):
            t = k / passos
            h00, h10 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t
            h01, h11 = -2 * t**3 + 3 * t**2, t**3 - t**2
            out += [xs[i] + t * h[i], h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]]
    return out


class _Grafico(tk.Canvas):
    def __init__(self, master, altura: int = 260, fmt_valor: Callable[[float], str] = lambda v: f"{v:.1f}"):
        super().__init__(master, height=altura, bg=master.cget("bg"), highlightthickness=0)
        self.rotulos: list[str] = []
        self.valores: list[float] = []
        self.fmt = fmt_valor
        self.linhas_ref: list[tuple[float, str, str]] = []  # (valor, cor, rótulo)
        self.ymax_min = 0.0
        self._pts: list[tuple[float, float]] = []
        self.bind("<Configure>", lambda e: self.redesenhar())
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda e: self.delete("dica"))

    def dados(self, rotulos: list[str], valores: list[float]) -> None:
        self.rotulos, self.valores = rotulos, [float(v) for v in valores]
        self.redesenhar()

    # área de plotagem
    def _area(self):
        w, h = self.winfo_width(), self.winfo_height()
        return 46, 12, max(60, w - 14), max(40, h - 28)

    def _eixos(self) -> tuple[float, float, float, float, float]:
        x0, y0, x1, y1 = self._area()
        topo = _escala_max(max(self.valores + [r[0] for r in self.linhas_ref] + [self.ymax_min, 1.0]))
        f = T.fontes().pequena
        for i in range(5):
            v = topo * i / 4
            y = y1 - (y1 - y0) * i / 4
            self.create_line(x0, y, x1, y, fill=T.GRID, dash=(3, 3))
            self.create_text(x0 - 8, y, text=f"{v:g}" if v < 1000 else f"{v / 1000:g}k", fill=T.TEXT_3, font=f, anchor="e")
        n = len(self.rotulos)
        if n:
            passo = max(1, math.ceil(n / max(1, (x1 - x0) // 52)))
            for i in range(0, n, passo):
                self.create_text(self._x(i), y1 + 14, text=self.rotulos[i], fill=T.TEXT_3, font=f)
        for valor, cor, rotulo in self.linhas_ref:
            y = y1 - (y1 - y0) * valor / topo
            self.create_line(x0, y, x1, y, fill=cor, dash=(6, 4))
            self.create_text(x1 - 4, y - 8, text=rotulo, fill=cor, font=f, anchor="e")
        return x0, y0, x1, y1, topo

    def _x(self, i: int) -> float:
        x0, _, x1, _ = self._area()
        n = max(1, len(self.rotulos))
        return x0 + (x1 - x0) * (i + 0.5) / n

    def _hover(self, e) -> None:
        self.delete("dica")
        if not self._pts:
            return
        i = min(range(len(self._pts)), key=lambda k: abs(self._pts[k][0] - e.x))
        x, y = self._pts[i]
        texto = f"{self.rotulos[i]}  ·  {self.fmt(self.valores[i])}"
        self.create_oval(x - 5, y - 5, x + 5, y + 5, outline=T.TEXT, width=2, tags="dica")
        tid = self.create_text(0, 0, text=texto, fill=T.TEXT, font=T.fontes().pequena, anchor="nw", tags="dica")
        bx0, by0, bx1, by1 = self.bbox(tid)
        lw, lh = bx1 - bx0, by1 - by0
        tx = min(max(4, x - lw / 2), self.winfo_width() - lw - 12)
        ty = max(2, y - lh - 18)
        self.coords(tid, tx + 6, ty + 4)
        rid = self.create_rectangle(tx, ty, tx + lw + 12, ty + lh + 8, fill=T.SIDEBAR, outline=T.BORDER, tags="dica")
        self.tag_raise(tid, rid)

    def redesenhar(self) -> None:  # sobrescrever
        pass


class GraficoLinha(_Grafico):
    def __init__(self, master, altura: int = 260, cor: str = T.ACCENT, **kw):
        super().__init__(master, altura, **kw)
        self.cor = cor

    def redesenhar(self) -> None:
        self.delete("all")
        if self.winfo_width() < 50:
            return
        x0, y0, x1, y1, topo = self._eixos()
        self._pts = [(self._x(i), y1 - (y1 - y0) * v / topo) for i, v in enumerate(self.valores)]
        if len(self._pts) > 1:
            self.create_line(*curva_suave(self._pts), fill=self.cor, width=2.5)
        r = 3 if len(self._pts) > 40 else 4
        for x, y in self._pts:
            self.create_oval(x - r, y - r, x + r, y + r, fill=self.cor, outline=self.cor)


class GraficoArea(_Grafico):
    def __init__(self, master, altura: int = 280, cor: str = T.ACCENT, **kw):
        super().__init__(master, altura, **kw)
        self.cor = cor

    def redesenhar(self) -> None:
        self.delete("all")
        if self.winfo_width() < 50:
            return
        x0, y0, x1, y1, topo = self._eixos()
        self._pts = [(self._x(i), y1 - (y1 - y0) * v / topo) for i, v in enumerate(self.valores)]
        if len(self._pts) > 1:
            linha = curva_suave(self._pts)
            self.create_polygon(self._pts[0][0], y1, *linha, self._pts[-1][0], y1, fill=T.ACCENT_SOFT, outline="")
            self.create_line(*linha, fill=self.cor, width=2.5)


class GraficoBarras(_Grafico):
    def __init__(self, master, altura: int = 220, cor: str = T.ACCENT, **kw):
        super().__init__(master, altura, **kw)
        self.cor = cor

    def redesenhar(self) -> None:
        self.delete("all")
        if self.winfo_width() < 50:
            return
        x0, y0, x1, y1, topo = self._eixos()
        n = max(1, len(self.valores))
        larg = min(56, (x1 - x0) / n * 0.55)
        self._pts = []
        for i, v in enumerate(self.valores):
            x = self._x(i)
            y = y1 - (y1 - y0) * v / topo
            self.create_rectangle(x - larg / 2, y, x + larg / 2, y1, fill=self.cor, width=0)
            self._pts.append((x, y))
