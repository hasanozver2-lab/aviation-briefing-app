# Entity seed review

Generated from `config/entities/*.csv`. Fleet and passenger figures are approximate; rows with a `verification_source` were checked on 2026-10-16 against public sources.
`needs_verification=1` = low confidence in the figure, or a +/-15% fleet (+/-10% passengers) error would change the tier.

## Counts

- groups 19, carrier brands 163, airports 140, aircraft types 69, history rows 7
- passenger/mixed carrier tiers: {1: 33, 2: 37, 3: 37, 4: 46}; cargo tiers: {1: 3, 3: 3, 4: 4}
- group tiers: {1: 8, 2: 11}; airport tiers: {1: 40, 2: 51, 3: 34, 4: 15}
- needs_verification: carriers 57/163, airports 71/140, groups 17/19

## Groups (passenger/mixed brands only; thresholds 400 / 200 / 100)

| entity_id | group | tier | weighted | brands | verify |
| --- | --- | ---: | ---: | --- | :-: |
| group:000009 | China Southern Airlines Group | 1 | 969 | China Southern Airlines, Xiamen Airlines | ⚠ |
| group:000008 | China Eastern Airlines Group | 1 | 830 | China Eastern Airlines, China Cargo Airlines | ⚠ |
| group:000001 | Lufthansa Group | 1 | 788.5 | Lufthansa, SWISS International Air Lines, Eurowings, Austrian Airlines, Brussels Airlines, Discover Airlines, Lufthansa Cargo, Air Dolomiti | ⚠ |
| group:000007 | Air China Group | 1 | 742 | Air China, Shenzhen Airlines, Air China Cargo | ⚠ |
| group:000002 | International Airlines Group | 1 | 717 | British Airways, Iberia, Vueling, Aer Lingus, LEVEL | ⚠ |
| group:000004 | Turkish Airlines Group | 1 | 590 | Turkish Airlines, AJet, Turkish Cargo | ⚠ |
| group:000003 | Air France-KLM | 1 | 577.5 | Air France, KLM, Transavia, Transavia France, KLM Cityhopper, Air France HOP, Martinair | ⚠ |
| group:000014 | Korean Air Group | 1 | 462 | Korean Air, Asiana Airlines, Jin Air | ⚠ |
| group:000018 | Alaska Air Group | 2 | 374 | Alaska Airlines, Hawaiian Airlines, Horizon Air | ⚠ |
| group:000016 | Air India Group | 2 | 352 | Air India, Air India Express | ⚠ |
| group:000013 | Cathay Group | 2 | 343 | Cathay Pacific, HK Express | ⚠ |
| group:000010 | ANA Holdings | 2 | 338 | All Nippon Airways, Peach Aviation, ANA Wings | ⚠ |
| group:000005 | Aeroflot Group | 2 | 322 | Aeroflot, Pobeda, Rossiya Airlines | ⚠ |
| group:000011 | Japan Airlines Group | 2 | 321 | Japan Airlines, ZIPAIR Tokyo, J-Air | ⚠ |
| group:000006 | Qantas Group | 2 | 319 | Qantas, Jetstar, QantasLink | ⚠ |
| group:000012 | Singapore Airlines Group | 2 | 300 | Singapore Airlines, Scoot |  |
| group:000017 | Saudia Group | 2 | 282 | Saudia, flyadeal | ⚠ |
| group:000019 | Abra Group | 2 | 274 | Avianca, GOL Linhas Aéreas |  |
| group:000015 | AirAsia Group | 2 | 234 | AirAsia, Thai AirAsia, Indonesia AirAsia, AirAsia X, Philippines AirAsia | ⚠ |

## Tier 1 passenger/mixed carriers

