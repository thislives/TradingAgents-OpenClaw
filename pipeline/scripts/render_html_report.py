#!/usr/bin/env python3
"""
独立HTML报告生成器 v2.0
从workflow JSON生成完整HTML报告（包含Risk Debate）
"""
import json, argparse, sys
from pathlib import Path

SIGNAL_COLORS = {
    "BUY": "#00c853", "OVERWEIGHT": "#64dd17", "HOLD": "#ffc107",
    "UNDERWEIGHT": "#ff6d00", "SELL": "#f44336",
}
SCORE_COLORS = {"A": "#00c853", "B": "#64dd17", "C": "#ffc107", "D": "#ff6d00", "F": "#f44336"}
VERDICT_COLORS = {"Bull": "#00c853", "Bear": "#f44336", "Neutral": "#ffc107"}

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def score_badge(score):
    color = SCORE_COLORS.get(score, "#9e9e9e")
    return f'<span style="background:{color};color:#fff;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:bold">{score}</span>'

def signal_badge(signal):
    color = SIGNAL_COLORS.get(signal, "#9e9e9e")
    return f'<span style="background:{color};color:#fff;padding:4px 16px;border-radius:14px;font-weight:bold;font-size:14px">{signal}</span>'

def verdict_badge(verdict):
    color = VERDICT_COLORS.get(verdict, "#9e9e9e")
    return f'<span style="background:{color};color:#fff;padding:3px 12px;border-radius:12px;font-weight:bold">{verdict}</span>'

def collapse(title, content):
    return f'<details checked style="margin:8px 0"><summary style="cursor:pointer;padding:8px 12px;background:#1a1f36;border-radius:6px;font-weight:bold;color:#e0e6ff">{title}</summary><div style="padding:12px 8px">{content}</div></details>'

def render_findings(findings):
    if not findings:
        return '<p style="color:#f44336">⚠️ 无数据</p>'
    return '<ul style="padding-left:16px;color:#b0b8d6;font-size:13px">' + ''.join(f"<li style='margin:3px 0'>{f}</li>" for f in findings) + '</ul>'

def analyst_section(report, index):
    score = report.get("score", "C")
    color = SCORE_COLORS.get(score, "#9e9e9e")
    name_map = {"market":"市场技术","fundamentals":"基本面","sentiment":"情绪","news":"新闻","policy":"政策","hot_money":"游资","lockup":"解禁"}
    analyst = report.get("analyst", f"Analyst {index+1}")
    display_name = name_map.get(analyst, analyst)
    findings = report.get("findings", [])
    conclusion = report.get("conclusion", "")
    detailed = report.get("detailed_report", "")
    badge = score_badge(score)

    findings_html = render_findings(findings)
    conclusion_html = f'<p style="margin:0;padding:10px;background:#1e2340;border-left:3px solid {color};border-radius:4px;font-size:13px;line-height:1.7;white-space:pre-wrap">{conclusion}</p>'
    detailed_html = f'<div style="margin-top:8px;padding:10px;background:#1a1f36;border-radius:4px;font-size:12px;color:#b0b8d6;white-space:pre-wrap;line-height:1.6;word-wrap:break-word">{detailed}</div>' if detailed else ""

    sub_id = f"{analyst}{index}"
    return f"""
<div style="background:#12172a;padding:12px;border-radius:8px;border:1px solid #2a3156;margin:8px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <span style="font-weight:bold;color:#e0e6ff;font-size:14px">{display_name}</span>
    {badge}
  </div>
  <details open style="margin:4px 0"><summary style="cursor:pointer;color:#b0b8d6;font-size:13px">📝 结论</summary>{conclusion_html}</details>
  <details style="margin:4px 0"><summary style="cursor:pointer;color:#b0b8d6;font-size:13px">📊 关键数据（{len(findings)}条）</summary>{findings_html}</details>
  <details style="margin:4px 0"><summary style="cursor:pointer;color:#b0b8d6;font-size:13px">📋 详细分析</summary>{detailed_html}</details>
</div>"""

