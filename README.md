# TradingAgents Pipeline for OpenClaw

> 基于 TradingAgents-AStock 的 A股多Agent投研流水线，适配 OpenClaw 工作流

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 一句话

说 `TradingAgents分析 <代码>`，7个AI分析师并行工作，经过多空辩论和三方风控，自动生成 HTML + Markdown + PDF 三格式报告，发送到企业微信。

## 架构

```
V3数据采集(腾讯+Sina双源)
        ↓
7 Analyst Subagents(并行)
  ◉市场技术 ◉基本面 ◉情绪 ◉新闻
  ◉政策分析 ◉游资追踪 ◉解禁监控
        ↓
Bull/Bear 辩论(LLM Subagent)
        ↓
Risk Debate 三方风控(LLM Subagent)
  🔴激进 🔵保守 🟡中性
        ↓
Portfolio Manager → BUY/HOLD/SELL
        ↓
四格式输出: JSON + HTML(82KB) + MD(54KB) + PDF(215KB)
```

## 与 TradingAgents-AStock 对比

| 维度 | 原版 | 本版 |
|------|------|------|
| 数据源 | mootdx单源 | **腾讯+Sina双源, 3次重试** |
| Agent | LangChain Tool-Call 循环 | **OpenClaw Subagent 并行** |
| 财务 | akshare(内存密集) | 腾讯API(PE/市值/52周, 零依赖) |
| 报告 | 纯文本 | **HTML+MD+PDF 三格式** |
| 分发 | 无 | **企业微信自动发送** |
| 触发 | Python CLI | **自然语言: TradingAgents分析 002611** |

## 快速开始

### 前提条件
- OpenClaw Agent 运行环境
- Python 3.9+
- wkhtmltopdf (PDF生成)

### 安装
```bash
# 1. 安装依赖
pip install markdown

# 2. 安装wkhtmltopdf
# 从 https://github.com/wkhtmltopdf/packaging/releases 下载对应版本

# 3. 复制项目到 OpenClaw workspace
cp -r scripts/ pipeline/ skills/ ~/.openclaw/workspace/
```

### 使用
```
# 在 OpenClaw 中说:
TradingAgents分析 002611
TradingAgents分析 东方精工
TradingAgents分析 300750
```

### 手动运行
```bash
# 数据采集
python3 scripts/collect_data_v3.py 002611

# 完整Pipeline (需先通过OpenClaw生成7份分析师报告)
python3 scripts/run_full_pipeline_v3.py 002611
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `scripts/collect_data_v3.py` | V3数据采集(腾讯+Sina, 双源, 重试) |
| `scripts/run_full_pipeline_v3.py` | V3主控Pipeline(数据→分析→辩论→输出) |
| `pipeline/scripts/render_html_report.py` | HTML报告渲染(折叠菜单, 无截断) |
| `skills/*.SKILL.md` | OpenClaw Skill定义文件 |

## 输出格式

每次运行产出4个文件:
```
reports/东方精工-002611-20260522-235102.html  ← HTML报告(82KB)
reports/东方精工-002611-20260522-235102.md    ← Markdown(54KB)
reports/东方精工-002611-20260522-235102.pdf   ← PDF(215KB)
scripts/workflow_东方精工-002611_*.json       ← 原始数据(92KB)
```

## 数据源

| 数据 | 来源 | 说明 |
|------|------|------|
| 行情/PE/市值 | 腾讯 qt.gtimg.cn | 零依赖, 快速 |
| K线(60日) | Sina money.finance | 稳定 |
| 技术指标 | 自算(MA/RSI/MACD/Boll) | 14个指标 |
| 新闻公告 | Sina/东财 | 备用 |

## 参考上游

本项目参考了以下开源项目:
- [TradingAgents-AStock](https://github.com/simonlin1212/TradingAgents-astock) — A股多Agent架构(本项目借鉴其7分析师+辩论+风控理念)
- [a-stock-data](https://github.com/simonlin1212/a-stock-data) — A股数据工具包(数据源参考)
- [AkShare](https://github.com/akfamily/akshare) — 备选数据源

## 免责声明

本工具仅供学习研究和技术演示，不构成任何投资建议。投资决策请咨询持牌专业机构。市场有风险，投资需谨慎。
