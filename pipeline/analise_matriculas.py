"""Análise Claude de matrículas — refator de processo_analises.py.

Mudanças vs original:
  • Adiciona dimensão **ano de matrícula** (extraído de data_matricula).
    Resultado: 9 cortes (3 redes × 3 anos: Todos, 2025, 2026).
  • Cache por hash SHA-256 do subset — não chama Claude se o hash bate com o salvo.
  • Usa SDK oficial `anthropic` em vez de urllib.request.
  • Output em `analises/matriculas/{rede}/{ano}/resultados.json` + `nuvens_palavras/*.png`.
  • Padroniza `ANTHROPIC_API_KEY` como variável de ambiente.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

import anthropic
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from wordcloud import WordCloud  # noqa: E402

try:
    import nltk
    from nltk.corpus import stopwords
    try:
        STOP_WORDS = set(stopwords.words("portuguese"))
    except LookupError:
        nltk.download("stopwords", quiet=True)
        STOP_WORDS = set(stopwords.words("portuguese"))
except Exception:
    STOP_WORDS = {
        "a", "o", "e", "é", "de", "da", "do", "em", "um", "uma", "os", "as", "dos", "das",
        "para", "com", "por", "no", "na", "nos", "nas", "ao", "aos", "à", "às",
        "que", "se", "como", "mais", "mas", "ou", "também", "quando", "muito", "já",
    }

from pipeline.cache import hash_subset, needs_processing

# ----------------------------------------------------------------------
# CONFIGURAÇÃO
# ----------------------------------------------------------------------
MODEL_SENTIMENTO = os.environ.get("CLAUDE_MODEL_SENTIMENTO", "claude-sonnet-4-6")
MODEL_RESUMO = os.environ.get("CLAUDE_MODEL_RESUMO", "claude-sonnet-4-6")
BATCH_SIZE = 10
SENTIMENTO_MAX_TOKENS = 1024
RESUMO_MAX_TOKENS = 1500

CAMPOS = {
    "aptidoes_rotina": "Expectativas em relação ao PMM-e",
    "competencias_fortalecer": "Aptidão para atuação",
    "impressao_servico": "Impressão sobre o serviço",
    "momento_imersao": "Expectativas para imersão",
}

CONTEXTOS_RESUMO = {
    "aptidoes_rotina": "expectativas dos profissionais em relação ao PMM-e",
    "competencias_fortalecer": "autopercepção de aptidão para atuação",
    "impressao_servico": "impressões sobre o serviço de alocação",
    "momento_imersao": "expectativas para imersão presencial",
}

# Dimensões dinâmicas — descobertas em runtime a partir dos records.
# Listas hardcoded como fallback se o dado estiver vazio.
_REDES_FALLBACK = ["Todas"]
_EDITAIS_FALLBACK = ["Todos"]


def _discover_redes(records: list[dict]) -> list[str]:
    redes = {r.get("rede_formadora") for r in records if r.get("rede_formadora")}
    return ["Todas", *sorted(redes)] if redes else _REDES_FALLBACK


def _discover_editais(records: list[dict]) -> list[str]:
    eds = set()
    for r in records:
        e = r.get("edital")
        if e is not None:
            eds.add(int(e) if isinstance(e, (int, float)) and not isinstance(e, bool) else str(e))
    if not eds:
        return _EDITAIS_FALLBACK
    return ["Todos", *(str(e) for e in sorted(eds, key=lambda x: (not isinstance(x, int), x)))]


# ----------------------------------------------------------------------
# CLIENTE CLAUDE (lazy)
# ----------------------------------------------------------------------
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic | None:
    global _client
    if _client is not None:
        return _client
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    _client = anthropic.Anthropic(api_key=key)
    return _client


# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
def _filtrar(records: list[dict], rede: str, edital: str) -> list[dict]:
    """Filtra records pelo corte (rede, edital)."""
    out = records
    if rede and rede != "Todas":
        out = [r for r in out if r.get("rede_formadora") == rede]
    if edital and edital != "Todos":
        out = [r for r in out if str(r.get("edital")) == str(edital)]
    return out


def _flat_textual(records: list[dict]) -> list[dict]:
    """Extrai apenas campos textuais relevantes (para hash + análise)."""
    return [
        {
            "id": r.get("id"),
            "aptidoes_rotina": r.get("aptidoes_rotina"),
            "competencias_fortalecer": r.get("competencias_fortalecer"),
            "impressao_servico": r.get("impressao_servico"),
            "momento_imersao": r.get("momento_imersao"),
            "rede_formadora": r.get("rede_formadora"),
            "edital": r.get("edital"),
        }
        for r in records
    ]


def _clean_text(text: str) -> str:
    """Limpa texto pra geração de nuvem."""
    s = str(text).lower()
    s = re.sub(r"http\S+|www\S+|https\S+", "", s)
    s = re.sub(r"\S+@\S+", "", s)
    s = re.sub(r"\d+", "", s)
    s = re.sub(r"[^\w\s-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _processar_para_nuvem(textos: Iterable[str]) -> str:
    todos = " ".join(_clean_text(t) for t in textos if t)
    palavras = [
        p for p in todos.split()
        if len(p) >= 3 and p not in STOP_WORDS and any(c.isalnum() for c in p)
    ]
    return " ".join(palavras)


def _criar_nuvem(textos: list[str], destino: Path) -> str | None:
    """Gera e salva PNG. Retorna caminho relativo a destino.parent."""
    txt = _processar_para_nuvem(textos)
    if not txt.strip():
        return None
    wc = WordCloud(
        width=1000, height=500, background_color="white",
        colormap="viridis", max_words=100, collocations=False,
        relative_scaling=0.5, min_font_size=10, prefer_horizontal=0.7,
        stopwords=STOP_WORDS,
    ).generate(txt)

    destino.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(12, 6))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.tight_layout(pad=0)
    plt.savefig(destino, format="png", bbox_inches="tight", dpi=100)
    plt.close()
    return f"nuvens_palavras/{destino.name}"


# ----------------------------------------------------------------------
# ANÁLISES CLAUDE
# ----------------------------------------------------------------------
def _sentimento_fallback(textos: list[str]) -> list[str]:
    """Análise simplificada sem Claude — usado em modo offline ou erro."""
    positivas = {"excelente", "ótimo", "bom", "boa", "qualidade", "oportunidade",
                 "crescimento", "aprimoramento", "comprometido", "valiosa",
                 "positiva", "satisfação", "entusiasmo", "aperfeiçoamento",
                 "melhor", "melhoria", "fortalecer", "contribuir", "expectativa",
                 "espero", "desejo", "apta", "apto", "competente", "capacitado"}
    negativas = {"dificuldade", "limitação", "problema", "carência",
                 "atraso", "baixa", "ausência", "desafio", "frustração",
                 "preocupação", "crítica", "não", "falta", "limitado",
                 "difícil", "ruim", "péssimo", "inadequado"}
    out = []
    for t in textos:
        if not t or not str(t).strip():
            out.append("Neutro")
            continue
        s = str(t).lower()
        p = sum(1 for w in positivas if w in s)
        n = sum(1 for w in negativas if w in s)
        if p > n + 1:
            out.append("Positivo")
        elif n > p + 1:
            out.append("Negativo")
        else:
            out.append("Neutro")
    return out


def _sentimento_claude(textos: list[str]) -> list[str]:
    """Análise de sentimentos via Claude, em lotes."""
    client = _get_client()
    if client is None:
        return _sentimento_fallback(textos)

    resultados: list[str] = []
    for i in range(0, len(textos), BATCH_SIZE):
        batch = textos[i:i + BATCH_SIZE]
        numerados = [f"[{j}] {str(t)[:300]}" for j, t in enumerate(batch)]
        prompt = (
            "Analise o sentimento de cada texto e classifique como: "
            "Positivo, Negativo ou Neutro.\n\n"
            f"Textos:\n{chr(10).join(numerados)}\n\n"
            'Responda APENAS em JSON: {"sentimentos": ["Positivo", "Negativo", "Neutro", ...]}'
        )
        try:
            msg = client.messages.create(
                model=MODEL_SENTIMENTO,
                max_tokens=SENTIMENTO_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            resposta = msg.content[0].text
            m = re.search(r"\{.*\}", resposta, re.DOTALL)
            if m:
                resultados.extend(json.loads(m.group()).get("sentimentos", []))
            else:
                resultados.extend(_sentimento_fallback(batch))
        except Exception as e:
            print(f"      [erro Claude sentimentos]: {e}")
            resultados.extend(_sentimento_fallback(batch))
    return resultados


def _resumo_fallback(textos: list[str], campo: str) -> str:
    palavras = " ".join(textos).lower().split()
    freq = Counter(p for p in palavras if len(p) > 5).most_common(5)
    chaves = ", ".join(p for p, _ in freq)
    return f"Análise resumida de {len(textos)} textos. Palavras-chave: {chaves}."


def _resumo_claude(textos: list[str], campo: str, rede: str, edital: str) -> str:
    client = _get_client()
    if client is None:
        return _resumo_fallback(textos, campo)

    amostra = [str(t)[:300] for t in textos[:20]]
    contexto = CONTEXTOS_RESUMO.get(campo, "respostas dos profissionais")
    rede_info = f" da rede {rede}" if rede != "Todas" else ""
    edital_info = f", edital {edital}" if edital != "Todos" else ""

    prompt = (
        f"Analise os textos sobre {contexto} de médicos do PMM-e{rede_info}{edital_info}.\n\n"
        f"Textos:\n{chr(10).join('- ' + t for t in amostra)}\n\n"
        "Crie um resumo executivo em 2-3 parágrafos com:\n"
        "1. Principais temas e expectativas\n"
        "2. Padrões identificados\n"
        "3. Aspectos positivos e desafios"
    )
    try:
        msg = client.messages.create(
            model=MODEL_RESUMO,
            max_tokens=RESUMO_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        print(f"      [erro Claude resumo]: {e}")
        return _resumo_fallback(textos, campo)


# ----------------------------------------------------------------------
# PIPELINE POR CORTE
# ----------------------------------------------------------------------
def _processar_corte(
    records: list[dict],
    rede: str,
    edital: str,
    base_dir: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Roda análise para um único corte (rede, edital). Retorna status dict."""
    subset = _filtrar(records, rede, edital)
    subset_textual = _flat_textual(subset)
    current_hash = hash_subset(subset_textual)
    total = len(subset)

    out_dir = base_dir / "matriculas" / rede / edital
    out_path = out_dir / "resultados.json"
    nuvens_dir = out_dir / "nuvens_palavras"

    if total == 0:
        return {"rede": rede, "edital": edital, "status": "skip-empty", "total": 0}

    if not needs_processing(out_path, current_hash, force=force):
        return {
            "rede": rede, "edital": edital, "status": "skip-cached",
            "total": total, "file_hash": current_hash,
        }

    if dry_run:
        return {
            "rede": rede, "edital": edital, "status": "would-run",
            "total": total, "file_hash": current_hash,
        }

    print(f"  [{rede}/edital={edital}] processando ({total} registros)...")
    out_dir.mkdir(parents=True, exist_ok=True)

    resultados: dict = {
        "data_processamento": datetime.now().isoformat(),
        "rede_formadora": rede,
        "edital": edital,
        "file_hash": current_hash,
        "total_registros": total,
        "usando_claude_api": _get_client() is not None,
        "campos": {},
    }

    for campo, descricao in CAMPOS.items():
        textos = [r.get(campo) for r in subset if r.get(campo)]
        textos = [str(t) for t in textos if str(t).strip()]
        if not textos:
            continue
        print(f"    • {descricao}: {len(textos)} textos")

        nuvem_path = nuvens_dir / f"{campo}.png"
        nuvem_rel = _criar_nuvem(textos, nuvem_path)
        sentimentos = _sentimento_claude(textos)
        distribuicao = dict(Counter(sentimentos))
        resumo = _resumo_claude(textos, campo, rede, edital)

        resultados["campos"][campo] = {
            "descricao": descricao,
            "total_textos": len(textos),
            "nuvem_palavras": nuvem_rel,
            "sentimentos": {"lista": sentimentos, "distribuicao": distribuicao},
            "resumo": resumo,
        }

    out_path.write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "rede": rede, "edital": edital, "status": "processed",
        "total": total, "file_hash": current_hash, "output": str(out_path),
    }


# ----------------------------------------------------------------------
# ENTRYPOINT
# ----------------------------------------------------------------------
def processar(
    records: list[dict],
    base_dir: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> list[dict]:
    """Roda análise para todos os cortes (rede × edital) — dinâmicos a partir dos records."""
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    redes = _discover_redes(records)
    editais = _discover_editais(records)
    print(f"  [matriculas] {len(redes)} redes × {len(editais)} editais = "
          f"{len(redes) * len(editais)} cortes")

    resumos = []
    for rede in redes:
        for edital in editais:
            r = _processar_corte(records, rede, edital, base_dir,
                                 force=force, dry_run=dry_run)
            resumos.append(r)
            print(f"  [{r['rede']}/edital={r['edital']}] {r['status']} "
                  f"(n={r.get('total', 0)})")
    return resumos
