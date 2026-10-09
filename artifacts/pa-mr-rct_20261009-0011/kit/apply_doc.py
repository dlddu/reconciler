import re
P='docs/mockups/_structure-map.md'
s=open(P).read()
SH='`ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift`'
TL='`ios/PocketAide/Todos/TodoListView.swift`'
TK='`ios/Shared/Sources/DesignSystem/Tokens.swift`'
a=s.index('## 표 M — 수치 (`screen-todo-personal`)'); b=s.index('## 표 S — 요소 순서·유무 (`screen-todo-personal`)'); c=s.index('## 검산')
M=s[a:b]; S=s[b:c]
def row(el,mq,mv,f,iq,iv,ver,why): return f"| {el} | {mq} | {mv} | {f} | {iq} | {iv} | {ver} | {why} |"
def sub(sec, start, contains, new):
    lines=sec.split('\n'); hit=[i for i,l in enumerate(lines) if l.startswith(start) and contains in l]
    assert len(hit)==1,(start,contains,len(hit)); lines[hit[0]]=new; return '\n'.join(lines)
def drop(sec,start,contains):
    lines=sec.split('\n'); hit=[i for i,l in enumerate(lines) if l.startswith(start) and contains in l]
    assert len(hit)==1,(start,len(hit)); del lines[hit[0]]; return '\n'.join(lines)
M=sub(M,'| 헤더 | `pb-3` |','',row('헤더','`pb-3`','12',TL,'`.padding(.horizontal, DesignTokens.Spacing.xl) .padding(.bottom, DesignTokens.Spacing.md)`','12','일치','헤더 블록 아래 여백 = `Spacing.md` — 목업은 필터 칩 줄 아래 12, 구현은 헤더 블록 맨 아래(검색 필드) 아래 12(필터 칩 줄 자체의 유무는 표 S 7)'))
M=sub(M,'| 제목 | `text-[28px]` |','',row('제목','`text-[28px]`','28',f'{SH} · {TL}','`size: titleSize, weight: .bold, family: titleFamily` · `titleSize: 28,`','28','일치','제목 크기 — 화면이 `titleSize: 28` 을 넘긴다(공용 기본값 24)'))
M=sub(M,'| 요약 줄 | `text-[12px]` |','',row('요약 줄','`text-[12px]`','12',f'{SH} · {TL}','`Text(subtitle) .font(DesignTokens.Typography.font(size: DesignTokens.Typography.captionSm))` · `subtitle: area.summary(open: viewModel.openCount, done: viewModel.doneCount),`','12','일치','「N개 남음 · N개 완료」 크기 — 요약 줄을 공용 헤더 부제로 넘겨 `captionSm` 12'))
M=sub(M,'| 요약 줄 | `text-stone-500` |','',row('요약 줄','`text-stone-500`','#78716C',f'{SH} · {TL}','`Text(subtitle) .font(DesignTokens.Typography.font(size: DesignTokens.Typography.captionSm)) .foregroundStyle(DesignTokens.Color.ink(area).opacity(0.55))` · `subtitle: area.summary(open: viewModel.openCount, done: viewModel.doneCount),`','#3D2A22/0.55','불일치','요약 줄 색 — 목업 stone, 구현 공용 부제 개인 ink 55% — S5(다짐·임시공간 보조 글자)와 같은 모양이나 이 화면은 아직 대상이 아니다(다크 목업 대조 뒤 등재 여부는 후속)'))
M=sub(M,'| 요약 줄 | `mt-0.5` |','',row('요약 줄','`mt-0.5`','2',SH,'`VStack(alignment: .leading, spacing: 2)`','2','일치','제목 ↔ 요약 줄 간격 = 공용 헤더 `VStack` 간격 2(요약 줄이 부제 자리 — 표 S 4)'))
for t in ('w-10','h-10'):
    M=sub(M,f'| 추가 버튼 | `{t}` |','',row('추가 버튼',f'`{t}`','40',TL,'`.frame(width: 40, height: 40)`','40','일치','추가 버튼 크기 — 목업 40 원'))
M=sub(M,'| 추가 버튼 | `bg-[var(--clay)]` |','',row('추가 버튼','`bg-[var(--clay)]`','#B65A3C',TL,'`.frame(width: 40, height: 40) .background(DesignTokens.Color.accent(tone))`','#B65A3C','일치','추가 버튼 채움 = 개인 accent(clay) — 외곽선 없음'))
M=sub(M,'| 추가 버튼 | `text-white` |','',row('추가 버튼','`text-white`','#FFFFFF',TL,'`.clipShape(Circle()) .foregroundStyle(.white)`','#FFFFFF','일치','더하기 색 = 흰색'))
for t in ('width:18px','height:18px'):
    M=sub(M,f'| 글리프 18(추가 · 삭제) | `{t}` |','"plus"',row('글리프 18(추가 · 삭제)',f'`{t}`','18',TL,'`Image(systemName: "plus") .font(.system(size: 18, weight: .bold))`','18','일치','더하기 글리프 크기 — 목업 svg 18 × 18, 구현 SF Symbol 18pt'))
