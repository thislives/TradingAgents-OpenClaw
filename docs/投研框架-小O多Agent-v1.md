# 小O多Agent投研框架 v1.1

> 基于 TradingAgents-AStock 源码深度研究设计，适配当前工作环境
> 源码深度研究完成，记录于 memory/2026-05-21.md
> 参考: https://github.com/simonlin1212/TradingAgents-astock (Apache 2.0)
> 创建日期: 2026-05-21 | 升级日期: 2026-05-22

---

## 一、设计思路

TradingAgents-AStock 的核心是**多Agent协作流程**：7个分析师分别产出报告 → 质量门控 → 多空辩论 → 研究经理综合 → 交易员制定 → 风控辩论 → 组合经理决策。

本框架继承这一**LangGraph流水线架构**，但做了3个关键适配：
1. **数据源替换**：akshare/Sina/腾讯 → 代替 mootdx/东财（减少网络依赖）
2. **LLM集成**：通过 OpenClaw Gateway 调用 MiniMax-M2.7 或 DeepSeek（无需额外API Key）
3. **聚焦自选股池**：面向持仓管理，而非全市场扫描

### 核心发现：源码深度研究确认的9个关键机制

以下机制均来自 `memory/2026-05-21.md` 的源码验证结果：

| # | 机制 | 来源 |
|:-:|------|------|
| 1 | Graph拓扑：12阶段状态图（含条件路由+loop back） | `graph/setup.py` |
| 2 | 每个Analyst内部都是 Tool-Call 循环（最多N轮） | `agents/analysts/*.py` |
| 3 | Quality Gate 2层验证（硬检查 + LLM复审，ABCDF分级） | `agents/quality_gate.py` |
| 4 | Bull/Bear N轮结构化辩论（英文推理 + A股框架注入） | `agents/researchers/*.py` |
| 5 | 三方风险辩论（Aggressive/Conservative/Neutral） | `agents/risk_mgmt/*.py` |
| 6 | 双LLM设计（quick_think分析 + deep_think决策） | `llm_clients/*.py` |
| 7 | Trader节点：A股交易规则全覆盖（T+1/涨跌停/手数/ST） | `agents/trader/trader.py` |
| 8 | Portfolio Manager 5级决策（Buy/Overweight/Hold/Underweight/Sell） | `agents/managers/portfolio_manager.py` |
| 9 | 数据供应商路由抽象层（17个A股接口） | `dataflows/interface.py` |

---

## 二、框架架构图

### 2.1 完整12阶段流水线（含条件路由）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    小O 多 Agent 投研框架 v1.1                          │
│                   LangGraph 12阶段状态机                                 │
└─────────────────────────────────────────────────────────────────────────┘

