#!/usr/bin/env python3
"""mcode `exec --output-format stream-json` 대화 기록에서 도구 호출을 뽑는다.

  summary <transcript.jsonl>               도구 이름별 호출 수와 실행 결과 상태(마크다운)
  require-tool <transcript.jsonl> <substr> 이름에 <substr>가 들어간 도구 호출이 있으면 0, 없으면 1

문장 응답만으로는 도구가 실제로 돌았다는 증거가 아니므로, MCP 배선 확인은 tool_call 항목으로 한다.
"""

from __future__ import annotations

import collections
import json
import sys


def events(path: str):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def tool_name(call: dict) -> str:
    for key in ("name", "toolName", "tool", "title"):
        value = call.get(key)
        if isinstance(value, str) and value:
            return value
    return "<unknown>"


def tool_calls(path: str) -> dict[str, dict]:
    calls: dict[str, dict] = {}
    for ev in events(path):
        item = ev.get("item") or {}
        if item.get("type") == "tool_call" and isinstance(item.get("toolCall"), dict):
            calls[item.get("id") or str(len(calls))] = item["toolCall"]
    return calls


def result(path: str) -> dict:
    final = {}
    for ev in events(path):
        if ev.get("type") == "exec.completed":
            final = ev.get("result") or {}
    return final


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("summary", "require-tool"):
        print(__doc__)
        return 2
    calls = tool_calls(argv[1])
    if argv[0] == "require-tool":
        needle = argv[2] if len(argv) > 2 else ""
        hits = [tool_name(c) for c in calls.values() if needle in tool_name(c)]
        print(f"tool calls matching {needle!r}: {hits or 'none'}")
        return 0 if hits else 1
    res = result(argv[1])
    counts = collections.Counter(tool_name(c) for c in calls.values())
    print(f"- mcode 결과: `{res.get('status', 'unknown')}`"
          + (f" — {res['error'].get('message')}" if isinstance(res.get("error"), dict) else ""))
    model = res.get("model") or {}
    if model:
        print(f"- 모델: `{model.get('providerId')}/{model.get('modelId')}`")
    print(f"- 도구 호출 {sum(counts.values())}회: " + (", ".join(f"`{n}`×{c}" for n, c in counts.most_common())
                                                    or "없음"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
