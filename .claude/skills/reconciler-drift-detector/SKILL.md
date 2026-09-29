---
name: reconciler-drift-detector
description: "reconciler 정합성 루프의 감지 단계 스킬. 등록된 ToBeModel 중 버전이 바뀐 한 건을 골라 assessing으로 점유한 뒤, 주어진 도구로 as-is/to-be의 실제 데이터를 수집하고, 둘 사이에 유의미한 차이가 있는지 판단하고, 그 차이를 좁히는 실제 작업이 필요한지까지 근거와 함께 판단해 ReconciliationTask에 기록·커밋한다. 감지할 대상이 없으면 아무것도 하지 않고 그대로 종료한다. 사용자가 'as-is/to-be 상태 수집해줘', '지금 실제 배포랑 매니페스트 뭐가 다른지 봐줘', 'drift 있는지 확인', '이 변경에 대응 작업이 필요한지 판단해줘', 'reconciler task 상태 요약/평가', '차이가 유의미한지 근거 써줘', '모니터 alert 떴는데 대응해야 하나' 같이 목표 상태와 현재 상태의 차이를 확인·평가하려 할 때 사용할 것. 계획을 세우거나 실제로 고치는 단계가 아니라, '차이가 있나 / 유의미한가 / 지금 작업해야 하나'를 판정하는 단계다."
---

# reconciler-drift-detector

as-is(현재 실제 상태)와 to-be(목표 상태)의 **차이를 관측하고 판정**하는 단계. 여기서는
아무것도 고치지 않는다. 먼저 감지 대상이 있는지 게이트를 통과하고, **한 건만 점유한 뒤**
세 가지 질문에 순서대로 답하고, 각 답을 근거와 함께 ReconciliationTask에 남긴다.

0. **대상 선정 · 진입 게이트(2-0)** → 감지 대상이 없으면 여기서 종료
1. **점유(claim)** → 고른 한 건의 task를 `assessing`으로 만들며(또는 이어받으며) 먼저 커밋·푸시
2. **무엇이 각각의 상태인가?** (수집 → `stateSummary.asIs`/`toBe`)
3. **둘 사이에 유의미한 차이가 있는가?** (판단 → `stateSummary.gap`)
4. **그 차이를 좁히는 실제 작업이 지금 필요한가?** (판단 → `assessment`)

> **핵심 제약 — 한 번에 하나만 점유(single in-flight).** 버전이 바뀐 모델이 여러 개여도 detector는
> **정확히 한 건만 골라 점유(claim)한다.** 나머지 모델은 `lastObservedVersion`을 **갱신하지 않은 채
> 그대로 둔다** — 그래야 다음 fire나 다른 워커가 같은 변화를 다시 발견해 이어받는다. 고른 한 건을
> **lock을 놓는 지점**(`no_action_needed`/`action_required` 전이, 또는 재확인 유예 기록)까지 끌고 간
> 뒤에야 다음 대상을 고려한다. 어느 순간에도 이 워커가 `assessing`으로 붙잡은 task는 **최대 1건**이다.
> 여러 모델을 한꺼번에 감지해 여러 task를 열지 않는다 — 판정도 끝내지 못하면서 다른 워커의 몫만 막는다.

> **detector의 claim은 생성 시점 compare-and-set이다.** planner·review·executor는 이미 존재하는
> task의 status(미점유 → 점유)를 뒤집어 점유하지만, detector가 집는 대상은 **아직 task가 없는
> 모델**인 경우가 대부분이다. 그래서 점유가 곧 **task 생성**이고, compare-and-set의 기준은 status가
> 아니라 **모델의 `lastObservedVersion`**이다: "아직 아무도 이 변화로 task를 만들지 않았다"를
> 재확인한 뒤, task 생성과 `lastObservedVersion` 갱신을 **한 커밋으로 묶어 즉시 push**한다.
> 그 push가 lock이다(Step 1).

