# TradingAgents Pipeline V3 — 项目文档

> **版本**: V3.0 | **日期**: 2026-05-22 | **状态**: ✅ 生产就绪

---

## 一、架构概览

```
                    ┌──────────────────────┐
                    │  V3 数据采集层(多源)   │
                    │  Tencent行情 + Sina K线│
                    │  新闻 + PE/市值/52周高 │
                    └──────────┬───────────┘
                               ▼
              ┌────────────────────────────────┐
              │  7 Analyst Subagents(并行)      │
              │  每个包含完整A股规则+数据上下文  │
              ├────────────────────────────────┤
              │ ◉市场技术 ◉基本面 ◉情绪 ◉新闻  │
              │ ◉政策分析 ◉游资追踪 ◉解禁监控  │
              └──────────────┬─────────────────┘
                             ▼
              ┌────────────────────────────────┐
              │  辩论层(LLM Subagent, 并行)     │
              │  🐂Bull Researcher(A股多头)     │
              │  🐻Bear Researcher(A股空头)     │
              └──────────────┬─────────────────┘
                             ▼
              ┌────────────────────────────────┐
              │  风控层(LLM Subagent, 并行)     │
              │  🔴Aggressive 🔵Conservative   │
              │  🟡Neutral(仓位+止损建议)       │
              └──────────────┬─────────────────┘
                             ▼
              ┌────────────────────────────────┐
              │  Portfolio Manager             │
              │  综合评分 → 信号→ BUY/HOLD/SELL │
              └──────────────┬─────────────────┘
                             ▼
              ┌────────────────────────────────┐
              │  四格式输出                     │
              │  JSON(原始) → HTML(报告)       │
              │  JSON → MD(可读)               │
              │  MD  → markdown→wkhtmltopdf→PDF│
              └────────────────────────────────┘
```

## 二、与原版TradingAgents对比

| 维度 | 原版 | V3 |
|------|------|-----|
| Agent类型 | LangChain Tool-Call循环 | OpenClaw Subagent并行 |
| 数据源 | mootdx+baostock+东财 | **腾讯(行情/PE/市值)+Sina(K线/新闻)** 双源验证 |
| 可靠度 | 单源, 网络断则失败 | 双源fallback, 3次重试, 错误日志 |
| A股规则 | 涨跌停/T+1/北向全量 | ✅ 同等完整(T+1/±10%涨停板/散户情绪) |
| 财务数据 | akshare(重) | **腾讯API(PE/市值/52周高低, 无依赖)** |
| 辩论机制 | LangGraph交替2轮 | Subagent各1轮(并行), 等效2轮产出 |
| 风控辩论 | 三方LangGraph交替 | ✅ 三方Subagent并行(同等能力) |
| 报告格式 | 纯文本 | **HTML(62KB)+MD(16KB)+PDF(187KB)** |
| 启动方式 | `python cli.py` | `TradingAgents分析 <代码>` 一键触发 |

## 三、文件结构

```
scripts/
├── collect_data_v3.py           ← V3数据采集(腾讯+Sina双源,3次重试)
├── run_full_pipeline_v3.py      ← V3主控(数据采集→分析→辩论→风控→四格式)
├── aggregate_reports.py         ← 旧汇总器(备份)
├── multi_agent_workflow.py      ← 旧工作流(备份)
└── run_full_pipeline_v2.py      ← V2版本(备份)

output/pipeline/scripts/
├── render_html_report.py        ← HTML渲染引擎(含三方辩论展示)
├── run_e2e_verify.py            ← 端到端验证
└── reports/                     ← 报告输出目录

subagent产出 (/tmp/analyst_workflow/):
├── {code}_data_v3.json          ← V3数据(nice+PE+指标+新闻+规则)
├── {code}_analyst_{role}.json   ← 7份分析师报告
├── {code}_bull_researcher.json  ← 多头辩论
├── {code}_bear_researcher.json  ← 空头辩论
└── {code}_risk_{role}.json      ← 三方风控
```

## 四、使用方式

### 一键分析
```
用户: TradingAgents分析 002611
小O:  自动执行完整V3流程 → 发送HTML+MD+PDF到企业微信
```

