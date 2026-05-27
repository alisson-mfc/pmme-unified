"""Carregamento de dados do PMM-e — multi-source com cache em memória.

Fontes (em ordem de prioridade configurável via env DATA_SOURCE):

  • LOCAL:
      1. pmme-unified/dados/processado/   (saída do pipeline antes de push)
      2. pmme-unified/analises/           (saída do pipeline antes de push)
      3. ../pmme-dados/                   (sibling repo, útil em dev)
      4. ../pmme-dashboard/analises/      (sibling — análises antigas de matrículas)

  • REMOTE:
      5. GitHub raw / API (pmme-dados privado), via GITHUB_TOKEN

DATA_SOURCE pode ser:
    "auto"   → local primeiro, remoto como fallback (default)
    "local"  → só local
    "remote" → só remoto (produção)

Cache: lru_cache em todas as funções públicas. Use refresh_all() pra invalidar.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

from data.parsers import format_br_date, infer_last_update, parse_date

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
GITHUB_REPO = os.environ.get("GITHUB_REPO", "alisson-mfc/pmme-dados")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
DATA_SOURCE = os.environ.get("DATA_SOURCE", "auto").lower()

_HERE = Path(__file__).resolve().parent.parent  # pmme-unified/
LOCAL_PROCESSADO = _HERE / "dados" / "processado"
LOCAL_ANALISES = _HERE / "analises"
SIBLING_DADOS = _HERE.parent / "pmme-dados"
SIBLING_DASH_ANALISES = _HERE.parent / "pmme-dashboard" / "analises"
ASSETS_NUVENS = _HERE / "assets" / "nuvens"
ASSETS_NUVENS.mkdir(parents=True, exist_ok=True)


def _use_local() -> bool:
    return DATA_SOURCE in ("auto", "local")


def _use_remote() -> bool:
    return DATA_SOURCE in ("auto", "remote")


# ----------------------------------------------------------------------
# FETCHERS BAIXO NÍVEL
# ----------------------------------------------------------------------
def _github_raw_url(path: str) -> str:
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{path}"


def _github_headers() -> dict[str, str]:
    headers = {"User-Agent": "pmme-unified", "Accept": "application/vnd.github.v3.raw"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def _fetch_remote_bytes(path: str) -> bytes | None:
    try:
        url = _github_raw_url(path)
        r = requests.get(url, headers=_github_headers(), timeout=20)
        if r.status_code == 200:
            return r.content
    except requests.RequestException:
        pass
    return None


def _fetch_remote_json(path: str) -> Any | None:
    data = _fetch_remote_bytes(path)
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _read_local_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_local_bytes(path: Path) -> bytes | None:
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _try_json_sources(local_paths: list[Path], remote_paths: list[str]) -> Any | None:
    """Tenta caminhos locais (na ordem) e depois remotos (na ordem). Primeira leitura válida vence."""
    if _use_local():
        for p in local_paths:
            data = _read_local_json(p)
            if data is not None:
                return data
    if _use_remote():
        for rp in remote_paths:
            data = _fetch_remote_json(rp)
            if data is not None:
                return data
    return None


def _try_bytes_sources(local_paths: list[Path], remote_paths: list[str]) -> bytes | None:
    if _use_local():
        for p in local_paths:
            data = _read_local_bytes(p)
            if data is not None:
                return data
    if _use_remote():
        for rp in remote_paths:
            data = _fetch_remote_bytes(rp)
            if data is not None:
                return data
    return None


# ----------------------------------------------------------------------
# UTIL: normalizar nome de rede pra path/arquivo
# ----------------------------------------------------------------------
def _rede_slug(rede: str) -> str:
    return rede.lower().replace(" ", "_").replace("-", "_")


# ----------------------------------------------------------------------
# API PÚBLICA — DADOS BRUTOS
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_matriculas_raw() -> list[dict]:
    """Retorna o array de records de matrículas (campo RECORDS desempacotado)."""
    data = _try_json_sources(
        local_paths=[
            LOCAL_PROCESSADO / "dados_anonimizados.json",
            SIBLING_DADOS / "dados_anonimizados.json",
        ],
        remote_paths=["dados_anonimizados.json"],
    )
    if isinstance(data, dict) and "RECORDS" in data:
        return data["RECORDS"]
    return data if isinstance(data, list) else []


@lru_cache(maxsize=1)
def get_logbook_raw() -> list[dict]:
    """Retorna o array de records de logbook."""
    data = _try_json_sources(
        local_paths=[
            LOCAL_PROCESSADO / "logbook_pseudonimizados.json",
            SIBLING_DADOS / "logbook_pseudonimizados.json",
        ],
        remote_paths=["logbook_pseudonimizados.json"],
    )
    if isinstance(data, dict) and "RECORDS" in data:
        return data["RECORDS"]
    return data if isinstance(data, list) else []


@lru_cache(maxsize=1)
def get_ml_predictions() -> dict:
    """Predições do Random Forest de dificuldade do logbook."""
    data = _try_json_sources(
        local_paths=[
            LOCAL_PROCESSADO / "predicoes_ml_dificuldade.json",
            SIBLING_DADOS / "predicoes_ml_dificuldade.json",
        ],
        remote_paths=["predicoes_ml_dificuldade.json"],
    )
    return data if isinstance(data, dict) else {}


# ----------------------------------------------------------------------
# API PÚBLICA — ANÁLISES CLAUDE
# ----------------------------------------------------------------------
@lru_cache(maxsize=8)
def get_logbook_analysis(rede: str) -> dict:
    """Análise Claude do logbook para uma rede (Todas/EBSERH/PROADI-SUS)."""
    slug = _rede_slug(rede)
    old_filename = f"analise_preditiva_{slug}.json"
    new_local_paths = [
        LOCAL_ANALISES / "logbook" / rede / "resultados.json",
        SIBLING_DADOS / "analises" / "logbook" / rede / "resultados.json",
    ]
    old_local_paths = [SIBLING_DADOS / old_filename]
    new_remote = [f"analises/logbook/{rede}/resultados.json"]
    old_remote = [old_filename]

    data = _try_json_sources(
        local_paths=new_local_paths + old_local_paths,
        remote_paths=new_remote + old_remote,
    )
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=32)
def get_matriculas_analysis(rede: str, ano: str = "Todos") -> dict:
    """Análise Claude de matrículas para um corte (rede, ano).

    Tenta primeiro a estrutura nova (analises/matriculas/{rede}/{ano}/resultados.json);
    fallback: estrutura antiga em pmme-dashboard/analises/{rede}/resultados_analises.json,
    válida apenas quando ano="Todos".
    """
    new_local = [
        LOCAL_ANALISES / "matriculas" / rede / ano / "resultados.json",
        SIBLING_DADOS / "analises" / "matriculas" / rede / ano / "resultados.json",
    ]
    new_remote = [f"analises/matriculas/{rede}/{ano}/resultados.json"]

    old_local: list[Path] = []
    old_remote: list[str] = []
    if ano == "Todos":
        old_local = [SIBLING_DASH_ANALISES / rede / "resultados_analises.json"]
        # Antiga estrutura não está no pmme-dados; sem fallback remoto.

    data = _try_json_sources(
        local_paths=new_local + old_local,
        remote_paths=new_remote + old_remote,
    )
    return data if isinstance(data, dict) else {}


# ----------------------------------------------------------------------
# API PÚBLICA — NUVENS DE PALAVRAS (PNGs)
# ----------------------------------------------------------------------
@lru_cache(maxsize=128)
def get_nuvem_palavras_src(rede: str, ano: str, campo: str) -> str | None:
    """Retorna o `src` (URL ou data: URI) de uma nuvem de palavras pra usar em html.Img.

    Estratégia: baixa o PNG da fonte com prioridade
    (local pipeline → sibling pmme-dashboard antigo → remoto), grava em
    assets/nuvens/ pra Dash servir como /assets/, e devolve essa URL.
    """
    slug_arquivo = f"{_rede_slug(rede)}_{ano}_{campo}.png"
    destino = ASSETS_NUVENS / slug_arquivo

    if destino.exists():
        return f"/assets/nuvens/{slug_arquivo}"

    new_local = [
        LOCAL_ANALISES / "matriculas" / rede / ano / "nuvens_palavras" / f"{campo}.png",
        SIBLING_DADOS / "analises" / "matriculas" / rede / ano / "nuvens_palavras" / f"{campo}.png",
    ]
    new_remote = [f"analises/matriculas/{rede}/{ano}/nuvens_palavras/{campo}.png"]

    old_local: list[Path] = []
    if ano == "Todos":
        old_local = [SIBLING_DASH_ANALISES / rede / "nuvens_palavras" / f"{campo}.png"]

    data = _try_bytes_sources(
        local_paths=new_local + old_local,
        remote_paths=new_remote,
    )
    if data is None:
        return None
    try:
        destino.write_bytes(data)
        return f"/assets/nuvens/{slug_arquivo}"
    except OSError:
        # Fallback: serve como data URI (lento; só em emergência)
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{b64}"


# ----------------------------------------------------------------------
# API PÚBLICA — METADADOS DE ATUALIZAÇÃO
# ----------------------------------------------------------------------
@lru_cache(maxsize=4)
def get_meta(dataset: str) -> dict | None:
    """Carrega _meta.json (data_atualizacao + file_hash + total_registros) para um dataset.

    Procura o arquivo _meta.json correspondente; se não houver, infere a partir dos dados.
    """
    meta_filenames = {
        "matriculas": "dados_anonimizados.meta.json",
        "logbook": "logbook_pseudonimizados.meta.json",
    }
    fname = meta_filenames.get(dataset)
    if not fname:
        return None

    data = _try_json_sources(
        local_paths=[LOCAL_PROCESSADO / fname, SIBLING_DADOS / fname],
        remote_paths=[fname],
    )
    if isinstance(data, dict):
        return data

    # Fallback: inferir do próprio dataset
    if dataset == "matriculas":
        records = get_matriculas_raw()
        last = infer_last_update(records, ("created_at", "updated_at", "data_matricula"))
        return {
            "data_atualizacao": last.isoformat() if last else None,
            "total_registros": len(records),
            "fonte": "inferido",
        }
    if dataset == "logbook":
        records = get_logbook_raw()
        last = infer_last_update(records, ("data_hora_insert", "data_hora_realizacao"))
        return {
            "data_atualizacao": last.isoformat() if last else None,
            "total_registros": len(records),
            "fonte": "inferido",
        }
    return None


def format_data_atualizacao(meta: dict | None) -> tuple[str | None, int | None]:
    """Extrai (data formatada dd/mm/aaaa, total_registros) de um _meta.json ou inferência."""
    if not meta:
        return None, None
    raw = meta.get("data_atualizacao") or meta.get("data_processamento")
    total = meta.get("total_registros")
    if not raw:
        return None, total
    dt = parse_date(raw)
    if dt is None:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return str(raw), total
    return format_br_date(dt), total


# Backwards-compat com o stub anterior
load_meta = get_meta


# ----------------------------------------------------------------------
# REFRESH
# ----------------------------------------------------------------------
def refresh_all() -> None:
    """Limpa todos os caches em memória. Próxima chamada refaz os fetches."""
    for fn in (
        get_matriculas_raw,
        get_logbook_raw,
        get_ml_predictions,
        get_logbook_analysis,
        get_matriculas_analysis,
        get_nuvem_palavras_src,
        get_meta,
    ):
        fn.cache_clear()
    # Limpa também os PNGs já baixados (forçar re-download na próxima)
    for png in ASSETS_NUVENS.glob("*.png"):
        try:
            png.unlink()
        except OSError:
            pass