레포 접근·검증·커밋·"스키마에 없는 필드가 필요할 때"는 **reconciler-repo-access** 스킬을
따른다(그 스킬 Step 1로 레포·헬퍼를 준비하고, 헬퍼는 그 스킬이 안내하는 경로 `$TOOL`로 호출).
task는 `data/reconciliation-tasks/<toBeModelId>.json` 배열에 산다. 채우는 필드의
정확한 형태는 프롬프트가 아니라 `schemas/reconciliation-task.schema.json`을 읽어 맞춘다.

> **checkout 경로 인자(`$ARGUMENTS`)**: 이 스킬은 인자로 이번 실행 전용 reconciler checkout
> 경로를 받는다(스케줄 러너가 fire마다 격리 디렉터리를 넘긴다 —
> `/reconciler-data-plane:reconciler-drift-detector <checkout-dir>`). reconciler-repo-access는 이 인자값을
> 레포 경로(`REPO="$ARGUMENTS"`)로 바로 쓴다. `claude --bg`로 띄운 세션엔 러너가 exec 직전 export한
> env가 도달하지 않으므로(프롬프트만 데몬 경계를 넘는다) 경로는 인자로만 전달된다 — 인자를 무시하고
> 다른(프리프로비전·공유) checkout에서 작업하지 말 것. 그러면 여러 fire가 한 working tree를 공유해
> 서로의 감지를 덮어쓴다.

## 상태 전이

```
(버전 변화 · 수동 트리거 요청)
        └─claim─> assessing ─┬─ 작업 불필요 ───> no_action_needed  (종료)
          (점유)             ├─ 작업 필요 ─────> action_required   (planner 대기, 미점유)
                             └─ 자동 해소 가능 ─> assessing 유지 + recheckAfter (유예)
```

- task가 아직 없으면 **점유 커밋에서 생성**(`assessing`)하며 `trigger`를 기록한다.
- 수집·차이판단을 하는 동안 `assessing`으로 둔다(이 단계를 붙잡고 있다는 점유 표시).
- 작업 불필요 → `no_action_needed`(종료, lock 해제).
- 작업 필요 → **`action_required`로 전이**하고 여기서 손을 뗀다. `action_required`는
  planner가 집어갈 수 있는 **미점유 인수인계 지점**이다(claim/lock 규약은 reconciler-repo-access
  참고). detector가 직접 `planning`으로 넘기지 않는다 — 계획 단계 진입(=lock)은 planner의 몫.
- 재확인 유예 → `assessing` + `assessment.recheckAfter`. 그 시각이 지나면 **누구나 이어받을 수 있는
  재진입점**이 된다(Step 1(C)). 시각 없이 파킹하면 아무도 풀 수 없는 lock이 되므로 금지한다.

## Step 0 — 대상 선정 · 진입 게이트 (2-0)

감지를 시작하기 전에, **지금 이 스킬로 감지할 대상이 있는지** 먼저 판정한다.
reconciler-repo-access Step 1로 레포·헬퍼를 확보한 뒤(읽기 토큰), 아래 순서로 후보를 찾는다.
**앞 단계에서 후보를 찾으면 뒤 단계는 보지 않는다** — 어차피 한 건만 집으므로 비싼 버전 스윕을
돌릴 이유가 없다.

1. **resume** — 이 세션이 이미 점유해 판정하다 중단한 `assessing` task. 있으면 그것으로 확정.
2. **재확인 만료** — 유예로 파킹된 `assessing` task 중 `assessment.recheckAfter`가 현재보다
   **과거**인 것. 있으면 그것으로 확정.
3. **수동 트리거 요청** — 활성 모델 중 `checkPolicy.manualTriggerRequestedAt`에 시각이 적힌 것.
   있으면 그것으로 확정한다. 사람이 직접 요청한 건이므로 버전 스윕보다 먼저 본다(스윕은 비싸고,
   어차피 한 건만 집는다). 요청 시각이 여럿이면 **가장 오래 기다린 것**부터.
