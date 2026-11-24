"""리포트 에이전트: 예측 결과 → 어르신·보호자가 읽을 쉬운 말 리포트.

- 우리 서버의 올라마(Ollama) 로컬 언어모델만 사용합니다. 데이터가 외부로 나가지 않습니다.
- 언어모델은 점수를 계산하지 않습니다. 예측 모델이 낸 숫자와 근거만 받아 '설명'합니다.
- 안전장치: 받은 숫자 외의 숫자, 병명·진단 표현이 나오면 그 글을 버리고 기본 문장으로 바꿉니다.
- 올라마가 꺼져 있어도 기본 문장(규칙 기반)으로 리포트가 나옵니다.
"""
import os
import re

import httpx

from .config import ACTIONS, PHRASES, STATE

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "exaone3.5:7.8b")
TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "120"))

BANNED = ["치매", "알츠하이머", "경도인지장애", "진단", "질환", "질병", "병원", "약을", "처방", "MCI", "센터"]
# 등급 C가 있을 때 프로그램이 직접 덧붙이는 안내 (언어모델이 쓰지 않음)
CENTER = "가까운 보건소(치매안심센터)에서 무료로 기억력 상담을 받으실 수 있어요."

SYSTEM = """너는 어르신 교통안전 교육 프로그램 '콤마인드'의 결과 설명 도우미다.
인사말은 프로그램이 먼저 붙이므로 너는 인사 없이 바로 본문부터 쓴다.
규칙:
1. 아래 [결과]에 있는 표현과 사실만 사용한다. 새로운 사실을 만들지 않는다.
2. 점수, 등급, 숫자를 말하지 않는다. 영역의 '상태' 문장을 그대로 쓴다. (생활 실천 안의 숫자는 그대로 써도 된다)
3. 병 이름, 진단, 약, 치료, 상담, 센터, 병원 이야기를 하지 않는다. 이것은 의학적 진단이 아닌 생활 점검이다.
4. 어르신이 읽기 쉽게 짧은 문장, 존댓말, 쉬운 낱말을 쓴다. 영어, 전문 용어, '어르신님' 같은 호칭을 쓰지 않는다.
5. 순서: 잘한 점 → 연습하면 좋은 점(있으면 하나만, 그대로) → 생활 실천 2가지.
6. '하지만', '그러나', '부족', '실수', '못하' 같은 말을 쓰지 않는다. 연습하면 좋은 점은 '그리고'나 '또'로 이어서 말한다.
7. 전체 3~5문장, 제목이나 목록 기호 없이 한 문단으로 쓴다."""

GREETING = "{name}, 오늘 교통안전 교육과 활동에 끝까지 함께해 주셔서 감사합니다."
# 말투 안전장치: 어르신께 부담이 되는 표현
TONE = ["하지만", "그러나", "부족", "실수", "못하", "나쁘", "떨어지", "등급", "점수", "어르신님", "이름하신"]


def facts(pred: dict, rules: dict | None = None, name: str = "어르신") -> dict:
    """리포트 재료. '_'로 시작하는 칸(점수·등급)은 언어모델에 보내지 않음"""
    f = {"이름": name, "영역": []}
    acts = list(ACTIONS["공통"])
    practice = []
    for key in ("attention", "memory"):
        p = pred.get(key)
        if not p:
            continue
        use = [d for d in p["factors"] if d["col"] in PHRASES and not d["missing"]]
        # 등급 C 영역에서는 그 영역의 세부 칭찬을 하지 않음 (점수와 칭찬이 어긋나 보이지 않게)
        good = [] if p["grade"] == "C" else [PHRASES[d["col"]][0] for d in use if d["contribution"] > 0.3][:2]
        weak = [PHRASES[d["col"]][1] for d in use if d["contribution"] < -0.3]
        if weak:
            practice.append((min(d["contribution"] for d in use), weak[0]))
        f["영역"].append({"이름": p["name"], "상태": f"{p['name']}은 {STATE[p['grade']]}", "잘한 점": good,
                         "_점수": p["score"], "_등급": p["grade"]})
        if p["grade"] != "A":
            acts = ACTIONS[p["name"]] + acts
    f["연습하면 좋은 점(하나)"] = min(practice)[1] if practice else ""
    f["권할 생활 실천(이 중에서 2가지)"] = acts[:6]
    if pred.get("brain_age"):
        diff = pred["brain_age"]["score"] - pred["brain_age"]["age"]
        f["두뇌 활동 나이"] = ("실제 나이와 비슷해요" if abs(diff) < 3 else
                         ("실제보다 조금 높게 나왔어요" if diff > 0 else "실제보다 젊게 나왔어요"))
        f["_뇌 나이"], f["_실제 나이"] = pred["brain_age"]["score"], pred["brain_age"]["age"]
    if rules:
        f["_참고 영역(검증 전)"] = rules
    return f


