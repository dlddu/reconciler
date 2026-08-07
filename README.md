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
data/                               # 운영 데이터 (스킬이 런타임에 생성·기록, 초기엔 비어 있음)
  to-be-models.json                 # ToBeModel (배열)
  reconciliation-tasks/             # task: to-be 모델(toBeModelId)별로 파일 분리
    <toBeModelId>.json
index.html                          # data/ 브라우징용 정적 웹페이지 (GitHub Pages)
.nojekyll                           # Pages가 data/*.json을 그대로 서빙하도록 Jekyll 우회
```

## 모델 템플릿

레포마다 반복 등록되는 두 정합성 유형 — **제품 문서 ↔ 구현**(docs-impl),
**AC ↔ E2E 1:1**(ac-e2e) — 은 `templates/`의 템플릿으로 등록한다. 판정 기준·
충돌 방향·추적 방식 같은 고정부는 템플릿이 유형의 SSOT이고, 새 대상 등록 시엔
슬롯(레포·경로·AC 체계 등)만 채운다. 자세한 절차는 `templates/README.md`.

## 데이터 브라우저 (GitHub Pages)

`index.html`은 의존성 없는 단일 파일 정적 페이지로, `data/`의 ToBeModel과
모델별 ReconciliationTask를 읽어 목록·상세로 보여준다. `to-be-models.json`을
불러온 뒤 각 모델 id로 `reconciliation-tasks/<id>.json`을 상대경로로 fetch하므로
외부 API·CDN이 필요 없다. 마크다운 정의 렌더링, 상태 배지, 검색, 라이트/다크
테마, 원본 JSON 보기를 지원한다.

- **보기 모드 4종**: 상단 툴바의 전환 버튼으로 사이드바 목록의 범위를 바꾼다.
  각 버튼에는 해당 모드의 모델 수가 함께 표시된다.

  | 모드 | 목록에 나오는 모델 |
  | --- | --- |
  | **실행 대기** (기본값) | 감지 활성 모델 중 `planned`(실행 대기) 작업이 있는 모델만 |
  | **실행 중** | 감지 활성 모델 중 워커가 붙잡고 처리 중인 작업이 있는 모델만 — `assessing`·`planning`·`awaiting_review`·`executing`·`verifying` |
  | **활성 전체** | 감지가 활성인 모델 전체 |
  | **숨김** | `checkPolicy.enabled`가 `false`인 모델만 |

  기본값은 **실행 대기**다 — 페이지를 열면 지금 실행을 기다리는 것부터 보인다.
  모드를 직접 고르면 새로고침(↻) 후에도 그 모드가 유지된다. 검색은 선택한 모드
  **안에서** 걸린다.

  **실행 대기**와 **실행 중**은 겹치지 않는다. `planned`는 executor에게 넘어가기를
  기다리는 인수인계 지점(미점유)이고, **실행 중**의 다섯 상태는 어떤 워커가 그 단계를
  붙잡고 있는 점유(lock) 상태다. 종료 상태(`succeeded`·`failed`·`cancelled`·
  `no_action_needed`)와 계획 대기(`action_required`)는 어느 쪽에도 들어가지 않는다.
  사이드바 항목에는 각각 **실행 대기 N**·**실행 중 N** 배지가 함께 표시된다.

- **감지 비활성 모델**: `checkPolicy.enabled`가 `false`인 모델은 감지 sweep에서 제외된
  모델이므로 기본 목록에 노출하지 않고 **숨김** 모드에서만 보여준다(정의·작업 이력은
  `data/`에 그대로 보존되며 상세도 정상 조회된다). 다시 기본 목록에 보이게 하려면
  `enabled`를 `true`로 되돌리거나 필드를 지운다(생략 시 기본값 `true`).

- **딥링크**: `#<toBeModelId>`로 들어오면 그 모델이 보이는 모드로 자동 전환되므로,
  숨김 모델 링크도 그대로 열린다.

- **GitHub Pages 활성화**: 저장소 Settings → Pages → *Deploy from a branch* →
  브랜치의 `/(root)` 선택. 페이지는 `data/`를 상대경로로 읽으므로 반드시
  루트에서 서빙해야 한다(`/docs` 아님). 배포 후 `https://<owner>.github.io/<repo>/`.
- **로컬 확인**: `python3 -m http.server` 실행 후 `http://localhost:8000/` 접속.
  `file://`로 직접 열면 브라우저 보안정책상 `data/`를 못 읽으니 서버로 열 것.
