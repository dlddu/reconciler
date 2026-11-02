# reconciler

as-is 상태와 to-be(목표) 상태를 비교해, 버전이 바뀔 때마다 정합성 작업을 만들어 실행·검증하는 시스템의 스키마와 운영 데이터.

## 엔티티

- **ToBeModel** — 목표 상태의 마크다운 정의와 as-is/to-be 데이터 소스, 소스별 버전 계산 스크립트.
  각 `versionScript`는 stdout 마지막 줄을 버전 문자열로 사용한다
  (github = 커밋 SHA + 하위 디렉터리 tree hash, k8s = deployment revision + 이미지, monitor = 최신 alert event id).
- **ReconciliationTask** — as-is/to-be 버전이 바뀔 때마다 생성되는 작업.
  버전이 그대로여도 모델의 `checkPolicy.manualTriggerRequestedAt`에 시각과 사유
  (`manualTriggerReason`, 짝으로만 존재한다)를 적으면 사람이 감지를 직접 트리거할 수 있고,
  그렇게 생긴 작업은 `trigger.source: "manual"`과 옮겨 적힌 `trigger.reason`으로 남는다.
  요약 → 판단 → 계획 → (사용자 검토) → 실행 → 검증 순으로 필드가 채워진다.

## 구조

```
schemas/
  to-be-model.schema.json           # ToBeModel JSON 스키마 (draft 2020-12)
  reconciliation-task.schema.json   # ReconciliationTask JSON 스키마 (draft 2020-12)
templates/                          # 반복 등록되는 모델 유형의 표준 템플릿
  README.md                         # 슬롯 규약·인스턴스화 절차
  docs-impl.tbm.md                  # 제품 문서 ↔ 구현 정합성
  scenario-e2e.tbm.md               # 테스트 시나리오 ↔ E2E 1:1 정합성
  e2e-mock-policy.tbm.md            # E2E 모킹 최소화 (정책 ↔ 실제 모킹 지점)
  mockup-render.tbm.md              # 목업 ↔ 구현 렌더링 정합성
  journey-mockup.tbm.md             # 사용자 여정 ↔ 목업 1:1 정합성
  comment-necessity.tbm.md          # 주석 필요성 (필요 사유 없는 주석 제거)
  pr-manual-approval.tbm.md         # PR 수동 승인 (정책 ↔ 판정기 ↔ ruleset · 케이스 신선도)
  data-model.tbm.md                 # 데이터 모델 (ERD ↔ 스키마 · 쿼리 패턴 ↔ 코드 · 패턴 ↔ 인덱스)
data/                               # 운영 데이터 (스킬이 런타임에 생성·기록, 초기엔 비어 있음)
  to-be-models.json                 # ToBeModel (배열)
  reconciliation-tasks/             # task: to-be 모델(toBeModelId)별로 파일 분리
    <toBeModelId>.json
index.html                          # data/·templates/ 브라우징용 정적 웹페이지 (GitHub Pages)
tests/                              # index.html 동작 테스트 (node --test), 워크플로 선정 스크립트 테스트 (python3 -m unittest)
.github/workflows/                  # 단계 스킬별 workflow_dispatch 워크플로
.github/scripts/                    # 워크플로 보조 스크립트 (select_drift_target.py / select_plan_target.py / select_review_target.py /
                                    #   select_execute_target.py: 감지·계획·리뷰·실행 대상 선정,
                                    #   claim_drift_target.py / claim_plan_target.py / claim_review_target.py: 선정 + 점유(compare-and-set 커밋) — MiniMax 감지·계획·리뷰,
                                    #   mcp_oidc_proxy.py·mcp_call.py: homelab-k3s-mcp OIDC 연결(샌드박스 모드: GitHub 도구를 대역으로),
                                    #   github_stub.py·github_sandbox.py·github_log.py: 스킬 빌드 test의 GitHub 샌드박스(대역·준비·기록 판정),
                                    #   validate_generated_skill.py(--profile drift-detector|work-planner|work-review|work-executor): 생성 스킬 정적 검증,
                                    #   check_detector_result.py / check_planner_result.py / check_review_result.py / check_executor_result.py: 실행 결과 점검,
                                    #   replay_review_task.py: 리뷰 스킬 빌드 test의 샌드박스 replay 픽스처,
                                    #   executor_fixture.py: 실행 스킬 빌드 test의 격리 무대)
.github/actions/setup-mcode/        # MiniMax Code(mcode) 설치 + subscription key 설정 composite action
.github/actions/github-sandbox/     # 스킬 빌드 test용 GitHub 샌드박스 올리기(up)·내리기(down) composite action
.github/minimax/                    # mcode에 주는 간결한 생성 지침(brief), 테스트·운영 실행 프롬프트
.nojekyll                           # Pages가 data/*.json을 그대로 서빙하도록 Jekyll 우회
```

## 감지 스킬 MiniMax 파이프라인

감지는 MiniMax Code(`mcode exec`)로 돈다. 워크플로는 둘로 나뉜다 — **스킬 생성은 자동화 대상이 아니다.**

| 워크플로 | 트리거 | 하는 일 |
| --- | --- | --- |
| `reconciler-drift-detector.yml` (운영 감지) | 수동, 스케줄(매시 17분 UTC) | 러너가 대상을 고르고 **점유**한 뒤, plugin-marketplace의 고정 스킬(`plugins/reconciler-data-plane`, MiniMax 플러그인 형식)을 mcode 로컬 플러그인으로 설치해 그 task 한 건을 판정한다. 결과 점검기로 계약을 확인하고 `drift-detector-result` 아티팩트를 남긴다. 점유·판정 커밋은 기본 브랜치에 push된다. |
| `reconciler-drift-detector-skill-build.yml` (스킬 빌드) | 수동만 | 지침이나 계약을 바꿀 때 사람이 돌린다. 아래 generate → validate → test를 통과한 생성본을 plugin-marketplace에 PR로 올리면, 운영 감지는 그 다음 실행부터 새 스킬을 쓴다(`plugin_ref` 입력으로 브랜치·SHA를 지정할 수 있다 — 그 실행도 실제 기록을 남긴다). |

스킬 빌드의 job:

| job | 하는 일 | 아티팩트 |
| --- | --- | --- |
| generate | 지침만 주고 — 메인 `.github/minimax/drift-detector-brief.md`(핵심 규칙: 무엇을 해야 하나) + 서브 `drift-detector-brief-sub.md`(품질 보조 규칙: 어떻게, 무엇을 하지 말 것)를 이어 한 프롬프트로 — mcode가 레포(README·스키마·점유 스크립트·데이터)를 직접 읽어 `SKILL.md`를 쓴다. 기존 스킬 본문은 모델에 주지 않는다. | `drift-detector-skill` (skill/, 대화 기록) |
| validate | 형식·계약 커버리지·금지 패턴·보조 스크립트 문법을 정적 검증한다. | `drift-detector-validation` |
| test | 생성본을 운영 감지와 같은 흐름(러너 점유 → 스킬 판정 → 결과 점검기)으로 **샌드박스** 위에서 돌린다 — reconciler는 샌드박스 원격, 대상 레포는 GitHub 샌드박스(아래 「GitHub 샌드박스」). 운영과 다른 점은 스킬 출처(이 빌드의 생성본)와 쓰기가 닿는 곳뿐이고, 점검기는 대역 기록으로 "대상 레포 쓰기 0건"도 본다. 대상은 입력 `target_id`·`reason`으로 지목하거나 자동 선정. | `drift-detector-test-result` (claim·결과 패치, 점검 보고, 대화 기록, `github-sandbox/`) |

**드라이런은 없다 — 대신 닿는 곳을 바꾼다.** 스킬 안에 드라이런 분기를 두지 않는다(검증기가 생성본의 드라이런 분기를 실패시킨다).
스킬 빌드의 test는 생성본을 운영과 같은 코드 경로로 **실제로** 돌리고, 계약 위반은 운영과 같은 결과 점검기가 잡는다. 다만 그
쓰기가 닿는 곳이 운영이 아니다: reconciler는 러너 로컬 bare 레포(샌드박스 원격), 대상 레포·GitHub API는 러너 안의 GitHub 대역
(아래 「GitHub 샌드박스」)이다. 스킬은 자기가 test 중인지 모른다. 서버 `MCP_GITHUB_OIDC_RULES`에 스킬 빌드 워크플로 파일의 규칙도
있어야 test가 돈다(러너가 미러링·읽기 중계에 쓰는 **읽기** 토큰만 — 스킬의 토큰 요청은 샌드박스 프록시가 대역에서 처리한다).