4. **새 변화** — 활성 모델을 훑어 `asIs.versionScript`·`toBe.versionScript`로 현재 버전을 계산하고
   모델의 `lastObservedVersion`과 비교한다. 달라진 모델이 후보다(바뀐 쪽은 따로 적지 않는다 — task의
   각 side `previousVersion`≠`currentVersion`에서 도출된다).

사용자가 특정 모델/task를 지목했으면 그 대상으로 한정한다(위 탐색을 건너뛴다).

**대상이 아님**(제외):
- `checkPolicy.enabled`가 **`false`인 모델** — 비활성. **버전 스크립트도 돌리지 않는다**(생략되어
  있으면 `true`로 본다 — 기존 모델은 모두 감지 대상이다). 스케줄 러너가 이미 걸러내지만 사람이 이
  스킬을 직접 부르는 경로도 있으므로 **스킬 자신도 확인한다**. 러너와 스킬 어느 쪽으로 들어와도
  결과가 같아야 한다. 비활성화는 **감지만 멈추는 것**이다 — 모델 정의와 지난 task 이력은 그대로
  남고, 이미 열려 있는 task는 planner·리뷰·실행 단계가 원래대로 마저 처리한다.
- 버전이 그대로인 모델 — 감지할 변화가 없다. 단 `checkPolicy.manualTriggerRequestedAt`가 적혀
  있으면 **예외다**(사람이 버전과 무관하게 지금 보라고 요청한 것이므로 후보 3번으로 잡힌다).
  비활성 모델에 적힌 요청은 **무시한다** — 비활성화가 수동 요청보다 강하다.
- 다른 워커가 점유 중인 `assessing`, 재확인 시각이 아직 오지 않은 파킹 task. 같은 모델에 이런
  task가 열려 있으면 **그 모델은 이번 후보에서 제외**한다(한 모델에 감지 task를 두 건 열지 않는다).
- `action_required`/`planning`/`planned`/`reviewing`/`approved`/
  `executing`/`verifying` — 이후 단계 몫이라 detector는 건드리지 않는다. 다만 그 task가 열려 있다는
  것이 **모델을 후보에서 빼는 사유는 아니다** — 새 버전 변화는 새 task로 잇는다.
- `no_action_needed`/`succeeded`/`cancelled`/`failed`/`review_rejected` — 종료·재작업 상태.

분기:
- **후보가 1건 이상** → **딱 한 건만 고른다.** 사용자가 지목했으면 그 대상을, 아니면 위 우선순위
  (resume → 재확인 만료 → 새 변화)로, 새 변화가 여럿이면 `lastObservedAt`이 **가장 오래된 모델**을
  고른다(오래 방치된 쪽부터 — 자주 바뀌는 모델이 감지를 독점하지 못하게 한다). 여러 건이면 무엇을
  골랐는지와 **나머지는 이번에 점유하지 않고 그대로 둔다**는 것을 한 줄로 알린 뒤 Step 1로 간다.
- **후보가 0건** → **여기서 종료한다.** 이번에 감지할 것이 없다는 뜻이다.
  - 훑은 모델 수와 **왜 대상이 아닌지**를 사유별로 한 줄씩 간결히 보고한다
    (예: "활성 12개 중 버전 변화 없음", "dear-baby: 재확인 유예 중(14:20 이후)").
  - **계획·실행을 여기서 시작하지 않는다.** 다른 reconciler-* 스킬로 갈아타지 않고, 사용자에게
    계속하라고 종용하거나 스킬 선택 메뉴를 들이밀지 않는다. 계획이 필요하면
    **reconciler-work-planner**, 실행이 필요하면 **reconciler-work-executor**, 검토 판정이
    필요하면 **reconciler-work-review**의 몫이라는 점만 한 줄로 알리고 턴을 끝낸다.

이 게이트는 **읽기 전용**이다. 버전 스크립트 실행은 읽기이므로 여기서 해도 되지만, 모델의
`lastObservedVersion`·`lastObservedAt`을 갱신하는 쓰기는 **오직 Step 1의 점유 커밋에서만** 한다.

