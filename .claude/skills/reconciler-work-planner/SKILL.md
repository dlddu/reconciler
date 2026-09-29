---
name: reconciler-work-planner
description: "reconciler 정합성 루프의 계획 단계 스킬. 작업이 필요하다고 판정된(status가 action_required인) ReconciliationTask에 대해, 차이를 좁힐 작업 계획을 근거와 함께 세우고(3-1), 실행을 스테이징하는 준비(주로 대상 레포에 PR 생성)를 하고(3-2), 실행 순서·검증 방법·주의사항을 담은 작업 지침을 작성해(3-3) task에 기록·커밋한다. 계획할 대상이 없으면 아무것도 하지 않고 그대로 종료한다. 사용자가 '이 drift 어떻게 고칠지 계획 세워줘', 'reconcile 작업 계획', '고치는 PR 만들어줘', '작업 준비해줘', '실행 순서랑 검증 방법 정리해줘', '롤백 포함해서 절차 써줘', '이 정합성 작업 어떤 순서로 하면 되는지' 같이 판정된 차이에 대한 실행 계획·준비·지침이 필요할 때 사용할 것. 실제 실행이나 검증은 다음 단계이고, 여기서는 '무엇을 어떤 순서로 어떻게 안전하게 할지'를 확정하고 PR까지 준비한다."
---

# reconciler-work-planner

"작업이 필요하다"는 판정이 난 task를, **실행 직전 상태**까지 끌어올리는 단계. 아직 실제로
반영하지 않는다(반영·검증은 reconciler-work-executor). 먼저 계획 대상이 있는지 게이트를 통과하고,
한 건만 점유한 뒤 세 가지를 만든다:

0. **대상 선정 · 진입 게이트(3-0)** → 계획 대상(`action_required`)이 없으면 여기서 종료
1. **계획(3-1)** — 무엇을 어떤 순서로 왜 그렇게 할지 → `plan`
2. **준비(3-2)** — 실행을 스테이징(주로 대상 레포에 PR 생성) → `preparation`
3. **지침(3-3)** — 실행 순서·검증 방법·주의사항 → `plan.executionGuide`

> **시도 기록은 `attempts[]`(append-only)에 쌓인다.** planner는 계획을 시작할 때 새 항목을 배열
> 끝에 덧붙이고, 위의 `plan`·`preparation`은 모두 그 **마지막 항목 안의** 필드다. 이전 항목
> (지난 시도)은 수정하지 않는다. 이 문서의 `plan`/`preparation` 표기는 전부 attempts 마지막 항목
> 기준이다.

> **핵심 제약 — 한 번에 하나만 점유(single in-flight).** 계획 대상(`action_required`)이 여러
> 건이어도 planner는 **정확히 한 건만 골라 점유(claim)한다.** 나머지는 `action_required`(미점유)로
> 그대로 두어 다음 계획 실행 또는 다른 워커의 몫으로 남긴다. 고른 한 건을 **lock을 놓는 지점**
> (계획·준비·지침을 마친 `planning → planned` 전이)까지 끌고 간 뒤에야 다음 task를 고려한다.
> 어느 순간에도 이 워커가 점유 상태(`planning`)로 붙잡은 task는 **최대 1건**이다. 여러 건을
> 한꺼번에 `action_required`에서 끌어내려 잠그지 않는다 — 처리하지도 않으면서 다른 워커의
> 인수인계만 막는다. 재작업 진입점(`review_rejected`/`failed`)에서 집을 때도 같다.

레포 접근·검증·커밋 절차와 스키마 규칙(data plane은 스키마를 수정하지 않는다)은 **reconciler-repo-access** 스킬을 따른다(그 스킬 Step 1로
레포·헬퍼를 준비하고, 헬퍼는 그 스킬이 안내하는 경로 `$TOOL`로 호출). 채우는 필드
형태는 런타임에 `schemas/reconciliation-task.schema.json`을 읽어 맞춘다.

> **checkout 경로 인자(`$ARGUMENTS`)**: 이 스킬은 인자로 이번 실행 전용 reconciler checkout
> 경로를 받는다(스케줄 러너가 fire마다 격리 디렉터리를 넘긴다 —
> `/reconciler-data-plane:reconciler-work-planner <checkout-dir>`). reconciler-repo-access는 이 인자값을
> 레포 경로(`REPO="$ARGUMENTS"`)로 바로 쓴다. `claude --bg`로 띄운 세션엔 러너가 exec 직전 export한
> env가 도달하지 않으므로(프롬프트만 데몬 경계를 넘는다) 경로는 인자로만 전달된다 — 인자를 무시하고
> 다른(프리프로비전·공유) checkout에서 작업하지 말 것. 그러면 여러 fire가 한 working tree를 공유해
> 서로의 계획을 덮어쓴다.

