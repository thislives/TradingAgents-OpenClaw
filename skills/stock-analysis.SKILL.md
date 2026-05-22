---
name: stock-analysis
description: A股补充数据采集层 — 采集TradingAgents缺失的11个 blocks（股本结构/融资融券/股东户数/基金持仓等）
---

# stock-analysis Skill

## 概述

**stock-analysis** 是 TradingAgents-AStock 框架的**补充数据采集层**，专门采集 A 股多维度补充数据，填补主框架在财务结构、股东变动、融资融券等方面的数据空白。

它通过 `stock_full_report.py` 脚本一次性采集 11 个数据 blocks，并对外输出标准化的 JSON 结构，供 TradingAgents 的 `fundamentals_analyst` 和 `lockup_watcher` 调用。

---

## 功能列表

| Block Key | 数据内容 | 说明 |
|-----------|----------|------|
| `share_structure` | 股本结构变动 | 限售股解禁、增发等导致的总股本变化 |
| `zygc` | 主营业务构成 | 按行业/产品分类的收入占比 |
| `top10` | 十大股东 | 前10大股东持股明细与增减持变化 |
| `top10_free` | 十大流通股东 | 前10大流通股东持股明细 |
| `dividend` | 历史分红 | 历次派息、送股、转增记录与进度 |
| `margin` | 融资融券 | 融资余额、融券余量（近20交易日） |
| `fund_hold` | 基金持仓 | 重仓该股的主动型基金列表与持股比例 |
| `recommend` | 机构推荐评级 | 券商研报评级与目标价（东财接口） |
| `yjyg` | 业绩预告 | 业绩预告内容摘要 |
| `yjkb` | 业绩快报 | 业绩快报关键财务数据 |
| `gdhs` | 股东户数变动 | 股东户数变化趋势（反映筹码集中度） |

---

## 使用方法

### 命令行调用

```bash
# 采集单只股票的11个blocks
python scripts/run_stock_analysis_snapshot.py 600519

# 采集后输出到 output/supplement/600519_stock_analysis_blocks.json
```

### Python 调用

```python
from tradingagents.dataflows.supplemental_stock_analysis import get_stock_analysis_supplement

# 获取中文摘要（适合LLM上下文）
summary = get_stock_analysis_supplement("600519")
print(summary)
```

### 输出文件位置

```
{stock_analysis_dir}/output/
├── data_{code}.json              # 原始完整数据（所有blocks）
└── output/supplement/
    └── {code}_stock_analysis_blocks.json  # 截断版11blocks + quality_flags
```

---

## quality_flags 数据质量标签

每个 block 在采集后会自动生成 `quality_flags` 标记，用于告知调用方数据的可信度：

| 状态 | 含义 | 处理策略 |
|------|------|----------|
| `OK` | 数据正常 | 直接使用 |
| `suspect` | 可疑数据 | 当辅助参考，不得作为强结论依据 |
| `empty` | 空数据 | 跳过，不编造数据 |
| `stale` | 数据过旧 | 仅作历史参考 |

### 质量检测规则

**margin（融资融券）：**
- 检查前3条记录的"标的证券代码"是否匹配当前股票代码
- 不匹配 → 状态 `suspect`，原因：疑似全市场ETF/非个股融资融券数据

**gdhs（股东户数）：**
- 检查最新数据日期距今是否超过2年
- 超过2年 → 状态 `stale`，仅作历史参考

**其他 blocks（fund_hold/recommend/yjkb/yjyg）：**
- 接口无返回 → 状态 `empty`，跳过不编造

---

## 数据结构

输出 JSON 结构：

```json
{
  "code": "600519",
  "source": "stock-analysis",
  "generated_at": "2026-05-22T02:00:00Z",
  "block_counts": {
    "share_structure": 3,
    "zygc": 8,
    "top10": 10,
    "top10_free": 10,
    "dividend": 10,
    "margin": 15,
    "fund_hold": 12,
    "recommend": 0,
    "yjyg": 2,
    "yjkb": 0,
    "gdhs": 15
  },
  "empty_blocks": ["recommend", "yjkb"],
  "quality_flags": {
    "margin": {"status": "OK"},
    "gdhs": {"status": "OK"}
  },
  "blocks": {
    "margin": [...],
    "gdhs": [...],
    ...
  }
}
```

### 数据行数截断配置

每个 block 有最大保留行数限制，防止 JSON 过大：

```
share_structure: 15行  |  top10: 10行     |  dividend: 15行
zygc: 15行            |  top10_free: 10行 |  fund_hold: 20行
margin: 15行          |  recommend: 20行  |  yjyg: 50行
yjkb: 50行            |  gdhs: 15行
```

---

## 输出格式示例

### margin（融资融券）

```json
{
  "信用交易日期": "2024-03-15",
  "标的证券代码": "600519",
  "标的证券简称": "贵州茅台",
  "融资余额": 1583000000,
  "融券余量": 218000
}
```

### gdhs（股东户数）

```json
{
  "股东户数统计截止日": "2024-03-31",
  "股东户数-本次": 146820,
  "股东户数-增减比例": -3.2
}
```

---

## 代码参考

**主采集脚本：** `scripts/run_stock_analysis_snapshot.py`

核心逻辑：

```python
TARGET_BLOCKS = [
    "share_structure", "zygc", "top10", "top10_free",
    "dividend", "margin", "fund_hold", "recommend",
    "yjyg", "yjkb", "gdhs",
]

def run_snapshot(code: str) -> dict | None:
    # 1. 调用 stock_full_report.py 生成 data_{code}.json
    json_path = ensure_stock_analysis_json(code)

    # 2. 提取11个blocks并截断
    for key in TARGET_BLOCKS:
        items = all_blocks.get(key, [])
        supplement_blocks[key] = items[:MAX_ROWS.get(key, 15)]

    # 3. 质量检测（margin标的代码匹配 / gdhs时效）
    quality_flags = check_quality(supplement_blocks)

    # 4. 输出 JSON
    return {
        "code": code,
        "source": "stock-analysis",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "block_counts": block_counts,
        "empty_blocks": empty_blocks,
        "quality_flags": quality_flags,
        "blocks": supplement_blocks,
    }
```

**中文摘要模块：** `tradingagents/dataflows/supplemental_stock_analysis.py`

---

## 注意事项

1. **数据来源**：通过 `mootdx` + `akshare` + 东财/新浪接口采集，部分接口可能失败导致 empty
2. **margin 污染**：全市场 ETF 融资数据可能混入个股记录，`suspect` 状态需结合标的证券代码交叉验证
3. **gdhs 时效**：部分股票股东户数更新频率低（季报），最新数据可能距今超过2年，标记为 stale
4. **fund_hold/recommend**：akshare 接口经常返回空数据，属正常现象，直接跳过
5. **采集超时**：单次采集限时 300 秒，若失败可重试
6. **依赖 stock-analysis 项目**：需确保 `stock_full_report.py` 可独立运行