"""Painel do síndico: moradores, cartões RFID e veículos."""

from __future__ import annotations

import tkinter as tk

from .. import theme as T
from ..widgets import Botao, Card, Dialogo, Pagina, Tabela, label


class Moradores(Pagina):
    intervalo_ms = 10000

    def montar(self) -> None:
        acoes = self.cabecalho("Moradores", "Cadastro de moradores, cartões RFID e veículos.")
        Botao(acoes, "+  Novo morador", self._novo).pack()
        c = Card(self.conteudo)
        c.pack(fill="both", expand=True)
        label(c.body, "Selecione um morador para vincular cartão, cadastrar veículo ou desativar.", T.TEXT_3, T.fontes().pequena).pack(anchor="w", pady=(0, 8))
        self.tabela = Tabela(c.body, [("nome", "Nome", 170, "w"), ("email", "E-mail", 210, "w"), ("un", "Unidade", 70, "w"),
                                      ("perfil", "Perfil", 80, "w"), ("cart", "Cartões RFID", 200, "w"), ("vei", "Veículos", 200, "w"),
                                      ("st", "Situação", 80, "w")], altura=14)
        self.tabela.pack(fill="both", expand=True)
        bts = tk.Frame(c.body, bg=T.CARD)
        bts.pack(fill="x", pady=(10, 0))
        Botao(bts, "Vincular cartão", self._cartao, "secundario").pack(side="left")
        Botao(bts, "Cadastrar veículo", self._veiculo, "secundario").pack(side="left", padx=8)
        Botao(bts, "Bloquear/desbloquear cartões", self._bloquear, "secundario").pack(side="left")
        Botao(bts, "Ativar/desativar morador", self._alternar, "perigo").pack(side="right")
        self.msg = label(c.body, "", T.AMBER, T.fontes().pequena)
        self.msg.pack(anchor="w", pady=(6, 0))
        self._usuarios: dict[str, dict] = {}

    def _sel(self) -> dict | None:
        iid = self.tabela.selecionado()
        if not iid:
            self.msg.configure(text="Selecione um morador na tabela primeiro.")
            return None
        self.msg.configure(text="")
        return self._usuarios[iid]

    def _novo(self) -> None:
        Dialogo(self, "Novo morador", [("nome", "Nome", "", None, False), ("email", "E-mail", "", None, False),
                                       ("senha", "Senha inicial (mín. 6)", "", None, True), ("unidade", "Unidade", "", None, False)],
                lambda v: (self.app.q.novo_usuario(v["nome"], v["email"], v["senha"], v["unidade"]), self.atualizar()), "Cadastrar")

    def _cartao(self) -> None:
        u = self._sel()
        if u:
            Dialogo(self, f"Novo cartão — {u['nome']}", [("uid", "UID do cartão", "", None, False)],
                    lambda v: (self.app.q.novo_cartao(u["id"], v["uid"]), self.atualizar()), "Vincular")

    def _veiculo(self) -> None:
        u = self._sel()
        if u:
            Dialogo(self, f"Novo veículo — {u['nome']}", [("modelo", "Modelo", "", None, False), ("placa", "Placa", "", None, False),
                                                          ("bat", "Bateria (kWh), usada para estimar o % de carga", "", None, False)],
                    lambda v: (self.app.q.novo_veiculo(u["id"], v["modelo"], v["placa"], v["bat"].replace(",", ".")), self.atualizar()), "Cadastrar")

    def _bloquear(self) -> None:
        u = self._sel()
        if u:
            for c in u["cartoes"]:
                self.app.q.alternar_cartao(c["id"])
            self.atualizar()

    def _alternar(self) -> None:
        u = self._sel()
        if u:
            if u["perfil"] == "admin":
                self.msg.configure(text="A conta de administrador não pode ser desativada por aqui.")
                return
            self.app.q.alternar_usuario(u["id"])
            self.atualizar()

    def atualizar(self) -> None:
        us = self.app.q.usuarios()
        self._usuarios = {str(u["id"]): u for u in us}
        self.tabela.preencher([(str(u["id"]), (u["nome"], u["email"], u["unidade"] or "—", "admin" if u["perfil"] == "admin" else "morador",
                                               "  ".join(c["uid"] + ("" if c["ativo"] else " (bloq.)") for c in u["cartoes"]) or "—",
                                               ", ".join(v["modelo"] for v in u["veiculos"]) or "—", "Ativo" if u["ativo"] else "Inativo"),
                                None if u["ativo"] else "cinza") for u in us])
