#!/usr/bin/env python3
"""리포트 언어모델 비교 시험 (가상 참여자만 사용, 모의 연구 – 가상 데이터)

여러 명의 리포트를 써 보고 안전장치 통과율, 걸린 이유, 걸린 시간을 셉니다.
등급 A·B·C가 고루 섞이도록 사람을 고릅니다.

    OLLAMA_MODEL=qwen2.5vl:7b python3 report_eval.py -n 20
    OLLAMA_MODEL=exaone3.5:2.4b python3 report_eval.py -n 20

결과 글 전체는 data/report_eval_<모델>.md 에 저장됩니다 (저장소에는 올라가지 않음).
"""
import argparse
import collections
import time
from pathlib import Path

import joblib

from commind_ai import report

ap = argparse.ArgumentParser()
ap.add_argument("-n", type=int, default=20)
a = ap.parse_args()

HERE = Path(__file__).parent
b = joblib.load(HERE / "models" / "commind.joblib")
m, table = b["model"], b["table"]
if m.card["source"] != "virtual":
    raise SystemExit("이 시험은 가상 데이터 모델에서만 돌립니다 (실제 어르신 기록으로 글을 만들어 저장하지 않으려고).")

# 기억력 점수 순으로 줄 세운 뒤 고르게 뽑아 A·B·C가 섞이게
rows = table.sort_values("cg_memory").reset_index(drop=True)
idx = [round(i * (len(rows) - 1) / max(1, a.n - 1)) for i in range(a.n)]

st = report.ollama_ok()
print(f"모델 {report.OLLAMA_MODEL} | 올라마 {'켜짐' if st['running'] else '꺼짐'} | 설치 {'됨' if st.get('installed') else '안 됨'}")
ok, times, reasons, out = 0, [], collections.Counter(), []
for k, i in enumerate(idx):
    r = rows.iloc[i].to_dict()
    pred = m.predict(r)
    f = report.facts(pred, None, "어르신")
    t0 = time.time()
    res = report.write(f)
    dt = time.time() - t0
    times.append(dt)
    grades = "/".join(x["_등급"] for x in f["영역"])
    if res["source"] == "ollama":
        ok += 1
    for g in res["guard"]:
        reasons[g.split(" [")[0].split(" (")[0]] += 1
    out.append(f"## {r['participantCode']} (등급 {grades}) · {res['source']} · {dt:.1f}초\n"
               + (f"안전장치: {res['guard']}\n\n" if res["guard"] else "\n")
               + res["text"] + ("\n\n> 걸러 낸 답: " + res["rejected"].replace("\n", " ") if res.get("rejected") else "") + "\n")
    print(f"  {k + 1:2d}/{len(idx)} {r['participantCode']} 등급 {grades:5s} → {res['source']:8s} {dt:5.1f}초 {('· ' + '; '.join(res['guard'])) if res['guard'] else ''}")

n = len(idx)
print(f"\n통과 {ok}/{n} ({ok / n:.0%}) | 평균 {sum(times) / n:.1f}초, 가장 오래 {max(times):.1f}초")
if reasons:
    print("걸린 이유: " + ", ".join(f"{k} {v}건" for k, v in reasons.most_common()))
name = report.OLLAMA_MODEL.replace(":", "_").replace("/", "_")
p = HERE / "data" / f"report_eval_{name}.md"
p.parent.mkdir(exist_ok=True)
p.write_text(f"# 리포트 시험: {report.OLLAMA_MODEL} (모의 연구 – 가상 데이터)\n\n통과 {ok}/{n}\n\n" + "\n".join(out), encoding="utf-8")
print(f"글 전체: {p}")
