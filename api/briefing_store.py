"""Select where finished briefings live: the git data branch (default) or Vercel Blob.

BRIEFING_STORE=github|blob. The Blob code stays available so the store can be switched
back with one environment variable.
"""

import os
import re

try:
    from . import blob_store
    from . import github_store
except ImportError:
    import blob_store
    import github_store


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STORES = ("github", "blob")
DEFAULT_STORE = "github"


def selected_store():
    name = os.environ.get("BRIEFING_STORE", "").strip().lower() or DEFAULT_STORE
    if name not in STORES:
        raise ValueError(f"BRIEFING_STORE must be one of {', '.join(STORES)}")
    return name


BRIEFING_PREFIX = "briefings"


def latest_path():
    return f"{BRIEFING_PREFIX}/latest.json"


def day_path(date_text):
    if not DATE_PATTERN.match(str(date_text)):
        raise ValueError("date must be YYYY-MM-DD")
    return f"{BRIEFING_PREFIX}/{date_text}.json"


def status_path():
    return f"{BRIEFING_PREFIX}/status.json"


def read_json(pathname):
    """Read a finished file from the selected store; None when it cannot be read."""
    if selected_store() == "blob":
        return blob_store.get_public_json(pathname)
    return github_store.get_public_json(pathname)


def publish(files, message, repo_dir=None):
    """Write {pathname: payload} to the selected store; returns a short description of the result."""
    if selected_store() == "blob":
        for pathname, payload in files.items():
            blob_store.put_public_json(pathname, payload)
        return f"blob: {len(files)} files"
    commit = github_store.publish_files(files, message, repo_dir=repo_dir)
    return f"github: {commit[:12]}" if commit else "github: unchanged"


def read_for_update(pathname, repo_dir=None):
    """Read a file the pipeline is about to rewrite: straight from git (no CDN lag) on the github store."""
    if selected_store() == "blob":
        return blob_store.get_public_json(pathname)
    return github_store.read_branch_json(pathname, repo_dir=repo_dir)
