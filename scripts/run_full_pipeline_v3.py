#!/usr/bin/env python3
"""
Pipeline V3: 数据采集(多源) → 7分析师(原版A股规则) → 辩论 → 风控 → 三格式输出
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
    """JSON→MD"""
    name_map = {"market":"市场技术","fundamentals":"基本面","sentiment":"情绪","news":"新闻","policy":"政策","hot_money":"游资","lockup":"解禁"}
    meta = data.get('meta', {})
    qg = data.get('quality_gate', {})
    pf = data.get('portfolio_signal', {})
    bb = data.get('bull_bear_debate', {})
    rd = data.get('risk_debate', {})

    md = [f"# {meta.get('name','N/A')}({meta.get('code','N/A')}) 投研报告",
          f"> V3 Pipeline | {meta.get('start_time','')}", ""]

    # Quality Gate
    md.extend(["## 质量门", f"- 决策: {qg.get('decision','?')} | 通过:{qg.get('passed',0)}/7 | 失败:{qg.get('failed',0)}",
               f"- {qg.get('quality_summary','')}",
               "| 分析师 | 评分 |",
               "|--------|------|"])
    for a, info in qg.get('scores', {}).items():
        md.append(f"| {name_map.get(a,a)} | {info['score']} |")
    md.append("")

    # Portfolio
    sb = pf.get('score_breakdown', {})
    md.extend(["## 交易决策",
               f"- **信号: {pf.get('signal','?')}** 评分:{pf.get('score','?')}分",
               f"- 仓位: {pf.get('position','')[:200]}",
               f"- 分解: 基础{sb.get('analyst_base','?')}+辩论{sb.get('debate_adjustment',0):+d}+风控{sb.get('risk_adjustment',0):+d}={sb.get('final','?')}", ""])

    # Bull/Bear
    md.extend(["## 多空辩论",
               f"裁决: {bb.get('verdict','?')} | Bull {bb.get('bull_score','?')} vs Bear {bb.get('bear_score','?')}", ""])
    md.append("### 🐂 Bull")
    for a in bb.get('bull', [])[:8]: md.append(f"- {a}")
    md.append("\n### 🐻 Bear")
    for a in bb.get('bear', [])[:8]: md.append(f"- {a}")
    md.append("")

    # Risk Debate
    md.append("## 风险辩论")
    for role, emoji, key in [("激进看多","🔴","aggressive"),("保守风控","🔵","conservative"),("中性平衡","🟡","neutral")]:
        d = rd.get(key, {})
        if not d: continue
        md.append(f"\n### {emoji} {role}")
        args = d.get('arguments', d.get('balanced_arguments', []))
        for a in args: md.append(f"- {a}")
        if key == 'neutral':
            md.append(f"\n仓位建议: {d.get('position_sizing','')[:120]}（详见交易决策）")
    md.append("")

    # Analyst reports
    md.append("## 7 Analyst报告")
    for r in data.get('analyst_reports', []):
        name = name_map.get(r['analyst'], r['analyst'])
        md.append(f"### {name} — {r['score']}级")
        md.append(f"**结论:** {r['conclusion']}")
        findings = r.get('findings', [])
        if findings:
            md.append("\n**关键数据:**")
            for f in findings[:8]:
                md.append(f"- {f}")
        dtl = r.get('detailed_report', '')
        if dtl:
            md.append(f"\n<details><summary>详细分析</summary>\n\n{dtl[:2000]}\n\n</details>")
        md.append("")

    md.append("> 本报告由AI Multi-Agent V3系统自动生成，仅供参考")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))

def _md_to_pdf(md_path, pdf_path, title="报告"):
    """MD→PDF (markdown→html→wkhtmltopdf)"""
    import markdown
    with open(md_path) as f: md_content = f.read()
    html_body = markdown.markdown(md_content, extensions=['tables'])
    html_doc = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{title}</title>
<style>body{{font-family:SimHei,sans-serif;max-width:900px;margin:40px auto;line-height:1.8;color:#222}}
h1{{border-bottom:2px solid #333}}h2{{color:#444;margin-top:24px}}h3{{color:#555}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:8px}}th{{background:#f5f5f5}}</style>
</head><body>{html_body}</body></html>"""
    tmp = md_path.replace('.md','_tmp.html')
    with open(tmp,'w',encoding='utf-8') as f: f.write(html_doc)
    subprocess.run(["/usr/bin/wkhtmltopdf","--encoding","UTF-8","--quiet",tmp,pdf_path])
    os.remove(tmp)

