"""i18n 单测：字典一致性、引用完整性、后端语言选择。

约定（与 web/js/i18n.js 的书写格式强耦合，格式变更需同步本文件）：
- 字典块形如 `\n  zh: {\n    "key": "value",\n  },`
- 值内不允许出现半角双引号（中文用「」，英文用 '），保证可按行解析
"""

from __future__ import annotations

import re
from pathlib import Path

from server import config as config_mod
from server.reader import ReadOnlyReader

WEB = Path(__file__).resolve().parents[1] / "web"
I18N_JS = WEB / "js" / "i18n.js"
KEY_LINE = re.compile(r'^\s*"([^"]+)":\s"(.*)",?$')
T_CALL = re.compile(r'\bt\(\s*"([\w.]+)"')
DATA_ATTR = re.compile(r'data-i18n(?:-placeholder|-title|-aria)?="([\w.]+)"')


def _parse_block(text: str, lang: str) -> dict[str, str]:
    m = re.search(rf"\n  {lang}: \{{\n(.*?)\n  \}},", text, re.S)
    assert m, f"i18n.js 缺少 {lang} 字典块"
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        km = KEY_LINE.match(line)
        if km:
            key = km.group(1)
            assert key not in out, f"{lang} 字典重复 key: {key}"
            out[key] = km.group(2)
    return out


def _load_dicts() -> tuple[dict[str, str], dict[str, str]]:
    assert I18N_JS.exists(), "web/js/i18n.js 尚未创建"
    text = I18N_JS.read_text(encoding="utf-8")
    return _parse_block(text, "zh"), _parse_block(text, "en")


def test_dicts_have_identical_keys():
    zh, en = _load_dicts()
    assert len(zh) >= 150, f"zh 字典过小（{len(zh)} 条），疑似未完成"
    assert set(zh) == set(en), f"zh/en key 不一致: {sorted(set(zh) ^ set(en))[:20]}"


def test_all_referenced_keys_exist():
    zh, _ = _load_dicts()
    refs: set[str] = set()
    files = [WEB / "index.html"] + [
        p for p in (WEB / "js").rglob("*.js") if "vendor" not in p.parts
    ]
    for p in files:
        text = p.read_text(encoding="utf-8")
        refs |= set(T_CALL.findall(text))
        refs |= set(DATA_ATTR.findall(text))
    missing = sorted(refs - set(zh))
    assert not missing, f"引用了未定义的 i18n key: {missing}"


class _Req:
    """最小 Request 替身：仅需 headers.get。"""

    def __init__(self, accept_language: str | None = None):
        self.headers: dict[str, str] = {}
        if accept_language is not None:
            self.headers["accept-language"] = accept_language


def test_lang_parsing():
    from server.app import _lang

    assert _lang(_Req()) == "zh"  # 缺省：与现有中文环境/测试兼容
    assert _lang(_Req("")) == "zh"
    assert _lang(_Req("zh-CN,zh;q=0.9,en;q=0.8")) == "zh"
    assert _lang(_Req("en-US,en;q=0.9")) == "en"
    assert _lang(_Req("ja-JP,ja;q=0.9")) == "en"


def test_palace_size_error_message_localized(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "PALACE", str(tmp_path / "empty_palace"))
    r = ReadOnlyReader()
    zh_err = r.palace_size(lang="zh")["error"]
    en_err = r.palace_size(lang="en")["error"]
    assert "未找到数据库文件" in zh_err
    assert not re.search(r"[\u4e00-\u9fff]", en_err), f"英文消息残留中文: {en_err}"
    assert "chroma.sqlite3" in en_err


def test_hub_log_unreadable_message_localized(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "HUB_LOG", str(tmp_path / "nope.log"))
    r = ReadOnlyReader()
    zh_txt = r.hub_log_tail(lang="zh")
    en_txt = r.hub_log_tail(lang="en")
    assert "不可读" in zh_txt
    assert not re.search(r"[\u4e00-\u9fff]", en_txt), f"英文消息残留中文: {en_txt}"
    assert "unreadable" in en_txt.lower()