START
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 第1阶段: 7个Analyst 并行/顺序分析（每个内部Tool-Call循环，最多N轮）      │
│                                                                      │
│ market_analyst → social_analyst → news_analyst → fundamentals_analyst │
│   → policy_analyst → hot_money_tracker → lockup_watcher              │
│                                                                      │
│ 每个Analyst: quick_think_llm + tools (N轮工具调用) → 结构化报告       │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 第2阶段: Quality Gate（数据质量门控）                                  │
│                                                                      │
│ Layer 1 硬检查（机器人逻辑）:                                          │
│   • 每份report长度 < 100 chars → FAIL                                 │
│   • 关键指标缺失（MA/RSI/MACD/营收YoY） → FAIL                        │
│   • 输出: ABCDF 5级评分                                               │
│                                                                      │
│ Layer 2 LLM复审:                                                      │
│   • 4+ 报告A/B级 → 直接进入辩论                                       │
│   • 2-3 报告A/B级 → LLM复审（通过则进入辩论）                          │
│   • <2 报告A/B级 → 跳过辩论，直接输出 HOLD                              │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 第3阶段: Bull/Bear 投研辩论（N轮，默认1轮，可配置1-3轮）               │
│                                                                      │
│ 轮次1: Bull Researcher（多方）                                        │
│        → 分析7份Analyst报告，生成Bull论据                             │
│        → 使用 quick_think_llm，英文推理保证质量                       │
│                                                                      │
│       Bear Researcher（空方）                                         │
│        → 看到Bull论据 + 所有报告，生成Bear反驳                       │
│                                                                      │
│ [条件: 还需要下一轮?] → Bull看到Bear反驳后再回应                       │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 第4阶段: Research Manager（综合研判）                                 │
│                                                                      │
│ 使用 deep_think_llm（深度思考模型）                                   │
│ 输入: 7份Analyst报告 + QualityGate评估 + Bull/Bear辩论纪要            │
│ 输出: 逻辑严密的投资计划书                                            │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 第5阶段: Trader（交易方案，A股约束全覆盖）                            │
│                                                                      │
│ A股约束 = {                                                          │
│   "T+1": "买入后次日才能卖出",                                        │
│   "涨跌停": "±10%（主板）/ ±20%（科创/创业板）",                       │
│   "最小手数": "100股=1手",                                           │
│   "交易时段": "9:30-11:30, 13:00-15:00",                            │
│   "ST/*ST": "5%涨跌停, 风险标识",                                     │
│   "融资融券": "标的限制",                                             │
│   "印花税": "卖出0.1%",                                              │
│   "佣金": "约0.025%双向",                                            │
│ }                                                                    │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 第6阶段: 三方风险辩论（N轮，默认1轮）                                  │
│                                                                      │
│ Aggressive（激进） ↔ Conservative（保守） ↔ Neutral（中立）           │
│                                                                      │
│ A股特有论据框架注入:                                                  │
│ • Aggressive: T+1可锁多止盈, 涨停动量, PE扩张, 散户放大, 游资确认     │
│ • Conservative: T+1无法逃出, 跌停陷阱, 解禁悬顶, ST/退市             │
│ • Neutral: T+1双刃剑, 政策分级, 估值区间, 轮动周期, 仓位优先          │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 第7阶段: Portfolio Manager（最终决策）                                │
│                                                                      │
│ 使用 deep_think_llm                                                  │
│ 输入: 交易方案 + 三方辩论纪要                                         │
│                                                                      │
│ 5级决策体系:                                                          │
│   BUY (买入)       — 强烈看多                                         │
│   OVERWEIGHT (增持) — 偏多但谨慎                                      │
│   HOLD (持有)      — 中性                                             │
│   UNDERWEIGHT (减持) — 偏空但可持有                                   │
│   SELL (卖出)     — 强烈看空                                         │
│                                                                      │
│ Alpha基准: 沪深300                                                     │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼
END

[条件路由]
QualityGate.fail → 跳过辩论，直接 Research Manager → Trader → Portfolio Manager
Portfolio Manager conclude=NO → loop back再跑一轮辩论
```

---

## 三、双LLM设计

### 3.1 模型分工

| 模型 | 用途 | 角色 |
|------|------|------|
| **quick_think_llm** | 快速推理，高吞吐 | 所有Analyst、Researcher、Trader、Risk Debater |
| **deep_think_llm** | 深度综合判断 | Research Manager（综合研判）、Portfolio Manager（最终决策） |

### 3.2 选择策略

```python
def get_llm_for_role(role):
    deep_think_roles = ["research_manager", "portfolio_manager"]
    if role in deep_think_roles:
        return deep_think_llm  # 聚合多源信息做全局判断
    return quick_think_llm    # 快速响应工具调用

# 当前环境配置
quick_think_llm = "MiniMax-M2.7"
deep_think_llm = "MiniMax-M2.7"  # 或 DeepSeek V4（用于深度决策）
```

---

## 四、Analyst内部实现：Tool-Call循环

### 4.1 核心机制

每个Analyst节点**不是简单函数直接返回**，而是**LLM + Tools 多轮循环**：

```python
def analyst_node(state, analyst_name, system_prompt, tools):
    """
    每个Analyst的通用Tool-Call循环实现
    最多N轮工具调用，直到LLM输出结构化报告
    """
    messages = [
        {"role": "system", "content": system_prompt},
        *state.get("analyst_reports_so_far", []),
        state["messages"][-1]  # 最新用户请求
    ]
    
    for round in range(max_rounds):
        # 1. LLM决定调用什么工具
        llm_response = quick_think_llm.invoke(
            messages,
            tools=tools  # analyst专属工具列表
        )
        
        # 2. 检测是否已生成最终报告（停止标记）
        if has_final_report(llm_response):
            final_report = extract_report(llm_response)
            state["analyst_reports"].append({
                "analyst": analyst_name,
                "report": final_report,
                "quality_score": assess_quality(final_report)
            })
            break
        
        # 3. 执行工具调用，追加结果到消息历史
        for tool_call in llm_response.tool_calls:
            tool_result = execute_tool(tool_call)
            messages.append(tool_result)
    
    return state
