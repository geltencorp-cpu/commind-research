"""리포트 에이전트: 예측 결과 → 어르신·보호자가 읽을 쉬운 말 리포트.

- 우리 서버의 올라마(Ollama) 로컬 언어모델만 사용합니다. 데이터가 외부로 나가지 않습니다.
- 언어모델은 점수를 계산하지 않습니다. 예측 모델이 낸 숫자와 근거만 받아 '설명'합니다.
- 안전장치: 받은 숫자 외의 숫자, 병명·진단 표현이 나오면 그 글을 버리고 기본 문장으로 바꿉니다.
- 올라마가 꺼져 있어도 기본 문장(규칙 기반)으로 리포트가 나옵니다.
"""
import os
import re

import httpx

from .config import ACTIONS, PHRASES

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "exaone3.5:7.8b")
TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "120"))

BANNED = ["치매", "알츠하이머", "경도인지장애", "진단", "질환", "질병", "병원에 가", "약을", "처방", "MCI"]

SYSTEM = """너는 어르신 교통안전 교육 프로그램 '콤마인드'의 결과 설명 도우미다.
규칙:
1. 아래 [결과]에 있는 숫자와 사실만 사용한다. 새로운 숫자나 사실을 만들지 않는다.
2. 병 이름, 진단, 약, 치료에 대한 말을 하지 않는다. 이것은 의학적 진단이 아닌 생활 점검이다.
3. 어르신이 읽기 쉽게 짧은 문장, 존댓말, 쉬운 낱말을 쓴다. 영어와 전문 용어를 쓰지 않는다.
4. 좋은 점을 먼저 말하고, 아쉬운 점은 부드럽게 말한 뒤, [결과]의 '권할 생활 실천' 중 2가지를 그대로 권한다.
5. 등급이 C인 영역이 있으면 '가까운 치매안심센터에서 무료로 자세한 상담을 받아 보시길 권해요'라고 한 번만 안내한다.
6. 전체 5~7문장, 제목이나 목록 기호 없이 한 문단으로 쓴다."""


def facts(pred: dict, rules: dict | None = None, name: str = "어르신") -> dict:
    f = {"이름": name, "영역": []}
    acts = list(ACTIONS["공통"])
    for key in ("attention", "memory"):
        p = pred.get(key)
        if not p:
            continue
        use = [d for d in p["factors"] if d["col"] in PHRASES and not d["missing"]]
        good = [PHRASES[d["col"]][0] for d in use if d["contribution"] > 0.3][:2]
        weak = [PHRASES[d["col"]][1] for d in use if d["contribution"] < -0.3][:2]
        f["영역"].append({"이름": p["name"], "점수": p["score"], "만점": 50, "등급": p["grade"],
                         "잘한 점": good, "아쉬운 점": weak})
        if p["grade"] != "A":
            acts = ACTIONS[p["name"]] + acts
    f["권할 생활 실천(이 중에서 2가지)"] = acts[:4]
    if pred.get("brain_age"):
        f["뇌 나이"] = pred["brain_age"]["score"]
        f["실제 나이"] = pred["brain_age"]["age"]
    if rules:
        f["참고 영역(검증 전)"] = rules
    return f


def _numbers(text):
    return {float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)}


def _allowed(f):
    nums = set()

    def walk(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.update({float(v), float(round(v)), float(round(v, 1))})
        elif isinstance(v, dict):
            [walk(x) for x in v.values()]
        elif isinstance(v, list):
            [walk(x) for x in v]
        elif isinstance(v, str):
            nums.update(_numbers(v))
    walk(f)
    nums.update({1.0, 2.0, 50.0})   # '2가지', '하루 1번' 같은 표현 허용
    if "뇌 나이" in f and "실제 나이" in f:
        nums.add(float(round(abs(f["뇌 나이"] - f["실제 나이"]))))
    return nums


def guard(text: str, f: dict) -> list:
    problems = []
    extra = sorted(n for n in _numbers(text) if n not in _allowed(f))
    if extra:
        problems.append(f"결과에 없는 숫자 {extra}")
    hit = [w for w in BANNED if w in text]
    if hit:
        problems.append(f"쓰면 안 되는 표현 {hit}")
    if len(text) < 40:
        problems.append("너무 짧음")
    return problems


def template(f: dict) -> str:
    """올라마를 쓸 수 없거나 안전장치에 걸렸을 때 쓰는 기본 문장"""
    s = [f"{f['이름']}, 오늘 교통안전 교육과 활동에 끝까지 참여해 주셔서 감사합니다."]
    for a in f["영역"]:
        msg = {"A": "좋은 편이에요", "B": "조금 더 신경 쓰면 좋아요", "C": "관심을 가지고 관리가 필요해요"}[a["등급"]]
        s.append(f"{a['이름']}은 {a['점수']}점으로 {msg}.")
    if "뇌 나이" in f:
        diff = f["뇌 나이"] - f["실제 나이"]
        s.append("두뇌 활동 나이는 실제 나이와 비슷해요." if abs(diff) < 3 else
                 ("두뇌 활동 나이가 실제보다 조금 높게 나왔어요." if diff > 0 else "두뇌 활동 나이가 실제보다 젊게 나왔어요."))
    acts = f.get("권할 생활 실천(이 중에서 2가지)", ["하루 30분 걷기", "가족·이웃과 자주 대화하기"])
    for a in f["영역"]:
        if a["잘한 점"]:
            s.append(a["잘한 점"][0] + ".")
            break
    s.append(f"오늘부터 '{acts[0]}'와 '{acts[1]}'를 꾸준히 해 보세요.")
    if any(a["등급"] == "C" for a in f["영역"]):
        s.append("가까운 치매안심센터에서 무료로 자세한 상담을 받아 보시길 권해요.")
    return " ".join(s)


def ollama_ok() -> dict:
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        names = [m["name"] for m in r.json().get("models", [])]
        return {"running": True, "model": OLLAMA_MODEL, "installed": OLLAMA_MODEL in names, "models": names}
    except Exception as e:
        return {"running": False, "model": OLLAMA_MODEL, "installed": False, "error": type(e).__name__}


def write(f: dict) -> dict:
    """리포트 만들기. 결과: text, source(ollama/template), 안전장치 결과"""
    user = "[결과]\n" + str(f).replace("'", '"') + "\n\n위 결과로 어르신께 드릴 설명을 써 주세요."
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=TIMEOUT, json={
            "model": OLLAMA_MODEL, "stream": False, "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]})
        r.raise_for_status()
        text = r.json()["message"]["content"].strip()
    except Exception as e:
        return {"text": template(f), "source": "template", "model": None,
                "guard": [f"올라마 연결 안 됨 ({type(e).__name__})"]}
    problems = guard(text, f)
    if problems:
        return {"text": template(f), "source": "template", "model": OLLAMA_MODEL, "guard": problems, "rejected": text}
    return {"text": text, "source": "ollama", "model": OLLAMA_MODEL, "guard": []}
