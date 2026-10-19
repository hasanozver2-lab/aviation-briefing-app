import json
import subprocess
from types import SimpleNamespace

import pytest

from scripts import connect_social


def setup_x(monkeypatch, tmp_path, *, code=0, output='[{"id":"123"}]'):
    script = tmp_path / "bird.js"
    script.touch()
    monkeypatch.setattr(connect_social, "BIRD_SCRIPT", script)
    monkeypatch.setattr(connect_social.shutil, "which", lambda name: "node")
    monkeypatch.setattr(connect_social.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    credentials = iter(("private-auth-example", "private-csrf-example"))
    monkeypatch.setattr(connect_social.getpass, "getpass", lambda prompt: next(credentials))
    calls, saved = [], {}

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=code, stdout=output, stderr="private-auth-example")

    monkeypatch.setattr(connect_social.subprocess, "run", run)
    monkeypatch.setattr(connect_social, "load_agent_config", lambda: SimpleNamespace(set=lambda key, value: saved.update({key: value})))
    return calls, saved


def test_x_session_is_hidden_and_only_passed_through_environment(monkeypatch, tmp_path, capsys):
    calls, saved = setup_x(monkeypatch, tmp_path)
    assert connect_social.connect_x() == 0
    command, arguments = calls[0]
    assert "private-auth-example" not in json.dumps(command)
    assert arguments["env"]["AUTH_TOKEN"] == "private-auth-example"
    assert arguments["env"]["CT0"] == "private-csrf-example"
    assert saved["twitter_auth_token"] == "private-auth-example"
    output = capsys.readouterr().out
    assert "private-auth-example" not in output and "private-csrf-example" not in output


@pytest.mark.parametrize("code,output", [(1, ""), (0, "invalid JSON"), (0, "[]"),
                                        (0, '{"error":"Expired session"}'), (0, '{"tweets":[]}')])
def test_failed_x_test_never_saves_or_prints_session(monkeypatch, tmp_path, capsys, code, output):
    calls, saved = setup_x(monkeypatch, tmp_path, code=code, output=output)
    assert connect_social.connect_x() == 1
    assert not saved and "private-auth-example" not in capsys.readouterr().out


def test_noninteractive_input_never_requests_cookies(monkeypatch, tmp_path):
    calls, saved = setup_x(monkeypatch, tmp_path)
    monkeypatch.setattr(connect_social.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    assert connect_social.connect_x() == 1
    assert not calls and not saved


def test_linkedin_login_never_auto_imports_browser_session():
    command = connect_social.linkedin_command("--no-auto-import", "--login")
    assert command[-2:] == ["--no-auto-import", "--login"]
    assert "--import-from-browser" not in command


def test_upstream_errors_do_not_leak_credentials(monkeypatch, capsys):
    def fail():
        raise subprocess.TimeoutExpired("private-session", 45)
    monkeypatch.setattr(connect_social, "connect_x", fail)
    assert connect_social.main(["x"]) == 1
    assert "private-session" not in capsys.readouterr().out
