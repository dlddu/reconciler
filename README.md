# reconciler

as-is 상태와 to-be(목표) 상태를 비교해, 버전이 바뀔 때마다 정합성 작업을 만들어 실행·검증하는 시스템의 스키마와 운영 데이터.

## 엔티티

- **ToBeModel** — 목표 상태의 마크다운 정의와 as-is/to-be 데이터 소스, 소스별 버전 계산 스크립트.
  각 `versionScript`는 stdout 마지막 줄을 버전 문자열로 사용한다
  (github = 커밋 SHA + 하위 디렉터리 tree hash, k8s = deployment revision + 이미지, monitor = 최신 alert event id).
- **ReconciliationTask** — as-is/to-be 버전이 바뀔 때마다 생성되는 작업.
  요약 → 판단 → 계획 → (사용자 검토) → 실행 → 검증 순으로 필드가 채워진다.

## 구조

```
schemas/
  to-be-model.schema.json           # ToBeModel JSON 스키마 (draft 2020-12)
  reconciliation-task.schema.json   # ReconciliationTask JSON 스키마 (draft 2020-12)
templates/                          # 반복 등록되는 모델 유형의 표준 템플릿
  README.md                         # 슬롯 규약·인스턴스화 절차
  docs-impl.tbm.md                  # 제품 문서 ↔ 구현 정합성
  ac-e2e.tbm.md                     # AC ↔ E2E 1:1 정합성
  e2e-mock-policy.tbm.md            # E2E 모킹 최소화 (정책 ↔ 실제 모킹 지점)
  mockup-render.tbm.md              # 목업 ↔ 구현 렌더링 정합성
  journey-mockup.tbm.md             # 사용자 여정 ↔ 목업 1:1 정합성
  comment-redundancy.tbm.md         # 주석 비중복성 (복원 가능한 주석 제거)
data/                               # 운영 데이터 (스킬이 런타임에 생성·기록, 초기엔 비어 있음)
  to-be-models.json                 # ToBeModel (배열)
  reconciliation-tasks/             # task: to-be 모델(toBeModelId)별로 파일 분리
    <toBeModelId>.json
index.html                          # data/·templates/ 브라우징용 정적 웹페이지 (GitHub Pages)
tests/                              # index.html 동작 테스트 (node --test)
.nojekyll                           # Pages가 data/*.json을 그대로 서빙하도록 Jekyll 우회
```

## 모델 템플릿

레포마다 반복 등록되는 정합성 유형 — **제품 문서 ↔ 구현**(docs-impl),
**AC ↔ E2E 1:1**(ac-e2e), **E2E 모킹 최소화**(e2e-mock-policy),
**목업 ↔ 구현 렌더링**(mockup-render), **사용자 여정 ↔ 목업 1:1**(journey-mockup),
**주석 비중복성**(comment-redundancy) — 은 `templates/`의
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

- **보기 모드 5종**(모델 보기): 상단 툴바의 전환 버튼으로 사이드바 목록의 범위를 바꾼다.
  버튼은 워크플로 순서대로 놓이고, 각 버튼에는 해당 모드의 모델 수가 함께 표시된다.

  | 모드 | 목록에 나오는 모델 |
  | --- | --- |
  | **계획 중** | 감지 활성 모델 중 detector·planner가 붙잡고 있는 작업이 있는 모델만 — `assessing`·`planning` |
  | **실행 대기** (기본값) | 감지 활성 모델 중 `planned`(실행 대기) 작업이 있는 모델만 |
  | **실행 중** | 감지 활성 모델 중 executor가 붙잡고 있는 작업이 있는 모델만 — `awaiting_review`·`executing`·`verifying` |
  | **활성 전체** | 감지가 활성인 모델 전체 |
  | **숨김** | `checkPolicy.enabled`가 `false`인 모델만 |

  기본값은 **실행 대기**다 — 페이지를 열면 지금 실행을 기다리는 것부터 보인다.
  모드를 직접 고르면 새로고침(↻) 후에도 그 모드가 유지된다. 검색은 선택한 모드
  **안에서** 걸린다.

  앞의 세 모드는 서로 겹치지 않는다. **계획 중**과 **실행 중**은 워커가 그 단계를
  붙잡고 있는 점유(lock) 상태이고, 그 사이의 **실행 대기**(`planned`)는 executor에게
  넘어가기를 기다리는 미점유 인수인계 지점이다. 종료 상태(`succeeded`·`failed`·
  `cancelled`·`no_action_needed`)와 계획 대기(`action_required`)는 어느 쪽에도
  들어가지 않는다. 사이드바 항목에는 각각 **계획 중 N**·**실행 대기 N**·**실행 중 N**
  배지가 함께 표시되므로, 한 모델이 여러 단계에 작업을 갖고 있으면 배지도 함께 붙는다.

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

- **딥링크**: `#<toBeModelId>`로 들어오면 그 모델이 보이는 모드로 자동 전환되므로,
  숨김 모델 링크도 그대로 열린다. `#tpl:<파일명>`(예: `#tpl:ac-e2e.tbm.md`)은
  템플릿 보기로 열린다.

- **GitHub Pages 활성화**: 저장소 Settings → Pages → *Deploy from a branch* →
  브랜치의 `/(root)` 선택. 페이지는 `data/`를 상대경로로 읽으므로 반드시
  루트에서 서빙해야 한다(`/docs` 아님). 배포 후 `https://<owner>.github.io/<repo>/`.
- **로컬 확인**: `python3 -m http.server` 실행 후 `http://localhost:8000/` 접속.
  `file://`로 직접 열면 브라우저 보안정책상 `data/`를 못 읽으니 서버로 열 것.
- **테스트**: `node --test "tests/*.test.mjs"` — 각 테스트는 `index.html`에서 해당
  함수 블록을 정규식으로 뽑아 `vm`으로 실행한다(빌드·의존성 없음).
