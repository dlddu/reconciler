---
name: reconciler-work-review
description: "reconciler 정합성 루프의 검토 판단 단계 스킬(무인). 계획·준비가 끝난 ReconciliationTask(planned) 한 건을 reviewing으로 점유한 뒤, 계획이 gap을 실제로 좁히는지·준비된 PR이 유효한지·위험이 통제되는지(위험도·영향 범위·불가역성·롤백 가능성)를 근거로 **승인 또는 거부를 직접 판정**하고(4-1) 그 결과를 task에 기록·커밋한다. 승인이면 approved(실행 대기)로 넘겨 reconciler-work-executor가 반영하게 하고, 대상 레포가 PR 머지에 사람 승인용 required status를 요구하는데 그 status가 PR head에 아직 없으면 approved로 넘기면서 review.manualApproval(sha·context)을 남겨 사람이 그 status를 붙인 뒤에만 실행되게 한다(4-2). 거부면 구체적 사유와 함께 review_rejected로 두어 reconciler-work-planner 재계획으로 넘긴다. 사람 승인 대기 상태로 보내지 않는다 — 사람 승인이 필요하면 review.manualApproval로만 남긴다. 판단할 대상이 없으면 아무것도 하지 않고 그대로 종료한다. 사용자가 '승인 대기 뭐 있어', '이 작업 승인해도 되나', '위험도 판단해줘', '정합성 작업 리뷰해줘', 'planned 것들 판정해줘', '자동으로 나가도 되는 건지 봐줘' 같이 준비된 정합성 작업의 승인/거부를 가리려 할 때 사용할 것. 이 스킬은 실행하지 않는다 — 실제 반영·검증은 reconciler-work-executor의 몫이다."
---

# reconciler-work-review

계획·준비가 끝난 task를 받아 **승인할지 거부할지를 직접 판정**하는 단계. 실행 직전의 갈림길이고,
여기서 하는 일은 판정과 기록뿐이다. 사람에게 넘기지 않는다 — 이 스킬의 판정이 곧 최종 검토다.

0. **대상 선정 · 진입 게이트(4-0)** → 판단 대상(`planned`)이 없으면 여기서 종료
1. **점유(claim)** → `planned → reviewing`을 먼저 커밋·푸시
2. **전제 신선도 확인** → 준비된 PR·직접 액션이 아직 유효한지
3. **승인/거부 판정(4-1)** → `approved` 또는 `review_rejected`로 전이해 lock 해제
   - **사람 승인 요구(4-2)** → 대상 레포의 사람 승인 status가 PR head에 없으면 `approved` + `review.manualApproval`

```
planned ──> reviewing ─┬─ 승인 ──> approved         (reconciler-work-executor가 이어받음)
                       ├─ 승인 + 사람 승인 요구 ──> approved + review.manualApproval
                       │                           (사람이 status를 붙인 뒤에야 executor가 집음)
                       ├─ 거부 ──> review_rejected  (reconciler-work-planner가 재계획)
                       └─ 반복 거부 한도 초과 ──> cancelled
```

> **핵심 제약 — 한 번에 하나만 점유(single in-flight).** 판단 대상(`planned`)이 여러 건이어도
> **정확히 한 건만 골라 점유(claim)한다.** 나머지는 `planned`(미점유)로 그대로 두어 다음 실행
> 또는 다른 워커의 몫으로 남긴다. 고른 한 건이 `approved`/`review_rejected`/`cancelled`에 도달해
> **lock을 놓은 뒤에야** 다음 task를 고려한다. 어느 순간에도 이 워커가 `reviewing`으로 붙잡은
> task는 **최대 1건**이다.

> **이 스킬은 실행하지 않는다.** PR 머지, 배포, `flux reconcile`, kubectl — 실제 반영은 하나도
> 하지 않는다. 실행·검증은 `approved`를 입구로 삼는 **reconciler-work-executor**의 몫이다.
> 승인을 기록했다고 이어서 반영하지 않는다.

