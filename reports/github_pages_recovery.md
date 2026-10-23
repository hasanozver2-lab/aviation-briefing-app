# GitHub Pages recovery mirror — 23 October 2026

The owner approved a free GitHub Pages mirror while the `vercel.app` connection is failing. The Vercel project remains unchanged and can still be used once its network access recovers.

## Implementation

- `scripts/build_pages.py` generates the same UI with a static read-only data transport. It reuses `get_ready_briefing` with an injected reader; it does not collect, cluster, score or call an LLM.
- Latest data and archives come from one pinned `briefing-data` commit. Latest uses the ordinary main-view policy; archive exports include the same low band as the API's archive request.
- A failed export or deployment leaves the previous published site intact. Stale pipeline status is presented by the existing API presenter.
- App assets and the PWA manifest resolve beneath the repository path. Personal Instagram drafts and repository contents are not copied to the site.
- The mirror uses the UI's existing system-font fallback instead of blocking startup on Google Fonts. The Vercel font configuration is untouched.
- The separate Pages workflow runs after the existing briefing workflow completes, on relevant main changes, and on manual dispatch. It needs no API keys and does not modify the briefing pipeline.
- Generated output is under the already ignored `output/github-pages/`; only `public/index.html` remains the editable source UI.

## Expected address

`https://hasanozver2-lab.github.io/aviation-briefing-app/`

## Verification and rollback

Run `python -m pytest tests/test_pages_export.py tests/test_ui_contract.py tests/test_archive_ui.py tests/test_security_contracts.py`, then `python scripts/build_pages.py`. Test the generated site under `/aviation-briefing-app/`, including a story, archive date, EN/TR and manifest assets. After publishing, repeat against the live URL in iPhone-profile WebKit.

No database migration or secret changes are required. To roll back only the mirror, disable its Pages workflow and unpublish GitHub Pages in repository settings. The Vercel deployment and data branch are unaffected.
