#!/usr/bin/env python3
"""ToBeModel 데이터 소스가 가리키는 대상 레포 이름을 쉼표로 이어 출력한다.

  target_repositories.py <reconciler checkout> [--owner dlddu] [--exclude a,b]

러너가 대상 레포 읽기 토큰(github_app_installation_token)을 받을 때 레포를 명시하는 데 쓴다 —
homelab-k3s-mcp의 제외 목록 상한(excludeRepositories)은 레포를 명시한 요청만 받는다.
`data/to-be-models.json` 안의 모든 `repository` 값(owner/name) 중 owner가 같은 것만 이름으로 모은다.
비활성 모델도 포함한다(지목 실행이 있을 수 있다). 목록이 비면 exit 1.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def collect(node, found: set[str], owner: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "repository" and isinstance(value, str) and REPO.match(value):
                repo_owner, name = value.split("/", 1)
                if repo_owner.lower() == owner.lower():
                    found.add(name.lower())
            else:
                collect(value, found, owner)
    elif isinstance(node, list):
        for item in node:
            collect(item, found, owner)


def target_repositories(repo_dir: Path, owner: str, exclude: set[str]) -> list[str]:
    models = json.loads((repo_dir / "data" / "to-be-models.json").read_text(encoding="utf-8"))
    found: set[str] = set()
    collect(models, found, owner)
    return sorted(found - exclude)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", help="reconciler checkout 경로")
    parser.add_argument("--owner", default="dlddu")
    parser.add_argument("--exclude", default="reconciler", help="쉼표 구분, 기본 reconciler")
    args = parser.parse_args(argv)
    exclude = {name.strip().lower() for name in args.exclude.split(",") if name.strip()}
    names = target_repositories(Path(args.repo), args.owner, exclude)
    if not names:
        print("대상 레포를 찾지 못함", file=sys.stderr)
        return 1
    print(",".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