```

### 4.2 7个Analyst的工具清单

| Analyst | 数据工具 | 核心关注点 |
|---------|----------|-----------|
| 🏪 市场分析师 | `get_stock_data`, `get_indicators` | K线形态、MA/RSI/MACD、量价关系 |
| 💬 舆情分析师 | `get_news`, `get_social_sentiment` | 散户情绪、讨论热度、换手率 |
| 📰 新闻分析师 | `get_news`, `get_global_news` | 公告、宏观事件、影响评估 |
| 📊 基本面分析师 | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | 财报三表、盈利能力、估值 |
| 🏛️ 政策分析师 | `get_news`, `get_global_news` | 监管政策、产业趋势（A股特有） |
| 🔥 游资追踪师 | `get_dragon_tiger_board`, `get_hot_stocks`, `get_northbound_flow`, `get_concept_blocks` | 龙虎榜、北向资金、概念热点（A股特有） |
| 🔓 解禁监控师 | `get_lockup_expiry`, `get_insider_transactions` | 限售解禁、大股东减持（A股特有） |

---

## 五、质量门控（Quality Gate）

### 5.1 Layer 1：硬检查（机器人逻辑）

```python
def quality_gate_layer1(analyst_reports):
    """
    逐报告检查，返回 ABCDF 评分
    """
    results = []
    for report in analyst_reports:
        score = "A"
        reasons = []
        
        # 长度检查
        if len(report.content) < 100:
            score = "F"
            reasons.append("report_too_short")
        
        # 必采指标检查（每个Analyst有5-7项必须数据）
        missing_indicators = check_required_indicators(report)
        if missing_indicators:
            score = max_score_below(score, "D")
            reasons.append(f"missing_indicators: {missing_indicators}")
        
        # 表格/结构化数据检查
        if not has_structured_data(report):
            score = max_score_below(score, "C")
        
        results.append({"report": report, "score": score, "reasons": reasons})
    
    return results

def quality_gate_decision(layer1_results):
    """
    Layer 1 结果 → 决定是否进入辩论
    """
    a_b_count = sum(1 for r in layer1_results if r["score"] in ["A", "B"])
    
    if a_b_count >= 4:
        return "PASS"  # 4+ A/B → 直接进入辩论
    elif a_b_count >= 2:
        return "LLM_REVIEW"  # 2-3 A/B → LLM复审
    else:
        return "FAIL"  # <2 A/B → 跳过辩论，直接HOLD
```

### 5.2 Layer 2：LLM复审（仅当 Layer 1 不确定时触发）

```python
def quality_gate_layer2(reports, layer1_results):
    """
    LLM评估报告可靠性，输出通过/不通过
    """
    prompt = f"""评估以下{len(reports)}份分析师报告的可靠性。

质量Gate评分: {layer1_results}

请判断：
- 这些报告整体是否可信，可以支持深入的投资辩论？
- 还是数据质量太差，应该直接输出 HOLD 回避风险？

输出：通过 / 不通过
"""
    
    llm_response = deep_think_llm.invoke([{"role": "user", "content": prompt}])
    decision = extract_decision(llm_response)  # "PASS" or "FAIL"
    
    return decision
