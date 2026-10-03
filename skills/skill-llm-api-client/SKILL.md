---
name: skill-llm-api-client
description: 統一的 LLM 客戶端函式庫（llm package），封裝 Gemini API 金鑰輪轉、skill-llm-api-server 的 codex-cli/gemini-cli 遠端橋接、以及本地 MLX 推論，內建 codex → gemini → mlx 自動備援鏈與 Draft/Judge 智慧路由。
---

# LLM API Client 技能 (skill-llm-api-client)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.0.1（詳見 `metadata.json`） |
| 來源 | https://github.com/wenchiehlee/llm |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-llm-api-client`） |
| 維護者 | wenchiehlee |
| 對應 Callee Skill | `common/skill-llm-api-server`（Synology NAS 上實際執行 codex-cli/gemini-cli） |

此技能是一個可安裝的 Python 函式庫（`llm` package），提供單一入口 `LLMClient` 呼叫三種 LLM provider，並具備自動備援、金鑰輪轉與智慧路由：

- **`codex`**（別名 `llm-cli`）：呼叫 `skill-llm-api-server` 的 `/exec`（ChatGPT Pro）與 `/gemini/exec`（Gemini，經 NAS 端 gemini-cli 橋接）
- **`gemini`**：直接呼叫 Google Gemini API，支援最多 20 把金鑰（`GEMINI_API_KEY` + `_1`~`_19`）的每日配額偵測與 round-robin 輪轉
- **`mlx`**：呼叫本地 Apple Silicon 上的 MLX 推論伺服器（見 `common/skill-mlx-api-server`）

預設備援鏈：`codex → gemini → mlx`。

## 📦 技能結構說明

```text
skill-llm-api-client/
├── SKILL.md
├── metadata.json
├── self_update.py
└── scripts/
    ├── __init__.py
    ├── client.py               # LLMClient：generate / generate_json / generate_smart / generate_json_smart
    ├── providers/
    │   ├── __init__.py         # BaseProvider 介面
    │   ├── codex.py            # CodexProvider：呼叫 skill-llm-api-server
    │   ├── gemini.py           # GeminiProvider：直連 Gemini API，金鑰輪轉
    │   └── mlx.py              # MLXProvider：呼叫 skill-mlx-api-server
    └── analytics/
        ├── __init__.py
        └── amplitude.py         # LLMCallTracker：Amplitude 埋點（provider/model/耗時/成功率）
```

> 部署時 `scripts/` 底下的內容對應到消費專案（如 `llm` repo）的 `llm/` package 根目錄，即 `scripts/client.py` → `llm/client.py`，`scripts/providers/*` → `llm/providers/*`，以此類推。

### ⚠️ 與 `skill-llm-api-server` 不同：`llm` repo 內刻意保留兩份程式碼

`skill-llm-api-server` 的消費端（`Llm-Cli-APIServer`）已將 `main.py` 完全搬進 `skills/skill-llm-api-server/scripts/`，根目錄不再有副本。**`llm` repo 無法比照辦理**：`pyproject.toml` 的 `[tool.hatch.build.targets.wheel]` 規定 `packages = ["llm"]`，也就是說 `llm/` package **必須留在 repo 根目錄**，`pip install`（無論是 `llm @ file:///.../llm` 本地路徑安裝，或 `llm @ git+https://github.com/wenchiehlee/llm.git`）都是直接從這個根目錄路徑建置 wheel。若把 `llm/` 搬進 `skills/skill-llm-api-client/scripts/`，會讓所有依賴此套件的其他 repo（凡是 `pyproject.toml` 內有 `llm @ file:///...` 或 `llm @ git+...` 這行的專案）的安裝失效。

因此 `llm` repo 內同時存在兩份程式碼，是**刻意並存、非自動同步**的快照，而非該修的重複：
- **根目錄 `llm/`** —— 唯一真實來源，`pip install` 永遠讀這裡，程式改動應直接在這裡進行
- **`skills/skill-llm-api-client/scripts/`** —— 對應登錄庫 `common/skill-llm-api-client` 的某個時間點快照，用途是讓 skills 登錄庫追蹤版本、以及供「未來可能直接 vendor 程式碼而非透過 pip 安裝」的其他 consumer repo 參考

修改 `llm/` 套件邏輯後，若要讓此快照跟上，需手動把變更同步進 `skills/skill-llm-api-client/scripts/`（或執行 `self_update.py --deploy-all` 從登錄庫推送），`self_update.py` 不會自動偵測根目錄 `llm/` 的變化。

## ⚙️ 前置環境配置

### 1. 安裝

本地路徑（開發環境，`pyproject.toml`）：
```toml
[project]
dependencies = [
    "llm @ file:///${PROJECT_ROOT}/../llm",
]
```
或 `uv add --editable "../llm"`。

GitHub 倉庫（CI/CD 或正式環境）：
```toml
[project]
dependencies = [
    "llm @ git+https://github.com/wenchiehlee/llm.git",
]
```

### 2. 環境變數（`.env`）

