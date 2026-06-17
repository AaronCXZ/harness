#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
运行轻量级 Harness 基准测试：
  1. 对目标 Harness 评分
  2. 检查 evals/evals.json 中的评估覆盖情况
  3. 生成 JSON 报告和可选的 HTML 报告

用法： python run_benchmark.py [--target DIR] [--output FILE] [--html FILE] [--evals FILE]
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from harness_utils import (
    format_score_report,
    html_report,
    load_harness_files,
    read_json,
    score_harness,
    write_text,
    escape_html,
    HarnessScore,
)


@dataclass
class EvalCheck:
    passed: bool
    message: str


@dataclass
class EvalScore:
    score: int
    passed: int
    total: int
    cases: int
    checks: List[EvalCheck]


@dataclass
class BenchmarkReport:
    generated_at: str
    target: str
    harness: HarnessScore
    evals: EvalScore
    recommendation: str


def score_evals(evals_data: Dict[str, Any]) -> EvalScore:
    """评估 evals.json 的覆盖情况，返回 EvalScore"""
    cases = evals_data.get("evals", []) if isinstance(evals_data, dict) else []

    checks = [
        EvalCheck(passed=len(cases) >= 10, message="At least 10 eval cases"),
        EvalCheck(
            passed=any("minimal" in item.get("name", "").lower() or "creation" in item.get("name", "").lower()
                       for item in cases),
            message="Covers minimal harness creation"
        ),
        EvalCheck(
            passed=any("session" in item.get("name", "").lower() or "continuity" in item.get("name", "").lower()
                       for item in cases),
            message="Covers session continuity"
        ),
        EvalCheck(
            passed=any("assessment" in item.get("name", "").lower() or "score" in item.get("name", "").lower()
                       for item in cases),
            message="Covers harness assessment"
        ),
        EvalCheck(
            passed=any("verification" in item.get("name", "").lower() for item in cases),
            message="Covers verification workflow"
        ),
        EvalCheck(
            passed=any("memory" in item.get("name", "").lower() for item in cases),
            message="Covers memory taxonomy"
        ),
        EvalCheck(
            passed=any("tool" in item.get("name", "").lower() or "permission" in item.get("name", "").lower() or
                       "safety" in item.get("name", "").lower() for item in cases),
            message="Covers tool safety"
        ),
        EvalCheck(
            passed=any("multi-agent" in item.get("name", "").lower() or "delegation" in item.get("name", "").lower() or
                       "coordination" in item.get("name", "").lower() for item in cases),
            message="Covers multi-agent coordination"
        ),
        EvalCheck(
            passed=all("prompt" in item and "expected_output" in item and "expectations" in item
                       for item in cases),
            message="Each eval has prompt, expected output, expectations"
        ),
        EvalCheck(
            passed=all(isinstance(item.get("expectations", []), list) and len(item["expectations"]) >= 3
                       for item in cases),
            message="Each eval has at least three expectation checks"
        )
    ]

    passed = sum(1 for c in checks if c.passed)
    score = round((passed / len(checks)) * 100) if checks else 0
    return EvalScore(score=score, passed=passed, total=len(checks), cases=len(cases), checks=checks)


def generate_recommendation(harness: HarnessScore, evals: EvalScore) -> str:
    """根据评分生成建议"""
    if harness.overall >= 85 and evals.score >= 90:
        return "Ready for realistic before/after agent-session benchmarking."
    if harness.overall < 70:
        return f"Improve the {harness.bottleneck} subsystem before benchmarking agent behavior."
    if evals.score < 80:
        return "Expand eval coverage before treating benchmark results as representative."
    return "Usable, with some gaps worth tightening after first real sessions."


def render_benchmark_html(report: BenchmarkReport) -> str:
    """生成 HTML 格式的基准报告（在 harness 报告基础上附加 eval 和推荐）"""
    base_html = html_report(report.harness, f"Harness Benchmark: {Path(report.target).name}")
    eval_section = f"""
<section>
  <h2>Eval Coverage <span>{report.evals.score}/100</span></h2>
  <p>{report.evals.passed}/{report.evals.total} benchmark checks passed across {report.evals.cases} eval cases.</p>
  <ul>
    {''.join(f'<li class="{"pass" if c.passed else "fail"}">{"PASS" if c.passed else "FAIL"} {escape_html(c.message)}</li>' for c in report.evals.checks)}
  </ul>
</section>
<section>
  <h2>Recommendation</h2>
  <p>{escape_html(report.recommendation)}</p>
</section>
"""
    return base_html.replace("</main>", eval_section + "\n</main>")


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 Harness 基准测试")
    parser.add_argument("--target", default=".", help="目标目录（默认为当前目录）")
    parser.add_argument("--output", help="输出 JSON 报告文件路径（默认 target/harness-benchmark.json）")
    parser.add_argument("--html", help="输出 HTML 报告文件路径")
    parser.add_argument("--evals", help="evals.json 文件路径（默认 ../evals/evals.json）")
    parser.add_argument("--min-score", type=int, default=70, help="Harness 最低通过分数（默认 70）")
    parser.add_argument("--min-eval-score", type=int, default=80, help="Eval 最低通过分数（默认 80）")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    output_path = Path(args.output).resolve() if args.output else target / "harness-benchmark.json"

    if args.evals:
        evals_path = Path(args.evals).resolve()
    else:
        # 默认在当前脚本目录的上上级的 evals/ 下
        script_dir = Path(__file__).resolve().parent
        evals_path = script_dir.parent / "evals" / "evals.json"

    # 加载并评分 harness
    harness_score = score_harness(load_harness_files(target))

    # 加载并评分 evals
    try:
        evals_data = read_json(evals_path)
    except FileNotFoundError:
        print(f"Warning: evals file not found at {evals_path}, using empty eval data.")
        evals_data = {"evals": []}
    eval_score = score_evals(evals_data)

    report = BenchmarkReport(
        generated_at=datetime.now().isoformat(),
        target=str(target),
        harness=harness_score,
        evals=eval_score,
        recommendation=generate_recommendation(harness_score, eval_score)
    )

    # 写入 JSON（自定义序列化）
    def to_dict(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return {k: to_dict(v) for k, v in obj.__dict__.items()}
        if isinstance(obj, list):
            return [to_dict(v) for v in obj]
        return obj

    write_text(output_path, json.dumps(to_dict(report), indent=2) + "\n")
    print(f"Benchmark report written to {output_path}")
    print()

    # 输出摘要
    print(format_score_report(harness_score, str(target)))
    print(f"Eval coverage: {eval_score.score}/100 ({eval_score.passed}/{eval_score.total})")
    print(f"Recommendation: {report.recommendation}")

    if args.html:
        html_path = Path(args.html).resolve()
        write_text(html_path, render_benchmark_html(report))
        print(f"HTML benchmark report written to {html_path}")

    exit_code = 0
    if harness_score.overall < args.min_score:
        exit_code = 1
    if eval_score.score < args.min_eval_score:
        exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()