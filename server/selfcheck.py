#!/usr/bin/env python3
"""설치 점검: 서버를 띄우지 않고 모델·지표 추출·언어모델 리포트를 한 번씩 돌려 봅니다.
출력 전체를 복사해서 전달하면 문제를 찾기 쉽습니다. (개인정보 없음: 가상 참여자로 시험)"""
import json
import platform
import sys
import time
from pathlib import Path

import joblib

HERE = Path(__file__).parent
print("[점검 결과 시작]")
print(f"OS: {platform.platform()} | 파이썬 {sys.version.split()[0]}")
try:
    import xgboost, sklearn, fastapi
    print(f"패키지: xgboost {xgboost.__version__}, scikit-learn {sklearn.__version__}, fastapi {fastapi.__version__}")
except Exception as e:
    print("패키지 문제:", e)

b = joblib.load(HERE / "models" / "commind.joblib")
m, table = b["model"], b["table"]
c = m.card
print(f"모델: {'가상' if c['source'] == 'virtual' else '현장'} {c['n']}명, 학습 {c['trained_at']}")
for k, t in c["targets"].items():
    l = t["loocv"]
    g = f", 등급 일치 {l['grade_agree']:.0%}" if "grade_agree" in l else ""
    print(f"  {t['name']}: {t['chosen_name']} | 교차검증 r {l['r']:.2f}, 평균 오차 {l['mae']:.1f}{g}")

# 지표 추출 (분석 코드 불러오기)
try:
    from commind_ai.features import extract  # noqa: F401
    print("지표 추출 코드: OK")
except Exception as e:
    print("지표 추출 코드 문제:", e)

# 리포트 (언어모델)
from commind_ai import report
st = report.ollama_ok()
print(f"올라마: {'켜짐' if st['running'] else '꺼짐'} | 모델 {st['model']} {'설치됨' if st.get('installed') else '없음'}"
      + (f" | 설치된 모델 {st.get('models')}" if st["running"] else ""))
pid = str(table["participantCode"].iloc[11])
row = table.iloc[11].to_dict()
pred = m.predict(row)
f = report.facts(pred, None, "어르신")
t0 = time.time()
r = report.write(f)
print(f"리포트 시험 ({pid}): 작성 {r['source']} ({time.time() - t0:.1f}초)"
      + (f" | 안전장치: {r['guard']}" if r["guard"] else " | 안전장치 통과"))
print("--- 리포트 ---")
print(r["text"])
if r.get("rejected"):
    print("--- 안전장치가 걸러 낸 언어모델 답 ---")
    print(r["rejected"])
print("[점검 결과 끝]")
