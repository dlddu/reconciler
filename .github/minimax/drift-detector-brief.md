너는 `reconciler-drift-detector` 스킬을 새로 작성한다. 완성본 예시는 없다 — 아래 지침과 레포를 직접 읽고 설계하라.

## 산출물
- `{{SKILL_DIR}}/SKILL.md` 하나(필요하면 같은 폴더 `scripts/`에 보조 스크립트). 다른 곳은 고치지 않는다.
- YAML frontmatter: `name: reconciler-drift-detector`, `description`(언제 쓰는지, 1024자 이하).
- 본문은 한국어, 다른 에이전트가 무인으로 따라 할 수 있는 단계별 절차. 군더더기 없이.

## 먼저 읽을 것 (`{{REPO_DIR}}`, reconciler 체크아웃)
- `README.md` — 엔티티와 상태 흐름, 특히 「점유는 러너가 한다」 절
- `schemas/to-be-model.schema.json`, `schemas/reconciliation-task.schema.json` — 필드 계약의 유일한 출처
- `.github/scripts/claim_drift_target.py` 머리말 — 러너가 이미 끝낸 대상 선정·점유가 무엇을 기록하는지
- `data/` 의 실제 레코드 몇 개 — 기록 형태 감 잡기

## 스킬이 할 일
감지 단계의 **판정**: 러너가 점유해 둔 task 한 건에 대해 as-is/to-be의 실제 상태를 관측하고, "차이가 유의미한가, 지금 작업이 필요한가"를 근거와 함께 판정해 그 task에 기록한다. 고치거나 계획하지 않는다.

입력: 러너가 프롬프트로 체크아웃 경로, 점유된 `task_id`·`model_id`, 점유 사유(`claim_reason`), 점유 커밋, 드라이런 여부를 넘긴다. 대상 선정과 점유(task 생성 또는 재진입 표시 + 모델 기준선 갱신, 커밋·push)는 **러너가 이미 끝냈다.** 스킬은 대상을 고르지도, 점유하지도 않는다.

지켜야 할 계약:
1. 넘겨받은 task 한 건만 다룬다. 시작할 때 그 task가 `assessing`인지 확인하고, 아니면 아무것도 쓰지 않고 멈춘다.
2. 점유 기록은 건드리지 않는다: 그 task의 `trigger`·`createdAt`, 그리고 `data/to-be-models.json`(기준선·수동 요청 필드 포함)은 수정하지 않는다. 다른 task·다른 모델 파일도 건드리지 않는다. 새 task를 만들지 않는다.
3. 상태 흐름: `assessing` → `no_action_needed` | `action_required`, 또는 `assessing` + `assessment.recheckAfter`(자동 해소 가능성 있을 때, 시각 필수).
4. `stateSummary`(asIs/toBe/gap)는 버전 문자열이 아니라 실제 관측 사실로. `assessment.reason`에 판정 근거. 수동 트리거 task면 `trigger.reason`이 가리키는 지점을 실제로 확인한다.
5. 스키마 파일은 절대 수정하지 않는다. 쓰기 전 레코드를 스키마로 검증한다(python `jsonschema`).
6. 커밋 메시지는 `detect(<toBeModelId>/<taskId>): <요약>`, 단계마다 개별 커밋(상태 요약 → 판정).
7. push는 `git pull --rebase` 후 한다. 다른 모델의 커밋이 먼저 들어와 거절되면 `pull --rebase` 후 다시 push한다(이 task 파일은 점유한 이 실행만 쓰므로 충돌하지 않는다). 강제 push 금지.
8. 드라이런(`RECONCILER_DRY_RUN=1`)이면 커밋은 하되 push는 건너뛰고 성공으로 간주한다.

도구: MCP 서버 `k3s`의 `github_app_installation_token`(대상 레포 읽기용, 권한은 contents:read로 좁힐 것), `resource_list`/`resource_get`(쿠버네티스 관측). 토큰 값은 echo·로그·커밋·task 기록에 절대 남기지 않는다.

다 쓰면 SKILL.md가 위 계약을 빠짐없이 다루는지 스스로 점검하고 끝내라.
