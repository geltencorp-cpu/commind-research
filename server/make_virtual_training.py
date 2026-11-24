#!/usr/bin/env python3
"""시연용 가상 학습 데이터 (모의 연구 – 가상 데이터, 실제 사람 아님).

현장 데이터가 모이기 전에 서버·모델·리포트가 끝까지 돌아가는지 보여 주기 위한 것입니다.
열 이름은 실제 데이터(extract_features.py 결과 + 시트의 코그메이트 칸)와 같습니다.
실제 데이터가 모이면 build_training.py 로 만든 표로 바꿔서 다시 학습하면 됩니다.

    python3 make_virtual_training.py -n 100 -o data/virtual_training.csv
"""
import argparse

import numpy as np
import pandas as pd


def make(n, seed):
    rng = np.random.default_rng(seed)
    age = rng.integers(65, 90, n)
    edu = rng.choice([0, 6, 9, 12, 16], n, p=[0.12, 0.33, 0.2, 0.25, 0.1])
    digital = rng.choice([0, 1, 2, 3], n, p=[0.3, 0.3, 0.2, 0.2])
    tremor = (rng.random(n) < 0.2).astype(int)
    common = rng.normal(0, 1, n)
    # 숨은 능력: 주의(빠르고 정확), 집중(끝까지 꾸준), 기억
    za = -0.06 * (age - 77) + 0.04 * (edu - 9) + 0.55 * common + 0.7 * rng.normal(0, 1, n)
    zf = 0.6 * za + 0.35 * common + 0.6 * rng.normal(0, 1, n)
    zm = -0.05 * (age - 77) + 0.05 * (edu - 9) + 0.55 * common + 0.7 * rng.normal(0, 1, n)
    sig = lambda x: 1 / (1 + np.exp(-x))
    clip = lambda x, lo, hi=None: np.clip(x, lo, hi)

    att = clip(22 + 4.5 * za + 2.5 * zf + rng.normal(0, 3, n), 0, 50).round(1)
    mem = clip(22 + 7 * zm + rng.normal(0, 3, n), 0, 50).round(1)
    brain = (age + 0.6 * (22 - (att + mem) / 2) + rng.normal(0, 2, n)).round(1)

    d = pd.DataFrame({
        "participantCode": [f"V{i + 1:03d}" for i in range(n)],
        "pf_age": age, "pf_eduYears": edu, "pf_digital": digital, "pf_tremor": tremor,
        # 주의력
        "B01_신호등_반응시간_ms": (780 - 75 * za + 3 * (age - 77) - 25 * digital + 40 * tremor + rng.normal(0, 110, n)).round(0),
        "B20_신호등_놓침률": (rng.binomial(6, sig(-2.2 - 0.9 * za)) / 6).round(3),
        # 집중력
        "B02_신호등_반응시간_변동계수": clip(0.22 - 0.05 * zf + rng.normal(0, 0.06, n), 0.05).round(3),
        "D01_반응저하비_2회차대1회차": clip(1.06 - 0.06 * zf + rng.normal(0, 0.07, n), 0.8).round(3),
        "B05_머뭇거림_분당": clip(2.0 - 0.5 * zf + rng.normal(0, 0.9, n), 0).round(2),
        "B16_기울기변동성_도": clip(3.0 - 0.6 * zf + 0.8 * tremor + rng.normal(0, 1.0, n), 0.3).round(2),
        "C01_불안정시_정확도저하비": clip(1.15 - 0.10 * zf + 0.08 * tremor + rng.normal(0, 0.16, n), 0.7).round(2),
        # 기억력
        "B23_표지판기억_오류": (rng.binomial(4, sig(-0.6 - 1.1 * zm)) / 4).round(3),
        "N01_1back_오답률": (rng.binomial(12, clip(0.18 - 0.08 * zm + rng.normal(0, 0.05, n), 0.01, 0.9)) / 12).round(3),
        "N04_1back_반응시간_ms": clip(1500 - 220 * zm + 8 * (age - 77) + rng.normal(0, 260, n), 500).round(0),
        "M02_기억유지_실패율": (rng.binomial(3, sig(-0.9 - 1.3 * zm)) / 3).round(3),
        "M03_모른다_비율": (rng.binomial(4, sig(-1.2 - 0.6 * zm)) / 4).round(2),
        "M05_출처기억_실패": (rng.random(n) < sig(-0.6 - 1.1 * zm)).astype(int),
        # 앱 규칙 점수 (지남력·시공간·집행기능·언어, 100점 환산)
        "cog_orientation": clip(np.round((0.85 + 0.08 * zm + rng.normal(0, 0.1, n)) * 25) * 4, 0, 100),
        "cog_visuospatial": clip(np.round(7 + 1.5 * za + rng.normal(0, 1.5, n)) * 10, 0, 100),
        "cog_executive": clip(np.round((0.8 + 0.08 * za + rng.normal(0, 0.08, n)) * 15) / 15 * 100, 0, 100).round(0),
        "cog_language": clip(np.round((0.85 + 0.06 * zm + rng.normal(0, 0.1, n)) * 4) * 25, 0, 100),
        # 코그메이트 (정답)
        "cg_attention": att, "cg_memory": mem, "cg_brainAge": brain,
    })
    # 센서가 없는 기기 (태블릿 대신 PC 등) 약 8%
    nos = rng.random(n) < 0.08
    d.loc[nos, ["B16_기울기변동성_도", "C01_불안정시_정확도저하비"]] = np.nan
    return d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20261124)
    ap.add_argument("-o", "--out", default="data/virtual_training.csv")
    a = ap.parse_args()
    df = make(a.n, a.seed)
    df.to_csv(a.out, index=False, encoding="utf-8-sig")
    print(f"가상 {len(df)}명 → {a.out}  (모의 연구 – 가상 데이터)")
