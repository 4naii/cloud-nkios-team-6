#!/usr/bin/env bash
# EC2 에서 1분마다 실행 (income-predictor-deploy.timer)
#   새 커밋이 있고 GitHub Actions CI("test" 잡)가 성공했으면 -> 체크아웃 -> 학습 -> 재시작 -> 헬스체크
#   헬스체크 실패 시 이전 커밋으로 롤백
# 수동 실행: sudo /home/app/repo/adult-income/deploy/deploy.sh
set -euo pipefail
# git checkout 이 실행 중인 이 파일을 바꿔도 안전하도록 복사본으로 실행
if [ -z "${DEPLOY_COPY:-}" ]; then
  cp "$0" /tmp/income-predictor-deploy.sh
  DEPLOY_COPY=1 exec bash /tmp/income-predictor-deploy.sh "$@"
fi
source /etc/income-predictor.env   # DEPLOY_BRANCH, GITHUB_REPO, CW_LOG_GROUP, AWS_REGION

REPO=/home/app/repo
APP=$REPO/adult-income
VENV=/home/app/venv
STATE=/var/lib/income-predictor
mkdir -p "$STATE"
as_app() { runuser -u app -- "$@"; }
log() { echo "[deploy] $*"; echo "$(date -u +%FT%TZ) $*" >> "$STATE/history.log"; }

cd "$REPO"
as_app git fetch -q origin "$DEPLOY_BRANCH"
NEW=$(as_app git rev-parse FETCH_HEAD)
CUR=$(cat "$STATE/deployed_sha" 2>/dev/null || echo none)
[ "$NEW" = "$CUR" ] && exit 0
[ "$NEW" = "$(cat "$STATE/failed_sha" 2>/dev/null || true)" ] && exit 0

CI=$("$VENV/bin/python" - "$GITHUB_REPO" "$NEW" <<'PY'
import json, sys, urllib.request
repo, sha = sys.argv[1:]
try:
    with urllib.request.urlopen(f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs", timeout=10) as r:
        runs = [c for c in json.load(r)["check_runs"] if c["name"] == "test"]
except Exception:
    print("pending"); sys.exit()
if not runs:
    print("pending")
elif any(c["status"] != "completed" for c in runs):
    print("pending")
else:
    print("success" if all(c["conclusion"] == "success" for c in runs) else "failure")
PY
)
case "$CI" in
  pending) echo "[deploy] ${NEW:0:7} CI 대기 중"; exit 0 ;;
  failure) log "SKIP ${NEW:0:7} CI 실패 -> 배포 안 함"; echo "$NEW" > "$STATE/failed_sha"; exit 0 ;;
esac

release() {  # $1 = sha
  as_app git checkout -q -f "$1"
  as_app "$VENV/bin/pip" install -q -r "$APP/requirements.txt"
  (cd "$APP" && as_app env GIT_SHA="$1" "$VENV/bin/python" -m src.train > "$STATE/train-$1.log")
  systemctl restart income-predictor
  for _ in $(seq 40); do
    sleep 2
    curl -sf localhost:8000/health | grep -q "\"git_sha\":\"$1\"" && return 0
  done
  return 1
}

log "DEPLOY ${NEW:0:7} 시작 (이전 ${CUR:0:7})"
if release "$NEW"; then
  echo "$NEW" > "$STATE/deployed_sha"
  log "DEPLOY ${NEW:0:7} 성공"
else
  echo "$NEW" > "$STATE/failed_sha"
  log "DEPLOY ${NEW:0:7} 헬스체크 실패 -> 롤백"
  [ "$CUR" != none ] && release "$CUR" && log "ROLLBACK ${CUR:0:7} 완료"
  exit 1
fi
