"""Painel do síndico: carregadores (status, limite de corrente, cadastro)."""

from __future__ import annotations

import tkinter as tk

from .. import theme as T
from ..widgets import Badge, Botao, Card, Dialogo, Pagina, label


TIPOS = ["Simulado (demonstração)", "Equipamento real (IP na rede)"]


class Carregadores(Pagina):
    intervalo_ms = 2000

    def montar(self) -> None:
        acoes = self.cabecalho("Carregadores", "GoodWe HCA G2 via Modbus TCP. Trocar o simulador pelo equipamento real é só mudar o endereço IP.")
        Botao(acoes, "+  Novo carregador", self._novo).pack()
        self.grade = tk.Frame(self.conteudo, bg=T.BG)
        self.grade.pack(fill="x")
        for i in range(3):
            self.grade.columnconfigure(i, weight=1, uniform="c")
        self._cards: dict[int, dict] = {}

    def _card(self, c: dict, idx: int) -> dict:
        card = Card(self.grade, c["codigo"], "⚡")
        card.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=(0 if idx % 3 == 0 else 10, 0), pady=(0, 20))
        w = {"card": card, "badge": Badge(card.head, c["status"])}
        w["badge"].pack(side="right")
        w["local"] = label(card.body, c["localizacao"] or "—", T.TEXT_2)
        w["local"].pack(anchor="w")
        linha = tk.Frame(card.body, bg=T.CARD)
        linha.pack(fill="x", pady=(12, 8))
        label(linha, "Potência agora", T.TEXT_3, T.fontes().pequena).grid(row=0, column=0, sticky="w")
        label(linha, "Nominal", T.TEXT_3, T.fontes().pequena).grid(row=0, column=1, sticky="e")
        linha.columnconfigure(0, weight=1)
        linha.columnconfigure(1, weight=1)
        w["pot"] = label(linha, "", T.ACCENT, T.fontes().numero_m)
        w["pot"].grid(row=1, column=0, sticky="w")
        label(linha, T.kw(c["potencia_max_kw"]), fonte=T.fontes().corpo_b).grid(row=1, column=1, sticky="e")
        w["info"] = {}
        for k, nome in (("end", "Endereço"), ("ult", "Última leitura"), ("uso", "Em uso por"), ("lim", "Limite de corrente")):
            f = tk.Frame(card.body, bg=T.CARD)
            f.pack(fill="x", pady=1)
            label(f, nome, T.TEXT_3, T.fontes().pequena).pack(side="left")
            w["info"][k] = label(f, "", T.TEXT, T.fontes().pequena)
            w["info"][k].pack(side="right")
        bts = tk.Frame(card.body, bg=T.CARD)
        bts.pack(fill="x", pady=(12, 0))
        Botao(bts, "Limite de corrente", lambda cid=c["id"], cod=c["codigo"]: self._limite(cid, cod), "secundario").pack(side="left")
        w["ativar"] = Botao(bts, "Desativar", lambda cid=c["id"]: (self.app.q.alternar_carregador(cid), self.atualizar()), "secundario")
        w["ativar"].pack(side="left", padx=8)
        return w

    def _limite(self, cid: int, codigo: str) -> None:
        Dialogo(self, f"Limite de corrente — {codigo}", [("amps", "Corrente máxima (A); 0 = sem limite", "16", None, False)],
                lambda v: (self.app.q.definir_limite(cid, int(v["amps"] or 0)), self.atualizar()), "Aplicar",
                "Controle de carga: o sistema escreve o limite no registrador do carregador. Mínimo de 6 A (norma IEC 61851).")

    def _novo(self) -> None:
        proximo = f"CH-{len(self.app.q.carregadores()) + 1:02d}"

        def salvar(v):
            pot = float(v["pot"].replace(",", ".") or 0)
            if v["tipo"].startswith("Simulado"):
                self.app.sistema.criar_carregador_simulado(v["codigo"], pot, v["local"])
            else:
                if not v["host"].strip():
                    raise ValueError("Informe o endereço IP do carregador.")
                self.app.q.novo_carregador(v["codigo"], v["host"], int(v["porta"] or 502), pot, v["local"])
            self.atualizar()

        d = Dialogo(self, "Novo carregador", [
            ("tipo", "Tipo", TIPOS[0], TIPOS, False),
            ("codigo", "Código", proximo, None, False),
            ("pot", "Potência nominal (kW)", "11", None, False),
            ("local", "Localização", "", None, False),
            ("host", "Endereço IP (só equipamento real)", "", None, False),
            ("porta", "Porta Modbus (só equipamento real)", "502", None, False),
        ], salvar, "Cadastrar",
            "Simulado: cria um carregador virtual que já aparece Disponível e pode ser usado no Simulador, "
            "nas sessões, alertas e faturas. Equipamento real: o sistema tenta se comunicar com o IP informado; "
            "enquanto não houver resposta ele aparece Offline.")

        def alternar_tipo(*_):
            real = not d.vars["tipo"].get().startswith("Simulado")
            for chave in ("host", "porta"):
                d.campos[chave].configure(state="normal" if real else "disabled", disabledbackground=T.CARD)

        d.vars["tipo"].trace_add("write", alternar_tipo)
        alternar_tipo()

    def atualizar(self) -> None:
        dados = self.app.q.carregadores()
        if [c["id"] for c in dados] != list(self._cards):
            for w in self.grade.winfo_children():
                w.destroy()
            self._cards = {c["id"]: self._card(c, i) for i, c in enumerate(dados)}
        for c in dados:
            w = self._cards[c["id"]]
            w["badge"].set(c["status"] if c["ativo"] else "CANCELADA", None if c["ativo"] else "Desativado")
            w["pot"].configure(text=T.kw(c["potencia_atual_kw"]))
            from evcharge.db import parse

            w["info"]["end"].configure(text=f"{c['host']}:{c['porta']}")
            w["info"]["ult"].configure(text=T.data_hora(parse(c["ultima_leitura"])))
            w["info"]["uso"].configure(text=c["em_uso_por"] or "—")
            w["info"]["lim"].configure(text=f"{c['limite_corrente_a']} A" if c["limite_corrente_a"] else "sem limite")
            w["ativar"].configure(text="Desativar" if c["ativo"] else "Ativar")
