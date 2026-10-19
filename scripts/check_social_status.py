"""Health and Status Inspector for Social Radar Collector.

Usage:
  python scripts/check_social_status.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api import briefing_store, social_feed
from scripts import collect_social, connect_social


def main():
    print("==================================================")
    print("📡 Aviation Briefing - Social Radar Health Check")
    print("==================================================")

    # 1. Local Credentials
    auth_token, ct0 = collect_social.saved_session()
    if auth_token and ct0:
        print("✅ Local Session Credentials: DETECTED (auth_token & ct0 present)")
    else:
        print("⚠️ Local Session Credentials: NOT FOUND")
        print("   Run: python scripts/connect_social.py")

    # 2. X Reader / Node Tool
    bird_installed = connect_social.BIRD_SCRIPT.is_file()
    print(f"{'✅' if bird_installed else '❌'} Node X Reader (@steipete/bird): {'INSTALLED' if bird_installed else 'MISSING'}")

    # 3. Data Branch State
    data = briefing_store.read_json(social_feed.ITEMS_PATH)
    if not data:
        print("⚠️ Data Branch (briefings/social_items.json): NO DATA YET")
        print("   Run: python scripts/collect_social.py --publish")
        return 0

    items = data.get("items", [])
    updated_str = data.get("updated_at", "")
    print(f"✅ Published Posts Count: {len(items)}")
    print(f"📅 Last Published At: {updated_str}")

    if updated_str:
        try:
            updated_dt = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            hours_ago = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 3600
            print(f"⏱️ Freshness: {hours_ago:.1f} hours ago")
            if hours_ago > social_feed.STALE_AFTER_HOURS:
                print(f"⚠️ Warning: Posts are older than {social_feed.STALE_AFTER_HOURS} hours (stale).")
            else:
                print("🟢 Status: FRESH & UP TO DATE")
        except Exception:
            pass

    # Sample top 3 accounts
    if items:
        accounts = {item.get("handle") for item in items if item.get("handle")}
        print(f"👥 Active Monitored Accounts with Posts: {len(accounts)} accounts ({', '.join(sorted(accounts)[:6])}...)")

    print("==================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
