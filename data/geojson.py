"""Helpers de geojson para mapas — Brasil (estados) e por estado (municípios)."""

from __future__ import annotations

from functools import lru_cache

import requests

from data.constants import GEOJSON_BRASIL_ESTADOS, SIGLAS_IBGE


@lru_cache(maxsize=1)
def geojson_brasil() -> dict:
    """Geojson com os 27 estados brasileiros (properties.name = nome do estado)."""
    try:
        r = requests.get(GEOJSON_BRASIL_ESTADOS, timeout=20)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return {"features": []}


@lru_cache(maxsize=32)
def geojson_municipios(uf_sigla: str) -> dict:
    """Geojson dos municípios de um estado.

    Fonte tbrugz/geodata-br — `properties.id` = código IBGE 7 dígitos,
    `properties.name` = nome do município.
    """
    codigo = SIGLAS_IBGE.get(uf_sigla)
    if not codigo:
        return {"features": []}
    url = (
        f"https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/"
        f"geojs-{codigo}-mun.json"
    )
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return {"features": []}
