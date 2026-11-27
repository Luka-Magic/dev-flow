"""使用量(コンテキスト使用率と利用枠)の読み方(純粋関数)。

入力は statusline_tee.py が書き出したファイルの中身:
  {"written_at": エポック秒, "session_id", "context_window": {"used_percentage", "context_window_size"},
   "rate_limits": {"five_hour": {"used_percentage", "resets_at"}, "seven_day": {...}}, "model", "cwd"}
"""
from __future__ import annotations

import time
from datetime import datetime

WEEKDAYS = "月火水木金土日"
LIMIT_KEYS = ("five_hour", "seven_day")


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _written(doc: dict) -> float:
    return _num(doc.get("written_at")) or 0.0


def age_minutes(doc: dict, now: float) -> int:
    return max(0, int((now - _written(doc)) // 60))


def latest_by_session(usage: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for doc in usage:
        sid = doc.get("session_id")
        if isinstance(sid, str) and sid and (sid not in out or _written(doc) > _written(out[sid])):
            out[sid] = doc
    return out


def context_of(doc: dict | None, now: float) -> dict | None:
    """R10: セッションのコンテキスト使用率と、何分前の値か。"""
    if not doc:
        return None
    pct = _num((doc.get("context_window") or {}).get("used_percentage"))
    if pct is None:
        return None
    return {"pct": int(round(pct)), "age_min": age_minutes(doc, now)}


def _epoch(value: object) -> float | None:
    n = _num(value)
    if n is not None:
        return n / 1000 if n > 1e12 else n
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def resets_text(value: object, now: float) -> str:
    """戻る時刻を短く(24 時間以内なら 03:10、それより先なら 火 09:00)。"""
    ts = _epoch(value)
    if ts is None:
        return ""
    lt = time.localtime(ts)
    hm = time.strftime("%H:%M", lt)
    return hm if ts - now < 86400 else f"{WEEKDAYS[lt.tm_wday]} {hm}"


def limits(usage: list[dict], now: float) -> dict | None:
    """R10: 利用枠は最も新しい書き出しの値を使う(終了したセッションの書き出しでもよい)。"""
    with_limits = [d for d in usage if isinstance(d.get("rate_limits"), dict)]
    if not with_limits:
        return None
    doc = max(with_limits, key=_written)
    out: dict = {"age_min": age_minutes(doc, now)}
    for key in LIMIT_KEYS:
        part = doc["rate_limits"].get(key)
        pct = _num(part.get("used_percentage")) if isinstance(part, dict) else None
        out[key] = None if pct is None else {
            "pct": int(round(pct)),
            "resets_at": part.get("resets_at"),
            "resets_text": resets_text(part.get("resets_at"), now),
        }
    return out
