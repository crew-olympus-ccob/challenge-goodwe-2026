"""Painel do síndico: IA 1 (previsão de pico) e IA 2 (detecção de anomalias)."""

from __future__ import annotations

import tkinter as tk
from datetime import timedelta

from evcharge import config
from evcharge.ai import service as ia
from evcharge.db import now_utc, parse

from .. import theme as T
from ..charts import GraficoArea
from ..widgets import Botao, Card, Pagina, Stat, Tabela, aviso, em_segundo_plano, label

REGRAS = {
    "ociosidade_excessiva": "Ociosidade excessiva", "ocioso_em_andamento": "Ocioso (em andamento)",
    "potencia_acima_nominal": "Potência acima do nominal", "energia_incompativel": "kWh incompatível",
    "sessao_longa": "Sessão muito longa", "isolation_forest": "Padrão atípico (Isolation Forest)",
    "rfid_uso_simultaneo": "Cartão em uso simultâneo", "recarga_sem_sessao": "Recarga sem sessão",
}


BOTAO = "↻  Reprocessar agora"


class Inteligencia(Pagina):
    intervalo_ms = 10000

    def montar(self) -> None:
        acoes = self.cabecalho("Inteligência", "IA 1: previsão de pico de demanda  ·  IA 2: detecção de anomalias")
        self.btn = Botao(acoes, BOTAO, self._executar)
        self.btn.pack()
        label(self.conteudo,
              "As duas IAs rodam sozinhas de hora em hora. O botão \"Reprocessar agora\" força a execução na hora, útil depois de "
              "uma demonstração: (1) retreina a previsão com as leituras dos últimos 90 dias e recalcula o pico das próximas 24 h; "
              "(2) retreina o Isolation Forest e reavalia as recargas encerradas nos últimos 90 dias, criando alertas para as "
              "anomalias que ainda não tinham alerta.", T.TEXT_2, wraplength=1000, justify="left", bg=T.BG).pack(anchor="w", pady=(0, 10))
        self.resultado = aviso(self.conteudo, "", "verde")
        self.resultado.configure(wraplength=1000)
        self._aviso_simulado = aviso(self.conteudo, "As métricas abaixo são calculadas sobre histórico SIMULADO. Com dados reais elas devem ser reavaliadas.")
        self._aviso_simulado.pack(fill="x", pady=(0, 18))

        c = Card(self.conteudo, "Previsão das próximas 24 h", "↗")
        c.pack(fill="x", pady=(0, 20))
        linha = tk.Frame(c.body, bg=T.CARD)
        linha.pack(fill="x", pady=(0, 10))
        self.stats = {}
        for i, (k, nome, dest) in enumerate((("modelo", "Modelo escolhido", False), ("pico", "Pico previsto", True),
                                             ("cap", "Capacidade instalada", False), ("mae", "Erro médio (14 dias)", False))):
            linha.columnconfigure(i, weight=1)
            self.stats[k] = Stat(linha, nome, destaque=dest)
            self.stats[k].grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
        self.grafico = GraficoArea(c.body, 280, fmt_valor=lambda v: T.kw(v))
        self.grafico.pack(fill="x")
        label(c.body, "Sugestões de controle de carga", fonte=T.fontes().h3).pack(anchor="w", pady=(14, 6))
        self.sugestoes = tk.Frame(c.body, bg=T.CARD)
        self.sugestoes.pack(fill="x")
        label(c.body, "O limite pode ser aplicado em Carregadores → Limite de corrente.", T.TEXT_3, T.fontes().pequena).pack(anchor="w", pady=(6, 0))

        c2 = Card(self.conteudo, "Anomalias detectadas (90 dias)", "⚠")
        c2.pack(fill="x")
        l2 = tk.Frame(c2.body, bg=T.CARD)
        l2.pack(fill="x", pady=(0, 10))
        self.st2 = {}
        for i, (k, nome, dest) in enumerate((("treino", "Sessões no treino", False), ("if", "Isolation Forest", False),
                                             ("det", "Detecção (simulado)", True), ("n", "Alertas no período", False))):
            l2.columnconfigure(i, weight=1)
            self.st2[k] = Stat(l2, nome, destaque=dest)
            self.st2[k].grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
        self.lbl_regras = label(c2.body, "", T.TEXT_2, wraplength=1000, justify="left")
        self.lbl_regras.pack(anchor="w", pady=(0, 8))
        self.tabela = Tabela(c2.body, [("q", "Quando", 110, "w"), ("sev", "Severidade", 85, "w"), ("r", "Regra", 210, "w"),
                                       ("car", "Carregador", 85, "w"), ("d", "Descrição", 520, "w")], altura=10)
        self.tabela.pack(fill="x")

    def _executar(self) -> None:
        self.btn.habilitar(False, "Executando…")
        db = self.app.sistema.db

        def tarefa(_progresso):
            return ia.executar_anomalias(db, desde=now_utc() - timedelta(days=90)), ia.executar_previsao(db)

        def terminou(r, erro):
            self.btn.habilitar(True, BOTAO)
            if erro:
                self.resultado.configure(text=f"Falha ao reprocessar: {erro}", fg=T.RED, bg=T.RED_SOFT)
            else:
                m, prev = r
                pico = f"pico de {T.kw(prev.pico[1])} às {T.hora(prev.pico[0])}" if prev.pico else "sem dados suficientes"
                self.resultado.configure(
                    fg=T.ACCENT, bg=T.ACCENT_SOFT,
                    text=f"Reprocessado às {T.hora(now_utc())}.  Previsão: modelo {prev.modelo}, {pico}.  "
                         f"Anomalias: {m['sessoes_avaliadas']} recargas avaliadas, {m['achados']} achados, "
                         f"{m['alertas_criados']} alerta(s) novo(s)" + (" (os demais já tinham alerta)." if m["achados"] > m["alertas_criados"] else "."))
            self.resultado.pack(fill="x", pady=(0, 10), before=self._aviso_simulado)
            self.atualizar()

        em_segundo_plano(self, tarefa, terminou)

    def atualizar(self) -> None:
        q = self.app.q
        p = q.previsao()
        aval = p["metricas"].get("avaliacao", {})
        maes = {k: v["mae_kw"] for k, v in aval.items() if "mae_kw" in v}
        self.stats["modelo"].set(p["modelo"] or "—", f"gerado {T.data_hora(p['gerado_em'])}" if p["gerado_em"] else "")
        self.stats["pico"].set(T.kw(p["pico"][1]) if p["pico"] else "—", f"às {T.hora(p['pico'][0])}" if p["pico"] else "")
        self.stats["cap"].set(T.kw(p["capacidade"]))
        self.stats["mae"].set(T.kw(min(maes.values()), 2) if maes else "—", "  ·  ".join(f"{k}: {v} kW" for k, v in maes.items()))
        self.grafico.linhas_ref = [(p["capacidade"], T.RED, "capacidade"),
                                   (p["capacidade"] * config.LIMIAR_CAPACIDADE, T.AMBER, f"{config.LIMIAR_CAPACIDADE:.0%}")]
        self.grafico.dados([T.hora(ts) for ts, _ in p["pontos"]], [v for _, v in p["pontos"]])
        for w in self.sugestoes.winfo_children():
            w.destroy()
        if p["sugestoes"]:
            for s in p["sugestoes"]:
                aviso(self.sugestoes, s.mensagem).pack(fill="x", pady=3)
        else:
            label(self.sugestoes, f"Nenhuma janela acima de {config.LIMIAR_CAPACIDADE:.0%} da capacidade. Nenhuma ação necessária.", T.TEXT_3).pack(anchor="w")

        ex = q.ultima_execucao_anomalias()
        m = ex.get("metricas", {})
        self.st2["treino"].set(str(m.get("sessoes_treino", "—")))
        self.st2["if"].set("treinado" if m.get("isolation_forest") else "não treinado", ex.get("modelo", ""))
        det = m.get("taxa_deteccao_simulada")
        self.st2["det"].set(f"{det:.0%}" if det is not None else "—", "anomalias injetadas detectadas")
        alertas = [a for a in q.alertas("todos", dias=90) if a["tipo"] in ("anomalia", "ocioso")]
        self.st2["n"].set(str(len(alertas)))
        contagem: dict[str, int] = {}
        for a in alertas:
            contagem[a["regra"]] = contagem.get(a["regra"], 0) + 1
        self.lbl_regras.configure(text="   ".join(f"{REGRAS.get(r, r)}: {n}" for r, n in sorted(contagem.items(), key=lambda x: -x[1])))
        self.tabela.preencher([(str(a["id"]), (T.data_hora(parse(a["criado_em"])), T.STATUS_TXT[a["severidade"]], REGRAS.get(a["regra"], a["regra"]),
                                               a["carregador"] or "—", a["descricao"]),
                                {"alta": "vermelho", "media": "ambar", "baixa": "azul"}[a["severidade"]]) for a in alertas[:100]])
