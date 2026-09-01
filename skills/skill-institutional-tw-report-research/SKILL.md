---
name: skill-institutional-tw-report-research
description: 維護台灣上市櫃公司法人研究情報；蒐集與正規化外資券商、國內券商、投顧等研究報告的 rating、target price、EPS/營運預估與 thesis revisions，串接公司法說會正式資料，並與 TWSE/TPEx 外資、投信、自營商交易 flow 比較。嚴格區分 research publisher view、company fact、market flow fact 與 repository inference。
---

# Taiwan Institutional Report Research

> **本 repo（GoogleAlertManager）僅供參考，不會在此執行此 skill。** 這個 skill 的家在
> `TW-institutional-research`，依賴該 repo 自己的資料檔與
> `skill-company-investorconference-ingest`/`-digest`/`-ir-pdf-md` 三個 skill，這裡都沒有。
> GoogleAlertManager 只透過 `data/institutional_reports/{stock_id}.json`（見
> `src/analysis/institutional.py`）讀取這個 skill 產出的精簡快照——若該同步管線尚未建立，
> 讀到的會是空值，分析報告會優雅降級、不受影響。

使用此 skill 時，把 repository 當成「台灣法人研究情報系統」，不是報告 PDF 倉庫。預設以繁體中文輸出；official titles、rating labels、URLs、schema keys、file paths 保留原文。

## 必讀

依任務讀取 `AGENTS.md`、`SOURCE_POLICY.md`、`DATA_MODEL.md`、`RESEARCH_WORKFLOW.md`、`INFERENCE_FRAMEWORK.md`、目標公司的既有 records 與相關 publisher profile。

## Phase 1 Coverage Universe

預設 P0 research publishers：

```text
Global / Foreign:
Goldman Sachs, Morgan Stanley, J.P. Morgan, Bank of America, UBS,
Citi, Nomura, Macquarie, CLSA, HSBC

Domestic:
Yuanta, KGI, Fubon, Cathay, SinoPac
```

完整名單、Phase 2 candidates 與 maturity 規則見 `PHASE1_COVERAGE.md`。
Domestic group 在 ingest 時仍需依實際報告抬頭解析證券公司／投顧等 legal publisher entity。

## 核心邊界

Research Publisher：`foreign_broker`、`domestic_broker`、`investment_advisory`、`asset_manager`、`research_platform`。

Institutional Flow：`foreign`、`investment_trust`、`dealer_proprietary`、`dealer_hedging`。

兩者永遠分離。不得因某券商上調 TP 就推論外資買進；不得因外資買超就推論某家外資券商 research view。

## Mode 1 — Report Ingest

1. verify publisher/date/stock/source tier/access type
2. duplicate check
3. extract analyst、rating original/previous、TP original/previous/horizon、EPS/revenue/margin forecasts、thesis、catalysts、risks、valuation method
4. link company event
5. append revisions
6. refresh company coverage

Secondary-only source：confidence 不得高於 medium，並留 primary-source verification TODO。

## Mode 2 — Investor Conference Follow-up

先用既有 InvestorConference skills 建立 company fact layer，再建立 pre-event consensus、收集 post-event 1/3/7/30 日 research updates、計算 EPS/TP/rating revision breadth，最後加入 flow 比較。

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
