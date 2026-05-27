"""Anonimizador de logbook — port 1:1 de anonimizador2.html.

Regras (mesmas do HTML original):
  • Pseudonimiza CPF determinística por execução: SHA-256(salt|cpf) → 12 chars b64 →
    prefixo 'CPF_xxxxxxxxxxxx'. Mesmo CPF gera mesmo token dentro da mesma execução.
  • Pseudonimiza `profissional` (nome): sequencial 'Profissional_0001', 'Profissional_0002', ...
    Determinístico pelo nome normalizado (case/espaços), na ordem em que aparece.
  • Filtra registros com data_hora_realizacao ≤ 08/2025
    (ano < 2025 OU (ano == 2025 E mês ≤ 8))
  • Remove prefixo 'Aprimoramento em ' de curso_aprimoramento
  • Opcional: retorna mapping (cpf_orig→token, nome_orig→token) pra CSV separado
    (NUNCA commitado)

O salt é gerado aleatoriamente por execução (16 bytes b64) ou pode ser passado
explicitamente para reprodutibilidade.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Any

# ----------------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------------
APRIMORAMENTO_PREFIX = "Aprimoramento em "


def _make_salt(length: int = 16) -> str:
    """16 bytes aleatórios codificados em base64 (mesma estratégia do JS)."""
    raw = os.urandom(length)
    return base64.b64encode(raw).decode("ascii")


def _sha256_b64url(text: str) -> str:
    """SHA-256 do texto retornando base64url (sem padding) — equivalente ao JS."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")


def _normalize_name(name: Any) -> str:
    """Normalização do JS: trim, colapsa espaços, lowercase."""
    if name is None:
        return ""
    return re.sub(r"\s+", " ", str(name).strip()).lower()


def _filter_by_date(rec: dict) -> bool:
    """Retorna True se o registro DEVE ser mantido (data > 08/2025).

    Formato esperado: 'DD/MM/YYYY HH:MM:SS-03' (data_hora_realizacao).
    Se o campo estiver ausente ou em formato inesperado, mantém por segurança
    (mesmo comportamento do JS).
    """
    raw = rec.get("data_hora_realizacao")
    if not raw:
        return True
    try:
        date_part = str(raw).split(" ")[0]
        parts = date_part.split("/")
        if len(parts) != 3:
            return True
        month = int(parts[1])
        year = int(parts[2])
        if year < 2025:
            return False
        if year == 2025 and month <= 8:
            return False
        return True
    except (ValueError, TypeError, IndexError):
        return True


# ----------------------------------------------------------------------
# API pública
# ----------------------------------------------------------------------
def anonymize(
    data: dict | list,
    *,
    keep_prefix: bool = True,
    salt: str | None = None,
) -> tuple[dict | list, dict]:
    """Pseudonimiza + filtra um JSON de logbook.

    Args:
        data: dict {RECORDS: [...]} ou array de objetos
        keep_prefix: usa 'CPF_xxxx' e 'Profissional_NNNN' (vs hash puro / inteiro)
        salt: salt explícito; se None, gera aleatório por execução

    Retorna (json_pseudonimizado, stats), onde stats inclui contagens e mappings.
    """
    if salt is None:
        salt = _make_salt()

    has_records = (isinstance(data, dict) and "RECORDS" in data
                   and isinstance(data["RECORDS"], list))
    records = data["RECORDS"] if has_records else (data if isinstance(data, list) else [])

    original_count = len(records)

    # 1. Filtrar por data
    filtered = [r for r in records if _filter_by_date(r)]
    removed_count = original_count - len(filtered)

    # 2. Pseudonimizar
    cpf_map: dict[str, str] = {}
    nome_map: dict[str, str] = {}
    name_seen: dict[str, str] = {}  # normalized_name → pseudo
    name_index = 0

    cpf_changes = 0
    nome_changes = 0
    out_records = []

    for src in filtered:
        # Deep clone
        import json as _json
        dst = _json.loads(_json.dumps(src))

        # CPF
        if dst.get("cpf") is not None:
            cpf_raw = str(dst["cpf"])
            token = cpf_map.get(cpf_raw)
            if token is None:
                h = _sha256_b64url(salt + "|" + cpf_raw)
                token = f"CPF_{h[:12]}" if keep_prefix else h
                cpf_map[cpf_raw] = token
            dst["cpf"] = token
            cpf_changes += 1

        # Profissional (nome)
        if dst.get("profissional") is not None:
            nome_raw = str(dst["profissional"])
            key = _normalize_name(nome_raw)
            pseudo = name_seen.get(key)
            if pseudo is None:
                name_index += 1
                pseudo = (f"Profissional_{name_index:04d}"
                          if keep_prefix else str(name_index))
                name_seen[key] = pseudo
                # mapping por nome original (primeira ocorrência)
                nome_map[nome_raw] = pseudo
            dst["profissional"] = pseudo
            nome_changes += 1

        # curso_aprimoramento — strip "Aprimoramento em "
        if dst.get("curso_aprimoramento"):
            curso = str(dst["curso_aprimoramento"])
            if curso.startswith(APRIMORAMENTO_PREFIX):
                dst["curso_aprimoramento"] = curso[len(APRIMORAMENTO_PREFIX):]

        out_records.append(dst)

    if has_records:
        out: dict | list = {**data, "RECORDS": out_records}
    else:
        out = out_records

    stats = {
        "registros_originais": original_count,
        "registros_removidos": removed_count,
        "registros_processados": len(out_records),
        "cpf_trocados": cpf_changes,
        "nomes_trocados": nome_changes,
        "salt": salt,
        "cpf_map": cpf_map,
        "nome_map": nome_map,
    }
    return out, stats


def mapping_to_csv(stats: dict) -> str:
    """Gera CSV de mapeamento (tipo,original,pseudonimo). Para auditoria local — NUNCA commitar."""
    lines = ['"tipo","original","pseudonimo"']
    for orig, pseudo in stats.get("cpf_map", {}).items():
        lines.append(f'"cpf","{orig}","{pseudo}"')
    for orig, pseudo in stats.get("nome_map", {}).items():
        safe_orig = orig.replace('"', '""')
        lines.append(f'"profissional","{safe_orig}","{pseudo}"')
    return "\n".join(lines)
