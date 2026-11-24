"""원시 기록(JSON) → 지표. 분석 코드(analysis/extract_features.py)를 그대로 불러 씀"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis"))
from extract_features import extract  # noqa: E402


def from_raw_bytes(data: bytes) -> dict:
    """앱이 드라이브에 저장한 원시 기록 파일 내용 → 지표 한 줄 + 화면 요약"""
    raw = json.loads(data.decode("utf-8"))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=True, encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
        f.flush()
        row = extract(f.name)
    summary = (raw.get("extra") or {}).get("summary") or {}
    return {"features": row, "summary": summary}