def main():
    code = sys.argv[1].strip().zfill(6) if len(sys.argv) > 1 else "300750"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Run data collection
    print(f"\n▶ 数据采集(V3多源)...")
    collector = "/root/.openclaw/workspace/scripts/collect_data_v3.py"
    r = subprocess.run([sys.executable, collector, code], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"❌ 数据采集失败: {r.stderr[-300:]}")
        sys.exit(1)
    print(r.stdout[-500:])

    # Load V3 data
    v3 = load_json(f"{TMP_DIR}/{code}_data_v3.json")
    if not v3:
        print("❌ 无法加载V3数据")
        sys.exit(1)
    name = v3.get('name', code)
    print(f"\n{'='*60}")
    print(f"🚀 Pipeline V3 | {name}({code})")
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
            score_map[d.get("score","C")] = score_map.get(d.get("score","C"),0) + 1
            print(f"  ✅ {a}: {d.get('score','?')} | findings={len(d.get('findings',[]))} | report={len(d.get('detailed_report',''))}chars")
        else:
            print(f"  ❌ {a}: 未找到(需先运行子agent)")

    # Phase B: Bull/Bear
    print("\n[Phase B] 读取Bull/Bear辩论...")
    bull = load_json(f"{TMP_DIR}/{code}_bull_researcher.json")
    bear = load_json(f"{TMP_DIR}/{code}_bear_researcher.json")
    if bull: print(f"  ✅ Bull: score={bull.get('score','?')} | {len(bull.get('arguments',[]))}条")
    if bear: print(f"  ✅ Bear: score={bear.get('score','?')} | {len(bear.get('arguments',[]))}条")

    # Phase C: Risk Debate
    print("\n[Phase C] 读取Risk Debate...")
    agg = load_json(f"{TMP_DIR}/{code}_risk_aggressive.json")
    con = load_json(f"{TMP_DIR}/{code}_risk_conservative.json")
    neu = load_json(f"{TMP_DIR}/{code}_risk_neutral.json")
    for label, d in [("Aggressive", agg), ("Conservative", con), ("Neutral", neu)]:
        if d:
            args = d.get('arguments', d.get('balanced_arguments', []))
            print(f"  ✅ {label}: {len(args)}条")
        else:
            print(f"  ❌ {label}: 未找到")

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
    if con and ("追高" in con.get("conclusion","") or "不追高" in con.get("conclusion","")):
        risk_score -= 5

    final_score = max(30, min(95, base + debate_score + risk_score))

    if final_score >= 80: signal, pos = "BUY", neu.get("position_sizing","15-20%") if neu else "15-20%"
    elif final_score >= 65: signal, pos = "OVERWEIGHT", neu.get("position_sizing","10-15%") if neu else "10-15%"
    elif final_score >= 45: signal, pos = "HOLD", "5-10%"
    elif final_score >= 30: signal, pos = "UNDERWEIGHT", "0-5%"
    else: signal, pos = "SELL", "0%"

    print(f"  Base:{base:.0f} Debate:{debate_score:+d} Risk:{risk_score:+d} → Final:{final_score} | {signal}")

    # Build result
    bull_args = len(bull.get("arguments",[])) if bull else 0
    bear_args = len(bear.get("arguments",[])) if bear else 0

    result = {
        "meta": {"code":code, "name":name, "start_time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "pipeline_version":"3.0", "architecture":"V3多源数据→7Analyst→辩论→风控→三格式"},
        "quality_gate": {
            "decision": "PASS" if score_map.get("D",0)+score_map.get("F",0)==0 else ("FAIL" if score_map.get("F",0)>0 else "LLM_REVIEW"),
            "scores": {k: {"score": v.get("score","C"), "status": "PASS" if v.get("score") in ["A","B","C"] else "FAIL", "reason": "正常" if v.get("score") in ["A","B","C"] else f"质量不足"} for k,v in reports.items()},
            "score_counts": {k: score_map.get(k,0) for k in ["A","B","C","D","F"]},
            "quality_summary": f"A+B={score_map.get('A',0)+score_map.get('B',0)}, C={score_map.get('C',0)}, D+F={score_map.get('D',0)+score_map.get('F',0)}",
            "passed": sum(1 for v in reports.values() if v.get("score") in ["A","B","C"]),
            "failed": sum(1 for v in reports.values() if v.get("score") in ["D","F"])
        },
        "analyst_reports": [dict(analyst=k, score=v.get("score","C"), score_status="PASS" if v.get("score") in ["A","B","C"] else "FAIL", findings=v.get("findings",[]), conclusion=v.get("conclusion",""), detailed_report=v.get("detailed_report",""), _source="openclaw_subagent") for k,v in reports.items()],
        "bull_bear_debate": {
            "bull": bull.get("arguments",[]) if bull else [], "bull_score": bull.get("score","?") if bull else "?",
            "bear": bear.get("arguments",[]) if bear else [], "bear_score": bear.get("score","?") if bear else "?",
            "bull_conclusion": bull.get("conclusion","") if bull else "", "bear_conclusion": bear.get("conclusion","") if bear else "",
            "bull_detailed": bull.get("detailed_analysis","") if bull else "", "bear_detailed": bear.get("detailed_analysis","") if bear else "",
            "bull_catalysts": bull.get("key_catalysts",[]) if bull else [], "bear_risks": bear.get("key_risks",[]) if bear else [],
            "verdict": "Bull" if bull_args > bear_args*1.3 else ("Bear" if bear_args > bull_args*1.3 else "Neutral"),
            "reasoning": f"多头{bull_args}条(Bull {bull.get('score','?') if bull else '?'}) vs 空头{bear_args}条(Bear {bear.get('score','?') if bear else '?'})"
        },
        "risk_debate": {
            "aggressive": dict(arguments=agg.get("arguments",[]) if agg else [], conclusion=agg.get("conclusion","") if agg else "") if agg else {},
            "conservative": dict(arguments=con.get("arguments",[]) if con else [], conclusion=con.get("conclusion","") if con else "") if con else {},
            "neutral": dict(balanced_arguments=neu.get("balanced_arguments",[]) if neu else [], position_sizing=neu.get("position_sizing","") if neu else "", conclusion=neu.get("conclusion","") if neu else "") if neu else {},
            "verdict": "Bull" if (agg and con and len(agg.get("arguments",[])) > len(con.get("arguments",[]))*1.3) else "Neutral"
        },
        "portfolio_signal": {
            "signal": signal, "score": final_score, "position": pos,
            "reasoning": f"综合评分{final_score}分，{signal}建议，{pos}",
            "score_breakdown": {"analyst_base": round(base,1), "debate_adjustment": debate_score, "risk_adjustment": risk_score, "final": final_score},
            "risk_notes": [con.get("conclusion","")[:150] if con else "", neu.get("conclusion","")[:150] if neu else ""]
        },
        "errors": []
    }

    # Save JSON
    json_path = os.path.join(OUT_DIR, f"workflow_{name}-{code}_{ts}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ JSON: {json_path} ({os.path.getsize(json_path)//1024}KB)")

    # HTML
    html_script = "/root/.openclaw/workspace/output/pipeline/scripts/render_html_report.py"
    html_path = f"/root/.openclaw/workspace/output/pipeline/scripts/reports/{name}-{code}-{ts}.html"
    if os.path.exists(html_script):
        subprocess.run([sys.executable, html_script, "--json", json_path, "--output", html_path],
                       capture_output=True, text=True)
        print(f"✅ HTML: {html_path} ({os.path.getsize(html_path)//1024}KB)")

    # MD
    md_path = f"/root/.openclaw/workspace/output/pipeline/scripts/reports/{name}-{code}-{ts}.md"
    _generate_md(result, md_path)
    print(f"✅ MD: {md_path} ({os.path.getsize(md_path)//1024}KB)")

    # PDF (MD→PDF)
    pdf_path = f"/root/.openclaw/workspace/output/pipeline/scripts/reports/{name}-{code}-{ts}.pdf"
    try:
        _md_to_pdf(md_path, pdf_path, f"{name}({code})")
        if os.path.exists(pdf_path):
            print(f"✅ PDF: {pdf_path} ({os.path.getsize(pdf_path)//1024}KB)")
    except Exception as e:
        print(f"⚠️ PDF: {e}")

    print(f"\n{'='*60}")
    print(f"✅ V3完成 | {name}({code}) | {signal} {final_score}分")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