| entity_id | brand | IATA | region | op | W | N | R | weighted | tier | group | verify |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | :-: |
| carrier:000116 | United Airlines | UA | Americas | passenger | 210 | 790 | 0 | 1210 | 1 |  |  |
| carrier:000115 | Delta Air Lines | DL | Americas | passenger | 165 | 825 | 0 | 1155 | 1 |  |  |
| carrier:000114 | American Airlines | AA | Americas | passenger | 107 | 855 | 0 | 1069 | 1 |  |  |
| carrier:000053 | China Eastern Airlines | MU | Asia-Pacific | passenger | 90 | 650 | 0 | 830 | 1 | China Eastern Airlines Group | ⚠ |
| carrier:000117 | Southwest Airlines | WN | Americas | passenger | 0 | 800 | 0 | 800 | 1 |  |  |
| carrier:000055 | China Southern Airlines | CZ | Asia-Pacific | passenger | 75 | 630 | 0 | 780 | 1 | China Southern Airlines Group | ⚠ |
| carrier:000029 | Ryanair | FR | Europe | passenger | 0 | 620 | 0 | 620 | 1 |  |  |
| carrier:000050 | Air China | CA | Asia-Pacific | passenger | 95 | 340 | 0 | 530 | 1 | Air China Group | ⚠ |
| carrier:000099 | Emirates | EK | Middle East & Gulf | mixed | 255 | 0 | 0 | 510 | 1 |  |  |
| carrier:000021 | Turkish Airlines | TK | Europe | passenger | 130 | 245 | 0 | 505 | 1 | Turkish Airlines Group |  |
| carrier:000001 | Lufthansa | LH | Europe | passenger | 100 | 205 | 0 | 405 | 1 | Lufthansa Group |  |
| carrier:000091 | IndiGo | 6E | Asia-Pacific | passenger | 0 | 380 | 45 | 402.5 | 1 |  |  |
| carrier:000009 | British Airways | BA | Europe | passenger | 125 | 140 | 0 | 390 | 1 | International Airlines Group |  |
| carrier:000100 | Qatar Airways | QR | Middle East & Gulf | mixed | 150 | 85 | 0 | 385 | 1 |  |  |
| carrier:000057 | Hainan Airlines | HU | Asia-Pacific | passenger | 45 | 270 | 0 | 360 | 1 |  | ⚠ |
| carrier:000030 | easyJet | U2 | Europe | passenger | 0 | 340 | 0 | 340 | 1 |  |  |
| carrier:000071 | Korean Air | KE | Asia-Pacific | mixed | 125 | 70 | 0 | 320 | 1 | Korean Air Group |  |
| carrier:000014 | Air France | AF | Europe | passenger | 92 | 125 | 0 | 309 | 1 | Air France-KLM |  |
| carrier:000069 | Cathay Pacific | CX | Asia-Pacific | mixed | 130 | 45 | 0 | 305 | 1 | Cathay Group |  |
| carrier:000136 | LATAM Airlines | LA | Americas | passenger | 45 | 215 | 0 | 305 | 1 |  |  |
| carrier:000064 | Japan Airlines | JL | Asia-Pacific | passenger | 118 | 62 | 0 | 298 | 1 | Japan Airlines Group |  |
| carrier:000061 | All Nippon Airways | NH | Asia-Pacific | passenger | 95 | 100 | 0 | 290 | 1 | ANA Holdings |  |
| carrier:000128 | Air Canada | AC | Americas | passenger | 75 | 135 | 0 | 285 | 1 |  |  |
| carrier:000118 | JetBlue | B6 | Americas | passenger | 0 | 235 | 55 | 262.5 | 1 |  |  |
| carrier:000119 | Alaska Airlines | AS | Americas | passenger | 5 | 249 | 0 | 259 | 1 | Alaska Air Group |  |
| carrier:000092 | Air India | AI | Asia-Pacific | passenger | 60 | 127 | 0 | 247 | 1 | Air India Group |  |
| carrier:000104 | Saudia | SV | Middle East & Gulf | passenger | 89 | 64 | 0 | 242 | 1 | Saudia Group |  |
| carrier:000024 | Aeroflot | SU | Europe | passenger | 45 | 150 | 0 | 240 | 1 | Aeroflot Group | ⚠ |
| carrier:000067 | Singapore Airlines | SQ | Asia-Pacific | mixed | 110 | 20 | 0 | 240 | 1 | Singapore Airlines Group |  |
| carrier:000149 | Ethiopian Airlines | ET | Africa | mixed | 83 | 55 | 30 | 236 | 1 |  |  |
| carrier:000058 | Sichuan Airlines | 3U | Asia-Pacific | passenger | 20 | 184 | 0 | 224 | 1 |  |  |
| carrier:000031 | Wizz Air | W6 | Europe | passenger | 0 | 215 | 0 | 215 | 1 |  | ⚠ |
| carrier:000051 | Shenzhen Airlines | ZH | Asia-Pacific | passenger | 7 | 198 | 0 | 212 | 1 | Air China Group |  |

## Cargo operators (cargo_tier; weights wide x2, narrow x1, regional x0.25)

| entity_id | brand | IATA | region | op | W | N | R | weighted | tier | group | verify |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | :-: |
| carrier:000144 | FedEx Express | FX | Americas | cargo | 330 | 120 | 240 | 840 | 1 |  | ⚠ |
| carrier:000145 | UPS Airlines | 5X | Americas | cargo | 180 | 75 | 0 | 435 | 1 |  | ⚠ |
| carrier:000146 | Atlas Air | 5Y | Americas | cargo | 110 | 0 | 0 | 220 | 1 |  | ⚠ |
| carrier:000148 | SF Airlines | O3 | Asia-Pacific | cargo | 15 | 60 | 0 | 90 | 3 |  | ⚠ |
| carrier:000147 | Cargolux | CV | Europe | cargo | 30 | 0 | 0 | 60 | 3 |  | ⚠ |
| carrier:000022 | Turkish Cargo |  | Europe | cargo | 28 | 0 | 0 | 56 | 3 | Turkish Airlines Group | ⚠ |
| carrier:000052 | Air China Cargo |  | Asia-Pacific | cargo | 15 | 0 | 0 | 30 | 4 | Air China Group | ⚠ |
| carrier:000008 | Lufthansa Cargo |  | Europe | cargo | 13 | 0 | 0 | 26 | 4 | Lufthansa Group |  |
| carrier:000054 | China Cargo Airlines | CK | Asia-Pacific | cargo | 10 | 0 | 0 | 20 | 4 | China Eastern Airlines Group | ⚠ |
| carrier:000020 | Martinair | MP | Europe | cargo | 3 | 0 | 0 | 6 | 4 | Air France-KLM | ⚠ |