```env
# Gemini（直連 API，可輪轉多把金鑰）
GEMINI_API_KEY=
GEMINI_API_KEY_1=
# ... 最多到 GEMINI_API_KEY_19
# GEMINI_SKIP_KEYS=GEMINI_API_KEY_7   # 預先跳過配額耗盡的 key

# skill-llm-api-server（NAS 上的 codex-cli/gemini-cli 橋接）
CODEX_API_URL=https://api.wenchiehlee.synology.me:8443
CODEX_API_KEY=

# skill-mlx-api-server（本地 MLX 推論）
MLX_API_URL=
MLX_SERVER_API_KEY=
# MLX_MODEL=mlx-qwen3

# Amplitude（不填則預設關閉追蹤）
AMPLITUDE_API_KEY=
LLM_APP_NAME=my-app
```

> API Key 中若包含 `#` 字元可能導致 `.env` 解析錯誤，請確保 Key 的正確性。

## 🚀 使用方式

### 基礎調用
```python
from llm import LLMClient

# 初始化（自動偵測可用 provider：codex → gemini → mlx）
client = LLMClient(app_name="NewsAnalyzer")

text = client.generate("請簡述台積電在 2024 年的營收表現。")
data = client.generate_json("分析此標題的感興趣程度：'新一代 AI 晶片發表'，格式：{score: 0-10, reason: str}")

print(f"Provider: {client.last_provider}")
print(f"Model: {client.last_model}")
```

### 指定路徑與模型
```python
# 強制走 codex 伺服器上的 gemini-cli 調用 Gemini 2.5
client = LLMClient(providers=["codex"], model="gemini-2.5-flash")
text = client.generate("透過 NAS 伺服器上的 gemini-cli 進行調用。")

# 呼叫時臨時覆寫
client.generate(prompt, provider="gemini", model="gemini-2.0-flash")
```

### 智慧路由 (Smart Routing)
```python
# 本地優化：MLX 生成，再交由強大模型評分；達標後自動永久切換為 MLX
text = client.generate_smart("TaskA", "請將這段文字翻譯成英文：...", draft_provider="mlx")

# NAS 端自我反思（極速模式）：draft_provider="codex" 時，
# 整個 Draft & Judge 流程交給 skill-llm-api-server 的 /smart/exec 在伺服器內部完成，
# 客戶端只有一次網路請求延遲。
text = client.generate_smart("TaskB", "請摘要此內容...", draft_provider="codex")
```

**機制：**
1. **草稿階段**：`draft_provider` 產生初步回答
2. **評審階段**：交給強大模型（預設避開直接呼叫 Gemini API 以節省配額）評核；回覆 `OK` 則採用草稿，否則採用評審修正後的答案
3. **晉升機制**：任務樣本數 > 10 且成功率 > 80% 時，該 `task_name` 晉升為直接執行草稿模型，跳過評審
4. 所有階段皆透過 `LLMCallTracker` 記錄到 Amplitude（`smart_route_status`: `judged_passed` / `judged_failed` / `draft_failed` / `server_side_executed`）

遷移既有呼叫：`client.generate(prompt)` → `client.generate_smart(task_name, prompt, draft_provider="codex")`，系統自動管理 `.llm_routing.json` 狀態文件。

## 📊 Provider 對照表

| Provider | 預設模型 | 說明 |
| :--- | :--- | :--- |
| `codex` / `llm-cli` | `chatgpt-pro` / `gemini` | 透過 `skill-llm-api-server` 橋接呼叫；`model` 設為 `gemini-*` 時自動切換為該伺服器的 `/gemini/exec` |
| `gemini` | `gemini-2.5-flash` | 直接調用 Google Gemini API，支援多金鑰自動輪轉 |
| `mlx` | `mlx-qwen3` / `mlx-gemma4` | 呼叫本地 Apple Silicon 上的 MLX 推論伺服器 |

## 📊 AI Model Usage 統計

`skill-llm-api-client` 是一般 LLM 呼叫的主要埋點位置。每次 `LLMClient.generate()` / `generate_json()` 都應送出單一 `llm_call` event：

| 欄位 | 來源 |
|------|------|
| `service` | 固定 `llm-api-client` |
| `stage` | 固定 `generate` |
| `provider` | 成功或失敗當下的 provider，如 `codex`、`gemini`、`mlx` |
| `model` | provider 回填，如 `chatgpt-pro`、`gemini-2.5-flash`、`Qwen3-14B-4bit` |
| `model_repo` | provider 可提供時填入精確來源；cloud provider 可留空 |
| `app_name` | `LLMClient(app_name=...)`，未提供時用 `LLM_APP_NAME`，再 fallback 到 `llm` |

呼叫端若要讓報表能回答「哪個 app 用了哪個模型」，必須明確設定 `app_name`，例如 `LLMClient(app_name="GoogleAlertManager")`。不要只依靠 server README 的總模型表；需要 `app_name × model` cross-tab 才能判斷單一 app 的模型來源。

## 🧪 測試與驗證

- `test_llm_cli.py`：驗證 `skill-llm-api-server` 的 `codex-cli`（ChatGPT）路徑
- `test_llm_cli_gemini.py`：驗證 `skill-llm-api-server` 的 `gemini-cli`（Gemini）路徑
- `test_mlx.py`：驗證本地 MLX 伺服器路徑
- `test_smart_routing.py` / `test_server_smart_routing.py`：驗證 Smart Routing 客戶端/伺服器端流程

## 🔄 版本管理與更新

- 唯一可信來源為 skills 登錄庫中的 `common/skill-llm-api-client`；`llm` repo 內的 `llm/` package 副本由登錄庫部署而來
- 版本採語意化版本，記錄於 `metadata.json`
- 檢查並更新到登錄庫最新版本：
  ```bash
  python self_update.py
  ```
