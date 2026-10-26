#!/usr/bin/env python3
"""Claude Code `-p --output-format stream-json --verbose` 대화 기록을 읽는 작은 도구.

  summary <jsonl>                  Step summary용 마크다운 몇 줄(모델 · MCP 연결 · 도구 호출 · 결과)
  final <jsonl> --out <file>       마지막 result 이벤트의 최종 보고 텍스트를 파일로
  check <jsonl> [--mcp NAME ...]   실행이 정상 종료했는지 판정. 실패면 exit 1
                                   (result 이벤트 없음 · is_error · 지정 MCP 서버 미연결)

기록 형식(한 줄에 JSON 하나):
  {"type":"system","subtype":"init","model":...,"mcp_servers":[{"name":"k3s","status":"connected"}],...}
  {"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{...}}, ...]}}
  {"type":"user","message":{"content":[{"type":"tool_result","is_error":false,...}]}}
  {"type":"result","subtype":"success","is_error":false,"num_turns":12,"duration_ms":...,
   "total_cost_usd":...,"result":"최종 보고"}
알 수 없는 줄·필드는 건너뛴다(형식이 조금 바뀌어도 요약이 실패로 끝나지 않게).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Transcript:
    init: dict = field(default_factory=dict)
    result: dict | None = None
    tool_calls: Counter = field(default_factory=Counter)
    tool_errors: int = 0
    skills: list = field(default_factory=list)  # Skill 도구로 불린 스킬 이름
    bad_lines: int = 0

    @property
    def mcp_status(self) -> dict:
        return {s.get("name"): s.get("status") for s in self.init.get("mcp_servers") or [] if isinstance(s, dict)}


def load(path: str | Path) -> Transcript:
    tr = Transcript()
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return tr
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            tr.bad_lines += 1
            continue
        if not isinstance(ev, dict):
            continue
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            tr.init = ev
        elif kind == "result":
            tr.result = ev
        elif kind in ("assistant", "user"):
            content = (ev.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    name = block.get("name") or "?"
                    tr.tool_calls[name] += 1
                    if name == "Skill":
                        skill = (block.get("input") or {}).get("skill") or (block.get("input") or {}).get("command")
                        if skill:
                            tr.skills.append(str(skill))
                elif block.get("type") == "tool_result" and block.get("is_error"):
                    tr.tool_errors += 1
    return tr


def problems(tr: Transcript, require_mcp: list[str]) -> list[str]:
    out = []
    if tr.result is None:
        out.append("result 이벤트가 없음 — 시간 초과나 비정상 종료로 보임")
    elif tr.result.get("is_error") or tr.result.get("subtype") != "success":
        out.append(f"실행 결과가 오류: subtype={tr.result.get('subtype')}")
    status = tr.mcp_status
    for name in require_mcp:
        if status.get(name) != "connected":
            out.append(f"MCP 서버 {name}가 연결되지 않음(status={status.get(name, '없음')})")
    return out


def summary(tr: Transcript) -> str:
    lines = []
    if tr.init:
        mcp = ", ".join(f"{k}={v}" for k, v in tr.mcp_status.items()) or "없음"
        lines.append(f"- claude: model `{tr.init.get('model', '?')}` · MCP {mcp}")
        errors = tr.init.get("mcp_server_errors")
        if errors:
            lines.append(f"- MCP 설정 오류: {json.dumps(errors, ensure_ascii=False)[:500]}")
    else:
        lines.append("- claude: init 이벤트 없음(실행 전에 끝났을 수 있음)")
    if tr.tool_calls:
        top = ", ".join(f"{name}×{n}" for name, n in tr.tool_calls.most_common(12))
        lines.append(f"- 도구 호출 {sum(tr.tool_calls.values())}회(오류 결과 {tr.tool_errors}): {top}")
    if tr.skills:
        lines.append(f"- Skill 호출: {', '.join(dict.fromkeys(tr.skills))}")
    r = tr.result
    if r is not None:
        cost = r.get("total_cost_usd")
        cost_txt = f" · ${cost:.2f}" if isinstance(cost, (int, float)) else ""
        dur = r.get("duration_ms")
        dur_txt = f" · {dur / 60000:.1f}분" if isinstance(dur, (int, float)) else ""
        lines.append(f"- 결과: {r.get('subtype')}{' (is_error)' if r.get('is_error') else ''}"
                     f" · {r.get('num_turns', '?')}턴{dur_txt}{cost_txt}")
    else:
        lines.append("- 결과: result 이벤트 없음")
    if tr.bad_lines:
        lines.append(f"- 해석 못 한 줄 {tr.bad_lines}개")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_sum = sub.add_parser("summary")
    p_sum.add_argument("jsonl")
    p_fin = sub.add_parser("final")
    p_fin.add_argument("jsonl")
    p_fin.add_argument("--out", required=True)
    p_chk = sub.add_parser("check")
    p_chk.add_argument("jsonl")
    p_chk.add_argument("--mcp", action="append", default=[], help="연결돼 있어야 하는 MCP 서버 이름")
    args = parser.parse_args(argv)

    tr = load(args.jsonl)
    if args.cmd == "summary":
        print(summary(tr))
        return 0
    if args.cmd == "final":
        text = (tr.result or {}).get("result") or ""
        Path(args.out).write_text(text if isinstance(text, str) else json.dumps(text, ensure_ascii=False),
                                  encoding="utf-8")
        return 0
    found = problems(tr, args.mcp)
    for msg in found:
        print(f"::error::{msg}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