## Capacity-purchase regionals (tier capped at 2)

| entity_id | brand | IATA | region | op | W | N | R | weighted | tier | group | verify |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | :-: |
| carrier:000126 | SkyWest Airlines | OO | Americas | passenger (CPA) | 0 | 0 | 480 | 240 | 2 |  | ⚠ |
| carrier:000127 | Republic Airways | YX | Americas | passenger (CPA) | 0 | 0 | 311 | 155.5 | 2 |  |  |
| carrier:000161 | Envoy Air | MQ | Americas | passenger (CPA) | 0 | 0 | 150 | 75 | 3 |  |  |
| carrier:000163 | Endeavor Air | 9E | Americas | passenger (CPA) | 0 | 0 | 140 | 70 | 3 |  |  |
| carrier:000162 | PSA Airlines | OH | Americas | passenger (CPA) | 0 | 0 | 130 | 65 | 3 |  |  |
| carrier:000129 | Jazz Aviation | QK | Americas | passenger (CPA) | 0 | 0 | 104 | 52 | 3 |  |  |
| carrier:000121 | Horizon Air | QX | Americas | passenger (CPA) | 0 | 0 | 60 | 30 | 4 | Alaska Air Group | ⚠ |

## Verification run 2026-10-16 (carriers within +/-15% of a tier threshold)

