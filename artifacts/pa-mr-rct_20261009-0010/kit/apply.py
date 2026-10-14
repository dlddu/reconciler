# 사용: pocket-aide 레포 루트에서 python3 <kit>/apply.py  (재생 가능 — 앵커 삽입, 한 번만 쓴다)
import pathlib, sys, collections
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from rows import E, M, S, NA
P = pathlib.Path("docs/mockups/_structure-map.md")
t = P.read_text()
SLUG = "screen-todo-personal"
assert f"(`{SLUG}`)" not in t, "이미 적용됨"
def rep(old, new):
    global t
    assert t.count(old) == 1, (t.count(old), old[:80])
    t = t.replace(old, new)
bq = lambda s: NA if s == NA else f"`{s}`"
def fcell(f):
    return f if f.startswith("`") or f == NA else f"`{f}`"
def qcell(q):
    return NA if q == NA else " · ".join(f"`{x}`" for x in q)
out = [f"## 표 E — 요소 (`{SLUG}`) · {len(E)}행", "", "| 요소 | 목업 선택 인용 |", "|---|---|"]
out += [f"| {n} | `{s}` |" for n, s in E]
out += ["", f"## 표 M — 수치 (`{SLUG}`) · {len(M)}행", "",
        "| 요소 | 목업 인용 | 목업 값 | 구현 파일 | 구현 인용 | 구현 값 | 판정 | 근거 |", "|---|---|---|---|---|---|---|---|"]
for el, tok, mv, f, q, iv, ver, why in M:
    out.append(f"| {el} | {bq(tok)} | {mv} | {fcell(f)} | {qcell(q)} | {iv} | {ver} | {why} |")
out += ["", f"## 표 S — 요소 순서·유무 (`{SLUG}`) · {len(S)}행", "",
        "행 순서가 목업 화면의 위 → 아래 순서다(1~18 「목록」 프레임 — 1~6 헤더·검색은 두 프레임 공통 · 19 「빈 상태」 프레임 · 20~21 구현만 그리는 상태).", "",
        "| # | 목업 요소 | 목업 인용 | 구현 파일 | 구현 인용 | 판정 | 근거 |", "|---|---|---|---|---|---|---|"]
for i, (name, mq, f, iq, ver, why) in enumerate(S, 1):
    out.append(f"| {i} | {name} | {bq(mq)} | {fcell(f)} | {bq(iq)} | {ver} | {why} |")
rep("\n## 검산\n", "\n" + "\n".join(out) + "\n\n## 검산\n")
cnt = collections.Counter()
for r in M:
    cnt[("M", r[6].split()[0] if r[6].startswith("허용") else r[6])] += 1
for r in S:
    cnt[("S", r[4])] += 1
order = [("M", "일치"), ("M", "기본값 일치"), ("M", "불일치"), ("M", "허용"), ("M", "목업 대기"), ("S", "일치"), ("S", "불일치"), ("S", "목업 대기")]
assert set(cnt) <= set(order), cnt
tally = "".join(f"| `{SLUG}` | {k} | {v} | {cnt[(k, v)]} |\n" for k, v in order)
rep("| `screen-scratchpad` | S | 목업 대기 | 0 |\n", "| `screen-scratchpad` | S | 목업 대기 | 0 |\n" + tally)
old = "남은 구조·수치 drift(`screen-scratchpad` 임시공간 탭 네 프레임): 표 M `불일치` 13행 · `목업 대기` 0행, 표 S `불일치` 3행 · `목업 대기` 0행.\n"
rep(old, old + f"남은 구조·수치 drift(`{SLUG}` 개인 투두 탭 두 프레임): 표 M `불일치` {cnt[('M','불일치')]}행 · `목업 대기` {cnt[('M','목업 대기')]}행, 표 S `불일치` {cnt[('S','불일치')]}행 · `목업 대기` {cnt[('S','목업 대기')]}행.\n")
rep("지금 표에 있는 화면은 **4개**다", "지금 표에 있는 화면은 **5개**다")
row = "| `screen-todo-personal` | `ios/PocketAide/Todos/TodoListView.swift` 의 `TodoListView(area: .personal)` (+ 그 화면이 쓰는 `ScreenHeader.swift`·`AreaLabel.swift`) | 개인 투두 탭 두 프레임 — 「목록」(헤더·검색 필드·필터 칩·섹션 머리·행 카드·스와이프된 행·완료 섹션) · 「빈 상태」(헤더·검색 필드·안내 한 줄)의 `<header>`·`<main>` 하위 트리. 편집 시트(`TodoEditSheet.swift` — 목업 없음)·상태바·맨 위 영역 띠·하단 탭 바는 범위 밖. 같은 뷰가 그리는 회사 탭(`screen-todo-work`)은 아직 표가 없다 |\n"
anchor = [l for l in t.split("\n") if l.startswith("| `screen-scratchpad` | `ios/PocketAide/Scratchpad/ScratchpadView.swift`")]
assert len(anchor) == 1
rep(anchor[0] + "\n", anchor[0] + "\n" + row)
rep("임시공간 탭은 `ScratchpadView.swift` 전체와 `ScreenHeader.swift` 본문(부제 분기 포함) — 의",
    "임시공간 탭은 `ScratchpadView.swift` 전체와 `ScreenHeader.swift` 본문(부제 분기 포함), 개인 투두 탭은 `TodoListView.swift` 전체와 `ScreenHeader.swift` 본문(부제 분기 제외) — 의")
rep("""             ("ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift", "public var body", "public extension")]},
]""", """             ("ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift", "public var body", "public extension")]},
    {"slug": "screen-todo-personal", "area": "personal", "svg": True, "roots": ["absolute top-[54px] inset-x-0 px-5 pt-3 pb-3 z-20", "bottom-[88px] inset-x-0 overflow-y-auto scroll px-5 pt-1 pb-6 space-y-1.5"],
     "fwd": [("ios/PocketAide/Todos/TodoListView.swift", None, None),
             ("ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift", "public var body", "if let subtitle"),
             ("ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift", "Spacer()", "public extension")]},
]""")
P.write_text(t)
print("applied", dict(cnt), "E", len(E), "M", len(M), "S", len(S))