def bull_bear_full_section(data):
    bb = data.get("bull_bear_debate", {})
    bull_pts = bb.get("bull", [])
    bear_pts = bb.get("bear", [])
    bull_detailed = bb.get("bull_detailed", "")
    bear_detailed = bb.get("bear_detailed", "")
    bull_catalysts = bb.get("bull_catalysts", [])
    bear_risks = bb.get("bear_risks", [])
    verdict = bb.get("verdict", "Neutral")
    bull_score = bb.get("bull_score", "?")
    bear_score = bb.get("bear_score", "?")
    reasoning = bb.get("reasoning", "")

    bull_items = ''.join(f"<li style='margin:4px 0'>{p}</li>" for p in bull_pts[:8])
    bear_items = ''.join(f"<li style='margin:4px 0'>{p}</li>" for p in bear_pts[:8])

    catalysts_html = ''.join(f'<span style="background:#1a3a1a;color:#00c853;padding:2px 8px;border-radius:10px;font-size:11px;margin-right:4px;display:inline-block;margin-bottom:4px">{c}</span>' for c in bull_catalysts[:5])
    risks_html = ''.join(f'<span style="background:#3a1a1a;color:#f44336;padding:2px 8px;border-radius:10px;font-size:11px;margin-right:4px;display:inline-block;margin-bottom:4px">{r}</span>' for r in bear_risks[:5])

    vb = verdict_badge(verdict)

    return f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0">
  <div style="background:#12172a;padding:12px;border-radius:8px;border:1px solid #2a3156">
    <div style="color:#00c853;font-weight:bold;margin-bottom:8px">🐂 多头 (Bull) | {bull_score}级</div>
    <ul style="padding-left:18px;color:#b0b8d6">{bull_items}</ul>
    <div style="margin-top:8px">{catalysts_html}</div>
    <div style="border-top:1px solid #1a3a1a;margin-top:8px;padding-top:6px;font-size:11px;color:#9e9e9e">{bull_detailed[:400]}...</div>
  </div>
  <div style="background:#12172a;padding:12px;border-radius:8px;border:1px solid #2a3156">
    <div style="color:#f44336;font-weight:bold;margin-bottom:8px">🐻 空头 (Bear) | {bear_score}级</div>
    <ul style="padding-left:18px;color:#b0b8d6">{bear_items}</ul>
    <div style="margin-top:8px">{risks_html}</div>
    <div style="border-top:1px solid #3a1a1a;margin-top:8px;padding-top:6px;font-size:11px;color:#9e9e9e">{bear_detailed[:400]}...</div>
  </div>
</div>
<div style="text-align:center;margin:8px 0">{vb}<span style="color:#b0b8d6;margin-left:8px;font-size:12px">{reasoning}</span></div>"""

def risk_debate_section(data):
    rd = data.get("risk_debate", {})
    agg = rd.get("aggressive", {})
    con = rd.get("conservative", {})
    neu = rd.get("neutral", {})

    agg_args = agg.get("arguments", [])
    agg_conc = agg.get("conclusion", "")
    agg_cb = agg.get("counter_bear", "")
    agg_sb = agg.get("support_bull", "")
    agg_score = agg.get("score", "?")

    con_args = con.get("arguments", [])
    con_conc = con.get("conclusion", "")
    con_cb = con.get("counter_bull", "")
    con_sb = con.get("support_bear", "")

    neu_bo = neu.get("bull_overoptimism", "")
    neu_bp = neu.get("bear_overpessimism", "")
    neu_ps = neu.get("position_sizing", "")
    neu_conc = neu.get("conclusion", "")

    verdict_r = rd.get("verdict", "Neutral")
    verdict_badge_r = verdict_badge(verdict_r)

    agg_html = f"""
