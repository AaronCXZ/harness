#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Harness 工具函数模块
提供文件操作、项目检测、模板复制、验证命令生成、评分报告等。
"""

import json
import shutil
import stat
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union, Tuple


# ---------- 常量 ----------
SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_ROOT / "templates"
SUBSYSTEMS = ("instructions", "state", "verification", "scope", "lifecycle")


# ---------- 数据结构 ----------
@dataclass
class FileInfo:
    """表示一个文件的信息（路径和内容）"""
    path: str
    content: str


@dataclass
class CheckResult:
    """单项检查结果"""
    passed: bool
    message: str


@dataclass
class SubsystemScore:
    """一个子系统的评分结果"""
    score: int          # 1-5
    passed: int         # 通过检查项数
    total: int          # 总检查项数
    checks: List[CheckResult]


@dataclass
class HarnessScore:
    """整体 Harness 评分"""
    overall: int        # 0-100
    bottleneck: str     # 最弱子系统名称
    subsystems: Dict[str, SubsystemScore]


@dataclass
class ProjectInfo:
    """项目检测信息"""
    root: Path
    stack: str
    package_json: Optional[Dict[str, Any]]
    files: List[str]
    package_manager: str


# ---------- 文件操作 ----------
def file_exists(path: Union[str, Path]) -> bool:
    """检查文件或目录是否存在"""
    return Path(path).exists()


def read_text(path: Union[str, Path]) -> str:
    """读取文本文件内容"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_json(path: Union[str, Path]) -> Dict[str, Any]:
    """读取 JSON 文件并解析"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path: Union[str, Path], content: str) -> None:
    """写入文本文件，自动创建父目录"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def copy_file_safe(source: Union[str, Path], target: Union[str, Path],
                   force: bool = False) -> Dict[str, str]:
    """
    安全复制文件，若目标存在且 force=False 则跳过。
    返回 {'path': str, 'status': 'written' | 'skipped', 'reason': ...}
    """
    src = Path(source)
    dst = Path(target)
    if not force and dst.exists():
        return {"path": str(dst), "status": "skipped", "reason": "exists"}
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {"path": str(dst), "status": "written"}


def copy_template(template_name: str, target_path: Union[str, Path],
                  replacements: Optional[Dict[str, str]] = None,
                  force: bool = False) -> Dict[str, str]:
    """
    复制模板文件并替换 {{key}} 占位符。
    若目标存在且 force=False 则跳过。
    若模板以 .sh 结尾，设置可执行权限。
    """
    if replacements is None:
        replacements = {}
    dst = Path(target_path)
    if not force and dst.exists():
        return {"path": str(dst), "status": "skipped", "reason": "exists"}

    template_file = TEMPLATE_DIR / template_name
    content = read_text(template_file)
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    write_text(dst, content)

    if template_name.endswith(".sh"):
        # 添加执行权限 (chmod +x)
        dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return {"path": str(dst), "status": "written"}


# ---------- 项目检测 ----------
def detect_package_manager(root: Path, explicit: Optional[str] = None) -> str:
    """检测包管理器，若 explicit 指定则直接返回"""
    if explicit:
        return explicit
    lock_files = {
        "bun": ("bun.lockb", "bun.lock"),
        "pnpm": ("pnpm-lock.yaml",),
        "yarn": ("yarn.lock",),
    }
    for pm, patterns in lock_files.items():
        if any((root / p).exists() for p in patterns):
            return pm
    return "npm"


def list_files(root: Path, max_files: int = 1000) -> List[str]:
    """
    递归列出根目录下所有文件（相对路径），忽略常见目录。
    最多返回 max_files 个。
    """
    ignored = {".git", "node_modules", "dist", "build", ".next", ".venv", "venv", "__pycache__"}
    results: List[str] = []

    def walk(current: Path, relative: str) -> None:
        if len(results) >= max_files:
            return
        try:
            entries = list(current.iterdir())
        except PermissionError:
            return
        for entry in entries:
            if len(results) >= max_files:
                return
            if entry.name in ignored:
                continue
            rel = f"{relative}/{entry.name}" if relative else entry.name
            if entry.is_dir():
                walk(entry, rel)
            elif entry.is_file():
                results.append(rel)

    walk(root, "")
    return sorted(results)


