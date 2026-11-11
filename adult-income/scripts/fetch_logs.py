"""CloudWatch Logs 에서 예측/피드백 이벤트를 받아 JSONL 로 저장

사용법 (AWS 자격증명이 있는 곳: CloudShell, EC2):
  python3 -m scripts.fetch_logs --days 14
  -> data/feedback/raw_logs.jsonl
"""
import argparse
import json
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/feedback/raw_logs.jsonl"


def main(group: str, days: int, region: str):
    logs = boto3.client("logs", region_name=region)
    start = int((time.time() - days * 86400) * 1000)
    events, bad = [], 0
    for page in logs.get_paginator("filter_log_events").paginate(logGroupName=group, startTime=start):
        for e in page["events"]:
            try:
                rec = json.loads(e["message"])
            except json.JSONDecodeError:
                bad += 1
                continue
            rec["_log_stream"] = e["logStreamName"]
            events.append(rec)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for rec in sorted(events, key=lambda r: r.get("timestamp", "")):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    kinds = {}
    for r in events:
        kinds[r.get("event_type")] = kinds.get(r.get("event_type"), 0) + 1
    print(f"{group}: {len(events)}건 저장 -> {OUT} (JSON 아님 {bad}건 제외)")
    print("이벤트 종류:", kinds)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="/mlops/team6-adult-income")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--region", default="ap-northeast-2")
    a = ap.parse_args()
    main(a.group, a.days, a.region)