```

---

## 六、Bull/Bear 辩论机制

### 6.1 辩论流程（N轮）

```python
def bull_bear_debate(analyst_reports, quality_scores, config):
    """
    N轮结构化多空辩论（默认1轮，可配置1-3轮）
    语言：英文（保证LLM推理质量）
    """
    max_rounds = config.get("max_debate_rounds", 1)
    debate_history = []
    
    for round in range(max_rounds):
        # === Bull Researcher ===
        bull_prompt = build_bull_prompt(analyst_reports, quality_scores, debate_history, round)
        bull_response = quick_think_llm.invoke(
            [{"role": "user", "content": bull_prompt}],
            # 无工具调用，纯LLM推理
        )
        bull_arguments = extract_arguments(bull_response)
        debate_history.append({"round": round, "side": "bull", "content": bull_arguments})
        
        # === Bear Researcher ===
        bear_prompt = build_bear_prompt(
            analyst_reports, quality_scores, 
            debate_history, round,
            bear_additional_context="A-share特有的空头论据框架"  # 框架注入
        )
        bear_response = quick_think_llm.invoke(
            [{"role": "user", "content": bear_prompt}],
        )
        bear_arguments = extract_arguments(bear_response)
        debate_history.append({"round": round, "side": "bear", "content": bear_arguments})
    
    return debate_history
```

### 6.2 A股特有论据框架（注入到Prompt）

**Bull论据框架：**
- 政策顺风（暖风频吹 / 行业支持政策）
- 北向确认（北向资金持续净流入）
- 游资接力（龙虎榜机构净买入）
- PE消化叙事（高增速消化高估值）
- 解禁出清（利空出尽）

**Bear论据框架：**
- 政策反转（监管收紧 / 窗口指导）
- 解禁压力（未来90天大比例解禁）
- 游资撤退（龙虎榜机构净卖出）
- T+1锁仓（流动性风险）
- 北向撤退（外资持续流出）
- 估值泡沫（PE显著高于行业平均）

---

## 七、Trader节点：A股交易规则

```python
A股_TRADING_CONSTRAINTS = {
    "T+1": "买入后次日才能卖出",
    "涨跌停": "±10%（主板）/ ±20%（科创/创业板）",
    "最小手数": 100,  # 股
    "交易时段": [
        {"name": "早盘", "start": "09:30", "end": "11:30"},
        {"name": "午盘", "start": "13:00", "end": "15:00"}
    ],
    "ST限制": "±5%涨跌停",
    "融资融券": "仅限标的池内",
    "印花税": 0.001,  # 卖出时0.1%
    "佣金": 0.00025,  # 双向约0.025%
}

def trader_node(state, constraints=A股_TRADING_CONSTRAINTS):
    """
    Trader节点：根据交易方案 + A股约束生成合规交易指令
    """
    trading_plan = state.get("trading_plan", {})
    current_price = state.get("current_price")
    price_limit = calculate_price_limit(current_price, constraints)
    
    # 手数取整（100股=1手）
    lots = max(100, round(trading_plan["shares"] / 100) * 100)
    
    # 涨跌停检查
    if trading_plan["action"] == "BUY":
        if current_price >= price_limit["up_limit"]:
            return {"action": "SKIP", "reason": "涨停无法买入"}
    elif trading_plan["action"] == "SELL":
        if current_price <= price_limit["down_limit"]:
            return {"action": "SKIP", "reason": "跌停无法卖出"}
    
    return {
        "action": trading_plan["action"],
        "shares": lots,
        "price": current_price,
        "estimated_cost": lots * current_price,
        "constraints_check": "PASS"
    }
```

---

## 八、三方风险辩论

```python
def risk_debate(trading_plan, analyst_reports, config):
    """
    三方风险辩论（N轮，默认1轮）
    Aggressive ↔ Conservative ↔ Neutral
    """
    max_rounds = config.get("max_risk_discuss_rounds", 1)
    risk_history = []
    
    for round_num in range(max_rounds):
        sides = ["aggressive", "conservative", "neutral"]
        
        for side in sides:
            prompt = build_risk_prompt(
                side=side,
                trading_plan=trading_plan,
                analyst_reports=analyst_reports,
                history=risk_history,
                round_num=round_num,
                a_share_frame=三方论据框架[side]  # A股特有框架注入
            )
            
            response = quick_think_llm.invoke([{"role": "user", "content": prompt}])
            arguments = extract_risk_arguments(response)
            risk_history.append({
                "round": round_num,
                "side": side,
                "arguments": arguments
            })
    
    return risk_history

