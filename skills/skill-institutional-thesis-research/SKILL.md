---
name: skill-institutional-thesis-research
description: Maintain and extend the TW-institutional-investment-theses repository in Traditional Chinese. Use when Codex needs to add or update institutional sources, articles, theses, forecast ledgers, taxonomy mappings, comparisons, consensus reports, research TODOs, or interpret an article/news item through selected institutional lenses such as Goldman Sachs, Morgan Stanley, J.P. Morgan, Bank of America, and UBS.
---

# Institutional Thesis Research

> **本 repo（GoogleAlertManager）僅供參考，不會在此執行此 skill。** 這個 skill 的家在
> `TW-institutional-investment-theses`，依賴該 repo 自己的資料檔。GoogleAlertManager 只透過
> `data/institutional_thesis/{stock_id}.json`（見 `src/analysis/institutional.py`）讀取這個
> skill 產出的精簡快照——若該同步管線尚未建立，讀到的會是空值，分析報告會優雅降級、不受影響。

使用此 skill 時，把本 repository 當成可長期維護的 institutional thesis database，而不是文章剪貼簿。預設以繁體中文輸出；但 official titles、URLs、entity names、taxonomy keys、schema field names、status values、quotes 與檔案路徑，在準確性需要時保留原文。

## 必讀脈絡

編輯前，依任務讀取相關 repo 文件：

- `AGENTS.md`：non-negotiable research rules。
- `TAXONOMY.md`：新增或調整 themes 前必讀。
- `DATA_MODEL.md`：調整 schema 或 forecast ledger 前必讀。
- `RESEARCH_WORKFLOW.md` 與 `SOURCE_POLICY.md`：ingest 新來源時必讀。
- `institutions/<institution>/` 既有檔案：建立新 thesis 前必讀。

## Epistemic Rules

- 優先使用 primary institutional sources；若只有 secondary source，明確標示並新增 primary-source verification TODO。
- 不得捏造 titles、authors、dates、URLs、forecasts、quotes 或 institutional positions。
- 嚴格區分 `fact`、`institution_interpretation`、`repository_inference`。
- forecast revision 必須 append chronologically，不得覆蓋舊 forecast。
- 不強迫形成 consensus；disagreement、scope mismatch、不可比數字都是研究結果。
- 不從 article 直接跳到 ticker；必須先寫清楚 transmission chain。

## Two Operating Modes

此 skill 有兩條不同 flow，必須分開使用。

### Mode A Overview: Core Workflow / Source Ingestion

目的：建立與維護 durable institutional thesis database。

輸入通常是 primary institutional source、company primary source、official report 或已查證 source。輸出是 repository record：article、claim、forecast ledger、thesis update、theme mapping、comparison update or research TODO。

這條 flow 可以建立或更新：

- `fact`：由 company primary source、official data 或明確可驗證資料支撐。
- `institution_interpretation`：由 institution primary source 支撐。
- `repository_inference`：由已驗證 facts / institutional interpretations 推導，且必須明確標示。

只有 Core Workflow 產出的已驗證資料，才能支撐 thesis status、conviction、forecast ledger 或 durable comparison conclusion。

### Mode B Overview: Article / News Interpretation

目的：用已建立的 institutional database 解讀使用者提供的 article、news、chart、claim、market information or unverified lead。

輸入可以是 unverified information。輸出是 institutional lens analysis，不是 durable source record，也不是宣稱 institution 已評論該輸入。

Interpretation Mode 的基本邏輯：

```text
user-provided input
-> separate input claim from verified repository evidence
-> compare against existing theses / ledgers / comparisons
-> provide Goldman / Morgan Stanley / J.P. Morgan / BofA / UBS lens comments
-> mark impact as supports / strengthens / weakens / contradicts / reframes / not material
-> recommend verification or source-ingestion if needed
```

Interpretation Mode 可以產生 comments、remarks、verification questions and research TODOs。它不能直接建立 fact、forecast ledger、institutional thesis or consensus conclusion。若輸入後續被 primary sources 驗證，才切回 Core Workflow ingest。

#### Switching Back To Core Workflow

「若輸入後續被 primary sources 驗證，才切回 Core Workflow ingest」的意思是：

