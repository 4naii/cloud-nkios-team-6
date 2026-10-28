"""CloudWatch Logs 의 로그 스트림 하나를 S3 로 내보낸다 (CreateExportTask).

사용 예:
  python scripts/export_logs_to_s3.py --group /mlops/income-predictor \
      --stream api-20261028 --bucket my-mlops-log-bucket --hours 24

사전 준비: S3 버킷 정책에서 logs.<region>.amazonaws.com 의 PutObject/GetBucketAcl 허용
(docs/s3-bucket-policy.json 참고)
"""
import argparse
import time
from datetime import datetime, timedelta, timezone

import boto3


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--group", required=True)
    p.add_argument("--stream", required=True, help="내보낼 로그 스트림 이름 (prefix 로 동작)")
    p.add_argument("--bucket", required=True)
    p.add_argument("--prefix", default="income-predictor-logs")
    p.add_argument("--hours", type=int, default=24, help="최근 N시간 구간")
    p.add_argument("--region", default="ap-northeast-2")
    a = p.parse_args()

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=a.hours)
    dest_prefix = f"{a.prefix}/{now:%Y/%m/%d}"

    logs = boto3.client("logs", region_name=a.region)
    task = logs.create_export_task(
        taskName=f"export-{a.stream}-{now:%H%M%S}",
        logGroupName=a.group,
        logStreamNamePrefix=a.stream,
        fromTime=int(start.timestamp() * 1000),
        to=int(now.timestamp() * 1000),
        destination=a.bucket,
        destinationPrefix=dest_prefix,
    )
    task_id = task["taskId"]
    print(f"Export task 생성: {task_id} -> s3://{a.bucket}/{dest_prefix}/")

    while True:
        status = logs.describe_export_tasks(taskId=task_id)["exportTasks"][0]["status"]
        print("상태:", status["code"], status.get("message", ""))
        if status["code"] in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(5)


if __name__ == "__main__":
    main()
