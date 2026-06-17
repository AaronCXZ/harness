#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证现有 Harness 并输出评分报告。

用法： python validate_harness.py [--target DIR] [--json] [--html FILE] [--min-score 70]
"""

import argparse
import json
import sys
from pathlib import Path

from harness_utils import (
    format_score_report,
    html_report,
    load_harness_files,
    score_harness,
    write_text,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="验证项目 Harness")
    parser.add_argument("--target", default=".", help="目标目录（默认为当前目录）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    parser.add_argument("--html", help="输出 HTML 报告的文件路径")
    parser.add_argument("--min-score", type=int, default=70,
                        help="最低通过分数（默认 70）")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    min_score = args.min_score

    files = load_harness_files(target)
    score = score_harness(files)

    if args.html:
        html_path = Path(args.html).resolve()
        write_text(html_path, html_report(score, f"Harness Assessment: {target.name}"))
        print(f"HTML report written to {html_path}")

    if args.json:
        # 将 dataclass 转换为 dict 以便 JSON 序列化
        def to_dict(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return {k: to_dict(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [to_dict(v) for v in obj]
            return obj
        print(json.dumps(to_dict(score), indent=2))
    else:
        print(format_score_report(score, str(target)))

    sys.exit(0 if score.overall >= min_score else 1)


if __name__ == "__main__":
    main()