## Step 1 — 점유(claim) + trigger 확정

**먼저 점유한다.** 여기서 점유하는 건 Step 0에서 고른 **그 한 건뿐이다**(single in-flight).
점유 push가 성공한 뒤에만 Step 2의 수집을 시작한다.

**(A) 새 변화를 점유 — task 생성**

1. `git pull --rebase`로 최신화한다.
2. 고른 모델의 해당 side `lastObservedVersion`이 **여전히 방금 관측한 이전 값 그대로**인지, 그
   모델에 열린 `assessing` task가 없는지 재확인한다.
3. 맞으면 **한 커밋**에 다음 둘을 함께 담고 **즉시 push**한다. 이 push가 lock이다.
   - 새 id(`python3 "$TOOL" next-id --file <file> --date $(date +%Y%m%d)`)로 task를 `--create`:
     `toBeModelId`·`status:"assessing"`·`trigger`(`detectedAt`, 바뀐 side의
     `asIs`/`toBe`: `previousVersion`/`currentVersion`)·`createdAt`. 버전 변경 task는 스키마가 `asIs`나
     `toBe` 중 하나 이상을 요구한다. `changedSides`는 폐기됐으니 쓰지 않는다.
   - 모델의 해당 side `lastObservedVersion`/`lastObservedAt`을 방금 계산한 값으로 갱신(캐시
     필드이므로 스키마 변경이 아니다).
   - 커밋: `detect(<tbm>/<rct>): claim`.
4. 2에서 값이 이미 바뀌어 있으면 **다른 워커가 먼저 집은 것**이다. 그 대상은 건드리지 말고 물러나,
   다른 후보를 고르거나 종료한다. push가 rebase 충돌로 실패하면 `pull --rebase` 후 2부터 재시도한다.

> **두 갱신을 한 커밋으로 묶는 이유**: task만 만들고 모델 갱신이 늦으면 다른 fire가 같은 변화로
> 중복 task를 만든다. 반대로 모델만 갱신되면 그 변화는 영영 감지되지 않는다. 둘은 한 커밋·한 push다.

**(B) 수동 트리거 요청을 점유 — task 생성**

1. `git pull --rebase`로 최신화한다.
2. 모델의 `checkPolicy.manualTriggerRequestedAt`가 **여전히 방금 본 그 값 그대로**인지, 그 모델에
   열린 `assessing` task가 없는지 재확인한다.
3. 맞으면 **한 커밋**에 다음을 함께 담고 **즉시 push**한다. 이 push가 lock이다.
   - 새 id로 task를 `--create`: `toBeModelId`·`status:"assessing"`·`createdAt`·`trigger`
     (`source:"manual"`, `detectedAt`, `reason`). 수동 요청은 바뀐 쪽이 없을 수 있으므로
     `asIs`/`toBe` 버전 기록은 **생략해도 된다** — 스키마가 `source:"manual"`일 때만 이를 허용한다.
   - `reason`은 모델의 `checkPolicy.manualTriggerReason`을 **그대로 옮겨 적는다**(요약·윤색하지
     않는다 — 요청한 사람의 말이 계획 단계까지 가야 한다). `source:"manual"`인데 `reason`이 없으면
     스키마가 생성을 거부하므로, 값이 비어 있으면 요청이 깨진 것이니 억지로 지어내지 말고 그
     모델을 건너뛰고 사용자에게 알린다.
   - 모델의 `manualTriggerRequestedAt`와 `manualTriggerReason`을 **둘 다** `null`로 지운다(스키마가
     둘을 짝으로 묶으므로 한쪽만 지우면 검증에 걸린다). **이 지움이 compare-and-set의 대상**이라,
     요청 하나가 task 하나만 만든다(지우지 않으면 이후 모든 fire가 같은 요청으로 task를 계속 연다).
   - 커밋: `detect(<tbm>/<rct>): claim manual`.
