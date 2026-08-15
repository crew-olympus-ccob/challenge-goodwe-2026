"""Gateway: a única parte do sistema que conversa com o "hardware".

Lê os registradores via Modbus TCP e devolve uma `Leitura`; escreve as
respostas de autorização e o limite de corrente. Funciona igual com o
simulador e com o GoodWe HCA G2 real (basta trocar host/porta).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from evcharge.hardware import registers as R
from evcharge.hardware.modbus import ModbusClient, ModbusError


class GatewayError(Exception):
    pass


@dataclass(frozen=True)
class Leitura:
    carregador: str
    ts: datetime                 # relógio do equipamento
    status: str
    conectado: bool
    potencia_kw: float
    corrente_a: float
    energia_kwh: float           # medidor acumulado
    rfid_seq: int = 0
    rfid_uid: str = ""
    erro: int = 0


class ModbusGateway:
    def __init__(self, codigo: str, host: str, porta: int, timeout: float = 2.0):
        self.codigo = codigo
        self.client = ModbusClient(host, porta, R.UNIT_ID, timeout)

    def ler(self) -> Leitura:
        raw: dict = {}
        try:
            for start, count in R.read_ranges():
                raw.update(R.decode_block(start, self.client.read(start, count)))
        except ModbusError as exc:
            raise GatewayError(str(exc)) from exc
        return self.converter(raw)

    def converter(self, raw: dict) -> Leitura:
        clock = int(raw.get("device_clock") or 0)
        return Leitura(
            carregador=self.codigo,
            ts=datetime.fromtimestamp(clock, UTC) if clock > 0 else datetime.now(UTC),
            status=R.STATUS.get(int(raw.get("status", 0)), "DESCONHECIDO"),
            conectado=bool(raw.get("cable_connected", 0)),
            potencia_kw=round(float(raw.get("power_w", 0)) / 1000, 3),
            corrente_a=round(float(raw.get("current_a", 0)), 2),
            energia_kwh=round(float(raw.get("energy_wh", 0)) / 1000, 3),
            rfid_seq=int(raw.get("rfid_seq", 0)),
            rfid_uid=str(raw.get("rfid_uid", "")).strip().upper(),
            erro=int(raw.get("error_code", 0)),
        )

    def autorizar(self, rfid_seq: int, aceito: bool) -> None:
        try:  # auth_result e auth_seq são contíguos → escrita atômica
            self.client.write(R.address("auth_result"), [1 if aceito else 2, rfid_seq])
        except ModbusError as exc:
            raise GatewayError(str(exc)) from exc

    def limitar_corrente(self, amps: int) -> None:
        try:
            self.client.write(R.address("current_limit_a"), [max(0, int(amps))])
        except ModbusError as exc:
            raise GatewayError(str(exc)) from exc

    def fechar(self) -> None:
        self.client.close()