<div style="background:#1a0d0d;padding:12px;border-radius:8px;border:1px solid #5a1a1a;margin-bottom:10px">
  <div style="color:#ff5252;font-weight:bold;font-size:14px;margin-bottom:8px">🔴 激进看多 (Aggressive) | {agg_score}级</div>
  <div style="color:#b0b8d6;font-size:12px;margin-bottom:6px">反驳空头论据：</div>
  <ul style="padding-left:16px;color:#e0e6ff;font-size:12px">{"".join(f"<li style='margin:3px 0'>{a}</li>" for a in agg_args[:5])}</ul>
  <div style="color:#b0b8d6;font-size:12px;margin:8px 0 4px">反驳内容：</div>
  <p style="color:#9e9e9e;font-size:12px">{agg_cb[:300]}{"..." if len(agg_cb)>300 else ""}</p>
  <div style="border-top:1px solid #3a1a1a;margin-top:8px;padding-top:6px;font-size:11px;color:#ff5252">结论：{agg_conc[:250]}{"..." if len(agg_conc)>250 else ""}</div>
</div>"""

    con_html = f"""
<div style="background:#0d1a1f;padding:12px;border-radius:8px;border:1px solid #1a4a5a;margin-bottom:10px">
  <div style="color:#40c4ff;font-weight:bold;font-size:14px;margin-bottom:8px">🔵 保守风控 (Conservative)</div>
  <div style="color:#b0b8d6;font-size:12px;margin-bottom:6px">反驳多头论据：</div>
  <ul style="padding-left:16px;color:#e0e6ff;font-size:12px">{"".join(f"<li style='margin:3px 0'>{a}</li>" for a in con_args[:5])}</ul>
  <div style="color:#b0b8d6;font-size:12px;margin:8px 0 4px">反驳内容：</div>
  <p style="color:#9e9e9e;font-size:12px">{con_cb[:300]}{"..." if len(con_cb)>300 else ""}</p>
  <div style="border-top:1px solid #1a3a4a;margin-top:8px;padding-top:6px;font-size:11px;color:#40c4ff">结论：{con_conc[:250]}{"..." if len(con_conc)>250 else ""}</div>
</div>"""

    neu_html = f"""
<div style="background:#1a1a0d;padding:12px;border-radius:8px;border:1px solid #5a5a1a;margin-bottom:10px">
  <div style="color:#ffd740;font-weight:bold;font-size:14px;margin-bottom:8px">🟡 中性平衡 (Neutral)</div>
  <div style="color:#b0b8d6;font-size:12px;margin-bottom:6px">多头过度乐观：</div>
  <p style="color:#9e9e9e;font-size:12px">{neu_bo[:300]}{"..." if len(neu_bo)>300 else ""}</p>
  <div style="color:#b0b8d6;font-size:12px;margin:8px 0 4px">空头过度悲观：</div>
  <p style="color:#9e9e9e;font-size:12px">{neu_bp[:300]}{"..." if len(neu_bp)>300 else ""}</p>
  <div style="border-top:1px solid #4a4a1a;margin-top:8px;padding-top:6px">
    <div style="color:#ffd740;font-weight:bold;font-size:13px">仓位建议：{neu_ps[:300]}{"..." if len(neu_ps)>300 else ""}</div>
    <div style="color:#ffd740;font-size:11px;margin-top:4px">结论：{neu_conc[:250]}{"..." if len(neu_conc)>250 else ""}</div>
  </div>
</div>"""

    return f"""
<div style="background:#12172a;padding:14px;border-radius:8px;border:1px solid #2a3156;margin:12px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
    <span style="font-size:15px;font-weight:bold;color:#e0e6ff">风险辩论 (Risk Debate)</span>
    {verdict_badge_r}
  </div>
  {agg_html}
  {con_html}
  {neu_html}