4. 2에서 이미 `null`이면 다른 워커가 먼저 집은 것이다. 물러나 다른 후보를 고르거나 종료한다.

> **사람이 이 스킬을 직접 불러** 저장된 요청 없이 특정 모델을 감지하는 경우에도, 버전이 그대로면
> task는 `source:"manual"`로 열린다. 이때 `reason`에는 **사용자가 지시한 내용**을 적는다
> (예: "사용자가 세션에서 직접 재감지를 지시 — 지난 판정 재확인"). 모델에는 요청이 없었으므로
> 지울 필드도 없다.

> **버전도 함께 바뀌어 있으면** 그 side의 `previousVersion`/`currentVersion`을 같이
> 적고 모델의 `lastObservedVersion`도 같은 커밋에서 갱신한다(`source`는 `manual`로 둔다 — 이 task를
> 연 계기는 사람이다). 그래야 방금 본 변화를 다음 스윕이 또 task로 열지 않는다.

**(C) 이어받기 — resume / 재확인 만료**

- **resume**: 이미 내가 잡고 있는 `assessing`이므로 별도 claim 없이 중단 지점부터 이어 채운다.
- **재확인 만료**: `pull --rebase` → `assessment.recheckAfter`가 **여전히 과거 값 그대로**인지
  재확인 → 그 필드를 `null`로 지우는 upsert(`--schema` 검증) → commit → **즉시 push**. 이 push가
  재진입 lock이다. 커밋: `detect(<tbm>/<rct>): claim recheck`. 이미 지워졌거나 미래 값으로 바뀌어
  있으면 다른 워커가 먼저 집은 것이므로 물러난다.

> 실행 단계가 부분 슬라이스로 task를 `succeeded`로 닫은 뒤에는, 그 실행이 만든 버전 변화가
> **이 단계를 다시 트리거하는 것이 정상이다**(executor는 `lastObservedVersion`을 건드리지 않고
> 후속 task도 직접 만들지 않는다). 그때 잔여 gap이 남아 있으면 이 Step에서 새 task를 열어
> `action_required`로 넘기고, gap이 다 닫혔으면 `no_action_needed`로 확정한다 — 슬라이스 →
> 재감지 → 후속 task가 정합성 루프의 정상 진행 방식이다.

## Step 2 — 수집 (2-1): 주어진 도구로 실제 데이터 모으기

버전 문자열만으로는 "무엇이 왜 다른지"를 알 수 없다. 각 dataSource 종류에 맞는 도구로
요약에 필요한 실제 상태를 읽는다. 버전 스크립트는 변경 감지용이고, 여기서는 그 이상을 본다.

- **github**: 대상 subPath를 얕은 클론하거나 두 커밋 간 diff를 떠서 *무엇이* 바뀌었는지 본다
  (이미지 태그, replicas, 리소스, 런북 절차 등).
- **kubernetes_deployment**: k3s 도구(pod describe/logs, workload list)나 kubectl로 현재
  revision·이미지·replicas·리소스·상태를 읽는다.
- **monitor_alert**: Datadog 등에서 해당 alert 이벤트의 발생/복구 시각, 지속시간, 메시지,
  관련 지표를 읽는다.
- **custom**: 모델 정의에 명시된 방식으로 읽는다.

수집 결과를 사실 위주의 마크다운으로 정리해 `stateSummary.asIs`와 `stateSummary.toBe`에
넣는다. 추측 대신 관측값을 쓰고, 읽은 시각/버전을 함께 남기면 좋다.

## Step 3 — 유의미한 차이 판단 (2-2)

두 상태를 나란히 놓고, **목표 정의(`definition`)에 비추어** 차이가 유의미한지 가른다.

- 유의미: 정의의 기준(이미지 버전, replicas, 리소스 하한, 임계값, 반영 시간 등)을 실제로
  어기거나 어길 위험이 있는 차이.
- 무의미: 정의가 신경 쓰지 않는 차이(예: 코멘트/포맷팅만 바뀐 매니페스트, 정의 기준을 여전히
  만족하는 값 변동), 또는 이미 해소된 차이.

