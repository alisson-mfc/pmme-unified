"""Orquestrador do pipeline PMM-e.

Fluxo padrão:
  1. Lê JSONs brutos em `dados/raw/` (matriculas_bruto.json, logbook_bruto.json)
  2. Anonimiza → `dados/processado/` + `.meta.json` (file_hash + data_atualizacao)
  3. Análise Claude (matrículas: 9 cortes, logbook: 3 redes) com cache por hash
  4. Treina ML do logbook
  5. (opcional --push) Sincroniza tudo para `../pmme-dados/` e faz `git commit + push`

Comandos típicos:
  python -m pipeline.run                # processa só o que mudou
  python -m pipeline.run --force        # ignora cache, refaz análise Claude
  python -m pipeline.run --dry-run      # NÃO chama Claude — só mostra o que faria
  python -m pipeline.run --push         # ao final, commita e push pra pmme-dados
  python -m pipeline.run --only matriculas
  python -m pipeline.run --no-anonymize # pula passo 1-2 (assume processado/ pronto)
  python -m pipeline.run --no-analyze   # pula passo 3-4

Env vars:
  ANTHROPIC_API_KEY    necessário pra análise Claude (se ausente: usa fallback)
  GITHUB_TOKEN         opcional, usado pra autenticar push se git não tiver creds
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Permite rodar via `python pipeline/run.py` E `python -m pipeline.run`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Força UTF-8 no stdout do Windows (PowerShell usa cp1252 por padrão)
if sys.platform == "win32":
    import io
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from pipeline import (  # noqa: E402
    analise_logbook,
    analise_matriculas,
    anonimizar_logbook,
    anonimizar_matriculas,
    cache,
    ml_logbook,
)


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
HERE = Path(__file__).resolve().parent.parent  # pmme-unified/
RAW_DIR = HERE / "dados" / "raw"
PROC_DIR = HERE / "dados" / "processado"
ANALISES_DIR = HERE / "analises"
PMME_DADOS = HERE.parent / "pmme-dados"

RAW_MAT = RAW_DIR / "matriculas_bruto.json"
RAW_LOG = RAW_DIR / "logbook_bruto.json"
PROC_MAT = PROC_DIR / "dados_anonimizados.json"
PROC_LOG = PROC_DIR / "logbook_pseudonimizados.json"
PROC_ML = PROC_DIR / "predicoes_ml_dificuldade.json"


# ----------------------------------------------------------------------
# Logging colorido (simples)
# ----------------------------------------------------------------------
def log(msg: str, *, level: str = "info") -> None:
    prefixes = {"info": "•", "ok": "✓", "skip": "⤵", "warn": "!", "step": ""}
    sys.stdout.write(f"{prefixes.get(level, '')} {msg}\n")
    sys.stdout.flush()


def section(title: str) -> None:
    sys.stdout.write(f"\n— {title}\n")
    sys.stdout.flush()


# ----------------------------------------------------------------------
# 1-2. ANONIMIZAÇÃO
# ----------------------------------------------------------------------
def _write_dataset(out_path: Path, data: dict | list, *, write_mapping_csv: bool = False,
                   mapping_stats: dict | None = None) -> str:
    """Grava o JSON anonimizado + meta sidecar com hash. Retorna o hash."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    records = data.get("RECORDS") if isinstance(data, dict) else data
    if not isinstance(records, list):
        records = []
    h = cache.hash_subset(records)
    cache.write_meta_sidecar(out_path, file_hash=h, total_registros=len(records))

    if write_mapping_csv and mapping_stats:
        csv_path = out_path.parent / f"{out_path.stem}_mapeamento.csv"
        csv_path.write_text(
            anonimizar_logbook.mapping_to_csv(mapping_stats),
            encoding="utf-8",
        )
    return h


