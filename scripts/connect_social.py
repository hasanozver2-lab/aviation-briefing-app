"""Local Agent Reach setup. Never imports browser cookies automatically or publishes credentials."""

import argparse
import getpass
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


TOOL_HOME = Path(os.environ.get("AGENT_REACH_HOME", str(Path.home() / ".agent-reach")))
NODE_TOOLS = TOOL_HOME / "tools" / "social-node" / "node_modules"
LINKEDIN_PACKAGES = TOOL_HOME / "tools" / "linkedin-python"
BIRD_SCRIPT = NODE_TOOLS / "@steipete" / "bird" / "dist" / "cli.js"
MCPORTER_SCRIPT = NODE_TOOLS / "mcporter" / "dist" / "cli.js"
CONNECT_TIMEOUT_SECONDS = 45
MAX_COOKIE_LENGTH = 2048


def status():
    print("X reader:", "installed" if BIRD_SCRIPT.is_file() else "missing")
    print("MCP connector:", "installed" if MCPORTER_SCRIPT.is_file() else "missing")
    installed = any(LINKEDIN_PACKAGES.glob("mcp_server_linkedin-*.dist-info"))
    print("LinkedIn reader:", "installed" if installed else "missing")
    print("Installation is not proof of authenticated access. Social collection is not enabled yet.")
    return 0


def read_cookie(label):
    value = getpass.getpass(label + " (hidden): ").strip()
    if not value or len(value) > MAX_COOKIE_LENGTH or any(character.isspace() for character in value):
        raise ValueError("Invalid cookie value. Enter only the value, not the whole browser cookie export.")
    return value


def load_agent_config():
    # Agent Reach is already installed in the base interpreter, not the project's shared venv.
    package_root = Path(sys.base_prefix) / "Lib" / "site-packages"
    sys.path.append(str(package_root))
    module = importlib.import_module("agent_reach.config")
    return module.Config()


def connect_x():
    if not BIRD_SCRIPT.is_file() or not shutil.which("node"):
        print("X reader is not installed.")
        return 1
    if not sys.stdin.isatty():
        print("Open this helper in a local terminal. Session values will never be accepted through chat or command arguments.")
        return 1
    print("Sign in to X in your browser. Enter only auth_token and ct0 from your own session.")
    print("These grant account access. Prefer a dedicated account; automation can cause account restrictions.")
    auth_token, ct0 = read_cookie("auth_token"), read_cookie("ct0")
    environment = {**os.environ, "AUTH_TOKEN": auth_token, "CT0": ct0, "NODE_USE_SYSTEM_CA": "1"}
    # Supplying both values bypasses browser-cookie discovery; nothing sensitive is put in argv.
    result = subprocess.run([shutil.which("node"), str(BIRD_SCRIPT), "--timeout", "20000",
                             "user-tweets", "Delta", "-n", "1", "--json"],
                            cwd=TOOL_HOME, env=environment, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=CONNECT_TIMEOUT_SECONDS)
    if result.returncode:
        print("X access failed. Nothing was saved; check your session and account access.")
        return 1
    try:
        posts = json.loads(result.stdout)
    except (ValueError, TypeError):
        print("X returned an unreadable response. Nothing was saved.")
        return 1
    entries = posts if isinstance(posts, list) else posts.get("tweets", []) if isinstance(posts, dict) else []
    if not isinstance(entries, list) or not any(isinstance(post, dict) and post.get("id") for post in entries):
        print("X returned no usable result. Nothing was saved.")
        return 1
    config = load_agent_config()
    config.set("twitter_auth_token", auth_token)
    config.set("twitter_ct0", ct0)
    print("X access tested. Session saved locally under Agent Reach; no values were printed or sent to GitHub.")
    return 0


def linkedin_command(*arguments):
    bootstrap = (
        "import sys,site,importlib.metadata; "
        "package_root=sys.argv.pop(1); sys.path.insert(0,package_root); site.addsitedir(package_root); "
        "entry=next(e for e in importlib.metadata.distribution('mcp-server-linkedin').entry_points "
        "if e.group=='console_scripts' and e.name=='mcp-server-linkedin'); entry.load()()"
    )
    return [sys.executable, "-c", bootstrap, str(LINKEDIN_PACKAGES), *arguments]


def connect_linkedin():
    if not any(LINKEDIN_PACKAGES.glob("mcp_server_linkedin-*.dist-info")):
        print("LinkedIn reader is not installed.")
        return 1
    print("A dedicated LinkedIn sign-in browser will open. Enter credentials there, never in chat.")
    return subprocess.run(linkedin_command("--no-auto-import", "--login"), cwd=TOOL_HOME).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("status", "x", "linkedin"))
    action = parser.parse_args(argv).action
    if action is None:
        print("AeroBrief social connection: 1 = X, 2 = LinkedIn, 3 = installation status")
        action = {"1": "x", "2": "linkedin", "3": "status"}.get(input("Choose: ").strip())
        if action is None:
            print("No connection selected.")
            return 1
    try:
        return {"status": status, "x": connect_x, "linkedin": connect_linkedin}[action]()
    except (EOFError, KeyboardInterrupt):
        print("Connection cancelled.")
        return 1
    except (OSError, ValueError, ImportError, subprocess.TimeoutExpired) as exc:
        # Upstream exceptions and subprocess output may include session values: show only the error type.
        print("Connection could not finish:", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