**전제**: 계획 대상은 status가 `action_required`인 task다(= detector가 조치 필요로 판정해
planner 대기로 넘긴 미점유 task). 재작업 진입점(`review_rejected`/`failed`)도 planner 관점에선
미점유 계획 대상으로 본다. 이 전제를 만족하는 task가 하나도 없으면 planner가 이번에 계획할 것은
없다. 그때는 감지·실행을 시작하지 말고(그건 detector/executor의 몫), 상태만 알리고 **깨끗이
종료한다**(Step 0).

**상태 전이(claim/lock)**: 계획 작성을 시작하기 **전에** 먼저 `action_required → planning`을
원자적으로 커밋·푸시해 이 task를 **점유(lock)**한다(reconciler-repo-access의 claim 규약: pull
--rebase → status가 아직 기대한 미점유 값인지 재확인 → `planning`으로 upsert → 즉시 push).
이 push가 lock이라, 다른 planner 워커는 이 task가 더 이상 미점유가 아님을 보고
물러난다. 재작업 진입점(`review_rejected`/`failed`)에서 집는 경우에도 별도 보존 작업은 없다 —
새 시도 항목을 `attempts[]` 끝에 덧붙여 계획하면 직전 시도는 자기 항목에 그대로 남는다(Step 1).
계획·준비·지침을 다 만든 뒤에는 `planning → planned`로 전이해 검토 판단 대기(미점유)로 넘긴다.

## Step 0 — 대상 선정 · 진입 게이트 (3-0)

계획을 시작하기 전에, **지금 이 스킬로 계획할 수 있는 task가 있는지** 먼저 판정한다.
reconciler-repo-access Step 1로 레포·헬퍼를 확보한 뒤(읽기 토큰), 대상 집합을 정한다.

- 사용자가 특정 task/모델을 지목했으면 그 task로 한정한다.
- 아니면 `data/reconciliation-tasks/*.json`의 task들을 훑어 아래 조건으로 거른다.

**계획 대상(ready)** = 다음 중 하나:
- status가 `action_required` — detector가 조치 필요로 판정해 planner 대기(미점유)로 넘긴 상태.
- status가 `review_rejected`/`failed` — 검토 거부·검증 실패의 **재작업 진입점**(미점유).
  거부/실패 사유를 반영해 재계획한다. `failed`는 직전 시도가 **자기 계획 범위조차 달성하지
  못했다**는 뜻이다 — 슬라이스를 완주하고 남은 잔여 gap은 `failed`가 아니라 재감지가 여는
  새 task로 온다.
- status가 `planning` — 이미 **이 planner가** 점유해 계획하다 중단된 것을 이어받는 경우(resume).
  다른 워커가 점유한 `planning`은 대상이 아니다(아래).

**계획 대상이 아님**(제외):
- `assessing` — 감지 단계 몫(detector 점유, 판정 미완). `no_action_needed` — 조치
  불필요로 판정됨(계획할 gap 없음).
- `planning` — 다른 planner 워커가 계획 중(점유).
- `planned` — 이미 계획 완료, 검토 판단 대기. claim은 reconciler-work-review의 몫이다.
- `reviewing` — reconciler-work-review가 승인/거부를 판정 중(점유).
- `approved` — 검토를 통과한 실행 대기. reconciler-work-executor의 몫이다.
- `executing`/`verifying` — reconciler-work-executor가 점유해 처리 중.
- `succeeded` — 이미 종료됨. `cancelled` — 취소됨.

분기:
- **ready가 1건 이상** → **딱 한 건만 고른다.** 사용자가 지목했으면 그 task를, 아니면 우선순위
  (위험도·오래된 순 등)로 하나를 정한다. 여러 건이면 어느 것을 고르는지 — 그리고 **나머지는
  이번에 점유하지 않고 미점유 상태로 남긴다**는 것을 — 한 줄로 알린 뒤, 그 한 건만 들고 Step 1로
  진행한다. 나머지 ready task는 건드리지 않는다(다음 계획 실행이나 다른 워커가 집는다).
- **ready가 0건** → **여기서 종료한다.** planner가 이번에 계획할 것이 없다는 뜻이다.
  - 관련 task들의 현재 status와 **왜 계획 대상이 아닌지**를 사유별로 한 줄씩 간결히 보고한다
    (예: "feature-doc: 검토 판단 대기 — 리뷰 몫", "dear-baby: 감지 판정 미완 — detector 몫").
  - **감지·실행을 여기서 시작하지 않는다.** 다른 reconciler-* 스킬로 갈아타지 않고, 사용자에게
    계속하라고 종용하거나 스킬 선택 메뉴를 들이밀지 않는다.
  - 감지가 필요하면 **reconciler-drift-detector**, 실행이 필요하면 **reconciler-work-executor**,
    검토 판정이 필요하면 **reconciler-work-review**의
    몫이라는 점만 한 줄로 알리고, 사용자가 원하면 그 스킬을 부르게 둔다. 그런 다음 턴을 끝낸다.

