"""재학습/강화학습 로그 테스트: pytest -q"""
import json

from fastapi.testclient import TestClient

from app import ml_logger
from app.main import app
from tests.test_api import GOOD


def read_events():
    return [json.loads(l) for l in ml_logger.LOCAL_FILE.read_text(encoding="utf-8").splitlines()]


def test_predict_logs_event():
    with TestClient(app) as c:
        rid = c.post("/predict", json=GOOD).json()["request_id"]
    ev = next(e for e in read_events() if e["request_id"] == rid)
    assert ev["event_type"] == "prediction"
    assert ev["raw_input"]["age"] == 45 and "features" in ev and "model_version" in ev


def test_feedback_reward_and_label():
    with TestClient(app) as c:
        rid = c.post("/predict", json=GOOD).json()["request_id"]           # >50K 로 예측됨
        assert c.post("/feedback", json={"request_id": rid, "actual_over_50k": True}).json()["reward"] == 1.0
        assert c.post("/feedback", json={"request_id": rid, "actual_over_50k": False}).json()["reward"] == -1.0
        assert c.post("/feedback", json={"request_id": rid, "reaction": "helpful"}).json()["reward"] == 0.5
    labels = [e["label"] for e in read_events() if e["request_id"] == rid and e["event_type"] == "feedback"]
    assert labels == [1, 0, None]


def test_feedback_unknown_id():
    with TestClient(app) as c:
        assert c.post("/feedback", json={"request_id": "nope"}).status_code == 404
