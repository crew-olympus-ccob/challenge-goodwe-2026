"""Painel do síndico: todas as sessões, com filtros."""

from __future__ import annotations

from tkinter import ttk

from .. import theme as T
from ..widgets import Card, Pagina, Tabela

FILTROS = {"Todas": None, "Em andamento": "ATIVAS", "Finalizadas": "FINALIZADA", "Com falha": "FALHA", "Canceladas": "CANCELADA"}


class Sessoes(Pagina):
    intervalo_ms = 3000

    def montar(self) -> None:
        acoes = self.cabecalho("Sessões", "Monitoramento de todas as recargas.")
        self.f_status = ttk.Combobox(acoes, values=list(FILTROS), state="readonly", style="Dark.TCombobox", width=16)
        self.f_status.set("Todas")
        self.f_status.pack(side="left", padx=4)
        self._carregadores = {"Todos os carregadores": None} | {c["codigo"]: c["id"] for c in self.app.q.carregadores()}
        self.f_car = ttk.Combobox(acoes, values=list(self._carregadores), state="readonly", style="Dark.TCombobox", width=20)
        self.f_car.set("Todos os carregadores")
        self.f_car.pack(side="left", padx=4)
        for cb in (self.f_status, self.f_car):
            cb.bind("<<ComboboxSelected>>", lambda e: self.atualizar())
        c = Card(self.conteudo)
        c.pack(fill="both", expand=True)
        self.tabela = Tabela(c.body, [("id", "#", 50, "e"), ("ini", "Início", 110, "w"), ("car", "Carregador", 85, "w"),
                                      ("mor", "Morador", 170, "w"), ("kwh", "Energia", 90, "e"), ("pot", "Pot. máx.", 80, "e"),
                                      ("oc", "Ociosidade", 85, "e"), ("tot", "Total", 95, "e"), ("ori", "Origem", 85, "w"),
                                      ("st", "Status", 110, "w")], altura=20)
        self.tabela.pack(fill="both", expand=True)

    def atualizar(self) -> None:
        linhas = []
        for s in self.app.q.sessoes(status=FILTROS[self.f_status.get()], carregador_id=self._carregadores[self.f_car.get()]):
            tag = {"FALHA": "vermelho", "CARREGANDO": "verde", "CARGA_COMPLETA": "ambar", "AUTORIZADA": "azul"}.get(s["status"])
            linhas.append((str(s["id"]), (s["id"], T.data_hora(s["inicio"]), s["carregador"], f"{s['usuario']} · {s['unidade']}",
                                          T.kwh(s["kwh_total"], 2), T.kw(s["potencia_max_kw"]), T.minutos(s["min_ociosos"]),
                                          T.dinheiro(s["custo_total"]), "simulado" if s["origem"] == "historico" else "carregador",
                                          T.STATUS_TXT.get(s["status"], s["status"])), tag))
        self.tabela.preencher(linhas)