M=sub(M,'| 검색 필드 | `mt-3` |','',row('검색 필드','`mt-3`','12',f'{SH} · {TL}','`.padding(.bottom, bottomPadding)` · `bottomPadding: DesignTokens.Spacing.md`','12','일치','제목 묶음 ↔ 검색 필드 간격 — 화면이 `bottomPadding: Spacing.md` 12 를 넘긴다(공용 기본값 8)'))
M=sub(M,'| 검색 필드 | `bg-white` |','',row('검색 필드','`bg-white`','#FFFFFF',TL,'`.padding(.vertical, DesignTokens.Spacing.sm) .background(DesignTokens.Color.card(tone))`','#FFFFFF','일치','검색 필드 배경 = 개인 card'))
M=sub(M,'| 검색 필드 | `py-2` |','',row('검색 필드','`py-2`','8',TL,'`.padding(.vertical, DesignTokens.Spacing.sm)`','8','일치','검색 필드 위아래 여백 = `Spacing.sm`'))
old=M[M.index('| 검색 필드 | `rounded-2xl` |'):]; old=old[:old.index('\n')]
M=M.replace(old, old.replace('`.padding(.vertical, 10) .background','`.padding(.vertical, DesignTokens.Spacing.sm) .background'),1)
M=sub(M,'| 검색 안내 | `text-[13px]` |','',row('검색 안내','`text-[13px]`','13',TL,'`TextField(area.searchPrompt, text: $viewModel.query) .font(DesignTokens.Typography.font(size: DesignTokens.Typography.bodySm))`','13','일치','「개인 영역만 검색…」 크기 = `bodySm` 13'))
M=drop(M,'| — | — | 0 |','.overlay(Circle().stroke')
M=sub(M,'| — | — | regular |','요약 줄 굵기',row('—','—','regular',f'{SH} · {TK}','`Text(subtitle) .font(DesignTokens.Typography.font(size: DesignTokens.Typography.captionSm))` · `weight: Font.Weight = .regular,`','regular','기본값 일치','요약 줄 굵기 — 목업은 굵기 클래스 없음(CSS 기본 400), 공용 부제는 굵기를 넘기지 않아 `font(size:)` 기본값 regular'))
n=len(re.findall(r'^\| (?!요소 \|)(?!---)', M, re.M)); assert n==145,n
M=M.replace('## 표 M — 수치 (`screen-todo-personal`) · 146행','## 표 M — 수치 (`screen-todo-personal`) · 145행',1)
S=sub(S,'| 4 | 요약 줄 |','',f"| 4 | 요약 줄 | `7개 남음 · 4개 완료</p>` | {TL} | `subtitle: area.summary(open: viewModel.openCount, done: viewModel.doneCount),` | 일치 | 제목 바로 아래 부제 자리 — 공용 헤더 부제(`ScreenHeader` 의 `subtitle`)로 그린다 |")
s=s[:a]+M+S+s[c:]
def rep(old,new):
    global s; k=s.count(old); assert k==1,(k,old[:50]); s=s.replace(old,new)
rep('개인 투두 탭은 `TodoListView.swift` 전체와 `ScreenHeader.swift` 본문(부제 분기 제외)','개인 투두 탭은 `TodoListView.swift` 전체와 `ScreenHeader.swift` 본문(부제 분기 포함)')
rep('''    {"slug": "screen-todo-personal", "area": "personal", "svg": True, "roots": ["absolute top-[54px] inset-x-0 px-5 pt-3 pb-3 z-20", "bottom-[88px] inset-x-0 overflow-y-auto scroll px-5 pt-1 pb-6 space-y-1.5"],
     "fwd": [("ios/PocketAide/Todos/TodoListView.swift", None, None),
             ("ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift", "public var body", "if let subtitle"),
             ("ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift", "Spacer()", "public extension")]},''','''    {"slug": "screen-todo-personal", "area": "personal", "svg": True, "roots": ["absolute top-[54px] inset-x-0 px-5 pt-3 pb-3 z-20", "bottom-[88px] inset-x-0 overflow-y-auto scroll px-5 pt-1 pb-6 space-y-1.5"],
     "fwd": [("ios/PocketAide/Todos/TodoListView.swift", None, None),
             ("ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift", "public var body", "public extension")]},''')
rep('남은 구조·수치 drift(`screen-todo-personal` 개인 투두 탭 두 프레임): 표 M `불일치` 98행 · `목업 대기` 3행, 표 S `불일치` 7행 · `목업 대기` 2행.','남은 구조·수치 drift(`screen-todo-personal` 개인 투두 탭 두 프레임): 표 M `불일치` 83행 · `목업 대기` 3행, 표 S `불일치` 6행 · `목업 대기` 2행.')
for v,o,nw in (('M | 일치','43','56'),('M | 기본값 일치','2','3'),('M | 불일치','98','83'),('S | 일치','12','13'),('S | 불일치','7','6')):
    rep(f'| `screen-todo-personal` | {v} | {o} |',f'| `screen-todo-personal` | {v} | {nw} |')
open(P,'w').write(s); print('doc ok')