def step_anonymize(only: str | None = None) -> dict:
    section("ANONIMIZAÇÃO")
    results: dict = {}

    if only != "logbook":
        if not RAW_MAT.exists():
            log(f"matriculas: {RAW_MAT.relative_to(HERE)} não existe, pulando", level="skip")
        else:
            log(f"matriculas: lendo {RAW_MAT.relative_to(HERE)}")
            raw = json.loads(RAW_MAT.read_text(encoding="utf-8"))
            out, stats = anonimizar_matriculas.anonymize(raw)
            h = _write_dataset(PROC_MAT, out)
            results["matriculas"] = {
                "registros": stats["registros_processados"],
                "campos_alterados": stats["campos_alterados"],
                "hash": h,
                "output": str(PROC_MAT.relative_to(HERE)),
            }
            log(f"matriculas: {stats['registros_processados']} registros, "
                f"{stats['campos_alterados']} campos alterados → {PROC_MAT.relative_to(HERE)}",
                level="ok")

    if only != "matriculas":
        if not RAW_LOG.exists():
            log(f"logbook: {RAW_LOG.relative_to(HERE)} não existe, pulando", level="skip")
        else:
            log(f"logbook: lendo {RAW_LOG.relative_to(HERE)}")
            raw = json.loads(RAW_LOG.read_text(encoding="utf-8"))
            out, stats = anonimizar_logbook.anonymize(raw)
            h = _write_dataset(PROC_LOG, out,
                                write_mapping_csv=True, mapping_stats=stats)
            results["logbook"] = {
                "registros_originais": stats["registros_originais"],
                "registros_processados": stats["registros_processados"],
                "filtrados_por_data": stats["registros_removidos"],
                "cpfs_unicos": len(stats["cpf_map"]),
                "hash": h,
                "output": str(PROC_LOG.relative_to(HERE)),
            }
            log(f"logbook: {stats['registros_processados']} registros "
                f"(filtrados por data ≤08/2025: {stats['registros_removidos']}, "
                f"CPFs únicos: {len(stats['cpf_map'])}) "
                f"→ {PROC_LOG.relative_to(HERE)}", level="ok")

    return results


# ----------------------------------------------------------------------
# 3-4. ANÁLISE
# ----------------------------------------------------------------------
def _load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "RECORDS" in data:
        return data["RECORDS"]
    return data if isinstance(data, list) else []


def step_analyze(*, force: bool = False, dry_run: bool = False, only: str | None = None) -> dict:
    section("ANÁLISE")
    results: dict = {}

    if only != "logbook":
        records = _load_records(PROC_MAT)
        if not records:
            log("matriculas: dados/processado/ vazio, pulando análise", level="skip")
        else:
            log(f"matriculas: analisando {len(records)} registros (Claude, 9 cortes)")
            results["matriculas_claude"] = analise_matriculas.processar(
                records, ANALISES_DIR, force=force, dry_run=dry_run,
            )

    if only != "matriculas":
        records = _load_records(PROC_LOG)
        if not records:
            log("logbook: dados/processado/ vazio, pulando análise", level="skip")
        else:
            log(f"logbook: analisando {len(records)} registros (Claude, 3 redes)")
            results["logbook_claude"] = analise_logbook.processar(
                records, ANALISES_DIR, force=force, dry_run=dry_run,
            )

            log(f"logbook: treinando ML (Random Forest + Gradient Boosting)")
            results["logbook_ml"] = ml_logbook.processar(
                records, PROC_ML, force=force, dry_run=dry_run,
            )

    return results


