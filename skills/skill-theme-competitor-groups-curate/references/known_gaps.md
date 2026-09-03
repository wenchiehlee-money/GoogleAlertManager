# Known TPEx Source-Data Gaps

`data/themes/*.json` `theme_supply_chain` criteria match against
`../biztrends.TW/data/ic.tpex.org.tw/raw_SupplyChain_{chain_code}.csv`, which is scraped
directly from TPEx's own industry-chain pages (`https://ic.tpex.org.tw/introduce.php?ic={chain_code}`).
That page's company-to-subcategory tagging is maintained by TPEx, not computed from revenue
mix, and it has confirmed gaps: a company can be a major, well-known player in a segment and
simply not be tagged into the matching subcategory node on TPEx's own site.

This file tracks gaps found while curating theme groupings, so the same investigation doesn't
have to be repeated. When you find a new one, add it here and (if the company matters for that
theme) inject it via `extra_entities` in the theme's JSON.

## `F000` 電腦及週邊設備 chain — `伺服器` subcategory

Confirmed via `grep ",2382,\|,2317,\|,2357,\|,6669,\|,3706,\|,3231,\|,2356," raw_SupplyChain_F000.csv`
(all rows from the same `download_timestamp`, so this is not a stale-data artifact):

| Ticker | Company | Tagged `伺服器`? | Actually an AI-server player? |
|---|---|---|---|
| 2317 | 鴻海 | Yes | Yes |
| 6669 | 緯穎 | Yes | Yes |
| 2357 | 華碩 | Yes | Yes |
| 3706 | 神達 | Yes | Yes |
| **2382** | **廣達** | **No** (only tagged 筆記型電腦 downstream / 其他電腦及週邊設備之零組件 upstream) | Yes — AI server revenue > 65% of total per its own business summary |
| **2356** | **英業達** | **No** (only tagged 筆記型電腦) | Yes — AI server ~45% of server revenue |
| **3231** | **緯創** | **No** (only tagged 筆記型電腦/桌上型電腦/其他電腦及週邊設備) | Yes — key NVIDIA DGX GPU baseboard supplier |
| **0992.HK** | **聯想 (Lenovo)** | **No** (only tagged 筆記型電腦/桌上型電腦/精簡型電腦) | Yes — Lenovo ISG is a top-3 global server brand; already injected via `extra_entities` in `data/themes/AI_伺服器.json` |

Practical takeaway: do not assume a company is absent from a theme's product line just because
it's untagged in the matching TPEx subcategory. Verify against the company's own business
summary (`output/enrichment_all_rendered/*.md`) before ruling it out.

## Decided: AI 伺服器's `ODM/系統整合` group intentionally stays merged (not split by biztrends.TW's finer relationship_type)

`../biztrends.TW`'s `skill-theme-competitor-analysis` classifies these same companies at a
finer grain than this theme's `competitive_groups` does -- its
`output/focus/{stock}/company_competitor_analysis_{stock}.csv` for 2382 (廣達) tags:

- `odm_peer` (notebook-centric ODM peers): 2324 仁寶, 4938 和碩
- `server_peer` (server-focused peers): 2317 鴻海, 2356 英業達, 3231 緯創, 6669 緯穎

`data/themes/AI_伺服器.json`'s `ODM/系統整合 (AI 伺服器代工)` group merges all of the above (plus
2382 itself, 3706, 6933, 3693, 7711, 6117) into one undifferentiated group. This is this
skill's own known, not-yet-implemented gap per SKILL.md's "Alignment requirement" section
("Extending `check_group_consistency.py` to diff directly against `skill-theme-competitor-
analysis`'s CSV output is a known follow-up, not yet implemented").

**Decision (2026-09-03, explicit user call when raised): keep this theme's grouping merged as
one `ODM/系統整合` competitive group. Do not split it to match biztrends.TW's odm_peer/server_peer
distinction.** Rationale as given: the theme-level grouping answers "who are AI-server-supply-
chain peers for AI 伺服器 research" (one competitive question), while biztrends.TW's
`relationship_type` answers a narrower per-stock revenue-mix question (notebook-ODM vs
server-ODM peer, for that skill's own financial peer-comparison use case) -- the two skills are
allowed to classify at different granularity for their different purposes; this is not a bug to
converge. If this decision needs revisiting later, re-open it explicitly rather than silently
"fixing" the merged group to match biztrends.TW.
