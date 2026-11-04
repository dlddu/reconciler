#!/usr/bin/env bash
# mcode exec를 한 번 돌리고, 재시도 가능한 오류로 끝나면 같은 세션을 이어서 한 번 더 돌린다.
# (reconciler-work-planner.yml의 Run skill과 같은 규칙 — 실행 단계 운영·리허설이 같이 쓴다.)
#
#   run_mcode.sh <prompt> <resume-prompt> <out-dir> <cwd> [budget-seconds]
#
#   - 1차: <prompt>. 마지막 exec.completed의 error.retryable이 참이고 세션 id가 있으면, 2차는 --session <id>로
#     <resume-prompt>를 준다(끊긴 지점의 도구 호출이 끝났는지 모르므로 현재 상태부터 다시 확인하게 하는 프롬프트).
#   - 1·2차 합계가 budget(기본 4200초 = 70분)을 넘지 않게 2차 --timeout을 남은 예산으로 준다. 남은 예산이 300초
#     미만이면 재시도하지 않는다.
#   - 대화 기록: <out-dir>/transcript.jsonl(마지막 시도), 1차는 transcript-attempt1.jsonl로 옮긴다.
#   - 환경: MODEL(선택, --model), MCODE_UNSET(공백 구분 — mcode 환경에서 뺄 변수).
#   - GITHUB_OUTPUT이 있으면 exit_code·attempts를 쓴다. 종료 코드는 항상 0(결과 점검이 판정한다).
set -uo pipefail

prompt=$1 resume=$2 out=$3 cwd=$4 budget=${5:-4200}
min_resume=300
mkdir -p "$out"
base_args=(exec --input - --cwd "$cwd" --permission full --output-format stream-json
           --output-last-message "$out/final-message.md" --diagnostics-dir "$out/diagnostics")
[ -n "${MODEL:-}" ] && base_args+=(--model "$MODEL")
unset_args=()
for v in ${MCODE_UNSET:-}; do unset_args+=(-u "$v"); done

remain=$budget
current=$prompt
session_args=()
code=0
for attempt in 1 2; do
  started=$(date +%s)
  env "${unset_args[@]}" mcode "${base_args[@]}" --timeout "${remain}s" "${session_args[@]}" \
    < "$current" > "$out/transcript.jsonl" 2> "$out/stderr.log"
  code=$?
  remain=$(( remain - ($(date +%s) - started) ))
  tail -n 5 "$out/stderr.log" || true
  [ "$code" -eq 0 ] && break
  [ "$attempt" -eq 1 ] || break
  read -r verdict session_id < <(python3 - "$out/transcript.jsonl" <<'PY' 2>/dev/null || echo "unknown -"
import json, sys
rows = []
for line in open(sys.argv[1], encoding="utf-8"):
    try:
        rows.append(json.loads(line))
    except ValueError:
        pass
done = [r.get("result") or {} for r in rows if r.get("type") == "exec.completed"]
sid = (done[-1].get("sessionId") if done else None) or next((r["sessionId"] for r in reversed(rows) if r.get("sessionId")), None)
if not (done and (done[-1].get("error") or {}).get("retryable")):
    print("not-retryable", sid or "-")
elif not sid:
    print("no-session -")
else:
    print("retryable", sid)
PY
  )
  if [ "$verdict" != retryable ]; then
    echo "재시도 안 함 — 판정: $verdict"; break
  fi
  if [ "$remain" -lt "$min_resume" ]; then
    echo "재시도 안 함 — 남은 mcode 예산 ${remain}s(< ${min_resume}s)"; break
  fi
  echo "::warning::mcode가 재시도 가능한 오류로 끝남 — 세션 $session_id 를 이어서 한 번 다시 돌린다(남은 예산 ${remain}s)"
  mv "$out/transcript.jsonl" "$out/transcript-attempt1.jsonl"
  mv "$out/stderr.log" "$out/stderr-attempt1.log"
  [ -d "$out/diagnostics" ] && mv "$out/diagnostics" "$out/diagnostics-attempt1"
  current=$resume
  session_args=(--session "$session_id")
done
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  { echo "exit_code=$code"; echo "attempts=$attempt"; } >> "$GITHUB_OUTPUT"
fi
[ "$code" -eq 0 ] || echo "::warning::mcode가 exit $code로 끝남 — 결과 점검은 계속한다"
exit 0