</div>"""

def render_html_report(data, output_path):
    meta = data.get("meta", {})
    code = meta.get("code", "N/A")
    name = meta.get("name", code)
    start_time = meta.get("start_time", "")
    pipeline_version = meta.get("pipeline_version", "N/A")
    analyst_reports = data.get("analyst_reports", [])
    quality_gate = data.get("quality_gate", {})
    portfolio = data.get("portfolio_signal", {})
    errors = data.get("errors", [])

    signal = portfolio.get("signal", "HOLD")
    signal_score = portfolio.get("score", "N/A")
    signal_position = portfolio.get("position", "")
    signal_reasoning = portfolio.get("reasoning", "")
    score_breakdown = portfolio.get("score_breakdown", {})

    signal_html = signal_badge(signal)
    bull_bear_html = bull_bear_full_section(data)
    risk_debate_html = risk_debate_section(data)

    gate_decision = quality_gate.get("decision", "N/A")
    gate_summary = quality_gate.get("quality_summary", "")
    gate_passed = quality_gate.get("passed", 0)
    gate_failed = quality_gate.get("failed", 0)
    gate_scores = quality_gate.get("scores", {})
    score_counts = quality_gate.get("score_counts", {})

    name_map = {"market":"市场技术","fundamentals":"基本面","sentiment":"情绪","news":"新闻","policy":"政策","hot_money":"游资","lockup":"解禁"}
    score_table_rows = ""
    for key, val in gate_scores.items():
        display = name_map.get(key, key)
        status = val.get("status", "N/A")
        reason = val.get("reason", "")
        score = val.get("score", "N/A")
        status_color = "#00c853" if status == "PASS" else "#f44336"
        score_table_rows += f"<tr><td style='padding:6px 8px;color:#e0e6ff'>{display}</td><td style='color:{status_color};font-weight:bold;padding:6px 8px'>{status}</td><td style='color:#9e9e9e;padding:6px 8px;font-size:12px'>{reason}</td><td style='padding:6px 8px'>{score_badge(score)}</td></tr>"

    gate_decision_color = "#00c853" if gate_decision == "PASS" else ("#ffc107" if gate_decision == "FAIL" else "#64dd17")
    gate_decision_html = f'<span style="background:{gate_decision_color};color:#fff;padding:3px 12px;border-radius:12px;font-weight:bold">{gate_decision}</span>'

    score_summary_html = ""
    for grade in ["A", "B", "C", "D", "F"]:
        cnt = score_counts.get(grade, 0)
        if cnt > 0:
            score_summary_html += f'<span style="margin-right:12px">{score_badge(grade)} ×{cnt}</span>'

    analyst_sections = "".join(analyst_section(r, i) for i, r in enumerate(analyst_reports))

    if errors:
        error_items = "".join(f"<li style='color:#f44336;margin:4px 0'>{e}</li>" for e in errors)
        errors_html = f'<div style="background:#1a0a0a;padding:12px;border-radius:8px;border:1px solid #5a1a1a;margin:12px 0"><div style="color:#f44336;font-weight:bold;margin-bottom:8px">⚠️ 错误日志</div><ul style="padding-left:18px">{error_items}</ul></div>'
    else:
        errors_html = '<p style="color:#00c853;text-align:center;padding:12px">✅ 无错误</p>'

    gate_card = f"""
<div style="background:#12172a;padding:14px;border-radius:8px;border:1px solid #2a3156;margin:12px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
    <span style="font-size:15px;font-weight:bold;color:#e0e6ff">质量门 (Quality Gate)</span>
    {gate_decision_html}
  </div>
  <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="color:#b0b8d6;border-bottom:1px solid #2a3156">
        <th style="text-align:left;padding:6px 8px">维度</th>
        <th style="text-align:center;padding:6px 8px">状态</th>
        <th style="text-align:left;padding:6px 8px">说明</th>
        <th style="text-align:center;padding:6px 8px">评分</th>
      </tr></thead>
      <tbody>{score_table_rows}</tbody>
    </table>
  </div>
  <div style="margin-top:10px;padding:8px;background:#1e2340;border-radius:6px">
    <div style="color:#b0b8d6;font-size:12px;margin-bottom:6px">评分分布: {score_summary_html or "无"}</div>
    <div style="color:#b0b8d6;font-size:12px">{gate_summary}</div>
    <div style="color:#b0b8d6;font-size:12px;margin-top:4px">通过: {gate_passed} / 失败: {gate_failed}</div>
  </div>