def detect_project(root: Path) -> ProjectInfo:
    """
    检测项目类型、读取 package.json、收集文件列表等。
    返回 ProjectInfo 对象。
    """
    files = list_files(root, max_files=800)
    has_file = lambda name: any(f == name or f.endswith(f"/{name}") for f in files)
    has_prefix = lambda prefix: any(f.startswith(prefix) for f in files)

    package_json_path = root / "package.json"
    package_json = read_json(package_json_path) if package_json_path.exists() else None

    # 推断技术栈
    stack = "generic"
    if package_json:
        deps = {}
        deps.update(package_json.get("dependencies", {}))
        deps.update(package_json.get("devDependencies", {}))
        if "react" in deps or has_prefix("src/renderer"):
            stack = "typescript-react"
        elif "typescript" in deps or has_file("tsconfig.json"):
            stack = "typescript"
        else:
            stack = "node"
    elif has_file("pyproject.toml") or has_file("requirements.txt"):
        stack = "python"
    elif has_file("go.mod"):
        stack = "go"
    elif has_file("Cargo.toml"):
        stack = "rust"
    elif has_file("pom.xml"):
        stack = "java-maven"
    elif has_file("build.gradle") or has_file("build.gradle.kts"):
        stack = "java-gradle"
    elif any(f.endswith(".csproj") or f.endswith(".sln") for f in files):
        stack = "dotnet"

    return ProjectInfo(
        root=root,
        stack=stack,
        package_json=package_json,
        files=files,
        package_manager=detect_package_manager(root)
    )


# ---------- 验证命令生成 ----------
def verification_commands(project: ProjectInfo,
                          explicit_package_manager: Optional[str] = None) -> List[str]:
    """根据项目信息生成验证命令列表（安装、测试、检查等）"""
    pm = explicit_package_manager or project.package_manager
    scripts = project.package_json.get("scripts", {}) if project.package_json else {}

    def run(script: str) -> str:
        if pm == "npm":
            return f"npm run {script}"
        if pm == "yarn":
            return f"yarn {script}"
        return f"{pm} run {script}"

    stack = project.stack

    # 特定栈的默认命令
    stack_commands = {
        "python": ["python -m pytest", "python -m compileall ."],
        "go": ["go test ./..."],
        "rust": ["cargo test"],
        "java-maven": ["mvn test"],
        "java-gradle": ["./gradlew test"],
        "dotnet": ["dotnet test"],
    }
    if stack in stack_commands:
        return stack_commands[stack]

    if not project.package_json:
        return ["echo \"No package manifest detected; replace this line with your project verification command.\""]

    install_cmd = {
        "npm": "npm install",
        "yarn": "yarn install",
    }.get(pm, f"{pm} install")

    candidates = []
    for script in ["check", "typecheck", "type-check", "lint", "test", "build"]:
        if script in scripts:
            if script == "test":
                candidates.append("npm test" if pm == "npm" else f"{pm} test")
            else:
                candidates.append(run(script))

    # 去重并过滤空值
    candidates = list(dict.fromkeys(c for c in candidates if c))
    return [install_cmd] + candidates


def init_script_from_commands(commands: List[str]) -> str:
    """根据命令列表生成 init.sh 脚本内容"""
    body_lines = []
    for cmd in commands:
        escaped = cmd.replace('"', '\\"')
        body_lines.append(f'echo "=== {escaped} ==="')
        body_lines.append(cmd)
    body = "\n\n".join(body_lines)

    return f"""#!/bin/bash
set -e

echo "=== Harness Initialization ==="

{body}

echo "=== Verification Complete ==="
echo ""
echo "Next steps:"
echo "1. Read feature_list.json to see current feature state"
echo "2. Pick ONE unfinished feature to work on"
echo "3. Implement only that feature"
echo "4. Re-run verification before claiming done"
"""


