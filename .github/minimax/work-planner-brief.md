# 메인 지침 — 무엇을 해야 하는가

너는 `reconciler-work-planner` 스킬을 새로 작성한다. 완성본 예시는 없다 — 아래 지침과 레포를 직접 읽고 설계하라.
이 메인 지침은 스킬이 반드시 갖춰야 할 핵심 규칙이다. 뒤따르는 **서브 지침**은 결과물의 품질을 위한 보조 규칙이다. 둘이 어긋나면 메인 지침이 우선한다.

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
4. `plan`: `summary`(접근과 그 이유, 이 시도의 범위·완료 기준, 범위 밖), `riskLevel`, `steps[]`(`seq` 1부터 · `action` · `expectedOutcome`, 검증 가능한 단위로), `plannedAt`. 완료 기준은 실행 단계가 실행·검증을 마친 뒤 이 task를 `succeeded`/`failed`로 닫는 기준이다 — 머지·반영 후에 참이 될 것을 쓰고, 계획 단계가 끝난 상태(PR 열림·미머지 등)는 쓰지 않는다.
   - **범위를 빠짐없이 대조한다.** 감지가 남긴 차이 하나하나와 모델 정의가 이 task에 지정한 의무(정의를 끝까지 읽어 찾는다 — 개정 메모의 「개정 뒤 첫 task가 맡는다」처럼 특정 task·시점에 맡긴 일) 전부를, 이번 시도에서 닫거나 아래 사유로 범위 밖에 둔다. 범위 밖 항목마다 이어받는 주체가 있어야 한다.
   - **범위 밖 사유는 다음 넷뿐이다.** (가) 다른 주체가 이미 맡음 — 같은 모델의 열린 형제 task(종료된 task는 안 된다) 또는 정의가 다른 모델 소관이라 한 축. (나) 사람 결정 대기 — 6번의 `제안:` PR이나 정의가 사람 몫이라 한 결정. (다) 모델 정의의 슬라이스·분할 규칙 — 남은 몫을 잇는 방법까지 정의가 정했을 때만. (라) 대상 레포 밖 선행 조건 — 다른 레포·클러스터·외부 서비스·권한처럼 이번 PR로 바꿀 수 없는 것.
   - **사유가 되지 않는 것**: 같은 대상 레포 안에서 이번 PR로 고칠 수 있는 도구·게이트·스크립트·테스트가 아직 없거나 맞지 않다는 것(그것을 고치는 일도 이번 범위다), 정의의 슬라이스 규칙 없이 작업량이 많다는 것, 「뒤의 재감지가 이어받는다」는 기대. 재감지는 대상 버전이 바뀔 때만 돌고 남은 항목을 다시 잡는다는 보장이 없으므로, 정의가 그렇게 정하지 않은 한 이어받는 주체로 삼지 않는다.
   - **완료 기준은 범위 밖 항목이 포함된 상태를 주장하지 않는다.**
5. `preparation`: git 관리 대상을 바꾸는 작업이면 대상 레포에 브랜치 → 커밋 → PR(머지하지 않는다). 기존 PR을 이어 쓰면 PR 본문도 이번 계획에 맞게 준비 단계에서 고친다. 바꿀 코드가 없으면 PR 없이 `pullRequestUrl: null`과 `notes`로 준비 성격을 남긴다. 준비를 끝내지 못했으면 `preparation`을 남기지 않는다. CI 게이트를 통과시키려고 다른 모델 소관의 판정·원장 기록을 실제 판정 없이 수치만 갱신하지 않는다 — 그런 게이트 실패는 범위 밖으로 적는다.
6. 사람이 소유한 결정(모델 정의나 대상 레포 문서가 사람 몫이라 한 것)을 거쳐야 gap이 닫히면, 결정을 스스로 내리지 말고 구체안을 `제안:` PR로 올린다. 그 경로가 대상 레포의 수동 승인 정책에 걸리는지 확인한다(README 「실행 전 사람 승인」).
7. `plan.executionGuide`(마크다운): 실행 순서와 이유, 단계별·전체 검증 방법(기대값), 주의사항과 롤백 절차, 범위 밖 잔여. 기존 PR을 이어 쓰거나 재사용하면 검증 기대값(`steps[].expectedOutcome` 포함 — 변경 파일 목록·개수, diff 통계)은 PR 전체(base..head) 기준으로 적는다. PR head에서 돌릴 수 있는 검증 명령은 마지막 커밋을 올린 뒤 그 head에서 전부 실제로 돌려, 나온 출력을 그대로 기대값으로 적는다. 머지 뒤에만 확인할 수 있는 값은 그렇다고 밝힌다.
8. 4–7을 다 채우면 `planning → planned`. `planned`로 넘기기 직전에 PR 본문이 최종 head·계획과 맞는지 확인한다. `planned` 뒤에는 task도 PR도 다시 쓰지 않는다 — 어긋남을 찾으면 고치지 말고 보고한다. 끝까지 못 하면 이번 시도의 변경을 남기지 않고 status를 `from_status`로 되돌려 lock을 푼 뒤 사유를 보고한다. `planning`으로 끝내지 않는다.
9. 스키마 파일은 절대 수정하지 않는다. 쓰기 전 레코드를 스키마로 검증한다(python `jsonschema`).
10. 커밋 메시지는 `plan(<toBeModelId>/<taskId>): <요약>`. 단계마다 개별 커밋을 이 순서로 남긴다: 계획(`plan`) → 준비(`preparation`) → 지침(`executionGuide`) → planned 전이. 두 단계를 한 커밋에 합치지 않는다(러너 점검이 오류로 본다).
11. reconciler push는 `git pull --rebase` 후 한다. 거절되면 다시 `pull --rebase` 후 push. 대상 레포 PR 브랜치는 rebase하지 않는다. 강제 push 금지.

도구: MCP 서버 `k3s`의 `github_app_installation_token`(대상 레포 접근, `repositories`를 그 레포 하나로 좁히고 권한은 필요한 만큼만), `resource_list`/`resource_get`(쿠버네티스 관측). reconciler push는 체크아웃에 설정된 자격 증명을 쓴다. 토큰 값은 echo·로그·커밋·task 기록·PR 본문에 절대 남기지 않는다.

다 쓰면 SKILL.md가 위 계약을 빠짐없이 다루는지 스스로 점검하고 끝내라.
