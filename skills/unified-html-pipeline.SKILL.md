---
name: unified-html-pipeline
description: 三项目统一投研流水线 — stock-analysis采集 → TradingAgents分析 → HTML报告，全链路Step 0-9
---

# unified-html-pipeline Skill

## 概述

**unified-html-pipeline** 是将 `TradingAgents-AStock`、`stock-analysis`、`a-stock-data` 三个项目整合的统一投研流水线。

它通过 4 个脚本驱动 3 个阶段，生成包含 7 个 Analyst 报告 + 多空辩论 + 风控评估 + 补充数据的**完整 HTML 研究报告**。

```
┌──────────────────────────────────────────────────────────────┐
│ Stage 1: 补充数据采集                                          │
│   stock_full_report.py → data_{code}.json                     │
│       ↓ run_stock_analysis_snapshot.py                        │
│   supplement JSON + quality_flags                             │
├──────────────────────────────────────────────────────────────┤
│ Stage 2: TradingAgents 多Agent分析                             │
│   get_supplemental_data 工具 → fundamentals/lockup Analyst   │
│       ↓ TradingAgentsGraph.full_states_log_*.json            │
│   7 Analyst 报告 + 辩论 + 最终决策                             │
├──────────────────────────────────────────────────────────────┤
│ Stage 3: 统一HTML报告                                          │
│   render_unified_html.py → Step 0-9 Markdown → HTML          │
│       output/reports/{code}_unified.html (61-87KB)            │
└──────────────────────────────────────────────────────────────┘
```

---

## 全链路流程

```
stock-analysis 采集 (stock_full_report.py)
  → supplement JSON + quality_flags (run_stock_analysis_snapshot.py)
    → 中文摘要 (supplemental_stock_analysis.py)
      → get_supplemental_data 工具 (agent_utils.py)
        → fundamentals_analyst / lockup_watcher 调用
          → full_states_log (TradingAgents)
            → render_unified_html.py
              → unified HTML (Step 0-9)
```

---

## 报告步骤结构（Step 0-9）

| 步骤 | 内容 | 数据来源 |
|------|------|----------|
| **Step 0** | 最终决策 | Portfolio Manager 输出（Buy/Hold/Sell + 仓位） |
| **Step 1** | 市场技术分析 | Market Analyst（K线形态、技术指标、量价关系） |
| **Step 2** | 市场情绪分析 | Social Media Analyst（散户讨论热度） |
| **Step 3** | 新闻舆情分析 | News Analyst（行业新闻、公告、宏观事件） |
| **Step 4** | 基本面分析 | Fundamentals Analyst（财报三表、估值、一致预期） |
| **Step 5** | 政策分析 | Policy Analyst（监管政策、产业政策） |
| **Step 6** | 游资与资金信号 | Hot Money Tracker（龙虎榜、北向资金、概念热点） |
| **Step 7** | 解禁与股权结构 | Lockup Watcher（限售解禁、大股东动态） |
| **Step 8** | 多空辩论与风险评估 | Bull/Bear 辩论 + 三方风险辩论 |
| **Step 9** | 补充数据摘要 | stock-analysis（主营构成、股东结构、分红、融资融券等） |

---

## 核心脚本

### Stage 1: run_stock_analysis_snapshot.py

**功能：** 调用 stock-analysis 采集 11 个 blocks，过滤截断，生成 quality_flags

```bash
# 采集单只股票
python scripts/run_stock_analysis_snapshot.py 600519

# 输出: output/supplement/600519_stock_analysis_blocks.json
```

**关键逻辑：**
```python
TARGET_BLOCKS = [
    "share_structure", "zygc", "top10", "top10_free",
    "dividend", "margin", "fund_hold", "recommend",
    "yjyg", "yjkb", "gdhs",
]

# 每个 block 截断行数
MAX_ROWS = {
    "share_structure": 15, "zygc": 15, "top10": 10, "top10_free": 10,
    "dividend": 15, "margin": 15, "fund_hold": 20, "recommend": 20,
    "yjyg": 50, "yjkb": 50, "gdhs": 15,
}
```

---

### Stage 2: TradingAgents 分析

通过 `tradingagents-web` 或 `run_trading_graph.py` 运行：

```bash
# 使用 LLM 分析单只股票（需配置 .env 中的 API Key）
# 分析结果自动保存到 ~/.tradingagents/logs/{code}/TradingAgentsStrategy_logs/
```

**分析过程：**
1. 7 个 Analyst 并行生成研报
2. Quality Gate 两层验证
3. Bull/Bear 多空辩论
4. Research Manager 综合研判
5. Trader 生成 A 股交易方案
6. 三方风险辩论
7. Portfolio Manager 最终决策

---

### Stage 3: render_unified_html.py

**功能：** 读取 TradingAgents 分析结果 + stock-analysis 补充数据 → 生成 HTML 报告

```bash
# 手动指定文件
python scripts/render_unified_html.py 600519 \
    --name 贵州茅台 \
    --ta-result /path/to/full_states_log.json \
    --sa-json /path/to/data_600519.json

# 自动查找最新文件
python scripts/render_unified_html.py 600519 \
    --name 贵州茅台 \
    --auto-latest

# 输出:
#   output/unified/{code}_unified.md     (Step 0-9 Markdown)
#   output/unified/{code}_unified.json  (html_renderer 兼容格式)
#   output/reports/{code}_unified.html  (最终 HTML 报告)
```

---

### 一键总控：run_full_report.py

```bash
# 完整流程（采集 + 分析 + HTML）
python scripts/run_full_report.py 300750 --name 宁德时代

# 跳过采集（已有分析结果）
python scripts/run_full_report.py 600519 --name 贵州茅台 --skip-snapshot
```

