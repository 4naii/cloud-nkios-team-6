"""소득 예측 API + 입력 화면

실행: uvicorn app.main:app --reload
화면: http://127.0.0.1:8000        API 문서: http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager
from pathlib import Path

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from app.schemas import PersonIn, PredictionOut
from src.predict import load_model, predict_one

STATIC = Path(__file__).parent / "static"



@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()  # 서버 시작 시 모델을 미리 로드 (없으면 바로 에러로 알려줌)
    yield


app = FastAPI(title="Adult Income Predictor", version="1.0.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """예상치 못한 에러도 원인을 JSON으로 돌려줘서 화면에 표시되게 함"""
    logging.error(traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "threshold": load_model()["threshold"]}


@app.post("/predict", response_model=PredictionOut)
def predict(person: PersonIn):
    return predict_one(person.model_dump())
