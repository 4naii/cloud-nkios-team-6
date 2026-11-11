"""배포된 서비스에 가상 사용자 트래픽을 보내 재학습용 로그를 쌓는다

test 데이터의 traffic 절반(src/splits.py)에서 프로필을 골라
  1) /predict 로 예측 요청 (source="simulated")
  2) /feedback 으로 실제 소득(정답) + 맞았는지에 따른 👍/👎 반응을 보낸다.
holdout 절반은 절대 보내지 않으므로 재학습 후 평가에 영향이 없다.

사용법: python -m scripts.simulate_users --url http://<EC2 IP>:8000 --n 500
"""
import argparse
import random

import requests

from src.splits import test_split, to_records


def main(url: str, n: int, seed: int):
    traffic, _ = test_split()
    sample = traffic.sample(min(n, len(traffic)), random_state=seed)
    s = requests.Session()
    sent = correct = 0
    for rec, label in zip(to_records(sample), sample["income"].astype(int)):
        res = s.post(f"{url}/predict", json={**rec, "source": "simulated"}, timeout=10)
        res.raise_for_status()
        body = res.json()
        hit = body["prediction"] == label
        s.post(f"{url}/feedback", json={"request_id": body["request_id"], "actual_over_50k": bool(label)}, timeout=10)
        if random.random() < 0.5:  # 절반 정도만 👍/👎 을 누른다고 가정
            s.post(f"{url}/feedback", json={"request_id": body["request_id"],
                                            "reaction": "helpful" if hit else "not_helpful"}, timeout=10)
        sent += 1
        correct += hit
        if sent % 50 == 0:
            print(f"{sent}/{len(sample)} 전송, 지금까지 정확도 {correct / sent:.3f}")
    print(f"완료: {sent}건 예측 + 피드백 전송 (배포 모델 정확도 {correct / max(sent, 1):.3f})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    random.seed(a.seed)
    main(a.url.rstrip("/"), a.n, a.seed)
