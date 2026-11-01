# 메인 지침 — 무엇을 해야 하는가

너는 `reconciler-work-executor` 스킬을 새로 작성한다. 완성본 예시는 없다 — 아래 지침과 레포를 직접 읽고 설계하라.
이 메인 지침은 스킬이 반드시 갖춰야 할 핵심 규칙이다. 뒤따르는 **서브 지침**은 결과물의 품질을 위한 보조 규칙(어떻게 할지, 무엇을 하지 말지)이다. 둘이 어긋나면 메인 지침이 우선한다.

## 산출물
- `{{SKILL_DIR}}/SKILL.md` 하나(필요하면 같은 폴더 `scripts/`에 보조 스크립트). 다른 곳은 고치지 않는다.
- YAML frontmatter: `name: reconciler-work-executor`, `description`(언제 쓰는지, 1024자 이하).
- 본문은 한국어, 다른 에이전트가 무인으로 따라 할 수 있는 단계별 절차.

## 먼저 읽을 것 (`{{REPO_DIR}}`, reconciler 체크아웃)
- `README.md` — 엔티티와 상태 흐름, 「점유는 러너가 한다」·「실행 전 사람 승인 (review.manualApproval)」 절
- `schemas/reconciliation-task.schema.json` — `attempts[]`·`execution`·`verification` 필드 계약의 유일한 출처
- `schemas/to-be-model.schema.json` — `asIs.versionScript`
- `.github/scripts/select_execute_target.py` 머리말 — 러너의 진입 게이트가 이미 확인한 것
- `data/reconciliation-tasks/` 의 `succeeded`·`failed` task 몇 개 — 기록 형태 감 잡기

## 스킬이 할 일
실행 단계: 러너가 점유해 둔 task 한 건의 **마지막 attempt**에 대해 `plan.steps`를 `plan.executionGuide`의 순서·주의사항대로 실제로 실행하고, 결과가 plan이 명시한 범위(완료 기준)에 수렴했는지 검증해 그 task에 기록한다. 재계획·재검토하지 않는다.

입력: 러너가 프롬프트로 체크아웃 경로, 점유된 `task_id`·`model_id`, 점유 커밋을 넘긴다. 대상 선정, 진입 게이트(`approved`·준비 완료·`review.manualApproval` 사람 승인 확인), 점유(`approved → executing` 전이를 `execute(<tbm>/<rct>): claim` 커밋으로 push)는 **러너가 이미 끝냈다.**

## 핵심 규칙
1. **한 건만.** 넘겨받은 task 한 건만 다룬다. 시작할 때 그 task가 `executing`인지 확인하고, 아니면 아무것도 쓰지 않고 멈춘다. 다른 task(`approved` 포함)를 스스로 집지 않는다.
2. **기록 보존.** 이 단계가 쓰는 것은 마지막 attempt의 `execution`·`verification`, task의 `status`·`updatedAt`뿐이다. 나머지(`trigger`·`createdAt`·`stateSummary`·`assessment`, 이전 attempts, 마지막 attempt의 `plan`·`preparation`·`review`)와 `data/to-be-models.json`(`lastObservedVersion` 포함), 다른 task·다른 모델 파일은 그대로 둔다. 새 task·새 attempt를 만들지 않는다.
3. **승인된 범위만.** plan에 적힌 것만 실행한다. 계획 밖 변경이 필요해지면 멈추고 `failed`로 남긴다. 전제가 무너졌으면(PR 닫힘·이미 머지·대상 사라짐) 억지로 진행하지 않는다 — 이미 해소된 것이면 `cancelled`, 아니면 `failed`. `review.manualApproval`이 있으면 머지 직전에 PR head가 그 `sha`인지 다시 확인하고, 다르면 실행하지 않고 `failed`. 사람 승인 status를 스스로 만들지 않는다.
4. **실행 기록.** `execution`을 `status: running`으로 열고, step마다 `entries[]`(`stepSeq`·`status`·`startedAt`·`finishedAt`·`log`)를 남긴다. 한 step이 실패하면 뒤 step은 중단한다. 끝나면 `execution.status`(`succeeded`|`failed`|`aborted`)와 `finishedAt`을 확정한다.
5. **검증.** task를 `verifying`으로 전이한 뒤, 모델의 `asIs.versionScript`를 다시 돌려 `asIsVersionAfter`를 남기고, `executionGuide`의 검증 방법을 `checks[]`(`name`·`status`·`detail`)로 실행한다. 판정 기준은 **plan의 범위**다 — 모델 전체 to-be와의 잔여 gap은 판정에 넣지 않고 detail에 사실로만 적는다(재감지가 후속 task를 연다).
   - 범위 달성 + checks 전부 통과 → `verification.status: passed`, task `succeeded`
   - 범위 미달성(실행 실패 포함) → `verification.status: failed`, task `failed`
6. **lock 해제.** 끝날 때 task는 반드시 `succeeded`·`failed`·`cancelled` 중 하나다. `executing`·`verifying`으로 남기지 않는다 — 도중에 막혀도 근거를 남기고 `failed`로 닫는다.
7. **검증 후 쓰기.** 쓰기 전에 task 레코드를 `schemas/reconciliation-task.schema.json`으로 검증한다(python `jsonschema`). 통과하지 않으면 쓰지 않는다.
8. **커밋.** 메시지는 `execute(<toBeModelId>/<taskId>): run`(실행 기록) → `execute(<toBeModelId>/<taskId>): verify`(검증·종료 상태), 단계마다 개별 커밋.
9. **push.** 커밋마다 `git pull --rebase` 후 push한다. 다른 작업자의 커밋이 먼저 들어와 거절되면 `pull --rebase` 후 다시 push한다.

## 도구
MCP 서버 `k3s`의 `github_app_installation_token`(대상 레포 — 읽기는 `contents:read`, 머지할 때만 그 레포 한정 write), `resource_list`/`resource_get`/`resource_patch` 등(쿠버네티스 직접 액션·관측). 실행 환경에 MCP가 없으면 plan·preparation에 적힌 위치만 쓴다.
