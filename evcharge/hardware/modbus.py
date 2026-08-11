"""Modbus TCP mínimo (cliente e servidor) usando só a biblioteca padrão.

Funções suportadas (as únicas que o sistema usa):
  * 0x03 Read Holding Registers
  * 0x06 Write Single Register
  * 0x10 Write Multiple Registers
Segue a especificação "MODBUS Messaging on TCP/IP v1.0b", então o mesmo
cliente conversa com o simulador e com o GoodWe HCA G2 real.
"""

from __future__ import annotations

import socket
import socketserver
import struct
import threading
from collections.abc import Callable

FC_READ = 0x03
FC_WRITE_ONE = 0x06
FC_WRITE_MANY = 0x10
MBAP = struct.Struct(">HHHB")  # transação, protocolo, tamanho, unit id


class ModbusError(Exception):
    pass


class ModbusConnectionError(ModbusError):
    """Sem conexão ou timeout: o chamador deve tentar de novo mais tarde."""


# =============================================================== servidor
class RegisterBank:
    """Holding registers de um equipamento, com callback quando alguém escreve."""

    def __init__(self, size: int, writable: set[int] | None = None, on_write: Callable[[int, list[int]], None] | None = None):
        self._regs = [0] * size
        self._lock = threading.Lock()
        self.writable = writable
        self.on_write = on_write

    def get(self, addr: int, count: int) -> list[int]:
        with self._lock:
            if addr < 0 or count < 1 or addr + count > len(self._regs):
                raise IndexError
            return self._regs[addr : addr + count]

    def set(self, addr: int, values: list[int]) -> None:
        with self._lock:
            if addr < 0 or addr + len(values) > len(self._regs):
                raise IndexError
            for i, v in enumerate(values):
                self._regs[addr + i] = int(v) & 0xFFFF

    def external_write(self, addr: int, values: list[int]) -> None:
        if self.writable is not None and any(a not in self.writable for a in range(addr, addr + len(values))):
            raise PermissionError
        self.set(addr, values)
        if self.on_write:
            self.on_write(addr, values)


def handle_pdu(bank: RegisterBank, pdu: bytes) -> bytes:
    fc = pdu[0] if pdu else 0
    try:
        if fc == FC_READ and len(pdu) == 5:
            addr, count = struct.unpack(">HH", pdu[1:5])
            if not 1 <= count <= 125:
                return bytes([fc | 0x80, 3])
            values = bank.get(addr, count)
            return bytes([fc, count * 2]) + struct.pack(f">{count}H", *values)
        if fc == FC_WRITE_ONE and len(pdu) == 5:
            addr, value = struct.unpack(">HH", pdu[1:5])
            bank.external_write(addr, [value])
            return pdu
        if fc == FC_WRITE_MANY and len(pdu) >= 6:
            addr, count, nbytes = struct.unpack(">HHB", pdu[1:6])
            if nbytes != count * 2 or len(pdu) != 6 + nbytes:
                return bytes([fc | 0x80, 3])
            bank.external_write(addr, list(struct.unpack(f">{count}H", pdu[6:])))
            return struct.pack(">BHH", fc, addr, count)
        return bytes([fc | 0x80, 1])
    except (IndexError, PermissionError):
        return bytes([fc | 0x80, 2])


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        bank: RegisterBank = self.server.bank  # type: ignore[attr-defined]
        self.server.conexoes.add(sock)  # type: ignore[attr-defined]
        try:
            while True:
                header = _recv_exact(sock, MBAP.size)
                tid, proto, length, unit = MBAP.unpack(header)
                pdu = _recv_exact(sock, length - 1)
                if proto != 0:
                    continue
                resp = handle_pdu(bank, pdu)
                sock.sendall(MBAP.pack(tid, 0, len(resp) + 1, unit) + resp)
        except (ConnectionError, OSError):
            pass
        finally:
            self.server.conexoes.discard(sock)  # type: ignore[attr-defined]


class ModbusServer(socketserver.ThreadingTCPServer):
    """Servidor Modbus TCP (um por carregador simulado)."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, bank: RegisterBank, host: str = "127.0.0.1", port: int = 502):
        self.bank = bank
        self.conexoes: set[socket.socket] = set()
        super().__init__((host, port), _Handler)
        self.port = self.server_address[1]
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Derruba o servidor e as conexões abertas (como um equipamento desligado)."""
        self.shutdown()
        self.server_close()
        for sock in list(self.conexoes):
            try:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except OSError:
                pass


# =============================================================== cliente
def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("conexão encerrada")
        buf += chunk
    return buf


class ModbusClient:
    """Cliente Modbus TCP síncrono, com reconexão automática."""

    def __init__(self, host: str, port: int = 502, unit_id: int = 1, timeout: float = 2.0):
        self.host, self.port, self.unit_id, self.timeout = host, port, unit_id, timeout
        self._sock: socket.socket | None = None
        self._tid = 0
        self._lock = threading.Lock()

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None

    def _request(self, pdu: bytes) -> bytes:
        with self._lock:
            try:
                if self._sock is None:
                    self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
                self._tid = (self._tid + 1) & 0xFFFF
                self._sock.sendall(MBAP.pack(self._tid, 0, len(pdu) + 1, self.unit_id) + pdu)
                while True:
                    tid, _proto, length, _unit = MBAP.unpack(_recv_exact(self._sock, MBAP.size))
                    body = _recv_exact(self._sock, length - 1)
                    if tid == self._tid:
                        break
            except (OSError, ConnectionError) as exc:
                self.close()
                raise ModbusConnectionError(f"{self.host}:{self.port} sem resposta ({exc})") from exc
        if body[0] & 0x80:
            raise ModbusError(f"exceção Modbus código {body[1]}")
        return body

    def read(self, addr: int, count: int) -> list[int]:
        body = self._request(struct.pack(">BHH", FC_READ, addr, count))
        if body[1] != count * 2:
            raise ModbusError("resposta com tamanho inválido")
        return list(struct.unpack(f">{count}H", body[2:]))

    def write(self, addr: int, values: list[int]) -> None:
        if len(values) == 1:
            self._request(struct.pack(">BHH", FC_WRITE_ONE, addr, values[0] & 0xFFFF))
        else:
            n = len(values)
            self._request(struct.pack(f">BHHB{n}H", FC_WRITE_MANY, addr, n, n * 2, *[v & 0xFFFF for v in values]))