수동 트리거로 열린 task라면 `trigger.reason`이 **무엇을 보라는 요청인지** 말해준다. 버전 diff가
비어 있어도 그 사유가 가리키는 지점을 실제로 확인하고, 확인 결과를 근거에 포함한다.

판단 결과와 **근거**를 `stateSummary.gap`에 한두 문장으로 적는다(무엇이 어떻게 다른지 +
그게 정의상 문제인지). `summarizedAt`도 채운다. 이 커밋으로 2-1/2-2가 남는다:
`detect(<tbm>/<rct>): summarize state`.

## Step 4 — 작업 필요 여부 판단 (2-3)

유의미한 차이가 있어도 "지금 작업"이 정답이 아닐 수 있다. **판정 자체는 status 전이로 기록하고**,
`assessment`에는 그 근거를 남긴다:

- `reason`(근거), `assessedAt`. (`assessedBy`는 폐기됐다 — 사람이 개입했으면 `reason`에 적는다.)
- `assessment.actionRequired`는 **쓰지 않는다**(status와 중복이라 스키마에서 폐기됐다). 조치 필요
  여부는 아래 status가 유일한 기록이다.

판단 지침:
- 차이가 없거나 무의미 → **status `no_action_needed`**(lock 해제). `reason`에 근거.
- 유의미하고 지금 대응이 필요 → **status를 `action_required`로 전이**(planner 대기, 미점유).
  이 커밋으로 조치 필요 판정과 lock 해제가 함께 남는다.
- **자동 해소 가능성이 있는 경우**(예: 롤아웃 진행 중, 5분 미만의 일시적 alert, 곧 재동기화될
  변경)는 섣불리 작업하지 말고 **일정 시간 후 재확인**을 택한다. 이때:
  - status는 `assessing`으로 두고, `assessment.reason`에 "차이 존재하나 자동 해소 가능성 있어
    `<시각>`에 재확인" 형태로 유예 근거와 재확인 시각을 남긴다.
  - **기계가 읽는 `assessment.recheckAfter`(date-time)를 반드시 함께 채운다.** 이 필드가 없으면
    파킹된 task는 아무도 이어받을 수 없는 lock으로 남는다(단일 in-flight 규약에서 특히 위험하다).
  - **유예는 이번 실행의 종료 지점이다.** 파킹한 뒤 다른 모델을 추가로 점유하지 않는다. 재확인
    시각이 지나면 Step 0의 후보 2번으로 잡혀, 차이가 지속되면 `action_required`로, 해소됐으면
    `no_action_needed`로 확정된다(재진입 시 `recheckAfter`는 `null`로 지운다).

이 커밋으로 2-3이 남는다: `detect(<tbm>/<rct>): assess action`.

## 산출물 / 핸드오프

- `stateSummary`(asIs/toBe/gap)와 `assessment`가 채워지고 검증을 통과해 커밋돼 있어야 한다.
- 조치 불필요 → status `no_action_needed`로 종료. 사용자에게 근거를 알린다.
- 조치 필요 → status `action_required`로 두고 종료. **reconciler-work-planner**가
  이 task를 집어(claim) 계획을 세울 차례다.
- 재확인 유예 → `assessing` + `recheckAfter`로 두고 종료. 지정 시각 이후의 실행이 이어받는다.
- **점유한 그 한 건만** 처리한다. lock을 놓은 뒤에도 남은 후보(다른 모델의 미반영 버전 변화)를
  같은 실행에서 연달아 점유하지 않는다. 남은 건이 있으면 몇 건인지 알리고, 이어서 감지하려면
  **한 건씩 새로 점유**해 같은 절차를 반복하되, 어느 순간에도 이 워커가 `assessing`으로 붙잡은
  task가 둘 이상이 되지 않게 한다.

항상 최종 판정과 **근거 요약**을 사용자에게 간결히 전달한다. 근거 없는 "작업 필요/불필요"는
남기지 않는다.
