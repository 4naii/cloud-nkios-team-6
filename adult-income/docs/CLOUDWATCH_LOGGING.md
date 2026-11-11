# 08주차: CloudWatch 로그 · S3 내보내기

## 1. 프로젝트 정의 (한 문장)

> **이직·연봉 협상을 앞둔 20~30대 직장인 '민지(29세, 학사, 마케팅 3년차, 주 45시간)'가 커리어 상담 웹에서**
> **나이·학력·직종·근무시간을 입력하면, 1994년 미국 인구조사(UCI Adult) 데이터로 학습한 모델이**
> **연소득 $50K 초과 그룹에 속할 확률을 알려 주어, 협상 전에 내 조건의 위치를 가늠하는 참고 지표로 쓰는 서비스.**

| 항목 | 내용 |
|---|---|
| 어떤 데이터로 | UCI Adult (1994 미국 인구조사), train 32,537건 / test 16,281건 |
| 무엇을 예측 | 연소득 $50K 초과(1) / 이하(0). **월급이 아니라 연소득 기준** |
| 누가 | 민지, 29세, 이직 제안을 받고 연봉 협상 근거를 찾는 마케터 |
| 어디서 | 커리어 상담 웹페이지 (`/` 화면) |
| 왜 | 협상 전에 "내 조건이면 고소득 그룹일 확률이 몇 %인가"를 객관적으로 확인하려고 |

## 2~4. 기존 모델 · API · 화면 동작 확인

| 확인 항목 | 명령 | 결과 |
|---|---|---|
| 모델 학습 | `python -m src.train` | 정확도 0.862, F1 0.723, >50K 재현율 0.762 (임계값 0.37) |
| 모델 검증 | `python -m scripts.validate` | 4개 항목 모두 PASS |
| API | `pytest -q` | 기존 5개 + 신규 3개 = 8 passed |
| 화면 | 브라우저에서 "예시: 고소득" → 99.8% 예측 → 피드백 버튼 → "피드백이 저장됐습니다 (reward 1)" | 정상 |

## 5. CloudWatch Logs: 재학습/강화학습용 로그

`app/ml_logger.py` 가 한 줄 JSON 이벤트를 남깁니다.
- 항상: 콘솔(stdout) + `logs/events.jsonl` (git 제외)
- `CW_LOG_GROUP` 환경변수가 있으면: boto3 `put_log_events` 로 CloudWatch Logs 에도 전송
- 로그 전송이 실패해도 예측 API 는 계속 동작합니다.

```bash
export CW_LOG_GROUP=/mlops/team6-adult-income
export AWS_REGION=ap-northeast-2
uvicorn app.main:app --host 0.0.0.0 --port 8000
# /health 응답의 "cloudwatch": true 로 연결 확인. 로그 스트림 이름 = api-YYYYMMDD
```

필요한 IAM 권한: `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`

### 이벤트 ① prediction (`POST /predict` 마다)

```json
{"timestamp":"2026-10-28T07:19:00Z","event_type":"prediction",
 "request_id":"9550416f-…","model_version":"v20261028-161735",
 "raw_input":{"age":45,"workclass":"Private","education_num":14,"capital_gain":15024.0,"…":"…"},
 "features":{"age":45,"capital_gain":9.617,"native_country":"United-States","…":"…"},
 "probability":0.9979,"prediction":1,"threshold":0.37,"confidence":0.6279,"latency_ms":12.4}
```

### 이벤트 ② feedback (`POST /feedback`, 화면의 피드백 버튼)

```json
{"timestamp":"2026-10-28T07:19:00Z","event_type":"feedback",
 "request_id":"9550416f-…","model_version":"v20261028-161735",
 "label":0,"prediction":1,"probability":0.9979,"threshold":0.37,
 "correct":false,"reaction":"none","reward":-1.0}
```

### 이벤트 ③ error: 처리되지 않은 예외 (경로 + 에러 메시지)

### 필드별로 왜 필요한가

| 필드 | 재학습 | 강화학습 | 이유 |
|---|:-:|:-:|---|
| `request_id` | ✅ | ✅ | prediction 과 feedback 을 연결하는 키 |
| `raw_input` | ✅ | ✅ state | 사람이 입력한 원본. 전처리가 바뀌어도 다시 변환 가능 |
| `features` | ✅ | | 실제 모델 입력 (`src/features.transform` 결과). 학습/서빙 불일치 점검 |
| `label` | ✅ | | 사용자가 알려 준 실제 소득 = 새 학습 데이터 |
| `model_version` | ✅ | ✅ | 어떤 모델이 낸 결과인지 (model.joblib 수정 시각). 버전별 성능 비교·롤백 판단 |
| `probability`, `confidence` | ✅ | | 확률 분포 변화 = 데이터 드리프트 신호. 임계값 근처(불확실) 샘플을 우선 라벨링 |
| `threshold` | | ✅ action | 우리 팀이 0.37 로 조정한 임계값 자체가 정책. 보상으로 다시 조정 가능 |
| `reward` | | ✅ | 실제값 맞춤 +1 / 틀림 −1, 👍 +0.5 / 👎 −0.5 |
| `latency_ms` | | | 재학습 후 응답이 느려지지 않았는지 운영 모니터링 |

