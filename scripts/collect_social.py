"""Read the latest posts of the official airline X accounts on THIS computer and make them visible in the app.

Uses the X session saved by scripts/connect_social.py (Agent Reach config). Session values are read from that config and passed to the
reader only through its environment; they are never printed, written to the output file or sent anywhere. Only the post text (first
line + short summary are used later), time, link and account name are kept.

  python scripts/collect_social.py              # writes output/social_items.json, nothing is published
  python scripts/collect_social.py --publish    # also publishes briefings/social_items.json to the data branch
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from api import github_store, social_feed  # noqa: E402
from scripts import connect_social  # noqa: E402

ACCOUNTS_PATH = PROJECT_DIR / "config" / "social_accounts.json"
OUTPUT_PATH = PROJECT_DIR / "output" / "social_items.json"
POSTS_PER_ACCOUNT = 10
KEEP_DAYS = 7
GAP_SECONDS = 3.0                 # one account at a time, with a pause: this is a person's session, not a crawler
READ_TIMEOUT_SECONDS = 60


def utc_now():
    return datetime.now(timezone.utc)


def load_accounts(path=None):
    return json.loads(Path(path or ACCOUNTS_PATH).read_text(encoding="utf-8"))["accounts"]


def saved_session(config=None):
    config = config or connect_social.load_agent_config()
    return config.get("twitter_auth_token"), config.get("twitter_ct0")


def post_fields(raw):
    """(id, text, time) of a raw post, or None for replies, reposts and anything incomplete."""
    if not isinstance(raw, dict) or raw.get("isRetweet") or raw.get("retweeted_status") or raw.get("inReplyToStatusId") or raw.get("in_reply_to_status_id"):
        return None
    post_id = str(raw.get("id") or raw.get("id_str") or "")
    text = raw.get("text") or raw.get("full_text") or ""
    created = raw.get("createdAt") or raw.get("created_at") or ""
    if not (post_id.isdigit() and text.strip() and created):
        return None
    return post_id, text.strip(), created


def read_account(account, session, runner=subprocess.run, now=None):
    """(posts, note). note is '' on success and never contains session values or process output."""
    auth_token, ct0 = session
    environment = {**os.environ, "AUTH_TOKEN": auth_token, "CT0": ct0, "NODE_USE_SYSTEM_CA": "1"}
    try:
        result = runner([shutil.which("node"), str(connect_social.BIRD_SCRIPT), "--timeout", "20000", "user-tweets", account["handle"], "-n", str(POSTS_PER_ACCOUNT), "--json"],
                        cwd=connect_social.TOOL_HOME, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=READ_TIMEOUT_SECONDS)
        if result.returncode:
            return [], "reader failed"
        raw_posts = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return [], f"reader error: {type(exc).__name__}"
    raw_posts = raw_posts if isinstance(raw_posts, list) else raw_posts.get("tweets", []) if isinstance(raw_posts, dict) else []
    cutoff = (now or utc_now()) - timedelta(days=KEEP_DAYS)
    posts = []
    for raw in raw_posts:
        fields = post_fields(raw)
        published = social_feed.parse_time(fields[2]) if fields else None
        if not published or published < cutoff:
            continue
        post_id, text, _ = fields
        posts.append({"id": post_id, "airline": account.get("airline", ""), "airline_code": account.get("airline_code", ""),
                      "author": account.get("author", ""), "role": account.get("role", ""),
                      "platform": account["platform"], "handle": account["handle"],
                      "text": text, "link": f"https://x.com/{account['handle']}/status/{post_id}", "published_at": published.isoformat(timespec="seconds")})
    return posts, "" if posts else "no recent original posts"


def merge(previous_posts, fresh_posts, now):
    """Fresh posts win; earlier ones stay for KEEP_DAYS so one failed account does not wipe its posts."""
    cutoff = now - timedelta(days=KEEP_DAYS)
    by_id = {post["id"]: post for post in previous_posts or []}
    by_id.update({post["id"]: post for post in fresh_posts})
    kept = [post for post in by_id.values() if social_feed.parse_time(post["published_at"]) >= cutoff]
    return sorted(kept, key=lambda post: post["published_at"], reverse=True)


def collect(accounts, session, previous_posts=None, runner=subprocess.run, sleep=time.sleep, now=None):
    """(payload, notes): notes maps handle -> note for accounts that returned nothing."""
    now = now or utc_now()
    fresh, notes = [], {}
    for position, account in enumerate(accounts):
        if position:
            sleep(GAP_SECONDS)
        posts, note = read_account(account, session, runner, now)
        fresh.extend(posts)
        if note:
            notes[account["handle"]] = note
    return {"generated_at": now.isoformat(timespec="seconds"), "posts": merge(previous_posts, fresh, now)}, notes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--publish", action="store_true", help="publish briefings/social_items.json to the data branch")
    publish = parser.parse_args(argv).publish
    if not (connect_social.BIRD_SCRIPT.is_file() and shutil.which("node")):
        print("X reader is not installed. Run connect_social.cmd, choose 3 for status.")
        return 1
    session = saved_session()
    if not all(session):
        print("No saved X session. Run connect_social.cmd and choose 1.")
        return 1
    previous = None
    if OUTPUT_PATH.is_file():
        previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8")).get("posts")
    payload, notes = collect(load_accounts(), session, previous)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    accounts_with_posts = len({post["handle"] for post in payload["posts"]})
    print(f"{len(payload['posts'])} posts from {accounts_with_posts} accounts -> {OUTPUT_PATH}")
    for handle, note in sorted(notes.items()):
        print(f"  @{handle}: {note}")
    if publish and payload["posts"]:
        commit = github_store.publish_files({social_feed.ITEMS_PATH: payload}, f"Social posts {payload['generated_at']}")
        print("published:", commit[:12] if commit else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
