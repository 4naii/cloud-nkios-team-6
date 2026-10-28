"""소득 예측 API + 입력 화면

실행: uvicorn app.main:app --reload
화면: http://127.0.0.1:8000        API 문서: http://127.0.0.1:8000/docs
CloudWatch 전송: CW_LOG_GROUP 환경변수 설정 시 (docs/CLOUDWATCH_LOGGING.md)
"""
from contextlib import asynccontextmanager
from pathlib import Path

import logging
import time
import traceback
import uuid

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.ml_logger import MLEventLogger
from app.schemas import FeedbackIn, PersonIn, PredictionOut
from src.features import transform
from src.predict import MODEL_PATH, load_model, predict_one

STATIC = Path(__file__).parent / "static"
# 모델 파일 수정 시각을 버전으로 사용 (재학습하면 자동으로 바뀜)
MODEL_VERSION = time.strftime("v%Y%m%d-%H%M%S", time.localtime(MODEL_PATH.stat().st_mtime)) \
    if MODEL_PATH.exists() else "unknown"

ml_log = MLEventLogger()
# request_id -> 예측 결과 (피드백 보상 계산용, 운영에서는 DynamoDB 등으로 교체)
PREDICTIONS: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()  # 서버 시작 시 모델을 미리 로드 (없으면 바로 에러로 알려줌)
    yield


app = FastAPI(title="Adult Income Predictor", version="1.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """예상치 못한 에러도 원인을 JSON으로 돌려줘서 화면에 표시되게 함"""
    logging.error(traceback.format_exc())
    ml_log.log("error", path=request.url.path, error=f"{type(exc).__name__}: {exc}")
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "threshold": load_model()["threshold"],
            "model_version": MODEL_VERSION, "cloudwatch": ml_log.cloudwatch_enabled}


@app.post("/predict", response_model=PredictionOut)
def predict(person: PersonIn):
    started = time.perf_counter()
    record = person.model_dump()
    result = predict_one(record)
    request_id = str(uuid.uuid4())
    PREDICTIONS[request_id] = result

    ml_log.log(
        "prediction",
        request_id=request_id,
        model_version=MODEL_VERSION,
        raw_input=record,                                        # 재학습: 원본 입력
        features=transform(pd.DataFrame([record])).iloc[0].to_dict(),  # 실제 모델 입력
        probability=result["probability"],
        prediction=result["prediction"],
        threshold=result["threshold"],                           # 강화학습: 정책(action)
        confidence=round(abs(result["probability"] - result["threshold"]), 4),
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return {**result, "request_id": request_id}


@app.post("/feedback")
def feedback(fb: FeedbackIn):
    origin = PREDICTIONS.get(fb.request_id)
    if origin is None:
        raise HTTPException(404, "알 수 없는 request_id 입니다 (서버 재시작 시 초기화됨)")

    correct, reward = None, None
    if fb.actual_over_50k is not None:
        correct = int(fb.actual_over_50k) == origin["prediction"]
        reward = 1.0 if correct else -1.0
    elif fb.reaction != "none":
        reward = 0.5 if fb.reaction == "helpful" else -0.5

    ml_log.log(
        "feedback",
        request_id=fb.request_id,
        model_version=MODEL_VERSION,
        label=None if fb.actual_over_50k is None else int(fb.actual_over_50k),  # 재학습 정답
        prediction=origin["prediction"],
        probability=origin["probability"],
        threshold=origin["threshold"],
        correct=correct,
        reaction=fb.reaction,
        reward=reward,                                           # 강화학습 보상
    )
    return {"ok": True, "reward": reward}
