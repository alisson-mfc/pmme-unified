"""Modelo ML do logbook — refator de modelo_ml_dificuldade.py.

Treina Random Forest + Gradient Boosting por rede, escolhe o melhor, e gera
predições de dificuldade por CID e por procedimento. Saída: dict com chaves
'Todas', 'EBSERH', 'PROADI-SUS' compatível com `predicoes_ml_dificuldade.json`.

Cache: hash do subset (CID+procedimento+dificuldade+nivel_desenvolvimento) por rede.
"""

from __future__ import annotations

import json
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from pipeline.cache import hash_subset

warnings.filterwarnings("ignore")


def _discover_redes(records: list[dict]) -> list[str]:
    """Redes presentes no JSON. Sempre tem 'Todas' (treina com tudo) + cada rede individual."""
    redes = {r.get("rede_formadora") for r in records if r.get("rede_formadora")}
    return ["Todas", *sorted(redes)] if redes else ["Todas"]


# ----------------------------------------------------------------------
def _preparar_df(records: list[dict], rede_filtro: str | None) -> pd.DataFrame:
    rows = []
    for r in records:
        if not (r.get("no_cid") and r.get("dificuldade") and r.get("nivel_desenvolvimento")):
            continue
        rede = r.get("rede_formadora", "Desconhecida")
        if rede_filtro and rede != rede_filtro:
            continue
        rows.append({
            "cid": r["no_cid"],
            "procedimento": r.get("no_procedimento", "N/A"),
            "dificuldade": int(r["dificuldade"]),
            "nivel_desenvolvimento": float(r["nivel_desenvolvimento"]),
            "rede": rede,
        })
    return pd.DataFrame(rows)


def _treinar_e_avaliar(df: pd.DataFrame) -> tuple[dict, str]:
    le_cid = LabelEncoder()
    le_proc = LabelEncoder()
    le_rede = LabelEncoder()

    X = df.copy()
    X["cid_encoded"] = le_cid.fit_transform(X["cid"])
    X["proc_encoded"] = le_proc.fit_transform(X["procedimento"])
    X["rede_encoded"] = le_rede.fit_transform(X["rede"])

    features = ["cid_encoded", "proc_encoded", "nivel_desenvolvimento", "rede_encoded"]
    X_feat = X[features]
    y = X["dificuldade"]
    X_tr, X_te, y_tr, y_te = train_test_split(X_feat, y, test_size=0.2, random_state=42)

    rf = RandomForestClassifier(
        n_estimators=100, max_depth=10, random_state=42,
        n_jobs=-1, class_weight="balanced",
    )
    rf.fit(X_tr, y_tr)
    rf_score = rf.score(X_te, y_te)

    gb = GradientBoostingClassifier(
        n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42,
    )
    gb.fit(X_tr, y_tr)
    gb_score = gb.score(X_te, y_te)

    melhor = "random_forest" if rf_score >= gb_score else "gradient_boosting"
    modelo = rf if melhor == "random_forest" else gb
    acuracia = rf_score if melhor == "random_forest" else gb_score

    return {
        "modelo": modelo,
        "acuracia": acuracia,
        "features": features,
        "encoders": {"cid": le_cid, "proc": le_proc, "rede": le_rede},
        "X_full": X,
    }, melhor


