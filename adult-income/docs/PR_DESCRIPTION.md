## 제목
feat: 소득 예측 API와 입력 화면 추가, 임계값 조정으로 >50K 재현율 개선

## 본문 (아래를 PR 본문에 붙여 넣기)

### 무엇을 했나요
- **예측 모델**: 원본 입력값을 그대로 받는 sklearn Pipeline(원-핫 + HistGradientBoosting)을 만들고 `models/`에 저장했습니다. (`src/train.py`)
- **API**: FastAPI로 `POST /predict`, `GET /health`를 만들었습니다. 잘못된 입력은 422로 거부합니다. (`app/`)
- **화면**: `/`에서 정보를 입력하면 예측 결과와 확률 막대를 보여줍니다. 예시 버튼도 넣었습니다. (`app/static/index.html`)
- **검증**: test 데이터 정확도, 저장된 지표와의 일치, 대표 사례, API와 모델 결과 일치를 검사합니다. (`scripts/validate.py`, `tests/`)
- **개선**: >50K 재현율이 0.65로 낮아서, 검증 데이터로 판정 임계값을 0.37로 조정했습니다. (`docs/IMPROVEMENT.md`)

### 결과 (test 16,281건)
| | 정확도 | F1 | >50K 재현율 |
|---|---|---|---|
| 개선 전 (0.5) | 0.873 | 0.708 | 0.650 |
| 개선 후 (0.37) | 0.862 | 0.723 | 0.762 |

### 실행 방법
```bash
pip install -r requirements.txt
python -m src.train
python -m scripts.validate
uvicorn app.main:app --reload   # http://127.0.0.1:8000
```

### 리뷰 포인트
- 정확도를 1%p 내주고 재현율을 올린 트레이드오프가 괜찮은지
- `models/model.joblib`은 sklearn 버전 차이 문제로 커밋하지 않고, 각자 `src.train`으로 생성하도록 했는데 괜찮은지