# ---------- Harness 评分 ----------
def load_harness_files(root: Path) -> List[FileInfo]:
    """从根目录加载所有 harness 相关文件，返回 FileInfo 列表"""
    candidates = [
        "AGENTS.md", "CLAUDE.md",
        "feature_list.json", "feature-list.json",
        "progress.md", "session-handoff.md", "init.sh"
    ]
    files = []
    for name in candidates:
        full = root / name
        if full.exists():
            files.append(FileInfo(path=name, content=read_text(full)))
    return files


def _has_file(by_path: Dict[str, str], names: List[str], message: str) -> CheckResult:
    """检查指定文件名是否在字典中"""
    return CheckResult(passed=any(n in by_path for n in names), message=message)


def _text_has(text: str, needles: List[str], message: str) -> CheckResult:
    """检查文本是否包含任一关键词（不区分大小写）"""
    lower = text.lower()
    return CheckResult(passed=any(needle.lower() in lower for needle in needles), message=message)


def _json_feature_list(text: str, message: str) -> CheckResult:
    """检查 feature_list.json 是否有效"""
    try:
        data = json.loads(text)
        features = data.get("features", [])
        valid = (
            isinstance(features, list) and
            all(isinstance(f, dict) and
                "id" in f and "name" in f and "description" in f and "status" in f
                for f in features)
        )
        return CheckResult(passed=valid, message=message)
    except Exception:
        return CheckResult(passed=False, message=message)


def score_harness(files: List[FileInfo]) -> HarnessScore:
    """对提供的 harness 文件进行五子系统评分，返回 HarnessScore 对象"""
    by_path = {f.path: f.content for f in files}
    all_text = "\n\n".join(f"{f.path}\n{f.content}" for f in files)

    agents = by_path.get("AGENTS.md") or by_path.get("CLAUDE.md") or ""
    feature_list = by_path.get("feature_list.json") or by_path.get("feature-list.json") or ""
    progress = by_path.get("progress.md") or ""
    init_sh = by_path.get("init.sh") or ""
    handoff = by_path.get("session-handoff.md") or ""

    # 定义各子系统的检查项
    subsystem_checks = {
        "instructions": [
            _has_file(by_path, ["AGENTS.md", "CLAUDE.md"], "Agent instruction file exists"),
            _text_has(agents, ["Startup Workflow", "Before writing code"], "Startup workflow documented"),
            _text_has(agents, ["Definition of Done", "done only when"], "Definition of done documented"),
            _text_has(agents, ["Verification Commands", "./init.sh", "test", "verify"], "Verification commands discoverable"),
            _text_has(agents, ["feature_list.json", "progress.md"], "State artifacts routed from instructions"),
        ],
        "state": [
            _has_file(by_path, ["feature_list.json", "feature-list.json"], "Feature tracker exists"),
            _json_feature_list(feature_list, "Feature tracker is valid and has feature fields"),
            _has_file(by_path, ["progress.md"], "Progress log exists"),
            _text_has(progress, ["Current State", "What", "Next"], "Progress log supports restart"),
            _text_has(handoff or progress, ["Blockers", "Files", "Next Session"], "Handoff captures blockers/files/next step"),
        ],
        "verification": [
            _has_file(by_path, ["init.sh"], "Verification entrypoint exists"),
            _text_has(init_sh, ["set -e"], "Verification fails fast"),
            _text_has(init_sh + agents, ["test", "pytest", "vitest", "cargo test", "go test", "dotnet test"],
                      "Test command documented"),
            _text_has(init_sh + agents, ["build", "type", "lint", "compile"], "Static/build check documented"),
            _text_has(all_text, ["Evidence", "Verification Evidence", "command and output"],
                      "Verification evidence is recorded"),
        ],
        "scope": [
            _text_has(agents, ["One feature at a time", "one-feature-at-a-time"],
                      "One-feature-at-a-time rule exists"),
            _text_has(feature_list, ["dependencies"], "Feature dependencies are tracked"),
            _text_has(agents + feature_list, ["status"], "Feature status is explicit"),
            _text_has(agents, ["Stay in scope", "scope"], "Scope boundary documented"),
            _text_has(agents, ["Definition of Done"], "Completion gate limits scope closure"),
        ],
        "lifecycle": [
            _has_file(by_path, ["init.sh"], "Startup script exists"),
            _text_has(agents, ["End of Session", "Before ending"], "End-of-session procedure exists"),
            _has_file(by_path, ["session-handoff.md"], "Session handoff template exists"),
            _text_has(progress + handoff, ["Last Updated", "Current Objective", "Recommended Next Step"],
                      "Session restart markers exist"),
            _text_has(agents + init_sh, ["restartable", "clean", "Next steps"], "Clean restart path documented"),
        ]
    }

    subsystems: Dict[str, SubsystemScore] = {}
    for name, checks in subsystem_checks.items():
        passed = sum(1 for c in checks if c.passed)
        score = max(1, round((passed / len(checks)) * 5))
        subsystems[name] = SubsystemScore(score=score, passed=passed, total=len(checks), checks=checks)

    total_score = sum(s.score for s in subsystems.values())
    overall = round((total_score / (len(SUBSYSTEMS) * 5)) * 100)
    bottleneck = min(subsystems.items(), key=lambda item: item[1].score)[0]

    return HarnessScore(overall=overall, bottleneck=bottleneck, subsystems=subsystems)


