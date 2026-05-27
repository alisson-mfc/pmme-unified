"""Anonimizador de matrículas — port 1:1 de anonimizador_inscritos4.html.

Regras (mesmas do HTML original):
  • Mascara com `*` × len: cpf, rg, pispasep, titulo_eleitor, crm, rqe, rg_dt_emissao, cep, telefone
  • Substitui por '[NOME ANONIMIZADO]': nome, nome_mae, nome_pai, nome_social
  • Substitui por '[ORGAO ANONIMIZADO]': rg_orgao_exp, rg_orgao_exp_ds
  • u_email → '[EMAIL REMOVIDO]'
  • logradouro/numero/complemento/bairro → '[ENDERECO REMOVIDO]'
  • info_pessoais: raca_ds 'marrom' → 'Parda', sexo_ds 'macho' → 'Masculino'
  • listas_selecao.rm_rec_cnrm_ds: 'Tenho...' → 'Possuo...'
  • listas_selecao.vaga_principal_jdata['curso.nome'] e vaga_secundaria_jdata['curso.nome']:
    remove prefixo de numeração e 'Aprimoramento em '

Aplica recursivamente em info_pessoais, formacao_academica, info_contato, listas_selecao
(que vêm como JSON strings serializadas).
"""

from __future__ import annotations

import json
import re
from typing import Any

# ----------------------------------------------------------------------
# CONFIGURAÇÃO — fiel ao anonimizador_inscritos4.html
# ----------------------------------------------------------------------
MASK_FIELDS = {"cpf", "rg", "pispasep", "titulo_eleitor", "crm", "rqe",
               "rg_dt_emissao", "cep", "telefone"}
NAME_FIELDS = {"nome", "nome_mae", "nome_pai", "nome_social"}
ORG_FIELDS = {"rg_orgao_exp", "rg_orgao_exp_ds"}
EMAIL_FIELDS = {"u_email"}
ADDR_FIELDS = {"logradouro", "numero", "complemento", "bairro"}

INFO_PESSOAIS_FIELDS = ["rg", "cpf", "nome", "nome_mae", "nome_pai", "pispasep",
                        "nome_social", "rg_orgao_exp", "rg_dt_emissao",
                        "titulo_eleitor", "rg_orgao_exp_ds"]
FORMACAO_FIELDS = ["crm", "rqe"]
INFO_CONTATO_FIELDS = ["u_email", "telefone", "logradouro", "numero", "complemento",
                       "cep", "bairro"]

CURSO_PREFIX_RE = re.compile(r"^(?:\d+\.?\s*[\.\-]?\s*)?Aprimoramento em\s*", re.IGNORECASE)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _anonymize_value(key: str, value: Any) -> Any:
    """Reproduz exatamente anonymizeValue do JS."""
    if value is None or value == "":
        return value
    if key in MASK_FIELDS:
        length = len(str(value)) or 4
        return "*" * length
    if key in NAME_FIELDS:
        return "[NOME ANONIMIZADO]"
    if key in ORG_FIELDS:
        return "[ORGAO ANONIMIZADO]"
    if key in EMAIL_FIELDS:
        return "[EMAIL REMOVIDO]"
    if key in ADDR_FIELDS:
        return "[ENDERECO REMOVIDO]"
    return value


def _clean_course_name(name: Any) -> Any:
    """Remove numeração + 'Aprimoramento em ' (cleanCourseName do JS)."""
    if not name:
        return name
    return CURSO_PREFIX_RE.sub("", str(name)).strip()


