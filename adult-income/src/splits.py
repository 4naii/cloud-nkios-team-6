"""test 데이터를 '사용자 트래픽' 과 '평가용 holdout' 으로 고정 분할

- traffic : 배포된 서비스에 가상 사용자가 입력하는 프로필 (피드백 -> 재학습 데이터가 됨)
- holdout : 재학습에 절대 쓰지 않는 평가 전용. 재학습 전/후 비교는 여기서만 한다.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src.features import FEATURES, clean_target, load_raw

ROOT = Path(__file__).resolve().parents[1]


def test_split() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = load_raw(ROOT / "data/raw/adult-test.csv", is_test=True)
    raw["income"] = clean_target(raw["income"])
    traffic, holdout = train_test_split(raw, test_size=0.5, random_state=42, stratify=raw["income"])
    return traffic, holdout


def to_records(df: pd.DataFrame) -> list[dict]:
    """원본 행 -> API 입력 형식(dict). 결측치는 API 가 받는 값으로 채움"""
    df = df[FEATURES].copy()
    df[["workclass", "occupation"]] = df[["workclass", "occupation"]].fillna("Unknown")
    df["native_country"] = df["native_country"].fillna("Unknown")
    df[["capital_gain", "capital_loss"]] = df[["capital_gain", "capital_loss"]].astype(float)
    return [{k: (v.item() if isinstance(v, np.generic) else v) for k, v in r.items()}
            for r in df.to_dict("records")]
