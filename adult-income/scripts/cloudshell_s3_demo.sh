#!/usr/bin/env bash
# AWS CloudShell 에서 5~6단계를 한 번에 실행:
#   API 실행(CloudWatch 로깅) -> 예측/피드백 요청 -> 로그 스트림을 S3 로 내보내기 -> 결과 확인
#
# 사용법 (CloudShell, adult-income 폴더에서):
#   bash scripts/cloudshell_s3_demo.sh [버킷이름]
set -euo pipefail

REGION="${AWS_REGION:-ap-northeast-2}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="${1:-team6-adult-income-logs-$ACCOUNT}"
export CW_LOG_GROUP="${CW_LOG_GROUP:-/mlops/team6-adult-income}"
export AWS_REGION="$REGION"
STREAM="api-$(date -u +%Y%m%d)"

echo "== 계정 $ACCOUNT / 리전 $REGION / 버킷 $BUCKET / 로그 그룹 $CW_LOG_GROUP / 스트림 $STREAM"

echo "== 1. 패키지 설치 + 모델 학습"
python3 -m pip install -q -r requirements.txt || python3 -m pip install -q --user -r requirements.txt
[ -f models/model.joblib ] || python3 -m src.train > /dev/null

echo "== 2. S3 버킷 준비"
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" > /dev/null
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION" > /dev/null
  fi
  echo "   버킷 생성: $BUCKET"
fi
sed -e "s/<YOUR-BUCKET>/$BUCKET/g" -e "s/ap-northeast-2/$REGION/g" docs/s3-bucket-policy.json > /tmp/policy.json
aws s3api put-bucket-policy --bucket "$BUCKET" --policy file:///tmp/policy.json
echo "   버킷 정책 적용 (CloudWatch Logs 쓰기 허용)"

echo "== 3. API 실행 (CloudWatch 로깅 켜짐)"
python3 -m uvicorn app.main:app --port 8000 > /tmp/api.log 2>&1 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
for _ in $(seq 30); do curl -sf localhost:8000/health > /dev/null && break; sleep 1; done
curl -s localhost:8000/health; echo

echo "== 4. 예측 + 피드백 요청 보내기"
post() { curl -s -X POST "localhost:8000/$1" -H 'Content-Type: application/json' -d "$2"; }
P1='{"age":45,"workclass":"Private","education_num":14,"marital_status":"Married-civ-spouse","occupation":"Exec-managerial","relationship":"Husband","race":"White","sex":"Male","capital_gain":15024,"capital_loss":0,"hours_per_week":50,"native_country":"United-States"}'
P2='{"age":22,"workclass":"Private","education_num":9,"marital_status":"Never-married","occupation":"Other-service","relationship":"Own-child","race":"White","sex":"Female","capital_gain":0,"capital_loss":0,"hours_per_week":25,"native_country":"United-States"}'
P3='{"age":29,"workclass":"Private","education_num":13,"marital_status":"Never-married","occupation":"Sales","relationship":"Not-in-family","race":"Asian-Pac-Islander","sex":"Female","capital_gain":0,"capital_loss":0,"hours_per_week":45,"native_country":"United-States"}'
for body in "$P1" "$P2" "$P3"; do
  rid=$(post predict "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["request_id"]); print(d["label"], d["probability"], file=sys.stderr)')
  post feedback "{\"request_id\":\"$rid\",\"reaction\":\"helpful\"}" > /dev/null
  post feedback "{\"request_id\":\"$rid\",\"actual_over_50k\":true}"; echo
done

echo "== 5. CloudWatch 반영 대기 (60초)"
sleep 60
aws logs get-log-events --log-group-name "$CW_LOG_GROUP" --log-stream-name "$STREAM" \
  --limit 3 --query 'events[].message' --output text | head -c 600 || true; echo

echo "== 6. 로그 스트림 -> S3 내보내기"
python3 scripts/export_logs_to_s3.py --group "$CW_LOG_GROUP" --stream "$STREAM" \
  --bucket "$BUCKET" --region "$REGION" --hours 24

echo "== 7. S3 결과"
aws s3 ls "s3://$BUCKET/income-predictor-logs/" --recursive
KEY=$(aws s3 ls "s3://$BUCKET/income-predictor-logs/" --recursive | awk '/\.gz$/ {print $4}' | tail -1)
[ -n "$KEY" ] && aws s3 cp "s3://$BUCKET/$KEY" - | gunzip | head -3 || true
echo "== 완료: s3://$BUCKET/income-predictor-logs/"
