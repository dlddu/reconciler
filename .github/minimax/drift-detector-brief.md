# 메인 지침 — 무엇을 해야 하는가

너는 `reconciler-drift-detector` 스킬을 새로 작성한다. 완성본 예시는 없다 — 아래 지침과 레포를 직접 읽고 설계하라.
이 메인 지침은 스킬이 반드시 갖춰야 할 핵심 규칙이다. 뒤따르는 **서브 지침**은 결과물의 품질을 위한 보조 규칙(어떻게 할지, 무엇을 하지 말지)이다. 둘이 어긋나면 메인 지침이 우선한다.

## 산출물
- `{{SKILL_DIR}}/SKILL.md` 하나(필요하면 같은 폴더 `scripts/`에 보조 스크립트). 다른 곳은 고치지 않는다.
- YAML frontmatter: `name: reconciler-drift-detector`, `description`(언제 쓰는지, 1024자 이하).
- 본문은 한국어, 다른 에이전트가 무인으로 따라 할 수 있는 단계별 절차.

## 먼저 읽을 것 (`{{REPO_DIR}}`, reconciler 체크아웃)
- `README.md` — 엔티티와 상태 흐름, 특히 「점유는 러너가 한다」 절
- `schemas/to-be-model.schema.json`, `schemas/reconciliation-task.schema.json` — 필드 계약의 유일한 출처
- `.github/scripts/claim_drift_target.py` 머리말 — 러너가 이미 끝낸 대상 선정·점유가 무엇을 기록하는지
- `data/` 의 실제 레코드 몇 개 — 기록 형태 감 잡기

## 스킬이 할 일
감지 단계의 **판정**: 러너가 점유해 둔 task 한 건에 대해 as-is/to-be의 실제 상태를 관측하고, "차이가 유의미한가, 지금 작업이 필요한가"를 근거와 함께 판정해 그 task에 기록한다. 고치거나 계획하지 않는다.

입력: 러너가 프롬프트로 체크아웃 경로, 점유된 `task_id`·`model_id`, 점유 사유(`claim_reason`), 점유 커밋을 넘긴다. 대상 선정과 점유(task 생성 또는 재진입 표시 + 모델 기준선 갱신, 커밋·push)는 **러너가 이미 끝냈다.**

## 핵심 규칙
1. **한 건만.** 넘겨받은 task 한 건만 다룬다. 시작할 때 그 task가 `assessing`인지 확인하고, 아니면 아무것도 쓰지 않고 멈춘다.
2. **점유 기록 보존.** 그 task의 `trigger`·`createdAt`과 `data/to-be-models.json`(기준선·수동 요청 필드 포함)은 그대로 둔다. 다른 task·다른 모델 파일도 그대로 둔다. 새 task를 만들지 않는다.
3. **관측.** 모델의 `definition`과 dataSource가 가리키는 실제 대상을 열어 as-is/to-be 상태를 확인한다. 수동 트리거 task면 `trigger.reason`이 가리키는 지점을 실제로 확인한다.
4. **기록.** `stateSummary`(asIs/toBe/gap)에 관측 사실을, `assessment.reason`에 판정 근거를 적는다.
5. **판정.** 현재 상태를 `definition` 기준에 비춰 셋 중 하나로 끝낸다. 기준은 `definition` **전체**다 — 목표 문장, 허용·불허 조건, 예외의 자격 요건, 충돌 시 기본 방향까지. 형식 불변식이나 대상 레포 게이트가 통과해도 다른 규칙을 어기면 gap이다.
   - `action_required` — 기준에 해당하는 gap이 남아 있고, 그 gap을 맡은 열린 형제 task가 없다. 이번 변화가 일부를 해소했어도 gap이 남았으면 여기다(실행 단계의 부분 슬라이스 → 재감지 → 후속 판정이 정상 흐름이다).
   - `no_action_needed` — 남은 gap이 없거나, 남은 gap을 이미 열린 형제 task가 맡고 있다.
   - `assessing` 유지 + `assessment.recheckAfter` — 롤아웃·머지 대기처럼 자동 해소될 가능성이 있다. `recheckAfter`는 시간대 있는 **미래** 시각이다.
6. **검증.** 쓰기 전에 레코드를 `schemas/reconciliation-task.schema.json`으로 검증한다(python `jsonschema`). 통과하지 않으면 쓰지 않는다.
7. **커밋.** 메시지는 `detect(<toBeModelId>/<taskId>): <요약>`, 단계마다 개별 커밋(상태 요약 → 판정).
8. **push.** `git pull --rebase` 후 push한다. 다른 모델의 커밋이 먼저 들어와 거절되면 `pull --rebase` 후 다시 push한다.

## 도구
MCP 서버 `k3s`의 `github_app_installation_token`(대상 레포 읽기, contents:read로 좁힌다), `resource_list`/`resource_get`(쿠버네티스 관측).
