"""Modelo físico/lógico de um carregador GoodWe HCA G2 virtual (camada física mockada).

Determinístico e dirigido por `tick(dt)`, o que facilita os testes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Códigos de status — os mesmos de hardware/registers.py
DISPONIVEL = 0
CONECTADO = 1
AGUARDANDO_AUTORIZACAO = 2
AUTORIZADO = 3
CARREGANDO = 4
CARGA_SUSPENSA = 5
FALHA = 6

AUTH_ACCEPTED = 1
AUTH_REJECTED = 2

AUTH_TIMEOUT_S = 6 * 60      # autorização expira se ninguém conectar o cabo
PENDING_TIMEOUT_S = 15        # sem resposta do backend → descarta a leitura RFID (tempo REAL:
                              # é um timeout de comunicação, não deve acelerar com o relógio simulado)
TAPER_START = 0.85            # a partir de 85% da energia pedida a potência cai


@dataclass
class VehicleProfile:
    """Veículo conectado: quanta energia ele quer e a potência máxima AC que aceita."""

    energy_needed_wh: float
    max_power_w: float = 11_000.0
    delivered_wh: float = 0.0

    @property
    def complete(self) -> bool:
        return self.delivered_wh >= self.energy_needed_wh - 1e-6


@dataclass
class VirtualCharger:
    code: str
    max_power_w: float = 11_000.0
    phases: int = 3
    voltage_v: float = 230.0
    auth_mode: str = "backend"            # "backend" ou "local" (ver risco R3)
    local_whitelist: set[str] = field(default_factory=set)

    # estado
    connected: bool = False
    authorized: bool = False
    pending_auth: bool = False
    fault_code: int = 0
    energy_wh: float = 0.0                # medidor acumulado (nunca zera)
    power_w: float = 0.0
    current_a: float = 0.0
    rfid_seq: int = 0
    rfid_uid: str = ""
    current_limit_a: int = 0              # 0 = sem limite
    vehicle: VehicleProfile | None = None

    # knobs de anomalia (cenário anomalia_consumo)
    power_multiplier: float = 1.0         # >1 = potência acima do nominal
    energy_multiplier: float = 1.0        # >1 = medidor "pula" (kWh incompatível)

    _auth_age_s: float = 0.0
    _pending_desde: float = 0.0
    last_event: str = ""

    # ------------------------------------------------------------- comandos
    def tap(self, uid: str) -> None:
        if self.fault_code:
            self.last_event = "leitura RFID ignorada: carregador em falha"
            return
        self.rfid_uid = uid.strip().upper()[:8]
        self.rfid_seq = (self.rfid_seq + 1) & 0xFFFF
        if self.auth_mode == "local":
            if self.rfid_uid in self.local_whitelist:
                self.authorized, self.pending_auth, self._auth_age_s = True, False, 0.0
                self.last_event = f"RFID {self.rfid_uid} aceito localmente"
            else:
                self.last_event = f"RFID {self.rfid_uid} negado localmente"
            return
        self.pending_auth = True
        self._pending_desde = time.monotonic()
        self.last_event = f"RFID {self.rfid_uid} lido, aguardando backend"

    def apply_auth(self, result: int, seq: int) -> bool:
        """Resposta do backend (registradores auth_result/auth_seq)."""
        if seq != self.rfid_seq or not self.pending_auth:
            return False
        self.pending_auth = False
        if result == AUTH_ACCEPTED:
            self.authorized = True
            self._auth_age_s = 0.0
            self.last_event = f"RFID {self.rfid_uid} autorizado pelo backend"
        elif result == AUTH_REJECTED:
            self.last_event = f"RFID {self.rfid_uid} negado pelo backend"
        return True

    def plug(self, vehicle: VehicleProfile) -> None:
        self.connected = True
        self.vehicle = vehicle
        self.last_event = f"veículo conectado ({vehicle.energy_needed_wh / 1000:.1f} kWh pedidos)"

    def unplug(self) -> None:
        self.connected = False
        self.authorized = False
        self.vehicle = None
        self.power_w = self.current_a = 0.0
        self.last_event = "veículo desconectado"

    def fault(self, code: int = 0x21) -> None:
        self.fault_code = code or 0x21
        self.power_w = self.current_a = 0.0
        self.last_event = f"falha {self.fault_code:#04x}"

    def clear_fault(self) -> None:
        self.fault_code = 0
        self.authorized = False
        self.last_event = "falha limpa"

    def set_anomaly(self, power_multiplier: float = 1.0, energy_multiplier: float = 1.0) -> None:
        self.power_multiplier = power_multiplier
        self.energy_multiplier = energy_multiplier

    # ------------------------------------------------------------- física
    def available_power_w(self) -> float:
        limit = self.max_power_w
        if self.current_limit_a:
            limit = min(limit, self.current_limit_a * self.voltage_v * self.phases)
        if self.vehicle:
            limit = min(limit, self.vehicle.max_power_w)
        return max(0.0, limit)

    def tick(self, dt_s: float) -> None:
        if dt_s <= 0:
            return
        if self.pending_auth:
            if time.monotonic() - self._pending_desde > PENDING_TIMEOUT_S:
                self.pending_auth = False
                self.last_event = "sem resposta do backend, leitura RFID descartada"
        if self.authorized and not self.connected:
            self._auth_age_s += dt_s
            if self._auth_age_s > AUTH_TIMEOUT_S:
                self.authorized = False
                self.last_event = "autorização expirou (cabo não conectado)"

        charging = (
            not self.fault_code
            and self.connected
            and self.authorized
            and self.vehicle is not None
            and not self.vehicle.complete
        )
        if not charging:
            self.power_w = self.current_a = 0.0
            return

        assert self.vehicle is not None
        available = self.available_power_w()
        progress = self.vehicle.delivered_wh / self.vehicle.energy_needed_wh if self.vehicle.energy_needed_wh else 1.0
        factor = 1.0 if progress < TAPER_START else max(0.05, (1.0 - progress) / (1.0 - TAPER_START))
        real_power = available * factor
        delivered = min(real_power * dt_s / 3600.0, self.vehicle.energy_needed_wh - self.vehicle.delivered_wh)
        self.vehicle.delivered_wh += delivered
        # potência e medidor reportados (podem estar "errados" no cenário de anomalia)
        self.power_w = real_power * self.power_multiplier
        self.current_a = self.power_w / (self.voltage_v * self.phases)
        self.energy_wh += delivered * self.power_multiplier * self.energy_multiplier
        if self.vehicle.complete:
            self.power_w = self.current_a = 0.0
            self.last_event = "carga completa (veículo parou de consumir)"

    # ------------------------------------------------------------- estado
    @property
    def status(self) -> int:
        if self.fault_code:
            return FALHA
        if self.pending_auth:
            return AGUARDANDO_AUTORIZACAO
        if not self.connected:
            return AUTORIZADO if self.authorized else DISPONIVEL
        if not self.authorized:
            return CONECTADO
        if self.vehicle and not self.vehicle.complete:
            return CARREGANDO
        return CARGA_SUSPENSA

    def to_fields(self, clock_epoch: float) -> dict:
        """Valores na forma do mapa de registradores."""
        return {
            "status": self.status,
            "cable_connected": int(self.connected),
            "error_code": self.fault_code,
            "phases": self.phases,
            "power_w": round(self.power_w),
            "current_a": self.current_a,
            "voltage_v": self.voltage_v if self.connected else 0.0,
            "energy_wh": int(self.energy_wh),
            "device_clock": int(clock_epoch),
            "rfid_seq": self.rfid_seq,
            "rfid_uid": self.rfid_uid,
            "max_power_w": round(self.max_power_w),
        }
