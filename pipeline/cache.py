"""Cache por hash SHA-256 do subset de dados.

Estratégia: cada análise (matrículas por rede×ano, logbook por rede) calcula o
hash SHA-256 do subset de registros usado. Esse hash vai no campo `file_hash`
do JSON de saída. Antes de re-rodar a análise, verificamos se o hash atual bate
com o gravado — se sim, pulamos a chamada Claude.

Compatível com o `processar_ia.py` original (mesmo algoritmo: json.dumps com
sort_keys=True, ensure_ascii=False).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def hash_subset(data: list[dict] | Any) -> str:
    """SHA-256 hex do JSON serializado com sort_keys=True. Compatível com pipeline original."""
    s = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read_existing_hash(output_path: Path, hash_field: str = "file_hash") -> str | None:
    """Lê o hash gravado em um arquivo de análise existente. None se ausente."""
    if not output_path.exists():
        return None
    try:
        data = json.loads(output_path.read_text(encoding="utf-8"))
        return data.get(hash_field)
    except (OSError, json.JSONDecodeError):
        return None


def needs_processing(output_path: Path, current_hash: str, force: bool = False) -> bool:
    """Retorna True se a análise precisa rodar."""
    if force:
        return True
    existing = read_existing_hash(output_path)
    return existing != current_hash


def write_meta_sidecar(
    output_path: Path,
    *,
    file_hash: str,
    total_registros: int,
    extra: dict | None = None,
) -> None:
    """Grava `<stem>.meta.json` ao lado de `output_path`.

    Ex.: output_path=dados_anonimizados.json → meta=dados_anonimizados.meta.json.
    Esse é o nome esperado pelo loader (data/loader.py).
    """
    if output_path.name.endswith(".meta.json"):
        meta_path = output_path
    else:
        meta_path = output_path.with_suffix(".meta.json")
    meta = {
        "data_atualizacao": datetime.now().isoformat(),
        "file_hash": file_hash,
        "total_registros": total_registros,
    }
    if extra:
        meta.update(extra)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
