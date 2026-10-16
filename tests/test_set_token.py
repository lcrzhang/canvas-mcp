"""Tests for `tools/set_token.py`, the helper that replaces `CANVAS_TOKEN` in
the MCP client configs.

No network and no token: `urlopen` is replaced, so the Canvas answer is chosen
by the test, and every config written is a file under `tmp_path`. The real
configs are never named — `client_configs` is either patched out or called with
a patched `sys.platform`, so a bug here cannot overwrite a working setup.

The tokens below are obviously fake. A value shaped like a real Canvas token
would trip the fixture guard's token detector, and it has no business being in
the repository anyway.
"""

import importlib.util
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

OLD_TOKEN = "fake-old-token-for-tests"
NEW_TOKEN = "fake-new-token-for-tests"


def load_set_token() -> ModuleType:
    """`tools/` holds scripts, not a package, so the module is loaded by path.

    The script has to run before the venv exists, which is why it is not part
    of `canvas_mcp` and cannot simply be imported.
    """
    path = REPO_ROOT / "tools" / "set_token.py"
    spec = importlib.util.spec_from_file_location("set_token", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


set_token = load_set_token()


class FakeResponse:
    """What `urlopen` hands back: a context manager with `.read()`."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def canvas_answers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: int = 200,
    name: str = "Test Student",
) -> None:
    """Make `/users/self` answer `status`, without a network or a token."""

    def urlopen(
        request: urllib.request.Request,
        context: object = None,
        timeout: float | None = None,
    ) -> FakeResponse:
        if status != 200:
            raise urllib.error.HTTPError(request.full_url, status, "no", {}, None)
        return FakeResponse({"name": name})

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    # The TLS context is irrelevant once urlopen is faked, and building one
    # would depend on the certificate store of whatever machine runs the test.
    monkeypatch.setattr(set_token, "ssl_context", lambda: None)


def types_the_token(monkeypatch: pytest.MonkeyPatch, token: str = NEW_TOKEN) -> None:
    monkeypatch.setattr(set_token.getpass, "getpass", lambda prompt="": token)


def a_config() -> dict[str, Any]:
    """A client config shaped like a real one: the canvas entry is a small
    part of a file that belongs to the client, not to this project."""
    return {
        "numStartups": 42,
        "theme": "dark",
        "tipsHistory": {"new-user-warmup": 3, "shift-enter": 7},
        "mcpServers": {
            "weather": {
                "command": "npx",
                "args": ["-y", "weather-mcp"],
                "env": {"WEATHER_KEY": "fake-weather-key"},
            },
            "canvas": {
                "command": ".venv/Scripts/python.exe",
                "args": ["-m", "canvas_mcp.server"],
                "env": {
                    "CANVAS_TOKEN": OLD_TOKEN,
                    "SSL_CERT_FILE": "/etc/ssl/cert.pem",
                },
            },
        },
        "projects": {
            "E:\\mcp": {"allowedTools": [], "history": [{"display": "hello"}]}
        },
    }


def write_config(path: Path, config: dict[str, Any]) -> Path:
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def read_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def only_these_configs(monkeypatch: pytest.MonkeyPatch, *paths: Path) -> None:
    labels = [(f"Config {index}", path) for index, path in enumerate(paths, start=1)]
    monkeypatch.setattr(set_token, "client_configs", lambda: labels)


def test_a_rejected_token_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = write_config(tmp_path / "claude.json", a_config())
    before = config.read_bytes()
    canvas_answers(monkeypatch, status=401)
    types_the_token(monkeypatch)
    only_these_configs(monkeypatch, config)

    with pytest.raises(SystemExit) as excinfo:
        set_token.main()

    assert excinfo.value.code not in (0, None)
    assert config.read_bytes() == before
    assert not (tmp_path / "claude.json.bak").exists()


def test_the_rejection_names_the_three_things_that_cause_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 401 is the one failure a user will actually hit, and the three causes
    # are not guessable: the wrong institution, a truncated paste, an expired
    # token. Without them the message is as opaque as the one it replaces.
    canvas_answers(monkeypatch, status=401)

    with pytest.raises(SystemExit) as excinfo:
        set_token.check(NEW_TOKEN)

    message = str(excinfo.value.code)
    assert "Nothing was written" in message
    assert set_token.BASE_URL in message
    assert "whole value" in message
    assert "expiry" in message


def test_an_accepted_token_changes_only_canvas_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = write_config(tmp_path / "claude.json", a_config())
    canvas_answers(monkeypatch)
    types_the_token(monkeypatch)
    only_these_configs(monkeypatch, config)

    set_token.main()

    expected = a_config()
    expected["mcpServers"]["canvas"]["env"]["CANVAS_TOKEN"] = NEW_TOKEN
    assert read_config(config) == expected


def test_the_token_is_never_printed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path / "claude.json", a_config())
    canvas_answers(monkeypatch)
    types_the_token(monkeypatch)
    only_these_configs(monkeypatch, config)

    set_token.main()

    captured = capsys.readouterr()
    assert NEW_TOKEN not in captured.out + captured.err


def test_the_previous_config_is_kept_as_a_bak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = write_config(tmp_path / "claude.json", a_config())
    canvas_answers(monkeypatch)
    types_the_token(monkeypatch)
    only_these_configs(monkeypatch, config)

    set_token.main()

    backup = tmp_path / "claude.json.bak"
    assert backup.exists()
    # The backup holds what was there before, which is what makes it a backup
    # rather than a second copy of the new file.
    assert read_config(backup) == a_config()


def test_a_config_without_a_canvas_entry_is_left_alone(tmp_path: Path) -> None:
    other = {"mcpServers": {"weather": {"command": "npx"}}}
    config = write_config(tmp_path / "claude.json", other)

    result = set_token.write(config, NEW_TOKEN)

    assert "skipped" in result
    # Not created: a config without the server registered is a config this
    # script has nothing to say about, and inventing an entry would produce a
    # half-registered server that fails in a different, stranger way.
    assert read_config(config) == other
    assert not (tmp_path / "claude.json.bak").exists()


def test_a_missing_config_file_is_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    present = write_config(tmp_path / "present.json", a_config())
    absent = tmp_path / "absent.json"
    canvas_answers(monkeypatch)
    types_the_token(monkeypatch)
    only_these_configs(monkeypatch, absent, present)

    set_token.main()

    assert not absent.exists()
    assert read_config(present)["mcpServers"]["canvas"]["env"]["CANVAS_TOKEN"] == (
        NEW_TOKEN
    )


def test_no_config_with_a_canvas_entry_is_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Exiting zero here would tell someone whose server is not registered that
    # their token was rotated, and the next failure would look like a bad token.
    config = write_config(tmp_path / "claude.json", {"mcpServers": {}})
    canvas_answers(monkeypatch)
    types_the_token(monkeypatch)
    only_these_configs(monkeypatch, config)

    with pytest.raises(SystemExit) as excinfo:
        set_token.main()

    assert excinfo.value.code not in (0, None)


def test_an_empty_token_is_not_checked_against_canvas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    types_the_token(monkeypatch, token="   ")
    monkeypatch.setattr(
        set_token, "check", lambda token: pytest.fail("Canvas was called")
    )

    with pytest.raises(SystemExit) as excinfo:
        set_token.main()

    assert "Nothing was written" in str(excinfo.value.code)


def test_windows_looks_in_appdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

    configs = dict(set_token.client_configs())

    assert configs["Claude Desktop"] == (
        tmp_path / "Roaming" / "Claude" / "claude_desktop_config.json"
    )
    assert configs["Claude Code"] == Path.home() / ".claude.json"


def test_macos_looks_in_application_support(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    configs = dict(set_token.client_configs())

    assert configs["Claude Desktop"] == (
        Path.home()
        / "Library"
        / "Application Support"
        / "Claude"
        / "claude_desktop_config.json"
    )
    assert configs["Claude Code"] == Path.home() / ".claude.json"


def test_elsewhere_looks_in_dot_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    configs = dict(set_token.client_configs())

    assert configs["Claude Desktop"] == (
        Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    )
    assert configs["Claude Code"] == Path.home() / ".claude.json"


def test_an_ssl_cert_file_that_is_gone_is_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Python reads SSL_CERT_FILE unconditionally. A stale user-level value --
    # a CA bundle from a tool that has since been uninstalled -- makes every
    # HTTPS call die with a FileNotFoundError that names no variable, which is
    # exactly the opaque failure this script exists to avoid.
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "gone.pem"))

    assert set_token.ssl_context() is not None
    assert "SSL_CERT_FILE" not in set_token.os.environ
