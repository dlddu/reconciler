# 메인 지침 — 무엇을 해야 하는가

너는 `reconciler-work-review` 스킬을 새로 작성한다. 완성본 예시는 없다 — 아래 지침과 레포를 직접 읽고 설계하라.
이 메인 지침은 스킬이 반드시 갖춰야 할 핵심 규칙이다. 뒤따르는 **서브 지침**은 결과물의 품질을 위한 보조 규칙이다. 둘이 어긋나면 메인 지침이 우선한다.

## 산출물
- `{{SKILL_DIR}}/SKILL.md` 하나(필요하면 같은 폴더 `scripts/`에 보조 스크립트). 다른 곳은 고치지 않는다.
- YAML frontmatter: `name: reconciler-work-review`, `description`(언제 쓰는지, 1024자 이하).
- 본문은 한국어, 다른 에이전트가 무인으로 따라 할 수 있는 단계별 절차.

## 먼저 읽을 것 (`{{REPO_DIR}}`, reconciler 체크아웃)
- `README.md` — 엔티티·상태 흐름, 「점유는 러너가 한다」, 「실행 전 사람 승인 (review.manualApproval)」
- `schemas/reconciliation-task.schema.json` — `attempts[]`·`review`·`preparation` 필드 계약의 유일한 출처
- `.github/scripts/claim_review_target.py` 머리말 — 러너가 이미 끝낸 대상 선정·점유
- `templates/pr-manual-approval.tbm.md` — 대상 레포의 사람 승인 status가 무엇인지
- `data/reconciliation-tasks/` 의 실제 레코드 중 `attempts[].review`가 있는 것 몇 개

## 스킬이 할 일
리뷰 단계의 **판정**: 러너가 `reviewing`으로 점유해 둔 task 한 건에 대해, 마지막 시도(attempts 마지막 항목)의 계획과 준비물(PR 또는 직접 액션)을 지금 그대로 실행해도 되는지 **승인 또는 거부로 직접 결론**내고 그 task에 기록한다. 실행하지 않는다.

입력: 러너가 프롬프트로 체크아웃 경로, 점유된 `task_id`·`model_id`, 점유 커밋, PR URL(없으면 직접 액션)을 넘긴다. 대상 선정과 점유(`planned → reviewing` 커밋·push)는 **러너가 이미 끝냈다.**

## 핵심 규칙
1. **한 건만.** 넘겨받은 task 한 건만 다룬다. 시작할 때 그 task가 `reviewing`인지 확인하고, 아니면 아무것도 쓰지 않고 멈춘다.
2. **신선도 확인(읽기 전용).** 판정 전에 준비물이 아직 유효한지 직접 본다 — PR이면 열림 여부·head 커밋·CI·충돌·베이스 이동·diff가 `plan.steps`와 맞는지, 직접 액션이면 `preparation.notes`·`plan.executionGuide`가 실행 가능할 만큼 구체적인지.
3. **판정 기준.** 계획이 `stateSummary.gap`을 실제로 좁히고 범위를 넘지 않는가, 준비물이 유효한가, 위험도에 맞는 검증 방법과 롤백이 있는가, 되돌릴 수 없는 작업에 안전장치가 있는가. 하나라도 못 채우거나 확신이 없으면 거부한다 — 불확실성 자체가 거부 사유다.
4. **사람 승인 요구.** 승인으로 결론 낸 뒤에만 본다. 대상 레포 기본 브랜치가 머지에 사람 승인용 required status를 요구하는데 그 status가 PR head에 `success`로 없으면, 거부하지 말고 승인하면서 `review.manualApproval`(`sha`=확인한 PR head, `context`)을 남긴다. 그 status를 스스로 붙이지 않는다.
5. **기록.** 마지막 attempts 항목에만 `review`(`status`·`reviewedAt`·`reason`, 거부면 `comment`)를 채운다. 이전 항목과 마지막 항목의 `plan`·`preparation`, 그 task의 다른 필드, 다른 task·모델 파일은 그대로 둔다.
6. **전이 — lock을 반드시 놓는다.** `reviewing → approved`(승인) | `review_rejected`(거부) | `cancelled`(이 스킬의 거부가 연속 3회째). `reviewing`으로 남기지 않는다. 판정 없이 중단해야 하면 `planned`로 되돌린다.
7. **검증.** 쓰기 전에 레코드를 `schemas/reconciliation-task.schema.json`으로 검증한다(python `jsonschema`). 통과하지 않으면 쓰지 않는다.
8. **커밋·push.** 메시지는 `review(<toBeModelId>/<taskId>): <approved|rejected|...>`. `git pull --rebase` 후 push하고, 다른 커밋 때문에 거절되면 `pull --rebase` 후 다시 push한다.
9. **실행 금지.** PR 머지·코멘트·리뷰·브랜치 갱신, 배포, 클러스터 변경을 하지 않는다. 실행은 다음 단계(executor) 몫이다.

## 도구
MCP 서버 `k3s`의 `github_app_installation_token`(대상 레포 읽기 전용 토큰)과 GitHub REST API.
