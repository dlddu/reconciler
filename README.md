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
tests/                              # index.html 동작 테스트 (node --test)
.nojekyll                           # Pages가 data/*.json을 그대로 서빙하도록 Jekyll 우회
```

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
