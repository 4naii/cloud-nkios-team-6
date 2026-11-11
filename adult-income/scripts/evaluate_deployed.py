"""배포된 서비스의 성능을 holdout 데이터로 직접 측정 (재배포 전/후 비교용)

holdout 행을 실제 /predict 로 보내 정확도·F1·재현율을 계산하고, /model-info 의 모델 정보와 함께
docs/deploy_eval/<시각>.json 에 저장한다. 요청은 source="eval" 로 표시되어 재학습 데이터에서 제외된다.

사용법: python -m scripts.evaluate_deployed --url http://<EC2 IP>:8000 --n 1000
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from sklearn.metrics import accuracy_score, f1_score, recall_score

from src.splits import test_split, to_records

ROOT = Path(__file__).resolve().parents[1]


def main(url: str, n: int):
    _, holdout = test_split()
    sample = holdout.sample(min(n, len(holdout)), random_state=7)
    s = requests.Session()
    info = s.get(f"{url}/model-info", timeout=10).json()

    preds, latencies = [], []
    for rec in to_records(sample):
        t0 = time.perf_counter()
        r = s.post(f"{url}/predict", json={**rec, "source": "eval"}, timeout=10)
        latencies.append((time.perf_counter() - t0) * 1000)
        r.raise_for_status()
        preds.append(r.json()["prediction"])

    y = sample["income"].astype(int).tolist()
    latencies.sort()
    result = {
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": url,
        "model_version": info["model_version"],
        "git_sha": info["info"].get("git_sha"),
        "n_feedback_in_training": info["info"].get("n_feedback"),
        "n_requests": len(y),
        "accuracy": round(accuracy_score(y, preds), 4),
        "f1": round(f1_score(y, preds), 4),
        "recall_over_50k": round(recall_score(y, preds), 4),
        "latency_ms_p50": round(latencies[len(latencies) // 2], 1),
        "latency_ms_p95": round(latencies[int(len(latencies) * 0.95)], 1),
    }
    out = ROOT / "docs/deploy_eval" / f"{result['measured_at'][:19].replace(':', '')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"-> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--n", type=int, default=1000)
    a = ap.parse_args()
    main(a.url.rstrip("/"), a.n)
