#!/usr/bin/env python3
"""워크플로가 모델 키를 제공자별 environment 안에서만 쓰는지 정적으로 검사한다.

  check_llm_key_scope.py [workflows_dir ...]   (기본 .github/workflows)

규칙(README 「모델 키 격리」):
  1. 모델 키(PROVIDERS의 secret 이름)는 그 제공자의 environment(`llm-<제공자>`)를 선언한 job 안에서만
     참조한다. 그래서 한 job이 두 제공자의 키를 함께 받을 수 없다.
  2. 워크플로 최상위 env:에서 모델 키를 참조하지 않는다(모든 job에 퍼진다).
  3. 모든 secret을 한꺼번에 넘기는 형태를 쓰지 않는다 — `secrets: inherit`, `toJSON(secrets)`,
     `secrets[...]` 같은 동적 참조.
  4. 모델 키는 environment secret으로만 둔다는 전제다. 같은 이름의 레포 secret이 남아 있으면 environment
     없는 job도 그 값을 받을 수 있으니, 이 검사와 별개로 레포 secret에서 지운다.

새 제공자를 붙일 때는 PROVIDERS에 environment 이름과 secret 이름을 추가한다. 위반을 출력하고 하나라도 있으면
exit 1.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - 러너에는 PyYAML이 있다
    print("check_llm_key_scope: PyYAML이 필요하다(pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

# environment 이름 → 그 environment에만 두는 모델 키 secret 이름들
PROVIDERS: dict[str, tuple[str, ...]] = {
    "llm-minimax": ("MINIMAX_SUBSCRIPTION_KEY",),
    "llm-glm": ("GLM_API_KEY", "ZHIPUAI_API_KEY"),
    "llm-claude": ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"),
}

SECRET_REF = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)")
WHOLE_SECRETS = re.compile(r"toJSON\(\s*secrets\s*\)|\bsecrets\s*\[", re.IGNORECASE)


def owner_of(secret: str) -> str | None:
    for env, names in PROVIDERS.items():
        if secret in names:
            return env
    return None


def walk_strings(node, path: str):
    """노드 안의 모든 문자열(키 포함)을 (경로, 값)으로 낸다."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                yield f"{path}.{key}", key
            yield from walk_strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk_strings(value, f"{path}[{i}]")


def environment_name(job: dict) -> str | None:
    env = job.get("environment")
    if isinstance(env, str):
        return env
    if isinstance(env, dict) and isinstance(env.get("name"), str):
        return env["name"]
    return None


def check_workflow(path: Path) -> list[str]:
    rel = path.as_posix()
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{rel}: YAML 파싱 실패 — {exc}"]
    if not isinstance(doc, dict):
        return []

    problems: list[str] = []

    for where, text in walk_strings(doc, ""):
        if WHOLE_SECRETS.search(text):
            problems.append(f"{rel}{where}: secret 전체를 넘기는 참조는 쓰지 않는다(모델 키가 함께 넘어간다)")

    for where, text in walk_strings(doc.get("env") or {}, ".env"):
        for name in SECRET_REF.findall(text):
            if owner_of(name):
                problems.append(f"{rel}{where}: 모델 키 {name}을 워크플로 최상위 env에서 참조한다 — "
                                f"{owner_of(name)} environment를 선언한 job 안으로 옮긴다")

    jobs = doc.get("jobs") or {}
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        if job.get("secrets") == "inherit":
            problems.append(f"{rel}.jobs.{job_id}: `secrets: inherit`는 모든 secret을 넘긴다 — 필요한 것만 명시한다")
        declared = environment_name(job)
        for where, text in walk_strings(job, f".jobs.{job_id}"):
            for name in SECRET_REF.findall(text):
                owner = owner_of(name)
                if owner and owner != declared:
                    got = f"environment {declared!r}" if declared else "environment 없음"
                    problems.append(f"{rel}{where}: 모델 키 {name}은 environment {owner!r} job에서만 쓴다({got})")
    return problems


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or [Path(".github/workflows")]
    files = sorted(p for d in dirs for p in list(d.glob("*.yml")) + list(d.glob("*.yaml")))
    problems = [p for f in files for p in check_workflow(f)]
    for p in problems:
        print(f"::error::{p}")
    print(f"check_llm_key_scope: 워크플로 {len(files)}개, 위반 {len(problems)}건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