def _predicoes_por_grupo(
    modelo_info: dict,
    df: pd.DataFrame,
    coluna_grupo: str,
    min_registros: int = 5,
) -> dict:
    modelo = modelo_info["modelo"]
    enc = modelo_info["encoders"]
    le_cid, le_proc, le_rede = enc["cid"], enc["proc"], enc["rede"]

    out = {}
    grupos = df[coluna_grupo].unique()
    if coluna_grupo == "procedimento":
        grupos = [g for g in grupos if g != "N/A"]

    for g in grupos:
        subset = df[df[coluna_grupo] == g]
        if len(subset) < min_registros:
            continue

        try:
            cid_enc = le_cid.transform([subset["cid"].iloc[0]])[0]
            proc_enc = le_proc.transform([subset["procedimento"].iloc[0]])[0]
            rede_enc = le_rede.transform([subset["rede"].iloc[0]])[0]
            nivel_medio = subset["nivel_desenvolvimento"].mean()

            X_pred = np.array([[cid_enc, proc_enc, nivel_medio, rede_enc]])
            pred = modelo.predict(X_pred)[0]
            prob = modelo.predict_proba(X_pred)[0]

            out[g] = {
                "dificuldade_predita": int(pred),
                "confianca": float(max(prob)),
                "distribuicao_probabilidade": {
                    str(i + 1): float(p) for i, p in enumerate(prob)
                },
                "registros": int(len(subset)),
                "dificuldade_media_historica": float(subset["dificuldade"].mean()),
                "desvio_historico": float(subset["dificuldade"].std()),
            }
        except Exception:
            continue
    return out


# ----------------------------------------------------------------------
def processar(
    records: list[dict],
    output_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Treina ML por rede e grava `predicoes_ml_dificuldade.json`.

    Cache: hash do subset usado pra treinar; comparado com hash gravado em
    `<output_path>.meta.json` na execução anterior.
    """
    output_path = Path(output_path)
    meta_path = output_path.with_suffix(".meta.json")

    # Hash do dataset filtrado (campos relevantes apenas)
    relevant = [
        {
            "id_profissional": r.get("id_profissional"),
            "no_cid": r.get("no_cid"),
            "no_procedimento": r.get("no_procedimento"),
            "dificuldade": r.get("dificuldade"),
            "nivel_desenvolvimento": r.get("nivel_desenvolvimento"),
            "rede_formadora": r.get("rede_formadora"),
        } for r in records
    ]
    current_hash = hash_subset(relevant)

    # Cache check
    if not force and output_path.exists() and meta_path.exists():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if existing_meta.get("file_hash") == current_hash:
                return {"status": "skip-cached", "file_hash": current_hash}
        except Exception:
            pass

    if dry_run:
        return {"status": "would-run", "file_hash": current_hash,
                "total_registros": len(relevant)}

    resultados_por_rede: dict = {}
    redes_alvo = _discover_redes(records)
    print(f"  [ml_logbook] redes encontradas: {', '.join(redes_alvo)}")
    for rede_filtro in redes_alvo:
        rede_param = None if rede_filtro == "Todas" else rede_filtro
        df = _preparar_df(records, rede_param)
        if len(df) < 10:
            print(f"  [{rede_filtro}] skip — poucos registros ({len(df)})")
            continue

        print(f"  [{rede_filtro}] treinando ({len(df)} registros)...")
        modelo_info, modelo_nome = _treinar_e_avaliar(df)
        importancia = dict(
            zip(modelo_info["features"],
                modelo_info["modelo"].feature_importances_.tolist())
        )
        pred_cid = _predicoes_por_grupo(modelo_info, modelo_info["X_full"], "cid")
        pred_proc = _predicoes_por_grupo(modelo_info, modelo_info["X_full"], "procedimento")

        resultados_por_rede[rede_filtro] = {
            "modelo_usado": modelo_nome,
            "acuracia": float(modelo_info["acuracia"]),
            "importancia_features": importancia,
            "total_registros_treino": int(len(df)),
            "cids": pred_cid,
            "procedimentos": pred_proc,
        }
        print(f"  [{rede_filtro}] {modelo_nome} acurácia={modelo_info['acuracia']:.2%} "
              f"(CIDs={len(pred_cid)}, Procs={len(pred_proc)})")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(resultados_por_rede, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    meta_path.write_text(
        json.dumps({
            "data_atualizacao": datetime.now().isoformat(),
            "file_hash": current_hash,
            "total_registros": len(relevant),
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "status": "processed",
        "file_hash": current_hash,
        "redes": list(resultados_por_rede.keys()),
        "output": str(output_path),
    }
