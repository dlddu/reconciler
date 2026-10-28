#!/usr/bin/env python3
"""Claude Code `-p --output-format stream-json --verbose` 대화 기록을 읽는 작은 도구.

  summary <jsonl>                  Step summary용 마크다운 몇 줄(모델 · MCP 연결 · 도구 호출 · 결과)
  final <jsonl> --out <file>       마지막 result 이벤트의 최종 보고 텍스트를 파일로
  check <jsonl> [--mcp NAME ...]   실행이 정상 종료했는지 판정. 실패면 exit 1
                                   (사용 한도 초과 · result 이벤트 없음 · is_error · 지정 MCP 서버 미연결)
  limit <jsonl>                    사용 한도 초과로 중단됐는지 판정해 $GITHUB_OUTPUT에 limited·limit_label·
                                   resets_local·message를 쓴다(한도 초과가 아니어도 exit 0)
  notify-args <jsonl> --skill S --target T --run-url U
                                   한도 초과 PocketAide 알림의 {"title","body"} JSON을 출력

기록 형식(한 줄에 JSON 하나):
  {"type":"system","subtype":"init","model":...,"mcp_servers":[{"name":"k3s","status":"connected"}],...}
  {"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{...}}, ...]}}
  {"type":"user","message":{"content":[{"type":"tool_result","is_error":false,...}]}}
  {"type":"result","subtype":"success","is_error":false,"num_turns":12,"duration_ms":...,
   "total_cost_usd":...,"result":"최종 보고"}
  {"type":"rate_limit_event","rate_limit_info":{"status":"allowed|allowed_warning|rejected",
   "rateLimitType":"five_hour|seven_day|...","resetsAt":<epoch>,"utilization":0.85,...}}
알 수 없는 줄·필드는 건너뛴다(형식이 조금 바뀌어도 요약이 실패로 끝나지 않게).

사용 한도 초과 판정(셋 중 하나):
  1. rate_limit_event의 status가 rejected
  2. 해석 못 한 줄에 rate_limit_event와 "rejected"가 함께 있다(이벤트가 다른 줄 중간에 끼어 줄이 깨지는 경우)
  3. result가 is_error이고 본문이 한도 메시지("You've hit your session limit · resets …",
     "API Error: Rate limit reached" 등)다 — claude -p는 한도에 걸려도 exit 0 · subtype success로 끝난다
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

LIMIT_TEXT = re.compile(r"hit your (?:[\w-]+ )?limit|usage limit|rate limit|session limit|weekly limit", re.IGNORECASE)
LIMIT_LABELS = {
    "five_hour": "5시간 세션 한도",
    "seven_day": "주간 한도",
    "seven_day_opus": "주간 Opus 한도",
    "seven_day_sonnet": "주간 Sonnet 한도",
    "overage": "추가 사용량 한도",
}


@dataclass
class Transcript:
    init: dict = field(default_factory=dict)
    result: dict | None = None
    tool_calls: Counter = field(default_factory=Counter)
    tool_errors: int = 0
    skills: list = field(default_factory=list)  # Skill 도구로 불린 스킬 이름
    bad_lines: int = 0
    rate_limits: list = field(default_factory=list)  # rate_limit_event의 rate_limit_info(순서대로)
    raw_rejected: bool = False  # 깨진 줄 안에서 본 rejected rate_limit_event

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
            if "rate_limit_event" in line and re.search(r'"status"\s*:\s*"rejected"', line):
                tr.raw_rejected = True
            continue
        if not isinstance(ev, dict):
            continue
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            tr.init = ev
        elif kind == "result":
            tr.result = ev
        elif kind == "rate_limit_event":
            info = ev.get("rate_limit_info")
            if isinstance(info, dict):
                tr.rate_limits.append(info)
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


def epoch_seconds(value) -> float | None:
    """resetsAt은 초 또는 밀리초로 온다 — 초로 맞춘다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return value / 1000 if value > 1e12 else float(value)