### 手动执行
```bash
# 数据采集
python3 scripts/collect_data_v3.py 002611

# 完整Pipeline
python3 scripts/run_full_pipeline_v3.py 002611
```

## 五、数据源详细

| 数据 | 主源 | 备源 | 字段 |
|------|------|------|------|
| 实时行情 | 腾讯qt.gtimg.cn | Sina hq.sinajs.cn | 价格/涨跌/量 |
| PE/市值 | 腾讯qt.gtimg.cn | — | PE=53, 市值=192亿 |
| K线 | Sina money.finance | — | 60条日K |
| 技术指标 | 自算(MA/RSI/MACD/Boll) | — | 全部14个指标 |
| 新闻 | Sina vip.stock | — | 10条最新 |
| A股规则 | 内置 | — | T+1/涨跌停/手数 |

## 六、信号分级

| 评分 | 信号 | 说明 |
|------|------|------|
| ≥80 | BUY | 强力买入 |
| 65-79 | OVERWEIGHT | 增持 |
| 45-64 | HOLD | 持有 |
| 30-44 | UNDERWEIGHT | 减持 |
| <30 | SELL | 卖出 |

## 七、已知限制与改进方向

1. **财务深度**: 当前仅有PE/市值, 缺少ROE/净利/营收等深度财务指标(akshare导入OOM)
2. **北向资金**: 获取不稳定, 需优化网络
3. **新闻源**: Sina新闻提取简单, 可增加AI摘要
4. **评委系统**: UZI-Skill的51评委role-play尚未集成

## 八、变更记录 (Changelog)

### V3.0 — 2026-05-22 深夜

**数据层升级**
- 新增 `collect_data_v3.py`：腾讯(qt.gtimg.cn)+Sina双源，3次重试，无akshare依赖
- 腾讯API提供：实时行情/PE/市值/52周高低
- Sina提供：60条日K线+新闻公告
- 14个技术指标全量自算(MA5/10/20/60, RSI, MACD, Boll)
- 内置A股规则上下文(T+1/涨跌停/手数/估值区间)

**Pipeline V3**
- 新增 `run_full_pipeline_v3.py`：数据采集→7分析师→辩论→风控→四格式输出
- 公司名称自动查询(腾讯API返回)
- 文件名规范: `公司简称-代码-时间戳.{html|md|pdf}`

**输出格式**
- JSON → MD：`_generate_md()` 含质量门/交易决策/多空辩论/风控/7分析师全文
- MD → PDF：`_md_to_pdf()` 通过 markdown→html→wkhtmltopdf 转换
- HTML(82KB) + MD(54KB) + PDF(215KB) + JSON(92KB) 四格式

**Bug修复**
- #1: 报告名称硬编码"宁德时代" → 改为公司查询
- #2: Aggressive/Conservative JSON中文引号解析失败 → 修复+容错
- #3: 质量门缺失 → 加入评分分布+通过/失败计数
- #4: MD只有结论无数据 → 加入findings+d详细报告
- #5: HTML详细报告被截断(max-height:200px) → 去掉限制
- #6: 分析师无子菜单 → 增加折叠: 📝结论/📊关键数据/📋详细分析
- #7: MD仓位重复(风控+交易决策) → 风控区只保留首行摘要
- #8: reasoning与position内容重复 → reasoning改为评分公式摘要
- #9: 交易决策框太小 → 全宽展开

**文档**
- 新增 `PROJECT_DOC_V3.md`（本文档）
- 新增根目录 README.md / .gitignore / LICENSE (MIT)
- 清洗敏感数据(代理IP替换)

### V2.0 — 2026-05-22 下午

- 从TradingAgents-AStock学习Bull/Bear+Risk Debate三方辩论
- 创建7分析师LLM Subagent体系(替代原关键词匹配)
- Bull Researcher + Bear Researcher + Aggressive/Conservative/Neutral
- 新增 `run_full_pipeline_v2.py`
- HTML渲染器增加Risk Debate三方展示

### V1.0 — 2026-05-20

- 初始版本: 数据采集(Sina) → 7 Analyst → Quality Gate → 简单评分
- `collect_data.py` / `aggregate_reports.py` / `multi_agent_workflow.py`
