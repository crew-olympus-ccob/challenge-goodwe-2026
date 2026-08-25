"""Cores, fontes e formatação (tema escuro do protótipo do Figma)."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime
from decimal import Decimal

from evcharge import config

# ---------------------------------------------------------------- paleta
BG = "#0b1120"          # fundo da página
SIDEBAR = "#0f172a"     # barra lateral
CARD = "#111a2e"        # cartões
CARD_HOVER = "#16213a"
BORDER = "#1e293b"
INPUT = "#0b1120"
TEXT = "#f1f5f9"
TEXT_2 = "#94a3b8"      # secundário
TEXT_3 = "#64748b"      # terciário
ACCENT = "#10b981"      # verde do protótipo
ACCENT_DARK = "#065f46"
ACCENT_SOFT = "#0f2f2a"
AMBER = "#f59e0b"
AMBER_SOFT = "#3a2a0c"
RED = "#f43f5e"
RED_SOFT = "#3b1220"
SKY = "#38bdf8"
SKY_SOFT = "#0c2a3d"
INDIGO = "#818cf8"
GRID = "#1e293b"

STATUS_COR = {
    "CARREGANDO": (ACCENT, ACCENT_SOFT),
    "AUTORIZADA": (SKY, SKY_SOFT), "AUTORIZADO": (SKY, SKY_SOFT), "AGUARDANDO_AUTORIZACAO": (SKY, SKY_SOFT),
    "CARGA_COMPLETA": (AMBER, AMBER_SOFT), "CARGA_SUSPENSA": (AMBER, AMBER_SOFT),
    "CONECTADO": (INDIGO, "#1e1b4b"),
    "FINALIZADA": (TEXT_2, BORDER), "DISPONIVEL": (TEXT_2, BORDER), "CANCELADA": (TEXT_3, BORDER),
    "FALHA": (RED, RED_SOFT), "OFFLINE": (RED, RED_SOFT),
    "alta": (RED, RED_SOFT), "media": (AMBER, AMBER_SOFT), "baixa": (SKY, SKY_SOFT),
    "paga": (ACCENT, ACCENT_SOFT), "emitida": (AMBER, AMBER_SOFT),
}

STATUS_TXT = {
    "AUTORIZADA": "Autorizada", "CARREGANDO": "Carregando", "CARGA_COMPLETA": "Carga completa",
    "FINALIZADA": "Finalizada", "FALHA": "Falha", "CANCELADA": "Cancelada", "DISPONIVEL": "Disponível",
    "CONECTADO": "Conectado", "AGUARDANDO_AUTORIZACAO": "Aguardando cartão", "AUTORIZADO": "Autorizado",
    "CARGA_SUSPENSA": "Carga suspensa", "OFFLINE": "Offline", "DESCONHECIDO": "Desconhecido",
    "alta": "Alta", "media": "Média", "baixa": "Baixa", "paga": "Paga", "emitida": "Em aberto",
}


# ---------------------------------------------------------------- fontes
class Fontes:
    def __init__(self, root: tk.Misc):
        familias = set(tkfont.families(root))
        base = next((f for f in ("Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue", "DejaVu Sans", "Arial") if f in familias), "TkDefaultFont")
        self.familia = base
        self.titulo = tkfont.Font(root, family=base, size=22, weight="bold")
        self.h2 = tkfont.Font(root, family=base, size=13, weight="bold")
        self.h3 = tkfont.Font(root, family=base, size=11, weight="bold")
        self.corpo = tkfont.Font(root, family=base, size=10)
        self.corpo_b = tkfont.Font(root, family=base, size=10, weight="bold")
        self.pequena = tkfont.Font(root, family=base, size=9)
        self.numero = tkfont.Font(root, family=base, size=30, weight="bold")
        self.numero_m = tkfont.Font(root, family=base, size=20, weight="bold")
        self.numero_p = tkfont.Font(root, family=base, size=15, weight="bold")
        self.icone = tkfont.Font(root, family=base, size=13)


FONTES: Fontes | None = None


def fontes() -> Fontes:
    assert FONTES is not None, "tema não inicializado"
    return FONTES


def iniciar(root: tk.Tk) -> None:
    global FONTES
    FONTES = Fontes(root)
    root.configure(bg=BG)
    from tkinter import ttk

    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure("Dark.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, bordercolor=BORDER,
                 rowheight=30, font=FONTES.corpo, borderwidth=0, relief="flat")
    st.configure("Dark.Treeview.Heading", background=CARD, foreground=TEXT_3, font=FONTES.pequena, relief="flat", borderwidth=0, padding=(6, 6))
    st.map("Dark.Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", TEXT)])
    st.map("Dark.Treeview.Heading", background=[("active", CARD)])
    st.layout("Dark.Treeview", [("Dark.Treeview.treearea", {"sticky": "nswe"})])
    st.configure("Dark.Vertical.TScrollbar", background=BORDER, troughcolor=BG, bordercolor=BG, arrowcolor=TEXT_3, relief="flat")
    st.configure("Dark.TCombobox", fieldbackground=INPUT, background=BORDER, foreground=TEXT, arrowcolor=TEXT_2,
                 bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, selectbackground=INPUT, selectforeground=TEXT, padding=6)
    st.map("Dark.TCombobox", fieldbackground=[("readonly", INPUT)], foreground=[("readonly", TEXT)])
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_DARK)


# ---------------------------------------------------------------- formatação (pt-BR)
def _num(v, casas: int) -> str:
    s = f"{float(v or 0):,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def dinheiro(v) -> str:
    return f"R$ {_num(Decimal(str(v or 0)), 2)}"


def kwh(v, casas: int = 1) -> str:
    return f"{_num(v, casas)} kWh"


def kw(v, casas: int = 1) -> str:
    return f"{_num(v, casas)} kW"


def num(v, casas: int = 0) -> str:
    return _num(v, casas)


def minutos(m: float) -> str:
    m = max(0, round(m or 0))
    return f"{m // 60}h {m % 60:02d}min" if m >= 60 else f"{m} min"


def data_hora(dt: datetime | None) -> str:
    return dt.astimezone(config.tz()).strftime("%d/%m %H:%M") if dt else "—"


def data(dt: datetime | None) -> str:
    return dt.astimezone(config.tz()).strftime("%d/%m/%Y") if dt else "—"


def hora(dt: datetime) -> str:
    return dt.astimezone(config.tz()).strftime("%H:%M")


def dia(d: date) -> str:
    return d.strftime("%d/%m")


MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def competencia(c: str) -> str:
    ano, mes = c.split("-")
    return f"{MESES[int(mes) - 1]} de {ano}"


def mudar_competencia(c: str, delta: int) -> str:
    ano, mes = (int(x) for x in c.split("-"))
    total = ano * 12 + (mes - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"
