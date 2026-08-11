"""Simulador dos carregadores: um servidor Modbus TCP por carregador virtual.

Substitui o hardware (HCA G2, leitor RFID, cabo) para desenvolvimento e
demonstração. O sistema conversa com ele exatamente como conversaria com o
equipamento real: lendo e escrevendo registradores Modbus.
"""

from __future__ import annotations

import logging
import threading
import time

from . import registers as R
from .charger import VehicleProfile, VirtualCharger
from .modbus import ModbusServer, RegisterBank

log = logging.getLogger(__name__)


class SimClock:
    """Relógio do equipamento, acelerável (speed=60 → 1 h simulada por minuto real)."""

    def __init__(self, speed: float = 1.0):
        self._speed = float(speed)
        self._base_sim = time.time()
        self._base_mono = time.monotonic()
        self._lock = threading.Lock()

    @property
    def speed(self) -> float:
        return self._speed

    def now(self) -> float:
        with self._lock:
            return self._base_sim + (time.monotonic() - self._base_mono) * self._speed

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("velocidade deve ser > 0")
        current = self.now()
        with self._lock:
            self._base_sim, self._base_mono, self._speed = current, time.monotonic(), float(speed)

    def resync(self) -> None:
        """Volta ao horário real e à velocidade 1× (só com todos os carregadores livres)."""
        with self._lock:
            self._base_sim, self._base_mono, self._speed = time.time(), time.monotonic(), 1.0

    def offset_seconds(self) -> float:
        return self.now() - time.time()

    def sleep(self, sim_seconds: float, stop: threading.Event | None = None) -> bool:
        """Dorme `sim_seconds` simulados. Retorna False se `stop` foi acionado."""
        deadline = self.now() + max(0.0, sim_seconds)
        while self.now() < deadline:
            if stop is not None and stop.is_set():
                return False
            time.sleep(min(0.05, max(0.001, (deadline - self.now()) / self._speed)))
        return True


class Simulator:
    def __init__(self, specs, host: str = "127.0.0.1", speed: float = 1.0, tick_s: float = 0.2):
        self.clock = SimClock(speed)
        self.host = host
        self.tick_s = tick_s
        self.chargers: dict[str, VirtualCharger] = {}
        self.ports: dict[str, int] = {}
        self._wanted_ports = {s.codigo: s.porta for s in specs}
        for s in specs:
            self.chargers[s.codigo] = VirtualCharger(code=s.codigo, max_power_w=s.potencia_kw * 1000, phases=s.fases)
        self.banks: dict[str, RegisterBank] = {}
        self.servers: dict[str, ModbusServer] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last = self.clock.now()

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        for code in list(self.chargers):
            self._subir_servidor(code)
        self._last = self.clock.now()
        self._thread = threading.Thread(target=self._loop, name="simulador", daemon=True)
        self._thread.start()
        log.info("simulador ativo: %s", self.ports)

    def _subir_servidor(self, code: str) -> None:
        bank = RegisterBank(R.total_size(), R.writable_addresses(), self._on_write(code))
        self.banks[code] = bank
        try:
            server = ModbusServer(bank, self.host, self._wanted_ports.get(code, 0))
        except OSError:  # porta ocupada → usa uma livre
            server = ModbusServer(bank, self.host, 0)
        server.start()
        self.servers[code] = server
        self.ports[code] = server.port
        self._sync(code)

    def adicionar(self, codigo: str, potencia_kw: float, fases: int | None = None, porta: int = 0) -> int:
        """Cria mais um carregador virtual (com o simulador já rodando ou não). Retorna a porta Modbus."""
        with self._lock:
            if codigo in self.chargers:
                return self.ports.get(codigo, 0)
            fases = fases or (3 if potencia_kw > 7.4 else 1)
            self.chargers[codigo] = VirtualCharger(code=codigo, max_power_w=potencia_kw * 1000, phases=fases)
            self._wanted_ports[codigo] = porta
            if self._thread is not None:
                self._subir_servidor(codigo)
                log.info("carregador virtual %s criado na porta %s", codigo, self.ports[codigo])
            return self.ports.get(codigo, 0)

    def stop(self) -> None:
        self._stop.set()
        for s in self.servers.values():
            s.stop()

    def _loop(self) -> None:
        while not self._stop.wait(self.tick_s):
            self.step()

    def step(self) -> None:
        with self._lock:
            now = self.clock.now()
            dt, self._last = now - self._last, now
            for code, ch in self.chargers.items():
                ch.tick(dt)
                self._sync(code)

    # ------------------------------------------------------------------ registradores
    def _sync(self, code: str) -> None:
        bank = self.banks.get(code)
        if bank is None:
            return
        for name, value in self.chargers[code].to_fields(self.clock.now()).items():
            if name in R.REGISTROS and not R.REGISTROS[name][3]:
                bank.set(R.address(name), R.encode(name, value))

    def _read(self, code: str, name: str):
        return R.decode(name, self.banks[code].get(R.address(name), R.size(name)))

    def _on_write(self, code: str):
        def handler(addr: int, values: list[int]) -> None:
            with self._lock:
                ch = self.chargers[code]
                touched = set(range(addr, addr + len(values)))
                if R.address("current_limit_a") in touched:
                    ch.current_limit_a = int(self._read(code, "current_limit_a"))
                    ch.last_event = f"limite de corrente = {ch.current_limit_a or 'sem limite'} A"
                if touched & {R.address("auth_result"), R.address("auth_seq")}:
                    result, seq = int(self._read(code, "auth_result")), int(self._read(code, "auth_seq"))
                    if result and ch.apply_auth(result, seq):
                        self.banks[code].set(R.address("auth_result"), [0])
                self._sync(code)

        return handler

    # ------------------------------------------------------------------ ações (painel / cenários)
    def tap(self, code: str, uid: str) -> None:
        with self._lock:
            self.chargers[code].tap(uid)
            self._sync(code)

    def plug(self, code: str, kwh: float, vehicle_kw: float = 11.0) -> None:
        with self._lock:
            self.chargers[code].plug(VehicleProfile(energy_needed_wh=kwh * 1000, max_power_w=vehicle_kw * 1000))
            self._sync(code)

    def unplug(self, code: str) -> None:
        with self._lock:
            self.chargers[code].unplug()
            self._sync(code)

    def fault(self, code: str, error: int = 0x21) -> None:
        with self._lock:
            self.chargers[code].fault(error)
            self._sync(code)

    def clear_fault(self, code: str) -> None:
        with self._lock:
            self.chargers[code].clear_fault()
            self._sync(code)

    def all_idle(self) -> bool:
        return all(not c.connected and not c.authorized and not c.pending_auth and not c.fault_code for c in self.chargers.values())

    def resync_clock(self) -> bool:
        with self._lock:
            if not self.all_idle():
                return False
            self.clock.resync()
            self._last = self.clock.now()
            return True

    def snapshot(self) -> list[dict]:
        with self._lock:
            out = []
            for code, ch in self.chargers.items():
                out.append(
                    {
                        "code": code,
                        "port": self.ports.get(code),
                        "status": R.STATUS.get(ch.status, "?"),
                        "connected": ch.connected,
                        "power_kw": ch.power_w / 1000,
                        "energy_kwh": ch.energy_wh / 1000,
                        "delivered_kwh": ch.vehicle.delivered_wh / 1000 if ch.vehicle else 0.0,
                        "needed_kwh": ch.vehicle.energy_needed_wh / 1000 if ch.vehicle else 0.0,
                        "fault": ch.fault_code,
                        "limit_a": ch.current_limit_a,
                        "last_event": ch.last_event,
                    }
                )
            return out
