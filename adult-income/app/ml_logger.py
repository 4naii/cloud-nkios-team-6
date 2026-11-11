"""재학습/강화학습용 구조화(JSON) 로그를 CloudWatch Logs 로 보내는 로거.

- 항상 콘솔(stdout) 과 logs/events.jsonl 에 한 줄 JSON 으로 남긴다.
- 환경변수 CW_LOG_GROUP 이 설정되어 있으면 boto3 로 CloudWatch Logs 에도 put_log_events 한다.
  (EC2/ECS 의 IAM Role 또는 aws configure 자격증명 사용)
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_GROUP = os.getenv("CW_LOG_GROUP")  # 예: /mlops/income-predictor
LOG_STREAM = os.getenv("CW_LOG_STREAM", f"api-{datetime.now(timezone.utc):%Y%m%d}")
REGION = os.getenv("AWS_REGION", "ap-northeast-2")
LOCAL_FILE = Path(__file__).resolve().parents[1] / "logs" / "events.jsonl"


class MLEventLogger:
    def __init__(self):
        self._lock = threading.Lock()
        self._client = None
        LOCAL_FILE.parent.mkdir(exist_ok=True)
        if LOG_GROUP:
            import boto3

            self._client = boto3.client("logs", region_name=REGION)
            self._ensure_stream()

    def _ensure_stream(self):
        c = self._client
        try:
            c.create_log_group(logGroupName=LOG_GROUP)
        except c.exceptions.ResourceAlreadyExistsException:
            pass
        try:
            c.create_log_stream(logGroupName=LOG_GROUP, logStreamName=LOG_STREAM)
        except c.exceptions.ResourceAlreadyExistsException:
            pass

    @property
    def cloudwatch_enabled(self) -> bool:
        return self._client is not None

    def log(self, event_type: str, **fields):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            **fields,
        }
        line = json.dumps(record, ensure_ascii=False)
        print(line, flush=True)
        with self._lock:
            with LOCAL_FILE.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            if self._client:
                try:
                    self._client.put_log_events(
                        logGroupName=LOG_GROUP,
                        logStreamName=LOG_STREAM,
                        logEvents=[{"timestamp": int(time.time() * 1000), "message": line}],
                    )
                except Exception as e:  # 로깅 실패가 예측 API 를 죽이면 안 된다
                    print(json.dumps({"event_type": "cloudwatch_error", "error": str(e)}), flush=True)
        return record
