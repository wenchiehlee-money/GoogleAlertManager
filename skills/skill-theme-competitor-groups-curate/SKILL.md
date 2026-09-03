---
name: skill-theme-competitor-groups-curate
description: >-
  Curate or consume accurate within-theme competitor groupings. In a theme-owner repo, edit
  data/themes/*.json (`competitive_groups`, `extra_entities`) and render output/themes/*.md.
  In a consumer repo that lacks data/themes/ or output/themes/, locate/read the canonical theme
  repo and produce a local theme/competitive_groups annotation without running the renderer. Use
  when companies need grouping by real product/business-model overlap rather than broad sector,
  IC-taxonomy subcategory, or supply-chain adjacency.
---

# Theme Competitor Groups Curate Skill

## Purpose

`output/themes/*.md` pages (built by `scripts/build_themes.py` from `data/themes/*.json` +
`data/enrichment_all/*.json`) exist to show, within one theme, which companies are actual
competitors of each other. The raw grouping signals available by default are too coarse for
that:

- IC-taxonomy subcategories (e.g. `其他電腦及週邊設備之零組件`) are catch-all buckets that mix
  unrelated business models.
- GICS/yfinance `profile.industry` sector labels (e.g. `Computer Hardware`) are even broader.
- The upstream TPEx `ic.tpex.org.tw` supply-chain pages this data is scraped from have real,
  confirmed gaps — a company can be a major player in a segment and simply not be tagged into
  the matching subcategory (see `references/known_gaps.md`).

This skill curates `data/themes/*.json`'s `competitive_groups` (regroup companies already in
the theme's dataset by real competitive segment) and `extra_entities` (inject a company the
source taxonomy omits entirely) so the rendered page groups true competitors together, and
keeps that grouping consistent with each company's own canonical competitor list maintained by
[skill-theme-competitor-analysis](../skill-theme-competitor-analysis/SKILL.md) /
[skill-company-enrichment-json](../skill-company-enrichment-json/SKILL.md)
(`data/enrichment_all/{ticker}.json` → `relationships.competitors`).

**Alignment requirement (authority direction corrected 2026-09-03 — see
`references/known_gaps.md` for the full history of the earlier, backwards version of this
paragraph, and `skill-theme-competitor-analysis`'s own SKILL.md for the matching correction
there)**: `competitive_groups` in this skill's `data/themes/*.json` is the authoritative
definition of **which companies belong to which competitive group** for a theme. Every member of
one of this skill's groups should also be classifiable by `skill-theme-competitor-analysis`'s
`relationship_type` (`brand_competitor`/`foundry_competitor`/`odm_peer`/`server_peer`/
`chip_competitor`, in `output/focus/{stock}/company_competitor_analysis_{stock}.csv`) — that
skill does not decide group *membership*, it supplies the detailed per-stock
financial/relationship data for members this skill's groups already define. A finer split that
skill's `relationship_type` draws within one group (e.g. `odm_peer` vs `server_peer` inside AI
伺服器's merged `ODM/系統整合` group) is not by itself a reason to split the group here — see the
worked example in `references/known_gaps.md`.

The check that *is* this skill's own responsibility: does every `relationship_type`-classified
peer for a stock in one of this skill's groups actually appear somewhere in that theme's
`competitive_groups` (in the right group or a defensible adjacent one)? `check_group_consistency.py`
today only cross-checks against `relationships.competitors` in `data/enrichment_all/*.json` — a
separate, text-extracted competitor list that is not guaranteed to be derived from
`skill-theme-competitor-analysis`'s own output. Treat that as an indirect proxy, not proof of
alignment: when curating a theme, spot-check disputed group members against
`skill-theme-competitor-analysis`'s actual `relationship_type` output for that stock, and prefer
its rule-based classification over `relationships.competitors` when deciding whether a company
is *missing from this skill's theme dataset entirely* (a real gap to fix here) — not as license to
re-split or re-define groups that already contain the company. Extending
`check_group_consistency.py` to diff directly against `skill-theme-competitor-analysis`'s CSV
output for this membership check is a known follow-up, not yet implemented.

## Operating Modes

Use the mode that matches the current workspace.

- **Theme-owner mode**: the current repo has `data/themes/`, `output/themes/`,
  `data/enrichment_all/`, and `scripts/build_themes.py`. In this mode, curate the canonical
  theme JSON and run the renderer/consistency checks.
- **Consumer/annotation mode**: the current repo does not own theme files, but the task needs a
  theme or `competitive_groups` classification for local notes, research records, media OCR, or
  downstream structured data. In this mode, do not treat missing `data/themes/` or
  `output/themes/` as a blocker. Locate a nearby canonical theme repo, read its existing theme
  files and rendered business summaries, then write only the requested local annotation/artifact
  in the current repo.

## Consumer/Annotation Workflow

Use this workflow when the current repo lacks `data/themes/` or `output/themes/`. Keep the user
update neutral: say that the current repo is a consumer of theme mappings, not that the workflow
will not run.

> [!IMPORTANT]
> A prior local annotation is **not** trustworthy just because it exists and cites a canonical
> source path — a `TW-institutional-research` copy of the AI 伺服器 theme was stale from the day
> it was created (captured only 2 of canonical's 13 `competitive_groups`, and even those 2
> predated a canonical commit that had already expanded one of them) and sat undetected for
> weeks before a user caught it by asking. Step 0 exists specifically to prevent that recurring
> silently in any consumer repo, this one included.

0. **If a local annotation for this theme already exists, verify it before reusing it — do not
   assume it's current.** Run:

   ```bash
   cd <canonical repo>
   git log -1 --format="%H %ci %s" -- data/themes/<theme>.json
   git status --short -- data/themes/<theme>.json   # confirm no uncommitted local drift on the canonical side itself
   ```

   Compare the canonical commit hash/date against the local annotation's own "Canonical commit
   checked" / "Last synced" line (add these fields if the existing annotation predates this rule
   and lacks them). If canonical has moved since the annotation was last synced — or the
   annotation has no recorded sync point at all — re-derive it from steps 1-4 below rather than
   trusting the existing content. Spot-check at least the `competitive_groups` count and one
   group's ticker list against canonical; do not assume "it looks complete" without counting.

1. **Locate the canonical theme repository.** Prefer an explicit user path if provided. Otherwise
   check likely sibling repositories and require these files before using one:

   ```bash
   find .. -maxdepth 3 -type d -path '*/data/themes' -print
   find .. -maxdepth 3 -type f -path '*/scripts/build_themes.py' -print
   ```

   A usable canonical repo should have `data/themes/*.json`; rendered summaries in
   `output/enrichment_all_rendered/*.md` are strongly preferred. If there are multiple matches,
   choose the one whose theme file names/tags match the requested domain, and state which repo
   you used.

2. **Read, do not edit, canonical inputs.** For the requested theme, read the matching
   `data/themes/<theme>.json`. Read rendered business summaries for only the companies being
   classified. If the canonical repo is outside the current writable root, do not edit it unless
   the user explicitly asks to curate the source theme repo.

3. **Classify local records by true competitive overlap.** Reuse canonical
   `competitive_groups` when a company already appears there. For companies not in a canonical
   group, classify them as adjacent/supplier/channel/singleton only when supported by their
   business summary. Do not force distributors, OSATs, components vendors, customers, or suppliers
   into an ODM/brand/server peer group merely because they appear in the same media table or
   supply chain theme.

4. **Write a local annotation.** Add a clearly labeled `theme` / `competitive_groups` block to
   the current repo's requested output file, note the canonical source path used, and state that
   the mapping is a classification layer only. It must not validate financial figures, OCR cells,
   research views, market-flow facts, or company facts. Always record the canonical commit hash
   and sync date (e.g. "Canonical commit checked: `<hash>`" / "Last synced: `<date>`") so a future
   step-0 check has something to compare against — an annotation without this is exactly what let
   the AI 伺服器 drift above go undetected.

5. **Validate only what applies locally.** Run local repository validators and formatting checks.
   Skip `scripts/build_themes.py` and `check_group_consistency.py` unless you are operating in
   the canonical theme-owner repo.

## Theme-Owner Workflow

Run from the My-TW-Coverage repository root or another repository that has the theme-owner
layout.

0. **Check `references/curation_status.md`** for which themes are already cooked (have real
   `competitive_groups`) and which are still on the TODO list, sorted by size. Update it when
   you finish a theme. Some un-cooked themes heavily overlap already-cooked ones (e.g. 矽光子/
   CPO/磷化銦 overlap 資料中心's optical groups) — reuse that research instead of starting over.

1. **Pick a target.** Render or re-render the theme and look at its largest fallback buckets
   (group headers that are still a raw subcategory or GICS label, not a curated name):

   ```bash
   python scripts/build_themes.py "<theme tag>"
   rg -n "^\*\*" output/themes/<theme_file>.md
   ```

2. **Research each company in the bucket — never guess.** For every ticker in the bucket, read
   its actual business description and decide whether it genuinely competes with others in the
   bucket:

   ```bash
   sed -n '9,12p' output/enrichment_all_rendered/<ticker>_<company>.md   # 業務簡介
   ```

   Group by **real product/business-model overlap** (who bids for the same orders), not by
   supply-chain adjacency. A supplier to a company is not that company's competitor. If a
   company's true business is unrelated to the theme (e.g. a components distributor, an
   unrelated consumer-electronics maker), leave it in the fallback bucket — do not force a
   grouping that isn't backed by evidence.

3. **Check for a source-data gap.** If a company you know belongs in the theme is missing from
   the whole page, check whether the raw TPEx CSV actually has it tagged under a matching
   chain/subcategory:

   ```bash
   grep -n ",<ticker>," ../biztrends.TW/data/ic.tpex.org.tw/raw_SupplyChain_<chain_code>.csv
   ```

   If the company is tagged under a *different* subcategory only (a real gap, not a wrong
   assumption on your part), add it via `extra_entities` (step 5) instead of forcing it into
   `theme_supply_chain` criteria it doesn't actually match.

4. **Cross-check against canonical competitor data before finalizing.** Run:

   ```bash
   python skills/skill-theme-competitor-groups-curate/scripts/check_group_consistency.py --theme "<theme tag>"
   ```

   This is a pure comparison tool — it never edits anything. It flags two kinds of findings:

   - **Actionable**: a company's `relationships.competitors` names another company that IS in
     this theme's dataset but sits in a *different* group (or an ungrouped fallback bucket).
     This is a real disagreement between the theme grouping and canonical competitor data.
   - **Informational**: a group member has `relationships.competitors` entries, but none
     overlap this group (e.g. its listed competitor is a foreign private company not in the
     dataset, or its competitor data just hasn't been reviewed yet). Not necessarily wrong.

   It also prints a third, purely informational section — AI-canonical-cycle segment weights
   (from `../biztrends.TW/output/company_cycle_major_weights.csv`, the same data
   `skill-theme-competitor-analysis` uses) for any curated group member that happens to have
   them. This is context only, never a grouping signal: coverage is far too sparse (a handful
   of tickers total have disclosed that granularity of revenue mix) and there is no reliable
   theme-level revenue total to normalize against, so a missing or low weight does not mean a
   company doesn't belong — see the discussion in `references/curation_status.md` if this needs
   revisiting later.

   **When the tool reports an actionable finding, stop and ask the user how to resolve it.**
   Verify the suggested addition against the company's own business summary first (step 2)
   before proposing it — the competitor list can itself be stale or `needs_review`. Do not
   silently pick a side. Possible resolutions:

   - Add the missing ticker to the `competitive_groups` entry (most common — the theme
     grouping was just incomplete).
   - Leave the theme grouping as-is if the two companies compete in the parent company's core
     business but not specifically in this theme's product/segment (e.g. a company can be a
     canonical competitor overall while only one of them participates in this particular
     AI-server/CoWoS/whatever product line).
   - Flag `relationships.competitors` itself as needing a fix — that data belongs to
     `skill-company-enrichment-json`, not this skill; do not edit
     `data/enrichment_all/*.json` from this skill without the user's explicit go-ahead.

5. **Edit `data/themes/<theme>.json`.**

   - `competitive_groups`: an ordered list of `{"name": "...", "tickers": [...]}`. Order
     controls display order (curated groups always render before fallback groups, which sort
     by descending total group market cap). A ticker can only belong to one group per theme.
   - `extra_entities`: a list of `{"ticker", "company", "role", "sector", "note"}` for
     companies the source taxonomy never tagged into this theme at all. Always fill `note`
     with what you actually verified (which raw CSV/subcategory you checked and what you found
     missing) — see the existing `聯想` entry in `data/themes/AI_伺服器.json` for the pattern.
     `role` should be `upstream`/`midstream`/`downstream` to match how comparable companies in
     the same segment are tagged, or `related` if there's no clean match.
   - Group names should be a real segment name in Traditional Chinese (e.g. `ODM/系統整合 (AI
     伺服器代工)`, `散熱模組/液冷`), not a copy of the raw subcategory/GICS string.

6. **Rebuild the full site, not just one theme.** `build_themes.py "<tag>"` (single-theme mode)
   overwrites `output/themes/README.md` with only that one theme's entry, wiping every other
   theme from the index. Always finish with a full rebuild:

   ```bash
   python scripts/build_themes.py
   ```

7. **Validate.**

   ```bash
   python -m py_compile scripts/build_themes.py
   python skills/skill-theme-competitor-groups-curate/scripts/check_group_consistency.py --theme "<theme tag>"
   git status --short output/themes/
   ```

   Confirm: the curated group renders with the expected member count and companies; no
   unresolved actionable conflicts remain (or the remaining ones were explicitly left as-is per
   step 4); all themes rebuilt without error; `output/themes/README.md` still lists all themes.

## Rules

- **Never guess group membership.** Every addition must be backed by reading the company's own
  business description (`output/enrichment_all_rendered/*.md`), per the project's "never guess,
  never fill generically" rule in `CLAUDE.md`.
- **Render text stays Traditional Chinese.** Fallback grouping labels come from
  `profile.industry`/`profile.sector`, which are often raw English GICS/yfinance strings (e.g.
  `Computer Hardware`, `Semiconductors`). `scripts/build_themes.py` translates known values via
  `GICS_INDUSTRY_ZH`. If you encounter a new untranslated English label surfacing as a group
  header, add it to that dict rather than leaving it in English.
- **`competitive_groups` groups by product/business-model competition, not supply-chain
  position.** The rendered theme page no longer splits companies into 上游/中游/下游 chapters —
  everything renders under one `## 相關公司` list, grouped only by `competitive_groups` (then
  fallback subcategory/sector). Do not try to reintroduce a positional split; the underlying
  TPEx position tagging was confirmed unreliable enough (see `references/known_gaps.md`) that
  it isn't worth the confusion of splitting a real competitor group across sections.
- **`extra_entities` is for genuine source-data gaps only**, confirmed by grepping the raw CSV,
  not a shortcut for "I couldn't be bothered to check the taxonomy criteria."
- **Reconcile with `relationships.competitors`, don't override it silently.** This skill reads
  that field to sanity-check groupings; it does not write to `data/enrichment_all/*.json`. If a
  conflict looks like `relationships.competitors` is the one that's wrong or stale, say so to
  the user and hand off to `skill-company-enrichment-json` rather than fixing it here.

## Data Sources

1. `data/themes/*.json` — theme definitions (`competitive_groups`, `extra_entities`,
   `theme_supply_chain`).
2. `data/enrichment_all/*.json` — canonical company data, including
   `relationships.competitors`.
3. `output/enrichment_all_rendered/*.md` — rendered business summaries used to verify group
   membership before adding a company anywhere.
4. `../biztrends.TW/data/ic.tpex.org.tw/raw_SupplyChain_*.csv` — the raw TPEx industry-chain
   source; grep this before claiming a company is missing due to a source-data gap.
5. `scripts/build_themes.py` — the renderer; `competitive_groups`/`extra_entities` handling
   lives in `build_theme_page()` / `scan_theme_links()` / `iter_extra_entities()`.

## Validation

For consumer/annotation mode, run the target repository's normal validators and diff/format
checks only; renderer validation does not apply if the repository does not own `data/themes/`
or `output/themes/`.

After editing theme JSON or the consistency checker in theme-owner mode:

```bash
python -c "import json; json.load(open('data/themes/<theme>.json', encoding='utf-8'))"
python scripts/build_themes.py
python skills/skill-theme-competitor-groups-curate/scripts/check_group_consistency.py --all
git status --short data/themes/ output/themes/
```
