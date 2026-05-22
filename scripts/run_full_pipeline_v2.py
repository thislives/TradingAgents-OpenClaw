#!/usr/bin/env python3
"""
完整投研Pipeline v2.0: 数据采集 → 7Analyst → Bull/Bear辩论 → Risk Debate → Portfolio Manager → HTML
"""
import json, sys, os, subprocess
from datetime import datetime

OUT_DIR = "/root/.openclaw/workspace/scripts"
TMP_DIR = "/tmp/analyst_workflow"

def load_json(path, default=None):
    if not os.path.exists(path): return default
    try: return json.load(open(path))
    except Exception as e:
        print(f"  解析失败 {path}: {e}")
        return None

def _generate_md(data, out_path):
    """Generate readable markdown from workflow JSON"""
    meta = data.get('meta', {})
    qg = data.get('quality_gate', {})
    pf = data.get('portfolio_signal', {})
    bb = data.get('bull_bear_debate', {})
    rd = data.get('risk_debate', {})
    name_map = {"market":"市场技术","fundamentals":"基本面","sentiment":"情绪","news":"新闻","policy":"政策","hot_money":"游资","lockup":"解禁"}

    md = []
    md.append(f"# {meta.get('name','N/A')}({meta.get('code','N/A')}) 投研报告")
    md.append(f"> Pipeline v{meta.get('pipeline_version','?')} | {meta.get('start_time','')}")
    md.append("")

    md.append("## 质量门")
    md.append(f"- **决策**: {qg.get('decision','?')} | 通过: {qg.get('passed',0)}/7 | 失败: {qg.get('failed',0)}")
    md.append(f"- **分布**: {qg.get('quality_summary','')}")
    md.append("| 分析师 | 评分 | 状态 |")
    md.append("|--------|------|------|")
    for a, info in qg.get('scores', {}).items():
        md.append(f"| {name_map.get(a,a)} | {info.get('score','?')} | {info.get('status','?')} |")
    md.append("")

    md.append("## 交易决策")
    md.append(f"- **信号**: {pf.get('signal','?')}")
    md.append(f"- **评分**: {pf.get('score','?')}分")
    md.append(f"- **仓位**: {pf.get('position','')[:200]}")
    sb = pf.get('score_breakdown', {})
    md.append(f"- **分解**: 基础{sb.get('analyst_base','?')} + 辩论{sb.get('debate_adjustment',0):+d} + 风控{sb.get('risk_adjustment',0):+d} = {sb.get('final','?')}")
    md.append("")

    md.append("## 多空辩论")
    md.append(f"**裁决: {bb.get('verdict','?')}** | Bull {bb.get('bull_score','?')} vs Bear {bb.get('bear_score','?')}")
    md.append("")
    md.append("### 🐂 Bull 论据")
    for a in bb.get('bull', [])[:8]:
        md.append(f"- {a}")
    md.append("")
    md.append("### 🐻 Bear 风险")
    for a in bb.get('bear', [])[:8]:
        md.append(f"- {a}")
    md.append("")

    md.append("## 风险辩论")
    md.append(f"裁决: {rd.get('verdict','?')}")
    md.append("")
    for role, emoji, key in [("Aggressive", "🔴", "aggressive"), ("Conservative", "🔵", "conservative"), ("Neutral", "🟡", "neutral")]:
        d = rd.get(key, {})
        if not d: continue
        md.append(f"### {emoji} {role}")
        for a in d.get('arguments', d.get('balanced_arguments', [])):
            md.append(f"- {a}")
        if key == "neutral":
            md.append(f"仓位: {d.get('position_sizing','')[:200]}")
    md.append("")

    md.append("## 7 Analyst报告")
    for r in data.get('analyst_reports', []):
        name = name_map.get(r.get('analyst',''), r.get('analyst',''))
        md.append(f"### {name} — {r.get('score','?')}级")
        md.append(f"{r.get('conclusion','')}")
        md.append("")

    md.append("> 本报告由AI Multi-Agent系统自动生成，仅供参考，不构成投资建议")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))


