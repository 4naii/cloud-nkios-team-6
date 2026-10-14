"""모델 학습 -> models/model.joblib, models/metrics.json 저장

사용법: python -m src.train
"""
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, f1_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.features import CAT_COLS, NUM_COLS, clean_target, load_raw, transform

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"


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


def main():
    raw = load_raw(ROOT / "data/raw/adult-training.csv").drop_duplicates()
    X, y = transform(raw), clean_target(raw["income"])

    # 1) train 일부(20%)를 검증용으로 떼서 임계값 결정
    X_tr, X_val, y_tr, y_val = train_test_split(X, y, test_size=0.2, random_state=0, stratify=y)
    pipe = build_pipeline().fit(X_tr, y_tr)
    p_val = pipe.predict_proba(X_val)[:, 1]
    threshold = choose_threshold(y_val, p_val)

    # 2) 전체 train으로 다시 학습
    pipe = build_pipeline().fit(X, y)

    # 3) test로 최종 평가 (기본 0.5 vs 조정된 임계값)
    raw_te = load_raw(ROOT / "data/raw/adult-test.csv", is_test=True)
    X_te, y_te = transform(raw_te), clean_target(raw_te["income"])
    p_te = pipe.predict_proba(X_te)[:, 1]

    def report(t):
        pred = p_te >= t
        return {"threshold": t,
                "accuracy": round(accuracy_score(y_te, pred), 4),
                "f1": round(f1_score(y_te, pred), 4),
                "recall_over_50k": round(recall_score(y_te, pred), 4)}

    metrics = {"baseline_all_le50k": round(1 - y_te.mean(), 4),
               "default_0.5": report(0.5),
               "tuned": report(threshold)}

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump({"pipeline": pipe, "threshold": threshold}, MODEL_DIR / "model.joblib")
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
