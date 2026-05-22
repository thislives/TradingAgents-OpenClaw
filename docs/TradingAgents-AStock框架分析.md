# TradingAgents-AStock 多 Agent 投研框架分析文档

> 学习来源：https://github.com/simonlin1212/TradingAgents-astock
> 上游项目：TauricResearch/TradingAgents（65K ⭐）
> 参考论文：TradingAgents: Multi-Agents LLM Financial Trading Framework (arXiv 2412.20138)
> 分析日期：2026-05-21

---

## 一、框架概述

TradingAgents-AStock 是一个**基于 LangGraph 的多 LLM Agent 协作文易投研框架**，专为 A 股市场深度定制。它通过 7 个 AI 分析师 + 多空辩论 + 三方风控辩论 + 组合经理的流水线架构，对单支股票进行系统性分析并输出 Buy / Hold / Sell 信号及仓位建议。

核心设计思路：**用多 Agent 辩论模拟投研团队的协作流程，用 A 股特化规则约束确保输出符合市场制度。**

### 1.1 与原版 TradingAgents 的关键区别

| 维度 | 原版（美股） | 本 Fork（A股） |
|------|-------------|----------------|
| 数据源 | Yahoo Finance / Alpha Vantage | mootdx + 东财 + 新浪 + 同花顺（全免费直连）|
| Analyst 角色 | 4 个（市场/情绪/新闻/基本面） | 7 个（+政策/游资/解禁）|
| 交易规则 | T+0、无涨跌停 | T+1、涨跌停、最小手数、交易时段 |
| 输出语言 | 英文 | 中文报告（内部辩论保持英文保证推理质量）|
| Alpha 基准 | SPY | 沪深 300 |

---

## 二、整体架构流水线

```
┌──────────────────────────────────────────────────────────────┐
│ 第1阶段：7 Analyst 研报生成                                    │
│ Market → Social → News → Fundamentals → Policy → HotMoney → Lockup │
│         （每个 Analyst 带工具循环，最多 N 轮）                    │
├──────────────────────────────────────────────────────────────┤
│ 第2阶段：Quality Gate 数据质量门控                              │
│         Layer 1：硬检查（长度/失败标记/必采清单/表格）→ ABCDF分级  │
│         Layer 2：LLM 复审（4+ 报告硬检查失败时跳过辩论）          │
├──────────────────────────────────────────────────────────────┤
│ 第3阶段：Bull vs Bear 投研辩论                                  │
│         Bull Researcher ←→ Bear Researcher（最多 N 轮）        │
├──────────────────────────────────────────────────────────────┤
│ 第4阶段：Research Manager 综合研判                              │
│         深度思考 LLM，输出投资计划                               │
├──────────────────────────────────────────────────────────────┤
│ 第5阶段：Trader 交易方案                                        │
│         A 股约束：T+1 / 涨跌停 / 手数 / 交易时段                  │
├──────────────────────────────────────────────────────────────┤
│ 第6阶段：三方风险辩论                                           │
│         Aggressive ←→ Conservative ←→ Neutral（最多 N 轮）     │
├──────────────────────────────────────────────────────────────┤
│ 第7阶段：Portfolio Manager 最终决策                              │
│         深度思考 LLM，输出 Buy/Hold/Sell + 仓位                   │
└──────────────────────────────────────────────────────────────┘
```

### 2.1 双 LLM 设计

- **quick_think_llm**：所有 Analyst、Researcher、Trader、Risk Debater — 快速推理，高吞吐
- **deep_think_llm**：Research Manager 和 Portfolio Manager — 需要综合全局信息做决策，深度思考

---

## 三、7 个 Analyst 角色详解

### 3.1 🏪 市场分析师 (Market Analyst)
- **职责**：K线形态识别、技术指标计算、量价关系分析
- **数据工具**：get_stock_data, get_indicators
- **必采清单**：5 项数据指标

### 3.2 💬 舆情分析师 (Social Media Analyst)
- **职责**：社交媒体情绪分析、散户讨论热度监测
- **数据工具**：get_news

### 3.3 📰 新闻分析师 (News Analyst)
- **职责**：行业新闻解读、公告分析、宏观事件影响评估
- **数据工具**：get_news, get_global_news, get_insider_transactions

### 3.4 📊 基本面分析师 (Fundamentals Analyst)
- **职责**：财报三表分析（利润表/资产负债表/现金流量表）、盈利能力评估、估值分析
- **数据工具**：get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_profit_forecast（一致预期EPS）, get_industry_comparison

