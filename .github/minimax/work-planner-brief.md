너는 `reconciler-work-planner` 스킬을 새로 작성한다. 완성본 예시는 없다 — 아래 지침과 레포를 직접 읽고 설계하라.

## 산출물
- `{{SKILL_DIR}}/SKILL.md` 하나(필요하면 같은 폴더 `scripts/`에 보조 스크립트). 다른 곳은 고치지 않는다.
- YAML frontmatter: `name: reconciler-work-planner`, `description`(언제 쓰는지, 1024자 이하).
- 본문은 한국어, 다른 에이전트가 무인으로 따라 할 수 있는 단계별 절차. 군더더기 없이.

## 먼저 읽을 것 (`{{REPO_DIR}}`, reconciler 체크아웃)
- `README.md` — 엔티티와 상태 흐름, 「점유는 러너가 한다」, 「실행 전 사람 승인」
- `schemas/reconciliation-task.schema.json` — `attempts`·`plan`·`preparation` 필드 계약의 유일한 출처
- `.github/scripts/claim_plan_target.py` 머리말 — 러너가 이미 끝낸 대상 선정·점유가 무엇을 기록하는지
- `data/reconciliation-tasks/`에서 `attempts`가 채워진 레코드 몇 개 — 계획·준비·지침이 실제로 어떻게 기록되는지

## 스킬이 할 일
계획 단계: 러너가 `planning`으로 점유해 둔 task 한 건에 대해, 감지가 남긴 gap(`stateSummary`·`assessment`)과 모델 정의를 근거로 차이를 좁힐 계획을 세우고, 실행을 스테이징하고(대개 대상 레포 PR), 실행 지침을 써서 `planned`로 넘긴다. 실행·머지·배포는 하지 않는다(executor 몫).

입력: 러너가 프롬프트로 체크아웃 경로, 점유된 `task_id`·`model_id`, 점유 전 status(`from_status`), 점유 커밋, 대상 레포 작업 디렉터리를 넘긴다. 대상 선정과 점유(`from_status → planning` 커밋·push)는 **러너가 이미 끝냈다.** 스킬은 대상을 고르지도, 점유하지도 않는다.

지켜야 할 계약:
1. 넘겨받은 task 한 건만 다룬다. 시작할 때 그 task가 `planning`인지 확인하고, 아니면 아무것도 쓰지 않고 멈춘다.
2. `attempts`는 append-only: 끝에 새 항목 하나를 덧붙이고 이전 항목은 고치지 않는다. 재작업(`from_status`가 `review_rejected`/`failed`)이면 새 항목 `reason`에 그 status를 적고, 직전 항목의 거부·실패 사유를 읽어 새 계획에 반영한다. 첫 시도면 `reason`을 생략한다.
3. 그 밖은 건드리지 않는다: task의 `id`·`toBeModelId`·`trigger`·`createdAt`·`stateSummary`·`assessment`, `data/to-be-models.json`, 다른 task·모델 파일. 새 task를 만들지 않는다. 대상 레포는 reconciler 체크아웃 **밖**(작업 디렉터리)에 클론한다.
4. `plan`: `summary`(접근과 그 이유, 이 시도의 범위·완료 기준, 범위 밖), `riskLevel`, `steps[]`(`seq` 1부터 · `action` · `expectedOutcome`, 검증 가능한 단위로), `plannedAt`.
5. `preparation`: git 관리 대상을 바꾸는 작업이면 대상 레포에 브랜치 → 커밋 → PR(머지하지 않는다). PR 본문에 task id·gap·단계·검증 방법. 바꿀 코드가 없으면 PR 없이 `pullRequestUrl: null`과 `notes`로 준비 성격을 남긴다. 준비를 끝내지 못했으면 `preparation`을 남기지 않는다.
6. 사람이 소유한 결정(모델 정의나 대상 레포 문서가 사람 몫이라 한 것)을 거쳐야 gap이 닫히면, 결정을 스스로 내리지 말고 구체안을 `제안:` PR로 올린다. 그 경로가 대상 레포의 수동 승인 정책에 걸리는지 확인한다(README 「실행 전 사람 승인」).
7. `plan.executionGuide`(마크다운): 실행 순서와 이유, 단계별·전체 검증 방법(기대값), 주의사항과 롤백 절차, 범위 밖 잔여.
8. 4–7을 다 채우면 `planning → planned`. 끝까지 못 하면 이번 시도의 변경을 남기지 않고 status를 `from_status`로 되돌려 lock을 푼 뒤 사유를 보고한다. `planning`으로 끝내지 않는다.
9. 스키마 파일은 절대 수정하지 않는다. 쓰기 전 레코드를 스키마로 검증한다(python `jsonschema`).
10. 커밋 메시지는 `plan(<toBeModelId>/<taskId>): <요약>`, 단계마다 개별 커밋(계획 → 준비 → 지침 → planned 전이).
11. push는 `git pull --rebase` 후 한다. 거절되면 다시 `pull --rebase` 후 push. 강제 push 금지.

도구: MCP 서버 `k3s`의 `github_app_installation_token`(대상 레포 접근, `repositories`를 그 레포 하나로 좁히고 권한은 필요한 만큼만), `resource_list`/`resource_get`(쿠버네티스 관측). reconciler push는 체크아웃에 설정된 자격 증명을 쓴다. 토큰 값은 echo·로그·커밋·task 기록·PR 본문에 절대 남기지 않는다.

마지막 보고: 최종 status, 계획 요약, 위험도, PR 링크.

다 쓰면 SKILL.md가 위 계약을 빠짐없이 다루는지 스스로 점검하고 끝내라.
