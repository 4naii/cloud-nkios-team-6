"""학습 / API / 검증에서 공통으로 쓰는 전처리 로직 (한 곳에서만 관리)"""
import numpy as np
import pandas as pd

RAW_COLS = ["age", "workclass", "fnlwgt", "education", "education_num",
            "marital_status", "occupation", "relationship", "race", "sex",
            "capital_gain", "capital_loss", "hours_per_week", "native_country", "income"]

NUM_COLS = ["age", "education_num", "capital_gain", "capital_loss", "hours_per_week"]
CAT_COLS = ["workclass", "marital_status", "occupation", "relationship",
            "race", "sex", "native_country"]
FEATURES = NUM_COLS + CAT_COLS


def load_raw(path: str, is_test: bool = False) -> pd.DataFrame:
    """원본 CSV 읽기: 헤더 없음, ', ' 구분, 결측치 '?', test는 첫 줄이 쓰레기 행"""
    return pd.read_csv(path, header=None, names=RAW_COLS, skiprows=1 if is_test else 0,
                       skipinitialspace=True, na_values="?")


def clean_target(s: pd.Series) -> pd.Series:
    """test 레이블은 '>50K.' 처럼 마침표가 붙어 있음 -> 0/1"""
    return s.str.rstrip(".").map({"<=50K": 0, ">50K": 1})


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """원본 형태(사람이 입력하는 값)를 모델 입력 형태로 변환. income 컬럼은 무시."""
    df = df.copy()
    for c in ["workclass", "occupation", "native_country"]:
        df[c] = df[c].fillna("Unknown")
    df["native_country"] = np.where(df["native_country"].isin(["United-States", "Unknown"]),
                                    df["native_country"], "Other")
    df["capital_gain"] = np.log1p(df["capital_gain"].astype(float))
    df["capital_loss"] = np.log1p(df["capital_loss"].astype(float))
    return df[FEATURES]
