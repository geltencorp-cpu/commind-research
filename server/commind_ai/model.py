"""콤마인드 예측 모델.

행동 지표 + 기본정보(보정)를 넣어 코그메이트 척도(0~50)의 주의·집중력, 기억력을 예측하고,
나이와 두 예측 점수로 뇌 나이를 예측한다.

- 후보 모델 두 개(규제 선형회귀, XGBoost)를 '한 명씩 빼고 확인(LOOCV)'으로 비교해 오차가 작은 쪽을 고른다.
- 뇌 나이는 학습에 쓰지 않은 사람 기준의 예측 점수(교차검증 예측)로 학습해 과대평가를 막는다.
- 한 사람의 예측마다 '어떤 지표가 점수를 올리고 내렸는지'(기여도)를 함께 돌려준다.
"""
import datetime as dt

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from xgboost import XGBRegressor

from .config import ADJUST, BRAIN_AGE_COL, TARGETS, feature_list, grade

XGB_PARAMS = dict(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8,
                  colsample_bytree=0.8, min_child_weight=3, random_state=7, n_jobs=1)


class _Linear:
    """표준화 + 규제 선형회귀. 기여도 = 가중치 × (값 - 평균)"""

    name = "규제 선형회귀"

    def fit(self, X, y):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        self.m = Ridge(alpha=1.0).fit((X - self.mu) / self.sd, y)
        return self

    def predict(self, X):
        return self.m.predict((X - self.mu) / self.sd)

    def contribs(self, X):
        return self.m.coef_ * (X - self.mu) / self.sd

    def importance(self, X):
        return np.abs(self.contribs(X)).mean(0)


class _XGB:
    """XGBoost. 기여도 = 트리 모델이 직접 계산하는 사람별 SHAP 값"""

    name = "XGBoost"

    def fit(self, X, y):
        self.m = XGBRegressor(**XGB_PARAMS).fit(X, y)
        return self

    def predict(self, X):
        return self.m.predict(X)

    def contribs(self, X):
        import xgboost as xgb
        c = self.m.get_booster().predict(xgb.DMatrix(X), pred_contribs=True)
        return c[:, :-1]   # 마지막 열은 기준값(평균)

    def importance(self, X):
        return np.abs(self.contribs(X)).mean(0)


CANDIDATES = {"linear": _Linear, "xgboost": _XGB}


def _loocv(cls, X, y):
    pred = np.zeros(len(y))
    for i in range(len(y)):
        m = np.ones(len(y), bool)
        m[i] = False
        pred[i] = cls().fit(X[m], y[m]).predict(X[i:i + 1])[0]
    return pred


def _wkappa(a, b, cats=("C", "B", "A")):
    idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)
    o = np.zeros((k, k))
    for x, y in zip(a, b):
        o[idx[x], idx[y]] += 1
    w = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)]) / (k - 1) ** 2
    e = np.outer(o.sum(1), o.sum(0)) / o.sum()
    return float(1 - (w * o).sum() / (w * e).sum()) if (w * e).sum() else float("nan")


def _metrics(y, p, graded=True):
    out = {"r": float(np.corrcoef(y, p)[0, 1]), "mae": float(np.mean(np.abs(p - y))),
           "bias": float(np.mean(p - y))}
    d = p - y
    out["loa"] = [float(d.mean() - 1.96 * d.std(ddof=1)), float(d.mean() + 1.96 * d.std(ddof=1))]
    if graded:
        gy, gp = [grade(v) for v in y], [grade(v) for v in p]
        out["grade_agree"] = float(np.mean([a == b for a, b in zip(gy, gp)]))
        out["kappa"] = _wkappa(gy, gp)
    return out