| carrier | before W/N/R | tier | after W/N/R | weighted | tier | source |
| --- | --- | :-: | --- | ---: | :-: | --- |
| Austrian Airlines | 5/32/14 | 4 | 12/40/15 | 71.5 | 3 | https://en.wikipedia.org/wiki/Austrian_Airlines (wikipedia, as of May 2026; rows sum to 67) |
| Brussels Airlines | 9/31/0 | 4 | 11/37/0 | 59 | 3 | https://en.wikipedia.org/wiki/Brussels_Airlines (wikipedia, as of 30 Jun 2026; 48 in service) |
| Transavia | 0/45/0 | 4 | 0/52/0 | 52 | 3 | https://en.wikipedia.org/wiki/Transavia (wikipedia, as of Oct 2026; Netherlands AOC only) |
| Pegasus Airlines | 0/115/0 | 2 | 0/131/0 | 131 | 2 | https://en.wikipedia.org/wiki/Pegasus_Airlines (wikipedia infobox, as of Jun 2026; type table of Aug 2025 shows 129) |
| Jet2 | 0/110/0 | 2 | 0/126/0 | 126 | 2 | https://en.wikipedia.org/wiki/Jet2.com (wikipedia, as of Oct 2025; passenger 737-800/A321 only, 7 freighter-type 737-300 excluded, infobox says 120) |
| Scandinavian Airlines | 12/75/30 | 2 | 14/94/15 | 129.5 | 2 | https://en.wikipedia.org/wiki/Scandinavian_Airlines (wikipedia, as of Sep 2025; mainline 74 + SAS Connect 34 A320neo + SAS Link 15 E195, wet-leases excluded) |
| Finnair | 20/50/12 | 3 | 24/29/24 | 89 | 3 | https://en.wikipedia.org/wiki/Finnair (wikipedia, as of Jul 2026; regional = Norra ATR72 12 + E190 12 flying for Finnair) |
| TAP Air Portugal | 17/60/15 | 2 | 22/75/0 | 119 | 2 | https://en.wikipedia.org/wiki/TAP_Air_Portugal (wikipedia, as of May 2026; Portugalia/TAP Express not included) |
| Air Europa | 15/25/0 | 3 | 29/18/0 | 76 | 3 | https://en.wikipedia.org/wiki/Air_Europa (wikipedia, as of Nov 2025) |
| Volotea | 0/45/0 | 4 | 0/41/0 | 41 | 4 | https://www.aviationoutlook.com/p/volotea-strategic-analysis-outlook-report (other, as of Jun 2026; wikipedia infobox says 45) |
| airBaltic | 0/50/0 | 3 | 0/55/0 | 55 | 3 | https://en.wikipedia.org/wiki/AirBaltic (wikipedia, as of Sep 2026; fleet planned to fall to ~36 by end 2026 after Chapter 11 filing) |
| S7 Airlines | 0/90/0 | 3 | 0/87/17 | 95.5 | 3 | https://en.wikipedia.org/wiki/S7_Airlines (wikipedia, as of Aug 2025; many aircraft parked) |
| Jetstar | 11/75/0 | 3 | 11/89/0 | 111 | 2 | https://en.wikipedia.org/wiki/Jetstar_Airways (wikipedia, as of May 2026; Australia AOC only) |
| Shenzhen Airlines | 0/215/0 | 1 | 7/198/0 | 212 | 1 | https://en.wikipedia.org/wiki/Shenzhen_Airlines (wikipedia, as of Jun 2026; table total 205) |
| Xiamen Airlines | 0/205/0 | 1 | 12/165/0 | 189 | 2 | https://en.wikipedia.org/wiki/Xiamen_Airlines (wikipedia, as of Jul 2026; per-type rows 177 vs stated 172, ambiguous) |
| Sichuan Airlines | 22/150/0 | 2 | 20/184/0 | 224 | 1 | https://en.wikipedia.org/wiki/Sichuan_Airlines (wikipedia, as of Oct 2025; passenger fleet only) |
| Japan Airlines | 75/60/0 | 1 | 118/62/0 | 298 | 1 | https://en.wikipedia.org/wiki/Japan_Airlines_fleet (wikipedia, as of Mar 2026; mainline only, widebody +/-1) |
| Asiana Airlines | 30/38/0 | 3 | 43/24/0 | 110 | 2 | https://en.wikipedia.org/wiki/Asiana_Airlines (wikipedia, as of Jul 2026; full integration into Korean Air due end 2026) |
| Thai Airways | 35/25/0 | 3 | 59/21/0 | 139 | 2 | https://en.wikipedia.org/wiki/Thai_Airways_International_fleet (wikipedia, as of Feb 2026; likely higher now) |
| Malaysia Airlines | 22/50/0 | 3 | 33/58/0 | 124 | 2 | https://www.ch-aviation.com/news/168576-malaysia-airlines-to-decide-on-a350-replacement-by-2026 (tracker, 2026; per search summary) |
| AirAsia | 0/105/0 | 2 | 0/108/0 | 108 | 2 | https://en.wikipedia.org/wiki/AirAsia (wikipedia, as of Jul 2026; AK only, 3 freighters excluded) |
| VietJet Air | 0/105/0 | 2 | 8/99/0 | 115 | 2 | https://vietnamnet.vn/en/vietnam-s-aircraft-fleet-hits-record-258-as-airlines-expand-2558666.html (CAAV data, as of 2026-09-22; Vietnam-registered only) |
| Lion Air | 0/100/0 | 2 | 12/80/0 | 104 | 2 | https://en.wikipedia.org/wiki/Lion_Air (wikipedia, as of Feb 2026; per-type rows sum 92 vs stated 99, unexplained gap) |
| Cebu Pacific | 8/70/8 | 3 | 14/68/0 | 96 | 3 | https://en.wikipedia.org/wiki/Cebu_Pacific (wikipedia, as of Oct 2026; turboprops sit under Cebgo, not counted) |
| Air New Zealand | 22/35/25 | 3 | 24/37/54 | 112 | 2 | https://en.wikipedia.org/wiki/Air_New_Zealand (wikipedia, as of Sep 2025; regional = Air NZ Link ATR72 31 + Q300 23) |
| Air India | 50/120/0 | 1 | 60/127/0 | 247 | 1 | https://en.wikipedia.org/wiki/Air_India_fleet (wikipedia, as of Oct 2025; includes ex-Vistara, narrowbody derived as total 187 minus widebody) |
| Air India Express | 0/100/0 | 2 | 0/105/0 | 105 | 2 | https://en.wikipedia.org/wiki/Air_India_Express (wikipedia, as of Aug 2026) |
| SpiceJet | 0/40/15 | 4 | 0/27/24 | 39 | 4 | https://en.wikipedia.org/wiki/SpiceJet (wikipedia, as of Jul 2026; 3 freighter 737-700 excluded) |
| Air Astana | 5/35/0 | 4 | 3/32/0 | 38 | 4 | https://en.wikipedia.org/wiki/Air_Astana (wikipedia, as of Jul 2026; FlyArystan excluded) |
| Saudia | 55/72/0 | 2 | 89/64/0 | 242 | 1 | https://en.wikipedia.org/wiki/Saudia (wikipedia, as of Sep 2025; passenger fleet, flyadeal and freighters excluded) |
| Gulf Air | 13/30/0 | 3 | 10/37/0 | 57 | 3 | https://en.wikipedia.org/wiki/Gulf_Air (wikipedia, as of Jan 2026) |
| Oman Air | 10/25/0 | 4 | 9/19/0 | 37 | 4 | https://en.wikipedia.org/wiki/Oman_Air (wikipedia, as of Nov 2025; per-type rows sum 28 vs stated 33; tier 4 either way) |
| Alaska Airlines | 0/230/0 | 1 | 5/249/0 | 259 | 1 | https://news.alaskaair.com/fleet/ (airline, as of Jul 2026; mainline passenger only, 5 freighters and Hawaiian/Horizon types excluded) |
| Hawaiian Airlines | 36/24/0 | 3 | 24/37/0 | 85 | 3 | https://en.wikipedia.org/wiki/Hawaiian_Airlines (wikipedia, as of Mar 2026; passenger only, 10 A330P2F freighters excluded) |
| Republic Airways | 0/0/190 | 3 | 0/0/311 | 155.5 | 2 | https://www.barchart.com/story/news/555273/republic-airways-holdings-inc-announces-q4-and-full-year-2025-financial-results (airline results, as of 2025-12-31; after Mesa merger) |
| Jazz Aviation | 0/0/95 | 4 | 0/0/104 | 52 | 3 | https://en.wikipedia.org/wiki/Jazz_Aviation (wikipedia, as of 2026-03-24; Transport Canada register) |
| WestJet | 12/140/40 | 2 | 7/155/35 | 186.5 | 2 | https://en.wikipedia.org/wiki/WestJet (wikipedia, as of 2026-09-10; regional = Encore Q400 in service) |
| Copa Airlines | 0/105/0 | 2 | 0/105/0 | 105 | 2 | https://en.wikipedia.org/wiki/Copa_Airlines (wikipedia, as of Jun 2025; passenger 737s, cargo 737-800BCF excluded) |
| Ethiopian Airlines | 75/40/12 | 2 | 83/55/30 | 236 | 1 | https://en.wikipedia.org/wiki/Ethiopian_Airlines_fleet (wikipedia, as of Nov 2025; widebody incl. 12 777F + 4 767F, narrowbody incl. 4 737-800SF; passenger-only would also be tier 1) |
| EgyptAir | 18/55/0 | 3 | 23/48/0 | 94 | 3 | https://en.wikipedia.org/wiki/EgyptAir (wikipedia, as of Jul 2026; passenger only) |
| Spirit Airlines | 0/205/0 | 1 | 0/0/0 | 0 | 4 | https://en.wikipedia.org/wiki/Spirit_Airlines (wikipedia, as of 2026-05-02; page states operations ceased and liquidation began; last fleet ~131 A320-family) |

