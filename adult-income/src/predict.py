"""저장된 모델을 불러와 예측 (API와 검증 스크립트가 공통으로 사용)"""
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from src.features import transform

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "model.joblib"


@lru_cache(maxsize=1)
def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError("models/model.joblib 이 없습니다. 먼저 `python -m src.train` 을 실행하세요.")
    return joblib.load(MODEL_PATH)


def predict_df(df: pd.DataFrame) -> pd.DataFrame:
    """원본 형태 DataFrame -> probability, prediction 컬럼"""
    bundle = load_model()
    proba = bundle["pipeline"].predict_proba(transform(df))[:, 1]
    return pd.DataFrame({"probability": proba,
                         "prediction": (proba >= bundle["threshold"]).astype(int)},
                        index=df.index)


def predict_one(record: dict) -> dict:
    row = predict_df(pd.DataFrame([record])).iloc[0]
    pred = int(row["prediction"])
    return {"prediction": pred,
            "label": ">50K" if pred == 1 else "<=50K",
            "probability": round(float(row["probability"]), 4),
            "threshold": load_model()["threshold"]}
