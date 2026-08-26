"""Portal do morador: dados, regras de cobrança, cartões e veículos."""

from __future__ import annotations

import tkinter as tk

from .. import theme as T
from ..widgets import Badge, Card, Pagina, label


class Perfil(Pagina):
    intervalo_ms = 30000

    def montar(self) -> None:
        self.cabecalho("Configurações", "Seus dados, cartões e veículos. Alterações são feitas pela administração.")
        self.grade = self.linha(2)

    def atualizar(self) -> None:
        for w in self.grade.winfo_children():
            w.destroy()
        u = self.app.q.usuario(self.app.usuario["id"])
        t = self.app.q.tarifa_atual()

        c1 = Card(self.grade, "Meus dados", "☺")
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 20))
        for rot, val in (("Nome", u["nome"]), ("E-mail", u["email"]), ("Unidade", u["unidade"] or "—")):
            f = tk.Frame(c1.body, bg=T.CARD)
            f.pack(fill="x", pady=3)
            label(f, rot, T.TEXT_3, width=10, anchor="w").pack(side="left")
            label(f, val).pack(side="left")

        c2 = Card(self.grade, "Regras de cobrança", "$")
        c2.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 20))
        if t:
            textos = [
                f"Energia: {T.dinheiro(t.valor_kwh)} por kWh.",
                f"Depois que a carga termina, você tem {t.carencia_min} min de carência para retirar o veículo.",
                f"Após a carência: {T.dinheiro(t.taxa_ociosidade_min)} por minuto" + (f" (máximo {T.dinheiro(t.teto_ociosidade)} por recarga)." if t.teto_ociosidade else "."),
                "A taxa existe para liberar as vagas compartilhadas para outros moradores.",
            ]
            for i, x in enumerate(textos):
                label(c2.body, "•  " + x, T.TEXT_3 if i == 3 else T.TEXT, wraplength=430, justify="left").pack(anchor="w", pady=2)

        c3 = Card(self.grade, "Cartões RFID", "▣")
        c3.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        for cartao in u["cartoes"]:
            f = tk.Frame(c3.body, bg=T.CARD)
            f.pack(fill="x", pady=4)
            label(f, cartao["uid"], fonte=T.fontes().corpo_b).pack(side="left")
            label(f, "  " + (cartao["apelido"] or ""), T.TEXT_3).pack(side="left")
            b = Badge(f)
            b.set("paga" if cartao["ativo"] else "FALHA", "Ativo" if cartao["ativo"] else "Bloqueado")
            b.pack(side="right")

        c4 = Card(self.grade, "Veículos", "⚡")
        c4.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        for v in u["veiculos"]:
            f = tk.Frame(c4.body, bg=T.CARD)
            f.pack(fill="x", pady=4)
            label(f, v["modelo"], fonte=T.fontes().corpo_b).pack(side="left")
            label(f, f"{v['placa'] or '—'}" + (f" · {T.num(v['capacidade_kwh'], 1)} kWh" if v["capacidade_kwh"] else ""), T.TEXT_2).pack(side="right")
