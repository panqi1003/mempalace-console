import pytest

from server import config
from server.reader import ReadOnlyReader, ReaderToolError, ReaderUnavailable


def make_reader(hub=None, stdio=None, cli=None):
    calls = {"hub": 0, "stdio": 0}
    transports = {}

    def hub_fn(tool, args):
        calls["hub"] += 1
        if hub is None:
            raise OSError("hub down")
        return hub(tool, args)

    def stdio_fn(tool, args):
        calls["stdio"] += 1
        if stdio is None:
            raise OSError("stdio down")
        return stdio(tool, args)

    transports["hub"] = hub_fn
    transports["stdio"] = stdio_fn
    if cli is not None:
        transports["cli"] = cli
    return ReadOnlyReader(transports=transports), calls


def test_hub_used_when_available():
    reader, calls = make_reader(hub=lambda tool, args: {"ok": tool})
    assert reader.call("mempalace_status") == {"ok": "mempalace_status"}
    assert calls == {"hub": 1, "stdio": 0}
    assert reader.tier_status()["hub"] == "ok"


def test_falls_back_to_stdio_when_hub_fails():
    reader, calls = make_reader(stdio=lambda tool, args: {"ok": "stdio"})
    assert reader.call("mempalace_status") == {"ok": "stdio"}
    assert calls == {"hub": 1, "stdio": 1}
    assert reader.tier_status() == {"hub": "fail", "stdio": "ok", "cli": "untried"}


def test_raises_unavailable_when_all_fail():
    reader, _ = make_reader()
    with pytest.raises(ReaderUnavailable):
        reader.call("mempalace_status")


def test_write_tool_rejected_before_transport():
    reader, calls = make_reader(hub=lambda tool, args: {"ok": tool})
    with pytest.raises(config.ReadOnlyViolation):
        reader.call("mempalace_delete_drawer", {"id": "x"})
    assert calls == {"hub": 0, "stdio": 0}


def test_tool_error_propagates():
    def hub(tool, args):
        raise ReaderToolError(-32602, "Missing required parameter 'query'")

    reader, _ = make_reader(hub=hub)
    with pytest.raises(ReaderToolError) as ei:
        reader.call("mempalace_search", {})
    assert ei.value.code == -32602