</div>"""

    breakdown_parts = []
    if score_breakdown:
        breakdown_parts.append(f"基础评分: {score_breakdown.get('analyst_base','?')}")
        db = score_breakdown.get('debate_adjustment', 0)
        rb = score_breakdown.get('risk_adjustment', 0)
        if db: breakdown_parts.append(f"辩论调整: {'+' if db>=0 else ''}{db}")
        if rb: breakdown_parts.append(f"风控调整: {'+' if rb>=0 else ''}{rb}")
        breakdown_parts.append(f"最终: {score_breakdown.get('final','?')}")

    # Portfolio card - full width, no overflow constraints
    portfolio_card = f"""
<div style="background:#12172a;padding:16px;border-radius:8px;border:1px solid #2a3156;margin:12px 0;word-wrap:break-word">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
    <span style="font-size:16px;font-weight:bold;color:#e0e6ff">交易决策 (Portfolio)</span>
    {signal_html}
  </div>
  <div style="margin-bottom:10px">
    <span style="font-size:22px;font-weight:bold;color:#00c853">{signal_score}分</span>
    <div style="color:#b0b8d6;font-size:13px;line-height:1.7;white-space:pre-wrap;margin-top:8px">{signal_position}</div>
  </div>
  <div style="color:#9e9e9e;font-size:12px">{' | '.join(breakdown_parts)}</div>
  <div style="margin-top:10px;padding:10px;background:#1e2340;border-radius:4px;font-size:12px;color:#b0b8d6;line-height:1.6;white-space:pre-wrap">{signal_reasoning[:500]}{"..." if len(signal_reasoning)>500 else ""}</div>
</div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>投研报告 - {name}({code})</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0d1117;color:#e0e6ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:16px}}
.header{{background:linear-gradient(135deg,#1a237e,#283593);padding:20px;border-radius:12px;margin-bottom:16px;text-align:center}}
.header h1{{font-size:24px;font-weight:bold;color:#fff;margin-bottom:8px}}
.header p{{color:#c5cae9;font-size:13px}}
.section{{margin:16px 0}}
.score-grid{{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}}
.details{{font-size:12px;color:#9e9e9e;margin-top:6px}}
a{{color:#64b5f6}}
</style>
</head>
<body>

<div class="header">
  <h1>📊 AI多Agent投研报告</h1>
  <p>{name}({code}) | {start_time} | Pipeline v{pipeline_version}</p>
</div>

{portfolio_card}

{gate_card}

{collapse("多空辩论 (Bull/Bear)", bull_bear_html)}

{collapse("风险辩论 (Risk Debate)", risk_debate_html)}

{collapse("分析师报告 (Analyst Reports)", analyst_sections)}

{collapse("错误日志 (Errors)", errors_html)}

<div style="margin-top:24px;padding:12px;text-align:center;color:#4a5580;font-size:11px;border-top:1px solid #2a3156">
  本报告由AI多Agent自动化分析系统生成，仅供参考，不构成投资建议。<br>
  市场有风险，投资需谨慎。
</div>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

def main():
    parser = argparse.ArgumentParser(description="HTML报告生成器 v2.0")
    parser.add_argument("--json", type=str, required=True, help="workflow JSON路径")
    parser.add_argument("--output", type=str, required=True, help="HTML输出路径")
    args = parser.parse_args()
    data = load_json(args.json)
    render_html_report(data, args.output)
    size = Path(args.output).stat().st_size
    print(f"✅ HTML report saved to: {args.output} ({size//1024}KB)")

if __name__ == "__main__":
    main()