# A股特有三方论据框架
三方论据框架 = {
    "aggressive": [
        "T+1可锁住利润，止盈策略更有效",
        "涨停动量效应，涨停次日高开概率大",
        "PE估值扩张，成长股享受流动性溢价",
        "散户放大效应，跟风资金推动上涨",
        "游资确认信号，龙虎榜买入席位多"
    ],
    "conservative": [
        "T+1无法逃出，一旦跌停深度套牢",
        "跌停陷阱，高位股一旦开板即瀑布",
        "解禁悬顶，大比例解禁压制估值",
        "政策反转风险，监管干预随时到来",
        "ST/退市风险，财务造假不可忽视"
    ],
    "neutral": [
        "T+1是双刃剑，限制的不只是你",
        "政策分级对待，优质资产有豁免",
        "估值区间合理，底部支撑明显",
        "轮动周期规律，板块轮动有节奏",
        "仓位控制优先，分批建仓更安全"
    ]
}
```

---

## 九、数据供应商路由层

### 9.1 抽象接口设计

```python
# dataflows/interface.py
class DataVendorRouter:
    """
    数据供应商抽象路由层
    所有数据调用通过统一的 route() 方法
    支持多vendor failover
    """
    def __init__(self, vendors_config):
        self.vendors = {}
        for name, cls in vendors_config.items():
            self.vendors[name] = cls()
    
    def route(self, method, params):
        """
        遍历所有vendor，找到第一个实现该方法的执行
        全部失败则抛出 NotImplementedError
        """
        for vendor_name, vendor in self.vendors.items():
            if hasattr(vendor, method):
                try:
                    return getattr(vendor, method)(**params)
                except Exception as e:
                    continue  # try next vendor
        raise NotImplementedError(f"No vendor for method: {method}")

# 当前环境的vendors配置
vendors_config = {
    "sina": SinaVendor,      # 实时行情、K线
    "tencent": TencentVendor, # PE/PB/市值
    "akshare": AkshareVendor,  # 财务数据、龙虎榜等
}
router = DataVendorRouter(vendors_config)
```

### 9.2 17个A股数据接口

| # | 方法名 | 数据内容 | 主要Vendor |
|:-:|--------|---------|-----------|
| 1 | `get_stock_data` | OHLCV K线 | Sina |
| 2 | `get_indicators` | 技术指标（MA/RSI/MACD/BOLL） | Sina |
| 3 | `get_news` | 公司公告+新闻（Policy/Fundamentals/Market分类） | Sina |
| 4 | `get_global_news` | 宏观经济/地缘新闻 | Sina |
| 5 | `get_fundamentals` | 财务摘要（营收/净利/EPS/ROE/分红） | Akshare |
| 6 | `get_balance_sheet` | 资产负债表 | Sina |
| 7 | `get_cashflow` | 现金流量表 | Sina |
| 8 | `get_income_statement` | 利润表 | Sina |
| 9 | `get_profit_forecast` | EPS一致预期（同花顺） | Akshare |
| 10 | `get_concept_blocks` | 概念板块分类（百度股市通） | Akshare |
| 11 | `get_industry_comparison` | 行业横向对比 | Akshare |
| 12 | `get_dragon_tiger_board` | 龙虎榜（东财） | Akshare |
| 13 | `get_lockup_expiry` | 限售解禁（未来90天） | Akshare |
| 14 | `get_insider_transactions` | 内部人交易 | Akshare |
| 15 | `get_northbound_flow` | 北向资金（自缓存历史+实时） | 自建缓存 |
| 16 | `get_fund_flow` | 个股资金流向 | Akshare |
| 17 | `get_hot_stocks` | 当日强势股+题材（同花顺） | Akshare |

---

## 十、工作流定义

### 10.1 全量分析流程（v1.1）

```
输入: 股票代码列表（如自选股75支）
─── 阶段1: 数据采集 ───
  1.1 批量获取实时行情 (Sina API)
  1.2 逐支获取K线数据 (Sina K线API, 并行)
  1.3 批量获取PE/PB (腾讯API)
  1.4 逐支获取财务数据 (Akshare, 通过router路由)
─── 阶段2: 7 Analyst并行分析 ───
  2.1 每个Analyst内部Tool-Call循环（最多N轮）
  2.2 产出结构化报告 + Quality评分
  2.3 quick_think_llm 全程使用英文推理
