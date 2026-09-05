"""Painel do síndico: controle do simulador dos carregadores (camada física mockada)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from evcharge.hardware import scenarios as S

from .. import theme as T
from ..widgets import Badge, Barra, Botao, Card, Pagina, aviso, label

VELOCIDADES = {"1× (tempo real)": 1, "10×": 10, "30×": 30, "60× (1 h por minuto)": 60, "120×": 120, "300×": 300}


class Simulador(Pagina):
    intervalo_ms = 500

    def montar(self) -> None:
        acoes = self.cabecalho("Simulador de carregadores", "Servidores Modbus TCP que imitam o GoodWe HCA G2. Use para demonstrações e testes.")
        self.sim = self.app.sistema.simulador
        self.cen = self.app.sistema.cenarios
        if self.sim is None:
            aviso(self.conteudo, "Simulador desativado nesta execução.", "vermelho").pack(fill="x")
            return
        label(acoes, "Velocidade do relógio  ", T.TEXT_2).pack(side="left")
        self.f_vel = ttk.Combobox(acoes, values=list(VELOCIDADES), state="readonly", style="Dark.TCombobox", width=20)
        self.f_vel.set("1× (tempo real)")
        self.f_vel.bind("<<ComboboxSelected>>", lambda e: self.sim.clock.set_speed(VELOCIDADES[self.f_vel.get()]))
        self.f_vel.pack(side="left")
        self.lbl_relogio = aviso(self.conteudo, "", "azul")

        self.grade = tk.Frame(self.conteudo, bg=T.BG)
        self.grade.pack(fill="x")
        for i in range(3):
            self.grade.columnconfigure(i, weight=1, uniform="s")
        self.cards: dict[str, dict] = {}

        linha = self.linha(2, pady=(0, 0))
        c = Card(linha, "Cenários", "▶")
        c.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.f_cen = ttk.Combobox(c.body, values=list(S.ScenarioRunner.CATALOGO), state="readonly", style="Dark.TCombobox", width=24)
        self.f_cen.set("apresentacao")
        self.f_cen.pack(anchor="w")
        self.lbl_desc = label(c.body, "", T.TEXT_2, wraplength=440, justify="left")
        self.lbl_desc.pack(anchor="w", pady=8)
        self.f_cen.bind("<<ComboboxSelected>>", lambda e: self.lbl_desc.configure(text=S.ScenarioRunner.CATALOGO[self.f_cen.get()]))
        self.lbl_desc.configure(text=S.ScenarioRunner.CATALOGO["apresentacao"])
        Botao(c.body, "▶  Executar cenário", self._executar).pack(anchor="w")
        label(c.body, "Os carregadores usados em cada cenário estão na documentação (docs/roteiro-apresentacao.md).", T.TEXT_3, T.fontes().pequena, wraplength=440, justify="left").pack(anchor="w", pady=(8, 0))
        c2 = Card(linha, "Execuções", "≋")
        c2.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.txt = tk.Text(c2.body, height=12, bg=T.CARD, fg=T.TEXT_2, font=T.fontes().pequena, relief="flat", wrap="word", highlightthickness=0)
        self.txt.pack(fill="both", expand=True)

    def _montar_cards(self) -> None:
        for w in self.grade.winfo_children():
            w.destroy()
        self.cards = {code: self._card(self.grade, code, i) for i, code in enumerate(self.sim.chargers)}

    def _card(self, master, code: str, idx: int) -> dict:
        card = Card(master, f"{code} · porta {self.sim.ports.get(code)}", "⚡")
        card.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=(0 if idx % 3 == 0 else 10, 0), pady=(0, 20))
        w = {"badge": Badge(card.head)}
        w["badge"].pack(side="right")
        top = tk.Frame(card.body, bg=T.CARD)
        top.pack(fill="x")
        w["pot"] = label(top, "", T.ACCENT, T.fontes().numero_m)
        w["pot"].pack(side="left")
        w["med"] = label(top, "", T.TEXT_2, T.fontes().pequena)
        w["med"].pack(side="right")
        w["barra"] = Barra(card.body, 6)
        w["barra"].pack(fill="x", pady=(8, 2))
        w["veic"] = label(card.body, "", T.TEXT_3, T.fontes().pequena)
        w["veic"].pack(anchor="w")
        w["evento"] = label(card.body, "", T.TEXT_2, T.fontes().pequena, wraplength=300, justify="left")
        w["evento"].pack(anchor="w", pady=(4, 8))
        f = tk.Frame(card.body, bg=T.CARD)
        f.pack(fill="x")
        uid = ttk.Combobox(f, values=self._cartoes(), state="readonly", style="Dark.TCombobox", width=11)
        uid.set(S.UIDS[idx % len(S.UIDS)])
        uid.pack(side="left")
        Botao(f, "Passar cartão", lambda: self.sim.tap(code, uid.get()), "secundario").pack(side="left", padx=6)
        f2 = tk.Frame(card.body, bg=T.CARD)
        f2.pack(fill="x", pady=(6, 0))
        kwh = tk.StringVar(value="30")
        tk.Entry(f2, textvariable=kwh, width=5, bg=T.INPUT, fg=T.TEXT, insertbackground=T.TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=T.BORDER, font=T.fontes().corpo).pack(side="left", ipady=4)
        label(f2, " kWh ", T.TEXT_3, T.fontes().pequena).pack(side="left")
        w["plug"] = Botao(f2, "Conectar", lambda: self._plug(code, kwh.get()), "secundario")
        w["plug"].pack(side="left")
        w["falha"] = Botao(f2, "Falha", lambda: self._falha(code), "perigo")
        w["falha"].pack(side="right")
        return w

    def _cartoes(self) -> list[str]:
        """Cartões cadastrados (inclusive os criados em Moradores) + um desconhecido para testar a recusa."""
        uids = [c["uid"] for u in self.app.q.usuarios() for c in u["cartoes"]]
        return uids + [S.CARTAO_DESCONHECIDO]

    def _plug(self, code: str, kwh: str) -> None:
        if self.sim.chargers[code].connected:
            self.sim.unplug(code)
        else:
            try:
                self.sim.plug(code, max(0.5, float(kwh.replace(",", "."))), 11.0)
            except ValueError:
                pass

    def _falha(self, code: str) -> None:
        if self.sim.chargers[code].fault_code:
            self.sim.clear_fault(code)
        else:
            self.sim.fault(code)

    def _executar(self) -> None:
        nome = self.f_cen.get()
        self.cen.start(nome, **({"velocidade": max(60, self.sim.clock.speed)} if nome == "apresentacao" else {}))

    def atualizar(self) -> None:
        if self.sim is None:
            return
        off = self.sim.clock.offset_seconds()
        if abs(off) > 120:
            self.lbl_relogio.configure(text=f"Relógio simulado {abs(off) / 60:.0f} min {'à frente do' if off > 0 else 'atrás do'} horário real "
                                            "(efeito da aceleração). Ele volta ao normal sozinho quando os cenários terminam.")
            self.lbl_relogio.pack(fill="x", pady=(0, 16), before=self.grade)
        else:
            self.lbl_relogio.pack_forget()
        if list(self.sim.chargers) != list(self.cards):  # carregador virtual criado em Carregadores
            self._montar_cards()
        rotulo = next((k for k, v in VELOCIDADES.items() if v == self.sim.clock.speed), f"{self.sim.clock.speed:g}×")
        if self.f_vel.get() != rotulo and self.focus_get() is not self.f_vel:
            self.f_vel.set(rotulo)
        for s in self.sim.snapshot():
            w = self.cards[s["code"]]
            w["badge"].set(s["status"])
            w["pot"].configure(text=T.kw(s["power_kw"], 2))
            w["med"].configure(text=f"medidor\n{T.kwh(s['energy_kwh'], 2)}", justify="right")
            w["barra"].set(s["delivered_kwh"] / s["needed_kwh"] if s["needed_kwh"] else 0)
            w["veic"].configure(text=f"veículo: {T.kwh(s['delivered_kwh'], 2)} de {T.kwh(s['needed_kwh'])}" if s["connected"] else "sem veículo conectado")
            w["evento"].configure(text=s["last_event"])
            w["plug"].configure(text="Desconectar" if s["connected"] else "Conectar")
            w["falha"].configure(text="Limpar falha" if s["fault"] else "Falha")
        linhas = []
        for r in reversed(self.cen.runs[-6:]):
            linhas.append(f"#{r.id} {r.nome} — {r.status}")
            linhas += [f"    {x}" for x in r.log[-5:]]
            if r.erro:
                linhas.append(f"    erro: {r.erro}")
        texto = "\n".join(linhas) or "Nenhum cenário executado ainda."
        if self.txt.get("1.0", "end-1c") != texto:
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", texto)
