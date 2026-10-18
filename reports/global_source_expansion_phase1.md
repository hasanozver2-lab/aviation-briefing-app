# Global priority-source expansion

Checked: 2026-10-18  
Branch: feature/global-source-expansion

## Outcome

The catalog contains 108 sources: 45 active, one verified candidate, 30 temporarily blocked, 13 excluded by policy, 11 without an extractable feed and eight without a public feed.

This pass activated six additional public sources:

| Source | Type / tier | Adapter | Real 7-day items | Probe result |
|---|---:|---:|---:|---|
| American Airlines Newsroom | official airline / 1 | public Q4 JSON API | 4 | 2 above list threshold |
| EUROCONTROL Newsroom | regulator / 1 | dated HTML cards | 2 | 1 above list threshold |
| FlightGlobal | trade / 2 | RSS | 10 | 1 above list threshold |
| Routes Online | trade / 3 | RSS | 19 | 4 above list threshold |
| AirlineGeeks | trade / 4 | RSS | 10 | 1 above list threshold |
| Australian Aviation | trade / 2 | RSS | 10 | 0 above list threshold |

The production collection path, after rebuilding SQLite from config/sources.csv, returned 206 articles in the seven-day diagnostic window. All six sources above returned articles through the same code path used by the pipeline. Thresholds and relevance weights were not changed.

UK Department for Transport remains candidate_verified and inactive. Its broad Atom feed is technically valid, but a real run admitted a shipping-fleet item through the generic aviation filter. It must not be activated until it has an aviation-only filter.

## Requested source matrix

Active means the pipeline can collect public metadata now. Covered by brand feeds means the requested group page is unavailable but active first-party brand feeds cover part of it. Other states remain explicit; the pipeline never counts an empty or blocked source as working.

### Airline IR / press

| State | Sources |
|---|---|
| Active | Delta, American Airlines, Lufthansa Group, Emirates, Qatar Airways (official Tumblr feed), Cathay Pacific, Ryanair, easyJet, Pegasus |
| Covered by brand feeds | Air France-KLM group page is blocked; Air France and KLM first-party feeds are active |
| Blocked / no extractable public feed | United, Southwest, IAG, Etihad, Singapore Airlines, ANA, JAL, LATAM, Turkish Airlines press |

### Regulators / institutions

| State | Sources |
|---|---|
| Active | ICAO, IATA, FAA, EASA, EUROCONTROL, ANAC Brazil, AAIB UK, BEA France |
| No extractable public feed | CAAC, DGCA India, SHGM |
| Excluded by robots policy | NTSB official RSS path |

### Exchanges / material disclosure

| State | Sources |
|---|---|
| Blocked pending required configuration | SEC EDGAR requires a truthful contact address in the User-Agent; none is configured |
| Excluded by terms | LSE RNS, HKEX |
| No documented public feed/API | KAP |

### Major press / wire services

| State | Sources |
|---|---|
| Active | The New York Times Business RSS |
| Excluded by terms or robots | Reuters, Bloomberg, Wall Street Journal, Associated Press |
| Blocked / no public feed | Financial Times, Washington Post, CNBC Airlines, The Economist, Nikkei Asia |

The separate FT and WSJ root/category URLs are represented as discovery URLs under one publisher row, not duplicate sources.

### Trade press / data

| State | Sources |
|---|---|
| Active | The Air Current, FlightGlobal, Simple Flying, AeroTime, Routes Online |
| No public feed | Aviation Week, ch-aviation, CAPA, Cirium |
| Excluded by terms or robots | OAG, AvHerald |

### RM / network / pricing technology

| State | Sources |
|---|---|
| Active | Accelya |
| No extractable public feed / blocked | PROS, Amadeus, Sabre, T2RL, PhocusWire, China Travel News |

### OEM newsroom / IR

| State | Sources |
|---|---|
| Active | Airbus, Boeing Commercial Airplanes, GE Aerospace, Rolls-Royce, Bombardier |
| No extractable public feed / blocked | Embraer, RTX, Safran |
| Excluded by terms | Textron Aviation |

## Policy boundary

- No login, cookie, proxy, browser impersonation, paywall bypass or article-page republication is used.
- Reuters, Bloomberg, FT, WSJ, AP, OAG and other restricted publishers stay inactive until a licensed feed/API or written automated-use permission is supplied.
- Source activation does not bypass relevance selection: a collected item appears in the briefing only if deterministic aviation filters and the configured score threshold accept it.
- Every unavailable source remains in config/sources.csv with its reason so failures are visible and retryable where appropriate.
