"""Agregações da aba Matrículas — port 1:1 da lógica original de dashboard.html e mapas.html.

Cada função extrai um corte específico do array de records (já filtrado por rede/edital).
A função `aggregate_for(rede, edital)` é o entrypoint principal: aplica filtros e retorna
todas as métricas calculadas como um dict, com cache em memória.

Filtros disponíveis dinamicamente:
  • `available_redes()`   — lê do JSON quais redes existem
  • `available_editais()` — lê do JSON quais editais existem (campo `edital`)
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from functools import lru_cache
from typing import Any

from data import loader
from data.constants import (
    ESTADOS_REGIOES,
    ESTADOS_SIGLAS,
    SIGLAS_ESTADOS,
    extrair_uf_de_municipio,
)


# ----------------------------------------------------------------------
# Helpers de baixo nível
# ----------------------------------------------------------------------
def _parse_nested(value: Any) -> dict | None:
    """JSON aninhado dos campos pode vir como string (do banco) ou já como dict."""
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


def _counter_field(records: list[dict], container: str, field: str) -> dict[str, int]:
    c: Counter = Counter()
    for r in records:
        obj = _parse_nested(r.get(container))
        if not obj:
            continue
        v = obj.get(field)
        if v is None or v == "":
            continue
        c[str(v)] += 1
    return dict(c)


def _counter_top_level(records: list[dict], field: str) -> dict[str, int]:
    c: Counter = Counter()
    for r in records:
        v = r.get(field)
        if v is None or v == "":
            continue
        c[str(v)] += 1
    return dict(c)


_CURSO_NUM_PREFIX = re.compile(r"^\d+\.\s*")


def _limpar_curso(nome: str) -> str:
    return _CURSO_NUM_PREFIX.sub("", str(nome)).strip()


# ----------------------------------------------------------------------
# Cálculos especiais
# ----------------------------------------------------------------------
def calcular_idades(records: list[dict]) -> list[int]:
    hoje = date.today()
    out: list[int] = []
    for r in records:
        obj = _parse_nested(r.get("info_pessoais"))
        if not obj:
            continue
        nasc = obj.get("data_nascimento")
        if not nasc:
            continue
        try:
            ano = int(str(nasc)[:4])
            idade = hoje.year - ano
            if 0 < idade < 120:
                out.append(idade)
        except (ValueError, TypeError):
            continue
    return out


def calcular_tempo_graduado(records: list[dict]) -> list[int]:
    hoje = date.today()
    out: list[int] = []
    for r in records:
        obj = _parse_nested(r.get("formacao_academica"))
        if not obj:
            continue
        dt = obj.get("data_formacao")
        if not dt:
            continue
        try:
            ano = int(str(dt)[:4])
            anos = hoje.year - ano
            if 0 <= anos < 60:
                out.append(anos)
        except (ValueError, TypeError):
            continue
    return out


def processar_nome_social(records: list[dict]) -> dict[str, int]:
    com, sem = 0, 0
    for r in records:
        obj = _parse_nested(r.get("info_pessoais"))
        nome = (obj or {}).get("nome_social")
        if nome and str(nome).strip():
            com += 1
        else:
            sem += 1
    return {"Sim": com, "Não": sem}


def extrair_cursos(records: list[dict], top: int = 25) -> dict[str, int]:
    c: Counter = Counter()
    for r in records:
        ls = _parse_nested(r.get("listas_selecao"))
        if not ls:
            continue
        vp = ls.get("vaga_principal_jdata") or {}
        nome = vp.get("curso.nome")
        if not nome:
            continue
        c[_limpar_curso(nome)] += 1
    return dict(c.most_common(top))


def extrair_regiao_nascimento(records: list[dict]) -> dict[str, int]:
    c: Counter = Counter()
    for r in records:
        obj = _parse_nested(r.get("info_pessoais"))
        if not obj:
            continue
        estado = obj.get("rg_uf_ds")
        if not estado:
            continue
        c[ESTADOS_REGIOES.get(estado, "Outros")] += 1
    return dict(c)


def extrair_regiao_vaga(records: list[dict]) -> dict[str, int]:
    c: Counter = Counter()
    for r in records:
        ls = _parse_nested(r.get("listas_selecao"))
        if not ls:
            continue
        vp = ls.get("vaga_principal_jdata") or {}
        estado = vp.get("ibge.no_uf")
        if not estado:
            continue
        c[ESTADOS_REGIOES.get(estado, "Outros")] += 1
    return dict(c)


def calcular_fluxo_regional(records: list[dict]) -> list[dict]:
    """4 momentos × N regiões = pontos de linha pra plotar evolução regional."""
    momentos: dict[str, Counter] = {
        "Nascimento": Counter(),
        "Graduação": Counter(),
        "CRM": Counter(),
        "Vaga": Counter(),
    }

    for r in records:
        # Nascimento: info_pessoais.municipio → UF → região
        ip = _parse_nested(r.get("info_pessoais"))
        if ip:
            sigla = extrair_uf_de_municipio(ip.get("municipio"))
            estado = SIGLAS_ESTADOS.get(sigla) if sigla else None
            if estado:
                momentos["Nascimento"][ESTADOS_REGIOES.get(estado, "Outros")] += 1

        fa = _parse_nested(r.get("formacao_academica"))
        if fa:
            # Graduação: municipio_formacao → UF → região
            sigla = extrair_uf_de_municipio(fa.get("municipio_formacao"))
            estado = SIGLAS_ESTADOS.get(sigla) if sigla else None
            if estado:
                momentos["Graduação"][ESTADOS_REGIOES.get(estado, "Outros")] += 1
            # CRM: uf_crm_ds → região
            estado_crm = fa.get("uf_crm_ds")
            if estado_crm:
                momentos["CRM"][ESTADOS_REGIOES.get(estado_crm, "Outros")] += 1

        ls = _parse_nested(r.get("listas_selecao"))
        if ls:
            vp = ls.get("vaga_principal_jdata") or {}
            estado_vaga = vp.get("ibge.no_uf")
            if estado_vaga:
                momentos["Vaga"][ESTADOS_REGIOES.get(estado_vaga, "Outros")] += 1

    regioes_unicas = set()
    for m in momentos.values():
        regioes_unicas.update(m.keys())

    pontos = []
    for regiao in sorted(regioes_unicas):
        for nome in ("Nascimento", "Graduação", "CRM", "Vaga"):
            pontos.append({
                "regiao": regiao,
                "momento": nome,
                "quantidade": momentos[nome].get(regiao, 0),
            })
    return pontos


# ----------------------------------------------------------------------
# Mapas (estados)
# ----------------------------------------------------------------------
def mapa_estado_nascimento(records: list[dict]) -> dict[str, int]:
    return _counter_field(records, "info_pessoais", "rg_uf_ds")


def mapa_estado_graduacao(records: list[dict]) -> dict[str, int]:
    c: Counter = Counter()
    for r in records:
        fa = _parse_nested(r.get("formacao_academica"))
        if not fa:
            continue
        sigla = extrair_uf_de_municipio(fa.get("municipio_formacao"))
        estado = SIGLAS_ESTADOS.get(sigla) if sigla else None
        if estado:
            c[estado] += 1
    return dict(c)


def mapa_estado_crm(records: list[dict]) -> dict[str, int]:
    return _counter_field(records, "formacao_academica", "uf_crm_ds")


def mapa_estado_vaga(records: list[dict]) -> tuple[dict[str, int], list[dict]]:
    c: Counter = Counter()
    vagas_por_municipio: list[dict] = []
    for r in records:
        ls = _parse_nested(r.get("listas_selecao"))
        if not ls:
            continue
        vp = ls.get("vaga_principal_jdata") or {}
        estado = vp.get("ibge.no_uf")
        if not estado:
            continue
        c[estado] += 1
        mun = vp.get("ibge.no_municipio")
        curso = vp.get("curso.nome")
        if not mun or not curso:
            continue
        curso_limpo = _limpar_curso(curso)
        for entry in vagas_por_municipio:
            if entry["vaga_uf"] == estado and entry["vaga_municipio"] == mun:
                if curso_limpo not in entry["cursos"]:
                    entry["cursos"].append(curso_limpo)
                break
        else:
            vagas_por_municipio.append({
                "vaga_uf": estado,
                "vaga_municipio": mun,
                "cursos": [curso_limpo],
            })
    return dict(c), vagas_por_municipio


# ----------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------
def _filtrar(records: list[dict], rede: str, edital: str) -> list[dict]:
    out = records
    if rede and rede != "Todas":
        out = [r for r in out if r.get("rede_formadora") == rede]
    if edital and edital != "Todos":
        # edital no JSON vem como int; compara via str pra robustez
        out = [r for r in out if str(r.get("edital")) == str(edital)]
    return out


@lru_cache(maxsize=64)
def aggregate_for(rede: str = "Todas", edital: str = "Todos") -> dict:
    """Retorna todas as agregações de matrículas para o corte (rede, edital)."""
    records_all = loader.get_matriculas_raw()
    rec = _filtrar(records_all, rede, edital)

    mapa_vaga, vagas_municipios = mapa_estado_vaga(rec)

    return {
        "total": len(rec),
        # Dados Pessoais
        "raca_ds": _counter_field(rec, "info_pessoais", "raca_ds"),
        "sexo_ds": _counter_field(rec, "info_pessoais", "sexo_ds"),
        "idade": calcular_idades(rec),
        "estado_civil_ds": _counter_field(rec, "info_pessoais", "estado_civil_ds"),
        "ident_genero_ds": _counter_field(rec, "info_pessoais", "ident_genero_ds"),
        "orientacao_sexual_ds": _counter_field(rec, "info_pessoais", "orientacao_sexual_ds"),
        "tem_nome_social": processar_nome_social(rec),
        "aa_tipo_ds": _counter_field(rec, "listas_selecao", "aa_flag_ds"),
        # Formação Acadêmica
        "tempo_graduado": calcular_tempo_graduado(rec),
        "pais_formacao_ds": _counter_field(rec, "formacao_academica", "pais_formacao_ds"),
        # Especialidades
        "rm_rec_cnrm_ds": _counter_field(rec, "listas_selecao", "rm_rec_cnrm_ds"),
        "tit_esp_amb_ds": _counter_field(rec, "listas_selecao", "tit_esp_amb_ds"),
        "rm_1_esp_medica_ds": _counter_field(rec, "listas_selecao", "rm_1_esp_medica_ds"),
        "rm_2_esp_medica_ds": _counter_field(rec, "listas_selecao", "rm_2_esp_medica_ds"),
        "amb_1_esp_medica_ds": _counter_field(rec, "listas_selecao", "amb_1_esp_medica_ds"),
        "amb_2_esp_medica_ds": _counter_field(rec, "listas_selecao", "amb_2_esp_medica_ds"),
        "curso_nome_limpo": extrair_cursos(rec),
        # Distribuição Geográfica
        "regiao_nascimento": extrair_regiao_nascimento(rec),
        "regiao_vaga": extrair_regiao_vaga(rec),
        "fluxo_regional": calcular_fluxo_regional(rec),
        # Mapas
        "mapa_estado_nascimento": mapa_estado_nascimento(rec),
        "mapa_estado_graduacao": mapa_estado_graduacao(rec),
        "mapa_estado_crm": mapa_estado_crm(rec),
        "mapa_estado_vaga": mapa_vaga,
        "vagas_por_municipio": vagas_municipios,
        # Apropriação (campos top-level dos records — A/E/N)
        "apropriacao_redes": _counter_top_level(rec, "apropriacao_redes"),
        "apropriacao_coordenacao": _counter_top_level(rec, "apropriacao_coordenacao"),
        "apropriacao_gestao": _counter_top_level(rec, "apropriacao_gestao"),
        "apropriacao_evidencias": _counter_top_level(rec, "apropriacao_evidencias"),
        "apropriacao_regulacao": _counter_top_level(rec, "apropriacao_regulacao"),
        "apropriacao_economia": _counter_top_level(rec, "apropriacao_economia"),
    }


def available_editais() -> list[str]:
    """Editais disponíveis no JSON (string ordenada crescente). Sempre tem 'Todos'."""
    records = loader.get_matriculas_raw()
    eds = set()
    for r in records:
        e = r.get("edital")
        if e is not None:
            eds.add(int(e) if isinstance(e, (int, float)) and not isinstance(e, bool) else str(e))
    return ["Todos", *(str(e) for e in sorted(eds, key=lambda x: (not isinstance(x, int), x)))]


def available_redes() -> list[str]:
    """Redes formadoras presentes no JSON (ordenadas alfabeticamente). Sempre tem 'Todas'."""
    records = loader.get_matriculas_raw()
    redes = {r.get("rede_formadora") for r in records if r.get("rede_formadora")}
    return ["Todas", *sorted(redes)]
