"""Componentes visuais reutilizáveis (cartões, botões, tabelas, formulários)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from . import theme as T


def em_segundo_plano(widget: tk.Misc, trabalho: Callable[[Callable[[str], None]], object],
                     ao_terminar: Callable[[object, BaseException | None], None],
                     ao_progredir: Callable[[str], None] | None = None) -> None:
    """Roda `trabalho` numa thread sem travar a tela.

    O tkinter só pode ser mexido pela thread principal, então a thread apenas
    deixa mensagens numa fila e a tela as recolhe a cada 100 ms.
    `trabalho` recebe uma função `progresso(msg)` para avisar o andamento.
    """
    fila: queue.Queue = queue.Queue()

    def rodar():
        try:
            fila.put(("fim", trabalho(lambda m: fila.put(("msg", m, None))), None))
        except BaseException as exc:  # noqa: BLE001
            fila.put(("fim", None, exc))

    def recolher():
        try:
            while True:
                tipo, valor, erro = fila.get_nowait()
                if tipo == "msg":
                    if ao_progredir:
                        ao_progredir(valor)
                else:
                    ao_terminar(valor, erro)
                    return
        except queue.Empty:
            pass
        if widget.winfo_exists():
            widget.after(100, recolher)

    threading.Thread(target=rodar, daemon=True).start()
    widget.after(100, recolher)


class Card(tk.Frame):
    """Cartão com borda, título opcional e área de conteúdo em `self.body`."""

    def __init__(self, master, titulo: str | None = None, icone: str | None = None, acao: Callable[[tk.Frame], tk.Widget] | None = None, pad: int = 18):
        super().__init__(master, bg=T.BORDER)
        inner = tk.Frame(self, bg=T.CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.inner = inner
        if titulo:
            head = tk.Frame(inner, bg=T.CARD)
            head.pack(fill="x", padx=pad, pady=(pad, 6))
            if icone:
                tk.Label(head, text=icone, bg=T.CARD, fg=T.ACCENT, font=T.fontes().icone).pack(side="left", padx=(0, 8))
            self.titulo = tk.Label(head, text=titulo, bg=T.CARD, fg=T.TEXT, font=T.fontes().h2)
            self.titulo.pack(side="left")
            self.head = head
            if acao:
                acao(head).pack(side="right")
        self.body = tk.Frame(inner, bg=T.CARD)
        self.body.pack(fill="both", expand=True, padx=pad, pady=(6 if titulo else pad, pad))


class Stat(Card):
    def __init__(self, master, rotulo: str, valor: str = "—", dica: str = "", destaque: bool = False):
        super().__init__(master, pad=14)
        tk.Label(self.body, text=rotulo.upper(), bg=T.CARD, fg=T.TEXT_2, font=T.fontes().pequena).pack(anchor="w")
        self.valor = tk.Label(self.body, text=valor, bg=T.CARD, fg=T.ACCENT if destaque else T.TEXT, font=T.fontes().numero_m)
        self.valor.pack(anchor="w", pady=(2, 0))
        self.dica = tk.Label(self.body, text=dica, bg=T.CARD, fg=T.TEXT_3, font=T.fontes().pequena)
        self.dica.pack(anchor="w")

    def set(self, valor: str, dica: str | None = None, cor: str | None = None) -> None:
        self.valor.configure(text=valor)
        if cor:
            self.valor.configure(fg=cor)
        if dica is not None:
            self.dica.configure(text=dica)


class Badge(tk.Label):
    def __init__(self, master, valor: str = "", bg: str = T.CARD):
        super().__init__(master, font=T.fontes().pequena, padx=10, pady=2)
        self.set(valor)

    def set(self, valor: str, texto: str | None = None) -> None:
        fg, bg = T.STATUS_COR.get(valor, (T.TEXT_2, T.BORDER))
        self.configure(text=texto or T.STATUS_TXT.get(valor, valor), fg=fg, bg=bg)


class Botao(tk.Label):
    """Botão plano com hover (aparência idêntica no Windows, macOS e Linux)."""

    ESTILOS = {
        "primario": (T.ACCENT, "#04140f", "#34d399"),
        "secundario": (T.CARD, T.TEXT, T.CARD_HOVER),
        "perigo": (T.RED, "#ffffff", "#fb7185"),
        "link": (None, T.ACCENT, None),
    }

    def __init__(self, master, texto: str, comando: Callable[[], None], estilo: str = "primario", **kw):
        bg, fg, hover = self.ESTILOS[estilo]
        bg = bg or master.cget("bg")
        super().__init__(master, text=texto, bg=bg, fg=fg, font=T.fontes().corpo_b, padx=14, pady=7, cursor="hand2", **kw)
        if estilo == "secundario":
            self.configure(highlightthickness=1, highlightbackground=T.BORDER)
        self._bg, self._fg, self._hover, self._comando, self._ativo = bg, fg, hover or bg, comando, True
        self.bind("<Enter>", lambda e: self._ativo and self.configure(bg=self._hover))
        self.bind("<Leave>", lambda e: self.configure(bg=self._bg))
        self.bind("<Button-1>", lambda e: self._ativo and self._comando())

    def habilitar(self, ativo: bool, texto: str | None = None) -> None:
        self._ativo = ativo
        self.configure(fg=self._fg if ativo else T.TEXT_3, cursor="hand2" if ativo else "arrow")
        if texto:
            self.configure(text=texto)


class Barra(tk.Canvas):
    def __init__(self, master, altura: int = 8, cor: str = T.ACCENT):
        super().__init__(master, height=altura, bg=master.cget("bg"), highlightthickness=0)
        self.altura, self.cor, self.valor = altura, cor, 0.0
        self.bind("<Configure>", lambda e: self._desenhar())

    def set(self, frac: float) -> None:
        self.valor = max(0.0, min(1.0, frac))
        self._desenhar()

    def _desenhar(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.altura
        self.create_rectangle(0, 0, w, h, fill=T.BORDER, width=0)
        if self.valor > 0:
            self.create_rectangle(0, 0, max(h, w * self.valor), h, fill=self.cor, width=0)


class Tabela(tk.Frame):
    """Treeview escuro. colunas: [(chave, título, largura, alinhamento)]."""

    def __init__(self, master, colunas, altura: int = 10, ao_clicar: Callable[[str], None] | None = None):
        super().__init__(master, bg=T.CARD)
        self.colunas = colunas
        self.tree = ttk.Treeview(self, columns=[c[0] for c in colunas], show="headings", height=altura, style="Dark.Treeview")
        for chave, titulo, largura, anc in colunas:
            self.tree.heading(chave, text=titulo.upper(), anchor=anc)
            self.tree.column(chave, width=largura, minwidth=40, anchor=anc, stretch=True)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for tag, cor in (("verde", T.ACCENT), ("ambar", T.AMBER), ("vermelho", T.RED), ("cinza", T.TEXT_3), ("azul", T.SKY)):
            self.tree.tag_configure(tag, foreground=cor)
        self.vazio = tk.Label(self, text="Nada por aqui ainda.", bg=T.CARD, fg=T.TEXT_3, font=T.fontes().corpo)
        if ao_clicar:
            self.tree.bind("<Double-1>", lambda e: self.selecionado() and ao_clicar(self.selecionado()))

    def preencher(self, linhas: list[tuple[str, tuple, str | None]]) -> None:
        """linhas: (iid, valores, tag). Mantém a seleção e a rolagem."""
        sel = self.selecionado()
        topo = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        for iid, valores, tag in linhas:
            self.tree.insert("", "end", iid=iid, values=valores, tags=(tag,) if tag else ())
        if sel and self.tree.exists(sel):
            self.tree.selection_set(sel)
        self.tree.yview_moveto(topo)
        if linhas:
            self.vazio.place_forget()
        else:
            self.vazio.place(relx=0.5, rely=0.55, anchor="center")

    def selecionado(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None


class Pagina(tk.Frame):
    """Página com rolagem vertical. Conteúdo em `self.conteudo`; `atualizar()` é chamado periodicamente."""

    intervalo_ms = 3000

    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.canvas = tk.Canvas(self, bg=T.BG, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Dark.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.conteudo = tk.Frame(self.canvas, bg=T.BG, padx=32, pady=26)
        self._win = self.canvas.create_window(0, 0, window=self.conteudo, anchor="nw")
        self.conteudo.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.bind_all("<MouseWheel>", self._rolar, add="+")
        self.bind_all("<Button-4>", lambda e: self._rolar(e, -1), add="+")
        self.bind_all("<Button-5>", lambda e: self._rolar(e, 1), add="+")
        self.montar()

    def _rolar(self, e, direcao: int | None = None) -> None:
        if not self.winfo_ismapped():
            return
        alvo = str(e.widget)
        if "treeview" in alvo or "listbox" in alvo:
            return
        passo = direcao if direcao is not None else (-1 if e.delta > 0 else 1)
        if self.conteudo.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(passo * 2, "units")

    def cabecalho(self, titulo: str, subtitulo: str = "") -> tk.Frame:
        f = tk.Frame(self.conteudo, bg=T.BG)
        f.pack(fill="x", pady=(0, 20))
        esq = tk.Frame(f, bg=T.BG)
        esq.pack(side="left", fill="x", expand=True)
        tk.Label(esq, text=titulo, bg=T.BG, fg=T.TEXT, font=T.fontes().titulo).pack(anchor="w")
        self.subtitulo = tk.Label(esq, text=subtitulo, bg=T.BG, fg=T.TEXT_2, font=T.fontes().corpo, justify="left")
        self.subtitulo.pack(anchor="w")
        acoes = tk.Frame(f, bg=T.BG)
        acoes.pack(side="right")
        return acoes

    def linha(self, colunas: int, pady=(0, 20), pesos: list[int] | None = None) -> tk.Frame:
        f = tk.Frame(self.conteudo, bg=T.BG)
        f.pack(fill="x", pady=pady)
        for i in range(colunas):
            f.columnconfigure(i, weight=(pesos[i] if pesos else 1), uniform="col" if not pesos else None)
        return f

    def montar(self) -> None:  # sobrescrever
        pass

    def atualizar(self) -> None:  # sobrescrever
        pass


def label(master, texto="", cor=T.TEXT, fonte=None, **kw) -> tk.Label:
    kw.setdefault("bg", master.cget("bg"))
    return tk.Label(master, text=texto, fg=cor, font=fonte or T.fontes().corpo, **kw)


def aviso(master, texto: str, tipo: str = "ambar") -> tk.Label:
    fg, bg = {"ambar": (T.AMBER, T.AMBER_SOFT), "vermelho": (T.RED, T.RED_SOFT), "verde": (T.ACCENT, T.ACCENT_SOFT), "azul": (T.SKY, T.SKY_SOFT)}[tipo]
    return tk.Label(master, text=texto, bg=bg, fg=fg, font=T.fontes().corpo, justify="left", anchor="w", padx=12, pady=10, wraplength=560)


class Dialogo(tk.Toplevel):
    """Formulário modal. campos: [(chave, rótulo, valor_inicial, opções|None, oculto)]."""

    def __init__(self, master, titulo: str, campos, ao_salvar: Callable[[dict], None], texto_botao: str = "Salvar", descricao: str = ""):
        super().__init__(master)
        self.title(titulo)
        self.configure(bg=T.CARD, padx=24, pady=20)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        tk.Label(self, text=titulo, bg=T.CARD, fg=T.TEXT, font=T.fontes().h2).pack(anchor="w")
        if descricao:
            tk.Label(self, text=descricao, bg=T.CARD, fg=T.TEXT_2, font=T.fontes().pequena, wraplength=380, justify="left").pack(anchor="w", pady=(4, 0))
        self.vars: dict[str, tk.StringVar] = {}
        self.campos: dict[str, tk.Widget] = {}
        for chave, rotulo, inicial, opcoes, oculto in campos:
            tk.Label(self, text=rotulo, bg=T.CARD, fg=T.TEXT_2, font=T.fontes().pequena).pack(anchor="w", pady=(12, 3))
            var = tk.StringVar(value=inicial)
            if opcoes:
                w = ttk.Combobox(self, textvariable=var, values=opcoes, state="readonly", style="Dark.TCombobox", width=38)
            else:
                w = tk.Entry(self, textvariable=var, bg=T.INPUT, fg=T.TEXT, insertbackground=T.TEXT, relief="flat",
                             highlightthickness=1, highlightbackground=T.BORDER, highlightcolor=T.ACCENT, font=T.fontes().corpo,
                             width=40, show="•" if oculto else "")
            w.pack(fill="x", ipady=5)
            self.vars[chave] = var
            self.campos[chave] = w
        self.erro = tk.Label(self, text="", bg=T.CARD, fg=T.RED, font=T.fontes().pequena, wraplength=380, justify="left")
        self.erro.pack(anchor="w", pady=(10, 0))
        rodape = tk.Frame(self, bg=T.CARD)
        rodape.pack(fill="x", pady=(10, 0))
        Botao(rodape, texto_botao, self._salvar).pack(side="right")
        Botao(rodape, "Cancelar", self.destroy, "secundario").pack(side="right", padx=8)
        self._ao_salvar = ao_salvar
        self.bind("<Return>", lambda e: self._salvar())
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(50, self._modal)

    def _modal(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _salvar(self) -> None:
        try:
            self._ao_salvar({k: v.get() for k, v in self.vars.items()})
        except (ValueError, LookupError) as exc:
            self.erro.configure(text=str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.erro.configure(text=f"Não foi possível salvar: {exc}")
            return
        self.destroy()
