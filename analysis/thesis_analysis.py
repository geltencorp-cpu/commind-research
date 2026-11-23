#!/usr/bin/env python3
"""
논문용 분석: 콤마인드 점수가 코그메이트와 얼마나 일치하는가

사용법:
    python3 analysis/thesis_analysis.py <사람별 CSV> -m <열 이름 설정 JSON> -o <결과 폴더> [--mock]

입력 CSV: 한 줄 = 한 사람. 기본정보 + 코그메이트 결과 + 콤마인드 지표가 한 줄에 있어야 합니다.
         (실제 연구에서는 extract_features.py 결과와 코그메이트 기록을 참여 번호로 이어 붙인 파일)
설정 JSON: 어느 열이 무엇인지 알려 줍니다. analysis/mapping_virtual.json 을 참고하세요.
--mock  : 모든 그림과 표에 '모의 연구 – 가상 데이터' 표시를 붙입니다.

결과 폴더에 나오는 것:
    표1_참여자특성.csv, 표2_지표별상관.csv, 표3_정확도.csv, 표4_모델비교.csv, 표5_큰오차.csv
    그림1_산점도.png, 그림2_블랜드알트만.png, 그림3_모델비교.png, 결과요약.md
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Noto Sans CJK KR"
plt.rcParams["axes.unicode_minus"] = False

MOCK_LABEL = "모의 연구 – 가상 데이터"


def grade(x):
    """코그메이트 등급 기준: A 20~50, B 15~19.9, C 0~14.9"""
    return np.where(x >= 20, "A", np.where(x >= 15, "B", "C"))


def fit(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    b, *_ = np.linalg.lstsq(X1, y, rcond=None)
    return b


def predict(b, X):
    return b[0] + np.asarray(X) @ b[1:]


def r2(y, yhat):
    return 1 - np.sum((y - yhat) ** 2) / np.sum((y - np.mean(y)) ** 2)


def adj_r2(r, n, k):
    return 1 - (1 - r) * (n - 1) / (n - k - 1)


def nested_f(y, X_small, X_big):
    """작은 모델 → 큰 모델로 늘어난 설명력이 우연인지 (F 검정)"""
    n = len(y)
    rs = r2(y, predict(fit(X_small, y), X_small)) if X_small.shape[1] else 0.0
    rb = r2(y, predict(fit(X_big, y), X_big))
    k_s, k_b = X_small.shape[1], X_big.shape[1]
    F = ((rb - rs) / (k_b - k_s)) / ((1 - rb) / (n - k_b - 1))
    p = 1 - stats.f.cdf(F, k_b - k_s, n - k_b - 1)
    return rs, rb, F, p


def loocv(X, y):
    """한 사람씩 빼고 나머지로 수식을 만든 뒤, 뺀 사람을 예측"""
    n = len(y); out = np.empty(n)
    for i in range(n):
        m = np.ones(n, bool); m[i] = False
        out[i] = predict(fit(X[m], y[m]), X[i:i + 1])[0]
    return out


def weighted_kappa(a, b, cats=("C", "B", "A")):
    """등급 일치도 (이웃 등급 차이는 덜, 두 칸 차이는 더 벌점: 2차 가중)"""
    idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)
    O = np.zeros((k, k))
    for x, y in zip(a, b):
        O[idx[x], idx[y]] += 1
    W = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)]) / (k - 1) ** 2
    E = np.outer(O.sum(1), O.sum(0)) / O.sum()
    return 1 - (W * O).sum() / (W * E).sum() if (W * E).sum() else np.nan


def agreement(y, yhat, graded=True):
    r, p = stats.pearsonr(yhat, y)
    d = yhat - y
    res = {"r": r, "p": p, "MAE": np.mean(np.abs(d)), "RMSE": np.sqrt(np.mean(d ** 2)),
           "평균차이(편향)": np.mean(d), "일치한계_하": np.mean(d) - 1.96 * np.std(d, ddof=1),
           "일치한계_상": np.mean(d) + 1.96 * np.std(d, ddof=1)}
    if graded:
        g1, g2 = grade(y), grade(yhat)
        res["등급일치율"] = np.mean(g1 == g2)
        res["가중카파"] = weighted_kappa(g1, g2)
    return res


def stamp(fig, mock):
    if mock:
        fig.text(0.99, 0.01, MOCK_LABEL, ha="right", va="bottom", fontsize=9, color="#b3261e")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("-m", "--mapping", required=True)
    ap.add_argument("-o", "--out", default="thesis_out"); ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    M = json.loads(Path(a.mapping).read_text(encoding="utf-8"))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(a.csv)

    inc = df[M["include_col"]] == M["include_value"]
    excluded = df[~inc]
    d = df[inc].reset_index(drop=True)
    n = len(d)
    C = M["cogmate"]
    y = {k: d[C[k]].to_numpy(float) for k in ("attention", "memory", "brain_age")}
    age = d[M["age"]].to_numpy(float)
    edu = d[M["education"]].to_numpy(float)

    # ---------------- 표1 참여자 특성
    rows = [["분석 인원", f"{n}명 (제외 {len(excluded)}명: 코그메이트 집중력 0.0)"]]
    for lab, col in [("나이", M["age"]), ("교육연수", M["education"])] + [(k, v) for k, v in M.get("describe", {}).items()]:
        v = d[col]; rows.append([lab, f"{v.mean():.1f} ± {v.std(ddof=1):.1f} (범위 {v.min():g}~{v.max():g})"])
    for lab, k in [("코그메이트 집중력", "attention"), ("코그메이트 기억력", "memory"), ("코그메이트 뇌 나이", "brain_age")]:
        v = y[k]; rows.append([lab, f"{v.mean():.1f} ± {v.std(ddof=1):.1f}"])
    for lab, k in [("집중력 등급 A/B/C", "attention"), ("기억력 등급 A/B/C", "memory")]:
        g = pd.Series(grade(y[k])).value_counts()
        rows.append([lab, " / ".join(f"{g.get(c, 0)}명" for c in "ABC")])
    t1 = pd.DataFrame(rows, columns=["항목", "값 (평균 ± 표준편차)"])

    # ---------------- 표2 지표별 상관
    rows = []
    other = {"attention": "memory", "memory": "attention"}
    names = {"attention": "집중력", "memory": "기억력"}
    for dom in ("attention", "memory"):
        for role in ("primary", "auxiliary"):
            for lab, col in M["indicators"][dom][role].items():
                x = d[col].to_numpy(float)
                r1, p1 = stats.pearsonr(x, y[dom]); r2_, p2 = stats.pearsonr(x, y[other[dom]])
                rows.append([names[dom], "주요" if role == "primary" else "보조", lab, r1, p1, r2_, abs(r1) - abs(r2_)])
    for lab, col in M.get("control_indicators", {}).items():
        x = d[col].to_numpy(float); r1, p1 = stats.pearsonr(x, y["attention"]); r2_, _ = stats.pearsonr(x, y["memory"])
        rows.append(["대조", "-", lab, r1, p1, r2_, np.nan])
    t2 = pd.DataFrame(rows, columns=["점수", "구분", "지표", "r(짝 점수)", "p", "r(다른 점수)", "영역 구분(|r짝|-|r다른|)"])

    # ---------------- 콤마인드 점수 (전체 적합 + 교차검증)
    def cols(dom, roles=("primary", "auxiliary")):
        cs = [c for role in roles for c in M["indicators"][dom][role].values()]
        return d[cs].to_numpy(float)
    X_att, X_att1 = cols("attention"), cols("attention", ("primary",))
    X_mem = cols("memory")
    pred_in = {"attention": predict(fit(X_att, y["attention"]), X_att),
               "memory": predict(fit(X_mem, y["memory"]), X_mem)}
    pred_cv = {"attention": loocv(X_att, y["attention"]), "memory": loocv(X_mem, y["memory"])}
    Xb_in = np.column_stack([age, pred_in["attention"], pred_in["memory"]])
    pred_in["brain_age"] = predict(fit(Xb_in, y["brain_age"]), Xb_in)
    # 뇌 나이 교차검증: 각 회차 안에서 집중력·기억력 수식부터 다시 만듦 (뺀 사람 정보가 새지 않게)
    bcv = np.empty(n)
    for i in range(n):
        m = np.ones(n, bool); m[i] = False
        ba = fit(X_att[m], y["attention"][m]); bm = fit(X_mem[m], y["memory"][m])
        Xtr = np.column_stack([age[m], predict(ba, X_att[m]), predict(bm, X_mem[m])])
        Xte = np.column_stack([age[i:i+1], predict(ba, X_att[i:i+1]), predict(bm, X_mem[i:i+1])])
        bcv[i] = predict(fit(Xtr, y["brain_age"][m]), Xte)[0]
    pred_cv["brain_age"] = bcv

    # ---------------- 표3 정확도
    rows = []
    for k, lab in [("attention", "집중력"), ("memory", "기억력"), ("brain_age", "뇌 나이")]:
        for how, P in [("교차검증 (본 결과)", pred_cv), ("전체 적합 (참고)", pred_in)]:
            g = agreement(y[k], P[k], graded=(k != "brain_age"))
            rows.append({"점수": lab, "방식": how, **g})
    t3 = pd.DataFrame(rows)

    # ---------------- 표4 모델 비교
    rows = []
    def add(name, Xs, Xb, yy, lab):
        rs, rb, F, p = nested_f(yy, Xs, Xb)
        mae_s = np.mean(np.abs(loocv(Xs, yy) - yy)) if Xs.shape[1] else np.mean(np.abs(yy.mean() - yy))
        mae_b = np.mean(np.abs(loocv(Xb, yy) - yy))
        rows.append([lab, name, Xs.shape[1], Xb.shape[1], rs, rb, rb - rs, F, p, mae_s, mae_b])
    AE = np.column_stack([age, edu])
    add("신호등만 → + 보조 지표", X_att1, X_att, y["attention"], "집중력")
    add("나이·학력만 → + 행동 지표", AE, np.column_stack([AE, X_att]), y["attention"], "집중력")
    add("나이·학력만 → + 행동 지표", AE, np.column_stack([AE, X_mem]), y["memory"], "기억력")
    add("나이만 → + 콤마인드 두 점수", age[:, None], Xb_in, y["brain_age"], "뇌 나이")
    t4 = pd.DataFrame(rows, columns=["점수", "비교", "작은 모델 값 수", "큰 모델 값 수", "R²(작은)", "R²(큰)", "ΔR²",
                                     "F", "p", "교차검증 MAE(작은)", "교차검증 MAE(큰)"])

    # ---------------- 표5 크게 빗나간 사람 (교차검증 기준 상위 5명)
    diff = pred_cv["attention"] - y["attention"]
    top = np.argsort(-np.abs(diff))[:5]
    t5 = pd.DataFrame({"참여번호": d[M["id"]].to_numpy()[top], "나이": age[top], "교육연수": edu[top],
                       "코그메이트 집중력": y["attention"][top], "콤마인드 집중력(교차검증)": pred_cv["attention"][top],
                       "차이": diff[top]})

    for t, f in [(t1, "표1_참여자특성"), (t2, "표2_지표별상관"), (t3, "표3_정확도"), (t4, "표4_모델비교"), (t5, "표5_큰오차")]:
        if a.mock:
            t = t.copy(); t.insert(0, "비고", MOCK_LABEL)
        t.to_csv(out / f"{f}.csv", index=False, encoding="utf-8-sig")

    # ---------------- 그림
    labs = [("attention", "집중력"), ("memory", "기억력"), ("brain_age", "뇌 나이")]
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.4))
    for ax, (k, lab) in zip(axs, labs):
        ax.scatter(y[k], pred_cv[k], s=22, color="#2563eb", alpha=.8)
        lo, hi = min(y[k].min(), pred_cv[k].min()), max(y[k].max(), pred_cv[k].max())
        ax.plot([lo, hi], [lo, hi], color="#9ca3af", lw=1, ls="--", label="완전 일치선")
        if k != "brain_age":
            for v in (15, 20):
                ax.axvline(v, color="#e5e7eb", lw=.8); ax.axhline(v, color="#e5e7eb", lw=.8)
        rr = stats.pearsonr(y[k], pred_cv[k])[0]
        ax.set_title(f"{lab}  (r = {rr:.2f}, 평균 오차 {np.mean(np.abs(pred_cv[k]-y[k])):.1f})", fontsize=11)
        ax.set_xlabel(f"코그메이트 {lab}"); ax.set_ylabel(f"콤마인드 {lab} (교차검증)")
    axs[0].legend(loc="upper left", fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.03, 1, 1)); stamp(fig, a.mock); fig.savefig(out / "그림1_산점도.png", dpi=160); plt.close(fig)

    fig, axs = plt.subplots(1, 3, figsize=(13, 4.4))
    for ax, (k, lab) in zip(axs, labs):
        mean_ = (pred_cv[k] + y[k]) / 2; dd = pred_cv[k] - y[k]
        bias, sd = dd.mean(), dd.std(ddof=1)
        ax.scatter(mean_, dd, s=22, color="#2563eb", alpha=.8)
        ax.axhline(bias, color="#111827", lw=1.2, label=f"평균 차이 {bias:+.1f}")
        for v in (bias - 1.96 * sd, bias + 1.96 * sd):
            ax.axhline(v, color="#dc2626", lw=1, ls="--")
        x0 = ax.get_xlim()[0]
        ax.text(x0, bias + 1.96 * sd, f" 일치 한계 상한 {bias+1.96*sd:+.1f}", va="bottom", ha="left", fontsize=8, color="#dc2626")
        ax.text(x0, bias - 1.96 * sd, f" 일치 한계 하한 {bias-1.96*sd:+.1f}", va="bottom", ha="left", fontsize=8, color="#dc2626")
        ax.set_title(lab, fontsize=11); ax.set_xlabel("두 점수의 평균"); ax.set_ylabel("콤마인드 − 코그메이트")
        ax.legend(loc="upper right", fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.03, 1, 1)); stamp(fig, a.mock); fig.savefig(out / "그림2_블랜드알트만.png", dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    labels = [f"{r[0]}\n{r[1]}" for r in rows]
    xs = np.arange(len(rows)); w = .36
    ax.bar(xs - w/2, t4["교차검증 MAE(작은)"], w, color="#9ca3af", label="작은 모델")
    ax.bar(xs + w/2, t4["교차검증 MAE(큰)"], w, color="#2563eb", label="큰 모델")
    for i, (s, b) in enumerate(zip(t4["교차검증 MAE(작은)"], t4["교차검증 MAE(큰)"])):
        ax.text(i - w/2, s, f"{s:.1f}", ha="center", va="bottom", fontsize=8)
        ax.text(i + w/2, b, f"{b:.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(xs); ax.set_xticklabels(labels, fontsize=8); ax.set_ylabel("교차검증 평균 오차 (낮을수록 정확)")
    ax.spines[["top", "right"]].set_visible(False); ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1)); stamp(fig, a.mock); fig.savefig(out / "그림3_모델비교.png", dpi=160); plt.close(fig)

    # ---------------- 요약 (논문 쓸 때 보는 숫자 모음)
    with open(out / "결과요약.md", "w", encoding="utf-8") as f:
        if a.mock: f.write(f"> {MOCK_LABEL}\n\n")
        for t, name in [(t1, "표1 참여자 특성"), (t2, "표2 지표별 상관"), (t3, "표3 정확도"), (t4, "표4 모델 비교"), (t5, "표5 크게 빗나간 사람")]:
            f.write(f"## {name}\n\n{t.round(3).to_markdown(index=False)}\n\n")
    print(f"완료: {out}  (분석 {n}명, 제외 {len(excluded)}명)")


if __name__ == "__main__":
    main()
