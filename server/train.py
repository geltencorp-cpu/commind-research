#!/usr/bin/env python3
"""모델 학습 → models/commind.joblib

    python3 train.py --data data/virtual_training.csv --source virtual     # 시연용 (가상)
    python3 train.py --data data/training.csv --source real                # 현장 데이터

source 가 virtual 이면 화면과 리포트에 '가상 데이터로 학습된 시연용 모델'이라고 표시됩니다.
"""
import argparse
import json

import joblib
import pandas as pd

from commind_ai.model import CommindModel

ap = argparse.ArgumentParser()
ap.add_argument("--data", required=True)
ap.add_argument("--source", choices=["virtual", "real"], required=True)
ap.add_argument("--note", default="")
ap.add_argument("-o", "--out", default="models/commind.joblib")
a = ap.parse_args()

df = pd.read_csv(a.data, dtype={"participantCode": str})
m = CommindModel().fit(df, a.source, a.note)
joblib.dump({"model": m, "table": df}, a.out)

c = m.card
print(f"학습 완료: {a.out}  ({'가상' if a.source == 'virtual' else '현장'} 데이터 {c['n']}명)")
for k, t in c["targets"].items():
    l = t["loocv"]
    extra = f"  등급 일치 {l['grade_agree']:.0%}  가중카파 {l['kappa']:.2f}" if "grade_agree" in l else ""
    print(f"- {t['name']}: {t['chosen_name']} 선택 | 교차검증 r {l['r']:.2f}  평균 오차 {l['mae']:.1f}{extra}")
    if "compare" in t:
        print("    비교: " + ", ".join(f"{n} 오차 {v['mae']:.2f}" for n, v in t["compare"].items()))
    if "importance" in t:
        print("    중요 지표: " + ", ".join(c for c, _ in t["importance"][:4]))
json.dump(c, open(a.out.replace(".joblib", "_card.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
