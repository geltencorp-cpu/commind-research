"""콤마인드 AI 서버 (우리 서버에서만 동작, 받은 기록은 저장하지 않음)

    uvicorn app:app --host 0.0.0.0 --port 8000

GET  /                      시연 화면
GET  /api/health            모델·올라마 상태
GET  /api/model             모델 카드 (학습 데이터, 선택 모델, 교차검증 정확도, 중요 지표)
GET  /api/oof               교차검증 예측 vs 코그메이트 (산점도)
GET  /api/people            학습 데이터 참여자 목록 (시연용)
POST /api/score/person/{id} 학습 데이터의 한 사람 결과 (그 사람을 빼고 학습한 교차검증 예측 포함)
POST /api/score/raw         앱 원시 기록 파일(JSON)을 올려 바로 예측 + 리포트
"""
import os
from pathlib import Path

import joblib
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from commind_ai import report
from commind_ai.config import RULE_ABILITIES
from commind_ai.features import from_raw_bytes

HERE = Path(__file__).parent
MODEL_PATH = os.environ.get("COMMIND_MODEL", str(HERE / "models" / "commind.joblib"))
bundle = joblib.load(MODEL_PATH)
model, table = bundle["model"], bundle["table"]

app = FastAPI(title="COMMIND AI", docs_url="/docs")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def _clean(v):
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    return v


def _rules(src: dict) -> dict:
    out = {}
    for col, name in RULE_ABILITIES:
        v = src.get(col)
        if v not in (None, "") and not (isinstance(v, float) and np.isnan(v)):
            out[name] = round(float(v))
    return out


def _result(feats: dict, summary: dict, name: str, with_report: bool, cv=None):
    pred = model.predict(feats)
    if cv:
        # 학습에 쓴 사람은 '그 사람을 빼고 학습한 모델'의 예측을 점수로 씀 (화면·리포트 모두)
        from commind_ai.config import grade
        for k, v in cv.items():
            if k in pred:
                pred[k]["score"] = v["pred"]
                if k != "brain_age":
                    pred[k]["grade"] = grade(v["pred"])
    rules = _rules(summary)
    res = {"prediction": pred, "rules": rules, "cv": cv, "source": model.card["source"]}
    if with_report:
        f = report.facts(pred, rules, name)
        res["report"] = report.write(f)
    return _clean(res)


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"model": {"source": model.card["source"], "n": model.card["n"], "trained_at": model.card["trained_at"]},
            "ollama": report.ollama_ok()}


@app.get("/api/model")
def model_card():
    return _clean(model.card)


@app.get("/api/oof")
def oof():
    """전체 참여자의 교차검증 예측과 코그메이트 실제 점수 (산점도용)"""
    o = model.oof
    return _clean({k: (list(map(float, v)) if k != "id" else v) for k, v in o.items()})


@app.get("/api/people")
def people():
    cols = ["participantCode", "pf_age", "cg_attention", "cg_memory", "cg_brainAge"]
    return _clean(table[[c for c in cols if c in table]].to_dict("records"))


@app.post("/api/score/person/{pid}")
def score_person(pid: str, report_: bool = True):
    rows = table[table["participantCode"].astype(str) == pid]
    if rows.empty:
        raise HTTPException(404, "없는 참여번호")
    r = rows.iloc[0].to_dict()
    return _result(r, r, "어르신", report_, cv=model.oof_for(pid))


@app.post("/api/score/raw")
async def score_raw(file: UploadFile = File(...), report_: bool = True):
    data = await file.read()
    if len(data) > 20_000_000:
        raise HTTPException(413, "파일이 너무 큽니다")
    try:
        x = from_raw_bytes(data)
    except Exception as e:
        raise HTTPException(400, f"원시 기록 파일을 읽지 못했습니다: {type(e).__name__}")
    feats, summ = x["features"], x["summary"]
    res = _result(feats, summ, "어르신", report_)
    res["participantCode"] = summ.get("participantCode") or feats.get("연구참여번호")
    res["cogmate"] = {k: summ.get(k) for k in ("cg_attention", "cg_memory", "cg_brainAge") if summ.get(k) not in (None, "")}
    return res
