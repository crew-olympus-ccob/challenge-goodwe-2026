"""Janela principal: tela de carregamento, login e o layout com barra lateral."""

from __future__ import annotations

import tkinter as tk

from evcharge import config
from evcharge.core.auth import autenticar
from evcharge.runtime import Sistema

from . import theme as T
from .pages import (
    alertas,
    carregadores,
    dashboard,
    faturamento,
    faturas,
    historico,
    inteligencia,
    integracoes,
    moradores,
    perfil,
    sessoes,
    simulador,
    visao_geral,
)
from .widgets import Botao, em_segundo_plano

MENU_MORADOR = [
    ("▦", "Dashboard", dashboard.Dashboard),
    ("↻", "Histórico de recargas", historico.Historico),
    ("▤", "Faturas", faturas.Faturas),
    ("⚙", "Configurações", perfil.Perfil),
]
MENU_ADMIN = [
    ("◉", "Visão geral", visao_geral.VisaoGeral),
    ("≋", "Sessões", sessoes.Sessoes),
    ("⚠", "Alertas", alertas.Alertas),
    ("✦", "Inteligência", inteligencia.Inteligencia),
    ("⚡", "Carregadores", carregadores.Carregadores),
    ("☺", "Moradores", moradores.Moradores),
    ("$", "Faturas e tarifas", faturamento.Faturamento),
    ("⇄", "Integrações", integracoes.Integracoes),
    ("▶", "Simulador", simulador.Simulador),
]