def usage_limit(tr: Transcript) -> dict | None:
    """사용 한도 초과로 중단됐으면 {source, type, label, resets_at, message}, 아니면 None."""
    result = tr.result or {}
    text = result.get("result") if isinstance(result.get("result"), str) else ""
    message = text.strip() if result.get("is_error") else ""
    rejected = [i for i in tr.rate_limits if i.get("status") == "rejected"]
    if rejected:
        info = rejected[-1]
        kind = info.get("rateLimitType") or info.get("rate_limit_type") or ""
        return {"source": "rate_limit_event", "type": kind, "label": LIMIT_LABELS.get(kind, kind or "사용 한도"),
                "resets_at": epoch_seconds(info.get("resetsAt", info.get("resets_at"))), "message": message}
    if tr.raw_rejected:
        return {"source": "rate_limit_event(깨진 줄)", "type": "", "label": "사용 한도", "resets_at": None,
                "message": message}
    if message and LIMIT_TEXT.search(message):
        return {"source": "result", "type": "", "label": "사용 한도", "resets_at": None, "message": message}
    return None


def format_reset(ts: float | None, tz: str) -> str:
    if ts is None:
        return ""
    when = dt.datetime.fromtimestamp(ts, ZoneInfo(tz))
    return when.strftime("%m-%d %H:%M ") + (when.tzname() or tz)


def notify_payload(limit: dict, skill: str, target: str, run_url: str, tz: str) -> dict:
    reset = format_reset(limit.get("resets_at"), tz)
    lines = [f"{limit['label']}{' · 재설정 ' + reset if reset else ''}"]
    if not reset and limit.get("message"):
        lines.append(limit["message"][:200])
    if target:
        lines.append(f"대상: {target} — 점유가 남았을 수 있음(재설정 뒤 다음 실행이 이어받는다)")
    if run_url:
        lines.append(run_url)
    stage = skill.removeprefix("reconciler-")
    return {"title": f"reconciler {stage} — Claude 한도 초과로 중단"[:120], "body": "\n".join(lines)}


def problems(tr: Transcript, require_mcp: list[str]) -> list[str]:
    out = []
    limit = usage_limit(tr)
    if limit:
        out.append(f"Claude 사용 한도 초과로 중단({limit['label']}, 판정 근거 {limit['source']})")
    if tr.result is None:
        out.append("result 이벤트가 없음 — 시간 초과나 비정상 종료로 보임")
    elif limit:
        pass  # 오류 result의 원인이 한도 초과다 — 위에 적었다
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
    if tr.rate_limits:
        last = tr.rate_limits[-1]
        util = last.get("utilization")
        util_txt = f" · 사용률 {util:.0%}" if isinstance(util, (int, float)) else ""
        lines.append(f"- 사용 한도: {last.get('status', '?')} · {last.get('rateLimitType', '?')}{util_txt}")
    limit = usage_limit(tr)
    if limit:
        lines.append(f"- ⛔ 사용 한도 초과로 중단: {limit['label']} (근거 {limit['source']})")
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
    p_lim = sub.add_parser("limit")
    p_lim.add_argument("jsonl")
    p_lim.add_argument("--tz", default="Asia/Seoul")
    p_lim.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    p_not = sub.add_parser("notify-args")
    p_not.add_argument("jsonl")
    p_not.add_argument("--skill", required=True)
    p_not.add_argument("--target", default="")
    p_not.add_argument("--run-url", default="")
    p_not.add_argument("--tz", default="Asia/Seoul")
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
    if args.cmd == "limit":
        limit = usage_limit(tr)
        out = {"limited": "true" if limit else "false"}
        if limit:
            out.update(limit_label=limit["label"], limit_source=limit["source"],
                       resets_local=format_reset(limit.get("resets_at"), args.tz),
                       message=" ".join((limit.get("message") or "").split())[:200])
            print(f"사용 한도 초과: {limit['label']} · 재설정 {out['resets_local'] or '알 수 없음'} · 근거 {limit['source']}")
        else:
            print("사용 한도 초과 아님")
        if args.github_output:
            with open(args.github_output, "a", encoding="utf-8") as fh:
                for key, value in out.items():
                    fh.write(f"{key}={value}\n")
        return 0
    if args.cmd == "notify-args":
        limit = usage_limit(tr) or {"label": "사용 한도", "source": "", "resets_at": None, "message": ""}
        print(json.dumps(notify_payload(limit, args.skill, args.target, args.run_url, args.tz), ensure_ascii=False))
        return 0
    found = problems(tr, args.mcp)
    for msg in found:
        print(f"::error::{msg}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