### 3.5 🏛️ 政策分析师 (Policy Analyst) — A 股特化
- **职责**：监管政策解读、产业政策分析、窗口指导追踪
- **数据工具**：get_news, get_global_news
- **为什么需要**：A 股是政策市，政策变化直接影响板块轮动
- **框架注入**：Bull 辩论中作为"政策顺风"论据，Bear 辩论中作为"政策反转"论据

### 3.6 🔥 游资追踪师 (Hot Money Tracker) — A 股特化
- **职责**：龙虎榜分析、大单流向追踪、主力资金动态监测、北向资金分析、概念板块热点
- **数据工具**：
  - get_dragon_tiger_board — 龙虎榜上榜记录 + 买卖席位明细 + 机构参与
  - get_hot_stocks — 同花顺当日强势股 + 题材归因
  - get_northbound_flow — 北向资金分钟级实时流向 + 自缓存历史
  - get_concept_blocks — 概念板块分类
  - get_fund_flow — 个股资金流向
  - get_industry_comparison — 全行业横向对比
- **为什么需要**：游资是 A 股短线定价的核心力量
- **框架注入**：Bull 中作为"游资接力"确认信号，Bear 中作为"游资撤退"预警

### 3.7 🔓 解禁监控师 (Lockup Watcher) — A 股特化
- **职责**：限售股解禁日历监控、大股东减持动态、股权质押风险
- **数据工具**：get_lockup_expiry（未来 90 天解禁日历）, get_insider_transactions, get_fundamentals
- **为什么需要**：解禁是 A 股特有的重大供给冲击因素
- **框架注入**：Bear/Cautious 辩论中作为核心利空论据

---

## 四、数据源架构

### 4.1 数据供应商体系

全部免费直连，无需 API Key，无需积分墙：

| 来源 | 协议 | 提供内容 |
|------|------|----------|
| mootdx | TCP 7709 | OHLCV K线、财务快照、F10 文本 |
| 腾讯财经 | HTTP (qt.gtimg.cn) | PE/PB/市值/换手率（实时） |
| 东方财富 | HTTP (datacenter/push2) | 龙虎榜、限售解禁、板块行情、个股信息 |
| 新浪财经 | HTTP | K线历史、财报三表 |
| 同花顺 | HTTP (10jqka) | EPS一致预期、当日强势股+题材归因 |
| 财联社 | HTTP (cls.cn) | 全球财经快讯 |
| 百度股市通 | HTTP (finance.pae.baidu) | 概念板块分类、资金流向 |
| akshare | Python 库 | 龙虎榜明细、限售解禁详情、行业对比 |

### 4.2 数据接口抽象层

```python
dataflows/
├── interface.py    # 数据接口抽象层：注册 vendor、路由方法
├── a_stock.py      # A 股数据 vendor（~1277行，17个接口方法）
```

数据供应商通过 `default_config.py` 中的 `data_vendors` 配置路由，所有数据调用走统一的抽象接口。

---

## 五、质量门控 (Quality Gate)

在 7 个 Analyst 生成报告之后、Bull/Bear 辩论之前，插入一个**数据质量验证节点**。

### 5.1 Layer 1：硬检查
- 检查每个 analyst 报告的长度（空报告标记失败）
- 检查必采清单是否完整（每个 analyst 有 5-7 项必采数据）
- 检查表格与结构化数据是否存在
- 输出 ABCDF 分级

### 5.2 Layer 2：LLM 复审
- 当 4+ 报告硬检查失败时，跳过后续辩论直接输出 Hold
- 否则将质量评分注入后续 Researcher 和 Debater 的 prompt

---

## 六、辩论机制

### 6.1 Bull vs Bear 投研辩论
- **两方辩论**：Bull Researcher 持多方立场，Bear Researcher 持空方立场
- **A 股特有论据框架**：
  - **Bull 框架**：政策顺风、北向确认、游资接力、PE 消化叙事、解禁出清
  - **Bear 框架**：政策反转、解禁压力、游资撤退、T+1 锁仓、估值泡沫、北向撤退
- 辩论材质：7 份 Analyst 报告 + 数据质量评分
- **语言**：英文（保持 LLM 推理质量）
- **轮数**：可配置（默认 1 轮）

