"""Painel do síndico: integrações secundárias (SEMS+ e Open Charge Map)."""

from __future__ import annotations

import tkinter as tk

from evcharge.services import integrations

from .. import theme as T
from ..widgets import Card, Pagina, em_segundo_plano, label


class Integracoes(Pagina):
    intervalo_ms = 600000

    def montar(self) -> None:
        self.cabecalho("Integrações", "Integrações secundárias. Nenhuma delas bloqueia a operação.")
        linha = self.linha(2)
        self.c1 = Card(linha, "SEMS+ (GoodWe)", "⇄")
        self.c1.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.c2 = Card(linha, "Open Charge Map: pontos públicos próximos", "⌖")
        self.c2.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

    def atualizar(self) -> None:
        for w in self.c1.body.winfo_children():
            w.destroy()
        s = integrations.sems_resumo()
        label(self.c1.body, s["fonte"], T.TEXT_3, T.fontes().pequena).pack(anchor="w", pady=(0, 6))
        for c in s["carregadores"]:
            f = tk.Frame(self.c1.body, bg=T.CARD)
            f.pack(fill="x", pady=3)
            label(f, c["codigo"], fonte=T.fontes().corpo_b).pack(side="left")
            label(f, "  " + c["sn"], T.TEXT_3, T.fontes().pequena).pack(side="left")
            label(f, f"firmware {c['firmware']}", T.TEXT_2, T.fontes().pequena).pack(side="right")
        label(self.c1.body, "A integração real depende das credenciais e da documentação da API fornecidas pela GoodWe.",
              T.TEXT_3, T.fontes().pequena, wraplength=420, justify="left").pack(anchor="w", pady=(10, 0))

        for w in self.c2.body.winfo_children():
            w.destroy()
        espera = label(self.c2.body, "Consultando…", T.TEXT_3)
        espera.pack(anchor="w")

        em_segundo_plano(self, lambda _p: integrations.pontos_proximos(),
                         lambda r, erro: self._mostrar_ocm(r or {"pontos": [], "aviso": f"Falha na consulta: {erro}"}))

    def _mostrar_ocm(self, r: dict) -> None:
        for w in self.c2.body.winfo_children():
            w.destroy()
        if not r["pontos"]:
            label(self.c2.body, r.get("aviso", "Nenhum ponto encontrado."), T.TEXT_3, wraplength=420, justify="left").pack(anchor="w")
        for p in r["pontos"]:
            label(self.c2.body, p["nome"] or "—", fonte=T.fontes().corpo_b).pack(anchor="w", pady=(6, 0))
            label(self.c2.body, f"{p['endereco']} · {p['km']} km · {p['conectores']} conector(es)", T.TEXT_3, T.fontes().pequena).pack(anchor="w")
