"""Export the existing UI and ready API payloads for the optional GitHub Pages mirror.

No collection, scoring or LLM calls. All JSON comes from one immutable data-branch commit.
The Vercel UI source is not modified; only generated Pages output gets a static transport.
"""

import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from api import _engine as engine


PUBLIC_DIR = PROJECT_DIR / "public"
DEFAULT_OUTPUT = PROJECT_DIR / "output" / "github-pages"
DEFAULT_REF = "refs/remotes/origin/briefing-data"
DATE_FILE = re.compile(r"^briefings/(\d{4}-\d{2}-\d{2})\.json$")
EXPECTED_BRIEFING_FETCHES = 3
ASSET_NAMES = ("apple-touch-icon.png", "favicon-32.png", "icon.svg", "icon-192.png", "icon-512.png")
STATIC_TRANSPORT = '''
    // GitHub Pages has no Python API. These payloads use the very same ready-briefing presenter.
    function fetchBriefing(input, options) {
      const requested = new URL(input, location.href);
      const date = requested.searchParams.get("date");
      if (date !== null && !/^\\d{4}-\\d{2}-\\d{2}$/.test(date)) {
        return Promise.reject(new Error("Invalid archive date"));
      }
      const target = new URL(date ? `data/${date}.json` : "data/latest.json", document.baseURI);
      target.searchParams.set("t", requested.searchParams.get("view") || requested.searchParams.get("t") || Date.now());
      return fetch(target.href, options);
    }
'''


class GitSnapshots:
    def __init__(self, ref=DEFAULT_REF):
        self.commit = self.git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
        self.paths = self.git("ls-tree", "-r", "--name-only", self.commit, "briefings/").decode().splitlines()
        self.cache = {}

    @staticmethod
    def git(*arguments):
        return subprocess.run(["git", *arguments], cwd=PROJECT_DIR, capture_output=True, check=True, timeout=30).stdout

    def __call__(self, pathname):
        if pathname not in self.paths:
            return None
        if pathname not in self.cache:
            payload = json.loads(self.git("show", f"{self.commit}:{pathname}").decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(f"Snapshot must be a JSON object: {pathname}")
            self.cache[pathname] = payload
        # The shared presenter updates badges and filters stories in place.
        return copy.deepcopy(self.cache[pathname])


def pages_html(html):
    marker = "  <script>\n"
    if html.count(marker) != 1:
        raise ValueError("Expected one application script; refusing to publish a partial UI")
    html = html.replace(marker, marker + STATIC_TRANSPORT, 1)
    # A recovery page must bootstrap even when the external font CDN cannot be reached.
    html = re.sub(r'^.*<link[^>]+href="https://fonts\.(?:googleapis|gstatic)\.com[^>]*>\s*\n', "", html, flags=re.MULTILINE)
    html, count = re.subn(r'\bfetch\((?=`\$\{BRIEFING_URL\})', "fetchBriefing(", html)
    if count != EXPECTED_BRIEFING_FETCHES:
        raise ValueError(f"Expected {EXPECTED_BRIEFING_FETCHES} briefing requests, found {count}")
    html = html.replace('href="/static/manifest.json"', 'href="./manifest.json"')
    return html.replace('href="/static/', 'href="./static/')


def pages_manifest(manifest):
    manifest = copy.deepcopy(manifest)
    manifest.update(start_url="./", scope="./", id="./")
    for icon in manifest.get("icons", []):
        icon["src"] = "./static/" + Path(icon["src"]).name
    return manifest


def build(output=DEFAULT_OUTPUT, snapshots=None):
    snapshots = snapshots or GitSnapshots()
    if not isinstance(snapshots("briefings/latest.json"), dict):
        raise ValueError("No ready latest snapshot; keeping the previously deployed Pages site")
    payloads = {"latest.json": engine.get_ready_briefing(reader=snapshots)}
    for path in snapshots.paths:
        matched = DATE_FILE.fullmatch(path)
        if matched:
            date_text = matched.group(1)
            payloads[f"{date_text}.json"] = engine.get_ready_briefing(date=date_text, include_low=True, reader=snapshots)

    html = pages_html((PUBLIC_DIR / "index.html").read_text(encoding="utf-8"))
    manifest = pages_manifest(json.loads((PUBLIC_DIR / "manifest.json").read_text(encoding="utf-8")))
    output = Path(output)
    (output / "data").mkdir(parents=True, exist_ok=True)
    (output / "static").mkdir(exist_ok=True)
    for name, payload in payloads.items():
        (output / "data" / name).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for name in ASSET_NAMES:
        shutil.copyfile(PUBLIC_DIR / name, output / "static" / name)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / ".nojekyll").touch()
    print(f"Pages export: {output}; {len(payloads)} ready payloads; data commit {snapshots.commit}")
    return payloads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ref", default=DEFAULT_REF)
    arguments = parser.parse_args()
    build(arguments.output, GitSnapshots(arguments.ref))


if __name__ == "__main__":
    main()
