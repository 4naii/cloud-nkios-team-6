# 6조 타이타닉 모델 · API · 웹페이지

**실제 테스트 정확도 74.37%, 목표 85% 미달성.** 개선·진단 결과는 `REPORT.md`에 있습니다.
공개 저장소에는 원본 데이터·학습된 모델·개별 입력 예시를 포함하지 않습니다. 아래 안내에 따라 `6.csv`로 먼저 학습하면 모델과 API 입력 규격이 생성됩니다.

## 가장 쉬운 방법: Colab

1. 저장소에서 `projects/titanic/titanic_colab.ipynb`를 다운로드합니다.
2. Colab에서 **파일 → 노트북 업로드**로 `titanic_colab.ipynb`를 엽니다.
3. 위에서부터 셀을 실행합니다. 파일 선택 창이 뜨면 팀 자료의 `6.csv`를 선택합니다.
4. 모델 비교·학습이 끝나면 API 실행 셀과 웹페이지 표시 셀을 실행합니다.
5. 마지막 웹페이지에서 정보를 입력하고 **생존 여부 예측하기**를 누릅니다.

Colab에서는 런타임이 종료되면 API도 종료됩니다. iframe이 표시되지 않으면 아래 로컬 방법을 사용하세요.
이 노트북의 Colab 전용 셀은 이 작업 환경에서 실행하지 못했으며 로컬 모델/API 검증 결과와 구분합니다.

## 내 컴퓨터에서 실행 (Python 3.11 이상, 3.11~3.13 권장)

저장소를 다운로드한 뒤 터미널에서 `projects/titanic` 폴더로 이동합니다.

```sh
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS / Linux:

```sh
source .venv/bin/activate
```

```sh
python -m pip install -r requirements.txt
# 기존 팀 자료의 6.csv를 data/6.csv에 둔 뒤 실행
python train.py --data data/6.csv
python app.py
```

브라우저에서 **http://127.0.0.1:8000** 을 엽니다. HTML 파일을 직접 더블클릭하지 마세요.
종료는 터미널에서 Ctrl+C입니다. 서버는 기본적으로 내 컴퓨터에서만 접속 가능합니다.
표준 라이브러리 HTTP 서버를 사용하는 과제용 로컬 앱입니다. 공개 운영 서버로 배포하는 구성은 포함하지 않습니다.

## 모델 재학습

데이터는 기존 [팀 자료](../../team-6.md)에 있는 `6.csv`를 내려받아 이 폴더 아래 `data/6.csv`에 둡니다. `data` 폴더가 없으면 만드세요.

```sh
python train.py --data data/6.csv
```

원본 정답을 유지하며 5개 후보를 비교합니다. 결과가 85% 미만이면 `target_met`가 false로 저장됩니다.
학습 후 서버를 다시 실행해야 새 모델이 반영됩니다.

## API 명세

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/` | 예측 웹페이지 |
| GET | `/api/health` | 모델 로드 상태 |
| GET | `/api/schema` | 입력 23개 항목·타입·범위·선택지 |
| GET | `/api/metrics` | 실제 평가 결과 |
| POST | `/api/predict` | JSON 입력을 받아 생존 여부·확률 반환 |

학습 후 생성되는 요청 전체 예시는 `example_request.json`입니다. 전 항목의 키를 보내고 결측 허용 항목은 null로 보냅니다.
문자 `None`과 JSON null은 다릅니다. 정의되지 않은 키, 잘못된 범주·타입·범위는 422 오류입니다.

```sh
curl -X POST http://127.0.0.1:8000/api/predict -H "Content-Type: application/json" --data-binary @example_request.json
```

Windows PowerShell에서 curl 대신 `curl.exe`를 사용하면 됩니다.

가족 수·1인당 요금·연령 그룹 등 원본의 파생 입력은 자동 계산하지 않습니다.
연관된 항목을 변경할 때 서로 일치하도록 함께 입력하세요. 실제 입력·출력 예시는 웹페이지에서도 확인할 수 있습니다.

## 테스트

먼저 위의 모델 학습을 완료해야 합니다.

```sh
python -m unittest -v test_api.py
```

서버를 실행한 상태에서 Node.js 18 이상이 있으면 웹페이지의 JavaScript 요청 연결도 확인할 수 있습니다.

```sh
# macOS / Linux
API_URL=http://127.0.0.1:8000/ node test_ui.mjs
```

```powershell
# Windows PowerShell
$env:API_URL="http://127.0.0.1:8000/"
node test_ui.mjs
```

이 테스트는 DOM 대체 환경을 사용하므로 화면 배치 검증을 대신하지 않습니다.

## 파일 구성

- `train.py`: 데이터 읽기, 전처리, 모델 비교, 평가, 모델 저장
- `app.py`: 저장된 모델을 사용하는 HTTP JSON API 및 웹페이지 제공
- `static/index.html`: 실제 API를 호출하는 반응형 웹페이지
- `artifacts/model.joblib`: 재학습으로 생성되는 전처리+모델(저장소에는 포함하지 않음)
- `artifacts/schema.json`: 재학습으로 생성되는 입출력 규격
- `artifacts/metrics.json`: 기존 실행의 집계 평가 결과; 재학습 시 갱신
- `titanic_colab.ipynb`: Colab에서 파일 생성부터 API 실행까지 진행하는 노트북
- `data/6.csv`: 별도 준비할 원본 데이터(저장소에는 포함하지 않음)
- `REPORT.md`: 결과와 데이터 한계


원본 노트북과 데이터 링크는 [팀 자료](../../team-6.md)에 있습니다.
