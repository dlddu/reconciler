너는 `reconciler-drift-detector` 스킬을 새로 작성한다. 완성본 예시는 없다 — 아래 지침과 레포를 직접 읽고 설계하라.

## 산출물
- `{{SKILL_DIR}}/SKILL.md` 하나(필요하면 같은 폴더 `scripts/`에 보조 스크립트). 다른 곳은 고치지 않는다.
- YAML frontmatter: `name: reconciler-drift-detector`, `description`(언제 쓰는지, 1024자 이하).
- 본문은 한국어, 다른 에이전트가 무인으로 따라 할 수 있는 단계별 절차. 군더더기 없이.

## 먼저 읽을 것 (`{{REPO_DIR}}`, reconciler 체크아웃)
- `README.md` — 엔티티와 상태 흐름
- `schemas/to-be-model.schema.json`, `schemas/reconciliation-task.schema.json` — 필드 계약의 유일한 출처
- `.github/scripts/select_drift_target.py` 머리말 — 대상 선정 규칙(러너가 이미 수행)
- `data/` 의 실제 레코드 몇 개 — 기록 형태 감 잡기

## 스킬이 할 일
감지 단계: as-is/to-be의 실제 상태를 관측해 "차이가 유의미한가, 지금 작업이 필요한가"를 근거와 함께 판정해 task에 기록한다. 고치거나 계획하지 않는다.

입력: 러너가 프롬프트로 체크아웃 경로, 선정된 대상(`target_id`, `target_kind`, `model_id`, `reason`), 드라이런 여부를 넘긴다.

지켜야 할 계약:
1. 한 번에 한 건만 점유한다. 다른 모델은 건드리지 않는다.
2. 점유는 compare-and-set: 최신화 → 전제(관측 버전/수동 요청/재확인 시각)가 그대로인지 재확인 → task 생성(또는 재진입 표시)과 모델 갱신을 **한 커밋**으로 → 즉시 push. 전제가 바뀌었으면 물러난다.
   **점유가 먼저다.** 점유 커밋 전에 하는 일은 레코드 읽기와 `versionScript` 버전 계산(점유 커밋에 적을 값)뿐이다. 대상 레포의 diff·파일 내용 읽기, 하네스·테스트 실행, 쿠버네티스 관측, 판정은 전부 점유 push가 성공한 **뒤에** 한다(드라이런이면 점유 커밋 뒤). 다른 워커가 같은 대상을 중복으로 판정하지 않게 하기 위해서다. 절차 순서를 이대로 적어라: 버전 계산 → 점유 → 수집 → 판정.
3. 상태 흐름: `assessing` → `no_action_needed` | `action_required`, 또는 `assessing` + `assessment.recheckAfter`(자동 해소 가능성 있을 때, 시각 필수).
4. `stateSummary`(asIs/toBe/gap)는 버전 문자열이 아니라 실제 관측 사실로. `assessment.reason`에 판정 근거.
5. 수동 트리거면 모델의 요청 사유를 task로 그대로 옮기고 요청 필드를 짝으로 지운다.
6. 스키마 파일은 절대 수정하지 않는다. 쓰기 전 레코드를 스키마로 검증한다(python `jsonschema`).
7. 커밋 메시지는 `detect(<toBeModelId>/<taskId>): <요약>`, 단계마다 개별 커밋.
8. 드라이런(`RECONCILER_DRY_RUN=1`)이면 커밋은 하되 push는 건너뛰고 성공으로 간주한다.

도구: MCP 서버 `k3s`의 `github_app_installation_token`(대상 레포 읽기용, 권한은 contents:read로 좁힐 것), `resource_list`/`resource_get`(쿠버네티스 관측). 토큰 값은 echo·로그·커밋·task 기록에 절대 남기지 않는다.

다 쓰면 SKILL.md가 위 계약을 빠짐없이 다루는지 스스로 점검하고 끝내라.