# ----------------------------------------------------------------------
# 5. PUSH PRA pmme-dados
# ----------------------------------------------------------------------
def _git(*args: str, cwd: Path, check: bool = True) -> tuple[int, str, str]:
    """Roda git e retorna (returncode, stdout, stderr)."""
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} falhou:\n{proc.stderr}")
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def step_push(message: str | None = None) -> dict:
    section("PUSH PRA pmme-dados")

    if not PMME_DADOS.exists():
        log(f"{PMME_DADOS} não existe — clone o repo como sibling primeiro", level="warn")
        return {"status": "skip-no-repo"}

    if not (PMME_DADOS / ".git").exists():
        log(f"{PMME_DADOS} não é um git repo", level="warn")
        return {"status": "skip-not-git"}

    # Sanity check: working tree limpo antes de começarmos a sobrescrever
    _, status, _ = _git("status", "--porcelain", cwd=PMME_DADOS)
    if status:
        log("pmme-dados tem alterações não commitadas — abortando push para evitar perda",
            level="warn")
        log(f"Status:\n{status}", level="warn")
        return {"status": "abort-dirty"}

    # Pull pra evitar non-fast-forward
    log("fetch + pull no pmme-dados (rebase)")
    _git("fetch", "--quiet", cwd=PMME_DADOS)
    rc, _, err = _git("pull", "--rebase", "--quiet", cwd=PMME_DADOS, check=False)
    if rc != 0:
        log(f"pull com rebase falhou: {err}", level="warn")
        return {"status": "abort-pull-failed"}

    # Copiar arquivos
    files = [
        (PROC_MAT, PMME_DADOS / "dados_anonimizados.json"),
        (PROC_MAT.with_suffix(".meta.json"),
         PMME_DADOS / "dados_anonimizados.meta.json"),
        (PROC_LOG, PMME_DADOS / "logbook_pseudonimizados.json"),
        (PROC_LOG.with_suffix(".meta.json"),
         PMME_DADOS / "logbook_pseudonimizados.meta.json"),
        (PROC_ML, PMME_DADOS / "predicoes_ml_dificuldade.json"),
        (PROC_ML.with_suffix(".meta.json"),
         PMME_DADOS / "predicoes_ml_dificuldade.meta.json"),
    ]
    for src, dst in files:
        if src.exists():
            shutil.copy2(src, dst)
            log(f"copy {src.name} → pmme-dados/{dst.name}")

    # Sincronizar pasta analises/ (nova estrutura)
    if ANALISES_DIR.exists() and any(ANALISES_DIR.iterdir()):
        dst_analises = PMME_DADOS / "analises"
        if dst_analises.exists():
            shutil.rmtree(dst_analises)
        shutil.copytree(ANALISES_DIR, dst_analises,
                        ignore=shutil.ignore_patterns(".gitkeep"))
        log("copy analises/ → pmme-dados/analises/")

    # Status de novo, agora deve mostrar mudanças
    _, status_after, _ = _git("status", "--porcelain", cwd=PMME_DADOS)
    if not status_after:
        log("nada mudou — commit pulado", level="skip")
        return {"status": "noop"}

    log(f"alterações detectadas:\n{status_after}")

    # Commit
    _git("add", "-A", cwd=PMME_DADOS)
    if message is None:
        message = f"Atualizar dados — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    log(f"commit: {message}")
    _git("commit", "-m", message, cwd=PMME_DADOS)

    # Push
    log("push origin main")
    rc, _, err = _git("push", "origin", "main", cwd=PMME_DADOS, check=False)
    if rc != 0:
        log(f"push falhou: {err}", level="warn")
        log("dica: verifique se GITHUB_TOKEN está configurado ou rode `git push` manualmente",
            level="warn")
        return {"status": "push-failed"}

    log("push concluído", level="ok")
    return {"status": "pushed", "message": message}


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pipeline PMM-e: anonimiza → analisa → (opcional) push",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--force", action="store_true",
                        help="ignora cache, refaz análise Claude/ML")
    parser.add_argument("--dry-run", action="store_true",
                        help="NÃO chama Claude — só mostra o que faria")
    parser.add_argument("--push", action="store_true",
                        help="commita e push pra ../pmme-dados/ ao final")
    parser.add_argument("--only", choices=["matriculas", "logbook"],
                        help="processa apenas um dataset")
    parser.add_argument("--no-anonymize", action="store_true",
                        help="pula anonimização (usa dados/processado/ existente)")
    parser.add_argument("--no-analyze", action="store_true",
                        help="pula análise Claude/ML")
    parser.add_argument("--message", "-m",
                        help="mensagem do commit (padrão: data/hora)")
    args = parser.parse_args()

    sys.stdout.write("\n" + "=" * 70 + "\n")
    sys.stdout.write(" PMM-e PIPELINE\n")
    sys.stdout.write("=" * 70 + "\n")
    if args.dry_run:
        log("modo dry-run — nenhuma chamada Claude será feita", level="info")
    if args.force:
        log("modo force — cache será ignorado", level="info")

    summary: dict = {}

    if not args.no_anonymize:
        summary["anonymize"] = step_anonymize(only=args.only)

    if not args.no_analyze:
        summary["analyze"] = step_analyze(
            force=args.force, dry_run=args.dry_run, only=args.only,
        )

    if args.push:
        if args.dry_run:
            log("--push ignorado em dry-run", level="warn")
        else:
            summary["push"] = step_push(message=args.message)

    sys.stdout.write("\n" + "=" * 70 + "\n")
    sys.stdout.write(" RESUMO\n")
    sys.stdout.write("=" * 70 + "\n")
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2,
                                 default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