---

## HTML 模板引擎

HTML 报告通过 stock-analysis 项目的 `html_renderer` 模块生成：

```python
from html_renderer import generate_html

html_path = generate_html(code, md_path, json_path)
# generate_html 内部读取 JSON 中的 blocks，
# 注入 stock-analysis 的 HTML 模板，
# 输出带有 charts 和样式的研究报告
```

**报告章节：**
- Header: 股票名称 + 代码 + 分析日期
- Step 0: 最终决策卡片（Buy/Hold/Sell + 仓位）
- Step 1-7: 各 Analyst 报告（可折叠/展开）
- Step 8: 辩论纪要
- Step 9: 补充数据摘要表格
- Footer: 数据质量提示 + 免责声明

---

## 报告章节结构详解

### Step 9: 补充数据摘要（来自 stock-analysis）

```markdown
## Step 9: stock-analysis 补充数据

### 主营业务构成
- [行业分类] 产品A: 收入 12.3亿, 占比 45.2%
- [行业分类] 产品B: 收入 8.1亿, 占比 29.7%

### 十大股东
- 香港中央结算有限公司: 9.6亿股, 7.64%
- 贵州省国有资产运营公司: 4.2亿股, 3.34% (减持)

### 近期分红
- 2024-06-14: 派息 25.9, 送0/转0 [已实施]
- 2023-06-16: 派息 25.9, 送0/转0 [已实施]

### 融资融券
> 以下数据疑似全市场ETF数据，仅供参考
- 2024-03-15 [贵州茅台]: 融资余额 15.8亿, 融券余量 21.8万

### 股东户数变动
> 数据较旧（最新日期距今超过2年），仅作历史参考
- 2022-03-31: 14.6万户 (-3.2%)

## 数据质量提示
- **margin** 标记为可疑：标的证券代码非当前股票
- **gdhs** 标记为过旧：最新数据日期2022-03-31距今超过2年
- **fund_hold/recommend/yjkb/yjyg** 为空：接口未返回数据
```

---

## 快速使用命令

```bash
# 完整流程
python scripts/run_full_report.py 600519 --name 贵州茅台

# 单独采集补充数据
python scripts/run_stock_analysis_snapshot.py 600519

# 单独生成 HTML
python scripts/render_unified_html.py 600519 --name 贵州茅台 --auto-latest

# 查看补充数据摘要
python -c "from tradingagents.dataflows.supplemental_stock_analysis import get_stock_analysis_supplement; print(get_stock_analysis_supplement('600519'))"

# 回归测试（5只股票）
python scripts/test_unified_pipeline.py
```

---

## 输出文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 补充数据 JSON | `output/supplement/{code}_stock_analysis_blocks.json` | 11 blocks + quality_flags |
| 统一 Markdown | `output/unified/{code}_unified.md` | Step 0-9 完整报告 |
| 统一 JSON | `output/unified/{code}_unified.json` | html_renderer 兼容格式 |
| 统一 HTML | `output/reports/{code}_unified.html` | 最终可视化报告（61-87KB） |
| TA 分析日志 | `~/.tradingagents/logs/{code}/TradingAgentsStrategy_logs/full_states_log_*.json` | TA 原始输出 |

---

## 已测试股票

| 代码 | 名称 | SA JSON | Supp | TA Log | HTML | Agent调用 | 质量降权 |
|------|------|:-------:|:----:|:------:|:----:|:--------:|:--------:|
| 600519 | 贵州茅台 | ✅ | 8/11 | ✅ | 76KB | ✅ | ✅ |
| 300750 | 宁德时代 | ✅ | 8/11 | ✅ | 78KB | ✅ | ✅ |
| 002594 | 比亚迪 | ✅ | 8/11 | ✅ | 81KB | ✅ | ✅ |
| 601318 | 中国平安 | ✅ | 7/11 | ✅ | 87KB | ✅ | ✅ |
| 688981 | 中芯国际 | ✅ | 8/11 | ✅ | 75KB | ✅ | ✅ |

---

## 配置说明

配置文件：`config/unified_pipeline.yaml`

```bash
# 从 example 复制后修改
cp config/unified_pipeline.example.yaml config/unified_pipeline.yaml
```

主要配置项：
```yaml
stock_analysis_dir: /path/to/stock-analysis
stock_analysis_python: python3
supplement_dir: output/supplement
unified_dir: output/unified
reports_dir: output/reports
tradingagents_logs_dir: ~/.tradingagents/logs
```

---

## 整合层文件清单（5个新增文件）

| 文件 | 作用 |
|------|------|
| `scripts/run_stock_analysis_snapshot.py` | 调 stock-analysis 采集 + 提取 11 个 blocks |
| `tradingagents/dataflows/supplemental_stock_analysis.py` | 中文摘要生成 + quality_flags |
| `scripts/render_unified_html.py` | 统一 HTML 报告生成器（含 --auto-latest） |
| `scripts/run_full_report.py` | 总控脚本（一键 snapshot → TA → HTML） |
| `scripts/test_unified_pipeline.py` | 5 股回归测试 |

---

## 注意事项

1. **执行顺序**：必须先有 TradingAgents 的 `full_states_log_*.json`，才能运行 render_unified_html.py
2. **auto-latest 依赖**：自动查找日志时依赖 `~/.tradingagents/logs/{code}/TradingAgentsStrategy_logs/` 目录存在
3. **HTML 体积**：每份报告 61-87KB，包含完整的 Step 0-9 内容
4. **数据质量降权**：HTML 报告中会显示 quality_flags 提示，告知哪些数据需要降权参考
5. **仅供学习研究**：报告由 AI 自动生成，明确声明不构成投资建议