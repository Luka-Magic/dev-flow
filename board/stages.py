"""段階の名前と順番(記録・合成・画面で共有する)。"""
from __future__ import annotations

# dev-flow の 8 段階。前後に「未着手」「完了」が付く
STAGES: tuple[tuple[str, str], ...] = (
    ("plan", "計画"),
    ("spec", "仕様"),
    ("ticket", "チケット"),
    ("test_review", "テストレビュー"),
    ("ui_check", "UI 確認"),
    ("briefing", "実装前の説明"),
    ("implement", "実装"),
    ("review", "レビュー"),
)
TODO = "todo"
DONE = "done"
LABELS: dict[str, str] = {TODO: "未着手", **dict(STAGES), DONE: "完了"}
ORDER: dict[str, int] = {key: i for i, key in enumerate(LABELS)}  # todo=0, plan=1 … review=8, done=9

# CLI で受け付ける別名(日本語の名前、空白・ハイフンの違い)
_ALIASES: dict[str, str] = {}
for _key, _label in LABELS.items():
    _ALIASES[_key] = _key
    _ALIASES[_key.replace("_", "-")] = _key
    _ALIASES[_label] = _key
    _ALIASES[_label.replace(" ", "")] = _key
_ALIASES.update({"ui": "ui_check", "test": "test_review", "impl": "implement", "pr": "review"})


def normalize(name: str) -> str:
    """段階の名前を正規のキーにする。知らない名前は ValueError。"""
    key = _ALIASES.get(name.strip()) or _ALIASES.get(name.strip().lower())
    if key is None:
        choices = " / ".join(LABELS)
        raise ValueError(f"知らない段階: {name!r}(使えるもの: {choices})")
    return key


def from_grill_kind(kind: str | None) -> str | None:
    """質問票の種類から、その質問票が属する段階を推す。分からなければ None。"""
    if not kind:
        return None
    k = kind.lower()
    table = (
        (("実装前", "brief", "説明"), "briefing"),
        (("ui",), "ui_check"),
        (("test", "テスト", "ルール"), "test_review"),
        (("仕様", "spec"), "spec"),
        (("計画", "plan"), "plan"),
        (("pr",), "review"),
    )
    for words, stage in table:
        if any(w in k for w in words):
            return stage
    return None