> **사람에게 묻지 않고, 사람에게 넘기지도 않는다.** 스케줄 러너가 `claude --bg`로 띄우는 무인
> 세션이 기본 실행 환경이라 그 자리에 답할 사람이 없다. 그래서 판정을 미루는 선택지
> 없이 **승인 또는 거부 중 하나로 결론을 낸다.** 사람 승인 요구(4-2)는 판정을 미루는 것이 아니다 —
> 이 스킬은 승인으로 결론을 내고, 대상 레포가 머지에 요구하는 사람 승인이 붙을 때까지 **실행**이
> 기다리는 것이다. 기다림은 executor가 승인 완료를 확인하는 것으로 처리된다. 확신이 서지 않으면 승인하지 않는다 — 불확실성
> 자체가 거부 사유이며, 무엇이 불확실한지를 사유로 남겨 planner가 보완하게 한다. 버튼·선택
> 위젯(ask_user_input 류)을 호출하지 않는다.

> **시도 기록은 `attempts[]`(append-only)에 있다.** planner가 만든 **마지막 항목**(현재 시도)에
> `review`를 채운다. 이전 항목은 수정하지 않는다. 헬퍼 병합 규칙상 배열은 통째 교체이므로 마지막
> 항목만 바꾸더라도 patch는 항상 **전체 attempts 배열**로 보낸다.

레포 접근·검증·커밋 절차와 스키마 규칙(data plane은 스키마를 수정하지 않는다)은 **reconciler-repo-access** 스킬을 따른다(그 스킬 Step 1로
레포·헬퍼를 준비하고, 헬퍼는 그 스킬이 안내하는 경로 `$TOOL`로 호출). 필드 형태는 런타임에
`schemas/reconciliation-task.schema.json`을 읽어 맞춘다.

> **checkout 경로 인자(`$ARGUMENTS`)**: 이 스킬은 인자로 이번 실행 전용 reconciler checkout
> 경로를 받는다(스케줄 러너가 fire마다 격리 디렉터리를 넘긴다 —
> `/reconciler-data-plane:reconciler-work-review <checkout-dir>`). reconciler-repo-access는 이 인자값을
> 레포 경로(`REPO="$ARGUMENTS"`)로 바로 쓴다. `claude --bg`로 띄운 세션엔 러너가 exec 직전 export한
> env가 도달하지 않으므로(프롬프트만 데몬 경계를 넘는다) 경로는 인자로만 전달된다 — 인자를 무시하고
> 다른(프리프로비전·공유) checkout에서 작업하지 말 것.

**전제**: 대상은 planner가 실행 직전 상태까지 끌어올린 task다 — attempts 마지막 항목에
`plan.steps`·`plan.executionGuide`·`preparation`(PR 또는 직접 액션)이 모두 채워졌고 status가
`planned`인 것. 이 전제를 만족하는 task가 없으면 판단할 것이 없다. 그때는 계획·실행을 시작하지
말고 상태만 알리고 **깨끗이 종료한다**(Step 0).

## Step 0 — 대상 선정 · 진입 게이트 (4-0)

reconciler-repo-access Step 1로 레포·헬퍼를 확보한 뒤(읽기 토큰), 대상 집합을 정한다.

- 사용자가 특정 task/모델을 지목했으면 그 task로 한정한다.
- 아니면 `data/reconciliation-tasks/*.json`의 task들을 훑어 아래 조건으로 거른다.

**대상(ready)** = 다음을 모두 만족:
- 마지막 attempts 항목에 `plan.steps`·`plan.executionGuide`가 있고 `preparation`이 기록돼 있다
  (PR url이 있거나, 직접 액션이라 `pullRequestUrl:null`+`notes`).
- status가 `planned` — 아직 검토 판단 전인 미점유 인수인계 지점.

**대상이 아님**(필드가 채워져 있어도 제외):
- `assessing`/`no_action_needed` — 감지 단계 몫.
- `action_required` — 조치 필요로 판정됐으나 아직 계획 전. 계획은 planner의 몫.
- `planning` — 다른 planner 워커가 계획 중(점유).
- `reviewing` — 다른 리뷰 워커가 판단 중(점유). Step 0에서 새로 집지 않는다.
  같은 대화에서 이 워커가 점유한 task는 이후 Step 흐름을 그대로 이어갈 뿐, 이 게이트로 되돌아와
  다시 고르는 대상이 아니다.
