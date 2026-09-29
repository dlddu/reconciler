---
name: reconciler-work-executor
description: "reconciler 정합성 루프의 실행 단계 스킬. 검토 판단이 끝나 실행 대기(approved)가 된 ReconciliationTask 한 건을 점유해, 계획과 실행 지침대로 실제 작업을 실행하고(4-3) 결과가 계획이 명시한 범위(완료 기준)에 수렴했는지 검증한다(4-4). 실행할 대상이 없으면 아무것도 하지 않고 그대로 종료한다. 모든 단계를 task에 기록·커밋한다. 사용자가 '이제 실행해줘', 'PR 머지하고 반영해줘', 'reconcile 작업 진행', '승인된 거 실행해줘', '작업 결과 검증해줘', '수렴했는지 확인', '롤아웃 됐는지 봐줘' 같이 검토를 통과한 정합성 작업을 실제로 반영·검증하려 할 때 사용할 것. 실제 프로덕션/클러스터/레포에 변경을 가하는 단계이므로 입구는 approved 하나뿐이다 — 검토 판정 전(planned)이거나 판정 중(reviewing)인 task는 어떤 이유로도 집지 않는다. approved라도 리뷰가 사람 승인을 요구한(review.manualApproval) task는 사람이 대상 레포의 승인 status를 붙인 것이 확인될 때만 집는다."
---

# reconciler-work-executor

검토 판단을 통과한 task를 **실제로 반영하고 검증**하는 단계. 여기서 프로덕션·클러스터·대상
레포에 변경이 일어난다.

0. **대상 선정 · 진입 게이트(4-0)** → 실행 대상(`approved`)이 없으면 여기서 종료
1. **점유(claim)** → `approved → executing`
2. **실행(4-3)** → `execution`
3. **검증(4-4)** → `verification`

> **입구는 `approved` 하나뿐이다.** 그 상태는 **reconciler-work-review**가 승인 판정을 내렸을 때만
> 만들어진다. 그래서 이 스킬은 승인 여부를 다시 판단하지도, 승인을 묻지도 않는다. 이미 판정이
> 끝난 것만 집는다.
>
> **사람 승인이 걸린 `approved`는 승인이 확인된 것만 집는다.** 대상 레포가 머지에 사람 승인을 요구하면
> 리뷰는 `approved`와 함께 `review.manualApproval`(`sha`·`context`)을 남긴다. 사람이 그 status를 붙이기
> 전에는 실행 대상이 아니다.
>
> **`approved` 앞의 상태는 무엇도 집지 않는다.** `planned`/`reviewing`은 아직 검토 판단 전이거나
> 판단 중이다. 어느 것이든 여기서
> 집으면 검토 게이트를 통째로 건너뛰게 된다. 감지·계획 요약이 아무리 그럴듯해도, 러너가 조용히 돌고 있어도, 위험도가
> 낮아 보여도 예외는 없다.

> **핵심 제약 — 한 번에 하나만 점유(single in-flight).** 실행 대상(`approved`)이 여러 건이어도
> **정확히 한 건만 골라 점유(claim)한다.** 나머지는 `approved`(미점유)로 그대로 두어 다음 실행
> 또는 다른 워커의 몫으로 남긴다. 고른 한 건을 **lock을 놓는 지점**까지 끌고 간 뒤에야
> (검증 완료 → `succeeded`/`failed`, 취소 → `cancelled`) 다음 task를 고려한다. 어느 순간에도 이
> 워커가 점유 상태(`executing`/`verifying`)로 붙잡은 task는 **최대 1건**이다.

> **시도 기록은 `attempts[]`(append-only)에 있다.** planner가 만들고 review가 판단한 **마지막
> 항목**(현재 시도)을 이어받아 그 안에 `execution`·`verification`을 채운다. 이전 항목은 수정하지
> 않는다. 헬퍼 병합 규칙상 배열은 통째 교체이므로 마지막 항목만 바꾸더라도 patch는 항상
> **전체 attempts 배열**로 보낸다.

레포 접근·검증·커밋 절차와 스키마 규칙(data plane은 스키마를 수정하지 않는다)은 **reconciler-repo-access** 스킬을 따른다(그 스킬 Step 1로
레포·헬퍼를 준비하고, 헬퍼는 그 스킬이 안내하는 경로 `$TOOL`로 호출). 필드 형태는 런타임에
`schemas/reconciliation-task.schema.json`을 읽어 맞춘다.