### 6.2 三方风险辩论
- **三方辩手**：Aggressive（进攻） ↔ Conservative（保守） ↔ Neutral（中立）
- **A 股特有论据框架**：
  - **Aggressive 框架**：涨停动量、政策底、PE 扩张、散户放大、游资确认
  - **Conservative 框架**：T+1 不可逃逸、跌停陷阱、解禁悬顶、政策反转、ST/退市
  - **Neutral 框架**：T+1 双刃剑、政策分级、估值区间、轮动周期、仓位优先
- **语言**：英文

---

## 七、决策层

### 7.1 Research Manager（综合研判）
- 使用 `deep_think_llm`（深度思考模型）
- 输入：各阶段所有报告 + 辩论纪要
- 输出：逻辑严密的投资计划书

### 7.2 Trader（交易方案）
- **完全重写为 A 股特化**
- A 股交易约束全覆盖：
  - T+1 交易规则
  - ±10% 涨跌停限制
  - 最小交易手数（100股 = 1手）
  - 交易时段（9:30-11:30 / 13:00-15:00）
  - ST / \*ST 股风险标识
  - 融资融券标的限制

### 7.3 Portfolio Manager（最终决策）
- 使用 `deep_think_llm`
- 输入：交易方案 + 三方辩论纪要
- 输出：**Buy / Hold / Sell + 仓位比例**
- prompt 中包含 A-Stock Trading Constraints 块
- Alpha 基准：沪深 300

---

## 八、核心创新点总结

| 创新点 | 说明 |
|--------|------|
| **7 Analyst 深度特化** | 政策分析师关注"政策市"、游资追踪师关注"龙虎榜"、解禁监控师关注"限售解禁"——这 3 个角色是 A 股独有 |
| **A 股数据全免费直连** | mootdx + 新浪 + 东财 + 同花顺 + 腾讯 + 百度股市通，零 API Key、零积分墙 |
| **数据质量门控** | 2 层验证（硬检查 + LLM 复审），避免数据源异常导致错误分析 |
| **北向资金自缓存** | 针对 2024-08 后官方数据断供问题，自建本地 CSV 缓存（northbound_daily.csv） |
| **三方辩论注入 A 股框架** | 同一机制（T+1/涨跌停）在三方风控中呈现对立观点，让 LLM 看到不同立场下的合理解读 |
| **辩论层英文 + 报告中文** | 内部辩论保持英文以保证推理质量，用户面向的报告输出中文 |
| **LangGraph 流水线架构** | 12 阶段 pipeline 可扩展，新增任何 Analyst 只需修改 6 个文件（本体 + 状态 + init + 条件路由 + graph + setup）|

---

## 九、部署与配置

### 9.1 环境要求
- Python >= 3.10
- pip install -e .
- 必须使用 LLM API Key（不能使用订阅版，每次分析需 30-50 次 LLM 调用）

### 9.2 支持的 LLM 供应商

| 供应商 | 推荐用途 | 配置项 |
|--------|----------|--------|
| MiniMax | 国内直连，性价比高 | MINIMAX_API_KEY |
| DeepSeek | 国产，推理强 | DEEPSEEK_API_KEY |
| 智谱 GLM | 国产合规 | ZHIPU_API_KEY |
| 通义千问 Qwen | 阿里生态 | DASHSCOPE_API_KEY |
| OpenAI | 国际 | OPENAI_API_KEY |
| Anthropic(Kimi) | 通过 Kimi 兼容 API | ANTHROPIC_AUTH_TOKEN |
| Google Gemini | 响应快 | GOOGLE_API_KEY |
| xAI Grok | Stark | XAI_API_KEY |
| Ollama | 本地部署 | Ollama 地址 |

### 9.3 核心配置参数

```python
config = {
    "llm_provider": "minimax",       # LLM 提供商
    "deep_think_llm": "MiniMax-M2.7", # 深度思考模型
    "quick_think_llm": "MiniMax-M2.7-highspeed", # 快速模型
    "output_language": "Chinese",    # 输出语言
    "max_debate_rounds": 1,          # 辩论轮数
    "max_risk_discuss_rounds": 1,    # 风控辩论轮数
    "data_vendors": "a_stock",       # 数据供应商
    "checkpoint_enabled": False,     # 断点续跑
    "backend_url": None,             # 自定义 API 端点
}
```

---

## 十、项目结构

