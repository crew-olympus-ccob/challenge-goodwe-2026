"""Painel do síndico: visão geral em tempo real."""

from __future__ import annotations

import tkinter as tk

from evcharge import config

from .. import theme as T
from ..charts import GraficoBarras, GraficoLinha
from ..widgets import Badge, Botao, Card, Pagina, Stat, label


class VisaoGeral(Pagina):
    intervalo_ms = 1000

    def montar(self) -> None:
        acoes = self.cabecalho("Visão geral", "")
        if self.app.sistema.cenarios is not None:
            self.btn_demo = Botao(acoes, "▶  Iniciar demonstração", self._demo)
            self.btn_demo.pack()

        linha = self.linha(5)
        self.stats = {}
        for i, (k, nome, dest) in enumerate((("kwh", "Energia no mês", False), ("receita", "Receita no mês", True),
                                             ("sessoes", "Recargas no mês", False), ("pot", "Potência agora", False),
                                             ("alertas", "Alertas abertos", False))):
            self.stats[k] = Stat(linha, nome, destaque=dest)
            self.stats[k].grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))

        l2 = self.linha(3)
        self.c_ativas = Card(l2, "Sessões em andamento", "≋")
        self.c_ativas.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=(0, 10))
        self.c_car = Card(l2, "Carregadores", "⚡")
        self.c_car.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        self.status_car: dict[int, tuple] = {}

        l3 = self.linha(3)
        c_d = Card(l3, "Consumo do condomínio — 30 dias", "▦")
        c_d.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=(0, 10))
        self.g_dias = GraficoLinha(c_d.body, 240, fmt_valor=lambda v: T.kwh(v))
        self.g_dias.pack(fill="x")
        c_b = Card(l3, "Energia por carregador (mês)", "▥")
        c_b.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        self.g_car = GraficoBarras(c_b.body, 240, fmt_valor=lambda v: T.kwh(v))
        self.g_car.pack(fill="x")

        self.c_prev = Card(self.conteudo, "Previsão de pico (próximas 24 h)", "✦")
        self.c_prev.pack(fill="x")
        self.lbl_prev = label(self.c_prev.body, "", wraplength=1000, justify="left")
        self.lbl_prev.pack(anchor="w")

    def _demo(self) -> None:
        cen = self.app.sistema.cenarios
        if cen.running():
            return
        cen.start("apresentacao", velocidade=config.VELOCIDADE_DEMO)
        self.btn_demo.habilitar(False, "Demonstração em andamento…")

    def atualizar(self) -> None:
        q = self.app.q
        vg = q.visao_geral()
        self.subtitulo.configure(text=f"Condomínio · {T.competencia(vg['competencia'])}")
        m = vg["mes"]
        self.stats["kwh"].set(T.kwh(m["kwh"], 0))
        self.stats["receita"].set(T.dinheiro(m["total"]), f"{T.dinheiro(m['ociosidade'])} de ociosidade")
        self.stats["sessoes"].set(str(m["sessoes"]))
        cap = vg["capacidade"] or 1
        self.stats["pot"].set(T.kw(vg["potencia_atual"]), f"{vg['potencia_atual'] / cap:.0%} de {T.kw(cap)} instalados")
        self.stats["alertas"].set(str(vg["alertas_abertos"]), "ver em Alertas", T.AMBER if vg["alertas_abertos"] else T.TEXT)
        if self.app.sistema.cenarios is not None:
            rodando = self.app.sistema.cenarios.running()
            self.btn_demo.habilitar(not rodando, "Demonstração em andamento…" if rodando else "▶  Iniciar demonstração")

        for w in self.c_ativas.body.winfo_children():
            w.destroy()
        ativas = q.sessoes_ativas()
        if not ativas:
            label(self.c_ativas.body, "Nenhum carregador em uso agora.", T.TEXT_3).pack(pady=24)
        for s in ativas:
            f = tk.Frame(self.c_ativas.body, bg=T.CARD)
            f.pack(fill="x", pady=5)
            label(f, f" {s['carregador']} ", T.TEXT, T.fontes().corpo_b, bg=T.BORDER).pack(side="left")
            label(f, f"  {s['usuario']}", fonte=T.fontes().corpo_b).pack(side="left")
            label(f, f" · Apto {s['unidade']}", T.TEXT_3).pack(side="left")
            label(f, T.dinheiro(s["custo_est"]), fonte=T.fontes().corpo_b).pack(side="right")
            if s["status"] == "CARGA_COMPLETA":
                label(f, f"ocioso {T.minutos(s['ocioso_min'])}   ", T.AMBER if s["carencia_restante"] > 0 else T.RED).pack(side="right")
            label(f, f"{T.minutos(s['duracao_min'])}   ", T.TEXT_2).pack(side="right")
            label(f, f"{T.kw(s['potencia_kw'])}   ", T.ACCENT).pack(side="right")
            label(f, f"{T.kwh(s['kwh_total'], 2)}   ", fonte=T.fontes().corpo_b).pack(side="right")
            b = Badge(f, s["status"])
            b.pack(side="right", padx=10)

        carregadores = q.carregadores()
        if [c["id"] for c in carregadores] != list(self.status_car):  # carregador novo ou removido
            for w in self.c_car.body.winfo_children():
                w.destroy()
            self.status_car = {}
            for c in carregadores:
                f = tk.Frame(self.c_car.body, bg=T.CARD)
                f.pack(fill="x", pady=5)
                label(f, c["codigo"], fonte=T.fontes().corpo_b).pack(side="left")
                b = Badge(f, c["status"])
                b.pack(side="right")
                pot = label(f, "", T.ACCENT, T.fontes().pequena)
                pot.pack(side="right", padx=10)
                self.status_car[c["id"]] = (b, pot)
        for c in carregadores:
            if c["id"] in self.status_car:
                b, pot = self.status_car[c["id"]]
                b.set(c["status"] if c["ativo"] else "CANCELADA", None if c["ativo"] else "Desativado")
                pot.configure(text=T.kw(c["potencia_atual_kw"]) if c["potencia_atual_kw"] else "")

        self.g_dias.dados([T.dia(d) for d, _ in vg["diario_30d"]], [v for _, v in vg["diario_30d"]])
        self.g_car.dados([c for c, _ in vg["por_carregador"]], [v for _, v in vg["por_carregador"]])

        if self.app.tk.call("clock", "seconds") % 15 == 0 or not self.lbl_prev.cget("text"):
            p = q.previsao()
            if p["pico"]:
                ts, kwp = p["pico"]
                txt = f"Pico previsto de {T.kw(kwp)} às {T.hora(ts)}."
                txt += (" " + p["sugestoes"][0].mensagem) if p["sugestoes"] else " Dentro da capacidade, nenhuma ação necessária."
            else:
                txt = "Ainda sem previsão. Abra Inteligência e clique em “Executar agora”."
            self.lbl_prev.configure(text=txt)