> **checkout 경로 인자(`$ARGUMENTS`)**: 이 스킬은 인자로 이번 실행 전용 reconciler checkout
> 경로를 받는다(스케줄 러너가 fire마다 격리 디렉터리를 넘긴다 —
> `/reconciler-data-plane:reconciler-work-executor <checkout-dir>`). reconciler-repo-access는 이 인자값을
> 레포 경로(`REPO="$ARGUMENTS"`)로 바로 쓴다. `claude --bg`로 띄운 세션엔 러너가 exec 직전 export한
> env가 도달하지 않으므로(프롬프트만 데몬 경계를 넘는다) 경로는 인자로만 전달된다 — 인자를 무시하고
> 다른(프리프로비전·공유) checkout에서 작업하지 말 것. 그러면 여러 fire가 한 working tree를 공유해
> 서로의 실행을 덮어쓴다.

## Step 0 — 대상 선정 · 진입 게이트 (4-0)

reconciler-repo-access Step 1로 레포·헬퍼를 확보한 뒤(읽기 토큰), 대상 집합을 정한다.

- 사용자가 특정 task/모델을 지목했으면 그 task로 한정한다.
- 아니면 `data/reconciliation-tasks/*.json`의 task들을 훑는다.

**대상(ready)** = status가 `approved`이고, attempts 마지막 항목에 `plan.steps`·
`plan.executionGuide`·`preparation`(기록돼 있으면 준비 완료)이 갖춰졌으며, `review.manualApproval`이 **없거나**
사람 승인이 완료된 task.

`manualApproval`이 있는 task의 **사람 승인 완료** = 다음이 모두 참:
  1. `preparation.pullRequestUrl`의 PR이 열려 있고(머지·닫힘 아님) head가 `manualApproval.sha` 그대로다.
  2. `manualApproval.sha`에 붙은 `manualApproval.context`의 **최신** commit status가 `success`다
     (`GET /repos/{owner}/{repo}/commits/{sha}/statuses`에서 그 context 중 가장 최근 것).
  확인하지 못하면(API 오류 등) 승인 안 됨으로 본다(fail-closed).

확인에는 대상 레포 한정 read 토큰(`contents`·`pull_requests`·`statuses`: read)을 쓴다. `manualApproval`이
없는 `approved`는 확인 없이 대상이다.

**대상이 아님**:
- `approved`지만 사람 승인이 완료되지 않은 것:
  - **승인 대기** — PR은 그대로인데 `context`의 최신 status가 `success`가 아니다(없음 포함). 사람이 대상
    레포 절차대로 status를 붙여야 한다(사람 세션의 reconciler-manual-approval이 이 건을 설명하고 붙인다).
  - **승인 무효** — PR이 닫혔거나 머지됐거나 head가 `sha`에서 바뀌었다. 이전 승인은 이어지지 않으므로 사람이
    status를 `planned`로 되돌려 재검토를 받게 하거나, reconciler-manual-approval에서 거부해 재계획으로 넘긴다.
  - **확인 불가** — API 오류 등. 승인 안 됨으로 본다.
- `planned`/`reviewing` — 아직 검토 판단 전 또는 판단 중. **reconciler-work-review**의 몫이다.
- `action_required`/`planning` — 계획 전 또는 계획 중(planner).
- `assessing`/`no_action_needed` — 감지 단계 몫.
- `executing`/`verifying` — 이미 어떤 워커가 점유해 진행 중. Step 0에서 새로 집지 않는다.
  같은 대화에서 이 워커가 점유한 task는 Step 2~3 흐름을 그대로 이어갈 뿐, 이 게이트로 되돌아와
  다시 고르는 대상이 아니다.
- `review_rejected`/`failed` — 재작업 진입점(planner).
- `cancelled`/`succeeded` — 종료됨.

분기:
- **ready가 1건 이상** → **딱 한 건만 고른다.** 사용자가 지목했으면 그 task를, 아니면 우선순위로
  하나를 정한다(승인이 오래 묵을수록 전제가 흔들리므로 `review.reviewedAt`이 오래된 순). 여러 건이면 어느 것을 고르는지 — 그리고 **나머지는 이번에 점유하지 않고
  `approved`로 남긴다**는 것을 — 한 줄로 알린 뒤, 그 한 건만 들고 Step 1로 진행한다.
