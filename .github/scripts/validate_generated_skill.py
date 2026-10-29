#!/usr/bin/env python3
"""MiniMax Code가 생성한 reconciler 단계 스킬의 정적 검증(`--profile`로 스킬을 고른다).

생성 결과를 사람이 읽기 전에 기계적으로 걸러낼 수 있는 것만 본다:
  - 형식: SKILL.md 존재, frontmatter(name/description), 본문 길이
  - 계약 커버리지: 그 단계 계약의 핵심 요소가 본문·번들 스크립트에 등장하는지(키워드 기반 — 실제 동작은
    결과 점검기(감지: 운영 감지의 check_detector_result.py, 실행: 빌드 테스트의 check_executor_result.py)가 본다)
  - 안전: 비밀값 리터럴, 강제 push, 스키마 파일 쓰기, 드라이런 분기 같은 금지 패턴
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

DEFAULT_PROFILE = "reconciler-drift-detector"
MIN_BODY_CHARS = 1500
MAX_BODY_CHARS = 60000
MAX_DESCRIPTION_CHARS = 1024

# (라벨, 하나라도 맞으면 통과하는 정규식들)
DETECTOR_REQUIRED = [
    ("상태 assessing", [r"\bassessing\b"]),
    ("상태 no_action_needed", [r"\bno_action_needed\b"]),
    ("상태 action_required", [r"\baction_required\b"]),
    ("재확인 유예 recheckAfter", [r"\brecheckAfter\b"]),
    ("기록 필드 stateSummary", [r"\bstateSummary\b"]),
    ("기록 필드 assessment", [r"\bassessment\b"]),
    ("task 스키마 참조", [r"reconciliation-task\.schema\.json"]),
    ("task 저장 위치", [r"data/reconciliation-tasks"]),
    ("커밋 메시지 규약 detect(...)", [r"detect\("]),
    ("push 전 최신화(pull --rebase)", [r"pull\s+--rebase"]),
    ("스키마 검증", [r"jsonschema", r"\bvalidat"]),
    ("점유된 task 입력(task_id)", [r"\btask_id\b"]),
]

DETECTOR_RECOMMENDED = [
    ("점유는 러너 몫 — 스킬은 점유·대상 선정을 하지 않음", [r"(점유|선정)[^\n]{0,80}러너", r"러너[^\n]{0,80}(점유|선정)"]),
    ("점유 기록(trigger·to-be-models) 보존", [r"\btrigger\b[^\n]{0,80}(건드리지|수정하지|바꾸지|고치지|손대지|그대로|불변)",
                                         r"to-be-models\.json[^\n]{0,80}(건드리지|수정하지|바꾸지|고치지|손대지|그대로|불변)"]),
    ("스키마 수정 금지 명시", [r"스키마[^\n]{0,40}(수정|변경)[^\n]{0,20}(않|금지|말)",
                         r"스키마[^\n]{0,40}(건드리지|고치지|손대지)\s*않",
                         r"스키마[^\n]{0,20}(고쳐|수정해|바꿔)[^\n]{0,30}않"]),
    ("k3s MCP 도구", [r"github_app_installation_token"]),
    ("잔여 gap 규칙 — 부분 해소를 no_action_needed로 닫지 않음", [r"잔여\s*gap", r"남은\s*(gap|차이)", r"현재\s*상태[^\n]{0,40}판정"]),
    ("기록 분량 기준(gap·reason)", [r"\bgap\b[^\n]{0,40}(문장|자\s*(이내|안팎|이하))", r"\breason\b[^\n]{0,40}\d+\s*자"]),
]

_NO = r"(건드리지|수정하지|바꾸지|고치지|손대지|그대로|불변|갱신하지|쓰지)"

EXECUTOR_REQUIRED = [
    ("상태 executing", [r"\bexecuting\b"]),
    ("상태 verifying", [r"\bverifying\b"]),
    ("상태 succeeded", [r"\bsucceeded\b"]),
    ("상태 failed", [r"\bfailed\b"]),
    ("기록 필드 execution·entries", [r"\bentries\b"]),
    ("기록 필드 stepSeq", [r"\bstepSeq\b"]),
    ("기록 필드 verification·checks", [r"\bchecks\b"]),
    ("실행 후 버전 asIsVersionAfter", [r"\basIsVersionAfter\b"]),
    ("시도 기록 attempts(마지막 항목)", [r"\battempts\b"]),
    ("계획 입력 plan.steps·executionGuide", [r"\bexecutionGuide\b"]),
    ("task 스키마 참조", [r"reconciliation-task\.schema\.json"]),
    ("task 저장 위치", [r"data/reconciliation-tasks"]),
    ("커밋 메시지 규약 execute(...)", [r"execute\("]),
    ("push 전 최신화(pull --rebase)", [r"pull\s+--rebase"]),
    ("스키마 검증", [r"jsonschema", r"\bvalidat"]),
    ("점유된 task 입력(task_id)", [r"\btask_id\b"]),
]

EXECUTOR_RECOMMENDED = [
    ("점유는 러너 몫 — 스킬은 점유·대상 선정을 하지 않음", [r"(점유|선정)[^\n]{0,80}러너", r"러너[^\n]{0,80}(점유|선정)"]),
    ("시작 시 executing 확인 — 아니면 멈춤", [r"executing[^\n]{0,80}(아니|확인|멈|중단|종료)"]),
    ("사람 승인 manualApproval — 머지 직전 head 재확인", [r"manualApproval[^\n]{0,200}(sha|head)", r"(sha|head)[^\n]{0,120}manualApproval"]),
    ("사람 승인 status를 만들지 않음", [r"(승인|approval)[^\n]{0,40}status[^\n]{0,60}(않|금지|말)",
                                 r"github_commit_status_create[^\n]{0,60}(않|금지|말)",
                                 r"(않|금지|말)[^\n]{0,40}github_commit_status_create"]),
    ("계획 범위 밖 변경 금지", [r"(계획|plan)[^\n]{0,30}(범위\s*)?밖", r"범위를?\s*(넓히|늘리)"]),
    ("lock 해제 — executing·verifying로 남기지 않음", [r"(executing|verifying)[^\n]{0,60}(남기지|두지|머물)",
                                                   r"\block\b[^\n]{0,40}(해제|풀|놓)"]),
    ("lastObservedVersion 보존", [r"lastObservedVersion[^\n]{0,80}" + _NO, r"to-be-models\.json[^\n]{0,80}" + _NO]),
    ("전제 붕괴 시 cancelled", [r"\bcancelled\b"]),
    ("스키마 수정 금지 명시", [r"스키마[^\n]{0,40}(수정|변경)[^\n]{0,20}(않|금지|말)",
                         r"스키마[^\n]{0,40}(건드리지|고치지|손대지)\s*않",
                         r"스키마[^\n]{0,20}(고쳐|수정해|바꿔)[^\n]{0,30}않"]),
    ("k3s MCP 도구", [r"github_app_installation_token"]),
]

# 금지 패턴을 "하지 말라"고 적은 줄(예: 「강제 push 금지(`git push --force`)」)은 사용이 아니라 금지 서술이다.
PROHIBITION = re.compile(r"금지|하지\s*않|하지\s*말|않는다|절대|쓰지\s*않|never|do\s+not|don't|must\s+not", re.I)

FORBIDDEN = [
    ("GitHub 토큰 리터럴", r"\bgh[spuor]_[A-Za-z0-9]{20,}"),
    ("MiniMax 키 리터럴", r"\bsk-(cp|api)-[A-Za-z0-9_-]{16,}"),
    ("강제 push", r"git\s+push\b[^\n]*(\s--force\b|\s-f\b|\s\+\S)"),
    # 정합성 루프에는 드라이런 모드가 없다(계획·실행은 구조적으로 드라이런이 불가능해 단계마다 다르면 헷갈린다).
    ("드라이런 분기", r"\bRECONCILER_DRY_RUN\b"),
    ("스키마 파일 쓰기", r"(>|\btee\b|sed\s+-i[^\n]*)\s*\S*schemas/[\w.-]+\.schema\.json"),
    ("토큰 출력", r"echo\s+[\"']?\$\{?(GITHUB_TOKEN|GH_TOKEN|SOURCE_GITHUB_TOKEN)\b"),
]

# 실행 단계 전용: 무인 단계는 사람 승인 status를 만들지 않는다(README 「실행 전 사람 승인」).
EXECUTOR_FORBIDDEN = [
    ("사람 승인 status 생성", r"github_commit_status_create|/statuses/[^\n]*-X\s*POST|-X\s*POST[^\n]*/statuses/"),
    ("강제 머지(관리자 우회)", r"gh\s+pr\s+merge\b[^\n]*--admin"),
]


@dataclass(frozen=True)
class Profile:
    name: str
    required: list
    recommended: list
    forbidden: list


PROFILES = {
    "reconciler-drift-detector": Profile("reconciler-drift-detector", DETECTOR_REQUIRED, DETECTOR_RECOMMENDED, FORBIDDEN),
    "reconciler-work-executor": Profile("reconciler-work-executor", EXECUTOR_REQUIRED, EXECUTOR_RECOMMENDED,
                                        FORBIDDEN + EXECUTOR_FORBIDDEN),
}


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


def check_scripts(skill_dir: Path, report: Report, forbidden: list = FORBIDDEN) -> None:
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
        for label, pattern in forbidden:
            if re.search(pattern, text):
                report.errors.append(f"금지 패턴({label}) — {rel}")


def validate(skill_dir: Path, profile: str = DEFAULT_PROFILE) -> Report:
    prof = PROFILES[profile]
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
    report.meta.update(profile=prof.name, name=name, description_chars=len(desc), body_chars=len(body.strip()),
                       files=sorted(str(p.relative_to(skill_dir)) for p in skill_dir.rglob("*") if p.is_file()))
    if name != prof.name:
        report.errors.append(f"frontmatter name이 {prof.name!r}가 아님: {name!r}")
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
    for label, patterns in prof.required:
        if any(re.search(p, covered) for p in patterns):
            report.passed.append(label)
        else:
            report.errors.append(f"계약 누락: {label}")
    for label, patterns in prof.recommended:
        if any(re.search(p, covered, re.I) for p in patterns):
            report.passed.append(label)
        else:
            report.warnings.append(f"권장 항목 누락: {label}")
    for label, pattern in prof.forbidden:
        hits = [line for line in text.splitlines() if re.search(pattern, line) and not PROHIBITION.search(line)]
        if hits:
            report.errors.append(f"금지 패턴({label}) — SKILL.md: {hits[0].strip()[:120]}")
    check_scripts(skill_dir, report, prof.forbidden)
    return report


def render(report: Report) -> str:
    out = [f"### 생성 스킬 검증{(' — ' + report.meta['profile']) if report.meta.get('profile') else ''}", f"- 결과: {'✅ 통과' if report.ok else '❌ 실패'}"]
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
    parser.add_argument("--profile", choices=sorted(PROFILES), default=DEFAULT_PROFILE,
                        help=f"검증할 스킬 계약(기본 {DEFAULT_PROFILE})")
    parser.add_argument("--report", type=Path, help="마크다운 보고서 경로")
    parser.add_argument("--json", type=Path, help="JSON 보고서 경로")
    args = parser.parse_args(argv)

    report = validate(args.skill_dir, args.profile)
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
