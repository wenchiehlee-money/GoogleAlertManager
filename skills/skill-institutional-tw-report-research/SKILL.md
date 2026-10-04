---
name: skill-institutional-tw-report-research
description: 維護台灣上市櫃公司法人研究情報；蒐集與正規化外資券商、國內券商、投顧等研究報告的 rating、target price、EPS/營運預估與 thesis revisions，串接公司法說會正式資料，並與 TWSE/TPEx 外資、投信、自營商交易 flow 比較。嚴格區分 research publisher view、company fact、market flow fact 與 repository inference。
---

# Taiwan Institutional Report Research

使用此 skill 時，把 repository 當成「台灣法人研究情報系統」，不是報告 PDF 倉庫。預設以繁體中文輸出；official titles、rating labels、URLs、schema keys、file paths 保留原文。

## 必讀

依任務讀取 `AGENTS.md`、`SOURCE_POLICY.md`、`DATA_MODEL.md`、`RESEARCH_WORKFLOW.md`、`INFERENCE_FRAMEWORK.md`、目標公司的既有 records 與相關 publisher profile。

## Phase 1 Coverage Universe

預設 P0 research publishers：

```text
Global / Foreign:
Goldman Sachs, Morgan Stanley, J.P. Morgan, Bank of America, UBS,
Citi, Nomura, Macquarie, CLSA, HSBC, Bernstein

Domestic:
Yuanta, KGI, Fubon, Cathay, SinoPac
```

完整名單、Phase 2 candidates 與 maturity 規則見 `PHASE1_COVERAGE.md`。
Domestic group 在 ingest 時仍需依實際報告抬頭解析證券公司／投顧等 legal publisher entity。

股票 universe 不限台股：TWSE/TPEx 之外另涵蓋 `ConceptStocks` 定義的美股 concept stocks（`companies/{TICKER}/`，如 `companies/TSM/`）。新增美股 ticker 一律經 `skill-stock-universe-onboarding` 從 `ConceptStocks` onboard，本 repo 不另建美股清單；美股 ledger 只用 USD，不得與台股 NT$ ledger 互相換算，見 `SOURCE_POLICY.md` 的 US Ticker Coverage。

## 核心邊界

Research Publisher：`foreign_broker`、`domestic_broker`、`investment_advisory`、`asset_manager`、`research_platform`。

Institutional Flow：`foreign`、`investment_trust`、`dealer_proprietary`、`dealer_hedging`。

兩者永遠分離。不得因某券商上調 TP 就推論外資買進；不得因外資買超就推論某家外資券商 research view。

## InvestorConference Digest Input

若 sibling repo `../InvestorConference` 已有 digest report，Mode 1 與 Mode 2 必須優先讀取該 digest 作為 company event context。預設路徑：

```text
../InvestorConference/data/reports/conference-digests/{stock_id}/{stock_id}_{period}_digest.md
```

例如：`../InvestorConference/data/reports/conference-digests/2330/2330_2026_q2_digest.md`。若不確定 period 或檔名，先查 `../InvestorConference/README.md` 的 `Digest(TW)` 欄位。

Digest report 的定位：

- digest 中可回溯到 company IR、MOPS、TWSE/TPEx、音檔、逐字稿、簡報的事實，屬於 `company_fact` / `company_event_context`。
- digest 自身的摘要、重點整理、問題歸納，屬於 repository-generated context；使用時必須保留 digest path 與 underlying official/source reference。
- digest 不是 `research_publisher_view`，不得當成券商報告、rating、TP、EPS revision 或 publisher consensus。
- digest 不是 `market_flow_fact`，不得用來推論外資、投信、自營商交易行為。

若 digest 不存在，才退回讀 InvestorConference 的 IR PDF/MD、SRT、audio metadata 與 MOPS/company IR links，並在 TODO 標示 `digest_missing`。

## Mode 0 — Cross-Repo Fetch Triage