Not verifiable (sources conflict, flag kept):

- Wizz Air: unverified 2026-10-16: found 118 but page also cites 250+ aircraft; count looks partial
- Eurowings: unverified 2026-10-16: Wikipedia table garbled, narrowbody count unreliable (about 90, Eurowings Europe separate)
- AJet: unverified 2026-10-16: sources conflict: 85-89 (news, infobox) vs 126 (table); lease scope unclear
- Sun Country Airlines: unverified 2026-10-16: found 66 incl. 20 cargo 737BCF but per-type split low confidence; Allegiant acquisition announced 2026-01-11

## Remaining carriers with needs_verification=1 (all tiers)

| entity_id | brand | IATA | region | op | W | N | R | weighted | tier | group | verify |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | :-: |
| carrier:000144 | FedEx Express | FX | Americas | cargo | 330 | 120 | 240 | 840 | None |  | ⚠ |
| carrier:000053 | China Eastern Airlines | MU | Asia-Pacific | passenger | 90 | 650 | 0 | 830 | 1 | China Eastern Airlines Group | ⚠ |
| carrier:000055 | China Southern Airlines | CZ | Asia-Pacific | passenger | 75 | 630 | 0 | 780 | 1 | China Southern Airlines Group | ⚠ |
| carrier:000050 | Air China | CA | Asia-Pacific | passenger | 95 | 340 | 0 | 530 | 1 | Air China Group | ⚠ |
| carrier:000145 | UPS Airlines | 5X | Americas | cargo | 180 | 75 | 0 | 435 | None |  | ⚠ |
| carrier:000057 | Hainan Airlines | HU | Asia-Pacific | passenger | 45 | 270 | 0 | 360 | 1 |  | ⚠ |
| carrier:000024 | Aeroflot | SU | Europe | passenger | 45 | 150 | 0 | 240 | 1 | Aeroflot Group | ⚠ |
| carrier:000126 | SkyWest Airlines | OO | Americas | passenger (CPA) | 0 | 0 | 480 | 240 | 2 |  | ⚠ |
| carrier:000146 | Atlas Air | 5Y | Americas | cargo | 110 | 0 | 0 | 220 | None |  | ⚠ |
| carrier:000031 | Wizz Air | W6 | Europe | passenger | 0 | 215 | 0 | 215 | 1 |  | ⚠ |
| carrier:000059 | Spring Airlines | 9C | Asia-Pacific | passenger | 0 | 120 | 0 | 120 | 2 |  | ⚠ |
| carrier:000002 | SWISS International Air Lines | LX | Europe | passenger | 26 | 64 | 0 | 116 | 2 | Lufthansa Group | ⚠ |
| carrier:000060 | Juneyao Airlines | HO | Asia-Pacific | passenger | 8 | 100 | 0 | 116 | 2 |  | ⚠ |
| carrier:000005 | Eurowings | EW | Europe | passenger | 0 | 95 | 0 | 95 | 3 | Lufthansa Group | ⚠ |
| carrier:000148 | SF Airlines | O3 | Asia-Pacific | cargo | 15 | 60 | 0 | 90 | None |  | ⚠ |
| carrier:000023 | AJet | VF | Europe | passenger | 0 | 85 | 0 | 85 | 3 | Turkish Airlines Group | ⚠ |
| carrier:000087 | Philippine Airlines | PR | Asia-Pacific | passenger | 15 | 40 | 0 | 70 | 3 |  | ⚠ |
| carrier:000151 | Royal Air Maroc | AT | Africa | passenger | 10 | 40 | 5 | 62.5 | 3 |  | ⚠ |
| carrier:000085 | Garuda Indonesia | GA | Asia-Pacific | passenger | 8 | 45 | 0 | 61 | 3 |  | ⚠ |
| carrier:000079 | Thai AirAsia | FD | Asia-Pacific | passenger | 0 | 60 | 0 | 60 | 3 | AirAsia Group | ⚠ |
| carrier:000147 | Cargolux | CV | Europe | cargo | 30 | 0 | 0 | 60 | None |  | ⚠ |
| carrier:000154 | Air Algérie | AH | Africa | passenger | 10 | 35 | 8 | 59 | 3 |  | ⚠ |
| carrier:000022 | Turkish Cargo |  | Europe | cargo | 28 | 0 | 0 | 56 | None | Turkish Airlines Group | ⚠ |
| carrier:000125 | Sun Country Airlines | SY | Americas | mixed | 0 | 45 | 0 | 45 | 4 |  | ⚠ |
| carrier:000019 | Transavia France | TO | Europe | passenger | 0 | 42 | 0 | 42 | 4 | Air France-KLM | ⚠ |
| carrier:000026 | Pobeda | DP | Europe | passenger | 0 | 42 | 0 | 42 | 4 | Aeroflot Group | ⚠ |
| carrier:000025 | Rossiya Airlines | FV | Europe | passenger | 0 | 40 | 0 | 40 | 4 | Aeroflot Group | ⚠ |
| carrier:000048 | QantasLink |  | Asia-Pacific | passenger | 0 | 0 | 80 | 40 | 4 | Qantas Group | ⚠ |
| carrier:000070 | HK Express | UO | Asia-Pacific | passenger | 0 | 38 | 0 | 38 | 4 | Cathay Group | ⚠ |
| carrier:000153 | Kenya Airways | KQ | Africa | passenger | 9 | 15 | 10 | 38 | 4 |  | ⚠ |
| carrier:000096 | Pakistan International Airlines | PK | Asia-Pacific | passenger | 5 | 25 | 0 | 35 | 4 |  | ⚠ |
| carrier:000131 | Porter Airlines | PD | Americas | passenger | 0 | 0 | 70 | 35 | 4 |  | ⚠ |
| carrier:000142 | JetSMART | JA | Americas | passenger | 0 | 35 | 0 | 35 | 4 |  | ⚠ |
| carrier:000073 | Jin Air | LJ | Asia-Pacific | passenger | 4 | 24 | 0 | 32 | 4 | Korean Air Group | ⚠ |
| carrier:000097 | SriLankan Airlines | UL | Asia-Pacific | passenger | 8 | 15 | 0 | 31 | 4 |  | ⚠ |
| carrier:000052 | Air China Cargo |  | Asia-Pacific | cargo | 15 | 0 | 0 | 30 | None | Air China Group | ⚠ |
| carrier:000121 | Horizon Air | QX | Americas | passenger (CPA) | 0 | 0 | 60 | 30 | 4 | Alaska Air Group | ⚠ |
| carrier:000158 | Air Peace | P4 | Africa | passenger | 2 | 20 | 8 | 28 | 4 |  | ⚠ |
| carrier:000080 | Indonesia AirAsia | QZ | Asia-Pacific | passenger | 0 | 25 | 0 | 25 | 4 | AirAsia Group | ⚠ |
| carrier:000141 | Sky Airline | H2 | Americas | passenger | 0 | 25 | 0 | 25 | 4 |  | ⚠ |
| carrier:000156 | Airlink | 4Z | Africa | passenger | 0 | 0 | 50 | 25 | 4 |  | ⚠ |
| carrier:000082 | AirAsia X | D7 | Asia-Pacific | passenger | 8 | 5 | 0 | 21 | 4 | AirAsia Group | ⚠ |
| carrier:000054 | China Cargo Airlines | CK | Asia-Pacific | cargo | 10 | 0 | 0 | 20 | None | China Eastern Airlines Group | ⚠ |
| carrier:000081 | Philippines AirAsia | Z2 | Asia-Pacific | passenger | 0 | 20 | 0 | 20 | 4 | AirAsia Group | ⚠ |
| carrier:000157 | FlySafair | FA | Africa | passenger | 0 | 20 | 0 | 20 | 4 |  | ⚠ |
| carrier:000159 | Tunisair | TU | Africa | passenger | 0 | 20 | 0 | 20 | 4 |  | ⚠ |
| carrier:000152 | South African Airways | SA | Africa | passenger | 5 | 8 | 0 | 18 | 4 |  | ⚠ |
| carrier:000015 | Air France HOP | A5 | Europe | passenger | 0 | 0 | 30 | 15 | 4 | Air France-KLM | ⚠ |
| carrier:000160 | Air Mauritius | MK | Africa | passenger | 5 | 0 | 5 | 12.5 | 4 |  | ⚠ |
| carrier:000063 | ANA Wings | EH | Asia-Pacific | passenger | 0 | 0 | 20 | 10 | 4 | ANA Holdings | ⚠ |
| carrier:000155 | RwandAir | WB | Africa | passenger | 0 | 10 | 0 | 10 | 4 |  | ⚠ |
| carrier:000066 | J-Air | XM | Asia-Pacific | passenger | 0 | 0 | 18 | 9 | 4 | Japan Airlines Group | ⚠ |
| carrier:000013 | LEVEL |  | Europe | passenger | 0 | 8 | 0 | 8 | 4 | International Airlines Group | ⚠ |
| carrier:000007 | Air Dolomiti | EN | Europe | passenger | 0 | 0 | 12 | 6 | 4 | Lufthansa Group | ⚠ |
| carrier:000020 | Martinair | MP | Europe | cargo | 3 | 0 | 0 | 6 | None | Air France-KLM | ⚠ |
| carrier:000107 | Riyadh Air |  | Middle East & Gulf | passenger | 0 | 0 | 0 | 0 | 4 |  | ⚠ |
| carrier:000122 | Spirit Airlines | NK | Americas | passenger | 0 | 0 | 0 | 0 | 4 |  | ⚠ |