이 게이트의 **대상 선정까지는 읽기 전용**이다. 실제 점유(claim) 커밋은 Step 1의 첫 동작으로,
미점유에서 `planning`으로 전이하는 push의 순간 일어난다(아래).

## Step 1 — 점유(claim) + 계획 작성 (3-1)

**먼저 점유한다.** 여기서 점유하는 건 Step 0에서 고른 **그 한 건뿐이다**(single in-flight).
계획을 짜기 전에 `pull --rebase` → status가 아직 기대한 미점유 값(`action_required`, 재작업이면
`review_rejected`/`failed`)인지 재확인 → `planning`으로 upsert(`--schema` 검증) → commit →
**즉시 push**. 이 push가 lock이며, 성공한 뒤에만 아래 계획 작성을 시작한다. 재확인에서 이미
`planning` 등으로 바뀌어 있으면 다른 워커가 먼저 집은 것이므로 이 task는 건드리지 않는다
(물러나 다른 대상을 고른다). 커밋: `plan(<tbm>/<rct>): claim`.

**계획은 새 attempts 항목으로 시작한다(append-only).** 계획 초안은 `attempts[]` 끝에 새 항목을
덧붙여 그 안의 `plan`에 쓴다:

- 새 항목은 `{ (reason), plan }`으로 시작한다. 재작업 진입이면 `reason`에 재계획을 유발한 직전
  status(`review_rejected`/`failed`)를 담고, 직전 항목의 거부/실패 사유(`review.comment`,
  `verification.checks` 등)를 읽어 새 계획에 반영한다. 첫 시도면 `reason`은 생략한다.
- **이전 항목은 수정하지 않는다.** 지난 시도의 계획·검토·실행·검증 기록은 자기 항목에 그대로
  남아 레코드 안의 이력이 된다.
- 헬퍼 병합 규칙상 배열은 통째 교체다. 항목 하나만 만지더라도 기존 attempts에 새 항목을 더한
  **전체 배열**을 patch로 보낸다.
- resume(`planning`)으로 이어받았을 때: 마지막 항목이 후속 단계 필드(`review`/`execution`/
  `verification`) 없이 계획 진행 중인 내 시도면 그 항목을 이어서 채우고, 직전 시도가 완결된
  항목이면 새 항목을 덧붙인다.

그다음 `stateSummary.gap`와 `definition`을 근거로, as-is를 to-be에 수렴시킬 최소 충분한 계획을
짠다. `plan`에 기록:

- `summary`: 접근을 한 문장으로(왜 이 방법인지 포함). **이 시도의 범위(완료 기준)를 함께
  명시한다** — gap 전체가 아니라 일부만 슬라이스로 계획한다면, 무엇을 달성하면 이 task가
  성공인지와 무엇이 범위 밖인지 경계를 긋는다. 실행 단계의 검증(4-4)은 모델 전체 to-be가 아니라
  **이 범위 기준으로** 수렴을 판정해 task를 `succeeded`/`failed`로 닫고, 범위 밖 잔여 gap은
  실행이 만든 버전 변화의 재감지가 새 task로 잇는다.
- `riskLevel`: `low`/`medium`/`high`. 프로덕션·데이터·불가역성이 있으면 상향.
- `steps[]`: 각 `seq`(1부터), `action`(수행할 작업/명령), `expectedOutcome`(성공 시 관측될 것).
  단계는 검증 가능한 단위로 쪼갠다. "매니페스트 수정"과 "롤아웃 확인"을 한 단계에 뭉치지 않는다.
- `plannedAt`.

접근을 고를 때 대안을 잠깐 저울질하고, 왜 이 경로인지 `summary`에 담는다. 가역성(롤백 경로)이
있는 쪽을 선호한다.

커밋: `plan(<tbm>/<rct>): draft plan`.

## Step 2 — 준비 = 실행 스테이징 (3-2)

실행이 **git 관리 대상(매니페스트·코드·설정)을 바꾸는 작업**이면, 대상 서비스 레포에 PR을
만들어 변경을 스테이징한다. 실행 단계에서 사람이 검토하고 머지/적용할 수 있게 하기 위함이다.

