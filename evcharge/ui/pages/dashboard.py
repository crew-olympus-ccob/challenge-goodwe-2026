"""Portal do morador: Dashboard (equivalente à tela principal do protótipo do Figma)."""

from __future__ import annotations

import tkinter as tk

from .. import theme as T
from ..charts import GraficoLinha
from ..widgets import Badge, Barra, Card, Pagina, Tabela, aviso, label


class Dashboard(Pagina):
    intervalo_ms = 1000

    def montar(self) -> None:
        u = self.app.usuario
        acoes = self.cabecalho("Dashboard", f"Olá, {u['nome'].split()[0]}. Acompanhe suas recargas e seu consumo.")
        # tarifa atual + status do veículo (como no protótipo)
        tar = tk.Frame(acoes, bg=T.BG)
        tar.pack(side="left", padx=(0, 14))
        label(tar, "Tarifa atual", T.TEXT_2, T.fontes().pequena).pack(anchor="e")
        self.lbl_tarifa = label(tar, "—", T.ACCENT, T.fontes().h2)
        self.lbl_tarifa.pack(anchor="e")
        chip = tk.Frame(acoes, bg=T.ACCENT, padx=1, pady=1)
        chip.pack(side="left")
        chip_in = tk.Frame(chip, bg=T.ACCENT_SOFT, padx=14, pady=6)
        chip_in.pack()
        veiculos = self.app.q.usuario(u["id"])["veiculos"]
        label(chip_in, "⚡  " + (veiculos[0]["modelo"] if veiculos else "Sem veículo"), T.TEXT_2, T.fontes().pequena).pack(anchor="w")
        self.lbl_veiculo = label(chip_in, "Não conectado", T.ACCENT, T.fontes().corpo_b)
        self.lbl_veiculo.pack(anchor="w")

        linha = self.linha(2)
        # ----- consumo do mês
        c1 = Card(linha, "Consumo do mês", "↗")
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        n = tk.Frame(c1.body, bg=T.CARD)
        n.pack(anchor="w", pady=(10, 0))
        self.lbl_kwh = label(n, "0", T.TEXT, T.fontes().numero)
        self.lbl_kwh.pack(side="left")
        label(n, " kWh", T.TEXT_2, T.fontes().h2).pack(side="left", anchor="s", pady=(0, 8))
        t = tk.Frame(c1.body, bg=T.CARD)
        t.pack(anchor="w", pady=(6, 0))
        self.lbl_total = label(t, "R$ 0,00", T.ACCENT, T.fontes().numero_p)
        self.lbl_total.pack(side="left")
        label(t, "  total no mês", T.TEXT_2).pack(side="left")
        g = tk.Frame(c1.body, bg=T.CARD)
        g.pack(fill="x", pady=(14, 0))
        self.lbl_det = {}
        for i, (k, nome) in enumerate((("energia", "Energia"), ("ociosidade", "Ociosidade"), ("sessoes", "Recargas"))):
            g.columnconfigure(i, weight=1)
            label(g, nome, T.TEXT_3, T.fontes().pequena).grid(row=0, column=i, sticky="w")
            self.lbl_det[k] = label(g, "—", T.TEXT, T.fontes().corpo_b)
            self.lbl_det[k].grid(row=1, column=i, sticky="w")
        self.lbl_periodo = label(c1.body, "", T.TEXT_3, T.fontes().pequena)
        self.lbl_periodo.pack(anchor="w", pady=(12, 0))

        # ----- recarga ativa
        c2 = Card(linha, "Recarga ativa", "⚡")
        c2.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.badge = Badge(c2.head, "")
        self.badge.pack(side="right")
        self.vazio = label(c2.body, "Nenhuma recarga em andamento.\nAproxime seu cartão RFID do carregador para começar.", T.TEXT_3, justify="center")
        self.ativa = tk.Frame(c2.body, bg=T.CARD)
        top = tk.Frame(self.ativa, bg=T.CARD)
        top.pack(fill="x")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        label(top, "Energia entregue", T.TEXT_2, T.fontes().pequena).grid(row=0, column=0, sticky="w")
        label(top, "Potência", T.TEXT_2, T.fontes().pequena).grid(row=0, column=1, sticky="e")
        self.lbl_ent = label(top, "0", T.TEXT, T.fontes().numero_m)
        self.lbl_ent.grid(row=1, column=0, sticky="w")
        self.lbl_pot = label(top, "0", T.ACCENT, T.fontes().numero_m)
        self.lbl_pot.grid(row=1, column=1, sticky="e")
        self.barra = Barra(self.ativa)
        self.barra.pack(fill="x", pady=(12, 2))
        self.lbl_pct = label(self.ativa, "", T.TEXT_3, T.fontes().pequena)
        self.lbl_pct.pack(anchor="w")
        info = tk.Frame(self.ativa, bg=T.CARD)
        info.pack(fill="x", pady=(10, 0))
        self.lbl_info = {}
        for i, (k, nome) in enumerate((("carregador", "Carregador"), ("tempo", "Tempo"), ("custo", "Custo estimado"))):
            info.columnconfigure(i, weight=1)
            label(info, nome, T.TEXT_3, T.fontes().pequena).grid(row=0, column=i, sticky="w")
            self.lbl_info[k] = label(info, "—", T.ACCENT if k == "custo" else T.TEXT, T.fontes().corpo_b)
            self.lbl_info[k].grid(row=1, column=i, sticky="w")
        self.lbl_aviso = aviso(self.ativa, "")

        # ----- gráfico diário
        c3 = Card(self.conteudo, "Consumo diário", "▦")
        c3.pack(fill="x", pady=(0, 20))
        label(c3.body, "kWh por dia no mês corrente", T.TEXT_2, T.fontes().pequena).pack(anchor="w")
        self.grafico = GraficoLinha(c3.body, 260, fmt_valor=lambda v: T.kwh(v))
        self.grafico.pack(fill="x", pady=(8, 0))

        # ----- recargas recentes
        c4 = Card(self.conteudo, "Recargas recentes", "↻")
        c4.pack(fill="x")
        self.tabela = Tabela(c4.body, [("data", "Data", 120, "w"), ("car", "Carregador", 90, "w"), ("kwh", "Energia", 100, "e"),
                                       ("dur", "Duração", 90, "e"), ("ocio", "Ociosidade", 90, "e"), ("valor", "Valor", 100, "e"),
                                       ("st", "Status", 110, "w")], altura=5)
        self.tabela.pack(fill="x")

    def atualizar(self) -> None:
        q, uid = self.app.q, self.app.usuario["id"]
        t = q.tarifa_atual()
        self.lbl_tarifa.configure(text=f"{T.dinheiro(t.valor_kwh)}/kWh" if t else "—")
        comp = q.competencia_atual()
        c = q.consumo(comp, uid)
        self.lbl_kwh.configure(text=T.num(c["kwh"], 1))
        self.lbl_total.configure(text=T.dinheiro(c["total"]))
        self.lbl_det["energia"].configure(text=T.dinheiro(c["energia"]))
        self.lbl_det["ociosidade"].configure(text=T.dinheiro(c["ociosidade"]), fg=T.AMBER if c["ociosidade"] > 0 else T.TEXT)
        self.lbl_det["sessoes"].configure(text=str(c["sessoes"]))
        self.lbl_periodo.configure(text=T.competencia(comp))
        self.grafico.dados([T.dia(d) for d, _ in c["diario"]], [v for _, v in c["diario"]])

        s = q.sessao_ativa_morador(uid)
        if s is None:
            self.ativa.pack_forget()
            self.vazio.pack(pady=28)
            self.badge.set("", "")
            self.badge.configure(bg=T.CARD)
            self.lbl_veiculo.configure(text="Não conectado")
        else:
            self.vazio.pack_forget()
            self.ativa.pack(fill="x")
            self.badge.set(s["status"])
            self.lbl_veiculo.configure(text=T.STATUS_TXT.get(s["status"], s["status"]))
            self.lbl_ent.configure(text=T.kwh(s["kwh_total"], 2))
            self.lbl_pot.configure(text=T.kw(s["potencia_kw"]))
            pct = s["percentual"]
            self.barra.set((pct or 0) / 100)
            self.lbl_pct.configure(text=f"≈ {T.num(pct, 0)}% da bateria (estimativa pela capacidade cadastrada do veículo)" if pct is not None else "")
            self.lbl_info["carregador"].configure(text=s["carregador"])
            self.lbl_info["tempo"].configure(text=T.minutos(s["duracao_min"]))
            self.lbl_info["custo"].configure(text=T.dinheiro(s["custo_est"]))
            if s["status"] == "CARGA_COMPLETA":
                if s["carencia_restante"] > 0:
                    self.lbl_aviso.configure(text=f"Carga completa! Retire o veículo em até {T.minutos(s['carencia_restante'])} para evitar a taxa de ociosidade.",
                                             fg=T.AMBER, bg=T.AMBER_SOFT)
                else:
                    self.lbl_aviso.configure(text=f"Veículo ocioso há {T.minutos(s['ocioso_min'])}. Taxa de ociosidade acumulada: {T.dinheiro(s['custo_ocio_est'])}.",
                                             fg=T.RED, bg=T.RED_SOFT)
                self.lbl_aviso.pack(fill="x", pady=(12, 0))
            else:
                self.lbl_aviso.pack_forget()

        linhas = []
        for x in q.sessoes(usuario_id=uid, limite=5):
            dur = (x["desconexao"] - x["inicio"]).total_seconds() / 60 if x["desconexao"] else 0
            linhas.append((str(x["id"]), (T.data_hora(x["inicio"]), x["carregador"], T.kwh(x["kwh_total"]), T.minutos(dur) if dur else "—",
                                          T.minutos(x["min_ociosos"]), "em andamento" if x["status"] in ("AUTORIZADA", "CARREGANDO", "CARGA_COMPLETA") else T.dinheiro(x["custo_total"]), T.STATUS_TXT.get(x["status"], x["status"])),
                           "ambar" if x["min_ociosos"] > 15 else None))
        self.tabela.preencher(linhas)
