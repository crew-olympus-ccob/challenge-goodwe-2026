"""Portal do morador: histórico de recargas, mês a mês."""

from __future__ import annotations

from .. import theme as T
from ..charts import GraficoLinha
from ..widgets import Botao, Card, Pagina, Stat, Tabela, label


class Historico(Pagina):
    intervalo_ms = 5000

    def montar(self) -> None:
        self.comp = self.app.q.competencia_atual()
        acoes = self.cabecalho("Histórico de recargas", "Todas as suas sessões, mês a mês.")
        Botao(acoes, "‹", lambda: self._mes(-1), "secundario").pack(side="left")
        self.lbl_mes = label(acoes, "", T.TEXT, T.fontes().corpo_b, width=18)
        self.lbl_mes.pack(side="left", padx=6)
        self.btn_prox = Botao(acoes, "›", lambda: self._mes(1), "secundario")
        self.btn_prox.pack(side="left")

        linha = self.linha(4)
        self.stats = {}
        for i, (k, nome, dest) in enumerate((("kwh", "Energia", False), ("total", "Total", True), ("sessoes", "Recargas", False), ("ocio", "Taxa de ociosidade", False))):
            self.stats[k] = Stat(linha, nome, destaque=dest)
            self.stats[k].grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
        c = Card(self.conteudo, "Consumo diário", "▦")
        c.pack(fill="x", pady=(0, 20))
        self.grafico = GraficoLinha(c.body, 230, fmt_valor=lambda v: T.kwh(v))
        self.grafico.pack(fill="x")
        c2 = Card(self.conteudo, "Sessões", "↻")
        c2.pack(fill="x")
        self.tabela = Tabela(c2.body, [("ini", "Início", 110, "w"), ("car", "Carregador", 80, "w"), ("vei", "Veículo", 130, "w"),
                                       ("kwh", "Energia", 90, "e"), ("pot", "Pot. máx.", 80, "e"), ("ocio", "Ociosidade", 85, "e"),
                                       ("en", "Energia R$", 90, "e"), ("oc", "Ociosid. R$", 90, "e"), ("tot", "Total", 90, "e"),
                                       ("st", "Status", 100, "w")], altura=12)
        self.tabela.pack(fill="x")

    def _mes(self, delta: int) -> None:
        novo = T.mudar_competencia(self.comp, delta)
        if novo <= self.app.q.competencia_atual():
            self.comp = novo
            self.atualizar()

    def atualizar(self) -> None:
        q, uid = self.app.q, self.app.usuario["id"]
        self.lbl_mes.configure(text=T.competencia(self.comp))
        self.btn_prox.habilitar(self.comp < q.competencia_atual())
        c = q.consumo(self.comp, uid)
        self.stats["kwh"].set(T.kwh(c["kwh"]))
        self.stats["total"].set(T.dinheiro(c["total"]))
        self.stats["sessoes"].set(str(c["sessoes"]))
        self.stats["ocio"].set(T.dinheiro(c["ociosidade"]), f"{T.minutos(c['min_ociosos'])} ociosos no mês")
        self.grafico.dados([T.dia(d) for d, _ in c["diario"]], [v for _, v in c["diario"]])
        linhas = []
        for s in q.sessoes(usuario_id=uid, competencia=self.comp, limite=500):
            linhas.append((str(s["id"]), (T.data_hora(s["inicio"]), s["carregador"], s["veiculo"] or "—", T.kwh(s["kwh_total"], 2),
                                          T.kw(s["potencia_max_kw"]), T.minutos(s["min_ociosos"]), T.dinheiro(s["custo_energia"]),
                                          T.dinheiro(s["custo_ociosidade"]), T.dinheiro(s["custo_total"]), T.STATUS_TXT.get(s["status"], s["status"])),
                           "ambar" if s["custo_ociosidade"] > 0 else None))
        self.tabela.preencher(linhas)