- **MiniMax 인증**: environment `llm-minimax`의 secret `MINIMAX_SUBSCRIPTION_KEY`(Token Plan subscription key)를
  `mcode provider set-minimax-key`로 job 전용 데이터 디렉터리에 넣는다. 텔레메트리와 데이터 기여는 끈다.
  레포 secret에는 두지 않는다(아래 「모델 키 격리」).
- **homelab-k3s-mcp 연결**: GitHub Actions OIDC. OIDC 토큰이 약 5분짜리라 `.mcp.json`에 박지 않고, 로컬 프록시
  (`mcp_oidc_proxy.py`, 127.0.0.1)가 요청마다 토큰을 붙이고 만료 전에 갱신한다. mcode 환경에서는 OIDC 요청
  변수와 대상 레포 토큰을 뺀다. 서버 `MCP_GITHUB_OIDC_RULES`에 운영 감지 워크플로 파일의 규칙이 있어야 하고
  (`github_app_installation_token` 필수 — 운영 감지는 이것으로 private plugin-marketplace도 읽는다,
  `resource_list`·`resource_get`·`api_resources`·`ping` 권장), audience는
  `vars.HOMELAB_K3S_MCP_AUDIENCE`(기본 `homelab-k3s-mcp`), URL은 `vars.HOMELAB_K3S_MCP_URL`로 바꿀 수 있다.
- **테스트**: `python3 -m unittest discover -s tests`가 선정·점유(경쟁 재현 포함)·프록시·점검기·검증기를
  네트워크 없이 검사한다.

- **스케줄 (켬, 2026-11-02)**: 운영 감지 워크플로가 매시 17분(UTC)에 돈다. 실행이 겹칠 수 있고(직렬화 없음) 같은 대상은
  점유 CAS가 막는다. `circuit-breaker` job이 함께 켜져 있어 스케줄 실행이 `FAILURE_THRESHOLD`(3)번 연속 실패하면
  `gh workflow disable`로 이 워크플로를 끄고 PocketAide로 알린다(GitHub는 실패 횟수로 워크플로를 끄지 않는다). 끌 때는
  두 블록을 함께 주석 처리한다. 켜기 전 시범 운영(수동 44회)에서 확인한 경로: 버전 변화 점유, 수동 트리거, 동시 실행의 점유
  경쟁, 판정 없이 끝난 점유의 재확인 유예와 재확인 만료 이어받기, 대상 없음.

### 점유는 러너가 한다 (MiniMax 감지)

Claude Code용 `reconciler-drift-detector` 스킬은 대상 선정(Step 0)과 점유(Step 1)를 스킬 안에서 한다.
MiniMax Code로 돌리는 감지는 이 둘을 **러너의 결정적 스크립트**(`claim_drift_target.py`)로 옮기고, 스킬은
점유가 끝난 task 한 건을 받아 수집·판정만 한다.

**근거 — 점유를 스킬 밖으로 뺄 수 있는 이유**

1. MiniMax Code는 앱(사람이 대화하는 세션)에서 실행하지 않는다. 항상 `mcode exec`를 부르는 러너
   (지금은 이 GitHub Actions 워크플로)가 있다.
2. 따라서 **target id를 정하는 컴포넌트가 항상 존재한다**고 가정할 수 있다. 사람이 스킬을 직접 불러
   "이 모델 봐줘"라고 하는 경로 — Claude Code 스킬이 선정·점유를 스스로 해야 했던 이유 — 가 MiniMax 쪽에는 없다.
   사람이 대상을 지목하고 싶으면 워크플로 입력(`target_id`, `reason`)으로 러너에 지목한다.
3. 대상을 정하는 컴포넌트가 늘 있으므로, 그 컴포넌트가 **점유까지 맡을 수 있다.** 점유는 판단이 필요 없는
   기계적 compare-and-set(전제 재확인 → task 생성/재진입 표시 + 모델 기준선 갱신을 한 커밋 → 즉시 push)이라
   모델보다 스크립트가 정확하다.

**얻는 것**

- **점유 순서가 구조적으로 보장된다.** 모델이 실행되기 전에 점유가 끝나 있으므로 "점유 전에 수집하지 말 것"을
  지침과 사후 점검으로 강제할 필요가 없다.
- **경쟁 처리가 한곳에 있다.** 다른 워커가 같은 변화를 먼저 집었으면(전제 불일치) 그 모델을 빼고 다음 후보를
  점유한다(지목 실행이면 종료). 무관한 커밋 때문에 push가 거절되면 새 상태에서 전제를 다시 확인해 재시도한다 —
  경쟁 패배와 단순 push 거절을 구분한다. 단위 테스트가 두 경우를 bare origin으로 재현한다.
- **결과가 출력으로 남는다.** `claimed`·`task_id`·`claim_reason`·`claim_commit`·`lost_count`를 GITHUB_OUTPUT으로 내보내,
  "점유할 대상 없음 / 경쟁에서 짐 / 점유 후 판정"이 워크플로에서 구분된다.

**스킬에 남는 계약**: 넘겨받은 task가 `assessing`인지 확인 → 수집·판정 → `stateSummary`·`assessment`·`status` 기록
(`detect(<tbm>/<rct>): …` 커밋) → `pull --rebase` 후 push. 점유 기록(그 task의 `trigger`·`createdAt`,
`data/to-be-models.json`)과 다른 task·모델은 건드리지 않는다. 운영 감지의 결과 점검기는 점유 커밋 이후 변경이 그 task 파일
하나뿐인지로 이를 확인한다.

**판정 없이 끝난 점유**: 스킬이 판정을 기록하기 전에 끝나면(mcode 타임아웃·오류, 플러그인 준비 실패, 취소) task는
`recheckAfter` 없는 `assessing` — 선정이 「다른 워커가 점유 중」으로 보고 아무도 이어받지 않는 lock — 으로 남는다.
워크플로의 `Release unfinished claim` 스텝(`release_unfinished_claim.py`)이 점유한 실행마다 원격에서 그 task를 다시
읽어, 여전히 그런 상태일 때만 재확인 유예(`assessment.recheckAfter` = 지금 + 30분, 커밋 `detect(<tbm>/<rct>): park
unfinished`)로 돌린다. 시각이 지나면 다음 감지 실행이 「재확인 만료」로 이어받는다. 판정이 있거나 이미 유예 중이면 손대지
않고, push가 거절되면 원격 상태에서 조건부터 다시 본다. 실행 자체는 결과 점검 실패로 그대로 실패한다.

**범위**: 이 분리는 MiniMax 감지 경로에만 해당한다. Claude Code 플러그인(`reconciler-data-plane`)의 감지 스킬은
사람 세션에서 직접 불릴 수 있으므로 지금처럼 선정·점유를 스스로 한다. 두 경로가 같은 레포에 쓰므로 점유 기록의
형태(커밋 제목, `trigger`, 기준선 갱신, 수동 요청 필드를 짝으로 `null`)는 같게 유지한다.

## 계획 스킬 MiniMax 파이프라인

계획도 감지와 같은 구조로 MiniMax Code에서 돈다. 점유를 러너가 하는 근거도 위 「점유는 러너가 한다」와 같다.

| 워크플로 | 트리거 | 하는 일 |
| --- | --- | --- |
| `reconciler-work-planner.yml` (운영 계획) | 수동 | 러너가 계획 대상 한 건을 **점유**(`claim_plan_target.py`)한 뒤 plugin-marketplace의 고정 스킬(`plugins/reconciler-data-plane`의 `reconciler-work-planner`)로 계획·준비(대상 레포 PR)·실행 지침을 쓴다. 결과 점검기(`check_planner_result.py`)로 계약을 확인하고 `work-planner-result` 아티팩트를 남긴다. 대상이 없으면 MCP·mcode를 띄우지 않는다. |
| `reconciler-work-planner-skill-build.yml` (스킬 빌드) | 수동만 | generate(`.github/minimax/work-planner-brief.md`만 주고 mcode가 레포를 읽어 `SKILL.md`를 쓴다 — 기존 스킬 본문은 주지 않는다) → validate(`validate_generated_skill.py --profile work-planner`) → test(생성본을 운영 계획과 같은 흐름으로 **샌드박스** 위에서 실행 — 점유·계획 커밋은 샌드박스 원격, 대상 레포 브랜치·PR은 GitHub 대역에만 생긴다. 점검기는 대역 기록으로 머지 시도 0건·PR 1개·preparation과 일치·기본 브랜치 직접 push 0건을 본다. 입력 `target_id`로 지목). 아티팩트 `work-planner-skill` · `work-planner-validation` · `work-planner-test-result`. 통과한 생성본을 plugin-marketplace에 PR로 올리면 운영 계획이 그 스킬을 쓴다. |