def _md_to_pdf(md_path, pdf_path, title="报告"):
    """Convert MD → HTML → PDF via markdown + wkhtmltopdf"""
    import markdown

    with open(md_path, encoding='utf-8') as f:
        md_content = f.read()

    html_body = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body {{ font-family: 'Microsoft YaHei',SimHei,sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #222; line-height: 1.8; }}
h1 {{ border-bottom: 2px solid #333; padding-bottom: 8px; }}
h2 {{ margin-top: 24px; color: #444; }}
h3 {{ color: #555; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
th, td {{ border: 1px solid #ccc; padding: 8px 12px; text-align: left; }}
th {{ background: #f5f5f5; }}
</style>
</head>
<body>{html_body}</body></html>"""

    tmp_html = md_path.replace('.md', '_tmp.html')
    with open(tmp_html, 'w', encoding='utf-8') as f:
        f.write(html_doc)

    r = subprocess.run(["/usr/bin/wkhtmltopdf", "--encoding", "UTF-8", "--quiet",
                        tmp_html, pdf_path], capture_output=True, text=True)
    os.remove(tmp_html)

    if not os.path.exists(pdf_path):
        raise RuntimeError(r.stderr[-300:])


def main():
    code = sys.argv[1].strip().zfill(6) if len(sys.argv) > 1 else "300750"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Look up company name
    name = code
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        match = df[df['code'] == code]
        if len(match) > 0:
            name = match.iloc[0]['name']
    except Exception as e:
        print(f"  ⚠️ 名称查询失败: {e}, 使用代码")

    print(f"  标的: {name}({code})")

    print(f"\n{'='*60}")
    print(f"🚀 完整投研Pipeline v2.0 | {code} {name}")
    print(f"{'='*60}")

    # Phase A: 7 Analyst Reports
    print("\n[Phase A] 读取7份Analyst报告...")
    analysts = ["market", "fundamentals", "sentiment", "news", "policy", "hot_money", "lockup"]
    reports = {}
    score_map = {"A":0,"B":0,"C":0,"D":0,"F":0}
    for a in analysts:
        d = load_json(f"{TMP_DIR}/{code}_analyst_{a}.json")
        if d:
            reports[a] = d
            s = d.get("score","C")
            score_map[s] = score_map.get(s,0) + 1
            print(f"  ✅ {a}: {s} | findings={len(d.get('findings',[]))} | report={len(d.get('detailed_report',''))}chars")
        else:
            print(f"  ❌ {a}: 文件不存在")

    # Phase B: Bull/Bear
    print("\n[Phase B] 读取Bull/Bear辩论...")
    bull = load_json(f"{TMP_DIR}/{code}_bull_researcher.json")
    bear = load_json(f"{TMP_DIR}/{code}_bear_researcher.json")
    if bull: print(f"  ✅ Bull: score={bull.get('score','?')} | {len(bull.get('arguments',[]))}条 | {len(bull.get('detailed_analysis',''))}chars")
    else: print("  ❌ Bull: 未找到")
    if bear: print(f"  ✅ Bear: score={bear.get('score','?')} | {len(bear.get('arguments',[]))}条 | {len(bear.get('detailed_analysis',''))}chars")
    else: print("  ❌ Bear: 未找到")

    # Phase C: Risk Debate
    print("\n[Phase C] 读取Risk Debate...")
    agg = load_json(f"{TMP_DIR}/{code}_risk_aggressive.json")
    con = load_json(f"{TMP_DIR}/{code}_risk_conservative.json")
    neu = load_json(f"{TMP_DIR}/{code}_risk_neutral.json")
    if agg: print(f"  ✅ Aggressive: {len(agg.get('arguments',[]))}条")
    else: print("  ❌ Aggressive: 未找到")
    if con: print(f"  ✅ Conservative: {len(con.get('arguments',[]))}条")
    else: print("  ❌ Conservative: 未找到")
    if neu: print(f"  ✅ Neutral: 仓位={neu.get('position_sizing','?')[:50]}")
    else: print("  ❌ Neutral: 未找到")

    # Phase D: Portfolio Manager
    print("\n[Phase D] Portfolio Manager...")
    score_val = {"A":100,"B":75,"C":50,"D":25,"F":10}
    base = sum(score_val.get(r.get("score","C"),50) for r in reports.values()) / len(reports) if reports else 50

    debate_score = 0
    if bull and bull.get("score") in ["A","B"] and bear and bear.get("score") in ["A","B"]:
        debate_score = 0
    elif bull and bull.get("score") in ["A","B"]:
        debate_score = +10
    elif bear and bear.get("score") in ["A","B"]:
        debate_score = -8

    risk_score = 0
    risk_caps = []
    if con:
        risk_caps.append(con.get("conclusion","")[:200])
    if neu:
        risk_caps.append(neu.get("conclusion","")[:200])
    if con and ("追高" in con.get("conclusion","") or "不追高" in con.get("conclusion","")):
        risk_score -= 5

    final_score = max(30, min(95, base + debate_score + risk_score))

    if final_score >= 80:
        signal = "BUY"
        pos = neu.get("position_sizing","15%-20%仓位") if neu else "15%-20%仓位"
    elif final_score >= 65:
        signal = "OVERWEIGHT"
        pos = neu.get("position_sizing","10%-15%仓位") if neu else "10%-15%仓位"
    elif final_score >= 45:
        signal = "HOLD"; pos = "5%-10%仓位"
    elif final_score >= 30:
        signal = "UNDERWEIGHT"; pos = "0%-5%仓位"
    else:
        signal = "SELL"; pos = "0%仓位"

    print(f"  Base:{base:.0f} Debate:{debate_score:+d} Risk:{risk_score:+d} → Final:{final_score}")
    print(f"  Signal: {signal} | Position: {pos}")

    # Build result
    bull_args = len(bull.get("arguments",[])) if bull else 0
    bear_args = len(bear.get("arguments",[])) if bear else 0

    result = {
        "meta": {"code":code,"name":name,"start_time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"pipeline_version":"2.0-full","architecture":"数据采集→7Analyst→Bull/Bear辩论→Risk Debate→Portfolio Manager"},
        "analyst_reports": [
            dict(analyst=k, score=v.get("score","C"), score_status="PASS" if v.get("score") in ["A","B","C"] else "FAIL",
                 findings=v.get("findings",[]), conclusion=v.get("conclusion",""), detailed_report=v.get("detailed_report",""), _source="openclaw_subagent")
            for k,v in reports.items()
        ],
        "quality_gate": {
            "decision": "PASS" if score_map.get("D",0) + score_map.get("F",0) == 0 else ("FAIL" if score_map.get("F",0) > 0 else "LLM_REVIEW"),
            "scores": {k: {"score": v.get("score","C"), "status": "PASS" if v.get("score") in ["A","B","C"] else "FAIL", "reason": "正常" if v.get("score") in ["A","B","C"] else f"质量不足({v.get('score','?')}级)"} for k,v in reports.items()},
            "score_counts": {k: score_map.get(k,0) for k in ["A","B","C","D","F"]},
            "quality_summary": f"高级报告(A+B): {score_map.get('A',0)+score_map.get('B',0)}个, 中级(C): {score_map.get('C',0)}个, 低级(D+F): {score_map.get('D',0)+score_map.get('F',0)}个",
            "passed": sum(1 for v in reports.values() if v.get("score") in ["A","B","C"]),
            "failed": sum(1 for v in reports.values() if v.get("score") in ["D","F"])
        },
        "bull_bear_debate": {
            "bull": bull.get("arguments",[]) if bull else [],
            "bull_score": bull.get("score","?") if bull else "?",
            "bull_conclusion": bull.get("conclusion","") if bull else "",
            "bull_detailed": bull.get("detailed_analysis","") if bull else "",
            "bull_catalysts": bull.get("key_catalysts",[]) if bull else [],
            "bear": bear.get("arguments",[]) if bear else [],
            "bear_score": bear.get("score","?") if bear else "?",
            "bear_conclusion": bear.get("conclusion","") if bear else "",
            "bear_detailed": bear.get("detailed_analysis","") if bear else "",
            "bear_risks": bear.get("key_risks",[]) if bear else [],
            "verdict": "Bull" if bull_args > bear_args * 1.3 else ("Bear" if bear_args > bull_args * 1.3 else "Neutral"),
            "reasoning": f"多头{bull_args}条(Bull {bull.get('score','?') if bull else '?'}) vs 空头{bear_args}条(Bear {bear.get('score','?') if bear else '?'})"
        },
        "risk_debate": {
            "aggressive": dict(score=agg.get("score","?") if agg else "?", target_claims=agg.get("target_claims",[]) if agg else [], arguments=agg.get("arguments",[]) if agg else [], counter_bear=agg.get("counter_bear","") if agg else "", support_bull=agg.get("support_bull","") if agg else "", conclusion=agg.get("conclusion","") if agg else "") if agg else {},
            "conservative": dict(target_claims=con.get("target_claims",[]) if con else [], arguments=con.get("arguments",[]) if con else [], counter_bull=con.get("counter_bull","") if con else "", support_bear=con.get("support_bear","") if con else "", conclusion=con.get("conclusion","") if con else "") if con else {},
            "neutral": dict(bull_overoptimism=neu.get("bull_overoptimism","") if neu else "", bear_overpessimism=neu.get("bear_overpessimism","") if neu else "", balanced_arguments=neu.get("balanced_arguments",[]) if neu else [], position_sizing=neu.get("position_sizing","") if neu else "", conclusion=neu.get("conclusion","") if neu else "") if neu else {},
            "verdict": "Bull" if (agg and con and len(agg.get("arguments",[])) > len(con.get("arguments",[]))*1.3) else "Neutral"
        },
        "portfolio_signal": {
            "signal":signal,"score":final_score,"position":pos,
            "reasoning":f"综合评分{final_score}分，{signal}建议，{pos}",
            "score_breakdown":{"analyst_base":round(base,1),"debate_adjustment":debate_score,"risk_adjustment":risk_score,"final":final_score},
            "risk_notes":risk_caps
        },
        "errors":[]
    }

    # File naming: 公司简称-6位代码-时间戳.扩展名
    out_path = os.path.join(OUT_DIR, f"workflow_{name}-{code}_{ts}.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ Workflow JSON: {out_path} ({os.path.getsize(out_path)//1024}KB)")

    html_path = ""
    md_path = ""
    pdf_path = ""

    # HTML
    html_script = "/root/.openclaw/workspace/output/pipeline/scripts/render_html_report.py"
    html_path = f"/root/.openclaw/workspace/output/pipeline/scripts/reports/{name}-{code}-{ts}.html"
    if os.path.exists(html_script):
        print("\n▶ 生成HTML报告...")
        r = subprocess.run([sys.executable, html_script, "--json", out_path, "--output", html_path],
                           capture_output=True, text=True, encoding='utf-8', errors='replace',
                           cwd="/root/.openclaw/workspace/output/pipeline")
        if r.stdout: print(r.stdout[-200:])
        if r.returncode != 0 and r.stderr: print(r.stderr[-500:])

    # MD (generate from JSON → readable markdown)
    md_path = f"/root/.openclaw/workspace/output/pipeline/scripts/reports/{name}-{code}-{ts}.md"
    _generate_md(result, md_path)
    print(f"✅ MD: {md_path} ({os.path.getsize(md_path)//1024}KB)")

    # PDF (from MD via markdown→html→wkhtmltopdf)
    if md_path and os.path.exists(md_path):
        pdf_path = f"/root/.openclaw/workspace/output/pipeline/scripts/reports/{name}-{code}-{ts}.pdf"
        try:
            _md_to_pdf(md_path, pdf_path, f"{name}({code})")
            if os.path.exists(pdf_path):
                print(f"✅ PDF: {pdf_path} ({os.path.getsize(pdf_path)//1024}KB)")
        except Exception as e:
            print(f"⚠️ PDF生成失败: {e}")

    print(f"\n{'='*60}")
    print(f"✅ 全部完成!")
    print(f"  JSON: {out_path}")
    print(f"  HTML: {html_path}")
    print(f"  MD:   {md_path}")
    print(f"  PDF:  {pdf_path or '跳过'}")
    print(f"  信号: {signal} ({final_score}分) | 仓位: {pos[:60]}...")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()