- **ready가 0건** → **여기서 종료한다.** 이번에 반영할 것이 없다는 뜻이다.
  - 관련 task들의 현재 status와 **왜 대상이 아닌지**를 사유별로 한 줄씩 간결히 보고한다
    (예: "feature-doc: 검토 판정 전 — 리뷰 몫", "dear-baby: 검토 거부 — 재계획 대기").
  - **판정 대기(`planned`) 건이 있으면 몇 건인지, 그건
    reconciler-work-review가 판정한다는 것을 한 줄로 알린다.**
  - **승인 대기·승인 무효 건이 있으면 task마다 한 줄로 알린다** — 승인 대기는 PR 링크와 붙여야 할
    `context`, 승인 무효는 재검토가 필요하다는 것.
  - **판단·계획·승인을 여기서 시작하지 않는다.** 다른 reconciler-* 스킬로 갈아타지 않고,
    사용자에게 계속하라고 종용하거나 스킬 선택 메뉴를 들이밀지 않는다. 필요한 단계가 있으면
    어느 스킬의 몫인지만 한 줄로 알리고 턴을 끝낸다.

이 게이트의 **대상 선정까지는 읽기 전용**이다.

## Step 1 — 점유(claim)

Step 0에서 고른 **그 한 건만** 점유한다. `git pull --rebase` 후 status가 아직 `approved`인지
재확인하고(아니면 다른 워커가 먼저 집은 것 → 물러나 다른 대상을 고르거나 상태만 보고한다),
`manualApproval`이 있으면 **사람 승인 완료를 다시 확인한다**(Step 0 이후 PR에 새 커밋이 올라와 승인이
무효가 됐을 수 있다). 완료가 아니면 점유하지 않고 물러난다. 맞으면 `approved → executing`으로 원자적으로 전이해 **곧바로 push**한다. 이 push가 lock이며,
성공해야만 실제 작업을 시작한다. 커밋: `execute(<tbm>/<rct>): claim`.

승인 기록(`review`)은 **읽기만 한다.** 판단을 다시 하거나 뒤집지 않는다. **사람 승인을 스스로 만들지
않는다** — `manualApproval.context`에 status를 쓰는 일(`github_commit_status_create` 포함)은 이 스킬도,
루프의 어떤 무인 단계도 하지 않는다.

`manualApproval`이 있으면 **머지 직전에도** PR head가 `manualApproval.sha` 그대로인지 확인한다. 달라졌으면
승인받지 않은 코드를 머지하게 되므로 실행하지 않고 `failed`로 남긴다(근거: 승인 후 head 변경).

## Step 2 — 실행 (4-3)

**실행은 반드시 `executing` 상태에서 시작한다.** `plan.steps`를 `plan.executionGuide`의
순서·주의사항대로 실행하고, 결과를 `execution`에 남긴다.

- 준비 단계에서 PR을 만들었으면, 그 PR을 머지하고(대상 레포용 write 토큰 발급)
  GitOps/파이프라인이 적용하도록 하거나, 계획에 따라 직접 적용한다.
- 직접 액션(예: `flux reconcile`, 재시작, kubectl)이면 k3s 도구/CLI로 실행한다.
- `execution`: `status:"running"`으로 시작 → 각 step을 `entries[]`에 `stepSeq`·`status`
  (`succeeded`/`failed`/`skipped`)·`startedAt`/`finishedAt`·`log`(stdout/stderr 요약 또는 링크)로
  기록. 한 step이 실패하면 뒤 step은 보통 중단하고 실패를 그대로 남긴다(임의 우회 금지).
  전체 종료 시 `execution.status`(`succeeded`/`failed`/`aborted`)와 `finishedAt` 확정.

**승인 시점의 계획대로만 한다.** 실행 도중 계획 밖의 변경이 필요해지면 임의로 넓히지 말고
중단해 `failed`로 남긴다 — 범위를 늘리는 순간 그 부분은 검토·승인을 받지 않은 변경이 된다.
재계획은 planner의 몫이다.