- **러너 점유**: 계획 대상(`action_required`·`review_rejected`·`failed`, 모델 켜짐) 한 건을 골라 status가 그대로인지
  재확인 → `planning` + `updatedAt` → `plan(<tbm>/<rct>): claim` 커밋 → 즉시 push. 경쟁에서 지면 다음 후보, 무관한
  커밋에 밀린 push는 재확인 후 재시도. `attempts`는 건드리지 않는다. 출력의 `from_status`(점유 전 status)로 스킬이
  재작업 여부를 안다. 선정만 하는 `select_plan_target.py`는 스킬이 직접 점유하는 Claude Code 경로가 쓴다.
- **스킬에 남는 계약**: 넘겨받은 task가 `planning`인지 확인 → `attempts` 끝에 새 항목(재작업이면 `reason`=`from_status`)을
  덧붙여 `plan`·`preparation`·`plan.executionGuide`를 채움 → `planned`. 완주하지 못하면 이번 시도를 남기지 않고
  `from_status`로 되돌린다. 이전 attempts 항목, `trigger`·`createdAt`·`stateSummary`·`assessment`, 다른 task·모델은
  건드리지 않는다. 대상 레포 PR은 머지하지 않는다(실행 단계 몫).
- **결과 점검**: 점유 커밋 이후 그 task 파일만 바뀌었는지, 보존 필드·이전 attempts, 스키마, 종료 상태를 본다.
  `planning`으로 끝나면(풀 수 없는 lock) 오류로 실패한다. 시도 없이 `from_status`로 lock을 푼 것은 계약상 허용이라 경고다.
  대상 레포 PR의 내용(계획과 diff가 맞는지, 관련 없는 변경이 섞였는지)은 리뷰 단계가 본다.
- **서버 OIDC 규칙**: `reconciler-work-planner.yml` 규칙에 `github_app_installation_token`(대상 레포 contents·pull_requests
  쓰기, plugin-marketplace 읽기)이 있어야 하고 `resource_list`·`resource_get`·`api_resources`·`ping`을 권장한다.

## 리뷰 스킬 MiniMax 파이프라인

`reconciler-work-review-skill-build.yml`(수동만)이 리뷰 스킬을 MiniMax Code로 **생성 → 검증 → 테스트**한다. 감지 스킬 빌드와
같은 구조이고, 리뷰는 대상 레포를 읽기만 하는 단계라 샌드박스 test를 더했다. 통과한 생성본(`work-review-build-result`의 `skill/`)을
plugin-marketplace의 `plugins/reconciler-data-plane`에 PR로 올린다(0.5.0~).

| 워크플로 | 트리거 | 하는 일 |
| --- | --- | --- |
| `reconciler-work-review.yml` (운영 리뷰) | 수동 | 러너가 `planned` 한 건을 **점유**(`claim_review_target.py`, `planned → reviewing`)한 뒤 plugin-marketplace의 고정 스킬(`plugins/reconciler-data-plane`의 `reconciler-work-review`)로 승인/거부를 판정한다. 결과 점검기(`check_review_result.py`)로 계약을 확인하고 `work-review-result` 아티팩트를 남긴다. 대상이 없으면 MCP·mcode를 띄우지 않는다. 점유 뒤 스킬을 돌리기 전에 러너가 실패하면(MCP·플러그인·mcode 설치) `--release`로 `planned`로 되돌린다. 점유·판정 커밋은 기본 브랜치에 push된다. |
| `reconciler-work-review-skill-build.yml` (스킬 빌드) | 수동만 | 아래 generate → validate → test → report. |


| job | 하는 일 | 아티팩트 |
| --- | --- | --- |
| generate | 메인 `.github/minimax/work-review-brief.md`(핵심 규칙) + 서브 `work-review-brief-sub.md`(품질 보조 규칙)만 주고, mcode가 레포(README·스키마·`claim_review_target.py`·템플릿·데이터)를 직접 읽어 `SKILL.md`를 쓴다. 기존 스킬 본문은 모델에 주지 않는다. | `work-review-skill` |
| validate | `validate_generated_skill.py --profile work-review` — 형식·계약 커버리지(`reviewing`·`approved`·`review_rejected`·`cancelled`·`manualApproval`·`attempts`·`review(...)` 커밋 등)·금지 패턴(commit status 쓰기·PR 머지 포함)·보조 스크립트 문법. | `work-review-validation` |
| test | 시나리오 matrix — `live`(운영 `planned` 그대로), `replay`(머지·종료된 PR 건을 점유 직전 `planned`로 되돌림), `replay-ci-failure`(열린 PR 건을 되돌려 대역 PR + CI 실패로). 러너 점유(`claim_review_target.py`, `planned → reviewing`) → 생성 스킬 판정(`work-review-run-prompt.md`) → 결과 점검(`check_review_result.py`). | `work-review-test-<시나리오>` |
| report | 위 결과를 하나로 모은다 — `skill/`, `validation/`, `test/<시나리오>/reviewed-task.json`·점검 보고·결과 diff·mcode 최종 보고, `README.md` 요약. | `work-review-build-result` |

**샌드박스 원격 — 드라이런이 아니다.** test job은 reconciler 체크아웃의 `origin`(fetch·push)을 러너 로컬 bare 레포로 바꾼다.
러너 점유와 스킬의 `pull --rebase`·push는 운영과 똑같이 돌고, 닿는 곳만 그 bare 레포다. 스킬에는 드라이런 분기가 없고(검증기가
금지) 자기가 test 중인지 모른다. job 토큰은 `contents: read`라 GitHub에는 어차피 쓸 수 없다. 대상 레포 쪽은 GitHub 샌드박스가 맡는다 —
실제 PR·status·ruleset은 러너의 읽기 토큰으로 중계해 보여 주고, 스킬이 status·머지·코멘트를 시도하면 대역에만 남아 점검기(`--github-log`)가
잡는다. 같은 두 겹(샌드박스 원격 + GitHub 샌드박스)이 대상 레포에 쓰는 계획 단계 test에도 쓰인다.

**replay 시나리오**: 운영 데이터에 `planned`가 늘 있지는 않아서, git 이력의 최근 `review(<tbm>/<rct>): claim` 커밋을 찾아 그 부모의
task 레코드(점유 직전)를 샌드박스에만 되돌려 놓는다(`replay_review_task.py` — 원격이 로컬 경로가 아니면 쓰지 않고 실패). 원래 판정(운영
기록)은 요약에 함께 남는다. 모드마다 시험하는 거부 경로가 다르다.

- `replay`(`--mode merged`): 최근 후보부터 PR을 조회해 **지금 머지·종료된** 건을 우선 고른다. 그 계획은 더 이상 실행할 수 없으므로
  점검기가 `review_rejected | cancelled`를 기대한다 — 신선도 확인을 건너뛰고 기록만 믿는 스킬은 여기서 걸린다. 조회 한도(20건) 안에
  그런 건이 없으면 가장 최근 건을 기대 없이 판정하고 경고한다.
