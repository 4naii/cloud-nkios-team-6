"""모델 학습 -> models/model.joblib, models/metrics.json 저장

사용법:
  python -m src.train                 # data/feedback/feedback_labeled.csv 가 있으면 재학습에 포함
  python -m src.train --no-feedback   # 원본 train 데이터만으로 학습
"""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, f1_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.features import CAT_COLS, NUM_COLS, clean_target, load_raw, transform
from src.splits import test_split

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"
FEEDBACK_CSV = ROOT / "data/feedback/feedback_labeled.csv"


def build_pipeline() -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CAT_COLS),
        ("num", "passthrough", NUM_COLS),
    ])
    clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, random_state=0)
    return Pipeline([("pre", pre), ("clf", clf)])


def choose_threshold(y_true, proba) -> float:
    """검증 데이터에서 F1이 가장 높은 임계값 선택 (test 데이터는 절대 사용하지 않음)"""
    grid = np.round(np.arange(0.20, 0.61, 0.01), 2)
    scores = [f1_score(y_true, proba >= t) for t in grid]
    return float(grid[int(np.argmax(scores))])


def scores(y, proba, t) -> dict:
    pred = proba >= t
    return {"threshold": t,
            "accuracy": round(accuracy_score(y, pred), 4),
            "f1": round(f1_score(y, pred), 4),
            "recall_over_50k": round(recall_score(y, pred), 4)}


def fit(X, y):
    """train 일부(20%)로 임계값 결정 -> 전체로 다시 학습"""
    X_tr, X_val, y_tr, y_val = train_test_split(X, y, test_size=0.2, random_state=0, stratify=y)
    p_val = build_pipeline().fit(X_tr, y_tr).predict_proba(X_val)[:, 1]
    return build_pipeline().fit(X, y), choose_threshold(y_val, p_val)


def git_sha() -> str:
    if os.getenv("GIT_SHA"):
        return os.environ["GIT_SHA"]
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def main(use_feedback: bool = True):
    raw = load_raw(ROOT / "data/raw/adult-training.csv").drop_duplicates()
    X, y = transform(raw), clean_target(raw["income"])

    fb = pd.read_csv(FEEDBACK_CSV) if use_feedback and FEEDBACK_CSV.exists() else None
    if fb is not None and len(fb):
        X_all = pd.concat([X, transform(fb)], ignore_index=True)
        y_all = pd.concat([y, fb["income"].astype(int)], ignore_index=True)
    else:
        fb, X_all, y_all = None, X, y

    pipe, threshold = fit(X_all, y_all)

    # 기존 지표: test 전체 (scripts.validate 와 비교용)
    raw_te = load_raw(ROOT / "data/raw/adult-test.csv", is_test=True)
    X_te, y_te = transform(raw_te), clean_target(raw_te["income"])
    p_te = pipe.predict_proba(X_te)[:, 1]

    # 재학습 전/후 비교: 재학습에 쓰이지 않는 holdout 에서만
    _, holdout = test_split()
    X_ho, y_ho = transform(holdout), holdout["income"]
    holdout_scores = scores(y_ho, pipe.predict_proba(X_ho)[:, 1], threshold)

    metrics = {"baseline_all_le50k": round(1 - y_te.mean(), 4),
               "default_0.5": scores(y_te, p_te, 0.5),
               "tuned": scores(y_te, p_te, threshold),
               "holdout": holdout_scores}

    if fb is not None:
        base_pipe, base_t = fit(X, y)
        metrics["before_retrain_holdout"] = scores(y_ho, base_pipe.predict_proba(X_ho)[:, 1], base_t)

    info = {"trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_sha": git_sha(),
            "n_train_original": int(len(X)),
            "n_feedback": int(0 if fb is None else len(fb)),
            "n_holdout": int(len(holdout))}

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump({"pipeline": pipe, "threshold": threshold, "info": info}, MODEL_DIR / "model.joblib")
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"info": info, **metrics}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-feedback", action="store_true", help="피드백 데이터 없이 원본 train 만으로 학습")
    main(use_feedback=not ap.parse_args().no_feedback)
