from server import config as config_mod
from server.reader import ReadOnlyReader


def recorder(payload=None):
    calls = []

    def hub(tool, args):
        calls.append((tool, args))
        return payload if payload is not None else {"tool": tool}

    reader = ReadOnlyReader(transports={"hub": hub})
    return reader, calls


def test_drawers_omits_none_filters():
    reader, calls = recorder()
    reader.drawers(wing="demo_wing", limit=5)
    assert calls == [
        ("mempalace_list_drawers", {"wing": "demo_wing", "offset": 0, "limit": 5})
    ]


def test_drawer_by_id_passes_id():
    reader, calls = recorder()
    reader.drawer("drawer_x")
    assert calls == [("mempalace_get_drawer", {"drawer_id": "drawer_x"})]


def test_search_minimal_args():
    reader, calls = recorder()
    reader.search("hello")
    assert calls == [("mempalace_search", {"query": "hello", "limit": 10})]


def test_kg_and_graph_methods():
    reader, calls = recorder()
    reader.kg_query("demo_wing")
    reader.kg_timeline()
    reader.find_tunnels("demo_wing", "mempalace")
    reader.traverse("diary", 3)
    assert calls == [
        ("mempalace_kg_query", {"entity": "demo_wing"}),
        ("mempalace_kg_timeline", {}),
        ("mempalace_find_tunnels", {"wing_a": "demo_wing", "wing_b": "mempalace"}),
        ("mempalace_traverse", {"start_room": "diary", "max_hops": 3}),
    ]


def test_diary_and_events():
    reader, calls = recorder()
    reader.diary("demo_agent", last_n=5)
    reader.events(limit=10)
    assert calls == [
        ("mempalace_diary_read", {"agent_name": "demo_agent", "last_n": 5}),
        ("mempalace_event_list", {"limit": 10}),
    ]


def test_taxonomy_unwraps_310_envelope():
    """mempalace 3.10 的 get_taxonomy 返回 {"taxonomy": {wing: {room: n}}}，需归一化为平铺。"""
    fake = {"taxonomy": {"demo_wing": {"diary": 3}}}
    r = ReadOnlyReader(transports={"hub": lambda t, a: fake})
    assert r.taxonomy() == {"demo_wing": {"diary": 3}}


def test_taxonomy_legacy_flat_passthrough():
    """3.7.x 直接返回平铺 {wing: {room: n}}，保持兼容。"""
    fake = {"alpha": {"technical": 5}}
    r = ReadOnlyReader(transports={"hub": lambda t, a: fake})
    assert r.taxonomy() == {"alpha": {"technical": 5}}


