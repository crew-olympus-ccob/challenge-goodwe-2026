"""Painel do síndico: alertas (ociosidade, anomalias da IA, falhas, comunicação)."""

from __future__ import annotations

from tkinter import ttk

from evcharge.db import parse

from .. import theme as T
from ..widgets import Botao, Card, Pagina, Tabela, label

TIPOS = {"ocioso": "Ociosidade", "anomalia": "Anomalia", "falha": "Falha", "rfid_negado": "RFID negado", "comunicacao": "Comunicação"}
SITUACOES = {"Abertos": "abertos", "Resolvidos": "resolvidos", "Todos": "todos"}


class Alertas(Pagina):
    intervalo_ms = 3000

    def montar(self) -> None:
        acoes = self.cabecalho("Alertas", "Ociosidade, anomalias da IA, falhas e comunicação com os carregadores.")
        self.f_sit = ttk.Combobox(acoes, values=list(SITUACOES), state="readonly", style="Dark.TCombobox", width=12)
        self.f_sit.set("Abertos")
        self.f_sit.pack(side="left", padx=4)
        self.f_tipo = ttk.Combobox(acoes, values=["Todos os tipos", *TIPOS.values()], state="readonly", style="Dark.TCombobox", width=16)
        self.f_tipo.set("Todos os tipos")
        self.f_tipo.pack(side="left", padx=4)
        for cb in (self.f_sit, self.f_tipo):
            cb.bind("<<ComboboxSelected>>", lambda e: self.atualizar())
        c = Card(self.conteudo)
        c.pack(fill="both", expand=True)
        barra = c.body
        topo = label(barra, "Selecione um alerta e clique em Resolver (ou dê dois cliques).", T.TEXT_3, T.fontes().pequena)
        topo.pack(anchor="w", pady=(0, 8))
        self.tabela = Tabela(c.body, [("q", "Quando", 110, "w"), ("sev", "Severidade", 85, "w"), ("tipo", "Tipo", 105, "w"),
                                      ("car", "Carregador", 85, "w"), ("desc", "Descrição", 520, "w"), ("st", "Situação", 90, "w")],
                             altura=18, ao_clicar=lambda iid: self._alternar())
        self.tabela.pack(fill="both", expand=True)
        Botao(c.body, "✓  Resolver / reabrir selecionado", self._alternar).pack(anchor="e", pady=(10, 0))
        self._resolvidos: dict[str, bool] = {}

    def _alternar(self) -> None:
        iid = self.tabela.selecionado()
        if iid:
            self.app.q.resolver_alerta(int(iid), not self._resolvidos.get(iid, False))
            self.atualizar()

    def atualizar(self) -> None:
        tipo = next((k for k, v in TIPOS.items() if v == self.f_tipo.get()), None)
        dados = self.app.q.alertas(SITUACOES[self.f_sit.get()], tipo)
        self._resolvidos = {str(a["id"]): bool(a["resolvido_em"]) for a in dados}
        self.tabela.preencher([(str(a["id"]), (T.data_hora(parse(a["criado_em"])), T.STATUS_TXT[a["severidade"]], TIPOS.get(a["tipo"], a["tipo"]),
                                               a["carregador"] or "—", a["descricao"], "Resolvido" if a["resolvido_em"] else "Aberto"),
                                "cinza" if a["resolvido_em"] else {"alta": "vermelho", "media": "ambar", "baixa": "azul"}[a["severidade"]])
                               for a in dados])