**재학습 흐름:** S3 로그에서 `prediction` ⋈ `feedback` (request_id) → `label` 있는 행만 → `raw_input` 을 기존 train 에 추가 → `python -m src.train` → `scripts.validate` 통과 + 지표 개선 시 교체.

**강화학습 흐름:** (state = raw_input, action = threshold, reward) 를 모아 contextual bandit 방식으로 임계값을 사용자 피드백 기준으로 조정. 지금의 0.37(F1 기준)을 실제 사용자 만족 기준으로 다시 맞추는 것이 목표.

## 6. Log Stream → S3 내보내기

### AWS CloudShell 에서 5~6단계를 한 번에

AWS 콘솔 상단의 CloudShell 아이콘(`>_`)을 열고:

```bash
git clone -b feat/0418dlftjd-cloudwatch-logs https://github.com/4naii/cloud-nkios-team-6.git
cd cloud-nkios-team-6/adult-income
bash scripts/cloudshell_s3_demo.sh
```

모델 학습 → 버킷 생성·정책 적용 → API 실행(CloudWatch 로깅) → 예측·피드백 3건 → 로그 스트림 S3 export → S3 파일 확인까지 진행합니다.
필요 권한: `s3:CreateBucket`, `s3:PutBucketPolicy`, `logs:*` (CreateLogGroup/Stream, PutLogEvents, CreateExportTask, DescribeExportTasks)

### 실행 결과 (2026-10-28, CloudShell, ap-northeast-2)

| 단계 | 결과 |
|---|---|
| `/health` | `"cloudwatch": true`, model_version `v20261028-074039` |
| 예측 3건 + 피드백 6건 | 로그 그룹 `/mlops/team6-adult-income` / 스트림 `api-20261028` 에 기록됨 |
| Export task `46a9ef75-…` | `PENDING` → `COMPLETED` |
| S3 | `s3://team6-adult-income-logs-<계정>/income-predictor-logs/2026/10/28/46a9ef75-…/api-20261028/000000.gz` (300B) + `aws-logs-write-test` |

S3 에서 받은 로그 예시 (CloudWatch 수집 시각 + 우리 JSON):

```
2026-10-28T07:40:48.358Z {"event_type": "feedback", "request_id": "490a03f9-…", "label": 1, "prediction": 0,
  "probability": 0.0855, "threshold": 0.37, "correct": false, "reaction": "none", "reward": -1.0}
```

> 참고: 로그를 보낸 지 약 1분 만에 export 해서 일부 이벤트만 포함됐습니다. AWS 문서상 로그가 export 가능해지기까지 최대 12시간이 걸릴 수 있으므로, 운영에서는 하루치를 다음 날 export 합니다 (`--hours 24`).

### 스크립트만 따로 실행

```bash
python scripts/export_logs_to_s3.py --group /mlops/team6-adult-income --stream api-20261028 --bucket <버킷> --hours 24
```

- CloudWatch `CreateExportTask` 로 스트림 하나를 `s3://<버킷>/income-predictor-logs/YYYY/MM/DD/` 로 내보내고, 완료될 때까지 상태를 출력합니다.
- 버킷 정책: [s3-bucket-policy.json](s3-bucket-policy.json) (`<YOUR-BUCKET>` 교체)
- 콘솔에서 할 경우: CloudWatch → 로그 그룹 → 작업 → "Amazon S3로 데이터 내보내기" → 스트림 접두사 지정

## 알려진 한계

- 피드백 매칭용 `PREDICTIONS` 는 메모리 dict 라 서버 재시작 시 사라집니다 → 운영 시 DynamoDB/Redis.
- 사용자가 알려 준 실제 소득은 자기 보고값이라 노이즈가 있을 수 있습니다.
- `sex`, `race` 를 입력으로 쓰므로, 재학습 시 공정성 점검(그룹별 재현율 비교)이 필요합니다.
- 한 번에 실행 중인 export task 는 계정당 1개뿐이라, 매일 자동으로 내보내려면 EventBridge 스케줄 + Lambda 또는 Kinesis Firehose 구독으로 바꾸는 것이 좋습니다.
