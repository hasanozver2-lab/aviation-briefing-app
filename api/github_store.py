"""Briefing storage on a dedicated git branch (default: briefing-data).

The scheduled pipeline commits daily.json / hourly.json / status files to that branch in
ONE commit and never touches main. The read-only API fetches the files from
raw.githubusercontent.com, so the repository must be public.

Publishing uses git plumbing (temporary index, commit-tree, push of a single ref), so the
checked-out branch and working tree are never modified.
"""

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


RAW_HOST = "https://raw.githubusercontent.com"
DEFAULT_REPO = "hasanozver2-lab/aviation-briefing-app"
DEFAULT_BRANCH = "briefing-data"
DEFAULT_REMOTE = "origin"
BOT_NAME = "aerobrief-bot"
BOT_EMAIL = "aerobrief-bot@users.noreply.github.com"
# The data branch carries its own Vercel config so a push to it never starts a deployment,
# whichever vercel.json Vercel reads for that commit.
VERCEL_CONFIG_PATH = "vercel.json"
VERCEL_CONFIG = {"version": 2, "git": {"deploymentEnabled": {DEFAULT_BRANCH: False}}}
FILE_MODE = "100644"


def _env_value(name):
    return os.environ.get(name, "").strip()


def repo_slug():
    configured = _env_value("BRIEFING_DATA_REPO")
    if configured:
        return configured
    owner, name = _env_value("VERCEL_GIT_REPO_OWNER"), _env_value("VERCEL_GIT_REPO_SLUG")
    return f"{owner}/{name}" if owner and name else DEFAULT_REPO


def data_branch():
    return _env_value("BRIEFING_DATA_BRANCH") or DEFAULT_BRANCH


def _safe_path(pathname):
    normalized = str(pathname or "").strip().lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        raise ValueError("invalid store pathname")
    return normalized


def public_url(pathname):
    return f"{RAW_HOST}/{repo_slug()}/{urllib.parse.quote(data_branch(), safe='/')}/{urllib.parse.quote(_safe_path(pathname), safe='/')}"


def get_public_json(pathname, timeout=8):
    """Read one JSON file from the data branch; any failure returns None (caller falls back)."""
    request = urllib.request.Request(public_url(pathname), headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def _git(args, repo_dir, env=None, input_bytes=None, check=True):
    result = subprocess.run(
        ["git", *args], cwd=repo_dir, env=env, input=input_bytes, capture_output=True, timeout=120,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.decode('utf-8', errors='replace').strip()[:300]}")
    return result


def _serialize(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def read_branch_json(pathname, repo_dir=None, remote=DEFAULT_REMOTE, branch=None):
    """Read one JSON file from the remote data branch via git (None when branch or file is missing)."""
    branch = branch or data_branch()
    repo_dir = str(repo_dir or Path(__file__).resolve().parent.parent)
    tracking_ref = f"refs/remotes/{remote}/{branch}"
    fetched = _git(["fetch", "--quiet", remote, f"+refs/heads/{branch}:{tracking_ref}"], repo_dir, check=False)
    if fetched.returncode != 0:
        return None
    shown = _git(["show", f"{tracking_ref}:{_safe_path(pathname)}"], repo_dir, check=False)
    if shown.returncode != 0:
        return None
    try:
        return json.loads(shown.stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def publish_files(files, message, repo_dir=None, remote=DEFAULT_REMOTE, branch=None, remove=()):
    """Commit {pathname: json_payload} to the data branch in a single commit and push it.

    Existing files that are not replaced stay in the tree; paths in `remove` are deleted from it.
    Returns the new commit id, or ""
    when nothing changed. Only refs/heads/<branch> is pushed; main is never written.
    """
    branch = branch or data_branch()
    repo_dir = str(repo_dir or Path(__file__).resolve().parent.parent)
    base_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": BOT_NAME, "GIT_AUTHOR_EMAIL": BOT_EMAIL,
        "GIT_COMMITTER_NAME": BOT_NAME, "GIT_COMMITTER_EMAIL": BOT_EMAIL,
    }
    tracking_ref = f"refs/remotes/{remote}/{branch}"
    # The branch does not exist before the first publish; that is not an error.
    _git(["fetch", "--quiet", remote, f"+refs/heads/{branch}:{tracking_ref}"], repo_dir, env=base_env, check=False)
    parent_result = _git(["rev-parse", "--verify", "--quiet", tracking_ref], repo_dir, env=base_env, check=False)
    parent = parent_result.stdout.decode().strip() if parent_result.returncode == 0 else ""

    with tempfile.TemporaryDirectory() as scratch:
        env = {**base_env, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        if parent:
            _git(["read-tree", parent], repo_dir, env=env)
        for path in remove:
            _git(["update-index", "--force-remove", _safe_path(path)], repo_dir, env=env)
        entries = {**{_safe_path(path): _serialize(payload) for path, payload in files.items()},
                   VERCEL_CONFIG_PATH: _serialize(VERCEL_CONFIG)}
        for path, data in entries.items():
            blob = _git(["hash-object", "-w", "--stdin"], repo_dir, env=env, input_bytes=data).stdout.decode().strip()
            _git(["update-index", "--add", "--cacheinfo", f"{FILE_MODE},{blob},{path}"], repo_dir, env=env)
        tree = _git(["write-tree"], repo_dir, env=env).stdout.decode().strip()
        if parent:
            parent_tree = _git(["rev-parse", f"{parent}^{{tree}}"], repo_dir, env=env).stdout.decode().strip()
            if parent_tree == tree:
                return ""
        commit_args = ["commit-tree", tree, "-m", message] + (["-p", parent] if parent else [])
        commit = _git(commit_args, repo_dir, env=env).stdout.decode().strip()
    _git(["push", "--quiet", remote, f"{commit}:refs/heads/{branch}"], repo_dir, env=base_env)
    return commit
