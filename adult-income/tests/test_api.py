"""API 테스트: pytest -q"""
from fastapi.testclient import TestClient

from app.main import app

GOOD = dict(age=45, workclass="Private", education_num=14, marital_status="Married-civ-spouse",
            occupation="Exec-managerial", relationship="Husband", race="White", sex="Male",
            capital_gain=15024, capital_loss=0, hours_per_week=50, native_country="United-States")


def test_health():
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"


def test_index_page():
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200 and "연소득 예측기" in r.text


def test_predict_high_income():
    with TestClient(app) as c:
        r = c.post("/predict", json=GOOD)
        assert r.status_code == 200
        body = r.json()
        assert body["label"] == ">50K" and 0 <= body["probability"] <= 1


def test_predict_rejects_bad_input():
    with TestClient(app) as c:
        assert c.post("/predict", json={**GOOD, "age": 5}).status_code == 422        # 범위 밖
        assert c.post("/predict", json={**GOOD, "sex": "X"}).status_code == 422      # 없는 범주
        bad = dict(GOOD); bad.pop("age")
        assert c.post("/predict", json=bad).status_code == 422                       # 필수값 누락
