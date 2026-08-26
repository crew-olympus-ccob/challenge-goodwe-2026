"""Portal do morador: faturas mensais."""

from __future__ import annotations

import tkinter as tk

from evcharge.db import parse

from .. import theme as T
from ..widgets import Botao, Card, Pagina, Tabela, label


def janela_itens(app, fatura: dict) -> None:
    """Detalhe da fatura: uma linha por recarga."""
    win = tk.Toplevel(app)
    win.title(f"Fatura — {T.competencia(fatura['competencia'])}")
    win.configure(bg=T.CARD, padx=22, pady=18)
    win.transient(app)
    label(win, f"Fatura de {T.competencia(fatura['competencia'])}", T.TEXT, T.fontes().h2).pack(anchor="w")
    label(win, f"{fatura.get('usuario', '')} · Apto {fatura.get('unidade', '')}", T.TEXT_2, T.fontes().pequena).pack(anchor="w", pady=(0, 10))
    t = Tabela(win, [("s", "Sessão", 80, "w"), ("kwh", "kWh", 90, "e"), ("en", "Energia", 100, "e"), ("oc", "Ociosidade", 100, "e")], altura=8)
    t.pack(fill="both", expand=True)
    t.preencher([(str(i["id"]), (f"#{i['sessao_id']}", T.num(i["kwh"], 2), T.dinheiro(i["valor_energia"]), T.dinheiro(i["valor_ociosidade"])), None)
                 for i in app.q.itens_fatura(fatura["id"])])
    tot = tk.Frame(win, bg=T.CARD)
    tot.pack(fill="x", pady=(12, 0))
    label(tot, "Total", T.TEXT, T.fontes().h3).pack(side="left")
    label(tot, T.dinheiro(fatura["valor_total"]), T.ACCENT, T.fontes().h3).pack(side="right")
    Botao(win, "Fechar", win.destroy, "secundario").pack(anchor="e", pady=(14, 0))


class Faturas(Pagina):
    intervalo_ms = 10000

    def montar(self) -> None:
        self.cabecalho("Faturas", "Fechamento mensal das suas recargas: energia + taxa de ociosidade.")
        c = Card(self.conteudo, "Minhas faturas", "▤")
        c.pack(fill="x")
        label(c.body, "Clique duas vezes numa fatura para ver as recargas incluídas.", T.TEXT_3, T.fontes().pequena).pack(anchor="w", pady=(0, 8))
        self.tabela = Tabela(c.body, [("comp", "Competência", 170, "w"), ("kwh", "Energia", 100, "e"), ("en", "Valor energia", 110, "e"),
                                      ("oc", "Ociosidade", 100, "e"), ("tot", "Total", 110, "e"), ("em", "Emitida em", 110, "w"),
                                      ("st", "Status", 100, "w")], altura=10, ao_clicar=self._abrir)
        self.tabela.pack(fill="x")
        self._faturas: dict[str, dict] = {}

    def _abrir(self, iid: str) -> None:
        janela_itens(self.app, self._faturas[iid])

    def atualizar(self) -> None:
        fs = self.app.q.faturas(usuario_id=self.app.usuario["id"])
        self._faturas = {str(f["id"]): f for f in fs}
        self.tabela.preencher([(str(f["id"]), (T.competencia(f["competencia"]), T.kwh(f["total_kwh"]), T.dinheiro(f["valor_energia"]),
                                               T.dinheiro(f["valor_ociosidade"]), T.dinheiro(f["valor_total"]), T.data(parse(f["emitida_em"])),
                                               T.STATUS_TXT[f["status"]]), "verde" if f["status"] == "paga" else None) for f in fs])
