#!/usr/bin/env python3
"""
主控验证脚本
顺序执行: multi_agent_workflow.py → run_e2e_verify.py → render_html_report.py
修复路径: 工作流JSON保存到scripts/，HTML保存到reports/
"""
import json
import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
WORKFLOW_SCRIPT = SCRIPTS_DIR / "multi_agent_workflow.py"
VERIFY_SCRIPT = SCRIPT_DIR / "run_e2e_verify.py"
RENDER_SCRIPT = SCRIPT_DIR / "render_html_report.py"
REPORTS_DIR = SCRIPT_DIR / "reports"
JSON_RESULTS_DIR = SCRIPTS_DIR  # workflow JSON保存位置

REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def run_cmd(cmd, desc, timeout=300, cwd=None):
    print(f"\n{'='*60}")
    print(f"▶ {desc}")
    print("=" * 60)
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        cwd=cwd or PROJECT_ROOT,
        encoding="utf-8", errors="replace"
    )
    if result.stdout:
        # 只打印最后30行
        lines = result.stdout.strip().split("\n")
        for line in lines[-30:]:
            print(line)
    if result.returncode != 0 and result.stderr:
        print(f"STDERR:\n{result.stderr[-500:]}")
    return result.returncode == 0


def find_latest_json(stock_code):
    """从scripts/目录找最新的workflow result JSON"""
    prefix = f"workflow_result_{stock_code}_"
    jsons = sorted(JSON_RESULTS_DIR.glob(f"{prefix}*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not jsons:
        # 找所有workflow result
        jsons = sorted(JSON_RESULTS_DIR.glob("workflow_result_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsons[0] if jsons else None


def main():
    parser = argparse.ArgumentParser(description="主控验证脚本")
    parser.add_argument("stock_code", type=str, help="股票代码")
    parser.add_argument("stock_name", type=str, nargs="?", default=None, help="股票名称")
    parser.add_argument("--skip-workflow", action="store_true", help="跳过工作流，直接验证+生成HTML")
    args = parser.parse_args()

    stock_code = args.stock_code.strip().zfill(6)
    stock_name = args.stock_name or stock_code
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n{'='*60}")
    print(f"  股票: {stock_code} {stock_name}")
    print(f"  时间: {ts}")
    print("=" * 60)

    json_path = None

    # Step 1: 运行工作流
    if not args.skip_workflow:
        ok = run_cmd(
            [sys.executable, str(WORKFLOW_SCRIPT), stock_code],
            f"Step 1/3: 运行多Agent工作流 ({stock_code} {stock_name})",
            timeout=300
        )
        if not ok:
            print("ERROR: Workflow failed")
            # 继续尝试找已有JSON
            json_path = find_latest_json(stock_code)
            if not json_path:
                return 1
        else:
            json_path = find_latest_json(stock_code)
    else:
        json_path = find_latest_json(stock_code)

    if not json_path or not json_path.exists():
        print(f"ERROR: 未找到workflow result JSON: {json_path}")
        return 1

    print(f"\n✅ 工作流JSON: {json_path} ({json_path.stat().st_size//1024}KB)")

    # Step 2: E2E验证
    verify_out = SCRIPT_DIR / f"verify_{stock_code}_{ts}.json"
    ok = run_cmd(
        [sys.executable, str(VERIFY_SCRIPT), "--json", str(json_path), "--output", str(verify_out)],
        f"Step 2/3: E2E验证 ({stock_code})",
        timeout=60
    )

    if verify_out.exists():
        with open(verify_out, encoding="utf-8") as f:
            verify_data = json.load(f)
        print(f"\n{'='*50}")
        print(f"  Overall: {verify_data.get('overall')} {'✅' if verify_data.get('overall')=='PASS' else '⚠️'}")
        print(f"  报告数: {verify_data.get('report_count')}/7")
        print(f"  质量门控: {verify_data['gate_check']['decision']} {'✅' if verify_data['gate_check']['ok'] else '❌'}")
        print(f"  多空辩论: {verify_data['debate_check']['verdict']} {'✅' if verify_data['debate_check']['ok'] else '❌'}")
        print(f"  投资信号: {verify_data['signal_check']['signal']} {'✅' if verify_data['signal_check']['ok'] else '❌'}")
        print("  Analyst检查:")
        for c in verify_data.get("analyst_checks", []):
            icon = "✅" if c["ok"] else "⚠️"
            print(f"    {icon} {c['analyst']:12s} score={c['score']} findings={c['findings_count']:2d} conclusion={c['conclusion_len']:3d}chars")
        if verify_data.get("errors"):
            print(f"  数据错误({len(verify_data['errors'])}条):")
            for e in verify_data["errors"][:3]:
                print(f"    ! {e[:100]}")
        print("=" * 50)
    else:
        print("WARNING: 验证JSON未生成")

    # Step 3: 生成HTML
    html_path = REPORTS_DIR / f"{stock_code}_{ts}.html"
    ok = run_cmd(
        [sys.executable, str(RENDER_SCRIPT), "--json", str(json_path), "--output", str(html_path)],
        f"Step 3/3: 生成HTML报告",
        timeout=30
    )

    print(f"\n{'='*60}")
    print("✅ 验证流程完成!")
    print(f"  Workflow JSON: {json_path}")
    print(f"  验证结果:   {verify_out}")
    print(f"  HTML报告:   {html_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())