## Airports with needs_verification=1

| entity_id | IATA | airport | country | pax (M) | tier | hub |
| --- | --- | --- | --- | ---: | ---: | :-: |
| airport:000094 | PVG | Shanghai Pudong International | China | 77 | 1 | ● |
| airport:000095 | CAN | Guangzhou Baiyun International | China | 76 | 1 | ● |
| airport:000098 | PEK | Beijing Capital International | China | 67 | 1 | ● |
| airport:000101 | SZX | Shenzhen Bao'an International | China | 60 | 1 | ● |
| airport:000049 | BCN | Barcelona-El Prat | Spain | 55 | 1 | ● |
| airport:000102 | BOM | Chhatrapati Shivaji Maharaj International | India | 55 | 1 | ● |
| airport:000103 | CTU | Chengdu Shuangliu International | China | 55 | 1 | ● |
| airport:000105 | CGK | Soekarno-Hatta International | Indonesia | 54 | 1 | ● |
| airport:000011 | SFO | San Francisco International | United States | 53 | 1 | ● |
| airport:000104 | HKG | Hong Kong International | Hong Kong | 53 | 1 | ● |
| airport:000012 | SEA | Seattle-Tacoma International | United States | 52 | 1 | ● |
| airport:000082 | DOH | Hamad International | Qatar | 52 | 1 | ● |
| airport:000013 | PHX | Phoenix Sky Harbor International | United States | 50 | 1 | ● |
| airport:000014 | EWR | Newark Liberty International | United States | 50 | 1 | ● |
| airport:000106 | SHA | Shanghai Hongqiao International | China | 50 | 1 | ● |
| airport:000123 | MNL | Ninoy Aquino International | Philippines | 50 | 1 | ● |
| airport:000050 | FCO | Rome Fiumicino | Italy | 49 | 2 | ● |
| airport:000083 | JED | King Abdulaziz International | Saudi Arabia | 49 | 2 | ● |
| airport:000015 | IAH | George Bush Intercontinental | United States | 48 | 2 | ● |
| airport:000107 | TPE | Taiwan Taoyuan International | Taiwan | 48 | 2 | ● |
| airport:000031 | MEX | Mexico City International | Mexico | 46 | 2 | ● |
| airport:000108 | PKX | Beijing Daxing International | China | 45 | 2 | ● |
| airport:000109 | NRT | Tokyo Narita | Japan | 42 | 2 | ● |
| airport:000110 | BLR | Kempegowda International | India | 40 | 2 | ● |
| airport:000112 | SGN | Tan Son Nhat International | Vietnam | 40 | 2 | ● |
| airport:000113 | TFU | Chengdu Tianfu International | China | 40 | 2 | ● |
| airport:000084 | RUH | King Khalid International | Saudi Arabia | 38 | 2 | ● |
| airport:000055 | SVO | Moscow Sheremetyevo | Russia | 36 | 2 | ● |
| airport:000115 | HAN | Noi Bai International | Vietnam | 30 | 2 | ● |
| airport:000116 | KIX | Osaka Kansai International | Japan | 30 | 2 | ● |
| airport:000128 | CAI | Cairo International | Egypt | 30 | 2 | ● |
| airport:000022 | SLC | Salt Lake City International | United States | 27 | 2 | ● |
| airport:000023 | BWI | Baltimore/Washington International | United States | 27 | 2 | ● |
| airport:000063 | MXP | Milan Malpensa | Italy | 27 | 2 | ● |
| airport:000024 | SAN | San Diego International | United States | 26 | 2 | ● |
| airport:000028 | YVR | Vancouver International | Canada | 26 | 2 | ● |
| airport:000118 | CCU | Netaji Subhas Chandra Bose International | India | 26 | 2 | ● |
| airport:000025 | DCA | Ronald Reagan Washington National | United States | 25 | 2 | ● |
| airport:000064 | OSL | Oslo Gardermoen | Norway | 25 | 2 | ● |
| airport:000065 | ARN | Stockholm Arlanda | Sweden | 25 | 2 | ● |
| airport:000066 | BER | Berlin Brandenburg | Germany | 25 | 2 | ● |
| airport:000117 | HYD | Rajiv Gandhi International | India | 25 | 2 | ● |
| airport:000124 | DMK | Bangkok Don Mueang | Thailand | 25 | 2 | ● |
| airport:000126 | HAK | Haikou Meilan International | China | 25 | 2 | ● |
| airport:000038 | SCL | Arturo Merino Benítez International | Chile | 24 | 3 | ● |
| airport:000039 | LIM | Jorge Chávez International | Peru | 24 | 3 | ● |
| airport:000067 | DUS | Düsseldorf Airport | Germany | 24 | 3 |  |
| airport:000119 | BNE | Brisbane Airport | Australia | 23 | 3 | ● |
| airport:000120 | MAA | Chennai International | India | 22 | 3 |  |
| airport:000121 | DPS | Ngurah Rai International | Indonesia | 21 | 3 |  |
| airport:000086 | TLV | Ben Gurion International | Israel | 19 | 3 |  |
| airport:000035 | BSB | Brasília International | Brazil | 15 | 3 | ● |
| airport:000042 | AEP | Jorge Newbery Airfield | Argentina | 14 | 3 |  |
| airport:000129 | ADD | Addis Ababa Bole International | Ethiopia | 14 | 3 | ● |
| airport:000130 | CMN | Mohammed V International | Morocco | 12 | 3 |  |
| airport:000036 | GIG | Rio de Janeiro-Galeão International | Brazil | 11 | 3 |  |
| airport:000041 | EZE | Ministro Pistarini International | Argentina | 11 | 3 |  |
| airport:000131 | CPT | Cape Town International | South Africa | 10 | 3 |  |
| airport:000091 | AMM | Queen Alia International | Jordan | 9 | 4 |  |
| airport:000077 | KEF | Keflavík International | Iceland | 8 | 4 |  |
| airport:000132 | LOS | Murtala Muhammed International | Nigeria | 8 | 4 |  |
| airport:000133 | NBO | Jomo Kenyatta International | Kenya | 8 | 4 |  |
| airport:000134 | ALG | Houari Boumediene | Algeria | 8 | 4 |  |
| airport:000078 | DLM | Dalaman Airport | Türkiye | 5 | 4 |  |
| airport:000135 | TUN | Tunis-Carthage | Tunisia | 5 | 4 |  |
| airport:000136 | ACC | Kotoka International | Ghana | 5 | 4 |  |
| airport:000079 | BJV | Milas-Bodrum | Türkiye | 4 | 4 |  |
| airport:000137 | MRU | Sir Seewoosagur Ramgoolam International | Mauritius | 4 | 4 |  |
| airport:000138 | DKR | Blaise Diagne International | Senegal | 3 | 4 |  |
| airport:000139 | ABJ | Félix-Houphouët-Boigny International | Côte d'Ivoire | 3 | 4 |  |
| airport:000140 | KGL | Kigali International | Rwanda | 2 | 4 |  |

## Entity history

| entity_id | kind | value | valid_from | valid_to | verify |
| --- | --- | --- | --- | --- | :-: |
| airport:000044 | iata | IST | 2019-04-06 |  | ⚠ |
| airport:000080 | iata | IST |  | 2019-04-06 | ⚠ |
| carrier:000092 | alias | Vistara |  | 2024-11-12 | ⚠ |
| carrier:000037 | alias | Alitalia |  | 2021-10-14 | ⚠ |
| carrier:000023 | alias | AnadoluJet |  | 2024-03-22 | ⚠ |
| carrier:000023 | alias | Anadolu Jet |  | 2024-03-22 | ⚠ |
| carrier:000136 | alias | LAN Airlines |  | 2016-05-05 | ⚠ |