- `replay-ci-failure`(`--mode ci-failure`): **지금 열린** PR 건을 고르고, 그 PR의 head 커밋에 대역 브랜치(`<head>-2`)를 걸어 대역 PR
  (#90001, 실제 PR의 제목·본문)을 시드로 세운다. 되돌린 레코드의 `preparation`과 마지막 시도 안의 옛 PR 링크·번호·브랜치는 대역 PR로
  바꾼다. 대역은 `synthetic-ci: failure`로 올라와 그 head의 CI가 실패로만 보인다(대역 PR head에서는 같은 커밋의 실제 체크 런을 섞지 않는다).
  diff·base·실제 commit status(사람 승인 포함)는 실제 그대로라 CI만 다르다 — CI가 실패한 준비물을 승인하면 점검기가 실패시킨다.
  열린 PR 건이 없으면 fixture가 실패한다.
- **회귀 케이스 고정**(입력 `replay_target` + `replay_expect`): 모드가 기대를 걸지 않는 건(예: PR이 열려 있는데 잘못 승인된 건)은 기대 status를
  직접 지정한다(`--expect`, 쉼표 구분). 예: `replay_target=tbm_pocket-aide-e2e-mock-policy/rct_20261026-0001`, `replay_expect=review_rejected`
  — 계획의 diff 기대값(3파일)과 PR #327 실제 diff(11파일)가 다른데 운영 리뷰가 승인했던 건(run 41304877532, 사람이 3cd59ef에서 철회).
  replay는 그 task의 가장 최근 `review(...): claim` 커밋의 부모 레코드를 되돌리므로, 그 뒤에 붙은 거부 기록과 무관하게 재현된다.

**점검기가 보는 계약**: 점유 이후 그 task 파일 하나·그 task 한 건만 바뀜, `review(<tbm>/<rct>): …` 커밋, `trigger`·`stateSummary`·
`assessment`와 이전 attempts 항목·마지막 항목의 `plan`·`preparation` 보존, 종료 상태 `approved | review_rejected | cancelled`
(`reviewing`이면 풀리지 않은 lock, `planned`면 판정 없는 해제), `review.status`와 status 일치, `reviewedAt`·`reason`(거부면 `comment`),
`manualApproval`은 승인에만, 대화 기록에 대상 레포 쓰기(commit status·머지·코멘트·리뷰) 없음, GitHub 대역 기록에 쓰기 0건.

**MCP 규칙**: 서버 `MCP_GITHUB_OIDC_RULES`에 두 워크플로 파일(운영 리뷰는 plugin-marketplace 읽기도) 각각의 규칙이 있어야 한다 — `github_app_installation_token`(대상 레포
읽기 상한, reconciler 제외), `ping`. 리뷰는 대상 레포에 쓰지 않으므로 write 권한이나 `github_commit_status_create`를 주지 않는다.

## 실행 스킬 MiniMax 파이프라인

`reconciler-work-executor-skill-build.yml`(수동만)이 실행 단계 스킬을 MiniMax Code로 **생성 → 검증 → 테스트**한다.
통과한 생성본(`work-executor-skill` 아티팩트의 `skill/`)을 plugin-marketplace의 `plugins/reconciler-data-plane`에 PR로 올리는
흐름은 감지 스킬과 같다.

| job | 하는 일 | 아티팩트 |
| --- | --- | --- |
| generate | 메인 `.github/minimax/work-executor-brief.md`(핵심 규칙) + 서브 `work-executor-brief-sub.md`(품질 보조 규칙)만 주고, mcode가 레포(README·스키마·진입 게이트 스크립트·데이터)를 직접 읽어 `SKILL.md`를 쓴다. 기존 스킬 본문은 모델에 주지 않는다. | `work-executor-skill` (skill/, 대화 기록) |
| validate | `validate_generated_skill.py --profile work-executor` — 형식·실행 단계 계약 커버리지(`executing`/`verifying`/종료 상태, `execution`·`verification`, `execute(…)` 커밋)·금지 패턴(사람 승인 status 생성, `--admin` 머지, 강제 push 등)·보조 스크립트 문법. | `work-executor-validation` |
| test | 시나리오별로 격리 무대를 만들어(`executor_fixture.py`) 생성본을 운영과 같은 실행 프롬프트(`work-executor-run-prompt.md`)로 돌리고, `check_executor_result.py`가 계약과 시나리오 기대값을 점검한다. | `work-executor-test-<시나리오>` (대화 기록, 점검 보고서, 결과 task·패치) |
| report | 세 단계 결과를 한 보고서로 묶는다. | `work-executor-build-report` (report.md, skill/) |

**테스트는 운영 데이터로 하지 않는다.** 감지와 달리 실행은 PR 머지·클러스터 변경처럼 되돌리기 어려운 일을 하므로, 생성본의
첫 실행을 운영에 맡기지 않고 러너 안의 격리 무대에서 먼저 돌린다. 무대에는 실제 GitHub·MCP·클러스터 자격 증명이 없다. 모든 시나리오에서
GitHub 샌드박스를 올려 두어, 스킬이 GitHub로 무엇을 보내든 러너 안의 대역이 받고 기록하며, `github_log.py --stage execute --expect`가
시나리오의 머지 규칙(`github.merge`: 승인 PR 머지 필수 `required` / 머지 시도조차 금지 `forbidden`)으로 판정한다.

- 대상 레포 = 로컬 bare 저장소(`target.git`, main + 준비 브랜치). reconciler = 로컬 bare 원격 + clone(실제 README·schemas·scripts 복사,
  data/에는 픽스처 모델 2개와 task 3건 — 같은 모델의 지난 `succeeded`, **점유된 `executing`** 한 건, 다른 모델의 `approved` 미끼).
- 점유는 러너 몫이라 `approved → executing`을 `execute(<tbm>/<rct>): claim` 커밋으로 미리 push해 둔다. 이 커밋이 점검 기준이다.
- 시나리오(로컬 대상): `merge`(준비 브랜치 병합 → 검증 통과 → `succeeded`), `broken-premise`(리뷰 뒤 준비 브랜치가 사라짐 → 대상은 그대로, `failed`).
- 시나리오(GitHub 대상 — 운영 실행의 실제 경로): 대상 레포 `fixture/target-app`이 GitHub 샌드박스에 있고 준비는 PR #90001, 리뷰가 사람 승인을
  요구했다(`review.manualApproval`). 실제 ruleset처럼 필수 체크 `ci-success`·`review/manual-approval`과 main 직접 push 금지가 걸려 있고,
  `ci-success`는 대역의 합성 CI, 사람 승인 status는 **리뷰 시점 head에만** 심어 둔다(`seed.json` — 스킬의 쓰기로 세지 않음).
  스킬은 오프라인 샌드박스 MCP(`mcp_oidc_proxy.py --offline`)의 `github_app_installation_token`으로 대역 토큰을 받고, 대상은
  `github.com/fixture/target-app`으로만 보인다(task·모델에 로컬 경로 없음, 버전 스크립트는 체크아웃 기준).
  - `pr-merge`: PR head = `manualApproval.sha`, 필수 체크 모두 success → API로 PR 머지 → `succeeded`(대역 기록: 승인 PR 머지 필수).
  - `pr-head-moved`: 리뷰(승인) 뒤 검토되지 않은 커밋이 PR에 올라와 head ≠ `manualApproval.sha` → 머지를 **시도하지 않고** `failed`,
    대상 refs 불변(대역 기록: 거절된 머지 시도도 오류 — 새 head엔 승인 status가 없어 대역도 실제처럼 거절하지만, 시도 자체가 계약 위반).
- 점검: 커밋 규약(run → verify), 변경이 그 task 파일 하나뿐인지, 판정·계획·리뷰 기록과 이전 attempts 보존, 스키마, lock 해제
  (`succeeded`|`failed`|`cancelled`), execution·verification 일관성(passed ⇔ succeeded, plan에 없는 stepSeq 없음), push 여부, 그리고
  시나리오 기대값(대상 main 내용·refs 불변·이력 재작성 없음·`asIsVersionAfter`).

**스킬에 남는 계약**(브리프의 핵심 규칙): 넘겨받은 task가 `executing`인지 확인 → 마지막 attempt의 `plan.steps`를 `executionGuide`대로
실행해 `execution` 기록(`execute(<tbm>/<rct>): run`) → `verifying` → `asIsVersionAfter`·`checks` 기록 후 `succeeded`|`failed`
(`… : verify`), 전제 붕괴면 `cancelled`|`failed` → 커밋마다 `pull --rebase` 후 push. 대상 선정·진입 게이트(사람 승인 확인 포함)·점유는
러너가 한다 — 운영 실행 워크플로(`reconciler-work-executor.yml`)에 감지의 `claim_drift_target.py`에 해당하는 점유 스크립트를 붙이는
것은 다음 단계다.

## GitHub 샌드박스 (스킬 빌드 test)

스킬 빌드의 test가 대상 레포와 GitHub API에 닿는 곳을 러너 안의 **대역**(test double)으로 바꾼다. 스킬은 평소처럼 MCP로 토큰을 받고,
`git clone`·`push`, REST·GraphQL(`curl`, `gh`, 파이썬 무엇이든)로 PR을 만들고 머지하고 status를 읽는다. 그 요청이 전부 대역에서 끝난다.
`.github/actions/github-sandbox`(composite)가 올리고(`up`) 내린다(`down`).

| 층 | 바꾸는 방법 |
| --- | --- |
| 토큰 (MCP `github_app_installation_token`) | `mcp_oidc_proxy.py` 샌드박스 모드가 이 호출을 실제 MCP로 보내지 않고 대역이 발급한 가짜 토큰을 같은 `.env` 모양으로 돌려준다. `github_commit_status_create`도 대역에 기록만 한다. 그 밖의 도구는 `--sandbox-allow-tools`에 적은 것(관측용 읽기)만 실제 MCP로 보내고 나머지는 막는다(fail-closed). |
| git (`github.com`) | `/etc/hosts`로 `github.com`·`api.github.com`·`raw.githubusercontent.com`을 127.0.0.1로 돌리고 자체 CA를 시스템 신뢰 목록에 넣는다. 대역은 러너가 미리 받아 둔 bare 미러(원격 제거)를 `git http-backend`로 서비스한다 — push는 미러에만 쌓인다. 실제 ruleset(기본 브랜치)은 pre-receive 훅으로 옮겨 직접 push를 실제처럼 거절한다. `github.com/<owner>/reconciler`는 샌드박스 원격으로 이어진다. |
| API (`api.github.com`) | PR 생성·수정·닫기·머지, 코멘트, status, ref를 대역 안에서 처리한다(머지는 미러에서 실제 git 병합, 필수 status가 없으면 실제처럼 405). `gh`가 쓰는 GraphQL은 질의의 선택 집합대로 응답을 깎아 돌려준다. 대역이 모델링하지 않는 **읽기(GET·GraphQL 질의)**만 러너의 읽기 전용 토큰으로 실제 GitHub에 중계한다(read passthrough). **쓰기는 어떤 경우에도 실제 GitHub로 나가지 않는다.** |

- **진짜 토큰은 에이전트에 닿지 않는다.** 러너만 실제 읽기 토큰을 받고(미러·ruleset·읽기 중계), mcode 환경에서는 뺀다. 대역은 그 토큰을
  0600 파일로 받아 읽은 뒤 지운다. 그래서 무엇이 대역을 빠져나가도 실제 GitHub 쓰기는 401로 끝난다.
- **대역은 자기가 발급한 토큰만 인정**하고 실제 서버처럼 레포 범위(밖이면 404)와 권한(부족하면 403)을 지킨다.
- **모든 요청은 `requests.jsonl`로 기록**된다(아티팩트 `github-sandbox/`: 기록·최종 상태·요약). 결과 점검기는 대화 기록의 명령 문자열이 아니라
  대역에 도착한 요청 그 자체로 판정한다(`github_log.py`, 점검기의 `--github-log`):

| 단계 | 대역 기록 규칙 |
| --- | --- |
| 감지·리뷰 | 쓰기 0건(거절된 시도 포함). 쓰기 권한 토큰 요청은 경고. |
| 계획 | 머지 시도 0건, commit status 쓰기 0건, 기본 브랜치 직접·강제 push 0건, 연 PR은 최대 1개이고 `preparation.pullRequestUrl`과 일치(열고 기록하지 않았거나 기록한 PR을 열지 않았으면 오류·경고). planned로 넘겼다면 planned 시각 뒤 대상 레포 쓰기 0건(CI를 볼지는 스킬 판단, CI 실패 판정은 리뷰 몫 — 합성 CI 결론은 사실로만 남긴다). |
| 실행 | 머지는 승인된 task의 그 PR 하나만, commit status 쓰기 0건, 강제 push 0건. 거절된 시도는 경고. |

  대역이 모르는 요청은 501 + `op: unsupported`로 남고 점검기 경고로 보인다 — 대역을 넓혀야 한다는 단서다.
- **시드·오프라인 MCP**(실행 빌드의 격리 무대, 리뷰 빌드 `replay-ci-failure`): 대역은 시작 때 `seed.json`의 브랜치(미러에 있는 커밋에 건다)·
  PR·commit status를 「스킬이 오기 전에 이미 있던」 것으로 심는다(기록 `seed.*`, 쓰기로 세지 않음). 대역 PR head에서는 실제 체크 런을
  중계하지 않으므로, 실제 커밋 위에 세운 대역 PR의 CI 결과는 합성 결과 하나다. OIDC가 없는 job은 `mcp-offline: "true"`로 프록시가 MCP 서버 자체가 되어 GitHub 도구 두 개(대역)와
  `ping`만 노출한다.
- **github.com 공개 자료**: git 밖 GET(릴리스 내려받기·아카이브 — 예: `npm install`의 prebuilt 바이너리)은 자격 증명 없이 실제 github.com에
  물어 그대로 돌려준다(쓰기는 중계하지 않는다).
- **합성 CI**: 대역 PR은 진짜 GitHub가 모르니 Actions CI가 돌지 않는다. 그래서 대역이 **자기가 만든 PR**의 head 커밋마다(새 push 포함)
  성공한 합성 체크 런을 붙인다 — 이름은 실제 ruleset의 필수 체크(예: `ci-success`), 필수 체크가 없으면 `ci`. 스킬이 보는 CI 결과(REST
  check-runs, `gh pr checks`·`statusCheckRollup`)와 대역의 머지 게이트가 이것으로 충족된다. **사람 승인 status(`review/` 접두어)는 절대
  합성하지 않는다** — 사람 승인 게이트는 샌드박스에서도 실제처럼 막힌다. 합성 런은 앱 `reconciler-sandbox`, 제목 "synthetic success — CI was
  not run"으로 표시되고 기록(`op: ci.synthetic`)·요약에 남는다. 실제 PR(읽기 중계)에는 붙이지 않는다.
  결론은 액션 입력 `synthetic-ci`로 고른다 — `success`(기본) · `failure`(매 head 실패: 고칠 수 없는 CI 실패 경로) ·
  `fail-first`(PR의 첫 head만 실패, 이후 push는 성공: 고칠 수 있는 실패) · `off`. 계획 스킬 빌드는 입력 `synthetic_ci`로 넘긴다.
  실패 런만은 합성임을 드러내지 않는다 — 앱 `github-actions`, 제목 「<체크> failed」, 요약 「Process completed with exit code 1.」로
  실제 Actions 실패처럼 보이고, 합성 여부는 기록(`ci.synthetic`, 결론 포함)에만 남는다. 「합성이라 무시해도 된다」는 판단을 막아야
  실패를 보고 스킬이 어떻게 대응하는지(범위 안에서 고치는지, 꼼수로 게이트를 넘기지 않는지, planned 뒤 PR을 다시 고치지 않는지)를 볼 수 있다.
- **한계**: 대역은 GitHub의 일부만 흉내 낸다(비동기 mergeable 계산, ruleset의 bypass·리뷰 요구는 없다). 웹훅·Actions 트리거는 없다(CI는 위
  합성 결과뿐). PR 번호는 실제와 겹치지 않게 90001부터다. 클러스터 쓰기는 MCP 허용 목록으로 막을 뿐 흉내 내지 않는다.
- **로컬로 돌려 보기**: `python3 -m unittest tests.test_github_stub tests.test_github_log` — 대역을 평문 HTTP로 띄워 실제 `git`으로
  clone·push하고 REST·GraphQL로 PR을 만들고 머지한다(네트워크 없이).

## 모델 키 격리

워크플로마다 쓰는 모델(MiniMax, 추후 GLM·Claude Code)이 다를 수 있다. 각 job의 에이전트는 **자기 모델 키만** 볼 수
있어야 하고, 다른 제공자의 키에는 닿지 않아야 한다. 같은 job 안에서 에이전트가 자기 키를 읽는 것은 막지 않는다
(`--permission full`이면 설정 파일을 읽을 수 있다).

- **제공자별 environment**: 모델 키는 레포 secret이 아니라 environment secret으로만 둔다 — `llm-minimax`
  (`MINIMAX_SUBSCRIPTION_KEY`), `llm-glm`(`GLM_API_KEY`), `llm-claude`(`ANTHROPIC_API_KEY` 또는
  `CLAUDE_CODE_OAUTH_TOKEN`). 키가 필요한 job만 `environment:`로 그 environment를 선언한다. 레포 secret은 environment가
  없는 job에도 넘어가니, 같은 이름의 레포 secret은 지운다.
- **한 job엔 한 제공자**: 두 모델을 쓰는 워크플로는 job을 나눈다. job마다 별도 VM이라 파일·프로세스로도 키가 섞이지 않는다.
- **배포 브랜치**: `llm-minimax`는 Deployment branches를 `main`으로 묶지 않는다 — 스킬 빌드 같은 수동 워크플로를 머지 전
  브랜치에서 `workflow_dispatch --ref <브랜치>`로 돌려 보기 위해서다(dispatch하려면 같은 경로의 워크플로 파일이 기본
  브랜치에 있어야 한다). 그래서 그 environment를 선언한 job이면 어느 브랜치에서든 키를 받는다. 키를 꺼내는 경로는 결국
  워크플로를 새로 쓰는 것이므로, 막는 선은 아래 App 토큰 상한(에이전트가 이 레포의 워크플로를 push하지 못하게)이다.
- **정적 검사**: `workflow-lint.yml`이 `.github/` 변경마다 `check_llm_key_scope.py`를 돌려, environment 밖의 키 참조,
  한 job의 두 제공자 키, 최상위 `env:`의 키, `secrets: inherit`·`toJSON(secrets)`·`secrets[...]`를 막는다.
  새 제공자는 스크립트의 `PROVIDERS`에 먼저 등록한다. 대화 기록 가림(`redact_secrets.py`)은 MiniMax·Anthropic·GLM 키
  모양을 안다.

에이전트가 키를 꺼내는 실제 경로는 YAML이 아니라 **워크플로를 새로 쓰는 것**이다. `GITHUB_TOKEN`은 `contents: write`여도
`.github/workflows`를 바꿀 수 없다. 하지만 에이전트가 MCP `github_app_installation_token`으로 받는 App 토큰은, App 설치에
이 레포와 Workflows 권한이 들어 있으면 워크플로를 push할 수 있다. 그래서 homelab-k3s-mcp OIDC 규칙의 `githubToken`
상한으로 토큰 범위를 고정한다(서버의 규칙별 상한 기능이 필요). 상한이 걸린 호출은 인자를 생략하면 상한을 받고, 상한 밖
레포·권한을 요청하면 거부된다. 상한에는 이 레포를 넣지 않는다. 대상 레포의 워크플로를 고쳐야 하는 단계는 `workflows: write`를
받아도 된다. 다만 서버가 **호출한 워크플로 자신의 레포(reconciler)가 포함되는 토큰에는 workflows 권한을 주지 않는다**.
`permissions`를 생략하면 App의 모든 권한(workflows 포함)이 되므로, 그때는 `repositories`를 명시하고 이 레포를 빼야 발급된다.

규칙의 형태를 보여 주는 **예시**다. 레포 이름과 권한은 자리표시이고, 실제 운영 값은 이 README가 아니라 SSM
`/flux-cd/homelab-k3s-mcp/github-oidc`의 `MCP_GITHUB_OIDC_RULES`가 기준이다.

```json
{"repository": "dlddu/reconciler", "workflow": ".github/workflows/<워크플로>.yml",
 "tools": ["github_app_installation_token", "ping"],
 "githubToken": {"repositories": ["<대상 레포 A>", "<대상 레포 B>"],
                 "permissions": {"contents": "read", "metadata": "read"}}}
```

상한을 정할 때의 원칙: 레포는 그 단계가 실제로 다루는 대상 레포(`data/to-be-models.json`, 꺼진 모델 포함)와 필요한
보조 레포만 넣고, 새 대상 레포를 등록하면 상한에도 추가한다. 권한은 감지처럼 관측만 하는 단계엔 읽기만 준다. 계획·실행
단계가 대상 레포에 PR을 만들고 머지하게 되면 `contents`·`pull_requests`의 `write`를, 대상 레포 워크플로를 고친다면
`workflows: write`도 준다. 상한의 권한은 GitHub App이 가진 권한 안이어야 발급된다.

## 실행 전 사람 승인 (review.manualApproval)

대상 레포가 PR 머지에 사람 승인용 required status(예: `pr-manual-approval` 유형의 `review/manual-approval`)를
요구하고, 리뷰 시점에 그 status가 PR head에 success로 붙어 있지 않으면, 리뷰는 status를 `approved`로
전이하면서 마지막 attempts 항목의 `review`에 `manualApproval`을 남긴다. 사람 승인 필요 여부는 이 필드의 유무가 유일한 기록이다.

```json
"manualApproval": { "sha": "<리뷰 시점 PR head>", "context": "review/manual-approval" }
```

`manualApproval`이 있는 `approved` task는 다음이 모두 참일 때만 실행 대상이다.

- `preparation.pullRequestUrl`의 PR이 열려 있고 head가 `sha` 그대로다 — 승인은 리뷰한 커밋에 묶이므로,
  새 커밋이 올라오면 이전 승인은 무효다.
- `sha`에 붙은 `context`의 최신 commit status가 `success`다 — 사람이 대상 레포의 승인 절차대로 붙인다.

`manualApproval`이 없는 `approved`는 사람 승인이 필요 없거나 이미 끝난 것이다.

사람 승인은 사람 세션에서 `reconciler-manual-approval`(control plane)로 처리한다. 대상 레포 판정기를 PR diff에
돌려 걸린 파일·규칙을 설명하고, 승인이면 `sha`에 `context` success를 붙인다(task는 바뀌지 않는다). 거부면
`approved → review_rejected`로 전이하고 사유를 `review.comment`에 남겨 planner 재계획으로 넘긴다 —
`manualApproval`이 남은 채 `rejected`인 기록이 곧 사람의 거부다. 이 전이는 그 context가 아직 success가 아닐
때만 쓰므로 executor의 점유(`approved → executing`)와 겹치지 않는다.

## 모델 템플릿

레포마다 반복 등록되는 정합성 유형 — **제품 문서 ↔ 구현**(docs-impl),
**테스트 시나리오 ↔ E2E 1:1**(scenario-e2e), **E2E 모킹 최소화**(e2e-mock-policy),
**목업 ↔ 구현 렌더링**(mockup-render), **사용자 여정 ↔ 목업 1:1**(journey-mockup),
**주석 필요성**(comment-necessity), **PR 수동 승인**(pr-manual-approval),
**데이터 모델**(data-model) — 은 `templates/`의
템플릿으로 등록한다. 판정 기준·충돌 방향·추적 방식 같은 고정부는 템플릿이 유형의
SSOT이고, 새 대상 등록 시엔 슬롯(레포·경로·AC 체계 등)만 채운다. 자세한 절차는
`templates/README.md`.

## 데이터 브라우저 (GitHub Pages)

`index.html`은 의존성 없는 단일 파일 정적 페이지로, `data/`의 ToBeModel과
모델별 ReconciliationTask, 그리고 `templates/`의 모델 템플릿을 읽어 목록·상세로
보여준다. `to-be-models.json`을 불러온 뒤 각 모델 id로
`reconciliation-tasks/<id>.json`을 상대경로로 fetch하므로 외부 API·CDN이 필요
없다. 마크다운 정의 렌더링(표 포함), 상태 배지, 마지막 조치 시각, 검색,
라이트/다크 테마, 원본 JSON 보기를 지원한다.

- **보기 대상 2종 (모델 / 템플릿)**: 상단 툴바 맨 왼쪽 전환 버튼으로 사이드바가
  무엇의 목록인지 바꾼다. **모델**은 `data/`의 운영 데이터, **템플릿**은
  `templates/`의 유형 템플릿이다. 각 버튼에는 등록된 모델 수·템플릿 수가 함께 표시된다.

  템플릿 보기에서는 사이드바에 **템플릿 개요**(`templates/README.md`)와 각 템플릿이
  나열되고, 고르면 본문 마크다운이 슬롯 표·스크립트까지 그대로 렌더링된다
  (원본 마크다운도 함께 볼 수 있다). 검색은 파일명·유형·대상에 걸리고,
  보기를 바꾸면 검색어는 초기화된다. 모드 전환 버튼과 상태 범례는 모델 목록에만
  해당하므로 템플릿 보기에서는 감춘다.

  목록의 출처는 `templates/README.md`의 **템플릿 목록** 표다. 정적 페이지는
  디렉터리를 나열할 수 없어 어딘가에 목록이 필요한데, 별도 매니페스트를 두면 그 표와
  두 벌이 되어 그 자체가 drift 대상이 되므로 이미 유형의 SSOT인 표를 그대로 파싱한다.
  **템플릿을 추가할 땐 그 표에 한 줄 넣으면 페이지에도 자동으로 나온다.**
  표에는 있는데 파일이 없으면 상세에서 404로 드러나고, 표와 `templates/`의 실제
  파일 목록이 어긋나면 `tests/index-templates.test.mjs`가 실패한다.

- **보기 모드 4종**(모델 보기): 상단 툴바의 전환 버튼으로 사이드바 목록의 범위를 바꾼다.
  각 버튼에는 해당 모드의 모델 수가 함께 표시된다.

  | 모드 | 목록에 나오는 모델 |
  | --- | --- |
  | **진행 중** (기본값) | 감지 활성 모델 중 완료되지 않은 작업이 있는 모델 — 완료 = `succeeded`·`cancelled`·`no_action_needed` |
  | **리뷰 대기 중** | 감지 활성 모델 중 대상 레포의 사람 승인을 기다리는 작업(`approved` + `review.manualApproval`)이 있는 모델 |
  | **활성 전체** | 감지가 활성인 모델 전체 |
  | **숨김** | `checkPolicy.enabled`가 `false`인 모델만 |

  기본값은 **진행 중**이다 — 페이지를 열면 루프가 아직 붙잡고 있는 것부터 보인다.
  모드를 직접 고르면 새로고침(↻) 후에도 그 모드가 유지된다(저장된 값이 없어진 모드면
  기본값으로 연다). 검색은 선택한 모드 **안에서** 걸린다.

  **진행 중**은 진행 상태를 나열하지 않고 완료(종료 상태)만 빼서 정의한다. 스키마에 새 진행
  상태가 생겨도 페이지 수정 없이 여기에 잡혀, 목록에서 조용히 사라지는 작업이 없게 하기
  위해서다. `failed`·`review_rejected`는 planner가 다시 집는 재작업 진입점이므로 완료가 아니라
  진행 중이다.

  **리뷰 대기 중**은 진행 중의 부분집합이다 — 승인을 기다리는 작업은 끝나지 않은 작업이기도
  하므로 두 모드에 함께 나온다. 사람 승인은 수동 승인 대기 하나뿐이다: status는 `approved`(실행
  대기)지만 마지막 시도의 `review.manualApproval`이 있으면 대상 레포의 사람 승인 status가 붙기
  전까지 실행되지 않는다. `planned`(리뷰 스킬의 **검토 판단 대기**)는 사람의 리뷰가 아니므로
  들어가지 않는다.

  사이드바 항목에는 **진행 중 N**·**수동 승인 대기 N** 배지가 함께 표시된다.

- **조치 pill (종료 상태에선 숨김)**: task 헤더의 **조치 필요** pill은 **status만으로** 정한다.
  감지 판정은 status 전이(`assessing` → `no_action_needed` | `action_required`)로 남고, 계획·실행
  경로의 모든 상태는 `action_required`를 거쳐야만 도달하므로 "종료가 아닌 상태 = 조치 필요"가
  성립한다. (예전의 `assessment.actionRequired`는 status와 중복이라 스키마에서 뺐다.)

  **종료 상태(`DONE_STATUSES`)에서는 pill을 그리지 않는다.** 라벨이 현재형으로 읽히는 탓에 끝난
  task에까지 붙여 두면 완료된 작업이 남은 할 일처럼 보이기 때문이다. 판단 근거는 상세의
  **판단(assessment)** 섹션에 그대로 남는다. `failed`/`review_rejected`는 planner가 다시 집는
  재작업 진입점이라 종료가 아니므로 pill을 유지한다. "조치 불필요"는 `no_action_needed` 상태 배지가
  이미 말해 주므로 pill로는 그리지 않는다.

  아직 판단 전인 `assessing` task도 **조치 필요** pill을 단다(툴팁으로 `아직 판단 전`임을 밝히고,
  `assessment.recheckAfter`로 파킹된 건은 재확인 시각을 적는다). 판정이 없다는 것은 조치가 필요
  없다는 결론이 아니라 아직 아무도 결론을 내지 않았다는 뜻이고, 그런 건을 무표시로 두면 판단
  단계에서 멈춰 선 task가 목록에서 가장 조용해진다. 판단 전에 취소된 건은 종료 상태라 pill이 없다.

- **조치 필요만 토글**(작업 목록): 상세의 `정합성 작업` 제목 오른쪽 **조치 필요만 N** 버튼으로
  작업 목록을 **조치 필요 pill이 붙은 작업**만으로 좁힌다. 버튼의 N은 그 모델의 조치 필요 건수고,
  제목의 전체 건수는 토글과 무관하게 그대로 둔다 — 걸러진 목록을 보는 동안에도 전체 규모가 보인다.

  거르는 기준은 pill과 **같은 함수**(`taskNeedsAction`)다. 목록과 pill이 어긋나면 "조치 필요만"이
  거짓말이 되므로 판정을 한 곳에만 적고 둘이 그 함수를 부른다(`tests/index-task-action-filter.test.mjs`가
  스키마의 모든 상태에 대해 둘의 일치를 검사한다). 따라서 종료 상태(`succeeded`·`cancelled`·
  `no_action_needed`)만 걸러지고, `failed`·`review_rejected`(재작업 진입점)와 **아직 판단 전인
  `assessing` task**는 남는다.

  토글을 켠 채로 조치 필요 건이 없으면 "작업이 없다"가 아니라 **필터 때문에 비었다**고 적어
  전체 건수를 함께 보여준다. 작업이 하나도 없는 모델에는 토글 자체를 그리지 않는다.
  상태는 모드·레포 필터와 같은 자리(localStorage)에 저장되어 모델을 옮기거나 새로고침해도
  유지된다.

- **감지 비활성 모델**: `checkPolicy.enabled`가 `false`인 모델은 감지 sweep에서 제외된
  모델이므로 기본 목록에 노출하지 않고 **숨김** 모드에서만 보여준다(정의·작업 이력은
  `data/`에 그대로 보존되며 상세도 정상 조회된다). 다시 기본 목록에 보이게 하려면
  `enabled`를 `true`로 되돌리거나 필드를 지운다(생략 시 기본값 `true`).

- **마지막 조치 시각**: 사이드바의 모델마다 마지막으로 조치가 있었던 시점을
  **`마지막 조치 3시간 전 [실행 완료]`** 형태로 보여준다(상세에는 정확한 시각도 함께).
  어떤 모델이 묵고 있는지 목록에서 바로 드러난다.

  시각은 그 모델의 **모든 task에 기록된 단계 시각 중 가장 최근 것**이고, 배지는 그때의
  단계(감지 · 상태 요약 · 판단 · 계획 · 실행 준비 · 검토 · 실행 · 검증)다. `updatedAt`
  하나만 보지 않는 이유는 그게 선택 필드라 초기 기록엔 비어 있기 때문이다 — 그 필드만
  보면 방금 움직인 모델이 오래 묵은 것처럼 보인다. 같은 시각에 여러 필드가 찍혀 있으면
  워크플로 뒤쪽 단계를 그 시점의 조치로 본다.

  `no_action_needed`로 끝난 task는 **조치가 아니므로 통째로 제외한다** — 감지가 돌긴 했지만
  할 일이 없다는 결론이라, 이걸 조치로 치면 아무 일도 없던 모델이 계속 방금 움직인 것처럼
  보인다. 사이드바 상태 점(`latestDisplayTask`)과 같은 기준이다. 조치가 될 task가 하나도
  없는 모델(아직 task가 없거나 전부 no-op)은 `기록 없음`.

- **목록 정렬**: 사이드바는 그 **마지막 조치 시각의 최신순**으로 정렬한다(모드·검색·레포
  필터를 적용한 뒤). `data/to-be-models.json`의 파일 순서대로 두면 방금 움직인 모델이
  목록 아래에 묻혀, 루프가 지금 무엇을 하고 있는지 스크롤해야만 보인다. `기록 없음`인
  모델은 비교할 시각이 없으므로 항상 맨 뒤로 보내고, 시각이 같은 모델끼리는 파일 순서를
  유지한다. 목록의 첫 모델이 기본 선택이므로, 페이지를 열면 가장 최근에 움직인 모델의
  상세가 바로 뜬다.

- **딥링크**: `#<toBeModelId>`로 들어오면 그 모델이 보이는 모드로 자동 전환되므로,
  숨김 모델 링크도 그대로 열린다. `#tpl:<파일명>`(예: `#tpl:scenario-e2e.tbm.md`)은
  템플릿 보기로 열린다.

  모델 선택은 주소에 남기지 않는다 — 목록에서 모델을 골라도 URL이 바뀌지 않으므로,
  새로고침하면 보던 모델이 아니라 기본 선택(목록의 첫 모델)으로 연다. 딥링크로 들어온 뒤
  다른 모델을 고르면 주소의 딥링크도 지워진다.

- **GitHub Pages 활성화**: 저장소 Settings → Pages → *Deploy from a branch* →
  브랜치의 `/(root)` 선택. 페이지는 `data/`를 상대경로로 읽으므로 반드시
  루트에서 서빙해야 한다(`/docs` 아님). 배포 후 `https://<owner>.github.io/<repo>/`.
- **로컬 확인**: `python3 -m http.server` 실행 후 `http://localhost:8000/` 접속.
  `file://`로 직접 열면 브라우저 보안정책상 `data/`를 못 읽으니 서버로 열 것.
- **테스트**: `node --test "tests/*.test.mjs"` — 각 테스트는 `index.html`에서 해당
  함수 블록을 정규식으로 뽑아 `vm`으로 실행한다(빌드·의존성 없음).

## 단계 워크플로 — Claude Code (`.github/workflows/reconciler-*-claude.yml`)

reconciler-local의 systemd 러너(`run-<stage>.sh`: 게이트 → `claude --bg "/reconciler-data-plane:<skill> $DIR"`)를
GitHub Actions로 옮긴 것이다. 기존 단계 워크플로(`reconciler-<stage>.yml`)와 MiniMax 감지 파이프라인
(`reconciler-drift-detector.yml`·`reconciler-drift-detector-skill-build.yml`)과는 **별개 파일**이고 그 파일들을 건드리지 않는다.
concurrency 그룹은 두지 않는다 — 같은 워크플로를 여러 번 띄우면 병렬로 돌고, 같은 task 중복 점유·push 충돌은
스킬의 compare-and-set 점유 커밋이 막는다(MiniMax 워크플로·로컬 러너와의 경쟁도 같은 규약). 네 단계가 같은 모양이다.

MiniMax 감지와 달리 **선정·점유를 스킬이 한다**(위 「점유는 러너가 한다」의 범위 참고) — 러너의 Select target은
claude를 띄울지 정하는 읽기 전용 게이트일 뿐 점유 커밋을 만들지 않는다. 점유 기록의 형태는 두 경로가 같다.

| 스텝 | 하는 일 |
| --- | --- |
| Checkout | 하네스(`harness/`, 자격 증명 없음)와 reconciler 기본 브랜치(`ws/reconciler`, 워크플로 토큰 유지 — 스킬의 push용). |
| Connect homelab-k3s-mcp | `homelab-mcp` 액션. GitHub OIDC 로컬 프록시(`mcp_oidc_proxy.py`, 127.0.0.1)를 띄우고 `tools/list`로 사전 점검, `SOURCE_GITHUB_TOKEN`(대상 레포 read)을 발급한다. |
| Select target | 단계별 `select_*_target.py` — 스킬 Step 0을 옮긴 읽기 전용 게이트. 대상이 없으면 claude를 띄우지 않고 성공, 판단할 수 없으면 실패(fail-closed). |
| Run skill (Claude Code) | `run-claude-skill` 액션. CLI 설치 → 마켓플레이스 `dlddu/plugin-marketplace` 등록 + `reconciler-data-plane` 설치 → `claude -p "/reconciler-data-plane:<skill> <ws/reconciler>"`. 점유·기록·커밋·push는 스킬이 한다. |

- **Claude 인증**: environment `llm-claude`의 secret `CLAUDE_CODE_OAUTH_TOKEN`(`claude setup-token`으로 발급한 OAuth 토큰).
  job이 `environment: llm-claude`를 선언한다(「모델 키 격리」). Deployment branches가 `main`뿐이면 이 워크플로들도 `main`에서만 돈다.
- **GitHub 토큰 경계**: reconciler push는 job의 워크플로 토큰(`contents: write`)으로 한다 — `.github/workflows`는 못 바꾼다.
  스킬(reconciler-repo-access)은 원래 reconciler용 App 토큰을 MCP로 받지만, githubToken 상한에서 reconciler를 빼므로
  러너가 시스템 프롬프트로 그 단계를 건너뛰고 체크아웃의 자격 증명으로 pull·push하게 한다. 대상 레포·plugin-marketplace
  토큰은 MCP(상한 안)로 받는다. claude 환경에서는 OIDC 요청 변수·`SOURCE_GITHUB_TOKEN`·`GITHUB_TOKEN` 환경 변수를 뺀다.
- **homelab-k3s-mcp**: 스킬이 부르는 서버 이름 `k3s`로 등록한다(`--mcp-config` + `--strict-mcp-config`). 설정 파일에는 로컬
  프록시 주소만 있다. `-claude.yml` 규칙 4개는 기존 규칙 파라미터가 4KB 한도에 차서 별도 SSM 파라미터
  `/flux-cd/homelab-k3s-mcp/github-oidc-claude`(키 `MCP_GITHUB_OIDC_RULES_CLAUDE`, homelab-k3s-mcp#289 · flux-cd-apps#89)에 둔다.
  도구는 4개 모두 `github_app_installation_token`·`api_resources`·`resource_list`·`resource_get`·`ping`·`pocket_aide_notification_send`
  (클러스터 쓰기 도구는 기존 task 실행 기록상 쓴 적이 없어 넣지 않았다). githubToken 상한은 레포를 나열하지 않고 **제외할 레포**로
  정한다(homelab-k3s-mcp#289 `excludeRepositories` — 나중에 생긴 레포도 자동 포함):
  - 감지·리뷰: reconciler를 뺀 모든 레포(plugin-marketplace·인프라 레포 포함)에 `contents`·`metadata`·`pull_requests`·`statuses`·`actions` read
  - 계획·실행: reconciler·plugin-marketplace·infrastructure·flux-cd·flux-cd-apps를 뺀 모든 레포에 권한 제한 없음(workflows 포함),
    그리고 `plugin-marketplace`·`infrastructure`·`flux-cd`·`flux-cd-apps`에 `contents`·`metadata` read. 요청은 상한 하나에 통째로
    들어맞아야 해서 이 넷에는 write가 없고,
    제외 상한은 레포를 명시한 요청에만 들어맞는다.
- **플러그인**: 마켓플레이스가 private라 클론용 읽기 토큰을 MCP로 받아 설치 명령의 git 환경 변수(`http.extraheader`)로만 준다.
  GitHub App 설치 범위에 `plugin-marketplace`가 있어야 한다. 버전은 `vars.CLAUDE_CODE_VERSION`(기본 `stable`), 모델은 입력 `model`
  또는 `vars.CLAUDE_MODEL`.
- **식별**: 커밋 작성자는 로컬과 같은 `reconciler-bot`이고 committer만 `reconciler-bot-actions`라 Actions 실행분을 구분할 수 있다.
- **결과**: step summary(선정 결과 · 도구 호출 · 이번 실행 커밋 · 최종 보고)와 아티팩트 `<stage>-claude-run`(대화 기록,
  업로드 전 토큰 가림). result 이벤트 없음 · 오류 종료 · `k3s` 미연결 · push 안 된 커밋이 있으면 실패.
- **사용 한도 초과 알림**: `claude -p`는 구독 한도에 걸려도 exit 0으로 끝나므로 대화 기록으로 판정한다 —
  `rate_limit_event`의 `status: rejected`(줄이 깨져도 찾는다) 또는 오류 result의 한도 문구("You've hit your … limit",
  "Rate limit reached" 등). 걸리면 실행을 「Claude 사용 한도 초과」로 실패 처리하고 PocketAide 푸시를 보낸다
  (`pocket_aide_notification_send` — 한도 종류 · 재설정 시각(KST) · 대상 · 실행 링크). 각 `-claude.yml` OIDC 규칙에 이 도구를
  넣어야 한다(없으면 경고만 남고 실행 판정은 그대로). 중간에 끊겨 점유가 남아도 재설정 뒤 다음 실행의 재개 규칙이 이어받는다.
- **대상 전달**: Select target이 고른 대상(입력 `target_id`가 있으면 그 지목을 반영한 결과)을 `<tbm>/<rct>`로 시스템 프롬프트에
  넘기고 스킬은 그 대상만 본다(슬래시 명령 뒤 문자열은 통째로 checkout 경로 `$ARGUMENTS`). 넘기지 않으면 스킬이 Step 0을 다시 돌려
  러너와 다른 후보를 고를 수 있다 — 테스트에서 계획 스킬이 러너가 뺀 감지 비활성 모델의 task를 고른 적이 있다.
- 스케줄은 없다(`workflow_dispatch`만). 로컬 타이머·MiniMax 감지와 동시에 돌아도 점유 compare-and-set이 경쟁을 막는다.
- 공용 스크립트(`mcp_oidc_proxy.py`·`mcp_call.py`·`redact_secrets.py`)는 MiniMax 워크플로와 함께 쓴다 — 고치면 양쪽 동작을 함께 확인할 것.
  Claude 전용은 `claude_transcript.py`(stream-json 기록 요약·검사)와 `.github/actions/{homelab-mcp,run-claude-skill}`.