- `approved` — 이미 판정이 끝난 실행 대기. **reconciler-work-executor**의 몫이다. 판정을 뒤집지 않는다.
- `executing`/`verifying` — 실행 워커가 점유해 진행 중.
- `review_rejected` — 거부됨. 거부 사유를 반영한 **재계획이 먼저**다(planner).
- `cancelled`/`succeeded`/`failed` — 종료 또는 재작업 진입점(planner).

분기:
- **ready가 1건 이상** → **딱 한 건만 고른다.** 사용자가 지목했으면 그 task를, 아니면 우선순위
  (오래된 순)로 하나를 정한다. 여러 건이면 어느 것을 고르는지 — 그리고 **나머지는 이번에
  점유하지 않고 `planned`로 남긴다**는 것을 — 한 줄로 알린 뒤, 그 한 건만 들고 Step 1로 간다.
  고른 건이 lock을 놓은 뒤 이어서 다음 건을 처리해도 되지만, **동시에 둘을 점유하지 않는다.**
- **ready가 0건** → **여기서 종료한다.**
  - 관련 task들의 현재 status와 **왜 대상이 아닌지**를 사유별로 한 줄씩 간결히 보고한다.
  - `approved`가 쌓여 있으면 reconciler-work-executor 몫, `review_rejected`가 쌓여 있으면
    reconciler-work-planner 몫이라는 것을 한 줄로 알린다.
  - **계획·실행을 여기서 시작하지 않는다.** 다른 reconciler-* 스킬로 갈아타지 않고,
    사용자에게 계속하라고 종용하거나 스킬 선택 메뉴를 들이밀지 않는다. 필요한 단계가 있으면
    어느 스킬의 몫인지만 한 줄로 알리고 턴을 끝낸다.

이 게이트의 **대상 선정까지는 읽기 전용**이다.

## Step 1 — 점유 (claim)

**판단을 시작하기 전에** 먼저 lock을 잡는다. reconciler-repo-access의 claim 규약대로:
`git pull --rebase` → 그 task의 status가 **여전히 Step 0에서 본 값(`planned`)인지
재확인**(아니면 다른 워커가 먼저 집은 것 → 물러나 다른 대상을 고르거나 상태만 보고한다) →
`reviewing`으로 upsert →
**즉시 push**. 이 push가 성공해야 판단을 시작한다. 커밋: `review(<tbm>/<rct>): claim`.

**다른 워커가 점유한 `reviewing`은 건드리지 않는다.** 오래 머물러 있어도 마찬가지다 —
시간만 보고 남의 lock을 회수하지 않는 것이 이 루프의 공통 규약이다(reconciler-repo-access).
점유한 세션이 죽어 lock이 남으면 사람이 상태를 직접 되돌려야 한다.

## Step 2 — 전제 신선도 확인

승인은 곧 실행 허가이므로, 판정 전에 **준비물이 아직 유효한지** 직접 확인한다. planner가 준비한
뒤 시간이 지나 전제가 무너졌을 수 있다.

- PR이 있으면(`preparation.pullRequestUrl`) 대상 레포 읽기 토큰(`k3s:github_app_installation_token`,
  해당 레포 한정·`contents`/`pull_requests` read)과 GitHub API로 확인한다:
  **아직 열려 있는지, CI가 통과했는지, 충돌·베이스 이동은 없는지, diff가 `plan.steps`와 일치하는지.**
- 직접 액션이면(`pullRequestUrl:null`) `preparation.notes`와 `plan.executionGuide`가 실행 가능한
  수준으로 구체적인지 본다.
- 이미 다른 경로로 해소되지 않았는지 — PR이 머지·종료됐거나 gap이 사라졌으면 이 계획은 더 이상
  승인 대상이 아니다(거부 사유가 된다, Step 3).

이 단계는 읽기 전용이다. PR에 코멘트·리뷰를 남기거나 브랜치를 갱신하지 않는다.

## Step 3 — 승인/거부 판정 (4-1)

판단: **이 계획을 지금 그대로 실행해도 되는가?** 아래 기준을 모두 따져 `review`에 기록한다.

**승인 조건** — 전부 만족해야 승인한다:
- **정합성**: 계획이 `stateSummary.gap`을 실제로 좁히고, 변경 범위가 to-be(`definition`) 수렴에
  필요한 만큼을 넘지 않는다(관련 없는 변경이 섞여 있지 않다).
