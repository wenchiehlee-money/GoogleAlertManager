# AI 伺服器

Record type: `theme_competitive_group_context`
Theme source: `My-TW-Coverage/data/themes/AI_伺服器.json` (canonical `competitive_groups`/`extra_entities`; company names cross-checked against the same repo's own rendered `output/themes/AI_伺服器.md`)
Skill: `skill-theme-competitor-groups-curate`
Canonical commit checked: `f9a5c74c3` (`git log -1 -- data/themes/AI_伺服器.json` at time of this sync)
Last synced: 2026-09-03
Evidence scope: local repository annotation; not a company fact, research publisher view, market flow fact, or consensus signal. Distinct from `data/competitors/{stock_id}_competitors.json` (synced separately via `skill-theme-competitor-analysis`'s `relationship_type` classification, read by `src/analysis/competitors.py`) -- this file is theme-level peer grouping, that one is per-stock competitor relationships; the two are related but not the same dataset, see `skill-theme-competitor-groups-curate`'s SKILL.md "Alignment requirement".

## Purpose

Full mirror of canonical's 13 curated `competitive_groups` for the AI 伺服器 theme, for use when contextualizing an alert/news item about a stock in this supply chain (e.g. "this stock's peers in the same competitive segment"). Classification layer only -- do not use to validate financial figures, analyst views, or trading flow.

## Competitive Groups

Company names below are the subset canonical's own `output/themes/AI_伺服器.md` could resolve (has enrichment/market-cap data); a ticker canonical's JSON lists but its own render could not resolve is listed under "Unresolved in canonical's own render" -- not independently guessed.

| Group | Tickers (resolved) | Companies | Unresolved in canonical's own render |
|---|---|---|---|
| ODM/系統整合 (AI 伺服器代工) | `2317`, `6669`, `2382`, `3231`, `2356`, `2324`, `3706`, `7711`, `3693`, `6933`, `6117` | 鴻海、緯穎、廣達、緯創、英業達、仁寶、神達、永擎、營邦、AMAX-KY、迎廣 | `4938`（和碩 — well-known ticker, but canonical's own render doesn't show it） |
| 品牌伺服器/主機板/顯卡 | `2357`, `2376`, `2377`, `3515`, `DELL`, `0992.HK` | 華碩、技嘉、微星、華擎、Dell、聯想 | `2353`, `2465`, `HPE` |
| 電源供應器 | `2308`, `2301`, `6412`, `3015` | 台達電、光寶科、群電、全漢 | `6282`, `2385` |
| 不斷電系統 (UPS)/電源管理 | `6409` | 旭隼 | `3043`, `3628` |
| 散熱模組/液冷 | `3017`, `3653`, `3324`, `3338` | 奇鋐、健策、雙鴻、泰碩 | `6224`, `4545`, `5223` |
| 伺服器機殼/機構件 | `2059`, `8210`, `6584`, `3013`, `5426` | 川湖、勤誠、南俊國際、晟銘電、振發 | `2354`（鴻準） |
| 連接器/線材 | `3665`, `3533`, `6290`, `3217`, `6220` | 貿聯-KY、嘉澤、良維、優群、岳豐 | `6197`, `2440`, `6833`, `3710` |
| ABF 載板/PCB | `3037`, `8046`, `4958`, `2368`, `3044` | 欣興、南電、臻鼎-KY、金像電、健鼎 | （none — all 5 resolved） |
| 銅箔基板 (CCL) | `2383` | 台光電 | （none — all 1 resolved） |
| 筆電鍵盤 | — | — | `8163`, `2387`, `5215`（none resolved in canonical's render） |
| 精密塑膠模具/射出成型 | — | — | `3679`, `3290`（none resolved in canonical's render） |
| 資料中心配電 (PDU) | `3002` | 歐格 | `3296` |
| 被動元件 | `2327`, `2492` | 國巨、華新科 | `2478` |

## Usage Rules

- Use `competitive_groups` for peer comparison only when the companies compete by product/business-model overlap.
- Do not infer research consensus or institutional trading behavior from this theme page.
- **Before treating this page as current, re-check it against canonical** — see `skill-theme-competitor-groups-curate`'s Consumer/Annotation Workflow step 0 (consistency check), added specifically because `TW-institutional-research`'s copy of this same theme silently drifted from canonical for ~2 months before being caught.
