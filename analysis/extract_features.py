#!/usr/bin/env python3
"""
콤마인드 원시 기록(JSON) → 사람별 지표 표(CSV)

사용법:
    python3 analysis/extract_features.py <JSON 파일들이 있는 폴더> [-o features.csv]

드라이브의 COMMIND_원시기록 폴더를 통째로 내려받아 그 폴더를 넣으면 됩니다.
결과 CSV 한 줄 = 검사 한 번(기록ID 하나). 열 이름 앞의 코드는 '수집 데이터 정의서'의 지표 코드입니다.
계산할 수 없는 지표(콘텐츠에 해당 장면이 없거나 센서가 없는 기기 등)는 빈칸으로 둡니다.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import welch

# 영상이 있는 문제 (영상 시청 시간이 섞이므로 머뭇거림·응답시간 계산에서 뺌)
VIDEO_SLIDES = {"q1", "q3", "q4", "q5", "q6", "q8"}
# 글 문제 (영상 없음) — 선택 반응시간(B03)
TEXT_SLIDES = {"q9", "q10", "q11", "q12"}
# 그리기·선 잇기 (터치가 넓은 영역 위에서 일어남)
DRAW_SLIDES = {"q13", "q15"}
# 교통안전 문제 (오답률 B19)
SAFETY_QS = ["q1", "q3", "q4", "q5", "q6", "q8", "q9", "q10", "q11", "q12"]

HESITATE_MS = 2000      # 머뭇거림: 2초 이상 아무것도 누르지 않은 구간
REPEAT_MS = 1000        # 불필요한 재터치: 같은 대상을 1초 안에 다시 누름
UNSTABLE_SD = 1.0       # 기울기 불안정: 개인 평균보다 표준편차 1배 이상 빠르게 움직이는 구간
FS = 50.0               # 움직임 센서를 이 주기(Hz)로 다시 맞춤


def nan_mean(a):
    a = [x for x in a if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.mean(a)) if a else np.nan


def nan_sd(a):
    a = [x for x in a if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.std(a, ddof=1)) if len(a) >= 2 else np.nan


def safe_div(a, b):
    return a / b if b else np.nan


# ---------------------------------------------------------------- 불러오기
def load(path):
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    touch = pd.DataFrame(r.get("touch", []), columns=r.get("touchCols"))
    motion = pd.DataFrame(r.get("motion", []), columns=r.get("motionCols"))
    events = r.get("events", [])
    return r, touch, motion, events


def slide_spans(events, duration):
    """화면별 [시작, 끝) 구간"""
    sl = [(e[0], e[2]) for e in events if e[1] == "slide"]
    spans = []
    for i, (t, s) in enumerate(sl):
        end = sl[i + 1][0] if i + 1 < len(sl) else duration
        spans.append((s, t, end))
    return spans


# ---------------------------------------------------------------- 기울기·떨림
def motion_features(motion, taps_t):
    """중력 방향 변화로 기울기를 잼 (들고 있는 각도 자체는 사람마다 달라서 쓰지 않음)"""
    out = {}
    m = motion.dropna(subset=["ax", "ay", "az"])
    if len(m) < FS * 5:          # 5초 분량도 안 되면 센서 없는 기기로 봄
        return out, None
    t = m["t"].to_numpy() / 1000.0
    grid = np.arange(t[0], t[-1], 1.0 / FS)
    acc = np.column_stack([np.interp(grid, t, m[c].to_numpy()) for c in ("ax", "ay", "az")])

    # 0.5초 이동평균 = 중력(자세) 성분, 나머지 = 떨림 성분
    k = int(FS * 0.5)
    kernel = np.ones(k) / k
    grav = np.column_stack([np.convolve(acc[:, i], kernel, mode="same") for i in range(3)])
    unit = grav / np.linalg.norm(grav, axis=1, keepdims=True)
    ref = np.median(unit, axis=0)
    ref /= np.linalg.norm(ref)
    dev = np.degrees(np.arccos(np.clip(unit @ ref, -1, 1)))          # 평소 각도에서 벗어난 정도(도)
    # 각속도(도/초): 0.2초 간격 방향 변화
    lag = int(FS * 0.2)
    ang = np.degrees(np.arccos(np.clip(np.sum(unit[lag:] * unit[:-lag], axis=1), -1, 1))) / 0.2
    speed = np.concatenate([np.full(lag, np.nan), ang])

    out["B16_기울기변동성_도"] = float(np.std(dev))
    # B18: 0.5초 안에 10도 이상 바뀐 횟수 (연속 구간은 한 번으로)
    half = int(FS * 0.5)
    jump = np.degrees(np.arccos(np.clip(np.sum(unit[half:] * unit[:-half], axis=1), -1, 1))) >= 10
    out["B18_기울기급변_횟수"] = int(np.sum(np.diff(jump.astype(int)) == 1) + (1 if jump.size and jump[0] else 0))
    out["B18_기울기급변_분당"] = out["B18_기울기급변_횟수"] / ((grid[-1] - grid[0]) / 60)

    # B17: 떨림 — 가속도 크기의 4~12Hz 성분 비율
    mag = np.linalg.norm(acc, axis=1)
    mag = mag - np.convolve(mag, kernel, mode="same")
    f, p = welch(mag, fs=FS, nperseg=min(256, len(mag)))
    band = (f >= 4) & (f <= 12)
    tot = (f >= 0.5)
    out["B17_떨림_4to12Hz비율"] = float(np.trapezoid(p[band], f[band]) / np.trapezoid(p[tot], f[tot])) if np.any(band) else np.nan
    out["B17_떨림_RMS"] = float(np.sqrt(np.mean(mag ** 2)))

    # C03: 터치 직전 1초 동안 기울기 변화량(도)
    pre = []
    for tt in taps_t:
        s = tt / 1000.0
        i0, i1 = np.searchsorted(grid, [s - 1.0, s])
        if i1 - i0 >= FS * 0.8:
            seg = unit[i0:i1]
            pre.append(float(np.degrees(np.arccos(np.clip(seg[0] @ seg[-1], -1, 1)))))
    out["C03_터치직전1초_기울기변화_도"] = nan_mean(pre)

    sp = speed[~np.isnan(speed)]
    thr = float(np.mean(sp) + UNSTABLE_SD * np.std(sp)) if sp.size else np.nan
    out["_불안정기준_도초"] = thr
    tilt = {"grid": grid, "speed": speed, "thr": thr, "tremor": mag}
    return out, tilt


def unstable_at(tilt, t_ms):
    """t 직전 0.5초 동안 기울기가 불안정했는지"""
    if tilt is None:
        return None
    s = t_ms / 1000.0
    i0, i1 = np.searchsorted(tilt["grid"], [s - 0.5, s])
    seg = tilt["speed"][i0:i1]
    seg = seg[~np.isnan(seg)]
    if seg.size == 0:
        return None
    return bool(np.max(seg) > tilt["thr"])


def tremor_rms(tilt, t0_ms, t1_ms):
    if tilt is None:
        return np.nan
    i0, i1 = np.searchsorted(tilt["grid"], [t0_ms / 1000.0, t1_ms / 1000.0])
    seg = tilt["tremor"][i0:i1]
    return float(np.sqrt(np.mean(seg ** 2))) if seg.size else np.nan


# ---------------------------------------------------------------- 터치
def tap_list(events):
    taps = []
    for e in events:
        if e[1] != "tap_target":
            continue
        d = e[3]
        taps.append({"t": e[0], "slide": e[2], **d})
    return taps


def touch_features(touch, taps):
    out = {}
    if touch.empty:
        return out
    # B11: 누름~뗌 시간 / B12: 접촉 면적
    dur, area = [], []
    open_ = {}
    for row in touch.itertuples(index=False):
        if row.kind == "d":
            open_[row.id] = row.t
            if row.type == "t" and row.w and row.h:
                area.append(row.w * row.h)
        elif row.kind in ("u", "c") and row.id in open_:
            if row.kind == "u":
                dur.append(row.t - open_[row.id])
            del open_[row.id]
    out["B11_터치지속_ms"] = nan_mean(dur)
    out["B12_접촉면적_평균"] = nan_mean(area) if area else np.nan
    out["B12_접촉면적_변동"] = nan_sd(area) if area else np.nan

    # 버튼 터치만 (그리기 화면과 영상 영역 제외)
    btn = [p for p in taps if p["slide"] not in DRAW_SLIDES and not p.get("none") and p.get("tag") == "button"]
    # B07: 버튼 중심에서 떨어진 거리 (버튼 반대각선 길이로 나눔: 0 = 정중앙, 1 = 모서리)
    acc = []
    for p in btn:
        cx, cy = p["x"] + p["w"] / 2, p["y"] + p["h"] / 2
        half_diag = math.hypot(p["w"], p["h"]) / 2
        if half_diag > 0:
            acc.append(math.hypot(p["px"] - cx, p["py"] - cy) / half_diag)
        p["_acc"] = acc[-1] if half_diag > 0 else None
    out["B07_터치정확도_중심거리비"] = nan_mean(acc)

    # B08: 빈 곳 터치 비율 (그리기 화면 제외)
    pool = [p for p in taps if p["slide"] not in DRAW_SLIDES]
    out["B08_빈곳터치_비율"] = safe_div(sum(1 for p in pool if p.get("none")), len(pool))
    out["B08_빈곳터치_횟수"] = sum(1 for p in pool if p.get("none"))

    # B09: 같은 버튼을 1초 안에 다시 누름 (숫자판은 연달아 누르는 게 정상이라 제외)
    rep = 0
    for a, b in zip(pool, pool[1:]):
        if a.get("none") or b.get("none") or a.get("cls") == "num-btn":
            continue
        same = (a["slide"], a.get("cls"), a.get("name"), a.get("x"), a.get("y")) == (b["slide"], b.get("cls"), b.get("name"), b.get("x"), b.get("y"))
        if same and b["t"] - a["t"] < REPEAT_MS:
            rep += 1
    out["B09_불필요재터치_횟수"] = rep
    out["_버튼터치수"] = len(btn)
    return out


def drag_features(touch):
    """B13·B14: 선 잇기(Q15)·시계(Q13)에서 손가락을 끈 궤적"""
    out = {}
    eff, peaks = [], []
    strokes, cur = [], {}
    for row in touch.itertuples(index=False):
        if row.slide not in DRAW_SLIDES:
            continue
        if row.kind == "d":
            cur[row.id] = [(row.t, row.x, row.y)]
        elif row.kind == "m" and row.id in cur:
            cur[row.id].append((row.t, row.x, row.y))
        elif row.kind in ("u", "c") and row.id in cur:
            cur[row.id].append((row.t, row.x, row.y))
            strokes.append(cur.pop(row.id))
    for st in strokes:
        a = np.array(st, dtype=float)
        if len(a) < 4:
            continue
        seg = np.hypot(np.diff(a[:, 1]), np.diff(a[:, 2]))
        path = seg.sum()
        straight = math.hypot(a[-1, 1] - a[0, 1], a[-1, 2] - a[0, 2])
        if path < 30:                      # 30px 미만은 탭으로 봄
            continue
        eff.append(straight / path)
        dt = np.diff(a[:, 0])
        v = np.where(dt > 0, seg / np.maximum(dt, 1e-6), 0)
        if len(v) >= 3:
            vs = np.convolve(v, np.ones(3) / 3, mode="same")
            pk = np.sum((vs[1:-1] > vs[:-2]) & (vs[1:-1] > vs[2:]) & (vs[1:-1] > 0.2 * vs.max()))
            peaks.append(int(pk))
    out["B13_드래그경로효율"] = nan_mean(eff)
    out["B14_드래그_속도봉우리수"] = nan_mean(peaks)
    out["_드래그수"] = len(eff)
    return out


# ---------------------------------------------------------------- 시간
def timing_features(events, spans, duration):
    out = {}
    taps_by_slide = {}
    for e in events:
        if e[1] == "tap_target":
            taps_by_slide.setdefault(e[2], []).append(e[0])
    answer_t = {e[2]: e[0] for e in events if e[1] == "answer"}

    # B03: 글 문제 화면이 뜬 뒤 답하기까지
    rts = []
    for s, t0, t1 in spans:
        if s in TEXT_SLIDES and s in answer_t:
            rts.append(answer_t[s] - t0)
    out["B03_글문제_응답시간_ms"] = nan_mean(rts)
    out["B03_글문제_응답시간_변동계수"] = safe_div(nan_sd(rts), nan_mean(rts)) if rts else np.nan

    # B04: 인지 과제(Q13~Q16) 화면별 소요 시간
    for s, t0, t1 in spans:
        if s in ("q13", "q15", "q16"):
            out[f"B04_{s}_소요_s"] = (t1 - t0) / 1000
    # B05·B06: 머뭇거림 (영상·신호등·로딩·결과 화면 제외)
    gaps = []
    total_s = 0.0
    for s, t0, t1 in spans:
        if s in VIDEO_SLIDES or s in ("q14", "loading", "result", "start") or t1 - t0 < 500:
            continue
        ts = [t0] + sorted(taps_by_slide.get(s, [])) + [t1]
        total_s += (t1 - t0) / 1000
        for a, b in zip(ts, ts[1:]):
            if b - a >= HESITATE_MS:
                gaps.append(b - a)
    out["B05_머뭇거림_분당"] = safe_div(len(gaps), total_s / 60) if total_s else np.nan
    out["B06_머뭇거림_평균_s"] = nan_mean(gaps) / 1000 if gaps else 0.0
    out["검사시간_s"] = duration / 1000
    return out


# ---------------------------------------------------------------- 신호등
def signal_features(events, tilt):
    out = {}
    trials = {}
    for e in events:
        d = e[3] if isinstance(e[3], dict) else {}
        if e[1] == "signal_on":
            trials[d["trial"]] = {"color": d["color"], "on": e[0], "press": None, "rt": None, "extra": 0}
        elif e[1] == "signal_press" and d.get("trial") in trials:
            tr = trials[d["trial"]]
            if d.get("first") and d.get("lightOn"):
                tr["press"], tr["rt"] = e[0], d.get("rt")
            else:
                tr["extra"] += 1
    if not trials:
        return out
    order = [trials[k] for k in sorted(trials)]
    go = [t["rt"] for t in order if t["color"] == "green" and t["rt"] is not None]
    n_green = sum(1 for t in order if t["color"] == "green")
    n_red = sum(1 for t in order if t["color"] == "red")
    out["B01_신호등_반응시간_ms"] = nan_mean(go)
    out["B02_신호등_반응시간_변동계수"] = safe_div(nan_sd(go), nan_mean(go)) if len(go) >= 2 else np.nan
    out["B20_신호등_놓침률"] = safe_div(sum(1 for t in order if t["color"] == "green" and t["press"] is None), n_green)
    out["신호등_빨강누름률"] = safe_div(sum(1 for t in order if t["color"] == "red" and t["press"] is not None), n_red)

    # C09: 뒤쪽 절반 정답률 - 앞쪽 절반 정답률 (음수 = 뒤로 갈수록 떨어짐)
    ok = [(t["color"] == "green") == (t["press"] is not None) for t in order]
    h = len(ok) // 2
    out["C09_후반_정답률변화"] = float(np.mean(ok[h:]) - np.mean(ok[:h])) if h else np.nan

    # C04: 빨간불에 누른 뒤 3초 안에 더 누른 횟수 / C05: 그때 떨림 증가
    errs = [t for t in order if t["color"] == "red" and t["press"] is not None]
    if errs:
        after = []
        for t in errs:
            n = sum(1 for e in events if e[1] == "signal_press" and 0 < e[0] - t["press"] <= 3000)
            after.append(n)
        out["C04_오류직후_재누름"] = nan_mean(after)
        if tilt is not None:
            post = nan_mean([tremor_rms(tilt, t["press"], t["press"] + 3000) for t in errs])
            base = tremor_rms(tilt, order[0]["on"], order[-1]["on"] + 2200)
            out["C05_오류직후_떨림증가비"] = safe_div(post, base)

    # C02: 기울기 불안정 직후 초록불 반응시간 / 안정 상태 반응시간
    if tilt is not None:
        st, un = [], []
        for t in order:
            if t["color"] == "green" and t["rt"] is not None:
                u = unstable_at(tilt, t["press"])
                (un if u else st).append(t["rt"])
        out["C02_불안정시_반응지연비"] = safe_div(nan_mean(un), nan_mean(st)) if un and st else np.nan
    return out


def tilt_accuracy(taps, tilt):
    """C01: 기울기가 불안정할 때 버튼 정확도 / 안정할 때 (1보다 크면 불안정할 때 더 빗나감)"""
    if tilt is None:
        return {}
    st, un = [], []
    for p in taps:
        if p.get("_acc") is None:
            continue
        u = unstable_at(tilt, p["t"])
        if u is None:
            continue
        (un if u else st).append(p["_acc"])
    return {"C01_불안정시_정확도저하비": safe_div(nan_mean(un), nan_mean(st)) if un and st else np.nan,
            "_불안정구간_터치수": len(un)}


# ---------------------------------------------------------------- 한 사람
def extract(path):
    r, touch, motion, events = load(path)
    duration = r.get("durationMs") or 0
    summ = (r.get("extra") or {}).get("summary") or {}
    spans = slide_spans(events, duration)
    taps = tap_list(events)

    row = {
        "기록ID": r.get("recordId"),
        "연구참여번호": str(summ.get("participantCode", "")),
        "검사시작": r.get("startedAt"),
        "기관": summ.get("institution", ""),
        "기기": "태블릿/폰" if (r.get("device") or {}).get("maxTouch", 0) > 0 else "PC",
        "화면_가로x세로": f'{(r.get("device") or {}).get("vw")}x{(r.get("device") or {}).get("vh")}',
        "센서_허락": r.get("sensorPermission"),
        "기록형식": r.get("version"),
    }
    # 기본정보 (통제·규준용)
    for k in ("pf_age", "pf_sex", "pf_eduYears", "pf_digital", "pf_hand", "pf_glasses", "pf_hearingAid",
              "pf_tremor", "pf_memoryComplaint", "pf_sleep", "pf_assisted"):
        row[k] = summ.get(k, "")

    tap_times = [p["t"] for p in taps if p["slide"] not in DRAW_SLIDES]
    mf, tilt = motion_features(motion, tap_times)
    row["센서_수집"] = tilt is not None

    row.update(signal_features(events, tilt))
    row.update(timing_features(events, spans, duration))
    row.update(touch_features(touch, taps))
    row.update(drag_features(touch))
    row.update(mf)
    row.update(tilt_accuracy(taps, tilt))

    # B19: 교통안전 문제 오답률 / B23: 표지판 기억 오류
    qs = [summ.get(q) for q in SAFETY_QS if summ.get(q) not in (None, "")]
    row["B19_교통문제_오답률"] = safe_div(sum(1 for v in qs if float(v) < 10), len(qs))
    # B19는 복습 퀴즈(Q9~Q12, 기록형식 2부터)를 빼고 처음 배우는 문제만
    if (summ.get("logVersion") or 1) >= 2:
        qs = [summ.get(q) for q in SAFETY_QS if q not in ("q9", "q10", "q11", "q12") and summ.get(q) not in (None, "")]
        row["B19_교통문제_오답률"] = safe_div(sum(1 for v in qs if float(v) < 10), len(qs))
    rec = [e[3] for e in events if e[1] == "recall_submit"]
    row["B23_표지판기억_오류"] = (3 - rec[-1]["hits"]) / 3 if rec else np.nan

    # M: 복습 퀴즈 (기억력 보조 지표, 원시 기록의 review_answer 사건에서 계산)
    rv = [e[3] for e in events if e[1] == "review_answer"]
    items = [x for x in rv if x.get("src") not in ("", None)]
    learned = [x for x in items if x.get("srcCorrect") == 1]
    row["M01_복습_오답률"] = safe_div(sum(1 for x in rv if not x.get("correct")), len(rv)) if rv else np.nan
    row["M02_기억유지_실패율"] = safe_div(sum(1 for x in learned if not x.get("correct")), len(learned)) if learned else np.nan
    row["M03_모른다_비율"] = safe_div(sum(1 for x in rv if x.get("dk")), len(rv)) if rv else np.nan
    row["M04_복습_반응시간"] = nan_mean([x["rtMs"] for x in rv if x.get("rtMs") is not None]) if rv else np.nan
    q12 = [x for x in rv if x.get("q") == 12]
    row["M05_출처기억_실패"] = (0 if q12[-1].get("correct") else 1) if q12 else np.nan
    delays = [x["delayMs"] / 1000 for x in items if isinstance(x.get("delayMs"), (int, float))]
    row["M06_복습까지_지연초"] = nan_mean(delays) if delays else np.nan

    # 응답 과정(R)·영상(V): 화면에서 이미 계산된 값
    for k in ("rp_yearTypingMs", "rp_yearDeletes", "rp_changes", "rp_profile1Ms", "rp_profile2Ms",
              "vid_n", "vid_played", "vid_early", "vid_watchPct", "vid_afterEndMs"):
        row[k] = summ.get(k, "")
    # 화면 점수 (참고용, 연구 결과 변수 아님)
    for k in ("safetyScore", "cognitiveScore", "q13_clock", "q15_match", "q16_memory"):
        row["화면점수_" + k] = summ.get(k, "")
    return row


def main():
    ap = argparse.ArgumentParser(description="콤마인드 원시 기록 → 지표 CSV")
    ap.add_argument("inputs", nargs="+", help="JSON 파일 또는 폴더")
    ap.add_argument("-o", "--out", default="features.csv")
    a = ap.parse_args()
    files = []
    for x in a.inputs:
        p = Path(x)
        files += sorted(p.glob("*.json")) if p.is_dir() else [p]
    rows, bad = [], []
    for f in files:
        try:
            rows.append(extract(f))
        except Exception as e:  # 깨진 파일이 있어도 나머지는 계속
            bad.append((f.name, repr(e)))
    df = pd.DataFrame(rows)
    df.to_csv(a.out, index=False, encoding="utf-8-sig")   # 엑셀에서 한글이 깨지지 않게
    print(f"{len(rows)}명 → {a.out}")
    for name, err in bad:
        print(f"  건너뜀: {name}: {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
