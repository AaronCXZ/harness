#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
创建最小生产级 Harness 文件：
  - AGENTS.md 或 CLAUDE.md
  - feature_list.json
  - progress.md
  - session-handoff.md
  - init.sh

用法： python create_harness.py [--target DIR] [--agent-file AGENTS.md|CLAUDE.md]
        [--package-manager npm|pnpm|yarn|bun] [--force] [--commands CMD1,CMD2,...]
"""

import argparse
from pathlib import Path

from harness_utils import (
    ProjectInfo,
    copy_template,
    detect_package_manager,
    detect_project,
    file_exists,
    init_script_from_commands,
    verification_commands,
    write_text,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="创建项目 Harness")
    parser.add_argument("--target", default=".", help="目标目录（默认为当前目录）")
    parser.add_argument("--agent-file", default="AGENTS.md",
                        help="Agent 指令文件名（AGENTS.md 或 CLAUDE.md）")
    parser.add_argument("--package-manager", choices=["npm", "pnpm", "yarn", "bun"],
                        help="显式指定包管理器")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    parser.add_argument("--commands", help="逗号分隔的自定义验证命令（覆盖自动检测）")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    agent_file = args.agent_file
    force = args.force

    # 检测项目
    project = detect_project(target)
    project.package_manager = detect_package_manager(target, args.package_manager)

    # 获取验证命令
    if args.commands:
        commands = [cmd.strip() for cmd in args.commands.split(",") if cmd.strip()]
    else:
        commands = verification_commands(project, args.package_manager)

    # 确保目标目录存在
    target.mkdir(parents=True, exist_ok=True)

    # 替换变量
    replacements = {
        "AGENT_FILE_NAME": agent_file,
        "PROJECT_PURPOSE": (
            f"Project harness for reliable agent-assisted development in a {project.stack} codebase."
            if project.stack != "generic"
            else "Project harness for reliable agent-assisted development."
        ),
        "VERIFICATION_COMMANDS": "\n".join(f"- `{cmd}`" for cmd in commands),
        "PRIMARY_VERIFICATION_COMMAND": "./init.sh"
    }

    results = []

    # 复制模板文件
    results.append(copy_template("agents.md", target / agent_file, replacements, force))
    results.append(copy_template("feature-list.json", target / "feature_list.json", {}, force))
    results.append(copy_template("progress.md", target / "progress.md", {}, force))
    results.append(copy_template("session-handoff.md", target / "session-handoff.md", {}, force))

    # 生成 init.sh
    init_path = target / "init.sh"
    if force or not init_path.exists():
        script_content = init_script_from_commands(commands)
        write_text(init_path, script_content)
        init_path.chmod(init_path.stat().st_mode | 0o111)
        results.append({"path": str(init_path), "status": "written"})
    else:
        results.append({"path": str(init_path), "status": "skipped", "reason": "exists"})

    # 输出结果
    print(f"Created harness for {target}")
    print(f"Detected stack: {project.stack}")
    print("Verification commands:")
    for cmd in commands:
        print(f"  - {cmd}")
    print()
    for res in results:
        status = res["status"].upper()
        path_str = str(Path(res["path"]).relative_to(target))
        reason = f" ({res['reason']})" if "reason" in res else ""
        print(f"{status} {path_str}{reason}")


if __name__ == "__main__":
    main()