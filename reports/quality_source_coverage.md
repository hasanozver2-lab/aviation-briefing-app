# Quality source coverage — 2026-10-17

Branch: feature/quality-source-coverage. Local verification; not deployed.
Machine-readable evidence: quality_source_coverage.json (checked at 13:12 Istanbul time).

## Results

The catalog now has 104 sources, 37 active. IATA, ICAO and NYT were existing inactive rows; ACI World and BBC Business are new rows. Existing tiers, scoring weights and the 40-point threshold are unchanged.

| Source | Verified route | Aviation items in 7 days | Above threshold and not excluded, in this five-source sample | Aviation items in last 48h |
| --- | --- | ---: | ---: | ---: |
| IATA | Official RSS: /api/rss/pressrelease | 3 | 2 | 0 |
| ICAO | Official /news cards, date and title paired within each card | 3 | 0 | 0 |
| ACI World | Official /feed/ | 0 | 0 | 0 |
| New York Times | Official Business RSS | 1 | 0 | 1 |
| BBC News Business | Official Business RSS | 1 | 0 | 0 |

The 7-day window is diagnostic only. Production collection remains 48 hours; old IATA/ICAO/ACI notices are not made fresh to fill the list. The sample is not a complete pipeline run: other publishers may corroborate these stories and change their scores.

The New York Times aviation item scores 35 (archive band); the BBC item scores 15. IATA's two qualifying items score 48.2 but are outside the current 48-hour window. Thus these additions do not demonstrate any immediate extra main-list story today.

The ICAO notice about attacks on civilian airports is untyped and scores 23.5; its CORSIA notice scores 39.2. These are concrete taxonomy/calibration gaps for a separate review, not reasons to increase every story's score. The source parser reads the publisher's truncated headline as published; it does not invent its missing ending.

## Collection changes and tests

- Working RSS addresses are saved in config/sources.csv, config/feeds_discovered.json and discovery candidates so a future probe can rediscover them.
- ICAO needs a card reader because its dates use DD/MM/YY rather than a time datetime attribute. Selectors/date format live in config/newsroom_cards.json; parser is restricted to the configured hostname and same-host article links.
- General business feeds previously lost aviation items below the first 25 raw entries. The 25-item cap now applies after the aviation filter. Future-dated entries are excluded.
- NYT/BBC/ACI are feed_only: no article-page fetch; short summary only for narrative input, no publisher-summary archive publication.
- 751 tests passed, including 9 new cases for card dates, Unicode, host boundaries, feed quota ordering, future dates and source registration. Existing retry test now freezes its clock instead of depending on the wall-clock date.
- No new dependencies, Gemini calls, UI changes, score changes or production writes.

## Reuters, Bloomberg and other candidates

Reuters and Bloomberg remain excluded from direct ingestion. Their names being recognized by the Google Alerts reader does not mean they are providing news.

Both local configuration and live status show Google Alerts not_configured. GitHub secret names checked: GEMINI_API_KEY and FRED_API_KEY only; ALERT_FEEDS is absent. No secret values or private feed URLs were output.

To complete that existing route, the owner must put their Google Alerts RSS addresses into ALERT_FEEDS (one URL per line); transfer only that value to the GitHub secret via stdin. Do not send private feed URLs in chat. Publisher-scoped aviation alerts can cover Reuters, Bloomberg, NYT, FT, AP and WSJ; this requires configured feeds and does not provide a redistribution licence or guaranteed complete coverage.

CNBC's general business RSS is reachable, but its current RSS directory did not expose its documented feed list or readable reuse conditions. CNBC remains inactive pending verification; no generic business-feed substitution was silently made for its Airlines row. EUROCONTROL's newsroom was reachable but the inspected cards were old; its existing inactive status remains. These are candidate checks, not newly working sources.

## Source conditions

The catalog's existing pilot policy records commercial-use risks separately from technical feed access. Public feed availability is not a commercial licence. All newly enabled/added rows are marked high risk for commercial reuse.

- [IATA terms](https://www.iata.org/en/terms/): restrictions on commercial exploitation and redistribution; no fuel-monitor scraping added.
- [NYT RSS-specific conditions](https://www.nytimes.com/rss): personal reader/non-commercial-blog use with attribution; written permission required for commercial use. Read directly using the project client.
- [ACI World conditions](https://aci.aero/terms-and-conditions-of-use/): rights reserved; no general content reuse licence inferred.
- [BBC official archived terms, section 15](https://downloads.bbc.co.uk/usingthebbc/bbc_terms_of_use_19September2022english.pdf): attribution and business-permission requirements. Current interactive terms page did not expose readable terms; the archive is evidence, not confirmation that terms are unchanged.

Recheck permissions before commercial launch. Reuters/Bloomberg direct restrictions are unchanged. GitHub runner access has not been tested on this branch; successful local reads do not guarantee runner access.

Reproduce: Q:\DEV\.venv\Scripts\python.exe scripts/check_quality_sources.py --output reports/quality_source_coverage.json