- 대상 레포용 토큰을 따로 발급한다(reconciler 레포 토큰과 별개):
  `k3s:github_app_installation_token(repositories=["<repo>"], permissions={"contents":"write","pull_requests":"write","metadata":"read"})`.
- 새 브랜치를 만들고 계획대로 변경을 커밋·푸시한 뒤 GitHub API로 PR을 연다(머지는 하지 않는다).
- PR 본문에 task id, gap 요약, 계획 단계, 검증 방법을 적어 검토자가 맥락을 갖게 한다.

준비 결과를 시도 항목(attempts 마지막 항목)의 `preparation`에 기록한다. **`preparation`이 기록돼 있다는 것
자체가 준비 완료**다(별도 `prepared` 플래그는 폐기됐다) — 준비를 끝내지 못했으면 `preparation`을 남기지 않는다.
권장 최소 형태:

```json
"preparation": {
  "repository": "dlddu/flux-cd-apps",
  "branch": "reconcile/rct_20260711-0001",
  "pullRequestUrl": "https://github.com/dlddu/flux-cd-apps/pull/NN",
  "preparedAt": "2026-07-11T10:07:00+09:00",
  "notes": "..."
}
```

**PR이 없는 작업**도 있다. 예를 들어 to-be가 이미 SSOT이고 as-is만 재동기화하면 되는 경우
(`flux reconcile`, 재시작 등)에는 바꿀 코드가 없어 PR을 만들지 않는다. 이때는
`preparation`에 `pullRequestUrl:null`, `notes`에 "코드 변경 없음, 직접 액션으로
실행" 식으로 준비 성격을 남긴다. "PR을 위해 억지 변경"을 만들지 않는다.

커밋: `plan(<tbm>/<rct>): prepare PR`(또는 `prepare direct action`).

## Step 3 — 작업 지침 작성 (3-3)

실행자가 그대로 따라 할 수 있도록 **순서·검증 방법·주의사항**을 지침으로 정리해
시도 항목의 `plan.executionGuide`(마크다운)에 넣는다.

지침에 반드시 담을 것:
- **순서**: 단계 실행 순서와, 순서가 중요한 이유(의존성). 병렬 가능/불가 표시.
- **검증 방법**: 각 단계와 전체가 성공했는지 확인하는 구체적 방법(명령·관측 지표·기대값).
  이후 검증 단계(4-4)가 이걸 근거로 **계획 범위(완료 기준) 기준** 수렴을 확인한다. 범위 밖으로
  남기는 잔여 gap이 있으면 "범위 밖(후속)" 목록으로 지침에 명시해, 재감지 후 다음 계획의
  입력이 되게 한다.
- **주의사항**: 되돌릴 수 없는 지점, 트래픽/데이터 영향, 실패 시 롤백 절차, 사전 조건
  (예: "머지 전 릴리스 노트 확인", "피크 시간대 회피").

커밋: `plan(<tbm>/<rct>): write execution guide`.

## 산출물 / 핸드오프

- 마지막 attempts 항목에 `plan`(steps 포함), `preparation`, `plan.executionGuide`가 채워지고
  검증을 통과해 커밋돼 있어야 한다.
- 재계획이었다면 직전 시도 항목들이 `attempts[]`에 그대로 남아 있고, 새 계획은 **마지막 항목**이다.
- 셋이 다 채워졌으면 **status를 `planning → planned`로 전이**해 lock을 놓고 검토 판단 대기(미점유)로
  넘긴다. 커밋: `plan(<tbm>/<rct>): ready for execution`. 이 전이 전까지는 `planning`(점유)이라
  reconciler-work-review가 집어가지 않는다.
- **점유한 그 한 건만** 처리한다. `planned`로 전이해 lock을 놓은 뒤에도, 남은 ready task
  (`action_required` 등)가 있으면 **동시에 점유하지 않는다.** 남은 건은 그대로 미점유로 두고
  사용자에게 몇 건이 남았는지 알린다. 이어서 계획하려면 **한 건씩 새로 점유**해 같은 절차를
  반복하되, 어느 순간에도 이 워커가 `planning`으로 붙잡은 task가 둘 이상이 되지 않게 한다.
- 이제 **reconciler-work-review**가 `planned` task를 집어(claim) 승인/거부를 직접 판정한다.
  승인이면 `approved`, 거부면 `review_rejected`(사유는 `review.comment` — 재계획의 입력)로 간다.
  `approved` task는 **reconciler-work-executor**가 집어 실행 → 검증을 이어받는다.
- 사용자에게 계획 요약, PR 링크(있으면), 위험도, 다음 단계를 간결히 알린다.

각 하위 단계를 개별 커밋으로 남겨, 계획 수립 이력이 그대로 감사 로그가 되게 한다.