- 不是整篇 user input 或 market claim 自動升級。
- 必須找到可引用、可保存 metadata 的 primary source，例如 institution official publication、company filing / earnings release、official dataset or source-defined benchmark。
- 只 ingest primary source 明確支撐的 atomic claims、numbers、dates and interpretations。
- 未被 primary source 支撐的部分仍維持 `user_provided_market_claim` / `unverified_research_lead`，或寫入 verification TODO。
- 若 primary source 是 company source，只能建立 `fact` / `company_fact`；不得推成 `institution_interpretation`。
- 若 primary source 是 institution source，才可建立或更新該 institution 的 article、forecast ledger、thesis evidence or stance。
- 若 primary source contradicts the original input，必須記錄 contradiction，而不是修飾原 claim 讓它看起來正確。

## Mode B Detailed Procedure: Article / News Interpretation

當使用者提供 article、news、excerpt、URL、chart、market claim 或尚未驗證的 information，並要求用不同 institutions 解讀時，使用此模式。輸出是「institutional lens analysis」，不是 source ingestion，也不是宣稱該機構已評論這篇文章；除非 primary source 證明該機構真的評論過。

處理流程：

1. 判斷輸入型態：pasted text、URL、source title、chart claim 或 user paraphrase。
2. 若使用者提供 URL，或要求 latest / current / verify，先查證 source。
3. 分離 article facts、user framing 與 repository inference。
4. 若使用者沒有指定 institutions，預設使用目前五家：Goldman Sachs、Morgan Stanley、J.P. Morgan、Bank of America、UBS。
5. 對每個 selected institution，先對照既有 thesis files、forecast ledgers 與 comparison reports，再評論。
6. 判斷該 news 對既有 thesis 是 `supports`、`strengthens`、`weakens`、`contradicts`、`reframes` 或 `not material`。
7. 不得 invent institutional reaction。除非該 institution 直接發布此來源，否則使用「從 Goldman lens 看...」或「Repository inference based on UBS stored thesis...」這類表述。
8. 若輸入是 unverified lead，只能標為 `user_provided_market_claim` / `unverified_research_lead`；不得寫入 forecast ledger 或 thesis evidence，除非切回 Core Workflow 完成 primary-source verification。

建議輸出格式：

```text
## News / Article Fact Layer
## Institution Lens
| Institution | Likely Lens | Thesis Impact | Confidence | Why |
## Consensus / Disagreement
## Forecast / Number Check
## Repository Update Recommendation
## Open Questions / Verification TODO
```

Institution lens shortcuts：

- Goldman Sachs：demand validation、ROI、utilization、power/grid bottlenecks，以及 capex 是否連到 revenue benefits。
- Morgan Stanley：industrial buildout、macro variable、financing absorption、time-to-power and infrastructure bottlenecks。
- J.P. Morgan：multiyear capex wave、growth-engine framing、bond issuance、private credit、leverage containment and power constraints。
- Bank of America：physical AI、manufacturing productivity、data-center power reliability and grid / energy investment；不要強行給可比 capex forecast。
- UBS：capex discipline、cash capex vs. operating cash flow、capex taper tantrum risk、valuation selectivity and real-asset infrastructure shift。

若 article 本身來自已追蹤的 institution，先當作 source-ingestion 任務處理，再做 lens comparison。若 article 是 secondary news，先把它當 discovery/context，建立 durable repository records 前要找 primary institutional 或 company sources。

## Mode A Detailed Procedure: Source Ingestion

1. 驗證 source identity、publication date、URL、institution 與 source tier。
2. 用 URL、normalized title、institution/date、syndicated copies 與 repeated claims 檢查 duplicate。
3. 在 `institutions/<institution>/articles/<year>/` 建立 article metadata。
4. 擷取 key claims 與 quantitative forecasts，標示 confidence 與 epistemic layer。
5. 建立新 thesis 前，先搜尋既有 thesis files 是否已有 conceptual overlap。
6. 更新 thesis evidence、history、invalidation conditions 與 theme mappings。
7. 若來源含重要數字，追加到 `data/<institution>-forecasts.yaml`。
8. 只有當新 evidence 改變 cross-institution view、open questions 或 reader navigation 時，才更新 `comparisons/` 或 `reports/`。

## Repository Maturity Map

用 maturity 判斷輸出語氣與 confidence。不要把 first-touch institution 寫得像 Goldman pilot 一樣成熟。