class CommindModel:
    def fit(self, df: pd.DataFrame, source: str, note: str = ""):
        self.adjust = [c for c, _, _ in ADJUST]
        self.parts, self.cols, self.medians, self.ref = {}, {}, {}, {}
        self.oof = {"id": df["participantCode"].astype(str).tolist()}
        card = {"source": source, "note": note, "n": int(len(df)),
                "trained_at": dt.datetime.now().isoformat(timespec="seconds"), "targets": {}}
        for key, t in TARGETS.items():
            feats = [c for c, _, _ in feature_list(t["groups"])] + self.adjust
            X = df[feats].astype(float)
            self.medians[key] = X.median()
            X = X.fillna(self.medians[key]).to_numpy()
            y = df[t["col"]].astype(float).to_numpy()
            tried = {}
            for name, cls in CANDIDATES.items():
                p = _loocv(cls, X, y)
                tried[name] = {"pred": p, **_metrics(y, p)}
            best = min(tried, key=lambda k: tried[k]["mae"])
            self.parts[key] = CANDIDATES[best]().fit(X, y)
            self.cols[key] = feats
            self.oof[key] = tried[best]["pred"]
            self.oof[t["col"]] = y
            # 지표 분포 (또래 대비 백분위 계산용)
            self.ref[key] = {c: np.sort(df[c].dropna().astype(float).to_numpy()) for c in feats}
            imp = self.parts[key].importance(X)
            card["targets"][key] = {
                "name": t["name"], "chosen": best, "chosen_name": CANDIDATES[best].name,
                "compare": {k: {m: v[m] for m in ("r", "mae", "grade_agree", "kappa")} for k, v in tried.items()},
                "loocv": {m: v for m, v in tried[best].items() if m != "pred"},
                "importance": sorted([[c, float(v)] for c, v in zip(feats, imp)], key=lambda x: -x[1]),
            }
        # 뇌 나이: 나이 + 교차검증 예측 점수 두 개 (학습에 쓰지 않은 사람 기준의 점수로 학습)
        if BRAIN_AGE_COL in df and df[BRAIN_AGE_COL].notna().all():
            A = np.column_stack([df["pf_age"].astype(float), self.oof["attention"], self.oof["memory"]])
            yb = df[BRAIN_AGE_COL].astype(float).to_numpy()
            pb = _loocv(_Linear, A, yb)
            p0 = _loocv(_Linear, A[:, :1], yb)
            self.brain = _Linear().fit(A, yb)
            self.oof["brain_age"] = pb
            self.oof[BRAIN_AGE_COL] = yb
            card["targets"]["brain_age"] = {"name": "뇌 나이", "chosen": "linear", "chosen_name": "선형회귀 (나이 + 두 점수)",
                                            "loocv": _metrics(yb, pb, graded=False),
                                            "age_only_mae": float(np.mean(np.abs(p0 - yb)))}
        else:
            self.brain = None
        self.card = card
        return self

    # ---------------------------------------------------------- 예측
    def _percentile(self, key, col, v):
        ref = self.ref[key].get(col)
        if ref is None or not len(ref) or v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(np.searchsorted(ref, v, side="right") / len(ref) * 100)

    def predict(self, feats: dict) -> dict:
        out = {}
        labels = {c: (lab, worse) for t in TARGETS.values() for c, lab, worse in feature_list(t["groups"])}
        labels.update({c: (lab, worse) for c, lab, worse in ADJUST})
        for key, t in TARGETS.items():
            cols = self.cols[key]
            raw = {c: feats.get(c) for c in cols}
            missing = [c for c, v in raw.items() if v is None or v == "" or (isinstance(v, float) and np.isnan(v))]
            x = pd.Series({c: (np.nan if c in missing else float(raw[c])) for c in cols}).fillna(self.medians[key])
            X = x.to_numpy()[None, :]
            score = float(np.clip(self.parts[key].predict(X)[0], 0, 50))
            con = self.parts[key].contribs(X)[0]
            group_of = {c: g for g, fs in t["groups"].items() for c, _, _ in fs}
            items = []
            for c, v, k in zip(cols, X[0], con):
                items.append({"col": c, "label": labels[c][0], "group": group_of.get(c, "보정"),
                              "value": None if c in missing else float(v), "missing": c in missing,
                              "contribution": float(k),
                              "percentile": None if c in missing else self._percentile(key, c, float(v))})
            items.sort(key=lambda d: -abs(d["contribution"]))
            by_group = {}
            for d in items:
                by_group[d["group"]] = by_group.get(d["group"], 0.0) + d["contribution"]
            out[key] = {"name": t["name"], "score": round(score, 1), "grade": grade(score),
                        "factors": items, "group_effect": {g: round(v, 2) for g, v in by_group.items()},
                        "missing": missing}
        if self.brain is not None and feats.get("pf_age") not in (None, ""):
            A = np.array([[float(feats["pf_age"]), out["attention"]["score"], out["memory"]["score"]]])
            out["brain_age"] = {"name": "뇌 나이", "score": round(float(self.brain.predict(A)[0]), 1),
                                "age": float(feats["pf_age"])}
        return out

    def oof_for(self, pid: str):
        """학습에 쓴 사람이면, 그 사람을 빼고 학습한 모델의 예측(교차검증 예측)을 돌려줌"""
        ids = self.oof["id"]
        if pid not in ids:
            return None
        i = ids.index(pid)
        res = {}
        for key, t in TARGETS.items():
            res[key] = {"pred": round(float(self.oof[key][i]), 1), "actual": float(self.oof[t["col"]][i])}
        if "brain_age" in self.oof:
            res["brain_age"] = {"pred": round(float(self.oof["brain_age"][i]), 1), "actual": float(self.oof[BRAIN_AGE_COL][i])}
        return res