class App(tk.Tk):
    def __init__(self, sistema: Sistema | None = None):
        super().__init__()
        self.title(f"{config.APP_NAME} — Gestão de recarga do condomínio")
        self.geometry("1360x860")
        self.minsize(1100, 700)
        T.iniciar(self)
        self.sistema = sistema or Sistema()
        self.q = self.sistema.consultas
        self.usuario: dict | None = None
        self.paginas: dict[str, tk.Frame] = {}
        self.pagina_atual: tk.Frame | None = None
        self._ticker: str | None = None
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self._tela_carregando()

    # ================================================================ inicialização
    def _tela_carregando(self) -> None:
        self.raiz = tk.Frame(self, bg=T.BG)
        self.raiz.pack(fill="both", expand=True)
        box = tk.Frame(self.raiz, bg=T.BG)
        box.place(relx=0.5, rely=0.45, anchor="center")
        tk.Label(box, text="⚡", bg=T.ACCENT, fg="#04140f", font=T.fontes().numero_m, width=2).pack()
        tk.Label(box, text=config.APP_NAME, bg=T.BG, fg=T.TEXT, font=T.fontes().titulo).pack(pady=(12, 4))
        self._msg = tk.Label(box, text="Iniciando…", bg=T.BG, fg=T.TEXT_2, font=T.fontes().corpo)
        self._msg.pack()

        def terminou(_, erro):
            if erro:
                self._msg.configure(text=f"Erro ao iniciar: {erro}", fg=T.RED)
            else:
                self._pronto()

        em_segundo_plano(self, self.sistema.preparar, terminou, lambda m: self._msg.configure(text=m))

    def _pronto(self) -> None:
        self.sistema.iniciar()
        self.tela_login()

    # ================================================================ login
    def tela_login(self) -> None:
        self._parar_ticker()
        for w in self.winfo_children():
            if isinstance(w, tk.Frame):
                w.destroy()
        self.paginas.clear()
        self.usuario = None
        self.raiz = tk.Frame(self, bg=T.BG)
        self.raiz.pack(fill="both", expand=True)
        borda = tk.Frame(self.raiz, bg=T.BORDER)
        borda.place(relx=0.5, rely=0.47, anchor="center")
        box = tk.Frame(borda, bg=T.CARD, padx=34, pady=30)
        box.pack(padx=1, pady=1)
        topo = tk.Frame(box, bg=T.CARD)
        topo.pack(anchor="w", pady=(0, 22))
        tk.Label(topo, text="⚡", bg=T.ACCENT, fg="#04140f", font=T.fontes().numero_p, width=2).pack(side="left")
        tit = tk.Frame(topo, bg=T.CARD)
        tit.pack(side="left", padx=12)
        tk.Label(tit, text=config.APP_NAME, bg=T.CARD, fg=T.TEXT, font=T.fontes().h2).pack(anchor="w")
        tk.Label(tit, text="Recarga de veículos elétricos do condomínio", bg=T.CARD, fg=T.TEXT_2, font=T.fontes().pequena).pack(anchor="w")
        email, senha = tk.StringVar(value="admin@condominio.local"), tk.StringVar(value="admin123")
        for rotulo, var, oculto in (("E-mail", email, False), ("Senha", senha, True)):
            tk.Label(box, text=rotulo, bg=T.CARD, fg=T.TEXT_2, font=T.fontes().pequena).pack(anchor="w", pady=(6, 3))
            e = tk.Entry(box, textvariable=var, show="•" if oculto else "", width=36, bg=T.INPUT, fg=T.TEXT, insertbackground=T.TEXT,
                         relief="flat", highlightthickness=1, highlightbackground=T.BORDER, highlightcolor=T.ACCENT, font=T.fontes().corpo)
            e.pack(fill="x", ipady=7)
        erro = tk.Label(box, text="", bg=T.CARD, fg=T.RED, font=T.fontes().pequena)
        erro.pack(anchor="w", pady=(8, 0))

        def entrar(_=None):
            u = autenticar(self.sistema.db, email.get(), senha.get())
            if not u:
                erro.configure(text="E-mail ou senha inválidos.")
                return
            self.usuario = u
            self.tela_principal()

        Botao(box, "Entrar", entrar).pack(fill="x", pady=(8, 0))
        self.bind("<Return>", entrar)
        dica = tk.Label(box, text="Demonstração:\nadmin@condominio.local / admin123\nmorador1@condominio.local / morador123",
                        bg=T.CARD, fg=T.TEXT_3, font=T.fontes().pequena, justify="left")
        dica.pack(anchor="w", pady=(18, 0))

    # ================================================================ layout principal
    def tela_principal(self) -> None:
        self.unbind("<Return>")
        self.raiz.destroy()
        self.raiz = tk.Frame(self, bg=T.BG)
        self.raiz.pack(fill="both", expand=True)
        admin = self.usuario["perfil"] == "admin"
        menu = MENU_ADMIN if admin else MENU_MORADOR

        lateral = tk.Frame(self.raiz, bg=T.SIDEBAR, width=250)
        lateral.pack(side="left", fill="y")
        lateral.pack_propagate(False)
        tk.Frame(self.raiz, bg=T.BORDER, width=1).pack(side="left", fill="y")
        marca = tk.Frame(lateral, bg=T.SIDEBAR)
        marca.pack(fill="x", padx=18, pady=20)
        tk.Label(marca, text="⚡", bg=T.ACCENT, fg="#04140f", font=T.fontes().numero_p, width=2).pack(side="left")
        txt = tk.Frame(marca, bg=T.SIDEBAR)
        txt.pack(side="left", padx=10)
        tk.Label(txt, text=config.APP_NAME, bg=T.SIDEBAR, fg=T.TEXT, font=T.fontes().h3).pack(anchor="w")
        tk.Label(txt, text="Painel do síndico" if admin else "Portal do morador", bg=T.SIDEBAR, fg=T.TEXT_2, font=T.fontes().pequena).pack(anchor="w")
        tk.Frame(lateral, bg=T.BORDER, height=1).pack(fill="x")

        nav = tk.Frame(lateral, bg=T.SIDEBAR)
        nav.pack(fill="x", padx=12, pady=12)
        self._itens_menu: dict[str, tuple[tk.Frame, list[tk.Label]]] = {}
        for icone, nome, _ in menu:
            item = tk.Frame(nav, bg=T.SIDEBAR, cursor="hand2")
            item.pack(fill="x", pady=2)
            li = tk.Label(item, text=icone, bg=T.SIDEBAR, fg=T.TEXT_2, font=T.fontes().icone, width=2)
            li.pack(side="left", padx=(10, 6), pady=9)
            lt = tk.Label(item, text=nome, bg=T.SIDEBAR, fg=T.TEXT_2, font=T.fontes().corpo_b)
            lt.pack(side="left")
            for w in (item, li, lt):
                w.bind("<Button-1>", lambda e, n=nome: self.abrir(n))
            self._itens_menu[nome] = (item, [li, lt])

        rodape = tk.Frame(lateral, bg=T.SIDEBAR)
        rodape.pack(side="bottom", fill="x", padx=12, pady=14)
        tk.Frame(lateral, bg=T.BORDER, height=1).pack(side="bottom", fill="x")
        quem = self.usuario["nome"] + (f" · Apto {self.usuario['unidade']}" if self.usuario["unidade"] and not admin else "")
        tk.Label(rodape, text=quem, bg=T.SIDEBAR, fg=T.TEXT_3, font=T.fontes().pequena).pack(anchor="w", padx=10)
        sair = tk.Label(rodape, text="⏻   Sair", bg=T.SIDEBAR, fg=T.TEXT_2, font=T.fontes().corpo_b, cursor="hand2")
        sair.pack(anchor="w", padx=10, pady=(8, 0))
        sair.bind("<Button-1>", lambda e: self.tela_login())

        self.area = tk.Frame(self.raiz, bg=T.BG)
        self.area.pack(side="left", fill="both", expand=True)
        self._menu = {nome: cls for _, nome, cls in menu}
        self.abrir(menu[0][1])
        self._ticker = self.after(1000, self._tick)

    def abrir(self, nome: str) -> None:
        for n, (item, labels) in self._itens_menu.items():
            ativo = n == nome
            bg = T.ACCENT_SOFT if ativo else T.SIDEBAR
            item.configure(bg=bg)
            for l in labels:
                l.configure(bg=bg, fg=T.ACCENT if ativo else T.TEXT_2)
        if self.pagina_atual is not None:
            self.pagina_atual.pack_forget()
        if nome not in self.paginas:
            self.paginas[nome] = self._menu[nome](self.area, self)
        self.pagina_atual = self.paginas[nome]
        self.pagina_atual.pack(fill="both", expand=True)
        self._atualizar_pagina(forcar=True)

    def _atualizar_pagina(self, forcar: bool = False) -> None:
        p = self.pagina_atual
        if p is None:
            return
        agora = self.tk.call("clock", "milliseconds")
        if forcar or agora - getattr(p, "_ultima", 0) >= p.intervalo_ms:
            p._ultima = agora
            try:
                p.atualizar()
            except Exception as exc:  # noqa: BLE001 — uma falha de tela não fecha o app
                import logging

                logging.getLogger(__name__).exception("erro atualizando %s: %s", type(p).__name__, exc)

    def _tick(self) -> None:
        self._atualizar_pagina()
        self._ticker = self.after(1000, self._tick)

    def _parar_ticker(self) -> None:
        if self._ticker:
            self.after_cancel(self._ticker)
            self._ticker = None

    def fechar(self) -> None:
        self._parar_ticker()
        try:
            self.sistema.parar()
        finally:
            self.destroy()
