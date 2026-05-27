"""Análise Gemini do logbook — refator de processar_ia.py.

Mudanças vs original:
  • Usa Google Gemini via SDK oficial `google-genai` (antes era Anthropic Claude).
  • Cache por hash SHA-256 — não re-roda se o subset não mudou.
  • Output em `analises/logbook/{rede}/resultados.json` (estrutura idêntica ao
    `analise_preditiva_{rede}.json` original, para compat retroativa com o front).
  • Padroniza GEMINI_API_KEY (com fallback GOOGLE_API_KEY).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types as genai_types

from pipeline.cache import hash_subset, needs_processing


# ----------------------------------------------------------------------
# CONFIGURAÇÃO
# ----------------------------------------------------------------------
MODEL_TOPICOS = os.environ.get("GEMINI_MODEL_TOPICOS", "gemini-3.1-flash-lite")
MAX_TOKENS = 2000
MIN_RECORDS_PARA_PREDICAO = 5
TOP_N_PREDICAO = 20

def _discover_redes(records: list[dict]) -> list[str]:
    """Redes encontradas no JSON (dinâmico). Sempre tem 'Todas'."""
    redes = {r.get("rede_formadora") for r in records if r.get("rede_formadora")}
    return ["Todas", *sorted(redes)] if redes else ["Todas"]


# ----------------------------------------------------------------------
# CLIENTE GEMINI (lazy)
# ----------------------------------------------------------------------
_client: genai.Client | None = None


def _get_client() -> genai.Client | None:
    global _client
    if _client is not None:
        return _client
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None
    _client = genai.Client(api_key=key)
    return _client


# ----------------------------------------------------------------------
# 1. TÓPICOS — agrupamento de procedimentos não listados via Gemini
# ----------------------------------------------------------------------
def _parse_temas(texto: str) -> list[dict]:
    temas = []
    for linha in texto.split("\n"):
        linha = linha.strip()
        if not linha.startswith("TEMA|"):
            continue
        partes = linha.split("|")
        if len(partes) < 4:
            continue
        nome = partes[1].strip()
        descricao = partes[2].strip()
        procs = [p.strip() for p in partes[3].split(",") if p.strip()]
        if nome and procs:
            temas.append({
                "nome": nome,
                "descricao": descricao,
                "procedimentos": procs,
                "frequencia": len(procs),  # será atualizado depois
            })
    return temas


def _analisar_topicos(records: list[dict]) -> dict:
    """Identifica temas em procedimentos não listados via Claude."""
    procs: dict[str, int] = {}
    for r in records:
        p = r.get("procedimento_nao_listado")
        if p:
            key = str(p).lower().strip()
            if key:
                procs[key] = procs.get(key, 0) + 1

    if not procs:
        return {"temas": []}

    procs_unicos = list(procs.keys())
    print(f"    • {len(procs_unicos)} procedimentos únicos não listados")

    client = _get_client()
    if client is None:
        # Sem Claude: tema único agregando todos
        total = sum(procs.values())
        return {"temas": [{
            "nome": "[Sem agrupamento — Claude indisponível]",
            "descricao": "Configure ANTHROPIC_API_KEY para análise via IA.",
            "procedimentos": procs_unicos,
            "frequencia": total,
        }]}

    prompt = (
        "Você é um especialista em análise de procedimentos médicos/cirúrgicos.\n\n"
        "Recebeu a seguinte lista de procedimentos NÃO listados em um sistema "
        "logbook de aprendizado profissional:\n\n"
        + "\n".join(procs_unicos[:100])
        + "\n\nTAREFA: Analise esses procedimentos e identifique temas/categorias "
        "comuns. Para cada tema, liste os procedimentos pertencentes.\n\n"
        "RESPONDA em formato texto simples, com cada tema em uma linha usando este "
        "padrão EXATO (sem JSON):\n\n"
        "TEMA|NomeDo Tema|Descrição breve|proc1,proc2,proc3\n\n"
        "Exemplo:\nTEMA|Complicações|Procedimentos com complicações intraoperatórias|"
        "Hemorragia,Infecção,Reação\nTEMA|Emergências|Procedimentos de urgência|"
        "Intubação,RCP,Cricotomia\n\n"
        "Responda SOMENTE com as linhas TEMA, sem explicação adicional."
    )

    try:
        resp = client.models.generate_content(
            model=MODEL_TOPICOS,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=MAX_TOKENS,
                temperature=0.3,
            ),
        )
        resposta = resp.text or ""
    except Exception as e:
        print(f"    [erro Gemini tópicos]: {e}")
        return {"temas": []}

    temas = _parse_temas(resposta)

    # Recalcular frequência somando ocorrências reais de cada procedimento
    agrupados = set()
    for tema in temas:
        freq_total = 0
        for proc in tema["procedimentos"]:
            freq_total += procs.get(proc, 0)
            agrupados.add(proc)
        tema["frequencia"] = freq_total

    # Procedimentos não agrupados → tema extra
    nao_agrupados = {p: f for p, f in procs.items() if p not in agrupados}
    if nao_agrupados:
        temas.append({
            "nome": "[Outros Procedimentos]",
            "descricao": "Procedimentos não classificados nos temas acima",
            "procedimentos": list(nao_agrupados.keys()),
            "frequencia": sum(nao_agrupados.values()),
        })

    return {"temas": temas}


# ----------------------------------------------------------------------
# 2. TRAJETÓRIA — perfis estatísticos de profissionais
# ----------------------------------------------------------------------
def _analisar_trajetoria(records: list[dict]) -> dict:
    stats: dict = {}
    for r in records:
        pid = r.get("id_profissional")
        if pid is None:
            continue
        s = stats.setdefault(pid, {
            "volume": 0,
            "somaDev": 0, "countDev": 0,
            "somaDif": 0, "countDif": 0,
            "cids": set(), "procs": set(),
        })
        s["volume"] += 1
        if r.get("nivel_desenvolvimento"):
            s["somaDev"] += r["nivel_desenvolvimento"]
            s["countDev"] += 1
        if r.get("dificuldade"):
            s["somaDif"] += r["dificuldade"]
            s["countDif"] += 1
        if r.get("no_cid"):
            s["cids"].add(r["no_cid"])
        if r.get("no_procedimento"):
            s["procs"].add(r["no_procedimento"])

    perfis: dict[str, list] = {
        "Especialista em desenvolvimento": [],
        "Aprendiz em desenvolvimento": [],
        "Generalista em desenvolvimento": [],
    }
    perfis_detalhados: dict = {}

    for pid, s in stats.items():
        media_dev = s["somaDev"] / s["countDev"] if s["countDev"] else 0
        media_dif = s["somaDif"] / s["countDif"] if s["countDif"] else 0

        if media_dev >= 2.0:
            perfil = "Especialista em desenvolvimento"
        elif media_dev >= 1.0:
            perfil = "Aprendiz em desenvolvimento"
        else:
            perfil = "Generalista em desenvolvimento"

        perfis[perfil].append(pid)
        perfis_detalhados[pid] = {
            "volume": s["volume"],
            "mediaDesenvolvimento": round(media_dev, 2),
            "mediaDificuldade": round(media_dif, 2),
            "cidUnicos": len(s["cids"]),
            "procedimentos": len(s["procs"]),
            "perfil": perfil,
        }

    return {"perfis": perfis, "perfisDetalhados": perfis_detalhados}


# ----------------------------------------------------------------------
# 3. DIFICULDADE — estatísticas por CID e procedimento
# ----------------------------------------------------------------------
def _stats(values: list[float]) -> dict | None:
    if not values:
        return None
    media = sum(values) / len(values)
    var = sum((v - media) ** 2 for v in values) / len(values)
    return {
        "media": round(media, 2),
        "desvio": round(var ** 0.5, 2),
        "min": int(min(values)),
        "max": int(max(values)),
        "count": len(values),
    }


def _analisar_dificuldade(records: list[dict]) -> dict:
    cid_dif: dict[str, list[float]] = {}
    proc_dif: dict[str, list[float]] = {}

    for r in records:
        dif = r.get("dificuldade")
        if not dif:
            continue
        if r.get("no_cid"):
            cid_dif.setdefault(r["no_cid"], []).append(float(dif))
        if r.get("no_procedimento"):
            proc_dif.setdefault(r["no_procedimento"], []).append(float(dif))

    def _top(d: dict[str, list[float]], key_name: str) -> list[dict]:
        out = []
        for nome, vals in d.items():
            if len(vals) < MIN_RECORDS_PARA_PREDICAO:
                continue
            s = _stats(vals)
            if s:
                out.append({key_name: nome, **s})
        out.sort(key=lambda x: x["media"], reverse=True)
        return out[:TOP_N_PREDICAO]

    return {
        "cidStats": _top(cid_dif, "cid"),
        "procedimentoStats": _top(proc_dif, "procedimento"),
    }


# ----------------------------------------------------------------------
# PIPELINE POR REDE
# ----------------------------------------------------------------------
def _filtrar(records: list[dict], rede: str) -> list[dict]:
    if rede == "Todas":
        return records
    return [r for r in records if r.get("rede_formadora") == rede]


def _stable_view(records: list[dict]) -> list[dict]:
    """Projeta apenas campos relevantes pra análise — exclui cpf e profissional,
    que variam com o salt do pseudonimizador a cada execução. Isso garante que
    o cache não invalide quando só o salt mudou.
    """
    return [
        {
            "id_profissional": r.get("id_profissional"),
            "no_cid": r.get("no_cid"),
            "no_procedimento": r.get("no_procedimento"),
            "procedimento_nao_listado": r.get("procedimento_nao_listado"),
            "dificuldade": r.get("dificuldade"),
            "nivel_desenvolvimento": r.get("nivel_desenvolvimento"),
            "rede_formadora": r.get("rede_formadora"),
            "sigla_formadora": r.get("sigla_formadora"),
            "curso_aprimoramento": r.get("curso_aprimoramento"),
            "data_hora_realizacao": r.get("data_hora_realizacao"),
        } for r in records
    ]


def _processar_rede(
    records: list[dict],
    rede: str,
    base_dir: Path,
    *,
    arquivo_input: str = "logbook_pseudonimizados.json",
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    subset = _filtrar(records, rede)
    total = len(subset)
    current_hash = hash_subset(_stable_view(subset))

    out_dir = base_dir / "logbook" / rede
    out_path = out_dir / "resultados.json"

    if total == 0:
        return {"rede": rede, "status": "skip-empty", "total": 0}

    if not needs_processing(out_path, current_hash, force=force):
        return {"rede": rede, "status": "skip-cached", "total": total,
                "file_hash": current_hash}

    if dry_run:
        return {"rede": rede, "status": "would-run", "total": total,
                "file_hash": current_hash}

    print(f"  [{rede}] processando ({total} registros)...")
    out_dir.mkdir(parents=True, exist_ok=True)

    topicos = _analisar_topicos(subset)
    trajetoria = _analisar_trajetoria(subset)
    dificuldade = _analisar_dificuldade(subset)

    resultado = {
        "timestamp": datetime.now().isoformat(),
        "arquivo_input": arquivo_input,
        "rede_formadora": rede,
        "file_hash": current_hash,
        "total_registros": total,
        "analiseTopicos": topicos,
        "analiseTrajetoria": trajetoria,
        "analiseModelo": dificuldade,
    }
    out_path.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"rede": rede, "status": "processed", "total": total,
            "file_hash": current_hash, "output": str(out_path)}


def processar(
    records: list[dict],
    base_dir: Path,
    *,
    arquivo_input: str = "logbook_pseudonimizados.json",
    force: bool = False,
    dry_run: bool = False,
) -> list[dict]:
    """Roda análise pra cada rede encontrada nos records (dinâmico)."""
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    redes = _discover_redes(records)
    print(f"  [logbook] {len(redes)} redes encontradas: {', '.join(redes)}")
    resumos = []
    for rede in redes:
        r = _processar_rede(records, rede, base_dir,
                            arquivo_input=arquivo_input,
                            force=force, dry_run=dry_run)
        resumos.append(r)
        print(f"  [{r['rede']}] {r['status']} (n={r.get('total', 0)})")
    return resumos