def format_score_report(score: HarnessScore, root: str = ".") -> str:
    """生成文本格式的评分报告"""
    lines = [
        f"Harness validation for {root}",
        f"Overall: {score.overall}/100",
        f"Bottleneck: {score.bottleneck}",
        ""
    ]
    for name, sub in score.subsystems.items():
        lines.append(f"{name}: {sub.score}/5 ({sub.passed}/{sub.total})")
        for check in sub.checks:
            status = "PASS" if check.passed else "FAIL"
            lines.append(f"  {status} {check.message}")
        lines.append("")
    return "\n".join(lines)


def escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    return (text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def html_report(score: HarnessScore, title: str = "Harness Assessment") -> str:
    """生成 HTML 格式的评分报告"""
    rows = []
    for name, sub in score.subsystems.items():
        checks_html = "".join(
            f'<li class="{"pass" if c.passed else "fail"}">'
            f'{"PASS" if c.passed else "FAIL"} {escape_html(c.message)}</li>'
            for c in sub.checks
        )
        rows.append(f"""
<section>
  <h2>{escape_html(name)} <span>{sub.score}/5</span></h2>
  <ul>{checks_html}</ul>
</section>""")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape_html(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #172026; background: #f7f8fa; }}
    main {{ max-width: 960px; margin: 0 auto; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; }}
    .summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 20px 0; }}
    .metric {{ background: white; border: 1px solid #d9dee5; border-radius: 8px; padding: 16px 18px; min-width: 180px; }}
    .metric strong {{ display: block; font-size: 28px; margin-top: 4px; }}
    section {{ background: white; border: 1px solid #d9dee5; border-radius: 8px; margin: 14px 0; padding: 16px 18px; }}
    h2 {{ margin: 0 0 10px; font-size: 20px; display: flex; justify-content: space-between; }}
    ul {{ margin: 0; padding-left: 20px; }}
    li {{ margin: 6px 0; }}
    .pass {{ color: #126c43; }}
    .fail {{ color: #a23020; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escape_html(title)}</h1>
      <p>Five-subsystem harness validation report.</p>
      <div class="summary">
        <div class="metric">Overall<strong>{score.overall}/100</strong></div>
        <div class="metric">Bottleneck<strong>{escape_html(score.bottleneck)}</strong></div>
      </div>
    </header>
    {''.join(rows)}
  </main>
</body>
</html>
"""