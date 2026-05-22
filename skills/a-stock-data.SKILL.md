---
name: a-stock-data
description: A股数据供应商路由层 — mootdx + akshare + 腾讯/东财/同花顺/百度等17个接口，统一抽象接口
---

# a-stock-data Skill

## 概述

**a-stock-data** 是 TradingAgents-AStock 框架的**数据供应商路由层**，通过统一的 `a_stock.py` vendor 模块，封装了对多个免费 A 股数据源的调用，提供 17 个标准化数据接口。

核心设计原则：
- **零 API Key**：全部数据源直连，无需申请任何付费账号
- **多源 fallback**：主力源失败时自动降级到备份源
- **A股专用**：覆盖 K 线、财务三表、龙虎榜、融资融券、北向资金等全套投研数据

数据来源矩阵：

| 来源 | 协议 | 主要用途 |
|------|------|----------|
| mootdx | TCP 7709 | OHLCV K线、财务快照、F10文本 |
| 腾讯财经 | HTTP (qt.gtimg.cn) | PE/PB/市值/换手率（实时） |
| 东方财富 | HTTP 直接调用 | 龙虎榜、限售解禁、板块行情 |
| 新浪财经 | HTTP | 财报三表（年报/季报） |
| 同花顺 | HTTP (10jqka) | EPS一致预期、当日强势股+题材归因 |
| 财联社 | HTTP (cls.cn) | 全球财经快讯 |
| 百度股市通 | HTTP (finance.pae.baidu) | 概念板块分类、资金流向 |
| akshare | Python 库 | 龙虎榜明细、限售解禁详情、行业对比 |

---

## 接口列表（17个）

### 1. get_stock_data
**功能：** 获取 OHLCV 日 K 线数据
**来源：** mootdx (TCP)
**参数：** `symbol`（6位代码）, `start_date`, `end_date`
**返回：** CSV 格式 K 线数据（Date, Open, High, Low, Close, Volume）
**缓存：** 本地 CSV 缓存（当日内复用）

---

### 2. get_indicators
**功能：** 技术指标计算（MACD/RSI/SMA/Bollinger等13种）
**来源：** stockstats + mootdx OHLCV
**参数：** `symbol`, `indicator`, `curr_date`, `look_back_days`
**返回：** 日期 → 指标值 列表
**支持指标：** `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`, `mfi`

---

### 3. get_fundamentals
**功能：** 公司基本面综合指标
**来源：** 腾讯财经（实时估值）+ mootdx（财务快照）+ akshare（个股信息）+ 同花顺（一致预期EPS）
**参数：** `ticker`, `curr_date`
**返回：** 公司名、PE/PB/市值/换手率、EPS、ROE、净利润、营收、流通股数等
**增强：** Forward PE、PEG、PE消化年限计算（针对高PE股票）

---

### 4. get_balance_sheet
**功能：** 资产负债表
**来源：** akshare → 新浪财经
**参数：** `ticker`, `freq`（annual/quarterly）, `curr_date`
**返回：** CSV 格式资产负债表（前8期）

---

### 5. get_cashflow
**功能：** 现金流量表
**来源：** akshare → 新浪财经
**参数：** `ticker`, `freq`（annual/quarterly）, `curr_date`
**返回：** CSV 格式现金流量表（前8期）

---

### 6. get_income_statement
**功能：** 利润表
**来源：** akshare → 新浪财经
**参数：** `ticker`, `freq`（annual/quarterly）, `curr_date`
**返回：** CSV 格式利润表（前8期）

---

### 7. get_news
**功能：** 个股新闻
**来源：** 东方财富（主力）→ 新浪财经（降级）
**参数：** `ticker`, `start_date`, `end_date`
**返回：** 新闻列表（标题、内容摘要、发布时间、来源、链接）

---

### 8. get_global_news
**功能：** 全球/中国财经快讯
**来源：** 财联社快讯 + 东财全球资讯
**参数：** `curr_date`, `look_back_days`, `limit`
**返回：** 快讯列表（去重后按时间排列）

---

### 9. get_insider_transactions
**功能：** 股东研究（类美股 insider transactions）
**来源：** mootdx F10 → 股东变化章节
**参数：** `ticker`
**返回：** 股东变化文本（前2000字符截断）

---

### 10. get_profit_forecast
**功能：** 一致预期 EPS（券商共识预测）
**来源：** akshare → 同花顺
**参数：** `ticker`, `curr_date`
**返回：** 分年度EPS预测（均值、最小值、最大值、预测机构数）
**增强：** Forward PE、PEG、PE消化年限计算；低覆盖预警（<3家机构）

---

### 11. get_hot_stocks
**功能：** 当日强势股+题材归因
**来源：** 同花顺（10jqka）
**参数：** `curr_date`（空则当天）
**返回：** 涨停股列表（含代码、涨幅、换手率、成交额、大单净量、人工标注题材标签）
**特殊：** 汇总所有标签，输出题材频率排名（top 15）

---

### 12. get_northbound_flow
**功能：** 沪深股通北向资金
**来源：** 同花顺 hsgtApi（实时）+ 本地CSV缓存（历史）
**参数：** `curr_date`, `include_history`
**返回：** 实时分钟级沪股通+深股通累计净流入；历史日线（最近20交易日）
**缓存策略：** 每次获取实时数据后自动保存当日收盘快照到 `northbound_daily.csv`；上游 API 在 2024-08 后停止更新历史数据，本地缓存为唯一可靠历史来源

