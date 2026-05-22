---
name: quality_flags
description: A股投研数据质量防护体系 — OK/suspect/empty/stale四级评级 + Quality Gate两层验证 + ABCDF分级标准
---

# quality_flags Skill

## 概述

**quality_flags** 是 TradingAgents-AStock 框架的**数据质量防护体系**，为所有补充数据 block 打上质量标签，告知调用方数据的可信度等级，并强制在后续分析中降权处理可疑数据。

核心原则：**不信任单一数据源，不编造数据，数据质量问题必须显式标记。**

---

## 数据质量等级

| 等级 | 标签 | 含义 | 处理策略 |
|------|------|------|----------|
| ✅ 正常 | `OK` | 数据正常、无污染、可直接使用 | 直接使用 |
| ⚠️ 可疑 | `suspect` | 数据存在混入/偏差，需交叉验证 | **当辅助参考**，不得作为强结论依据 |
| ❌ 空数据 | `empty` | 接口无返回数据 | **跳过**，不编造 |
| ⏰ 过旧 | `stale` | 数据日期距今超过阈值，仅历史参考 | **仅作历史参考**，不反映当前状态 |

---

## 检查规则

### margin（融资融券）— 标的证券代码匹配

**问题背景：** `margin` block 采集自东财接口，可能混入全市场 ETF（如 510300 沪深300ETF）的融资融券数据，导致"张冠李戴"。

**检查逻辑：**
```python
margin_items = supplement_blocks.get("margin", [])
margin_suspect = True
for r in margin_items[:3]:
    sc_code = str(r.get("标的证券代码", ""))
    if sc_code == code:          # 匹配当前股票代码
        margin_suspect = False   # 确认是个股数据
        break
if margin_suspect:
    quality_flags["margin"] = {
        "status": "suspect",
        "reason": "标的证券代码非当前股票，疑似全市场ETF/非个股融资融券数据"
    }
```

**触发条件：** 前3条记录的"标的证券代码"无一条匹配当前股票代码

**降权影响：**
- 不得作为"该股票融资余额变化趋势"的结论依据
- 可作为"全市场融资情绪"的辅助参考

---

### gdhs（股东户数）— 数据时效检查

**问题背景：** 股东户数数据来自季报披露，更新频率低（通常每季度末更新一次），部分股票可能最新数据距今超过2年。

**检查逻辑：**
```python
from datetime import datetime, timezone, timedelta

gdhs_items = supplement_blocks.get("gdhs", [])
if gdhs_items:
    newest_date_str = gdhs_items[0].get("股东户数统计截止日", "")
    stale = True
    if newest_date_str:
        newest_date = datetime.fromisoformat(newest_date_str.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - newest_date < timedelta(days=730):  # 2年
            stale = False
    if stale:
        quality_flags["gdhs"] = {
            "status": "stale",
            "reason": f"最新数据日期 {newest_date_str} 距今超过2年"
        }
```

**触发条件：** 最新数据日期距今 **≥ 730天（2年）**

**降权影响：**
- 不得用于判断"当前筹码集中度"
- 可作为"历史股东户数变化规律"的参考

---

### fund_hold / recommend / yjkb / yjyg — 空数据标记

**问题背景：** akshare 和东财的部分接口经常返回空数据（如基金持仓、机构评级），这是接口层面的数据缺失，不编造。

**检查逻辑：**
```python
empty_blocks = []
for key in TARGET_BLOCKS:
    items = all_blocks.get(key, [])
    if len(items) == 0:
        empty_blocks.append(key)
        quality_flags[key] = {
            "status": "empty",
            "reason": "接口未返回数据"
        }
```

**降权影响：** 相关 block 完全跳过，不出现在分析报告中

---

## 降权策略汇总

```
收到 suspect 数据 → 当辅助参考，降权处理
收到 empty 数据   → 跳过，不编造
收到 stale 数据   → 仅历史参考，不代表当前
收到 OK 数据      → 直接使用
```

### Agent Prompt 中的质量约束

在 `fundamentals_analyst.py` 和 `lockup_watcher.py` 的 prompt 中内置约束：

```
You should be aware that the following data blocks have quality issues:
- margin: marked as "suspect" — do not use as strong conclusion basis
- gdhs: marked as "stale" — only for historical reference
- fund_hold/recommend/yjkb/yjyg: marked as "empty" — skip them
```

---

## Quality Gate 架构

### Layer 1：硬检查（自动）

在 7 个 Analyst 生成报告之后、Bull/Bear 辩论之前执行：

| 检查项 | 通过条件 | 失败后果 |
|--------|----------|----------|
| 报告长度 | 每份报告 ≥ N 字符 | 标记该 Analyst 失败 |
| 必采清单 | 每个 Analyst 的5-7项必采数据均有 | 标记失败 |
| 表格/结构化数据 | 财务三表等必须有表格输出 | 标记失败 |
| 数据源失败 | 无 `Error:` 关键字混入 | 标记失败 |

