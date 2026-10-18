# Global source expansion — phase 1

Checked: 2026-10-18  
Branch: `feature/global-source-expansion`

## Outcome

The catalog contains 109 sources. Boeing Commercial Airplanes is the only newly activated source in this phase; its official RSS was explicitly requested and approved earlier. Four further sources have technically valid public feeds but remain `candidate_verified` (`active=0`) pending a separate activation decision. The pipeline ignores them while they are in this state.

| Source | Region | Type / tier | Method | Items in 7d | Aviation-pass / listed in probe | Decision |
|---|---|---:|---:|---:|---:|---|
| AirlineGeeks | Global | trade / 4 | RSS | 10 | 10 / 1 | Verified candidate, inactive |
| Australian Aviation | Asia-Pacific | trade / 2 | RSS | 10 | 10 / 0 | Verified candidate, inactive |
| NASA Aeronautics | North America | official research / 1 | RSS | 1 | 1 / 0 | Verified candidate, inactive |
| UK Department for Transport | Europe | regulator / 1 | Atom | 20 | 2 / 1 | Verified candidate, inactive; broad transport feed uses the aviation filter |
| NTSB News | North America | regulator / 1 | Official RSS exists | 0 | 0 / 0 | Excluded: robots.txt disallows `/_layouts/feed.aspx`; no feed request is made |

The read-only probe saw 41 feed items across the four valid candidates in its seven-day window. Two would have produced a story above the current score threshold. Scores, thresholds and taxonomy were not changed.

## Source-policy notes

- Only publisher-provided public RSS/Atom endpoints were tested. No login, cookie, proxy, paywall bypass or article-page scraping was used.
- Reuters, Bloomberg, FT, OAG and other licensed publishers remain inactive unless a licensed API/RSS endpoint or written automated-use permission is supplied.
- NASA and GOV.UK terms are recorded as low risk because their public-information reuse terms were read. AirlineGeeks and Australian Aviation stay medium risk because a readable reuse/automation terms page was not found; the feed addresses are public, but that does not itself decide commercial-use permission.
- `config/feeds_discovered.json` records the verified endpoints so they can be enabled without rediscovery after approval. `status=candidate_verified` prevents collection until then.

## Coverage after activation (projected)

Current active total, including Boeing: 39. Approving all four verified candidates would make 43 active sources and improve Asia-Pacific from one to two active sources. Africa would still have no active regional source; the next phase should add a dedicated adapter only for official pages whose terms and robots policy permit automated reading (for example national CAAs or AFRAA), then measure real seven-day yield before activation.
