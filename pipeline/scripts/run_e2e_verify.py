#!/usr/bin/env python3
"""
E2E Pipeline 验证脚本
验证多Agent工作流的每一步输出是否完整
"""
import json
import argparse
import sys
import os
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_report(name, report, rules):
    """检查单个analyst报告"""
    findings = report.get("findings", [])
    conclusion = report.get("conclusion", "")
    score = report.get("score", "")

    min_findings = rules.get("findings", 1)
    min_conclusion = rules.get("conclusion", 10)

    findings_ok = len(findings) >= min_findings
    conclusion_ok = len(conclusion) >= min_conclusion

    status = "PASS" if (findings_ok and conclusion_ok) else "WARN"
    reasons = []
    if not findings_ok:
        reasons.append(f"findings={len(findings)} < {min_findings}")
    if not conclusion_ok:
        reasons.append(f"conclusion={len(conclusion)}chars < {min_conclusion}chars")

    return {
        "analyst": name,
        "score": score,
        "findings_count": len(findings),
        "conclusion_len": len(conclusion),
        "status": status,
        "ok": status == "PASS",
        "reasons": reasons,
    }


def verify_workflow(json_path):
    """验证已有workflow JSON"""
    data = load_json(json_path)

    meta = data.get("meta", {})
    stock_code = meta.get("code", "N/A")
    stock_name = meta.get("name", stock_code)
    run_time = meta.get("start_time", "")

    # 检查规则
    rules_map = {
        "market_report": {"findings": 3, "conclusion": 10},
        "fundamentals_report": {"findings": 1, "conclusion": 10},
        "sentiment_report": {"findings": 1, "conclusion": 10},
        "news_report": {"findings": 1, "conclusion": 10},
        "policy_report": {"findings": 1, "conclusion": 10},
        "hot_money_report": {"findings": 1, "conclusion": 10},
        "lockup_report": {"findings": 3, "conclusion": 10},
    }

    # analyst报告检查
    analyst_reports = data.get("analyst_reports", [])
    report_names = [
        "market_report",
        "fundamentals_report",
        "sentiment_report",
        "news_report",
        "policy_report",
        "hot_money_report",
        "lockup_report",
    ]

    analyst_checks = []
    for i, report in enumerate(analyst_reports):
        name = report.get("analyst", report_names[i] if i < len(report_names) else f"report_{i}")
        # 映射到规则
        rule_key = name if name in rules_map else report_names[i] if i < len(report_names) else None
        if rule_key and rule_key in rules_map:
            check = check_report(name, report, rules_map[rule_key])
        else:
            check = check_report(name, report, {"findings": 1, "conclusion": 10})
        analyst_checks.append(check)

    # Quality Gate
    quality_gate = data.get("quality_gate", {})
    gate_decision = quality_gate.get("decision", "")
    gate_ok = gate_decision in ("PASS", "FAIL", "LLM_REVIEW")
    gate_check = {
        "decision": gate_decision,
        "ok": gate_ok,
    }

    # Bull/Bear Debate
    debate = data.get("bull_bear_debate", {})
    verdict = debate.get("verdict", "")
    debate_ok = verdict in ("Bull", "Bear", "Neutral")
    debate_check = {
        "verdict": verdict,
        "ok": debate_ok,
    }

    # Portfolio Signal
    portfolio = data.get("portfolio_signal", {})
    signal = portfolio.get("signal", "")
    signal_ok = signal in ("BUY", "OVERWEIGHT", "HOLD", "UNDERWEIGHT", "SELL")
    signal_check = {
        "signal": signal,
        "ok": signal_ok,
    }

    # 错误
    errors = data.get("errors", [])

    # Overall
    all_ok = all(c["ok"] for c in analyst_checks) and gate_ok and debate_ok and signal_ok
    any_warn = any(c["status"] == "WARN" for c in analyst_checks)
    if all_ok:
        overall = "PASS"
    elif any_warn:
        overall = "PARTIAL"
    else:
        overall = "FAIL"

    return {
        "stock": {"code": stock_code, "name": stock_name, "time": run_time},
        "overall": overall,
        "report_count": len(analyst_checks),
        "gate_check": gate_check,
        "debate_check": debate_check,
        "signal_check": signal_check,
        "analyst_checks": analyst_checks,
        "errors": errors,
        "details": {
            "quality_gate": quality_gate,
            "bull_bear_debate": debate,
            "portfolio_signal": portfolio,
        },
    }


def run_workflow_and_verify(stock_code, stock_name=None):
    """运行完整流程并验证"""
    wf_script = PROJECT_ROOT / "scripts" / "multi_agent_workflow.py"
    if not wf_script.exists():
        return {"error": f"Workflow script not found: {wf_script}"}

    cmd = [sys.executable, str(wf_script), stock_code]
    if stock_name:
        cmd.append(stock_name)

    print(f"Running workflow: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return {"error": f"Workflow failed: {result.stderr}"}

    # 找最新生成的JSON
    output_dir = PROJECT_ROOT / "output" / "pipeline"
    json_files = sorted(output_dir.glob("workflow_result_*.json"), key=lambda p: p.stat().st_mtime)
    if not json_files:
        return {"error": "No workflow result JSON found after run"}

    latest_json = json_files[-1]
    print(f"Using result: {latest_json}")
    return verify_workflow(latest_json)


def main():
    parser = argparse.ArgumentParser(description="E2E Pipeline 验证脚本")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--json", type=str, help="验证已有workflow JSON文件")
    group.add_argument("--run", type=str, help="运行完整流程并验证 (股票代码)")

    parser.add_argument("--name", type=str, default=None, help="股票名称 (配合--run使用)")
    parser.add_argument("--output", type=str, default=None, help="验证报告输出路径")

    args = parser.parse_args()

    if args.json:
        result = verify_workflow(args.json)
    else:
        result = run_workflow_and_verify(args.run, args.name)

    # 输出
    output_path = args.output
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Verification report saved to: {output_path}")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("overall") in ("PASS", "PARTIAL") else 1


if __name__ == "__main__":
    sys.exit(main())