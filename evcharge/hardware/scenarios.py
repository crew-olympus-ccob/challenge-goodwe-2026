"""Cenários prontos de uso dos carregadores (demonstração e testes).

Cada cenário "age como o morador": passa o cartão, conecta o carro, espera
e desconecta. Rodam em threads; os tempos são em segundos SIMULADOS.
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field

from .simulator import Simulator

UIDS = [f"AB12{i:04d}" for i in range(1, 11)]
CARTAO_DESCONHECIDO = "FFFFFFFF"


class ScenarioError(Exception):
    pass


@dataclass
class Run:
    id: int
    nome: str
    status: str = "executando"
    log: list[str] = field(default_factory=list)
    erro: str | None = None
    thread: threading.Thread | None = None


class ScenarioRunner:
    def __init__(self, sim: Simulator, resync_delay_s: float = 8.0):
        self.sim = sim
        self.runs: list[Run] = []
        self._ids = itertools.count(1)
        self._stop = threading.Event()
        self.resync_delay_s = resync_delay_s

    # ------------------------------------------------------------------ utilidades
    def _wait(self, pred, timeout_sim_s: float, what: str, minimo_real_s: float = 20.0) -> None:
        """Espera `pred()`. O prazo é em tempo simulado, mas nunca menor que `minimo_real_s`
        segundos reais: com o relógio acelerado, a resposta do sistema (que lê os
        carregadores a cada 1 s real) poderia "demorar" horas simuladas."""
        deadline = self.sim.clock.now() + timeout_sim_s
        limite_real = time.monotonic() + minimo_real_s
        while not pred():
            if self._stop.is_set():
                raise ScenarioError("interrompido")
            if self.sim.clock.now() > deadline and time.monotonic() > limite_real:
                raise ScenarioError(f"tempo esgotado esperando: {what}")
            time.sleep(0.02)

    def _sleep(self, sim_s: float) -> None:
        if not self.sim.clock.sleep(sim_s, self._stop):
            raise ScenarioError("interrompido")

    def _authorize(self, code: str, uid: str, log) -> bool:
        ch = self.sim.chargers[code]
        self.sim.tap(code, uid)
        log(f"{code}: cartão {uid} aproximado")
        self._wait(lambda: not ch.pending_auth, 120, "resposta de autorização")
        log(f"{code}: {'autorizado' if ch.authorized else 'NEGADO'}")
        return ch.authorized

    def _cycle(self, code, uid, log, kwh, idle_min, vehicle_kw=11.0, fault_after_min=None):
        ch = self.sim.chargers[code]
        if not self._authorize(code, uid, log):
            return
        self._sleep(30)
        self.sim.plug(code, kwh, vehicle_kw)
        log(f"{code}: veículo conectado pedindo {kwh:g} kWh")
        if fault_after_min is not None:
            self._sleep(fault_after_min * 60)
            self.sim.fault(code)
            log(f"{code}: FALHA durante a recarga")
            self._sleep(120)
            self.sim.unplug(code)
            self.sim.clear_fault(code)
            log(f"{code}: desconectado e falha limpa")
            return
        horas = kwh / max(0.5, min(vehicle_kw, ch.max_power_w / 1000)) * 2 + 1
        self._wait(lambda: ch.vehicle is not None and ch.vehicle.complete, horas * 3600, "carga completa")
        log(f"{code}: carga completa; veículo segue conectado por {idle_min:g} min")
        self._sleep(idle_min * 60)
        self.sim.unplug(code)
        log(f"{code}: veículo desconectado")

    # ------------------------------------------------------------------ cenários
    def normal(self, log, carregador="CH-01", uid=UIDS[0], kwh=40.0, ocioso_min=5.0):
        self._cycle(carregador, uid, log, kwh, ocioso_min)

    def ocioso(self, log, carregador="CH-02", uid=UIDS[1], kwh=15.0, ocioso_min=90.0):
        self._cycle(carregador, uid, log, kwh, ocioso_min)

    def anomalia(self, log, carregador="CH-03", uid=UIDS[2], kwh=12.0):
        ch = self.sim.chargers[carregador]
        ch.set_anomaly(power_multiplier=1.35)
        log(f"{carregador}: medidor com defeito (potência reportada ×1,35)")
        try:
            self._cycle(carregador, uid, log, kwh, 5.0)
        finally:
            ch.set_anomaly(1.0, 1.0)

    def cartao_desconhecido(self, log, carregador="CH-03", uid=CARTAO_DESCONHECIDO):
        if self._authorize(carregador, uid, log):
            raise ScenarioError("cartão desconhecido foi aceito")

    def falha(self, log, carregador="CH-03", uid=UIDS[2], kwh=20.0):
        self._cycle(carregador, uid, log, kwh, 0, 7.4, fault_after_min=20)

    def pico(self, log, kwh=20.0):
        threads = [
            threading.Thread(target=self._cycle, args=(code, uid, log, kwh, 10.0), daemon=True)
            for code, uid in zip(self.sim.chargers, UIDS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def apresentacao(self, log, velocidade=60.0):
        """Roteiro do pitch (~4 min reais a 60×): uma situação de cada, ao mesmo tempo."""
        self.sim.clock.set_speed(velocidade)
        log(f"relógio acelerado para {velocidade:g}×")
        c1, c2, c3 = list(self.sim.chargers)[:3]
        erros: list[BaseException] = []

        def guard(fn, *a, **k):
            try:
                fn(*a, **k)
            except BaseException as exc:  # noqa: BLE001
                erros.append(exc)

        def terceiro():
            self.cartao_desconhecido(log, c3)
            self._sleep(20 * 60)
            self.anomalia(log, c3, UIDS[2], 12.0)

        threads = [
            threading.Thread(target=guard, args=(self.normal, log, c1, UIDS[0], 30.0, 5.0), daemon=True),
            threading.Thread(target=guard, args=(self.ocioso, log, c2, UIDS[1], 15.0, 75.0), daemon=True),
            threading.Thread(target=guard, args=(terceiro,), daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if erros:
            raise erros[0]
        log("roteiro concluído")

    CATALOGO = {
        "apresentacao": "Roteiro de pitch: recarga normal, multa por ociosidade, cartão negado e anomalia (~4 min)",
        "normal": "Cartão → carrega 40 kWh → desconecta em 5 min",
        "ocioso": "Carga completa e o carro fica 90 min parado (gera multa e alerta)",
        "anomalia": "Medidor reporta potência acima do nominal",
        "cartao_desconhecido": "Cartão não cadastrado (deve ser negado)",
        "falha": "Carregador entra em falha no meio da recarga",
        "pico": "Todos os carregadores ao mesmo tempo",
    }

    # ------------------------------------------------------------------ execução
    def start(self, nome: str, **params) -> Run:
        if nome not in self.CATALOGO:
            raise KeyError(nome)
        run = Run(next(self._ids), nome)

        def log(msg: str) -> None:
            ts = time.strftime("%H:%M", time.localtime(self.sim.clock.now()))
            run.log.append(f"[{ts}] {msg}")

        def target():
            try:
                getattr(self, nome)(log, **params)
                run.status = "concluido"
            except Exception as exc:  # noqa: BLE001
                run.status, run.erro = "erro", str(exc)
                log(f"erro: {exc}")
            finally:
                timer = threading.Timer(self.resync_delay_s, self._maybe_resync)
                timer.daemon = True
                timer.start()

        run.thread = threading.Thread(target=target, name=f"cenario-{nome}", daemon=True)
        self.runs.append(run)
        run.thread.start()
        return run

    def running(self) -> bool:
        return any(r.thread and r.thread.is_alive() for r in self.runs)

    def _maybe_resync(self) -> None:
        """Ao fim das demonstrações o relógio volta ao horário real (e 1×)."""
        if not self.running() and (self.sim.clock.speed != 1 or abs(self.sim.clock.offset_seconds()) > 60):
            self.sim.resync_clock()

    def stop(self) -> None:
        self._stop.set()
