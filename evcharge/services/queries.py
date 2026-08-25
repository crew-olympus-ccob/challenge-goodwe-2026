"""Consultas e ações usadas pelas telas (a interface nunca escreve SQL)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from evcharge import config
from evcharge.ai.forecast import sugerir_controle
from evcharge.core.auth import hash_senha
from evcharge.core.billing import calcular_custo, competencia_de, limites_competencia, q2
from evcharge.core.repo import ATIVAS, Repo, sessao_de, tarifa_de
from evcharge.db import Database, dec, iso, now_utc, parse


class Consultas:
    def __init__(self, db: Database):
        self.db = db
        self.repo = Repo(db)
        self.tz = config.tz()

    # ================================================================ geral
    def tarifa_atual(self):
        row = self.db.one("SELECT * FROM tarifas WHERE vigencia_fim IS NULL ORDER BY vigencia_inicio DESC LIMIT 1")
        return tarifa_de(row) if row else None

    def competencia_atual(self) -> str:
        return competencia_de(now_utc(), self.tz)

    def _filtro_mes(self, competencia: str):
        ini, fim = limites_competencia(competencia, self.tz)
        return iso(ini), iso(fim)

    def consumo(self, competencia: str, usuario_id: int | None = None) -> dict:
        ini, fim = self._filtro_mes(competencia)
        sql = "SELECT * FROM sessoes WHERE inicio >= ? AND inicio < ? AND status IN ('FINALIZADA','FALHA')"
        params: list = [ini, fim]
        if usuario_id is not None:
            sql += " AND usuario_id = ?"
            params.append(usuario_id)
        sessoes = [sessao_de(r) for r in self.db.query(sql, params)]
        dias: dict[date, float] = {}
        d0, d1 = limites_competencia(competencia, self.tz)
        d = d0.date()
        while d < d1.date():
            dias[d] = 0.0
            d += timedelta(days=1)
        for s in sessoes:
            dia = s["inicio"].astimezone(self.tz).date()
            dias[dia] = dias.get(dia, 0.0) + s["kwh_total"]
        energia = sum((s["custo_energia"] for s in sessoes), Decimal(0))
        ocio = sum((s["custo_ociosidade"] for s in sessoes), Decimal(0))
        return {
            "kwh": sum(s["kwh_total"] for s in sessoes),
            "energia": q2(energia),
            "ociosidade": q2(ocio),
            "total": q2(energia + ocio),
            "sessoes": len(sessoes),
            "min_ociosos": sum(s["min_ociosos"] for s in sessoes),
            "diario": sorted(dias.items()),
        }

    # ================================================================ sessões
    def sessoes(self, usuario_id=None, status=None, carregador_id=None, competencia=None, limite=300) -> list[dict]:
        sql = """SELECT s.*, c.codigo AS carregador, u.nome AS usuario, u.unidade, v.modelo AS veiculo
                 FROM sessoes s JOIN carregadores c ON c.id = s.carregador_id JOIN usuarios u ON u.id = s.usuario_id
                 LEFT JOIN veiculos v ON v.id = s.veiculo_id WHERE 1=1"""
        params: list = []
        if usuario_id is not None:
            sql += " AND s.usuario_id = ?"
            params.append(usuario_id)
        if status == "ATIVAS":
            sql += f" AND s.status IN {ATIVAS}"
        elif status:
            sql += " AND s.status = ?"
            params.append(status)
        if carregador_id:
            sql += " AND s.carregador_id = ?"
            params.append(carregador_id)
        if competencia:
            ini, fim = self._filtro_mes(competencia)
            sql += " AND s.inicio >= ? AND s.inicio < ?"
            params += [ini, fim]
        sql += " ORDER BY s.inicio DESC LIMIT ?"
        params.append(limite)
        return [sessao_de(r) for r in self.db.query(sql, params)]

    def ao_vivo(self, sessao: dict) -> dict:
        """Sessão ativa com custo estimado. "Agora" = última leitura do carregador (relógio do equipamento)."""
        ch = self.db.one("SELECT * FROM carregadores WHERE id = ?", (sessao["carregador_id"],))
        agora = parse(ch["ultima_leitura"]) or now_utc()
        ocioso = max(0.0, (agora - sessao["fim_carga"]).total_seconds() / 60) if sessao["status"] == "CARGA_COMPLETA" and sessao["fim_carga"] else 0.0
        try:
            tarifa = self.repo.tarifa_em(sessao["inicio"])
            custo = calcular_custo(sessao["kwh_total"], round(ocioso, 2), tarifa)
            carencia = tarifa.carencia_min
        except LookupError:
            custo, carencia = None, 15
        cap = self.db.scalar("SELECT capacidade_kwh FROM veiculos WHERE id = ?", (sessao["veiculo_id"],)) if sessao.get("veiculo_id") else None
        return {
            **sessao,
            "carregador": ch["codigo"],
            "potencia_kw": ch["potencia_atual_kw"] if sessao["status"] == "CARREGANDO" else 0.0,
            "duracao_min": max(0.0, (agora - sessao["inicio"]).total_seconds() / 60),
            "ocioso_min": ocioso,
            "carencia_min": carencia,
            "carencia_restante": max(0.0, carencia - ocioso),
            "custo_energia_est": q2(custo.energia) if custo else Decimal(0),
            "custo_ocio_est": q2(custo.ociosidade) if custo else Decimal(0),
            "custo_est": q2(custo.total) if custo else Decimal(0),
            "percentual": min(100.0, sessao["kwh_total"] / cap * 100) if cap else None,
        }

    def sessao_ativa_morador(self, usuario_id: int) -> dict | None:
        s = self.repo.sessao_ativa_usuario(usuario_id)
        return self.ao_vivo(s) if s else None

    def sessoes_ativas(self) -> list[dict]:
        rows = self.db.query(f"""SELECT s.*, u.nome AS usuario, u.unidade FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id
                                 WHERE s.status IN {ATIVAS} ORDER BY s.inicio""")
        out = []
        for r in rows:
            s = sessao_de(r)
            out.append(self.ao_vivo(s))
        return out

    # ================================================================ admin
    def visao_geral(self) -> dict:
        comp = self.competencia_atual()
        mes = self.consumo(comp)
        hoje = now_utc().astimezone(self.tz).date()
        ini30 = datetime(hoje.year, hoje.month, hoje.day, tzinfo=self.tz) - timedelta(days=29)
        rows = self.db.query("SELECT inicio, kwh_total, carregador_id FROM sessoes WHERE inicio >= ? AND status IN ('FINALIZADA','FALHA')", (iso(ini30),))
        dias = {(ini30 + timedelta(days=i)).date(): 0.0 for i in range(30)}
        for r in rows:
            d = parse(r["inicio"]).astimezone(self.tz).date()
            if d in dias:
                dias[d] += r["kwh_total"]
        ini_mes, fim_mes = self._filtro_mes(comp)
        por_carregador = self.db.query(
            """SELECT c.codigo, COALESCE(SUM(s.kwh_total), 0) AS kwh FROM carregadores c
               LEFT JOIN sessoes s ON s.carregador_id = c.id AND s.inicio >= ? AND s.inicio < ? AND s.status IN ('FINALIZADA','FALHA')
               GROUP BY c.id ORDER BY c.codigo""", (ini_mes, fim_mes))
        cap = self.db.scalar("SELECT COALESCE(SUM(potencia_max_kw),0) FROM carregadores WHERE ativo=1") or 0
        return {
            "competencia": comp,
            "mes": mes,
            "potencia_atual": self.db.scalar("SELECT COALESCE(SUM(potencia_atual_kw),0) FROM carregadores WHERE ativo=1") or 0,
            "capacidade": cap,
            "alertas_abertos": self.db.scalar("SELECT COUNT(*) FROM alertas WHERE resolvido_em IS NULL"),
            "diario_30d": sorted(dias.items()),
            "por_carregador": [(r["codigo"], r["kwh"]) for r in por_carregador],
        }

    def carregadores(self) -> list[dict]:
        return [dict(r) for r in self.db.query(
            f"""SELECT c.*, (SELECT u.nome FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id
                             WHERE s.carregador_id = c.id AND s.status IN {ATIVAS} LIMIT 1) AS em_uso_por
                FROM carregadores c ORDER BY c.codigo""")]

    def definir_limite(self, carregador_id: int, amps: int) -> None:
        if 0 < amps < 6:
            raise ValueError("O limite mínimo é 6 A (norma IEC 61851), ou 0 para remover o limite.")
        self.db.execute("UPDATE carregadores SET limite_corrente_a = ? WHERE id = ?", (amps, carregador_id))

    def alternar_carregador(self, carregador_id: int) -> None:
        self.db.execute("UPDATE carregadores SET ativo = 1 - ativo WHERE id = ?", (carregador_id,))

    def novo_carregador(self, codigo: str, host: str, porta: int, potencia: float, local: str) -> None:
        codigo = codigo.strip().upper()
        if not codigo:
            raise ValueError("Informe o código do carregador.")
        if self.db.scalar("SELECT 1 FROM carregadores WHERE codigo = ?", (codigo,)):
            raise ValueError(f"Já existe um carregador {codigo}.")
        if potencia <= 0:
            raise ValueError("Informe a potência nominal em kW.")
        self.db.execute("INSERT INTO carregadores (codigo, host, porta, potencia_max_kw, localizacao) VALUES (?,?,?,?,?)",
                        (codigo.strip().upper(), host.strip(), int(porta), float(potencia), local.strip() or None))

    # ---------------------------------------------------------------- alertas
    def alertas(self, situacao: str = "abertos", tipo: str | None = None, dias: int | None = None) -> list[dict]:
        sql = "SELECT a.*, c.codigo AS carregador FROM alertas a LEFT JOIN carregadores c ON c.id = a.carregador_id WHERE 1=1"
        params: list = []
        if situacao == "abertos":
            sql += " AND a.resolvido_em IS NULL"
        elif situacao == "resolvidos":
            sql += " AND a.resolvido_em IS NOT NULL"
        if tipo:
            sql += " AND a.tipo = ?"
            params.append(tipo)
        if dias:
            sql += " AND a.criado_em >= ?"
            params.append(iso(now_utc() - timedelta(days=dias)))
        sql += " ORDER BY a.criado_em DESC LIMIT 300"
        return [dict(r) for r in self.db.query(sql, params)]

    def resolver_alerta(self, alerta_id: int, resolvido: bool = True) -> None:
        self.db.execute("UPDATE alertas SET resolvido_em = ? WHERE id = ?", (iso(now_utc()) if resolvido else None, alerta_id))

    # ---------------------------------------------------------------- faturas e tarifas
    def faturas(self, usuario_id: int | None = None, competencia: str | None = None) -> list[dict]:
        sql = "SELECT f.*, u.nome AS usuario, u.unidade FROM faturas f JOIN usuarios u ON u.id = f.usuario_id WHERE 1=1"
        params: list = []
        if usuario_id is not None:
            sql += " AND f.usuario_id = ?"
            params.append(usuario_id)
        if competencia:
            sql += " AND f.competencia = ?"
            params.append(competencia)
        sql += " ORDER BY f.competencia DESC, u.unidade"
        out = []
        for r in self.db.query(sql, params):
            f = dict(r)
            for k in ("valor_energia", "valor_ociosidade", "valor_total"):
                f[k] = dec(f[k])
            out.append(f)
        return out

    def itens_fatura(self, fatura_id: int) -> list[dict]:
        return [dict(r) for r in self.db.query("SELECT * FROM itens_fatura WHERE fatura_id = ? ORDER BY id", (fatura_id,))]

    def alternar_pagamento(self, fatura_id: int) -> None:
        self.db.execute("UPDATE faturas SET status = CASE status WHEN 'paga' THEN 'emitida' ELSE 'paga' END WHERE id = ?", (fatura_id,))

    def tarifas(self):
        return [tarifa_de(r) for r in self.db.query("SELECT * FROM tarifas ORDER BY vigencia_inicio DESC")]

    def nova_tarifa(self, valor_kwh: str, taxa_min: str, carencia: int, teto: str | None, inicio: datetime) -> None:
        if Decimal(valor_kwh) <= 0 or Decimal(taxa_min) < 0 or carencia < 0:
            raise ValueError("Valores inválidos para a tarifa.")
        if self.db.scalar("SELECT 1 FROM tarifas WHERE vigencia_inicio >= ?", (iso(inicio),)):
            raise ValueError("Já existe tarifa com vigência igual ou posterior a essa data.")
        with self.db.transaction() as c:
            c.execute("UPDATE tarifas SET vigencia_fim = ? WHERE vigencia_fim IS NULL", (iso(inicio),))
            c.execute("INSERT INTO tarifas (valor_kwh, taxa_ociosidade_min, carencia_min, teto_ociosidade, vigencia_inicio) VALUES (?,?,?,?,?)",
                      (str(Decimal(valor_kwh)), str(Decimal(taxa_min)), int(carencia), str(Decimal(teto)) if teto else None, iso(inicio)))

    # ---------------------------------------------------------------- moradores
    def usuario(self, usuario_id: int) -> dict:
        u = dict(self.db.one("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)))
        u["cartoes"] = [dict(r) for r in self.db.query("SELECT * FROM cartoes_rfid WHERE usuario_id = ? ORDER BY id", (usuario_id,))]
        u["veiculos"] = [dict(r) for r in self.db.query("SELECT * FROM veiculos WHERE usuario_id = ? ORDER BY id", (usuario_id,))]
        return u

    def usuarios(self) -> list[dict]:
        return [self.usuario(r["id"]) for r in self.db.query("SELECT id FROM usuarios ORDER BY perfil DESC, unidade, nome")]

    def novo_usuario(self, nome: str, email: str, senha: str, unidade: str) -> int:
        email = email.strip().lower()
        if len(nome.strip()) < 2 or "@" not in email or len(senha) < 6:
            raise ValueError("Preencha nome, um e-mail válido e senha com pelo menos 6 caracteres.")
        if self.db.scalar("SELECT 1 FROM usuarios WHERE email = ?", (email,)):
            raise ValueError("E-mail já cadastrado.")
        return self.db.execute("INSERT INTO usuarios (nome, email, senha_hash, unidade) VALUES (?,?,?,?)",
                               (nome.strip(), email, hash_senha(senha), unidade.strip() or None))

    def novo_cartao(self, usuario_id: int, uid: str) -> None:
        uid = uid.strip().upper()
        if not uid.isalnum() or not 4 <= len(uid) <= 16:
            raise ValueError("UID deve ter de 4 a 16 letras/números.")
        if self.db.scalar("SELECT 1 FROM cartoes_rfid WHERE uid = ?", (uid,)):
            raise ValueError("Esse cartão já está vinculado a outra pessoa.")
        self.db.execute("INSERT INTO cartoes_rfid (uid, usuario_id) VALUES (?,?)", (uid, usuario_id))

    def alternar_cartao(self, cartao_id: int) -> None:
        self.db.execute("UPDATE cartoes_rfid SET ativo = 1 - ativo WHERE id = ?", (cartao_id,))

    def novo_veiculo(self, usuario_id: int, modelo: str, placa: str, bateria: str) -> None:
        if len(modelo.strip()) < 2:
            raise ValueError("Informe o modelo do veículo.")
        placa = placa.strip().upper().replace("-", "") or None
        if placa and self.db.scalar("SELECT 1 FROM veiculos WHERE placa = ?", (placa,)):
            raise ValueError("Placa já cadastrada.")
        self.db.execute("INSERT INTO veiculos (usuario_id, modelo, placa, capacidade_kwh) VALUES (?,?,?,?)",
                        (usuario_id, modelo.strip(), placa, float(bateria) if bateria.strip() else None))

    def alternar_usuario(self, usuario_id: int) -> None:
        with self.db.transaction() as c:
            c.execute("UPDATE usuarios SET ativo = 1 - ativo WHERE id = ? AND perfil <> 'admin'", (usuario_id,))

    # ---------------------------------------------------------------- IA
    def previsao(self) -> dict:
        rows = self.db.query("SELECT * FROM previsoes ORDER BY ts")
        pontos = [(parse(r["ts"]), r["kw"]) for r in rows]
        cap = self.db.scalar("SELECT COALESCE(SUM(potencia_max_kw),0) FROM carregadores WHERE ativo=1") or 0
        n = self.db.scalar("SELECT COUNT(*) FROM carregadores WHERE ativo=1") or 0
        ex = self.db.one("SELECT * FROM execucoes_ia WHERE tipo='previsao' ORDER BY id DESC LIMIT 1")
        return {
            "modelo": rows[0]["modelo"] if rows else None,
            "gerado_em": parse(rows[0]["gerado_em"]) if rows else None,
            "pontos": pontos,
            "pico": max(pontos, key=lambda p: p[1]) if pontos else None,
            "capacidade": cap,
            "sugestoes": sugerir_controle(pontos, cap, n, config.LIMIAR_CAPACIDADE, self.tz),
            "metricas": json.loads(ex["metricas"]) if ex else {},
        }

    def ultima_execucao_anomalias(self) -> dict:
        ex = self.db.one("SELECT * FROM execucoes_ia WHERE tipo='anomalia' ORDER BY id DESC LIMIT 1")
        return {"modelo": ex["modelo"], "metricas": json.loads(ex["metricas"]), "em": parse(ex["executado_em"])} if ex else {}
