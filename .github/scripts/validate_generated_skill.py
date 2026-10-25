#!/usr/bin/env python3
"""MiniMax Code가 생성한 reconciler-drift-detector 스킬의 정적 검증.

생성 결과를 사람이 읽기 전에 기계적으로 걸러낼 수 있는 것만 본다:
  - 형식: SKILL.md 존재, frontmatter(name/description), 본문 길이
  - 계약 커버리지: 감지 단계 계약의 핵심 요소가 본문·번들 스크립트에 등장하는지(키워드 기반 — 의미 검증은 test job 몫)
  - 안전: 비밀값 리터럴, 강제 push, 스키마 파일 쓰기 같은 금지 패턴
  - 보조 스크립트: .py는 컴파일, .sh는 `bash -n`

오류가 하나라도 있으면 종료 코드 1. 경고는 보고만 한다.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

EXPECTED_NAME = "reconciler-drift-detector"
MIN_BODY_CHARS = 1500
MAX_BODY_CHARS = 60000
MAX_DESCRIPTION_CHARS = 1024

# (라벨, 하나라도 맞으면 통과하는 정규식들)
REQUIRED = [
    ("상태 assessing", [r"\bassessing\b"]),
    ("상태 no_action_needed", [r"\bno_action_needed\b"]),
    ("상태 action_required", [r"\baction_required\b"]),
    ("재확인 유예 recheckAfter", [r"\brecheckAfter\b"]),
    ("관측 버전 lastObservedVersion", [r"\blastObservedVersion\b"]),
    ("수동 트리거 요청 manualTriggerRequestedAt", [r"\bmanualTriggerRequestedAt\b"]),
    ("수동 트리거 사유 manualTriggerReason", [r"\bmanualTriggerReason\b"]),
    ("기록 필드 stateSummary", [r"\bstateSummary\b"]),
    ("기록 필드 assessment", [r"\bassessment\b"]),
    ("task 스키마 참조", [r"reconciliation-task\.schema\.json"]),
    ("task 저장 위치", [r"data/reconciliation-tasks"]),
    ("커밋 메시지 규약 detect(...)", [r"detect\("]),
    ("드라이런 RECONCILER_DRY_RUN", [r"\bRECONCILER_DRY_RUN\b"]),
    ("점유 전 최신화", [r"pull\s+--rebase", r"git\s+fetch"]),
    ("스키마 검증", [r"jsonschema", r"\bvalidat"]),
]

RECOMMENDED = [
    ("한 건만 점유(single in-flight)", [r"한\s*건", r"single[\s-]*in[\s-]*flight", r"하나만"]),
    ("compare-and-set / 재확인", [r"compare[\s-]*and[\s-]*set", r"재확인"]),
    ("스키마 수정 금지 명시", [r"스키마[^\n]{0,40}(수정|변경)[^\n]{0,20}(않|금지|말)"]),
    ("k3s MCP 도구", [r"github_app_installation_token"]),
    ("점유가 수집보다 먼저", [r"점유[^\n]{0,60}(push|푸시|커밋)[^\n]{0,60}(뒤|후|다음|성공한\s*뒤)",
                          r"버전\s*계산\s*→\s*점유\s*→\s*수집"]),
]

FORBIDDEN = [
    ("GitHub 토큰 리터럴", r"\bgh[spuor]_[A-Za-z0-9]{20,}"),
    ("MiniMax 키 리터럴", r"\bsk-(cp|api)-[A-Za-z0-9_-]{16,}"),
    ("강제 push", r"git\s+push\b[^\n]*(\s--force\b|\s-f\b|\s\+\S)"),
    ("스키마 파일 쓰기", r"(>|\btee\b|sed\s+-i[^\n]*)\s*\S*schemas/[\w.-]+\.schema\.json"),
    ("토큰 출력", r"echo\s+[\"']?\$\{?(GITHUB_TOKEN|GH_TOKEN|SOURCE_GITHUB_TOKEN)\b"),
]


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def split_frontmatter(text: str) -> tuple[dict | None, str, str | None]:
    """(frontmatter dict, body, error). frontmatter가 없거나 깨졌으면 dict는 None."""
    match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(\r?\n|\Z)", text, re.S)
    if not match:
        return None, text, "frontmatter(--- ... ---)가 파일 맨 앞에 없음"
    raw, body = match.group(1), text[match.end():]
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return None, body, "frontmatter가 매핑이 아님"
        return data, body, None
    except ImportError:
        return parse_simple_yaml(raw), body, None
    except Exception as exc:  # yaml.YAMLError
        return None, body, f"frontmatter YAML 파싱 실패: {exc}"


def parse_simple_yaml(raw: str) -> dict:
    """PyYAML이 없을 때를 위한 최소 파서: 최상위 `key: value`와 `key: >`/`|` 블록만."""
    data: dict = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
        i += 1
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if value in (">", "|", ">-", "|-"):
            block = []
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            value = (" " if value.startswith(">") else "\n").join(b for b in block if b)
        elif len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key] = value
    return data


def bundled_text(skill_dir: Path) -> str:
    parts = []
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file() and path.name != "SKILL.md" and path.stat().st_size < 2_000_000:
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def check_scripts(skill_dir: Path, report: Report) -> None:
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name == "SKILL.md":
            continue
        rel = path.relative_to(skill_dir)
        if path.suffix == ".py":
            try:
                compile(path.read_text(encoding="utf-8"), str(rel), "exec")
                report.passed.append(f"스크립트 컴파일: {rel}")
            except (SyntaxError, ValueError, UnicodeDecodeError) as exc:
                report.errors.append(f"스크립트 컴파일 실패 {rel}: {exc}")
        elif path.suffix == ".sh":
            result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            if result.returncode:
                report.errors.append(f"셸 문법 오류 {rel}: {result.stderr.strip()[-300:]}")
            else:
                report.passed.append(f"셸 문법: {rel}")
        text = path.read_text(encoding="utf-8", errors="replace") if path.stat().st_size < 2_000_000 else ""
        for label, pattern in FORBIDDEN:
            if re.search(pattern, text):
                report.errors.append(f"금지 패턴({label}) — {rel}")


def validate(skill_dir: Path) -> Report:
    report = Report()
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file() or skill_md.is_symlink():
        report.errors.append(f"{skill_md}가 없음(일반 파일이어야 함)")
        return report
    text = skill_md.read_text(encoding="utf-8")
    front, body, err = split_frontmatter(text)
    if err:
        report.errors.append(err)
    front = front or {}
    name = str(front.get("name") or "").strip()
    desc = str(front.get("description") or "").strip()
    report.meta.update(name=name, description_chars=len(desc), body_chars=len(body.strip()),
                       files=sorted(str(p.relative_to(skill_dir)) for p in skill_dir.rglob("*") if p.is_file()))
    if name != EXPECTED_NAME:
        report.errors.append(f"frontmatter name이 {EXPECTED_NAME!r}가 아님: {name!r}")
    if not desc:
        report.errors.append("frontmatter description이 비어 있음")
    elif len(desc) > MAX_DESCRIPTION_CHARS:
        report.errors.append(f"description이 {MAX_DESCRIPTION_CHARS}자 초과({len(desc)}자)")
    body_len = len(body.strip())
    if body_len < MIN_BODY_CHARS:
        report.errors.append(f"본문이 너무 짧음({body_len}자 < {MIN_BODY_CHARS})")
    elif body_len > MAX_BODY_CHARS:
        report.errors.append(f"본문이 너무 김({body_len}자 > {MAX_BODY_CHARS})")

    # 계약 커버리지는 SKILL.md와 번들 스크립트를 합쳐 본다 — 스키마 경로처럼 절차를 스크립트에 위임한 경우가 있다.
    covered = text + "\n" + bundled_text(skill_dir)
    for label, patterns in REQUIRED:
        if any(re.search(p, covered) for p in patterns):
            report.passed.append(label)
        else:
            report.errors.append(f"계약 누락: {label}")
    for label, patterns in RECOMMENDED:
        if any(re.search(p, covered, re.I) for p in patterns):
            report.passed.append(label)
        else:
            report.warnings.append(f"권장 항목 누락: {label}")
    for label, pattern in FORBIDDEN:
        if re.search(pattern, text):
            report.errors.append(f"금지 패턴({label}) — SKILL.md")
    check_scripts(skill_dir, report)
    return report


def render(report: Report) -> str:
    out = ["### 생성 스킬 검증", f"- 결과: {'✅ 통과' if report.ok else '❌ 실패'}"]
    meta = report.meta
    if meta:
        out.append(f"- name: `{meta.get('name')}` · description {meta.get('description_chars')}자 · "
                   f"본문 {meta.get('body_chars')}자 · 파일 {len(meta.get('files', []))}개")
    for title, items, mark in (("오류", report.errors, "❌"), ("경고", report.warnings, "⚠️"),
                               ("통과", report.passed, "✅")):
        if items:
            out.append(f"\n**{title}** ({len(items)})")
            out.extend(f"- {mark} {item}" for item in items)
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("skill_dir", type=Path)
    parser.add_argument("--report", type=Path, help="마크다운 보고서 경로")
    parser.add_argument("--json", type=Path, help="JSON 보고서 경로")
    args = parser.parse_args(argv)

    report = validate(args.skill_dir)
    text = render(report)
    print(text, end="")
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps({"ok": report.ok, "errors": report.errors, "warnings": report.warnings,
                                         "passed": report.passed, "meta": report.meta},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
    for err in report.errors:
        print(f"::error::{err}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
