"""Mapa de registradores Modbus do GoodWe HCA G2.

ATENÇÃO: MAPA FICTÍCIO. Os endereços abaixo NÃO são os do equipamento real.
Quando o manual oficial estiver disponível, ajuste SOMENTE este arquivo
(endereços, tipos, escalas e códigos de status). Nenhum outro código muda.
"""

from __future__ import annotations

UNIT_ID = 1
WORD_ORDER = "big"  # valores de 32 bits: word mais significativa primeiro

# nome: (endereço, tipo, escala, gravável, tamanho_string)
REGISTROS = {
    "status": (0, "uint16", 1, False, 0),
    "cable_connected": (1, "uint16", 1, False, 0),
    "error_code": (2, "uint16", 1, False, 0),
    "phases": (3, "uint16", 1, False, 0),
    "power_w": (10, "uint32", 1, False, 0),
    "current_a": (12, "uint16", 0.01, False, 0),
    "voltage_v": (13, "uint16", 0.1, False, 0),
    "energy_wh": (20, "uint32", 1, False, 0),        # medidor acumulado
    "device_clock": (30, "uint32", 1, False, 0),     # relógio do equipamento (epoch UTC)
    "rfid_seq": (40, "uint16", 1, False, 0),         # incrementa a cada leitura de cartão
    "rfid_uid": (41, "string", 1, False, 8),         # 4 registradores
    "auth_result": (50, "uint16", 1, True, 0),       # backend escreve: 1 aceito, 2 negado
    "auth_seq": (51, "uint16", 1, True, 0),          # rfid_seq que está sendo respondido
    "current_limit_a": (52, "uint16", 1, True, 0),   # limite de corrente (0 = sem limite)
    "max_power_w": (60, "uint32", 1, False, 0),
}

STATUS = {
    0: "DISPONIVEL",
    1: "CONECTADO",
    2: "AGUARDANDO_AUTORIZACAO",
    3: "AUTORIZADO",
    4: "CARREGANDO",
    5: "CARGA_SUSPENSA",
    6: "FALHA",
}
STATUS_CODE = {v: k for k, v in STATUS.items()}


def size(name: str) -> int:
    _, kind, _, _, length = REGISTROS[name]
    if kind == "string":
        return (length + 1) // 2
    return 2 if kind in ("uint32", "int32") else 1


def address(name: str) -> int:
    return REGISTROS[name][0]


def total_size() -> int:
    return max(address(n) + size(n) for n in REGISTROS)


def writable_addresses() -> set[int]:
    return {address(n) + i for n, r in REGISTROS.items() if r[3] for i in range(size(n))}


def read_ranges(max_count: int = 125, gap: int = 10) -> list[tuple[int, int]]:
    """Agrupa os registradores em poucas leituras contíguas (início, quantidade)."""
    ranges: list[list[int]] = []
    for n in sorted(REGISTROS, key=address):
        start, end = address(n), address(n) + size(n)
        if ranges and start - ranges[-1][1] <= gap and end - ranges[-1][0] <= max_count:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])
    return [(a, b - a) for a, b in ranges]


def encode(name: str, value) -> list[int]:
    _, kind, scale, _, length = REGISTROS[name]
    if kind == "string":
        raw = str(value or "").encode("ascii", "replace")[:length].ljust(size(name) * 2, b"\x00")
        return [(raw[i] << 8) | raw[i + 1] for i in range(0, len(raw), 2)]
    number = int(round(float(value) / scale))
    if kind == "uint16":
        return [max(0, min(number, 0xFFFF))]
    number = max(0, min(number, 0xFFFFFFFF))
    hi, lo = (number >> 16) & 0xFFFF, number & 0xFFFF
    return [hi, lo] if WORD_ORDER == "big" else [lo, hi]


def decode(name: str, regs: list[int]):
    _, kind, scale, _, length = REGISTROS[name]
    if kind == "string":
        raw = b"".join(bytes([(r >> 8) & 0xFF, r & 0xFF]) for r in regs)
        return raw.split(b"\x00", 1)[0].decode("ascii", "replace")[:length]
    if kind == "uint16":
        number = regs[0]
    else:
        hi, lo = (regs[0], regs[1]) if WORD_ORDER == "big" else (regs[1], regs[0])
        number = (hi << 16) | lo
    return number * scale if scale != 1 else number


def decode_block(start: int, regs: list[int]) -> dict:
    out = {}
    end = start + len(regs)
    for n in REGISTROS:
        a = address(n)
        if a >= start and a + size(n) <= end:
            out[n] = decode(n, regs[a - start : a - start + size(n)])
    return out
