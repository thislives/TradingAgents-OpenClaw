#!/usr/bin/env python3
"""
汇总7个子Agent报告 → 生成完整workflow JSON → E2E验证 → HTML报告
"""
import json, sys, os
from datetime import datetime

def main():
    code = sys.argv[1].strip().zfill(6) if len(sys.argv) > 1 else "300750"
    name = sys.argv[2] if len(sys.argv) > 2 else code

    print(f"\n{'='*60}")
    print(f"汇总 {code} {name} 的7份Subagent报告")
    print(f"{'='*60}")

    analyst_files = {
        "market": f"/tmp/analyst_workflow/{code}_analyst_market.json",
        "fundamentals": f"/tmp/analyst_workflow/{code}_analyst_fundamentals.json",
        "sentiment": f"/tmp/analyst_workflow/{code}_analyst_sentiment.json",
        "news": f"/tmp/analyst_workflow/{code}_analyst_news.json",
        "policy": f"/tmp/analyst_workflow/{code}_analyst_policy.json",
        "hot_money": f"/tmp/analyst_workflow/{code}_analyst_hot_money.json",
        "lockup": f"/tmp/analyst_workflow/{code}_analyst_lockup.json",
    }

    reports = []
    score_map = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}

    print("\n读取Analyst报告:")
    for name_key, path in analyst_files.items():
        if os.path.exists(path):
            try:
                d = json.load(open(path))
                reports.append({
                    "analyst": name_key,
                    "score": d.get("score", "C"),
                    "findings": d.get("findings", []),
                    "conclusion": d.get("conclusion", ""),
                    "detailed_report": d.get("detailed_report", "")
                })
                sc = d.get("score", "C")
                score_map[sc] = score_map.get(sc, 0) + 1
                print(f"  ✅ {name_key}: score={sc} findings={len(d.get('findings',[]))} conc={len(d.get('conclusion',''))}chars")
            except Exception as e:
                print(f"  ❌ {name_key}: {e}")
        else:
            print(f"  ❌ {name_key}: 文件不存在 {path}")

    print(f"\n评分分布: A={score_map['A']} B={score_map['B']} C={score_map['C']} D={score_map['D']} F={score_map['F']}")

    # Quality Gate
    quality_passed = sum(score_map[k] for k in ["A", "B"])
    quality_failed = sum(score_map[k] for k in ["D", "F"])
    if quality_passed >= 2:
        decision = "PASS"
    elif quality_failed > 0:
        decision = "FAIL"
    else:
        decision = "LLM_REVIEW"

    quality = {
        "decision": decision,
        "scores": {r["analyst"]: {"score": r["score"], "status": "PASS" if r["score"] in ["A","B","C"] else "FAIL", "reason": "正常" if r["score"] in ["A","B","C"] else f"质量不足({r['score']}级)"} for r in reports},
        "score_counts": score_map,
        "quality_summary": f"高级报告：A级{score_map['A']}个 + B级{score_map['B']}个 = {quality_passed}个，中级{score_map['C']}级{score_map.get('C',0)}个，低级D级{score_map['D']}个+F级{score_map['F']}个",
        "passed": quality_passed + score_map["C"],
        "failed": quality_failed
    }

    # PASS条件：高级(A+B)>=2 且 低级(D+F)<=1
    if quality_passed >= 2 and quality_failed <= 1:
        decision = "PASS"
    elif quality_failed > 1:
        decision = "FAIL"
    else:
        decision = "LLM_REVIEW"

    # Bull/Bear Debate
    bull_args, bear_args = [], []
    for r in reports:
        if r["score"] in ["A", "B"]:
            for f in r["findings"]:
                if any(kw in f for kw in ["强势", "多头", "上涨", "增长", "积极", "利好", "净流入", "优质", "突破", "强势"]):
                    bull_args.append(f"[{r['analyst']}] {f}")
        elif r["score"] in ["D", "F"]:
            for f in r["findings"]:
                if any(kw in f for kw in ["弱势", "空头", "下跌", "下滑", "风险", "净流出", "减持", "压力"]):
                    bear_args.append(f"[{r['analyst']}] {f}")

    bull_args = list(dict.fromkeys(bull_args))[:8]
    bear_args = list(dict.fromkeys(bear_args))[:8]

    if len(bull_args) > len(bear_args) * 1.5:
        verdict = "Bull"
        reasoning = f"多头论据{len(bull_args)}条 vs 空头论据{len(bear_args)}条，多头明显占优"
    elif len(bear_args) > len(bull_args) * 1.5:
        verdict = "Bear"
        reasoning = f"空头论据{len(bear_args)}条 vs 多头论据{len(bull_args)}条，空头明显占优"
    elif bull_args and not bear_args:
        verdict = "Bull"
        reasoning = f"纯多头环境，多头{len(bull_args)}条，无空头论据"
    elif bear_args and not bull_args:
        verdict = "Bear"
        reasoning = f"纯空头环境，空头{len(bear_args)}条，无多头论据"
    elif bull_args > bear_args:
        verdict = "Bull"
        reasoning = f"多头论据{len(bull_args)}条略占优，空头{len(bear_args)}条"
    elif bear_args > bull_args:
        verdict = "Bear"
        reasoning = f"空头论据{len(bear_args)}条略占优，多头{bull_args}条"
    else:
        verdict = "Neutral"
        reasoning = f"多空均衡，各{len(bull_args)}条论据"

    debate = {
        "bull": bull_args if bull_args else ["无明确多头论据"],
        "bear": bear_args if bear_args else ["无明确空头论据"],
        "verdict": verdict,
        "reasoning": reasoning
    }

    # Portfolio Manager
    score_map_val = {"A": 100, "B": 75, "C": 50, "D": 25, "F": 10}
    raw = sum(score_map_val.get(r["score"], 50) for r in reports) / len(reports) if reports else 50
    qual_mult = 1.0 if decision == "PASS" else 0.8
    adj = raw * qual_mult

    if verdict == "Bull" and adj >= 70:
        signal = "BUY"
        pos = "15%-20%仓位"
    elif verdict == "Bull" and adj >= 50:
        signal = "OVERWEIGHT"
        pos = "10%-15%仓位"
    elif verdict == "Bear" and adj < 40:
        signal = "SELL"
        pos = "0%-5%仓位"
    elif verdict == "Bear" and adj < 60:
        signal = "UNDERWEIGHT"
        pos = "5%-10%仓位"
    else:
        signal = "HOLD"
        pos = "5%-10%仓位"

    portfolio = {
        "signal": signal,
        "score": round(adj),
        "position": pos,
        "reasoning": f"综合评分{round(adj)}分，{'多' if verdict=='Bull' else '空' if verdict=='Bear' else '多空'}头信号{verdict}。{reasoning}"
    }

    # Build final result
    result = {
        "meta": {
            "code": code,
            "name": name,
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "workflow_version": "2.0-LLM",
            "analyst_mode": "openclaw_subagent"
        },
        "analyst_reports": [
            {
                "analyst": r["analyst"],
                "score": r["score"],
                "findings": r["findings"],
                "conclusion": r["conclusion"],
                "detailed_report": r.get("detailed_report", ""),
                "_source": "openclaw_subagent"
            } for r in reports
        ],
        "quality_gate": quality,
        "bull_bear_debate": debate,
        "portfolio_signal": portfolio,
        "errors": []
    }

    # Save
    out_dir = "/root/.openclaw/workspace/scripts"
    out_path = os.path.join(out_dir, f"workflow_result_{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ Workflow JSON已保存: {out_path} ({os.path.getsize(out_path)//1024}KB)")

    # Run E2E verify
    verify_script = "/root/.openclaw/workspace/output/pipeline/scripts/run_e2e_verify.py"
    if os.path.exists(verify_script):
        import subprocess
        print(f"\n{'='*60}")
        print("▶ E2E验证")
        print("=" * 60)
        r = subprocess.run([sys.executable, verify_script, "--json", out_path],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', cwd="/root/.openclaw/workspace/output/pipeline")
        if r.stdout: print(r.stdout[-2000:])
        if r.returncode != 0 and r.stderr: print(r.stderr[-500:])

    # Generate HTML
    html_script = "/root/.openclaw/workspace/output/pipeline/scripts/render_html_report.py"
    os.makedirs("/root/.openclaw/workspace/output/pipeline/scripts/reports", exist_ok=True)
    html_path = f"/root/.openclaw/workspace/output/pipeline/scripts/reports/{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    if os.path.exists(html_script):
        import subprocess
        print(f"\n{'='*60}")
        print("▶ 生成HTML报告")
        print("=" * 60)
        r = subprocess.run([sys.executable, html_script, "--json", out_path, "--output", html_path],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', cwd="/root/.openclaw/workspace/output/pipeline")
        if r.stdout: print(r.stdout[-500:])
        if r.returncode != 0 and r.stderr: print(r.stderr[-500:])

    print(f"\n{'='*60}")
    print("✅ 全部完成!")
    print(f"  Workflow: {out_path}")
    print(f"  HTML: {html_path}")
    print(f"  信号: {signal} | 评分: {round(adj)}分 | 仓位: {pos}")
    print(f"  裁决: {verdict} | 质量门控: {decision}")
    print("=" * 60)

if __name__ == "__main__":
    main()