```
TradingAgents-Astock/
├── tradingagents/
│   ├── agents/
│   │   ├── analysts/           # 7 个分析师
│   │   │   ├── market_analyst.py
│   │   │   ├── social_media_analyst.py
│   │   │   ├── news_analyst.py
│   │   │   ├── fundamentals_analyst.py
│   │   │   ├── policy_analyst.py         # A 股特化
│   │   │   ├── hot_money_tracker.py      # A 股特化
│   │   │   └── lockup_watcher.py         # A 股特化
│   │   ├── researchers/        # Bull / Bear 研究员
│   │   │   ├── bull_researcher.py
│   │   │   └── bear_researcher.py
│   │   ├── risk_mgmt/          # 激进/保守/中立 辩手
│   │   │   ├── aggressive_debator.py
│   │   │   ├── conservative_debator.py
│   │   │   └── neutral_debator.py
│   │   ├── managers/           # Research Manager + Portfolio Manager
│   │   ├── trader/             # A 股约束 trader
│   │   ├── quality_gate.py     # 数据质量门控
│   │   └── utils/              # 状态定义、工具函数
│   ├── dataflows/
│   │   ├── a_stock.py          # A 股数据 vendor（17个接口）
│   │   └── interface.py        # 数据接口抽象层
│   ├── graph/
│   │   ├── trading_graph.py    # 主入口：TradingAgentsGraph
│   │   ├── setup.py            # LangGraph 拓扑定义
│   │   ├── propagation.py      # 状态初始化与传播
│   │   ├── reflection.py       # 交易反思（CSI 300 基准）
│   │   └── conditional_logic.py
│   └── llm_clients/            # LLM 客户端适配器
├── web/
│   ├── app.py                  # Streamlit 主入口
│   ├── runner.py               # 后台线程运行分析
│   ├── progress.py             # 线程安全进度追踪
│   ├── history.py              # 历史记录
│   ├── pdf_export.py           # PDF 报告生成
│   └── components/             # UI 组件
└── CHANGES_FROM_UPSTREAM.md    # 25+ 文件改动记录
```

---

## 十一、对现有系统的启发与可行性评估

### 11.1 可直接借鉴的设计

| 设计点 | 现有系统 | 可借鉴程度 |
|--------|----------|-----------|
| **多 Agent 辩论机制** | 单一 LLM 分析 | 🔥 高 — 现有系统可增加多角度辩论 |
| **A 股数据源直连** | 新浪 + akshare | ✅ 已有，可替换 mootdx 增强 K 线 |
| **龙虎榜/游资分析** | 无 | 🔥 高 — 对新股/题材股分析价值大 |
| **政策分析 Agent** | 无 | 🔥 高 — 发债/担保/城投相关政策影响大 |
| **数据质量门控** | 无 | ✅ 中 — 可加入现有流水线 |
| **报告中文输出** | 已有 | ✅ 保持 |
| **Streamlit Web UI** | 无 | ✅ 低 — CLI 已满足需求 |
| **涨跌停/T+1 约束** | 无 | ✅ 低 — 分析师手动把控即可 |

### 11.2 当前环境可实现性

| 维度 | 评估 |
|------|------|
| LLM 成本 | 每次分析 30-50 次调用，当前 MiniMax 配置可直接使用 |
| 数据源 | 已有 akshare + 新浪，缺失 mootdx（TCP 7709 需确认） |
| 部署复杂度 | pip install + .env 配置即可运行 |
| 维护成本 | 贡献者活跃，上游 TradingAgents 65K ⭐ 社区活跃 |
| 定制灵活性 | Apache 2.0 开源，可 fork 深度改造 |

---

## 十二、总结

TradingAgents-AStock 是目前**最完整的开源 A 股多 Agent 投研框架**。其核心价值在于：
1. **7 个 Analyst 覆盖 A 股特有维度**（政策、游资、解禁）——这些是传统量化模型无法触及的
2. **零外部依赖的数据源架构**——不使用任何需要 API Key/积分墙的数据服务
3. **辩论驱动的推理提升**——通过多角度观点碰撞提高 LLM 决策质量
4. **LangGraph 流水线方便扩展**——新增 Analyst 有清晰的文件修改模板（6 文件管线）

该框架可直接部署在当前环境（MiniMax API 已有），生成单支 A 股的专业投研报告，建议考虑将其作为**深度分析模块**融入现有的早报/早盘分析流水线中。