전제가 이미 무너져 있으면(PR이 닫혔거나 이미 머지됨, 대상이 사라짐) 억지로 진행하지 말고 그
사실을 근거로 남기고 멈춘다 — 해소된 것이면 `cancelled`, 실행하려다 실패한 것이면 `failed`.

시크릿·토큰은 절대 로그에 남기지 않는다. 커밋: `execute(<tbm>/<rct>): run`.

## Step 3 — 검증 (4-4)

실행이 **이 시도의 계획 범위(plan이 명시한 완료 기준)** 를 실제로 달성했는지 확인한다.
task의 완료 기준은 모델 전체 to-be가 아니라 **plan의 범위**다 — planner가 gap의 일부만
슬라이스로 계획했다면, 그 슬라이스의 달성·검증이 곧 이 task의 성공이다. status `verifying`.
`verification`에 기록:

- 모델의 `asIs.versionScript`를 다시 실행해 `asIsVersionAfter`를 계산한다(기록용).
- `plan.executionGuide`의 검증 방법을 `checks[]`로 실행:
  각 `name`·`status`(`passed`/`failed`)·`detail`(관측값).
- 판정은 **plan이 명시한 범위(완료 기준) 기준**이다. 모델 전체 to-be와의 잔여 gap은 판정에 넣지
  않는다 — 그건 이 task의 범위 밖이며, 아래 재감지 루프가 이어받는다. 잔여 gap이 관측되면 checks의
  detail(정보성)로 사실만 남긴다. 범위 수렴 여부를 따로 적는 필드는 없다 — `status`가 곧 그 판정이다.
- 전부 통과+범위 달성 → `verification.status:"passed"`, task status `succeeded`.
  하나라도 실패(계획한 범위조차 미달성) → `verification.status:"failed"`, task status
  `failed`(근거를 checks/detail에). `failed`는 planner의 재작업 진입점이 되어 **같은 범위**를
  재계획·재시도한다.
- `verifiedAt` 기록.
- **모델의 `lastObservedVersion`은 건드리지 않는다.** 실행이 만든 as-is/to-be 버전 변화는
  다음 감지 주기의 트리거가 되어야 한다 — 잔여 gap이 있으면 detector가 그 변화를 보고 후속
  task를 열고(`action_required`), gap이 다 닫혔으면 `no_action_needed`로 확정한다.
  슬라이스 완료 → 재감지 → 후속 task가 이 루프의 정상 진행 방식이다.

커밋: `execute(<tbm>/<rct>): verify`.

## 산출물 / 핸드오프

- `execution`·`verification`이 채워지고 커밋돼 있어야 한다. 최종 status: `succeeded`(계획 범위
  수렴) / `failed`(범위 미달성·재작업 필요) / `cancelled`.
- 실패 시 원인 근거를 남기고, 재계획이 필요하면 그 판단·재작업은 reconciler-work-planner의
  몫이다(이 스킬이 스스로 재계획으로 넘어가지 않는다). 성공했지만 모델 전체 gap이 남아 있으면
  그 후속은 **재감지가 잇는다** — 후속 task를 직접 만들지 않고, 잔여 gap과 "다음 감지 주기가
  후속 task를 연다"는 사실만 알린다.
- **점유한 그 한 건만** 처리한다. 그 건이 lock을 놓는 지점에 도달하면 남은 `approved` task가
  있어도 **동시에 점유하지 않는다.** 남은 건은 그대로 두고 사용자에게 몇 건이 남았는지 알린다.
  이어서 처리하려면 **한 건씩 새로 점유**해 같은 절차를 반복하되, 어느 순간에도 점유 중인
  task가 둘 이상이 되지 않게 한다.
- **대상이 없었던 경우(Step 0 종료)**: 아무것도 반영하지 않았고 커밋도 없다. 관련 task의
  상태와 사유(승인 대기 건수 포함)를 알린 채로 **그대로 종료**한다.
- 사용자에게 결과를 간결히 알린다: 수렴 여부·핵심 check·남은 이슈, 또는 할 게 없었으면 각
  task가 걸린 지점. 이 보고 역시 모든 도구 작업·커밋이 끝난 뒤 **턴의 마지막**에 연속된
  블록으로 둔다 — 로그 사이에 끼워 넣지 않는다.

각 하위 단계를 개별 커밋으로 남겨, 실행 이력이 그대로 감사 로그가 되게 한다.
