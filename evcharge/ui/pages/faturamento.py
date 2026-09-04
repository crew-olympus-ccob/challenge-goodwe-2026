"""Painel do síndico: faturas mensais e tarifas."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk

from evcharge import config
from evcharge.core.invoices import gerar_faturas

from .. import theme as T
from ..widgets import Botao, Card, Dialogo, Pagina, Stat, Tabela, label
from .faturas import janela_itens


class Faturamento(Pagina):
    intervalo_ms = 10000

    def montar(self) -> None:
        acoes = self.cabecalho("Faturas e tarifas", "Fechamento mensal (gerado automaticamente no início do mês) e tarifas vigentes.")
        atual = self.app.q.competencia_atual()
        self._meses = {T.competencia(T.mudar_competencia(atual, -i)): T.mudar_competencia(atual, -i) for i in range(12)}
        self.f_mes = ttk.Combobox(acoes, values=list(self._meses), state="readonly", style="Dark.TCombobox", width=20)
        self.f_mes.set(T.competencia(T.mudar_competencia(atual, -1)))
        self.f_mes.bind("<<ComboboxSelected>>", lambda e: self.atualizar())
        self.f_mes.pack(side="left", padx=6)
        Botao(acoes, "Gerar / atualizar faturas", self._gerar).pack(side="left")

        linha = self.linha(3)
        self.stats = {k: Stat(linha, n, destaque=d) for k, n, d in (("n", "Faturas", False), ("total", "Total faturado", True), ("pagas", "Pagas", False))}
        for i, s in enumerate(self.stats.values()):
            s.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
        c = Card(self.conteudo, "Faturas da competência", "▤")
        c.pack(fill="x", pady=(0, 20))
        label(c.body, "Dois cliques numa fatura mostram as recargas incluídas.", T.TEXT_3, T.fontes().pequena).pack(anchor="w", pady=(0, 8))
        self.tabela = Tabela(c.body, [("un", "Unidade", 70, "w"), ("mor", "Morador", 180, "w"), ("kwh", "Energia", 100, "e"),
                                      ("en", "Valor energia", 110, "e"), ("oc", "Ociosidade", 100, "e"), ("tot", "Total", 110, "e"),
                                      ("st", "Status", 90, "w")], altura=11, ao_clicar=lambda iid: janela_itens(self.app, self._faturas[iid]))
        self.tabela.pack(fill="x")
        Botao(c.body, "Marcar como paga / em aberto", self._pagar, "secundario").pack(anchor="e", pady=(10, 0))
        self.msg = label(c.body, "", T.ACCENT, T.fontes().pequena)
        self.msg.pack(anchor="w")

        c2 = Card(self.conteudo, "Tarifas", "$", acao=lambda m: Botao(m, "+  Nova tarifa", self._nova_tarifa, "secundario"))
        c2.pack(fill="x")
        self.t_tar = Tabela(c2.body, [("vig", "Vigência", 260, "w"), ("kwh", "R$/kWh", 100, "e"), ("car", "Carência", 90, "e"),
                                      ("oc", "Ociosidade (R$/min)", 140, "e"), ("teto", "Teto por recarga", 130, "e")], altura=4)
        self.t_tar.pack(fill="x")
        self._faturas: dict[str, dict] = {}

    def _gerar(self) -> None:
        comp = self._meses[self.f_mes.get()]
        n = gerar_faturas(self.app.sistema.db, comp, config.tz())
        self.msg.configure(text=f"{n} fatura(s) geradas para {T.competencia(comp)}.")
        self.atualizar()

    def _pagar(self) -> None:
        iid = self.tabela.selecionado()
        if iid:
            self.app.q.alternar_pagamento(int(iid))
            self.atualizar()

    def _nova_tarifa(self) -> None:
        def salvar(v):
            inicio = datetime.strptime(v["inicio"], "%d/%m/%Y %H:%M").replace(tzinfo=config.tz())
            self.app.q.nova_tarifa(v["kwh"].replace(",", "."), v["taxa"].replace(",", "."), int(v["car"]), v["teto"].replace(",", ".") or None, inicio)
            self.atualizar()

        Dialogo(self, "Nova tarifa", [("kwh", "R$ por kWh", "0,95", None, False), ("car", "Carência (min)", "15", None, False),
                                      ("taxa", "Ociosidade (R$ por minuto)", "0,50", None, False), ("teto", "Teto por recarga (R$, opcional)", "60", None, False),
                                      ("inicio", "Início da vigência (dd/mm/aaaa hh:mm)", datetime.now().strftime("%d/%m/%Y 00:00"), None, False)],
                salvar, "Salvar", "A tarifa anterior é encerrada automaticamente. Cada recarga usa a tarifa vigente no início dela.")

    def atualizar(self) -> None:
        comp = self._meses[self.f_mes.get()]
        fs = self.app.q.faturas(competencia=comp)
        self._faturas = {str(f["id"]): f for f in fs}
        self.stats["n"].set(str(len(fs)))
        self.stats["total"].set(T.dinheiro(sum(f["valor_total"] for f in fs)))
        self.stats["pagas"].set(str(sum(f["status"] == "paga" for f in fs)))
        self.tabela.preencher([(str(f["id"]), (f["unidade"], f["usuario"], T.kwh(f["total_kwh"]), T.dinheiro(f["valor_energia"]),
                                               T.dinheiro(f["valor_ociosidade"]), T.dinheiro(f["valor_total"]), T.STATUS_TXT[f["status"]]),
                                "verde" if f["status"] == "paga" else None) for f in fs])
        linhas = []
        for t in self.app.q.tarifas():
            vig = f"{T.data(t.vigencia_inicio)} {T.hora(t.vigencia_inicio)} → " + (f"{T.data(t.vigencia_fim)} {T.hora(t.vigencia_fim)}" if t.vigencia_fim else "vigente")
            linhas.append((str(t.id), (vig, T.dinheiro(t.valor_kwh), f"{t.carencia_min} min", T.dinheiro(t.taxa_ociosidade_min),
                                       T.dinheiro(t.teto_ociosidade) if t.teto_ociosidade is not None else "sem teto"),
                           "verde" if t.vigencia_fim is None else "cinza"))
        self.t_tar.preencher(linhas)
