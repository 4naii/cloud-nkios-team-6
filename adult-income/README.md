# Adult Income 소득 예측

1994년 미국 인구조사 데이터(UCI Adult)로 **연소득 5만 달러 초과 여부**를 예측하는 이진 분류 프로젝트입니다.

## 결과

| 모델 | Test 정확도 | >50K 재현율 |
|---|---|---|
| 기준선 (전부 `<=50K`로 예측) | 0.764 | 0 |
| Logistic Regression | 0.847 | – |
| Random Forest | 0.848 | – |
| HistGradientBoosting (임계값 0.5) | 0.873 | 0.650 |
| **HistGradientBoosting (임계값 0.37, 최종)** | **0.862** | **0.762** |

임계값을 조정한 이유는 [docs/IMPROVEMENT.md](docs/IMPROVEMENT.md)에 정리했습니다.

## 빠른 시작

```bash
pip install -r requirements.txt
python -m src.train              # 모델 학습 -> models/model.joblib
python -m scripts.validate       # test 데이터로 검증
uvicorn app.main:app --reload    # 서버 실행
```

- 입력 화면: http://127.0.0.1:8000
- API 문서 (직접 호출 테스트 가능): http://127.0.0.1:8000/docs
- 테스트: `pytest -q`
- 예측/피드백 로그: `logs/events.jsonl`, `CW_LOG_GROUP` 설정 시 CloudWatch Logs 로 전송 → [docs/CLOUDWATCH_LOGGING.md](docs/CLOUDWATCH_LOGGING.md)

### API 예시

```bash
curl -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" -d '{
  "age": 45, "workclass": "Private", "education_num": 14, "marital_status": "Married-civ-spouse",
  "occupation": "Exec-managerial", "relationship": "Husband", "race": "White", "sex": "Male",
  "capital_gain": 15024, "capital_loss": 0, "hours_per_week": 50, "native_country": "United-States"}'
# {"prediction":1,"label":">50K","probability":0.9979,"threshold":0.37}
```

## 폴더 구조

```
├── app/
│   ├── main.py            # FastAPI: /, /predict, /feedback, /health
│   ├── ml_logger.py       # 재학습/강화학습용 JSON 로그 → CloudWatch Logs
│   ├── schemas.py         # 입력값 검증 규칙
│   └── static/index.html  # 입력 화면
├── src/
│   ├── features.py        # 전처리 (학습·API 공통)
│   ├── train.py           # 학습 + 임계값 선택 + 평가
│   ├── predict.py         # 예측 함수
│   └── preprocess.py      # (지난주) 전처리 CSV 생성
├── scripts/validate.py    # 검증
├── scripts/export_logs_to_s3.py  # CloudWatch 로그 스트림 → S3
├── tests/                 # pytest
├── models/                # 학습 결과 (model.joblib은 git 제외)
├── data/raw, data/processed
├── notebooks/adult_income.ipynb
└── docs/                  # 개선 분석, PR 가이드, Q&A
```

## 컬럼 설명

| 컬럼 | 의미 | 처리 |
|---|---|---|
| age | 나이 | 유지 |
| workclass | 고용 형태 (민간, 자영업, 정부 등) | 결측 → `Unknown` |
| fnlwgt | 인구조사 표본 가중치 | **삭제** |
| education | 최종 학력 (문자) | **삭제** |
| education_num | 학력 숫자 (1~16) | 유지 |
| marital_status | 혼인 상태 | 유지 |
| occupation | 직업군 | 결측 → `Unknown` |
| relationship | 가구 내 역할 (남편, 아내, 자녀 등) | 유지 |
| race | 인종 | 유지 |
| sex | 성별 | 유지 |
| capital_gain | 자본 이득 | log1p 변환 |
| capital_loss | 자본 손실 | log1p 변환 |
| hours_per_week | 주당 근무시간 | 유지 |
| native_country | 출신 국가 | 미국 / 기타 / Unknown |
| income | **타깃** (>50K = 1, <=50K = 0) | 숫자 변환 |

## 전처리 근거

- **fnlwgt 삭제**: 개인 특성이 아닌 통계용 표본 가중치이며, 소득과의 상관계수가 −0.01로 사실상 0입니다.
- **education 삭제**: `education_num`과 정확히 1:1 대응하는 중복 정보입니다.
- **결측치(`?`)를 `Unknown` 범주로 유지**: 결측 행이 전체의 7.4%라 삭제하면 손실이 큽니다. 또 결측 그룹의 고소득 비율(10%)이 평균(25%)과 달라, 결측 자체가 정보입니다.
- **native_country 그룹화**: 90%가 미국이고 나머지 국가는 표본이 매우 적어 과적합 위험이 있습니다.
- **capital_gain/loss log 변환**: 90% 이상이 0이고 최댓값이 99,999인 극단적 치우침을 완화합니다.
- **파일 오류 수정**: test 첫 줄의 쓰레기 행을 건너뛰고, test 레이블 끝의 마침표(`>50K.`)를 제거했습니다.
- **train 중복 제거**: 완전 중복 24행을 제거했습니다.
- 범주형 변수는 원-핫 인코딩했고, test 컬럼은 train 기준으로 맞췄습니다.

## 데이터 출처

Becker, B. & Kohavi, R. (1996). *Adult* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5XW20 (CC BY 4.0)