─── 阶段3: Quality Gate ───
  3.1 Layer 1 硬检查 → ABCDF评分
  3.2 汇总A/B级数量 → PASS / LLM_REVIEW / FAIL
  3.3 Layer 2（如需要）LLM复审
─── 阶段4: Bull/Bear辩论（N轮） ───
  4.1 Bull Researcher 生成多方论据（英文）
  4.2 Bear Researcher 生成空方反驳（英文）
  4.3 A股特有论据框架注入
─── 阶段5: Research Manager ───
  5.1 deep_think_llm 综合研判
  5.2 输出投资计划书
─── 阶段6: Trader ───
  6.1 生成交易方案（A股约束全覆盖）
  6.2 T+1/涨跌停/手数/时段检查
─── 阶段7: 三方风险辩论 ───
  7.1 Aggressive / Conservative / Neutral 轮流发言
  7.2 A股特有风险论据框架注入
─── 阶段8: Portfolio Manager ───
  8.1 deep_think_llm 最终决策
  8.2 输出5级信号: BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL
  8.3 输出仓位建议
```

### 10.2 快速分析（单支股票，10分钟内）

```
1. 实时行情 (Sina) → 2s
2. K线技术分析 (Sina) → 3s/支
3. PE/PB (腾讯) → 1s
4. 基本面 (Akshare via router) → 5s/支
5. 7维度Analyst报告（Tool-Call循环）→ 10s/支
6. Quality Gate → 2s
7. Bull/Bear辩论（1轮）→ 5s
8. Research Manager → 3s
9. Trader（A股约束）→ 2s
10. 三方风控辩论 → 5s
11. Portfolio Manager 5级决策 → 3s
总耗时: ~40s/支（含LLM调用）
```

---

## 十一、当前环境适配清单

| 组件 | 状态 | 说明 |
|------|:----:|------|
| 📡 实时行情（Sina） | ✅ 可用 | `hq.sinajs.cn` 单次请求可获取~80支 |
| 📊 K线数据（Sina日K） | ✅ 可用 | `money.finance.sina.com.cn` JSON API |
| 📈 PE/PB（腾讯） | ✅ 可用 | `qt.gtimg.cn` 实时估值数据 |
| 📋 财务数据（akshare） | ⚠️ ~67% | `stock_financial_abstract` 稳定但部分JSON解析失败 |
| 📰 新闻/公告 | ❌ 不可用 | akshare新闻API返回空，需用web_fetch代替 |
| 🔥 龙虎榜 | ⚠️ 可用 | akshare `stock_lhb_stock_detail_em` 需要代理 |
| 🧠 LLM (MiniMax-M2.7) | ✅ 可用 | 通过OpenClaw Gateway调用 |
| 🧠 LLM (DeepSeek V4) | ✅ 可用 | DeepSeek V4 Flash 备用 |
| 📊 数据供应商路由层 | ⚠️ 待实现 | 当前直接调用API，需封装router |

### 已知限制
1. **财务数据覆盖率~67%**：剩下1/3的股票akshare JSON解析失败，可改用腾讯/新浪F10数据
2. **新闻数据缺失**：akshare新闻API返回空，可以从财联社/东方财富网站爬取
3. **龙虎榜不稳定**：akshare龙虎榜接口有时限
4. **本地模型太弱**：Qwen3.6-35B-A3B输不出有效文本，必须用云端MiniMax或DeepSeek
5. **数据供应商路由层**：当前未实现，直接硬编码调用API

---

## 十二、输出模板

### 12.1 单支股票分析报告模板

```
┌────────────────────────────────────────────────────────────────┐
│ 📊 小O投研分析 — {股票名}({代码})                                │
│ 日期: {YYYY-MM-DD} | 现价: ¥{price} | 信号: {5级信号}          │
├────────────────────────────────────────────────────────────────┤
│ 信号: {BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL} | 评分: {score}  │
│ 仓位: {仓位建议} | Alpha基准: 沪深300                           │
├────────────────────────────────────────────────────────────────┤
│ 7 Analyst 报告摘要                                              │
│ 🏪 市场: {趋势} MA多头排列:{是/否} RSI:{rsi} MACD:{macd}      │
│ 📊 基本面: 营收{rev_g}% 净利{profit_g}% PE:{pe} PB:{pb}      │
│ 💬 舆情: {情绪} | 🏛️ 政策: {政策影响}                         │
│ 🔥 游资: {北向}{龙虎榜} | 🔓 解禁: {解禁风险}                  │
├────────────────────────────────────────────────────────────────┤
│ Quality Gate: {PASS/FAIL} (A/B:{n}份)                          │
├────────────────────────────────────────────────────────────────┤
│ Bull论据: {bull_arguments}                                     │
│ Bear论据: {bear_arguments}                                    │
├────────────────────────────────────────────────────────────────┤
│ 三方风控:                                                       │
│ ⚡ 激进: {aggressive_args}                                      │
│ 🛡️ 保守: {conservative_args}                                   │
│ ⚖️ 中立: {neutral_args}                                        │
├────────────────────────────────────────────────────────────────┤
│ Research Manager: {investment_plan}                             │
│ Trader: {trading_action} {shares}手 @ ¥{price}                 │
├────────────────────────────────────────────────────────────────┤
│ 最终决策: {信号} | 仓位: {position}                             │
│ 风险提示: {risk_alerts}                                        │
└────────────────────────────────────────────────────────────────┘
```

### 12.2 批量TOP 20报告模板

```
# 小O投研 — 增长股TOP 20
日期: YYYY-MM-DD | 数据: 实时行情 + 2025年报 | 框架版本: v1.1

