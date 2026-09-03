# Theme Curation TODO

Tracks which `data/themes/*.json` themes have real `competitive_groups` curated (per
`SKILL.md`'s workflow) versus which are still rendering companies grouped only by raw
IC-taxonomy subcategory or GICS sector fallback (accurate scope, inaccurate "who competes with
whom"). Update this file whenever a theme is cooked or a new theme is added.

Sorted by company count (`output/themes/README.md`) descending — larger themes have the
messiest fallback buckets and the most value from curation, so work top-down unless the user
asks for a specific theme.

## Cooked

| Theme | Companies | competitive_groups | extra_entities | Notes |
|---|---:|---:|---:|---|
| AI 伺服器 | 380 | 12 | 1 (聯想, TPEx 伺服器子分類缺漏) | Also has `theme_supply_chain` (IC taxonomy F000/5300); see `references/known_gaps.md` |
| 資料中心 | 111 | 21 | 4 (鴻海/仁寶/和碩/華擎 — enrichment 文字缺「[[資料中心]]」wikilink) | No `theme_supply_chain` — pure context-match theme, so this class of gap (relevant company simply never mentions the theme's exact tag string) is systemic, not a one-off; see note below. One intentional boundary case left un-merged: 3163 波若威 (光被動元件) vs 4979 華星光 (光收發模組主動元件) — `relationships.competitors` links them but they're genuinely different product segments |

## Not yet cooked

| Theme | Companies | Priority notes |
|---|---:|---|
| 電動車 | 169 | Large, un-cooked — next best candidate by size |
| 5G | 138 | Large, un-cooked |
| NVIDIA 供應鏈 | 114 | Brand-supply-chain theme type — check `related_entities`/`anchor_entities` semantics differ from product themes before reusing the same workflow verbatim |
| Apple 供應鏈 | 100 | Same brand-supply-chain type as NVIDIA 供應鏈 |
| 低軌衛星 | 55 | |
| Tesla 供應鏈 | 55 | Brand-supply-chain theme type |
| 矽晶圓 | 45 | |
| CoWoS | 39 | Has `theme_supply_chain`? verify before assuming pure context-match |
| 碳化矽 | 24 | |
| 氮化鎵 | 20 | |
| 矽光子 | 17 | Heavy overlap with 資料中心's optical groups (光收發模組/光被動元件/化合物半導體磊晶) — reuse those groupings as a starting point rather than re-researching from scratch |
| HBM | 16 | |
| CPO | 14 | Heavy overlap with 矽光子/資料中心 optical groups — same reuse note |
| ABF 載板 | 14 | Heavy overlap with AI 伺服器's ABF 載板/PCB and 銅箔基板 (CCL) groups — reuse |
| VCSEL | 10 | |
| EUV | 10 | |
| 光阻液 | 6 | |
| 磷化銦 | 6 | Heavy overlap with 資料中心's 化合物半導體磊晶/晶圓代工 group — reuse |

## Segment weight cross-check: informational only, not a gate

`check_group_consistency.py` also prints AI-canonical-cycle segment weights (from
`../biztrends.TW/output/company_cycle_major_weights.csv`) for curated group members that have
them. This was deliberately kept informational-only rather than a real cross-check gate: as of
this writing that CSV has ~20 rows total across all Taiwan tickers, so most group members will
simply show no data — that's expected, not a red flag. There is also no reliable theme-level
revenue total to normalize weights against (the CSV is per-company disclosed revenue mix, not a
market-size model), so "company X has a low/no AI_Server_Rack weight" cannot be used to argue it
doesn't belong in a group. Don't try to upgrade this into a hard filter without first solving
both of those data gaps.

## Pure context-match themes systematically under-collect

Themes without `theme_supply_chain` (資料中心 today; likely others on the not-yet-cooked list)
only pull in a company if its own `data/enrichment_all/{ticker}.json` business text happens to
contain the theme's exact tag as a `[[wikilink]]`. A company can be a huge, obvious participant
in that theme's real supply chain and still be silently absent just because its summary uses a
related-but-different phrase (e.g. 鴻海's summary says "AI 伺服器"/"雲端及網路" but never
"資料中心" verbatim, so it was missing from 資料中心 until added via `extra_entities`; 仁寶/和碩/
華擎 had the same gap). When cooking a context-match theme, don't just curate the companies
already present — spot-check a handful of obviously-relevant companies from a sibling theme
(e.g. companies already grouped in AI 伺服器) to see if they're missing here too, the way 鴻海/
仁寶/和碩/華擎 were found. The durable fix is adding the missing wikilink to the company's own
enrichment JSON (`skill-company-enrichment-json`'s job); `extra_entities` is the
immediate stopgap.

## Cross-theme reuse note

Several un-cooked themes (矽光子, CPO, 磷化銦) substantially overlap the optical/compound-
semiconductor companies already researched and grouped in 資料中心's `competitive_groups`
(光收發模組/光通訊主動元件, 光被動元件, 化合物半導體磊晶/晶圓代工). When cooking those themes,
start from that existing grouping rather than re-reading every company's business summary from
scratch — just re-verify the subset of members that actually appear in the new theme's dataset.
