# Primary Financial Source Access Review

Checked at: 2026-10-16T07:37:29.586340+00:00

All candidates are inactive. No adapter, feed ingestion, body storage, or publication is enabled by this check.

| Candidate | HTTP | Content type | Test | Adapter | Usage review |
| --- | ---: | --- | --- | --- | --- |
| SEC EDGAR — Delta Air Lines submissions | 200 | application/json | GET-range | Required | Public SEC API; identify the automated client with User-Agent and remain at or below SEC fair-access limits. |
| SEC EDGAR — United Airlines Holdings submissions | 200 | application/json | GET-range | Required | Public SEC API; identify the automated client with User-Agent and remain at or below SEC fair-access limits. |
| SEC EDGAR — Boeing submissions | 200 | application/json | HEAD | Required | Public SEC API; identify the automated client with User-Agent and remain at or below SEC fair-access limits. |
| Delta Air Lines Investor Relations | 200 | text/html | HEAD | Required | Public investor page found; a dedicated machine-readable RSS/API and reuse permission were not confirmed. |
| United Airlines Investor Relations | 403 | - | GET-range | Required | Public investor page found; a dedicated machine-readable RSS/API and reuse permission were not confirmed. |
| Southwest Airlines Investor Relations | 200 | text/html | HEAD | Required | Public investor page found; a dedicated machine-readable RSS/API and reuse permission were not confirmed. |
| Lufthansa Group Financial News | 200 | text/html | HEAD | Required | The public newsroom exposes an RSS area and financial-news navigation; a financial-only endpoint and reuse conditions were not confirmed. |
| Air France-KLM Regulated Information | 200 | text/html | HEAD | Required | Public regulated-information page found; a dedicated machine-readable RSS/API and reuse permission were not confirmed. |
| KAP — Turkish Airlines disclosures | 200 | text/html | HEAD | Required | Public disclosure page found; no documented public RSS/API or automated-reuse permission was confirmed in this review. |

## Implementation boundary

- SEC EDGAR is the only confirmed structured public API in this review. A future adapter must request only configured airline/manufacturer CIKs, use a real contact-bearing User-Agent, and rate-limit below the SEC maximum.
- The airline IR and KAP candidates are public pages, not approved machine feeds. They remain inactive until a separate adapter and source-specific reuse review are approved.
