"""4단계: 검증용(test) 데이터로 모델이 예상대로 동작하는지 확인

사용법:
  python -m scripts.validate                 # 모델 직접 호출로 검증
  python -m scripts.validate --api http://127.0.0.1:8000   # 실행 중인 API도 함께 검증
"""
import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score

from src.features import clean_target, load_raw
from src.predict import load_model, predict_df, predict_one

ROOT = Path(__file__).resolve().parents[1]
TARGET_ACC = 0.85

CASES = [  # (설명, 입력, 기대 결과)
    ("고학력·관리직·기혼 남성·자본이득", dict(age=45, workclass="Private", education_num=14,
     marital_status="Married-civ-spouse", occupation="Exec-managerial", relationship="Husband",
     race="White", sex="Male", capital_gain=15024, capital_loss=0, hours_per_week=50,
     native_country="United-States"), 1),
    ("22세·고졸·미혼·서비스직·파트타임", dict(age=22, workclass="Private", education_num=9,
     marital_status="Never-married", occupation="Other-service", relationship="Own-child",
     race="White", sex="Female", capital_gain=0, capital_loss=0, hours_per_week=25,
     native_country="United-States"), 0),
    ("결측값(Unknown)·미국 외 국가 입력도 처리", dict(age=30, workclass="Unknown", education_num=10,
     marital_status="Never-married", occupation="Unknown", relationship="Not-in-family",
     race="Black", sex="Male", capital_gain=0, capital_loss=0, hours_per_week=40,
     native_country="Mexico"), 0),
]


def main(api_url=None):
    ok = True
    raw = load_raw(ROOT / "data/raw/adult-test.csv", is_test=True)
    y = clean_target(raw["income"])
    out = predict_df(raw)
    pred = out["prediction"]

    acc = accuracy_score(y, pred)
    print(f"[1] Test 정확도 {acc:.4f} (목표 {TARGET_ACC}) -> {'PASS' if acc >= TARGET_ACC else 'FAIL'}")
    ok &= acc >= TARGET_ACC
    print(f"    F1 {f1_score(y, pred):.4f} | >50K 재현율 {recall_score(y, pred):.4f} | 임계값 {load_model()['threshold']}")
    tn, fp, fn, tp = confusion_matrix(y, pred).ravel()
    print(f"    혼동행렬: 맞힌 <=50K {tn} | 틀린 >50K예측 {fp} | 놓친 >50K {fn} | 맞힌 >50K {tp}")

    saved = json.loads((ROOT / "models/metrics.json").read_text(encoding="utf-8"))["tuned"]["accuracy"]
    same = abs(saved - round(acc, 4)) < 1e-4
    print(f"[2] 학습 시 기록한 정확도({saved})와 일치 -> {'PASS' if same else 'FAIL'}")
    ok &= same

    p = out["probability"]
    print(f"[3] 확률 범위 0~1: {p.min():.4f} ~ {p.max():.4f} -> {'PASS' if p.between(0, 1).all() else 'FAIL'}")
    ok &= bool(p.between(0, 1).all())

    print("[4] 대표 사례")
    for name, rec, expected in CASES:
        r = predict_one(rec)
        hit = r["prediction"] == expected
        ok &= hit
        print(f"    {'PASS' if hit else 'FAIL'}  {name}: {r['label']} (확률 {r['probability']})")

    if api_url:
        import requests
        print(f"[5] API 응답이 모델 직접 호출과 같은지 ({api_url})")
        sample = raw.sample(20, random_state=0)
        same_cnt = 0
        for idx, row in sample.iterrows():
            rec = row.drop(["income", "fnlwgt", "education"]).to_dict()
            rec = {k: (v if not (isinstance(v, float) and np.isnan(v)) else
                       ("Unknown" if k in ("workclass", "occupation") else "United-States"))
                   for k, v in rec.items()}
            res = requests.post(f"{api_url}/predict", json=rec, timeout=10).json()
            same_cnt += res["prediction"] == int(predict_one(rec)["prediction"])
        print(f"    20건 중 {same_cnt}건 일치 -> {'PASS' if same_cnt == 20 else 'FAIL'}")
        ok &= same_cnt == 20

    print("\n전체 결과:", "모두 통과" if ok else "실패 항목 있음")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=None)
    raise SystemExit(0 if main(ap.parse_args().api) else 1)
