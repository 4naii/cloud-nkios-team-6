"""로그(JSONL) -> 재학습용 데이터셋 + 분석 리포트

입력: data/feedback/raw_logs.jsonl  (scripts.fetch_logs 결과)
출력: data/feedback/feedback_labeled.csv  (원본 컬럼 + income, src.train 이 자동으로 사용)
      docs/FEEDBACK_ANALYSIS.md         (PR 에 넣을 재학습 데이터 분석)

전처리 규칙
  1. JSON 이 아니거나 event_type 이 없는 줄 제외
  2. source == "eval" 인 예측(배포 성능 측정용 요청)과 그 피드백 제외
  3. prediction 과 feedback 을 request_id 로 연결, 짝이 없는 feedback 제외
  4. 실제 소득(label)이 있는 피드백만 학습 데이터로 사용. 같은 요청에 여러 번 답하면 마지막 값
  5. 입력값을 API 와 같은 규칙(PersonIn)으로 다시 검증해서 범위 밖 값 제외
  6. 완전히 같은 (입력, 정답) 행은 1개만 유지
"""
import argparse
import json
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from app.schemas import PersonIn
from src.features import FEATURES, clean_target, load_raw

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/feedback/raw_logs.jsonl"
OUT_CSV = ROOT / "data/feedback/feedback_labeled.csv"
OUT_MD = ROOT / "docs/FEEDBACK_ANALYSIS.md"


def read_jsonl(path: Path) -> tuple[list[dict], int]:
    rows, bad = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if "event_type" in r:
                rows.append(r)
                continue
        except json.JSONDecodeError:
            pass
        bad += 1
    return rows, bad


def table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def main(raw_path: Path):
    events, bad = read_jsonl(raw_path)
    ev = pd.DataFrame(events)
    pred = ev[ev.event_type == "prediction"].drop_duplicates("request_id", keep="last").set_index("request_id")
    fb = ev[ev.event_type == "feedback"]
    src = pred["raw_input"].map(lambda r: (r or {}).get("source") or "web")
    pred = pred.assign(source=src)

    stats = {"전체 이벤트": len(ev), "JSON 오류로 제외": bad,
             "prediction": len(pred), "feedback": len(fb),
             "error": int((ev.event_type == "error").sum())}

    eval_ids = set(pred.index[pred.source == "eval"])
    pred_use = pred[pred.source != "eval"]
    fb = fb[~fb.request_id.isin(eval_ids)]
    orphan = ~fb.request_id.isin(pred_use.index)
    stats["eval 요청 제외 (prediction)"] = len(eval_ids)
    stats["짝 없는 feedback 제외"] = int(orphan.sum())
    fb = fb[~orphan]

    labeled = fb[fb.label.notna()].drop_duplicates("request_id", keep="last")
    stats["정답(label) 있는 피드백"] = len(labeled)

    rows, invalid = [], 0
    for rid, label in zip(labeled.request_id, labeled.label):
        raw_input = {k: v for k, v in pred_use.at[rid, "raw_input"].items() if k != "source"}
        try:
            PersonIn(**raw_input)
        except ValidationError:
            invalid += 1
            continue
        rows.append({**{k: raw_input[k] for k in FEATURES}, "income": int(label),
                     "_request_id": rid, "_pred": int(pred_use.at[rid, "prediction"]),
                     "_prob": float(pred_use.at[rid, "probability"]),
                     "_version": pred_use.at[rid, "model_version"], "_source": pred_use.at[rid, "source"]})
    data = pd.DataFrame(rows)
    stats["입력값 검증 실패 제외"] = invalid
    before = len(data)
    data = data.drop_duplicates(subset=FEATURES + ["income"])
    stats["중복 (입력, 정답) 제외"] = before - len(data)
    stats["최종 재학습 행 수"] = len(data)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    data[FEATURES + ["income"]].to_csv(OUT_CSV, index=False)

    # ---- 분석 ----
    train = load_raw(ROOT / "data/raw/adult-training.csv").drop_duplicates()
    train_pos = clean_target(train["income"]).mean()
    correct = data["_pred"] == data["income"]
    rewards = fb.reward.dropna()
    reactions = fb.reaction.value_counts().rename_axis("reaction").reset_index(name="건수")
    by_src = data.groupby("_source").agg(행수=("income", "size"), 고소득비율=("income", "mean"),
                                         기존모델정확도=("_pred", lambda s: (s == data.loc[s.index, "income"]).mean()))
    data["확률구간"] = pd.cut(data["_prob"], [0, .2, .37, .6, .8, 1.0], include_lowest=True).astype(str)
    by_bin = data.groupby("확률구간", observed=True).agg(
        행수=("income", "size"), 실제고소득비율=("income", "mean"),
        기존모델정확도=("_pred", lambda s: (s == data.loc[s.index, "income"]).mean())).reset_index()
    wrong = data[~correct]
    fp = int(((wrong._pred == 1) & (wrong.income == 0)).sum())
    fn = int(((wrong._pred == 0) & (wrong.income == 1)).sum())
    num = ["age", "education_num", "hours_per_week"]
    drift = pd.DataFrame({"컬럼": num, "train 평균": train[num].mean().round(2).values,
                          "피드백 평균": data[num].mean().round(2).values if len(data) else None})

    md = [
        "# 재학습 데이터 분석 (CloudWatch Logs → feedback_labeled.csv)", "",
        f"원본 로그: `{raw_path.name}`, "
        f"기간 {ev.timestamp.min()} ~ {ev.timestamp.max()}", "",
        "## 1. 전처리 단계별 건수", "", table(pd.DataFrame(stats.items(), columns=["단계", "건수"])), "",
        "## 2. 피드백 데이터 개요", "",
        f"- 정답이 있는 피드백 **{len(data)}건**, 고소득(>50K) 비율 **{data.income.mean():.1%}** "
        f"(원본 train {train_pos:.1%})",
        f"- 배포 모델이 이 사용자들에게 맞힌 비율 **{correct.mean():.1%}** "
        f"(틀린 {len(wrong)}건: 고소득 아닌데 고소득 예측 {fp}건, 고소득인데 놓침 {fn}건)",
        f"- 보상(reward) 평균 **{rewards.mean():+.3f}** ({len(rewards)}건)" if len(rewards) else "- 보상 기록 없음",
        "", "### 출처별", "", table(by_src.round(3).reset_index().rename(columns={"_source": "출처"})), "",
        "### 반응(reaction)", "", table(reactions), "",
        "### 예측 확률 구간별 실제 결과", "", table(by_bin.round(3)), "",
        "### 입력 분포 비교 (드리프트 점검)", "", table(drift), "",
    ]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"-> {OUT_CSV}\n-> {OUT_MD}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=RAW)
    main(ap.parse_args().input)
