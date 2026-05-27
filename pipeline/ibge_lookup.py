"""Resolução de códigos IBGE de municípios → (cidade, UF, sigla).

Usa a API oficial do IBGE:
    https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo}

Cacheia resultados em `data/ibge_cache.json` (commitado no repo do app pra
deploys rápidos no Render — o conteúdo é pequeno e estático).

Uso típico:
    from pipeline.ibge_lookup import enrich_records
    records = enrich_records(records, fields={
        "ibge_atuacao": ("cidade_atuacao", "uf_atuacao", "uf_atuacao_sigla"),
        "ibge_formadora": ("cidade_formadora", "uf_formadora", "uf_formadora_sigla"),
    })
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

_HERE = Path(__file__).resolve().parent.parent  # pmme-unified/
CACHE_PATH = _HERE / "data" / "ibge_cache.json"

IBGE_API_ALL_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
REQUEST_TIMEOUT = 30


def _load_cache() -> dict[str, dict[str, str]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict[str, dict[str, str]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _normalize_code(code: int | str) -> str:
    """Trunca para 6 dígitos (formato dos dados PMM-e — sem dígito verificador)."""
    s = str(code)
    if len(s) >= 7:
        return s[:6]
    return s


def _fetch_all() -> dict[str, dict[str, str]]:
    """Busca TODOS os municípios brasileiros da IBGE API em uma chamada.

    Retorna dict com chave = código de 6 dígitos (compatível com dados PMM-e).
    """
    print("  [ibge] baixando lista completa de municípios da API IBGE...")
    r = requests.get(IBGE_API_ALL_URL, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()

    out: dict[str, dict[str, str]] = {}
    for m in data:
        try:
            uf = m["microrregiao"]["mesorregiao"]["UF"]
            entry = {
                "cidade": m["nome"],
                "uf": uf["nome"],
                "uf_sigla": uf["sigla"],
            }
            # Cacheia por código de 6 dígitos (truncando o DV)
            code_6 = _normalize_code(m["id"])
            out[code_6] = entry
            # Também por 7 dígitos pra robustez
            out[str(m["id"])] = entry
        except (KeyError, TypeError):
            continue
    print(f"  [ibge] {len(data)} municípios carregados")
    return out


def resolve_codes(
    codes: set[int | str] | list[int | str],
    *,
    verbose: bool = True,
) -> dict[str, dict[str, str]]:
    """Resolve códigos IBGE pra (cidade, uf, uf_sigla).

    Usa cache local. Se algum código não estiver em cache, baixa a lista
    completa de uma vez (uma única chamada à API).
    """
    cache = _load_cache()
    codes_str = [_normalize_code(c) for c in codes if c is not None]
    missing = [c for c in codes_str if c not in cache]

    if missing:
        if verbose:
            print(f"  [ibge] {len(missing)} códigos não cacheados — baixando lista IBGE...")
        try:
            full_lookup = _fetch_all()
        except (requests.RequestException, ValueError) as e:
            if verbose:
                print(f"  [ibge] falha ao baixar lista IBGE: {e}")
            return {c: cache[c] for c in codes_str if c in cache}

        # Mescla no cache local apenas os códigos que precisamos (mantém arquivo enxuto)
        for c in codes_str:
            if c not in cache and c in full_lookup:
                cache[c] = full_lookup[c]

        _save_cache(cache)
        if verbose:
            resolved = sum(1 for c in missing if c in cache)
            print(f"  [ibge] {resolved}/{len(missing)} resolvidos, cache atualizado")

    return {c: cache[c] for c in codes_str if c in cache}


def enrich_records(
    records: list[dict],
    *,
    fields: dict[str, tuple[str, str, str]] | None = None,
    verbose: bool = True,
) -> list[dict]:
    """Enriquece cada record com cidade/uf/sigla derivados de códigos IBGE.

    Args:
        records: lista de dicts (modificados in-place também)
        fields: mapping {campo_ibge: (campo_cidade, campo_uf, campo_uf_sigla)}.
            Default: ibge_atuacao + ibge_formadora.
        verbose: imprime progresso

    Retorna a mesma lista (registros mutados).
    """
    if fields is None:
        fields = {
            "ibge_atuacao": ("cidade_atuacao", "uf_atuacao", "uf_atuacao_sigla"),
            "ibge_formadora": ("cidade_formadora", "uf_formadora", "uf_formadora_sigla"),
        }

    # Coleta todos os códigos distintos primeiro
    all_codes: set = set()
    for r in records:
        for src in fields:
            v = r.get(src)
            if v:
                all_codes.add(v)

    if not all_codes:
        return records

    lookup = resolve_codes(all_codes, verbose=verbose)

    # Aplica enriquecimento (normaliza pra 6 dígitos como chave do lookup)
    for r in records:
        for src, (k_cidade, k_uf, k_sigla) in fields.items():
            code = r.get(src)
            if code is None:
                continue
            info = lookup.get(_normalize_code(code))
            if not info:
                continue
            r[k_cidade] = info["cidade"]
            r[k_uf] = info["uf"]
            r[k_sigla] = info["uf_sigla"]

    return records
