#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
渲染五子系统 Harness 评估为独立的 HTML 文件。

用法： python render_assessment_html.py [--target DIR] [--output FILE]
"""

import argparse
from pathlib import Path

from harness_utils import html_report, load_harness_files, score_harness, write_text


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Harness 评估 HTML 报告")
    parser.add_argument("--target", default=".", help="目标目录（默认为当前目录）")
    parser.add_argument("--output", help="输出 HTML 文件路径（默认 target/harness-assessment.html）")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    output_path = Path(args.output).resolve() if args.output else target / "harness-assessment.html"

    score = score_harness(load_harness_files(target))
    write_text(output_path, html_report(score, f"Harness Assessment: {target.name}"))
    print(f"HTML report written to {output_path}")
    print(f"Overall: {score.overall}/100")


if __name__ == "__main__":
    main()