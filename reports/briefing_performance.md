# Briefing Performance Baseline

Baseline captured before the card/detail split at commit `b67e55e` on 2026-10-16.

| Measure | Before | Method / qualification |
| --- | ---: | --- |
| Daily briefing JSON | 24.15 KB (24,733 bytes) | Existing `briefing_cache_daily.json`; 7 cards, each containing its detail fields. |
| First meaningful content (local equivalent) | 10.1 ms median | Five warm requests to the local `/api/briefing?mode=daily` endpoint, which returned the legacy single JSON used to render the first card list. This is a local API/render-input measurement, not a network Lighthouse result. |
| Pipeline duration | Not captured by the legacy output | The legacy cache does not retain run duration. |
| LLM input/output tokens | Not captured by the legacy output | The legacy Gemini client discards `usageMetadata`; an exact historical total cannot be reconstructed from the cache. |

## Baseline constraints

- The pre-change payload has no `relevance_score`, `include_threshold`, `priority_threshold`, or `exclude_threshold` field.
- None of the seven cached stories has a numeric relevance score. Therefore there is no existing score distribution from which to justify an initial `exclude_threshold` without changing the scoring model.
- The local Vercel Blob base URL was not configured during this capture, so the local cache was used as the production-shape fixture.

Post-change runs will record pipeline duration and Gemini `usageMetadata` totals in this report, alongside the new main JSON size and browser measurement.