def llm_view(f):
    """언어모델에 보낼 재료: 점수·등급 등 '_' 칸 제거"""
    if isinstance(f, dict):
        return {k: llm_view(v) for k, v in f.items() if not k.startswith("_")}
    if isinstance(f, list):
        return [llm_view(x) for x in f]
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
    nums.update({1.0, 2.0})   # '2가지', '하루 1번' 같은 표현 허용
    return nums


def guard(text: str, f: dict) -> list:
    problems = []
    extra = sorted(n for n in _numbers(text) if n not in _allowed(llm_view(f)))
    if extra:
        problems.append(f"결과에 없는 숫자 {extra}")
    hit = [w for w in BANNED if w in text]
    if hit:
        problems.append(f"쓰면 안 되는 표현 {hit}")
    # 낱말 중간에 들어간 경우는 빼고 셈 (예: '연습하실수록'의 '실수')
    tone = [w for w in TONE if re.search(r"(?<![가-힣])" + w, text)]
    if tone:
        problems.append(f"말투 {tone}")
    if len(text) < 40:
        problems.append("너무 짧음")
    return problems


def template(f: dict) -> str:
    """올라마를 쓸 수 없거나 안전장치에 걸렸을 때 쓰는 기본 문장 (인사·센터 안내는 write()가 붙임)"""
    s = []
    for a in f["영역"]:
        s.append(a["상태"] + ".")
        if a["잘한 점"]:
            s.append(a["잘한 점"][0] + ".")
    if f.get("두뇌 활동 나이"):
        s.append("두뇌 활동 나이는 " + f["두뇌 활동 나이"] + ".")
    if f.get("연습하면 좋은 점(하나)"):
        s.append("그리고 " + f["연습하면 좋은 점(하나)"] + ".")
    acts = f.get("권할 생활 실천(이 중에서 2가지)", ["하루 30분 걷기", "가족·이웃과 자주 대화하기"])
    s.append(f"오늘부터 '{acts[0]}'와 '{acts[1]}'를 꾸준히 해 보세요.")
    return " ".join(s)


def _center(f):
    return (" " + CENTER) if any(a["_등급"] == "C" for a in f["영역"]) else ""


def ollama_ok() -> dict:
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        names = [m["name"] for m in r.json().get("models", [])]
        return {"running": True, "model": OLLAMA_MODEL, "installed": OLLAMA_MODEL in names, "models": names}
    except Exception as e:
        return {"running": False, "model": OLLAMA_MODEL, "installed": False, "error": type(e).__name__}


def write(f: dict) -> dict:
    """리포트 만들기. 결과: text, source(ollama/template), 안전장치 결과"""
    head = GREETING.format(name=f.get("이름", "어르신"))
    user = "[결과]\n" + str(llm_view(f)).replace("'", '"') + "\n\n위 결과로 어르신께 드릴 설명 본문을 써 주세요."
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=TIMEOUT, json={
            "model": OLLAMA_MODEL, "stream": False, "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]})
        r.raise_for_status()
        text = r.json()["message"]["content"].strip()
    except Exception as e:
        return {"text": head + " " + template(f) + _center(f), "source": "template", "model": None,
                "guard": [f"올라마 연결 안 됨 ({type(e).__name__})"]}
    problems = guard(text, f)
    if problems:
        return {"text": head + " " + template(f) + _center(f), "source": "template", "model": OLLAMA_MODEL,
                "guard": problems, "rejected": text}
    return {"text": head + " " + text + _center(f), "source": "ollama", "model": OLLAMA_MODEL, "guard": []}
