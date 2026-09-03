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
