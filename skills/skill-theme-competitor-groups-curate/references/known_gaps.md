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

## Decided: which skill has authority over group *membership* vs per-stock *detail* (2026-09-03)

This was raised as an apparent conflict: `../biztrends.TW`'s `skill-theme-competitor-analysis`
classifies AI 伺服器's ODM-group companies at a finer grain than this theme's `competitive_groups`
does -- its `output/focus/{stock}/company_competitor_analysis_{stock}.csv` for 2382 (廣達) tags:

- `odm_peer` (notebook-centric ODM peers): 2324 仁寶, 4938 和碩
- `server_peer` (server-focused peers): 2317 鴻海, 2356 英業達, 3231 緯創, 6669 緯穎

`data/themes/AI_伺服器.json`'s `ODM/系統整合 (AI 伺服器代工)` group merges all of the above (plus
2382 itself, 3706, 6933, 3693, 7711, 6117) into one undifferentiated group.

An earlier version of this note (and of `skill-theme-competitor-analysis`'s own SKILL.md)
claimed the opposite authority direction -- that `relationship_type` was "canonical" and this
skill's groups were expected to conform to it. **That was backwards and has been corrected in
both skills' SKILL.md.** The user's explicit decision when this was raised:

1. **This skill (`skill-theme-competitor-groups-curate`) defines the group and its member
   mapping** -- `competitive_groups` in `data/themes/*.json` is authoritative for *which
   companies belong to which theme group*.
2. **Given that group, `skill-theme-competitor-analysis` supplies the detail** -- per-stock
   `relationship_type` and quarterly financial comparison data for the members this skill's
   groups already define. It does not redefine or override group membership.

So the actual, still-open follow-up is a **membership check, not a re-splitting exercise**: does
every company `skill-theme-competitor-analysis` classifies with a `relationship_type` for a given
stock also appear somewhere in that stock's theme's `competitive_groups`? In this case, yes --
all 6 companies above (2324/4938/2317/2356/3231/6669) are already members of AI 伺服器's
`ODM/系統整合` group, so there is no actual membership gap here. `skill-theme-competitor-analysis`'s
finer `odm_peer`/`server_peer` split is a detail layer on top of that membership, not a
disagreement about who belongs in the group -- do not use it as grounds to split the group.
`check_group_consistency.py` extending to automate this membership check (not a granularity
check) remains the known follow-up.
