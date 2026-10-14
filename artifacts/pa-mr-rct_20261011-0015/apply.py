# 사용: pocket-aide 레포 루트에서 python3 <kit>/apply.py  (재생 가능 — 앵커 삽입, 한 번만 쓴다)
import pathlib, sys, collections, re
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from rows import E, M, S, NA
from checker import patch_checker
P = pathlib.Path("docs/mockups/_structure-map.md")
t = P.read_text()
SLUG = "screen-approval"
assert f"(`{SLUG}`)" not in t, "이미 적용됨"
def rep(old, new):
    global t
    assert t.count(old) == 1, (t.count(old), old[:80])
    t = t.replace(old, new)
bq = lambda s: NA if s == NA else f"`{s}`"
fcell = lambda f: f if f.startswith("`") or f == NA else f"`{f}`"
qcell = lambda q: NA if q == NA else " · ".join(f"`{x}`" for x in q)
out = [f"## 표 E — 요소 (`{SLUG}`) · {len(E)}행", "", "| 요소 | 목업 선택 인용 |", "|---|---|"]
out += [f"| {n} | `{s}` |" for n, s in E]
out += ["", f"## 표 M — 수치 (`{SLUG}`) · {len(M)}행", "",
        "| 요소 | 목업 인용 | 목업 값 | 구현 파일 | 구현 인용 | 구현 값 | 판정 | 근거 |", "|---|---|---|---|---|---|---|---|"]
for el, tok, mv, f, q, iv, ver, why in M:
    out.append(f"| {el} | {bq(tok)} | {mv} | {fcell(f)} | {qcell(q)} | {iv} | {ver} | {why} |")
out += ["", f"## 표 S — 요소 순서·유무 (`{SLUG}`) · {len(S)}행", "",
        "행 순서가 목업 화면의 위 → 아래 순서다(1~9 「설정 — 자동 응답·호출자 키」 프레임 · 10~17 「키 발급 — 원문 1회 표시」 프레임의 시트 — 시트 뒤 헤더·제목·섹션 머리·키 카드는 1·2·5·6 과 같은 요소).", "",
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
rep("| `screen-todo-work` | S | 목업 대기 | 0 |\n", "| `screen-todo-work` | S | 목업 대기 | 0 |\n" + tally)
# 집계 줄 — 회사 투두 줄의 수치는 자매 PR 이 바꿀 수 있어 정규식 앵커
m = re.findall(r"^남은 구조·수치 drift\(`screen-todo-work` [^\n]*\n", t, re.M)
assert len(m) == 1, m
rep(m[0], m[0] + f"남은 구조·수치 drift(`{SLUG}` 승인 게이트 설정·키 발급 두 프레임): 표 M `불일치` {cnt[('M','불일치')]}행 · `목업 대기` {cnt[('M','목업 대기')]}행, 표 S `불일치` {cnt[('S','불일치')]}행 · `목업 대기` {cnt[('S','목업 대기')]}행.\n")
rep("지금 표에 있는 화면은 **6개**다", "지금 표에 있는 화면은 **7개**다")
row = ("| `screen-approval` | `ios/PocketAide/Approvals/ApprovalKeysView.swift`(`ApprovalKeysView`·`ApprovalKeyIssueSheet`) | 승인 게이트 설정 두 프레임 — "
       "「설정 — 자동 응답·호출자 키」(헤더·제목·「자동 응답 모드」 섹션·「호출자 키」 섹션 머리·키 목록·발급 버튼) · 「키 발급 — 원문 1회 표시」(같은 헤더·본문 + 발급 시트)의 "
       "`<header>`·`<main>`·시트 하위 트리(검산 `frames` 7·8 — 0부터 센 프레임 순번). 「대기 목록」·「요청 상세」·「결정 확인」·「처리 이력」·「빈 상태」·「오류」·「자동 응답 모드 배너」 일곱 프레임"
       "(`ApprovalsView.swift`·`ApprovalDetailView.swift` 행)·시트 뒤 딤·상태바·하단 탭 바는 아직 표가 없다(범위 밖). 발급 입력 시트·빈 목록·오류 배너·폐기 확인 대화상자는 목업이 없다 |\n")
m = re.findall(r"^\| `screen-todo-work` \| `ios/PocketAide/Todos/TodoListView\.swift`[^\n]*\n", t, re.M)
assert len(m) == 1
rep(m[0], m[0] + row)
rep("개인·회사 투두 탭은 각각 `TodoListView.swift`·`TodoCheckBox.swift` 전체와 `ScreenHeader.swift` 본문(부제 분기 포함) — 의",
    "개인·회사 투두 탭은 각각 `TodoListView.swift`·`TodoCheckBox.swift` 전체와 `ScreenHeader.swift` 본문(부제 분기 포함), 승인 게이트 설정은 `ApprovalKeysView.swift` 전체(발급 시트 포함) — 의")
rep("  그 화면 영역(다짐 · 루틴) 색 에셋의 라이트 값에서 온다(`.white` 는 `#FFFFFF`).",
    "  그 화면 영역(다짐 · 루틴) 색 에셋의 라이트 값에서 온다(`.white` 는 `#FFFFFF`, `DesignTokens.StatusColor.<이름>` 은 `Tokens.swift` 의 `light:` 값).")
rep("화면마다 표 E·M·S 한 벌을 두고, 아래 검산의 `SCREENS` 목록이 화면별 목업 파일·영역 색 에셋·요소 하위 트리의 루트(`roots`)·정방향 대상 파일(구조체 범위)을 정한다.",
    "화면마다 표 E·M·S 한 벌을 두고, 아래 검산의 `SCREENS` 목록이 화면별 목업 파일·영역 색 에셋·요소 하위 트리의 루트(`roots`)·정방향 대상 파일(구조체 범위)을 정한다. "
    "`frames` 가 있는 화면은 그 프레임(목업의 `.frame` 을 0부터 센 순번)의 루트만 읽는다 — 한 목업의 일부 프레임만 대조한 화면이다.")
patch_checker(t, rep)
P.write_text(t)
print({k: v for k, v in sorted(cnt.items())}, len(E), len(M), len(S))