| Institution | Maturity | Current Coverage | How To Use The Lens |
|---|---|---|---|
| Goldman Sachs | `pilot / reference implementation` | 13 article records、3 thesis files、forecast ledger、forecast summary、open questions、deeper reports | 可作為最成熟的 AI capex / power-grid / demand-validation reference lens；仍需區分 Goldman forecast、cited consensus and market commentary。 |
| Morgan Stanley | `first-touch plus / industrial-buildout lens` | 4 article records、1 umbrella thesis、forecast ledger、first-touch report | 適合解讀 industrial buildout、macro variable、financing absorption、time-to-power；不宜拆太多子 thesis。 |
| J.P. Morgan | `first-touch plus / capex-financing lens` | 4 source records、1 umbrella thesis、forecast ledger、first-touch report | 適合解讀 multiyear capex wave、growth engine、bond issuance、private credit、leverage containment；Global Research formal model 仍待補。 |
| UBS | `first-touch plus / capex-discipline lens` | 3 article records、1 umbrella thesis、forecast ledger、first-touch report | 適合解讀 capex discipline、cash capex vs. operating cash flow、capex taper tantrum、valuation selectivity；`USD 820bn` / `USD 990bn` capex scope 需查證。 |
| Bank of America | `directional first-touch / physical-AI-power lens` | 2 article records、1 umbrella thesis、forecast ledger、first-touch report | 適合解讀 physical AI、manufacturing productivity、data-center power reliability、grid / energy investment；不要強行給可比 hyperscaler capex forecast。 |

Maturity 使用規則：

- `pilot / reference implementation`：可支撐 thesis update、comparison update、forecast-summary update；但仍不可捏造未入庫來源。
- `first-touch plus`：可用於 institutional lens analysis 與 provisional comparison；建立新子 thesis 前要有更多 direct evidence。
- `directional first-touch`：可用於補充 transmission / framing；除非來源有明確數字，不納入 capex forecast range。
- 目前 five-institution AI capex overview 使用 Goldman Sachs、Morgan Stanley、J.P. Morgan、Bank of America、UBS。
- 目前 focus themes 包含 `AI_CAPEX`、`AI_INFRASTRUCTURE`、`POWER_DEMAND`、`POWER_GRID`、`DATA_CENTERS`、`AI_ROI`、`PHYSICAL_AI`、`PRIVATE_CREDIT`、`RELEVERAGING`、`HALO_REAL_ASSETS`。
- `POWER_EQUIPMENT`、cooling、networking and AI infrastructure financing 仍是 candidate sub-theses；必須等 direct evidence 足夠後才能拆 thesis。

Maturity upgrade criteria：

- `directional first-touch` -> `first-touch plus`：至少 3 個 primary sources，包含 1 個清楚 thesis anchor、1 個 quantitative observation / forecast ledger entry，以及可寫入 institution index 的 open questions。
- `first-touch plus` -> `validated thesis lens`：至少 5-7 個 primary sources，跨 2 個以上 publication dates，umbrella thesis 有 forecast ledger、invalidation conditions、evolution history，且能穩定解讀新 article/news。
- `validated thesis lens` -> `pilot candidate`：至少 2 個可分辨的 recurring theses，forecast revisions 或 stance changes 有 chronology，並已有 cross-institution comparison update。
- `pilot candidate` -> `pilot / reference implementation`：接近 Goldman 標準，包含 multiple thesis files、article history、forecast summary、open-question backlog、comparison links and mature thesis boundaries。
- 不因為機構名氣、文章數量或單一強句自動升級；升級必須由 direct evidence、forecast history、thesis recurrence and invalidation conditions 支撐。
- 降級也允許：若後續查證發現 source scope 不清、secondary-only、或 thesis 無法重複出現，應把 maturity 調回較低層級。

## Output Patterns

- Article records：一個 source 一個 Markdown file，保留 official metadata，並分離 claims 與 inference。
- Thesis records：記錄 recurring institutional interpretation，包含 evidence、status、conviction、invalidation conditions、history 與 taxonomy mapping。
- Forecast ledgers：append-only dated observations；新增 ledger 時使用 `templates/forecast-ledger-template.yaml`。
- Comparisons：提出 consensus 或 ranges 前，先說明 scope mismatch；不要在 metric scope 不可比時平均 Goldman、Morgan Stanley、J.P. Morgan、UBS 的 capex anchors。
- TODOs：當 evidence missing、ambiguous 或不足以拆 thesis 時使用。

## Validation

編輯 forecast ledgers 後，執行：

```bash
python3 skills/skill-institutional-thesis-research/scripts/check_forecast_ledger.py data/goldman-forecasts.yaml data/morgan-stanley-forecasts.yaml data/jpmorgan-forecasts.yaml data/bank-of-america-forecasts.yaml data/ubs-forecasts.yaml
```

commit Markdown / YAML 前，執行：

```bash
git diff --check
```