處理 `GoogleAlertManager`／`Facebook.Fetch`／`YoutubeAudio.Fetch` 這類抓取端上游新內容時，先做三選一判準（完整規則與最新修正案例見 `SOURCE_POLICY.md` 的 Cross-Repo Fetch Triage）：

1. 具體個股 rating/TP/EPS 數字、可歸屬原始機構或**具名可查資歷的獨立分析師本人**（不限於轉述第三方券商報告）→ 進本 repo Mode 1。
2. 總經／產業主題、明確歸屬某機構但未綁定單一個股 → 屬 `TW-institutional-investment-theses`，不在本 repo 建 record。
3. 兩者皆非（閒聊、情緒、無數字無歸屬）→ 兩邊都不收，不算積壓。

抓取端本身不分類；判準錯誤要當作規則修正記錄下來（見既有案例），不要靜默改判。

## Mode 1 — Report Ingest

1. verify publisher/date/stock/source tier/access type；若來源是即時網路搜尋（WebSearch 等），先過 `SOURCE_POLICY.md` 的 Search-Tool Discovery Hazard 檢查——只信有實際 URL 的 `Links` 結果，摘要文字裡憑空出現的文件名/日期/券商名一律視為疑似幻覺，不得引用
2. duplicate check
3. if the report is event-linked, read the matching InvestorConference digest first and attach `company_event_context.digest_path`; if digest is missing, attach `digest_missing` TODO
4. extract analyst、rating original/previous、TP original/previous/horizon、EPS/revenue/margin forecasts、thesis、catalysts、risks、valuation method
5. compare research thesis / forecast deltas against digest company facts without merging the objects
6. link company event
7. append revisions
8. refresh company coverage

Secondary-only source：confidence 不得高於 medium，並留 primary-source verification TODO。

## Mode 2 — Investor Conference Follow-up

優先以 `../InvestorConference` 產生的 digest report 建立 company fact layer 與 event baseline。流程：

1. locate digest via `../InvestorConference/README.md` Digest(TW) 欄或預設 digest path
2. extract company facts、management tone、Q&A topics、guidance / no-guidance boundaries、open questions，並保留 digest path 與 underlying official/source references
3. build pre-event consensus snapshot from eligible research records only
4. collect post-event 1/3/7/30 日 research updates
5. calculate EPS/TP/rating revision breadth only from eligible publisher records
6. add TWSE/TPEx flow comparison as separate `market_flow_fact`
7. produce repository inference only after all underlying records are traceable

Digest 可用來定義「公司實際說了什麼」與後續研究報告要比較的 event baseline；不得直接產生 publisher consensus 或 view-flow divergence。

## Mode 3 — Company Consensus

建議輸出：Company Facts、Latest Research Coverage、Rating Distribution、Target Price Distribution、EPS Revision History、Key Thesis Agreements/Disagreements、Institutional Flow、View-Flow Divergence、Open Questions。

## Mode 4 — Revision Intelligence

優先研究 EPS、TP、Rating、Margin、Revenue、Valuation Multiple revisions。所有 revision 保留 previous/new values，永不覆蓋歷史。

## Mode 5 — Flow Comparison

Flow source 優先 TWSE / TPEx official。rolling windows：1D、5D、10D、20D、60D。Flow 是 market behavior，不是 research thesis。

## Mode 6 — Derived Intelligence

允許計算 Research Revision Momentum、EPS Revision Breadth、TP Revision Breadth、Rating Breadth、Post-IR Revision Intensity、View-Flow Divergence、Foreign-vs-Domestic Research Divergence、Estimate Dispersion、Coverage Freshness。所有 signal 必須保存 inputs。

## Copyright Rules

對 client_portal/paywalled/user_provided/restricted report，不假設可 public redistribution；public repo 預設只保存 metadata、structured notes、checksum、private source reference，不 commit full report。

## Validation

```bash
python3 skills/skill-institutional-tw-report-research/scripts/validate_records.py
git diff --check
```