---

### 13. get_concept_blocks
**功能：** 概念板块/行业分类
**来源：** 百度股市通 PAE API
**参数：** `ticker`
**返回：** 行业分类（申万）、概念主题、地区分类（含当日涨跌幅）

---

### 14. get_fund_flow
**功能：** 个股资金流向
**来源：** 百度股市通 PAE API
**参数：** `ticker`, `curr_date`, `include_history`
**返回：** 实时分钟级主力/散户/超大单/大单/中单/小单净流入；历史日线（最近20交易日）

---

### 15. get_dragon_tiger_board
**功能：** 龙虎榜上榜记录+席位明细+机构参与
**来源：** akshare → 东方财富
**参数：** `ticker`, `trade_date`, `look_back_days`
**返回：** 上榜记录（日期/原因/净买额/成交额/换手率）；买卖席位TOP5；机构买卖席位统计

---

### 16. get_lockup_expiry
**功能：** 限售股解禁日历
**来源：** akshare → 东方财富
**参数：** `ticker`, `trade_date`, `forward_days`
**返回：** 历史解禁记录（15批）；未来解禁日历（含解禁前后20日涨跌幅）

---

### 17. get_industry_comparison
**功能：** 全行业横向对比
**来源：** akshare → 同花顺
**参数：** `ticker`, `trade_date`, `top_n`
**返回：** 全行业表现排名（涨跌幅/成交额/净流入/上涨下跌家数/领涨股），显示 top_n × 2 条（头部+尾部）

---

## data_vendor 路由机制

### 路由配置

```python
# tradingagents/dataflows/default_config.py
data_vendors:
  - a_stock        # 主vendor
  # 可扩展其他市场
```

### 抽象接口层

```python
# tradingagents/dataflows/interface.py
class DataVendorInterface:
    def get_stock_data(self, symbol, start_date, end_date) -> str
    def get_fundamentals(self, ticker, curr_date) -> str
    # ... 其他方法
```

所有数据调用通过 `interface.py` 统一路由，不直接引用具体 vendor 实现。

---

## 多源 fallback 策略

```
主力源失败 → 降级到备份源
```

| 数据类型 | 主力源 | 降级源 |
|----------|--------|--------|
| K线 | mootdx | — |
| 财务三表 | akshare→新浪 | — |
| 个股新闻 | 东方财富 | 新浪财经 |
| 全球快讯 | 财联社 | 东财全球资讯 |
| 北向资金 | 同花顺 hsgtApi | 本地CSV缓存 |

---

## 缓存机制

### OHLCV 缓存
- mootdx K线数据首次获取后缓存至 `~/.tradingagents/cache/{code}-astock-daily.csv`
- 当日内多次调用直接读缓存，不重复请求

### 北向资金自缓存
- 核心问题：2024-08后同花顺/东财停止开放北向历史数据
- 解决方案：每次获取实时数据后，自动将沪股通+深股通收盘值写入 `northbound_daily.csv`
- 读取历史时优先查本地缓存，支持最近20交易日分析

```python
def _save_northbound_snapshot(date_str, hgt, sgt):
    """Append today's northbound close to local CSV cache (dedup by date)."""

def _load_northbound_history(n=20):
    """Load last N days of northbound close data from local cache."""
```

---

## 异常处理模式

### 标准模式
```python
try:
    data = source.fetch(...)
except Exception as e:
    logger.warning(f"Primary source failed: {e}")
    # fallback 或返回空数据
    return fallback_data or f"No data found for {code}"
```

### mootdx 降级
```python
# TCP连接失败（如端口7709不可达）→ 记录 warning，返回提示让用户检查网络
```

### akshare 降级
```python
# push2.eastmoney.com 代理超时 → 自动降级到备用源
```

### 日志级别
- `logger.warning`：单源失败但有 fallback，不影响最终输出
- `logger.error` 或直接 `return f"Error: ..."`：所有源均失败，返回错误提示字符串

---

## 代码参考

**主文件：** `tradingagents/dataflows/a_stock.py`（约1277行）

### 关键辅助函数

```python
def _normalize_ticker(symbol: str) -> str:
    """标准化6位代码，移除SH/SZ/BJ前缀后缀"""

def _get_prefix(code: str) -> str:
    """6位代码→腾讯财经前缀（sh/sz/bj）"""

def resolve_ticker(user_input: str) -> str:
    """中文名称或代码→6位标准化代码"""

def _tencent_quote(codes: list[str]) -> dict:
    """腾讯财经批量实时报价（HTTP GBK）"""

def _load_ohlcv_astock(symbol: str, curr_date: str) -> pd.DataFrame:
    """mootdx OHLCV + CSV缓存"""
```

---

## 注意事项

1. **mootdx TCP 7709**：需确保本地端口 7709 可用（部分券商防火墙可能拦截）
2. **akshare 接口稳定性**：部分接口（如东财 push2）在代理环境下可能超时，约5/5概率会自动降级
3. **数据时效**：K线/北向资金为实时数据；财务三表为历史数据（有1-2个月滞后）；一致预期EPS为预测数据
4. **Proxy 支持**：如需通过代理访问外网数据源，设置 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量
5. **缓存清理**：`~/.tradingagents/cache/` 目录可定期清理释放空间，但会丢失OHLCV缓存和北向历史
6. **龙虎榜/解禁数据**：依赖 akshare，数据质量由 akshare 维护团队保证