## 榜单
1. {name}({code}) 评分{score} 信号{信号} 营收{rev_g}% 净利{profit_g}% ✅双增
2. ...
20. ...

## 重点推荐（信号= BUY / OVERWEIGHT）
### {name}({code}) — 信号:{信号} 评分:{score}
{技术面简述}
{基本面简述}
{游资/政策简述}
建议: {signal} | 仓位: {position}
```

---

## 十三、使用说明

### 命令行调用
```bash
# 分析单支股票（v1.1 流水线）
python3 scripts/stock_analysis_v2.py 688328

# 批量分析自选股（v1.1 并行）
python3 scripts/batch_analysis_v2.py

# 更新TOP 20增长股
python3 scripts/find_top20_growth.py

# 生成早盘简报
python3 scripts/morning_brief.py
```

### 配置文件
```python
# config.py
DATA_SOURCES = {
    'realtime': 'sina',
    'kline': 'sina',
    'fundamentals': 'akshare',
    'pe_pb': 'tencent',
    'data_vendor_router': True,  # v1.1 新增：启用抽象路由层
}

LLM = {
    'provider': 'minimax',
    'quick_think': 'MiniMax-M2.7',
    'deep_think': 'MiniMax-M2.7',  # 或 'DeepSeek-V4'
}

DEBATE = {
    'max_debate_rounds': 1,        # Bull/Bear辩论轮数
    'max_risk_rounds': 1,         # 三方风控轮数
    'debate_language': 'English', # 辩论语言（保持推理质量）
}

WATCHLIST = 'memory/自选股列表.md'
```

---

## 十四、迭代计划

| 版本 | 计划功能 | 状态 |
|:----:|----------|:----:|
| v1.0 | 7 Analyst分析 + 评分决策（简单函数版） | ✅ 已交付 |
| **v1.1** | **源码9个机制全部更新：Tool-Call循环、2层QualityGate、N轮辩论、三方风控、双LLM、Trader节点、5级决策、供应商路由** | ✅ **本次升级** |
| v1.2 | 数据供应商路由层实现，财务数据覆盖率达90%+ | 待实现 |
| v1.3 | 接入财联社/东财新闻摘要作为News Analyst | 待实现 |
| v1.4 | 龙虎榜/游资追踪Analyst稳定接入 | 待实现 |
| v1.5 | 解禁数据Analyst、北向资金缓存层 | 待实现 |
| v2.0 | LangGraph正式集成，流水线可配置化 | 待实现 |

---

*本框架基于 Apache 2.0 开源协议，遵循 TradingAgents-AStock 的设计理念。*
*9个核心机制源码验证：memory/2026-05-21.md*
