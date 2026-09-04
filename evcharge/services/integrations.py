"""Integrações externas secundárias (nenhuma bloqueia o sistema).

* SEMS+ (GoodWe): dados fictícios por enquanto. A API do SEMS+ não é pública;
  a integração real depende de credenciais e documentação fornecidas pela GoodWe.
* Open Charge Map: pontos públicos de recarga próximos (urllib, biblioteca padrão).
  Precisa de uma chave gratuita em openchargemap.org (variável OCM_API_KEY).
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

LATITUDE, LONGITUDE = -23.5614, -46.6559  # exemplo: Av. Paulista, SP


def sems_resumo() -> dict:
    return {
        "fonte": "SEMS+ (dados de demonstração)",
        "carregadores": [
            {"sn": "HCA-G2-DEMO-0001", "codigo": "CH-01", "firmware": "1.0.0-demo", "online": True},
            {"sn": "HCA-G2-DEMO-0002", "codigo": "CH-02", "firmware": "1.0.0-demo", "online": True},
            {"sn": "HCA-G2-DEMO-0003", "codigo": "CH-03", "firmware": "1.0.0-demo", "online": True},
        ],
    }


def pontos_proximos(km: float = 5, limite: int = 10) -> dict:
    chave = os.getenv("OCM_API_KEY", "")
    if not chave:
        return {"pontos": [], "aviso": "Defina a variável OCM_API_KEY para consultar o Open Charge Map."}
    params = urllib.parse.urlencode({
        "output": "json", "latitude": LATITUDE, "longitude": LONGITUDE, "distance": km,
        "distanceunit": "KM", "maxresults": limite, "compact": "true", "verbose": "false", "key": chave,
    })
    try:
        with urllib.request.urlopen(f"https://api.openchargemap.io/v3/poi/?{params}", timeout=8) as resp:
            itens = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        return {"pontos": [], "aviso": f"Open Charge Map indisponível: {exc}"}
    pontos = []
    for it in itens:
        info = it.get("AddressInfo") or {}
        pontos.append({"nome": info.get("Title"), "endereco": info.get("AddressLine1") or "", "km": round(info.get("Distance") or 0, 1),
                       "conectores": len(it.get("Connections") or [])})
    return {"pontos": pontos}
