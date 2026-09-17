import hashlib
import os
from pathlib import Path

import pytest

from server import config


def test_whitelist_contains_core_read_tools():
    for name in [
        "mempalace_status",
        "mempalace_list_drawers",
        "mempalace_get_drawer",
        "mempalace_search",
        "mempalace_kg_query",
        "mempalace_kg_stats",
        "mempalace_kg_timeline",
        "mempalace_get_taxonomy",
        "mempalace_traverse",
        "mempalace_diary_read",
        "mempalace_event_list",
        "mempalace_artifact_get",
    ]:
        assert name in config.READONLY_TOOLS


def test_write_tools_are_rejected():
    for name in [
        "mempalace_add_drawer",
        "mempalace_delete_drawer",
        "mempalace_update_drawer",
        "mempalace_mine",
        "mempalace_sync",
        "mempalace_diary_write",
        "mempalace_kg_add",
        "mempalace_kg_supersede",
        "mempalace_kg_invalidate",
        "mempalace_compress",
        "mempalace_event_append",
        "mempalace_artifact_put",
    ]:
        with pytest.raises(config.ReadOnlyViolation):
            config.assert_readonly(name)


def test_unknown_tool_is_rejected():
    with pytest.raises(config.ReadOnlyViolation):
        config.assert_readonly("mempalace_not_a_tool")


def test_hub_state_dir_matches_official_algorithm(tmp_path):
    palace = str(tmp_path / "palace")
    key = hashlib.sha256(
        os.path.normcase(os.path.realpath(os.path.abspath(palace))).encode("utf-8")
    ).hexdigest()[:24]
    assert config.hub_state_dir(palace) == Path.home() / ".mempalace" / "server" / key


def test_discover_hub_reads_serverinfo_and_token(tmp_path, monkeypatch):
    palace = str(tmp_path / "palace")
    state = tmp_path / "state"
    monkeypatch.setattr(config, "hub_state_dir", lambda p: state)
    monkeypatch.setattr(config, "_pid_alive", lambda pid: True)
    state.mkdir(parents=True)
    (state / "serverinfo.json").write_text(
        '{"palace_path": "%s", "host": "127.0.0.1", "port": 8765, "scheme": "http", "pid": 1}'
        % palace.replace("\\", "\\\\"),
        encoding="utf-8",
    )
    (state / "token").write_text("secret", encoding="utf-8")
    result = config.discover_hub(palace)
    assert result is not None
    base_url, headers = result
    assert base_url == "http://127.0.0.1:8765"
    assert headers["Authorization"] == "Bearer secret"


def test_discover_hub_returns_none_without_serverinfo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "hub_state_dir", lambda p: tmp_path / "nope")
    assert config.discover_hub("X:/any") is None


def test_default_palace_precedence(tmp_path, monkeypatch):
    home = tmp_path
    monkeypatch.delenv("MEMPALACE_PALACE", raising=False)
    monkeypatch.delenv("MEMPALACE_PALACE_PATH", raising=False)
    # 1) 无任何配置 → 默认 ~/.mempalace/palace
    assert config.default_palace(home) == str(home / ".mempalace" / "palace")
    # 2) config.json 的 palace_path 生效
    dotm = home / ".mempalace"
    dotm.mkdir()
    (dotm / "config.json").write_text(
        '{"palace_path": "%s"}' % str(tmp_path / "from_cfg").replace("\\", "\\\\"),
        encoding="utf-8",
    )
    assert config.default_palace(home) == str(tmp_path / "from_cfg")
    # 3) 环境变量最优先
    monkeypatch.setenv("MEMPALACE_PALACE", str(tmp_path / "env"))
    assert config.default_palace(home) == str(tmp_path / "env")


def test_find_exe_env_override_and_missing(tmp_path, monkeypatch):
    real = tmp_path / "real.exe"
    real.write_bytes(b"")
    monkeypatch.setenv("MEMPALACE_EXE", str(real))
    # 环境变量指向存在的文件 → 直接用（不依赖 which）
    assert config.find_exe(["definitely-not-a-tool"], "MEMPALACE_EXE") == str(real)
    # 环境变量缺失且 which 找不到 → None
    monkeypatch.delenv("MEMPALACE_EXE", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert config.find_exe(["definitely-not-a-tool"], "MEMPALACE_EXE") is None


def test_optional_viz_config_file(monkeypatch, tmp_path):
    exe = tmp_path / "fake-mempalace.exe"
    exe.write_bytes(b"")
    cfg = tmp_path / "mempalace_viz.json"
    cfg.write_text(
        '{"hub_log": "H:/hub.log", "backup_dir": "B:/backup", "port": 9001, '
        '"mempalace_exe": "%s"}' % str(exe).replace("\\", "\\\\"),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "VIZ_CONFIG_CANDIDATES", [cfg])
    s = config.load_settings()
    assert s["hub_log"] == "H:/hub.log"
    assert s["backup_dir"] == "B:/backup"
    assert s["port"] == 9001
    assert s["mempalace_exe"] == str(exe)
