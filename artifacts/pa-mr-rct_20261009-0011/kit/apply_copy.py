# 리뷰 거부(2026-10-09T12:28Z) 반영: 요약 줄 식별자 리터럴이 `subtitleIdentifier:` 인자로 옮겨져
# 카피 검산 EXCL(accessibilityIdentifier( 뒤만 제외)에 걸리지 않으므로 표 A 에 비표시 행을 등재한다.
# apply_ios.py → apply_doc.py 뒤에 레포 루트에서 실행. 앵커 assert(1회 일치)로 재생 정확성 보장.
P='docs/mockups/_copy-map.md'
s=open(P).read()
def rep(old,new):
    global s; k=s.count(old); assert k==1,(k,old[:60]); s=s.replace(old,new)
anchor='| `ios/PocketAide/Todos/TodoListView.swift` | `todos.\\(area.rawValue)` | 비표시 | 접근성 식별자 접두어(`idPrefix`) |\n'
rep(anchor, anchor+'| `ios/PocketAide/Todos/TodoListView.swift` | `\\(idPrefix).summary` | 비표시 | 요약 줄 접근성 식별자 — `ScreenHeader` 의 `subtitleIdentifier:` 인자로 넘겨 `accessibilityIdentifier(` 제외 규칙에 걸리지 않는다 |\n')
rep('| A | 비표시 | 14 |','| A | 비표시 | 15 |')
rep('## 표 A — 정방향 (구현 리터럴 → 목업) · 164행','## 표 A — 정방향 (구현 리터럴 → 목업) · 165행')
open(P,'w').write(s); print('copy ok')