### Layer 2：LLM 复审（智能）

当 **4+ 份报告硬检查失败** 时：
- 跳过 Bull/Bear 辩论环节
- 直接输出 **Hold** 信号

当 **< 4 份报告失败** 时：
- 将质量评分注入后续 Researcher 和 Debater 的 prompt
- 提示 LLM 对低质量数据保持怀疑

---

## ABCDF 分级标准

Quality Gate 的 Layer 1 输出 ABCDF 分级：

| 等级 | 含义 | 报告可用性 |
|------|------|------------|
| **A** | 所有数据完整、结构清晰、无异常 | 完全可信 |
| **B** | 少量数据轻微缺失，仍可分析 | 基本可信 |
| **C** | 部分数据有问题，需要降权 | 参考性分析 |
| **D** | 大部分数据有问题，可信度低 | 谨慎参考 |
| **F** | 数据严重缺失或严重错误 | 跳过分析 |

---

## ToolNode 完整性检查

### 问题背景

LLM ToolNode 在生成结构化输出时可能发生"数据污染"：
- 在应该输出空数据时，LLM 可能"编造"符合格式但虚假的数据
- 字段缺失 vs 字段为空（`None`/`""` vs `[]`）需要区分

### 检查机制

```python
def check_tool_output(tool_name: str, output: str) -> dict:
    """检查 ToolNode 输出的完整性"""
    issues = []

    # 1. 检查是否混入 Error 关键字
    if "Error:" in output and "No data" not in output:
        issues.append("error混入")

    # 2. 检查是否在空数据时输出了结构化内容（疑似编造）
    if tool_name in ["get_fund_hold", "get_recommend"]:
        if output and "No data" not in output:
            # 可能是编造的数据，需要确认
            pass

    return {
        "status": "pass" if not issues else "fail",
        "issues": issues
    }
```

### 完整性保护规则

1. **数据截断**：每个 block 最多保留 N 行（见 stock-analysis Skill）
2. **Error 隔离**：所有 `Error:` 开头的字符串不得混入结构化数据
3. **None 处理**：空字段统一使用 `null`（JSON）而非空字符串 `""`

---

## 质量标志在统一报告中的呈现

在 `render_unified_html.py` 生成的 HTML 报告中，quality_flags 通过 `supplemental_stock_analysis.py` 的中文摘要呈现：

```markdown
## 数据质量提示

- **margin** 标记为可疑：标的证券代码非当前股票，疑似全市场ETF数据
- **gdhs** 标记为过旧：最新数据日期2022-03-31距今超过2年，仅作历史参考
- **fund_hold** 为空：接口未返回数据

> 分析时请注意：标记为可疑(suspect)或过旧(stale)的数据必须降权处理
```

---

## 代码参考

**质量检测逻辑：** `scripts/run_stock_analysis_snapshot.py`

```python
# margin 标的证券代码匹配
margin_items = supplement_blocks.get("margin", [])
for r in margin_items[:3]:
    if r.get("标的证券代码") == code:
        # OK
        break
else:
    quality_flags["margin"] = {"status": "suspect", ...}

# gdhs 时效检查
from datetime import datetime, timezone, timedelta
newest_date = datetime.fromisoformat(...)
if datetime.now(timezone.utc) - newest_date > timedelta(days=730):
    quality_flags["gdhs"] = {"status": "stale", ...}
```

**中文摘要生成：** `tradingagents/dataflows/supplemental_stock_analysis.py`

```python
def get_stock_analysis_supplement(ticker: str) -> str:
    # 分block生成摘要，suspect/stale block 附加质量警告
    if is_suspect:
        lines.append("> 以下数据疑似全市场 ETF/非个股标的，仅供参考")
    if is_stale:
        lines.append("> 数据较旧（最新日期距今超过2年），仅作历史参考")
```

**Quality Gate：** `tradingagents/agents/quality_gate.py`

---

## 注意事项

1. **质量标签不消除数据**：标记为 suspect/stale 的数据不会从 JSON 中删除，只是标注了可信度等级，由 Agent prompt 强制降权
2. **empty 不等于 zero**：空 block 的字段可能存在但行数为0，这是真实的接口无返回状态
3. **时效阈值可配置**：gdhs 的2年阈值定义在 `run_stock_analysis_snapshot.py` 的常量中，可根据需求调整
4. **margin 只检查前3条**：检查范围仅前3条，避免全量遍历开销；若前3条均为ETF数据，则整体标记为suspect
5. **LLM 不可绕过降权**：Prompt 中的质量约束会明确要求 LLM 不得对 suspect/stale 数据做强结论，否则该结论的可信度需要打折扣