- **준비물 유효**: Step 2 확인 결과 PR이 열려 있고 CI 통과·충돌 없음, 또는 직접 액션이 실행 가능하게
  구체적이다.
- **위험 통제**: `plan.riskLevel`과 영향 범위에 걸맞은 대비가 `plan.executionGuide`에 있다 —
  검증 방법(완료 기준)과 롤백 절차가 명시돼 있다. medium 이상이면 롤백이 구체적이고 실제로
  가능해야 한다.
- **불가역성**: 되돌릴 수 없는 작업(데이터 삭제·파괴적 마이그레이션·외부로 나간 부작용 등)이
  포함돼 있지 않거나, 포함돼 있다면 그 필요성과 사전 백업 등 안전장치가 계획에 명시돼 있다.

**거부 사유** — 하나라도 해당되면 거부한다:
- 계획이 gap을 해소하지 못하거나, 범위를 벗어난 변경이 섞여 있다.
- PR이 닫힘·머지됨·CI 실패·충돌·베이스 이동 등으로 유효하지 않다, 또는 이미 해소됐다.
- 검증 방법·롤백 절차가 없거나 모호하다.
- 불가역 작업에 안전장치가 없다, 또는 영향 범위 대비 위험이 과하다.
- 판단에 필요한 정보가 부족해 확신할 수 없다(무엇이 부족한지를 사유로 쓴다).

**기록**:
- **승인** → `review.status:"approved"`, `reviewedAt`(현재 시각), `reason`(승인 근거). status `reviewing → approved`.
  커밋: `review(<tbm>/<rct>): approved`.
- **거부** → `review.status:"rejected"`, `reviewedAt`, `reason`(판정 근거), `comment`(**planner가 고쳐야 할 것**). status
  `reviewing → review_rejected`. 커밋: `review(<tbm>/<rct>): rejected`.

`review.required`·`review.reviewer`는 폐기됐다 — 쓰면 스키마가 거부한다. 사람 승인 필요 여부는
**`manualApproval`의 유무가 유일한 기록**이다(사람 승인 요구(4-2)로 승인할 때만 남긴다).

### 사람 승인 요구 (4-2)

승인 조건을 모두 만족해 **승인하기로 결론 낸 뒤에만** 따진다. 사람 승인은 부족한 계획을 통과시키는
수단이 아니다 — 승인 조건을 못 채웠으면 거부한다.

**조건은 하나다: 대상 레포가 PR 머지에 사람 승인을 요구하는데, 그 승인이 아직 없다.** 즉
- 대상 레포 기본 브랜치의 required status check 중 **사람 승인용 context**가 있고
  (`GET /repos/{owner}/{repo}/rules/branches/{base}`의 `required_status_checks`), 그 context가 사람 승인용이라는
  것은 대상 레포의 수동 승인 정책 문서(`pr-manual-approval` 유형의 프로세스 표 `status context`)로 확인한다.
- 그 context의 최신 status가 Step 2에서 확인한 PR head에 `success`로 붙어 있지 않다(대상 레포의 판정기가
  "사람이 봐야 한다"고 판단해 붙이지 않은 것).

이 경우 CI 미통과로 보고 거부하지 않는다 — 머지를 막는 것은 사람 승인이지 계획의 결함이 아니다. 해당하지
않으면(그런 context가 없거나 이미 success) 지금까지처럼 승인하되 `manualApproval`을
남기지 않는다. 위험도·불가역성은 이 조건과 무관하게 4-1의 승인/거부 기준으로만 다룬다.

**기록** — 승인 기록에 다음을 더한다:
- `review.manualApproval`: `{"sha": "<Step 2에서 확인한 PR head>", "context": "<그 사람 승인 context>"}`.
  PR 위치는 `preparation.pullRequestUrl`에 이미 있으므로 옮겨 적지 않는다. 승인은 이 `sha`에 묶인다 —
  PR에 새 커밋이 올라오면 이전 승인은 무효다.
- `reason`에 사람 승인이 필요한 이유(어느 context가 없는지)를 한 문장 포함한다.
- status는 그대로 `reviewing → approved`. 커밋: `review(<tbm>/<rct>): approved (manual approval required)`.