def _parse_nested(value: Any) -> dict | None:
    """Campos JSON aninhados vêm como string ou dict."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _serialize_nested(obj: dict, original_was_string: bool) -> Any:
    """Re-serializa como string se o original era string; caso contrário mantém dict."""
    return json.dumps(obj, ensure_ascii=False) if original_was_string else obj


# ----------------------------------------------------------------------
# Processamento de um registro
# ----------------------------------------------------------------------
def _process_entry(entry: dict) -> tuple[dict, int]:
    """Aplica todas as regras ao registro. Retorna (registro_novo, campos_alterados)."""
    new = json.loads(json.dumps(entry))  # deep clone
    altered = 0

    # 1. CPF raiz
    if new.get("cpf"):
        new["cpf"] = _anonymize_value("cpf", new["cpf"])
        altered += 1

    # 2. info_pessoais (com correções de raça e sexo)
    if new.get("info_pessoais"):
        orig_is_str = isinstance(new["info_pessoais"], str)
        parsed = _parse_nested(new["info_pessoais"])
        if parsed is not None:
            # Correção raça
            raca = parsed.get("raca_ds")
            if isinstance(raca, str) and raca.strip().lower() == "marrom":
                parsed["raca_ds"] = "Parda"
                altered += 1
            # Correção sexo
            sexo = parsed.get("sexo_ds")
            if isinstance(sexo, str) and sexo.strip().lower() == "macho":
                parsed["sexo_ds"] = "Masculino"
                altered += 1
            # Anonimização padrão
            for f in INFO_PESSOAIS_FIELDS:
                if parsed.get(f):
                    parsed[f] = _anonymize_value(f, parsed[f])
                    altered += 1
            new["info_pessoais"] = _serialize_nested(parsed, orig_is_str)

    # 3. formacao_academica
    if new.get("formacao_academica"):
        orig_is_str = isinstance(new["formacao_academica"], str)
        parsed = _parse_nested(new["formacao_academica"])
        if parsed is not None:
            for f in FORMACAO_FIELDS:
                if parsed.get(f):
                    parsed[f] = _anonymize_value(f, parsed[f])
                    altered += 1
            new["formacao_academica"] = _serialize_nested(parsed, orig_is_str)

    # 4. info_contato
    if new.get("info_contato"):
        orig_is_str = isinstance(new["info_contato"], str)
        parsed = _parse_nested(new["info_contato"])
        if parsed is not None:
            for f in INFO_CONTATO_FIELDS:
                if parsed.get(f):
                    parsed[f] = _anonymize_value(f, parsed[f])
                    altered += 1
            new["info_contato"] = _serialize_nested(parsed, orig_is_str)

    # 5. listas_selecao
    if new.get("listas_selecao"):
        orig_is_str = isinstance(new["listas_selecao"], str)
        parsed = _parse_nested(new["listas_selecao"])
        if parsed is not None:
            # rm_rec_cnrm_ds: "Tenho..." → "Possuo..."
            rm = parsed.get("rm_rec_cnrm_ds")
            if isinstance(rm, str) and re.match(r"^Tenho", rm, re.IGNORECASE):
                new_rm = re.sub(r"^Tenho", "Possuo", rm, count=1, flags=re.IGNORECASE)
                if new_rm != rm:
                    parsed["rm_rec_cnrm_ds"] = new_rm
                    altered += 1

            # Vaga principal — limpar curso.nome
            vp = parsed.get("vaga_principal_jdata")
            if isinstance(vp, dict) and vp.get("curso.nome"):
                old = vp["curso.nome"]
                vp["curso.nome"] = _clean_course_name(old)
                if old != vp["curso.nome"]:
                    altered += 1

            # Vaga secundária — limpar curso.nome
            vs = parsed.get("vaga_secundaria_jdata")
            if isinstance(vs, dict) and vs.get("curso.nome"):
                old = vs["curso.nome"]
                vs["curso.nome"] = _clean_course_name(old)
                if old != vs["curso.nome"]:
                    altered += 1

            new["listas_selecao"] = _serialize_nested(parsed, orig_is_str)

    return new, altered


# ----------------------------------------------------------------------
# API pública
# ----------------------------------------------------------------------
def anonymize(data: dict | list) -> tuple[dict | list, dict]:
    """Anonimiza JSON (estrutura {RECORDS: [...]} ou array direto).

    Retorna (json_anonimizado, stats).
    """
    has_records = isinstance(data, dict) and "RECORDS" in data and isinstance(data["RECORDS"], list)
    records = data["RECORDS"] if has_records else (data if isinstance(data, list) else [])

    out_records = []
    total_altered = 0
    for r in records:
        new_r, n = _process_entry(r)
        out_records.append(new_r)
        total_altered += n

    if has_records:
        out: dict | list = {**data, "RECORDS": out_records}
    else:
        out = out_records

    stats = {
        "registros_processados": len(records),
        "campos_alterados": total_altered,
    }
    return out, stats
