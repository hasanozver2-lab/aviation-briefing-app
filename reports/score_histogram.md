# Score histogram of the clustered story set

109 real articles collected over 48 hours became **98 stories** after cross-language clustering (the set the selection threshold works on). Scores are relevance v2 (provisional). `min_score` is unchanged (45); the decision is the owner's.

'Before' = main as merged (clustering, finance gate, military exclusion). 'After' = this branch (adds `route_network_change` and the finance-commentary filter).

## Distribution

| score | before | after | examples (after): score · type · headline |
| --- | ---: | ---: | --- |
| 0-25 | 52 | 56 | 24.5 · - · Frontier Airlines Passengers Stranded Overnight After Crew Timeout From Weather <br>10.5 · - · 300+ Engines: Major Airline Signs Huge Deal To Power Its Boeing 737 MAX Fleet<br>4.5 · - · **EXCLUDED: commentary** · Boeing Price Target Slashed To $235 By RBC – Firm Says Lingering Defense Budget  |
| 25-35 | 20 | 18 | 30.5 · - · SAS targets ‘spread and depth’ through long-haul expansion<br>30.5 · - · Lufthansa, TAP Air Portugal yarışında Air France-KLM’yi geride bıraktı<br>30.5 · - · Lufthansa could transfer eight Airbus A350 jets to TAP after 2030 |
| 35-45 | 13 | 10 | 43.5 · - · Emirates brings global travel rehearsal programme to Colombia<br>36.5 · - · Condor chief outlines ‘bleisure’ transformation and blasts European airline regu<br>35.0 · - · Boeing (BA) Heads Into Talks Over Up To 50 Wide Body Jets |
| 45-55 | 8 | 7 | 51.5 · route_network_change · ITA Airways to resume Rome-Caracas flights after 12-year absence<br>48.8 · geopolitics_airspace · **EXCLUDED: military** · MSB’den F-35 ve C-130J açıklaması: 6 savaş uçağı için temaslar sürüyor<br>48.8 · safety_incident · ACT Airlines’ın Hong Kong kazasında yeni gelişme: Boeing 747-400’de teknik arıza |
| 55-65 | 3 | 4 | 62.0 · operations_disruption · Vali Gül açıkladı: İstanbul Havalimanı’nda 19 sefer iptal edildi, 51 uçak divert<br>58.0 · fleet_orders · Aviation Capital Group Grows Portfolio with Order for 75 Airbus A320neo Family A (5 publishers)<br>57.5 · route_network_change · Air Canada Launches Nonstop Flights To New US City: See Map Now |
| 65-75 | 1 | 2 | 70.5 · route_network_change · New Lufthansa Airbus A350-1000 to fly first to Tokyo<br>65.5 · route_network_change · Lufthansa selects Tokyo as first destination for Airbus A350-1000 (2 publishers) |
| 75-+ | 1 | 1 | 78.0 · fleet_orders · Turkish Airlines and CFM sign MOU for more than 600 LEAP-1B engines (4 publishers) |

## Stories that would be selected at each threshold (excluded ones never count; no per-run cap applied)

| min_score | before | after |
| ---: | ---: | ---: |
| 35 | 21 | 19 |
| 40 | 13 | 13 |
| 45 | 9 | 10 |
| 50 | 5 | 8 |
| 55 | 5 | 7 |
| 60 | 4 | 5 |

Excluded from the list: before {'military': 6}, after {'commentary': 7, 'military': 6}.

## Stories now classified as route_network_change

| score | publishers | headline |
| ---: | ---: | --- |
| 70.5 | 1 | New Lufthansa Airbus A350-1000 to fly first to Tokyo |
| 65.5 | 2 | Lufthansa selects Tokyo as first destination for Airbus A350-1000 |
| 57.5 | 1 | Air Canada Launches Nonstop Flights To New US City: See Map Now |
| 51.5 | 1 | ITA Airways to resume Rome-Caracas flights after 12-year absence |
