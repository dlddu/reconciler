## 무엇
reconciler task `tbm_pocket-aide-docs-impl/rct_20261012-0004` — **문서 없는 사용자 대면 동작(판정 기준 4)**.

#275 가 개인 투두에 기한 필터 칩(「전체 · N」·「오늘」·「이번 주」·「날짜 없음」)을 착지시켰다. 칩은 목업 `screen-todo-personal.html` 「filter pills」에 근거가 있지만, **무엇을 거르는지**는 `PocketAideAPI` 의 `TodoDueFilter` 와 `TodoDueFilterTests` 에만 있었다. 문서가 SSOT 이므로 구현 그대로 문서에 확정한다. **코드 변경 0.**

## 변경 (docs 3파일)
| 파일 | 변경 |
|---|---|
| `docs/product/prd-todo.md` | 「결정 사항」에 2026-10-12 블록 — 칩 넷·단일 선택·기본 「전체」, N = 영역 전 항목 수(완료 포함), 「오늘」/「이번 주」는 **마감 지난 항목 포함**, 주 경계는 **기기 달력**(주 시작 요일 미고정), 「날짜 없음」, 두 섹션 공통·검색과 교집합, 머리 개수 요약은 필터 무관, 개인 탭 전용·항목 0개면 칩 줄 없음. 기존 AC5 bullet 바이트 불변 |
| `docs/product/test-todo.md` | 시나리오 10(검증 AC1 — 시나리오 2 「검색 = AC1」 선례의 필터 쪽, 구현됨, 관련 코드 테스트 `TodoDueFilterTests` 4건)을 끝에 덧붙임 + 작성 기준 1문장 |
| `docs/product/doc-tracker/2026-10.md` | 시나리오 74→75, T-3 9→10, 고아 테스트 문면, PRD 공백 해소 bullet, 변경 이력 1행. **「e2e 매핑」 절 바이트 불변**(sha256 앞 16 `3c3a8ef6f9fe96b6` 동일 — 시나리오 10 등재는 scenario-e2e 소관) |

## 문면 ↔ 코드 대응
- 「오늘」 `due <= TodoDueDate.string(from: now)` · 「이번 주」 `calendar.dateInterval(of: .weekOfYear, for: now)` 의 마지막 날 이하 (`ios/Shared/Sources/PocketAideAPI/Todos.swift:137-150`, `calendar: .current`)
- 완료 섹션 포함·검색 교집합: `TodoListViewModel.visibleItems = TodoSearch.filter(…) ∩ dueFilter.includes` → `openItems`/`doneItems`
- 개수 요약·N: `openCount`/`doneCount` 와 `total: viewModel.items.count` 는 `items`(영역 전체) 기준
- 개인 탭 전용·빈 목록이면 숨김: `TodoListView.swift:156` `area == .personal && !viewModel.items.isEmpty`
- 저장 안 함: `@Published var dueFilter: TodoDueFilter = .all` (UserDefaults 무사용)

대안 「주 시작 요일 월요일 고정」은 코드·`TodoDueFilterTests` 변경과 iOS 관례 이탈을 부르고 문서 근거가 없어 기각했다(이 결정 블록 한 줄 + 코드로 뒤집을 수 있다).

## 검증
- 로컬: `check_ledger.py` rc=0(주석 0줄) · `judge.py` 「수동 승인 케이스 미접촉 (3 경로)」 · journey-mockup-harness rc=0(위반 0)
- 원문 재집계: `### 시나리오` 75, 구현 상태 63/6/6 (main 기준 62/6/6 + 1)
- PR CI: docs 전용이라 Detect · comment-policy ledger · Journey mockup · ci-success 만 돈다

## 자매 PR
#278(docs-impl 0002)과 `doc-tracker/2026-10.md` 의 합계 줄·변경 이력 끝에서 겹친다(merge-tree 충돌 2곳, 둘 다 「양쪽 다 살리기」). #278 이 먼저 착지하면 이 브랜치를 새 main 위에서 재생 스크립트로 다시 만든다(이력 행의 구현 상태 수치는 재생 시 원문에서 다시 센다).

범위 밖: 「e2e 매핑」 절 시나리오 10 등재(scenario-e2e) · `_impl-map` 문면(mockup-render) · 잔여 미구현 AC(#278).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
