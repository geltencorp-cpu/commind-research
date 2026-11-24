#!/usr/bin/env python3
"""현장 데이터 → 학습용 표 (training.csv)

1) 드라이브 COMMIND_원시기록 폴더를 내려받아 지표 표를 만듭니다.
       python3 ../analysis/extract_features.py ~/내려받은/COMMIND_원시기록 -o data/features.csv
2) 구글 시트 첫 번째 탭을 CSV로 내려받습니다 (파일 > 다운로드 > CSV) → data/sheet.csv
3) 두 표를 기록ID로 이어 붙여 학습용 표를 만듭니다.
       python3 build_training.py data/features.csv data/sheet.csv -o data/training.csv
4) 학습
       python3 train.py --data data/training.csv --source real

빼는 기준: 참여번호가 없거나 T로 시작(진행자 시험), 코그메이트 점수가 없거나 집중력 0.0(검사 미완료).
같은 사람이 여러 번 했으면 첫 검사만 씁니다(연습 효과를 피하려고).
"""
import argparse
import re
from pathlib import Path

import pandas as pd

from commind_ai.config import ADJUST, BRAIN_AGE_COL, RULE_ABILITIES, TARGETS, feature_list

ROOT = Path(__file__).resolve().parents[1]


def sheet_headers():
    """apps-script.gs 의 COLUMNS 에서 '시트 제목 → 영문 키' 표를 읽음"""
    txt = (ROOT / "apps-script.gs").read_text(encoding="utf-8")
    return {h: k for h, k in re.findall(r"\['([^']+)',\s*'([A-Za-z0-9_]+)'\]", txt)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("sheet")
    ap.add_argument("-o", "--out", default="data/training.csv")
    a = ap.parse_args()

    f = pd.read_csv(a.features, dtype={"연구참여번호": str, "기록ID": str})
    s = pd.read_csv(a.sheet, dtype=str).rename(columns=sheet_headers())
    keep = ["recordId", "participantCode", "cg_attention", "cg_memory", "cg_brainAge", "cg_order"] + [c for c, _ in RULE_ABILITIES]
    s = s[[c for c in keep if c in s]]
    d = f.merge(s, left_on="기록ID", right_on="recordId", how="inner")
    log = [f"지표 {len(f)}줄, 시트 {len(s)}줄 → 기록ID로 이어진 줄 {len(d)}"]

    d["participantCode"] = d["participantCode"].fillna(d.get("연구참여번호")).astype(str).str.strip()
    n0 = len(d)
    d = d[(d["participantCode"] != "") & (d["participantCode"].str.lower() != "nan") & ~d["participantCode"].str.upper().str.startswith("T")]
    log.append(f"참여번호 없음·T로 시작 제외 {n0 - len(d)}")
    for c in ("cg_attention", "cg_memory", BRAIN_AGE_COL):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    n0 = len(d)
    d = d[d["cg_attention"].notna() & d["cg_memory"].notna() & (d["cg_attention"] > 0)]
    log.append(f"코그메이트 없음·집중력 0.0 제외 {n0 - len(d)}")
    n0 = len(d)
    d = d.sort_values("검사시작").drop_duplicates("participantCode", keep="first")
    log.append(f"같은 사람 재검사 제외 {n0 - len(d)}")

    cols = ["participantCode", "기록ID"] + [c for c, _, _ in ADJUST]
    for t in TARGETS.values():
        cols += [c for c, _, _ in feature_list(t["groups"])]
    cols += [c for c, _ in RULE_ABILITIES] + ["cg_attention", "cg_memory", BRAIN_AGE_COL, "cg_order"]
    out = d[[c for c in dict.fromkeys(cols) if c in d]]
    out.to_csv(a.out, index=False, encoding="utf-8-sig")
    print("\n".join(log))
    print(f"학습용 {len(out)}명 → {a.out}")
    miss = out.isna().mean()
    miss = miss[miss > 0.2]
    if len(miss):
        print("빈칸이 20% 넘는 지표 (모델은 평균으로 채움): " + ", ".join(f"{k} {v:.0%}" for k, v in miss.items()))


if __name__ == "__main__":
    main()