def test_backups_lists_files(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    (backup_dir / "chroma_1.sqlite3").write_bytes(b"x" * 10)
    monkeypatch.setattr(config_mod, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(config_mod, "PALACE", str(tmp_path / "nonexistent_palace"))
    r = ReadOnlyReader(transports={"hub": lambda t, a: {}})
    items = r.backups()
    assert len(items) == 1
    assert items[0]["name"] == "chroma_1.sqlite3"
    assert items[0]["size_bytes"] == 10
    assert items[0]["source"] == "custom"


def test_backups_discovers_official_locations(tmp_path, monkeypatch):
    """官方备份自动发现：宫殿旁 <palace>.backup 目录 + 宫内 max-seq-id 文件。"""
    palace = tmp_path / "mypalace"
    palace.mkdir()
    # 官方目录级备份（repair/migrate 生成）
    dir_backup = tmp_path / "mypalace.backup"
    dir_backup.mkdir()
    (dir_backup / "chroma.sqlite3").write_bytes(b"y" * 20)
    # 官方 max-seq-id 文件备份
    (palace / "chroma.sqlite3.max-seq-id-backup-20260901T120000").write_bytes(b"z" * 5)

    monkeypatch.setattr(config_mod, "BACKUP_DIR", None)
    monkeypatch.setattr(config_mod, "PALACE", str(palace))
    r = ReadOnlyReader(transports={"hub": lambda t, a: {}})
    items = r.backups()
    sources = {i["source"] for i in items}
    names = {i["name"] for i in items}
    assert sources == {"official-dir", "official-file"}
    assert "mypalace.backup" in names
    assert "chroma.sqlite3.max-seq-id-backup-20260901T120000" in names


def test_activity_buckets_by_day_and_wing():
    from datetime import date, timedelta

    today = date.today()
    d_recent = (today - timedelta(days=1)).isoformat()
    d_prev = (today - timedelta(days=2)).isoformat()
    d_old = (today - timedelta(days=40)).isoformat()

    def md(wing, filed_at, room=None):
        return {"wing": wing, "room": room, "metadata": {"filed_at": filed_at}}

    pages = [
        md("demo_wing", f"{d_recent}T10:00:00", "diary"),
        md("demo_wing", f"{d_recent}T11:00:00"),
        md("alpha", f"{d_prev}T09:00:00", "lessons"),
        md(None, f"{d_old}T00:00:00"),  # 超出 30 天窗口，不计
    ]

    def hub(tool, args):
        if tool != "mempalace_list_drawers":
            return {"tool": tool}
        if args.get("offset", 0) == 0:
            return {"drawers": pages, "total": 4}
        return {"drawers": [], "total": 4}

    r = ReadOnlyReader(transports={"hub": hub})
    out = r.activity(days=30)
    assert out["per_day"][d_recent]["demo_wing"] == 2
    assert out["per_day"][d_prev]["alpha"] == 1
    assert d_old not in out["per_day"]
    assert out["last_by_room"]["diary"] == f"{d_recent}T10:00:00"


def test_audit_counts_anomalies():
    drawers = [
        {
            "drawer_id": "a",
            "wing": "demo_wing",
            "room": "diary",
            "content_preview": "x",
            "metadata": {"ingest_mode": "manual", "source_file": "f"},
        },
        {
            "drawer_id": "b",
            "wing": None,
            "content_preview": "",
            "metadata": {"ingest_mode": "convos"},
        },
        {
            "drawer_id": "c",
            "wing": "unknown",
            "content_preview": "y",
            "metadata": {"ingest_mode": "convos", "source_file": "g"},
        },
    ]

    def hub(tool, args):
        if tool == "mempalace_list_drawers":
            return {"drawers": drawers, "total": 3}
        if tool == "mempalace_kg_stats":
            return {"entities": 1, "triples": 0, "current_facts": 0, "expired_facts": 1}
        return {"tool": tool}

    r = ReadOnlyReader(transports={"hub": hub})
    out = r.audit(sample_size=0)
    assert out["total"] == 3
    assert out["no_wing"] == 1
    assert out["unknown_wing"] == 1
    assert out["empty_preview"] == 1
    assert out["by_ingest"] == {"manual": 1, "convos": 2}
    assert out["kg"]["expired"] == 1


def test_audit_splits_missing_source_by_ingest():
    """缺 source_file 按 ingest_mode 拆分：mined 缺源=真问题，精选缺源=正常。"""
    drawers = [
        {
            "drawer_id": "curated1",
            "wing": "w",
            "room": "diary",
            "content_preview": "c",
            "metadata": {"ingest_mode": "manual"},
        },
        {
            "drawer_id": "mined1",
            "wing": "w",
            "room": "technical",
            "content_preview": "m",
            "metadata": {"ingest_mode": "convos"},
        },
        {
            "drawer_id": "mined2",
            "wing": "w",
            "room": "technical",
            "content_preview": "m2",
            "metadata": {"ingest_mode": "project", "source_file": "ok.txt"},
        },
    ]

    def hub(tool, args):
        if tool == "mempalace_list_drawers":
            return {"drawers": drawers, "total": 3}
        if tool == "mempalace_kg_stats":
            return {"current_facts": 1, "expired_facts": 0}
        return {"tool": tool}

    r = ReadOnlyReader(transports={"hub": hub})
    out = r.audit(sample_size=0)
    assert out["no_source"] == 2  # curated1 + mined1
    assert out["no_source_mined"] == 1  # 仅 mined1 属真问题
    assert out["no_source_curated"] == 1  # curated1 属正常


def test_audit_issue_samples_and_elapsed():
    """问题样本可按类追溯（点击查看），并带扫描耗时。"""
    drawers = [
        {
            "drawer_id": "bad1",
            "wing": None,
            "room": None,
            "content_preview": "",
            "metadata": {"ingest_mode": "convos"},
        },
        {
            "drawer_id": "dup1",
            "wing": "w",
            "room": "r",
            "content_preview": "same-preview",
            "metadata": {"ingest_mode": "manual", "source_file": "s"},
        },
        {
            "drawer_id": "dup2",
            "wing": "w",
            "room": "r",
            "content_preview": "same-preview",
            "metadata": {"ingest_mode": "manual", "source_file": "s"},
        },
    ]

    def hub(tool, args):
        if tool == "mempalace_list_drawers":
            return {"drawers": drawers, "total": 3}
        if tool == "mempalace_kg_stats":
            return {"current_facts": 1, "expired_facts": 0}
        return {"tool": tool}

    r = ReadOnlyReader(transports={"hub": hub})
    out = r.audit(sample_size=0)
    assert out["issue_samples"]["no_wing"] == ["bad1"]
    assert out["issue_samples"]["empty_preview"] == ["bad1"]
    assert out["issue_samples"]["dup_pairs"] == [{"a": "dup1", "b": "dup2"}]
    assert isinstance(out["elapsed_s"], (int, float))
    assert out["elapsed_s"] >= 0


def test_wakeup_uses_cli_with_wing():
    r = ReadOnlyReader(
        transports={
            "hub": lambda t, a: (_ for _ in ()).throw(OSError("down")),
            "cli": lambda argv: " ".join(argv),
        }
    )
    text = r.wakeup("demo_wing")
    assert "--wing" in text and "demo_wing" in text


def test_palace_size_stats(tmp_path, monkeypatch):
    db = tmp_path / "chroma.sqlite3"
    db.write_bytes(b"z" * 7)
    monkeypatch.setattr(config_mod, "PALACE", str(tmp_path))
    r = ReadOnlyReader()
    out = r.palace_size()
    assert out["size_bytes"] == 7
    assert out["path"].endswith("chroma.sqlite3")


def test_palace_size_handles_sqlite_exact_backend(tmp_path, monkeypatch):
    """3.10 的 sqlite_exact 后端数据文件不是 chroma.sqlite3，大小卡片需兼容。"""
    db = tmp_path / "sqlite_exact.sqlite3"
    db.write_bytes(b"e" * 9)
    monkeypatch.setattr(config_mod, "PALACE", str(tmp_path))
    r = ReadOnlyReader()
    out = r.palace_size()
    assert out["size_bytes"] == 9
    assert out["path"].endswith("sqlite_exact.sqlite3")


def test_activity_returns_logical_scan_totals():
    """activity 顺带返回逻辑条目总数与 wing/room 分布（总览统一口径用）。

    逻辑条目 = list_drawers 折叠分块后的条数；含窗口外与无日期条目。
    """
    from datetime import date, timedelta

    recent = (date.today() - timedelta(days=1)).isoformat()
    old = (date.today() - timedelta(days=40)).isoformat()
    pages = [
        {"wing": "w1", "room": "diary", "metadata": {"filed_at": f"{recent}T10:00:00"}},
        {"wing": "w1", "room": "lessons", "metadata": {"filed_at": f"{recent}T11:00:00"}},
        {"wing": "w2", "room": "diary", "metadata": {"filed_at": f"{old}T10:00:00"}},
        {"wing": None, "room": None, "metadata": {}},
    ]

    def hub(tool, args):
        if tool != "mempalace_list_drawers":
            return {"tool": tool}
        if args.get("offset", 0) == 0:
            return {"drawers": pages, "total": 4}
        return {"drawers": [], "total": 4}

    r = ReadOnlyReader(transports={"hub": hub})
    out = r.activity(days=7)
    assert out["scan_total"] == 4
    assert out["by_wing"] == {"w1": 2, "w2": 1, "unknown": 1}
    assert out["by_room"] == {"diary": 2, "lessons": 1, "unknown": 1}
