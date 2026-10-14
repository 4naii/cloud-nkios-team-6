"""Adult Income 데이터 전처리 (train/test 공통)"""
import sys
import numpy as np
import pandas as pd

TRAIN = sys.argv[1] if len(sys.argv) > 1 else "data/raw/adult-training.csv"
TEST = sys.argv[2] if len(sys.argv) > 2 else "data/raw/adult-test.csv"

COLS = ["age", "workclass", "fnlwgt", "education", "education_num",
        "marital_status", "occupation", "relationship", "race", "sex",
        "capital_gain", "capital_loss", "hours_per_week", "native_country", "income"]

def load(path, skip):
    # 원본은 헤더가 없고, ", " 구분자, 결측치는 "?"
    return pd.read_csv(path, header=None, names=COLS, skiprows=skip,
                       skipinitialspace=True, na_values="?")

train = load(TRAIN, 0).drop_duplicates()   # 원본 기준 완전 중복 행(24개) 제거
test = load(TEST, 1)          # test 첫 줄은 "|1x3 Cross validator" 쓰레기 행

def clean(df):
    df = df.copy()
    # 1) 타깃: test는 ">50K." 처럼 마침표가 붙어 있음 -> 제거 후 0/1
    df["income"] = df["income"].str.rstrip(".").map({"<=50K": 0, ">50K": 1})
    # 2) 결측치("?") -> 'Unknown' 범주로 유지 (행 삭제 X)
    for c in ["workclass", "occupation", "native_country"]:
        df[c] = df[c].fillna("Unknown")
    # 3) 국가: 대부분 미국(약 90%), 나머지는 희귀 범주 -> 미국 / 기타 / Unknown
    df["native_country"] = np.where(df["native_country"].isin(["United-States", "Unknown"]),
                                    df["native_country"], "Other")
    # 4) 자본 이득/손실: 대부분 0이고 극단적으로 치우침 -> log1p
    df["capital_gain"] = np.log1p(df["capital_gain"])
    df["capital_loss"] = np.log1p(df["capital_loss"])
    # 5) 불필요/중복 컬럼 제거
    df = df.drop(columns=["fnlwgt", "education"])
    return df

train = clean(train)
test = clean(test)

# 6) 원-핫 인코딩 (test는 train 컬럼에 맞춰 정렬)
cat_cols = ["workclass", "marital_status", "occupation", "relationship",
            "race", "sex", "native_country"]
X_train = pd.get_dummies(train.drop(columns="income"), columns=cat_cols, dtype=int)
X_test = pd.get_dummies(test.drop(columns="income"), columns=cat_cols, dtype=int)
X_test = X_test.reindex(columns=X_train.columns, fill_value=0)
y_train, y_test = train["income"], test["income"]

pd.concat([X_train, y_train], axis=1).to_csv("data/processed/adult_train_clean.csv", index=False)
pd.concat([X_test, y_test], axis=1).to_csv("data/processed/adult_test_clean.csv", index=False)
print("train", X_train.shape, "test", X_test.shape, "| >50K 비율:", round(y_train.mean(), 3))

# 확인용 모델
if __name__ == "__main__":
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import accuracy_score
    m = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, random_state=0)
    m.fit(X_train, y_train)
    print("기준선(전부 <=50K):", round(1 - y_test.mean(), 4))
    print("Test 정확도:", round(accuracy_score(y_test, m.predict(X_test)), 4))