> **승인을 스스로 만들지 않는다.** 이 스킬(과 루프의 어떤 무인 단계)도 사람 승인 context에 status를 쓰지
> 않는다(`github_commit_status_create` 포함). 사람 없이 도는 것이 그 status를 붙이면 사람 승인은 형식이 된다.
> 승인은 대상 레포의 정책 문서가 정한 절차대로 사람이 한다(사람 세션의 reconciler-manual-approval 포함). 사람이
> 거부하면 그 스킬이 `approved → review_rejected`로 넘긴다.

**`reason`과 `comment`는 다른 세션이 읽는다.** 여기서 한 생각은 기록에 남긴 것만 건너간다.
- `reason` — 판정 근거를 **위험 요인·불가역성·신선도 확인 결과 중심으로 2~4문장**(예: "프로덕션
  이미지 태그 교체. PR #12 열림·CI 통과·충돌 없음. 롤백은 이전 태그 재배포로 가능하고 검증 기준이
  명시돼 있어 승인").
- `comment`(거부 시) — planner 재계획의 입력이 된다. "위험함"처럼 뭉뚱그리지 말고 **무엇을 바꾸면
  승인될지**를 구체적으로 쓴다(예: "executionGuide에 롤백 절차 없음 — 이전 values 복원 단계 추가
  필요. PR에 gap과 무관한 resources 변경 포함 — 제거 필요").
- gap·계획·PR 링크는 이미 `trigger`·`assessment`·`plan`·`preparation`에 있으므로 옮겨 적지 않는다.

**반복 거부 한도.** 거부 → 재계획 → 거부가 끝없이 돌지 않게 한다. 이번 판정이 거부이고, 직전
attempts 항목들까지 합쳐 **연속 3회째 이 스킬의 거부**(`review.status:"rejected"`이고 `manualApproval`이 없는 것 —
`manualApproval`이 남은 거부는 사람의 거부라 세지 않는다)라면
`review_rejected` 대신 status를 `cancelled`로 두고 `comment`에 반복 거부 사실과 공통 원인을
남긴다. 커밋: `review(<tbm>/<rct>): cancel after repeated rejection`. 자동 루프로 풀리지 않는
건이므로 사람이 계획을 직접 들여다봐야 한다는 뜻이다.

이 전이가 lock 해제이자 인수인계다. 판정을 마쳤으면 **반드시 `approved`/`review_rejected`/
`cancelled` 중 하나로 전이해 `reviewing`을 벗어난다** — 판정만 하고 `reviewing`으로 남겨두면
아무도 집을 수 없는 상태가 된다. 판정 도중 중단해야 하면(도구 장애 등) 근거를 남기고 점유 전 값(`planned`)으로
되돌려 lock을 푼다.

**스키마에 없는 필드를 임의로 만들지 않는다.** 기록은 기존 `review` 필드로 충분하다.

> 판정은 **그 시도(attempts 마지막 항목)에 대한 것**이다. 재작업으로 새 시도가 append되면 그
> 항목에는 `review`가 없으므로 자연히 다시 판정 대상이 된다 — 지난 판정이 새 계획으로 흘러들지
> 않는다.

## 산출물 / 핸드오프

- 점유했던 task는 attempts 마지막 항목에 `review`가 채워지고, status가 `approved`(실행 대기 — 사람 승인을
  요구했으면 `review.manualApproval`과 함께),
  `review_rejected`(재계획 대기) 또는 `cancelled`(반복 거부)로 전이돼 커밋돼 있다. `reviewing`으로
  남은 task가 있으면 안 된다.
- 실행·검증은 하지 않았다. `approved` 건은 **reconciler-work-executor**가, `review_rejected` 건은
  **reconciler-work-planner**가 이어받는다.
- 남은 `planned` 건이 있으면 몇 건인지 알린다. 이어서 처리하려면 **한 건씩 새로 점유**해 같은
  절차를 반복하되, 어느 순간에도 점유 중인 task가 둘 이상이 되지 않게 한다.
- 사용자에게 결과를 간결히 알린다: 승인/거부/취소 중 어느 쪽인지, 핵심 근거, 거부면 planner가
  고쳐야 할 것, 사람 승인을 요구했으면 어느 PR의 어느 context가 필요한지. 판단할 게 없었으면 각 task가 걸린 지점.
- 이 보고는 모든 도구 작업·커밋이 끝난 뒤 **턴의 마지막**에 연속된 블록으로 둔다.
