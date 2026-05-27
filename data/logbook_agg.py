"""Agregações da aba Logbook — port 1:1 da lógica de index.html (logbook dashboard).

Cobre as 3 sub-abas:
  • Visão Geral: KPIs + 8 gráficos
  • Análise Diagnóstica: progressão, heatmap, dificuldade/curso, institucional, CIDs alta complexidade
  • Análise Preditiva: combinação com analise_preditiva_{rede}.json + predicoes_ml_dificuldade.json

Filtros suportados: rede, data_inicio, data_fim, curso, instituicao, hospital.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

from data import loader
from data.parsers import parse_date


DIF_LABELS = {1: "Fácil", 2: "Médio", 3: "Difícil", 4: "Muito Difícil", 5: "Extremo"}
DIF_COLORS = {
    "Fácil": "#10b981",
    "Médio": "#f59e0b",
    "Difícil": "#ea580c",
    "Muito Difícil": "#ef4444",
    "Extremo": "#991b1b",
    "Não informado": "#9ca3af",
}


# ----------------------------------------------------------------------
# Filtros e opções
# ----------------------------------------------------------------------
def _to_date(date_str: str | None):
    if not date_str:
        return None
    return parse_date(date_str)


def _filter_records(
    records: list[dict],
    rede: str | None,
    data_inicio: str | None,
    data_fim: str | None,
    curso: str | None,
    instituicao: str | None,
    hospital: str | None,
) -> list[dict]:
    out = records
    if rede and rede != "Todas":
        out = [r for r in out if r.get("rede_formadora") == rede]

    ini = _to_date(data_inicio)
    fim = _to_date(data_fim)
    if ini or fim:
        filt = []
        for r in out:
            dt = parse_date(r.get("data_hora_realizacao"))
            if dt is None:
                continue
            # Comparar sem timezone pra evitar incompatibilidades
            naive = dt.replace(tzinfo=None)
            if ini and naive < ini.replace(tzinfo=None):
                continue
            if fim and naive > fim.replace(tzinfo=None):
                continue
            filt.append(r)
        out = filt

    if curso and curso != "Todos":
        out = [r for r in out if r.get("curso_aprimoramento") == curso]
    if instituicao and instituicao != "Todas":
        out = [r for r in out if r.get("instituicao_formadora") == instituicao]
    if hospital and hospital != "Todos":
        out = [r for r in out if r.get("hospital_atuacao") == hospital]
    return out


def available_cursos() -> list[str]:
    records = loader.get_logbook_raw()
    items = sorted({r.get("curso_aprimoramento") for r in records if r.get("curso_aprimoramento")})
    return ["Todos", *items]


def available_instituicoes() -> list[str]:
    records = loader.get_logbook_raw()
    items = sorted({r.get("instituicao_formadora") for r in records if r.get("instituicao_formadora")})
    return ["Todas", *items]


def available_hospitais() -> list[str]:
    records = loader.get_logbook_raw()
    items = sorted({r.get("hospital_atuacao") for r in records if r.get("hospital_atuacao")})
    return ["Todos", *items]


# ----------------------------------------------------------------------
# Helpers internos
# ----------------------------------------------------------------------
def _month_key_sort(k: str) -> tuple[int, int]:
    m, y = k.split("/")
    return (int(y), int(m))


# ----------------------------------------------------------------------
# Entrypoint principal
# ----------------------------------------------------------------------
@lru_cache(maxsize=128)
def aggregate_for(
    rede: str = "Todas",
    data_inicio: str | None = None,
    data_fim: str | None = None,
    curso: str | None = None,
    instituicao: str | None = None,
    hospital: str | None = None,
) -> dict:
    records_all = loader.get_logbook_raw()
    rec = _filter_records(records_all, rede, data_inicio, data_fim, curso, instituicao, hospital)

    total = len(rec)

    # --- KPIs ---
    profissionais = len({r.get("id_profissional") for r in rec if r.get("id_profissional") is not None})
    instituicoes_form = len({r.get("id_hospital_formador") for r in rec if r.get("id_hospital_formador")})
    hospitais_atu = len({r.get("id_estabelecimento") for r in rec if r.get("id_estabelecimento")})
    cursos_unicos = len({r.get("id_aprimoramento") for r in rec if r.get("id_aprimoramento") is not None})

    media_dev = sum((r.get("nivel_desenvolvimento") or 0) for r in rec) / total if total else 0
    media_dif = sum((r.get("dificuldade") or 0) for r in rec) / total if total else 0

    # --- VISÃO GERAL ---
    temporal_count: Counter = Counter()
    for r in rec:
        dt = parse_date(r.get("data_hora_realizacao"))
        if dt:
            temporal_count[f"{dt.month}/{dt.year}"] += 1
    temporal = sorted(temporal_count.items(), key=lambda kv: _month_key_sort(kv[0]))

    # Top instituições: além de contar por sigla, guarda metadados pro tooltip
    # (nome completo, cidade, UF). Uma sigla → um conjunto de metadados.
    inst_meta: dict[str, dict] = {}
    inst_count: Counter = Counter()
    for r in rec:
        s = r.get("sigla_formadora") or "Não informado"
        inst_count[s] += 1
        if s not in inst_meta:
            inst_meta[s] = {
                "nome": r.get("instituicao_formadora") or s,
                "cidade": r.get("cidade_formadora") or "",
                "uf_sigla": r.get("uf_formadora_sigla") or "",
            }
    instituicoes_top = inst_count.most_common(10)
    instituicoes_top_hover = []
    for sigla, _ in instituicoes_top:
        m = inst_meta.get(sigla, {})
        nome = m.get("nome", sigla)
        cidade = m.get("cidade", "")
        uf = m.get("uf_sigla", "")
        local = f"{cidade}/{uf}" if cidade and uf else (cidade or uf)
        instituicoes_top_hover.append(
            f"<b>{nome}</b><br>{local}" if local else f"<b>{nome}</b>"
        )

    niveis_count: Counter = Counter()
    for r in rec:
        v = r.get("nivel_desenvolvimento")
        if v in (1, 2, 3, 4, 5):
            niveis_count[f"Nível {v}"] += 1
    niveis = [(f"Nível {i}", niveis_count.get(f"Nível {i}", 0)) for i in range(1, 6)]

    dif_count: Counter = Counter()
    for r in rec:
        v = r.get("dificuldade")
        if v in DIF_LABELS:
            dif_count[DIF_LABELS[v]] += 1
        else:
            dif_count["Não informado"] += 1
    ordem_dif = ["Fácil", "Médio", "Difícil", "Muito Difícil", "Extremo", "Não informado"]
    dificuldade = [(k, dif_count[k]) for k in ordem_dif if dif_count.get(k, 0) > 0]

    proc_counter: Counter = Counter()
    for r in rec:
        p = r.get("procedimento_nao_listado") or r.get("no_procedimento") or "Não especificado"
        proc_counter[p] += 1
    procedimentos_top = proc_counter.most_common(10)

    cids_top = Counter(r.get("no_cid") for r in rec if r.get("no_cid")).most_common(10)
    # Top hospitais de atuação: igual instituições, monta metadata pro hover
    hosp_meta: dict[str, dict] = {}
    hosp_count: Counter = Counter()
    for r in rec:
        h = r.get("hospital_atuacao") or "Não informado"
        hosp_count[h] += 1
        if h not in hosp_meta:
            hosp_meta[h] = {
                "cidade": r.get("cidade_atuacao") or "",
                "uf_sigla": r.get("uf_atuacao_sigla") or "",
            }
    hospitais_top = hosp_count.most_common(10)
    hospitais_top_hover = []
    for nome, _ in hospitais_top:
        m = hosp_meta.get(nome, {})
        cidade = m.get("cidade", "")
        uf = m.get("uf_sigla", "")
        local = f"{cidade}/{uf}" if cidade and uf else (cidade or uf)
        hospitais_top_hover.append(
            f"<b>{nome}</b><br>{local}" if local else f"<b>{nome}</b>"
        )
    cursos_top = Counter(r.get("curso_aprimoramento") or "Não informado" for r in rec).most_common(10)

    # --- DIAGNÓSTICA ---
    prog_mes: dict[str, dict[str, float]] = {}
    for r in rec:
        dt = parse_date(r.get("data_hora_realizacao"))
        nv = r.get("nivel_desenvolvimento")
        if dt and nv:
            k = f"{dt.month}/{dt.year}"
            entry = prog_mes.setdefault(k, {"sum": 0.0, "count": 0})
            entry["sum"] += nv
            entry["count"] += 1
    progressao = sorted(
        ((k, v["sum"] / v["count"]) for k, v in prog_mes.items() if v["count"] > 0),
        key=lambda kv: _month_key_sort(kv[0]),
    )

    heatmap: dict[tuple[int, int], int] = {(n, d): 0 for n in range(1, 6) for d in range(1, 6)}
    for r in rec:
        n = r.get("nivel_desenvolvimento")
        d = r.get("dificuldade")
        if n in range(1, 6) and d in range(1, 6):
            heatmap[(n, d)] += 1

    curso_dif: dict[str, list[float]] = {}
    for r in rec:
        c = r.get("curso_aprimoramento") or "Não informado"
        if r.get("dificuldade"):
            curso_dif.setdefault(c, []).append(float(r["dificuldade"]))
    top_volume = sorted(curso_dif.items(), key=lambda kv: len(kv[1]), reverse=True)[:10]
    dificuldade_por_curso = sorted(
        [(c, sum(v) / len(v)) for c, v in top_volume],
        key=lambda kv: kv[1],
        reverse=True,
    )

    inst_stats: dict[str, dict[str, float]] = {}
    for r in rec:
        i = r.get("sigla_formadora") or "Não informado"
        s = inst_stats.setdefault(i, {"vol": 0, "sd": 0.0, "cd": 0, "sn": 0.0, "cn": 0})
        s["vol"] += 1
        if r.get("dificuldade"):
            s["sd"] += r["dificuldade"]
            s["cd"] += 1
        if r.get("nivel_desenvolvimento"):
            s["sn"] += r["nivel_desenvolvimento"]
            s["cn"] += 1
    top_inst = sorted(inst_stats.items(), key=lambda kv: kv[1]["vol"], reverse=True)[:10]
    institucional = [
        {
            "sigla": i,
            "volume": int(s["vol"]),
            "media_dificuldade": s["sd"] / s["cd"] if s["cd"] else 0,
            "media_nivel": s["sn"] / s["cn"] if s["cn"] else 0,
        }
        for i, s in top_inst
    ]

    cids_alta_complexidade = Counter(
        r.get("no_cid")
        for r in rec
        if r.get("dificuldade") and r["dificuldade"] >= 3 and r.get("no_cid")
    ).most_common(10)

    # --- GEOGRAFIA ---
    # Contagem de registros por estado (sigla → count) e por município (sigla_uf → cidade → count)
    geo_estados: Counter = Counter()
    geo_municipios: dict[str, Counter] = {}
    geo_municipios_ibge: dict[str, Counter] = {}  # sigla_uf → ibge_6dig → count
    for r in rec:
        sigla = r.get("uf_atuacao_sigla")
        cidade = r.get("cidade_atuacao")
        ibge = r.get("ibge_atuacao")
        if sigla:
            geo_estados[sigla] += 1
            if cidade:
                geo_municipios.setdefault(sigla, Counter())[cidade] += 1
            if ibge:
                geo_municipios_ibge.setdefault(sigla, Counter())[str(ibge)[:6]] += 1
    # Converte pra estrutura serializável (dict normais)
    geo_municipios_dict = {s: dict(c) for s, c in geo_municipios.items()}
    geo_municipios_ibge_dict = {s: dict(c) for s, c in geo_municipios_ibge.items()}

    # --- PREDITIVA (dados derivados — combinação com claude analysis vem na página) ---
    proc_nl: Counter = Counter()
    for r in rec:
        p = r.get("procedimento_nao_listado")
        if p:
            proc_nl[str(p).lower().strip()] += 1
    procedimentos_nl_total = sum(proc_nl.values())
    procedimentos_nl_unicos = len(proc_nl)

    return {
        # KPIs
        "total": total,
        "profissionais": profissionais,
        "instituicoes_form": instituicoes_form,
        "hospitais_atu": hospitais_atu,
        "cursos_unicos": cursos_unicos,
        "media_dev": round(media_dev, 2),
        "media_dif": round(media_dif, 2),
        # Visão Geral
        "temporal": temporal,
        "instituicoes_top": instituicoes_top,
        "instituicoes_top_hover": instituicoes_top_hover,
        "niveis": niveis,
        "dificuldade": dificuldade,
        "procedimentos_top": procedimentos_top,
        "cids_top": cids_top,
        "hospitais_top": hospitais_top,
        "hospitais_top_hover": hospitais_top_hover,
        "cursos_top": cursos_top,
        # Geografia
        "geo_estados": dict(geo_estados),
        "geo_municipios": geo_municipios_dict,
        "geo_municipios_ibge": geo_municipios_ibge_dict,
        # Diagnóstica
        "progressao": progressao,
        "heatmap": heatmap,
        "dificuldade_por_curso": dificuldade_por_curso,
        "institucional": institucional,
        "cids_alta_complexidade": cids_alta_complexidade,
        # Preditiva (derivados)
        "procedimentos_nl_total": procedimentos_nl_total,
        "procedimentos_nl_unicos": procedimentos_nl_unicos,
    }
