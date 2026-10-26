#!/usr/bin/env python3
"""아티팩트로 올리기 전에 디렉터리 안 텍스트 파일의 비밀값을 가린다.

에이전트는 MCP `github_app_installation_token` 결과로 받은 토큰을 셸 명령에 옮겨 적을 수밖에 없어서,
대화 기록(stream-json)·진단 파일에 토큰이 그대로 남는다. 업로드 직전에 알려진 모양의 비밀값을
`<redacted:종류>`로 바꾼다. 파일은 제자리에서 고친다.

  redact_secrets.py <dir> [--extra-env NAME ...]

--extra-env로 준 환경 변수 값(예: 러너가 받은 SOURCE_GITHUB_TOKEN)도 문자 그대로 가린다.
가린 건수를 파일별로 출력한다(값은 출력하지 않는다).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

PATTERNS = [
    ("github-token", re.compile(r"\bgh[spuor]_[A-Za-z0-9_]{20,}")),
    ("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("minimax-key", re.compile(r"\bsk-(?:cp|api)-[A-Za-z0-9_\-]{16,}")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("glm-key", re.compile(r"\b[0-9a-f]{32}\.[A-Za-z0-9]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("basic-auth", re.compile(r"(?i)(authorization:\s*basic\s+)[A-Za-z0-9+/=]{16,}")),
    ("url-credential", re.compile(r"(https?://[^/\s:@]+:)[^@\s/]{8,}(@)")),
]
MAX_BYTES = 200 * 1024 * 1024


def redact_text(text: str, literals: list[str]) -> tuple[str, int]:
    count = 0
    for value in literals:
        if value and value in text:
            count += text.count(value)
            text = text.replace(value, "<redacted:env>")
    for label, pattern in PATTERNS:
        if label in ("basic-auth", "url-credential"):
            text, n = pattern.subn(lambda m: f"{m.group(1)}<redacted:{label}>" + (m.group(2) if label == "url-credential" else ""), text)
        else:
            text, n = pattern.subn(f"<redacted:{label}>", text)
        count += n
    return text, count


def redact_dir(root: Path, literals: list[str]) -> dict[str, int]:
    hits: dict[str, int] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()):
        if path.stat().st_size > MAX_BYTES:
            continue
        raw = path.read_bytes()
        if b"\0" in raw[:8192]:
            continue  # 바이너리
        text = raw.decode("utf-8", errors="surrogateescape")
        new, n = redact_text(text, literals)
        if n:
            path.write_bytes(new.encode("utf-8", errors="surrogateescape"))
            hits[str(path.relative_to(root))] = n
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--extra-env", action="append", default=[])
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print(f"redact: {args.root} 없음 — 건너뜀")
        return 0
    literals = [os.environ.get(name, "") for name in args.extra_env]
    literals = [v for v in literals if len(v) >= 8]
    hits = redact_dir(args.root, literals)
    if not hits:
        print("redact: 가릴 비밀값 없음")
    for rel, n in hits.items():
        print(f"redact: {rel} — {n}건 가림")
    return 0


if __name__ == "__main__":
    sys.exit(main())
