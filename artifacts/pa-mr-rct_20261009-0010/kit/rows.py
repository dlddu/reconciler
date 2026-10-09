# screen-todo-personal 구조·수치 대응표 행 데이터 (rct_20261009-0010)
TL = "ios/PocketAide/Todos/TodoListView.swift"
SH = "ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift"
AL = "ios/Shared/Sources/DesignSystem/Components/AreaLabel.swift"
NA = "—"
E = [
 ("헤더", "absolute top-[54px] inset-x-0 px-5 pt-3 pb-3 z-20"),
 ("라벨 줄", "flex items-center gap-1.5 mb-1"),
 ("영역 점", "w-2 h-2 rounded-full bg-[var(--clay)]"),
 ("영역 라벨(헤더)", "text-[11px] uppercase tracking-[0.22em] text-[var(--clay)] font-bold"),
 ("제목", "text-[28px] font-bold tracking-tight"),
 ("요약 줄", "text-[12px] text-stone-500 mt-0.5"),
 ("추가 버튼", "w-10 h-10 rounded-full bg-[var(--clay)] text-white grid place-items-center active:scale-95"),
 ("글리프 18(추가 · 삭제)", "style=width:18px;height:18px"),
 ("검색 필드", "mt-3 flex items-center gap-2 bg-white border border-[var(--rule)] px-3 py-2 rounded-2xl"),
 ("검색 글리프", "text-stone-400"),
 ("검색 안내", "text-[13px] text-stone-400"),
 ("필터 칩 줄", "flex gap-1.5 mt-3 -mx-5 px-5 overflow-x-auto scroll"),
 ("필터 칩(선택)", "pill px-3 py-1 rounded-full text-[12px] font-semibold whitespace-nowrap text-[var(--ink)]"),
 ("필터 칩", "px-3 py-1 rounded-full text-[12px] font-medium whitespace-nowrap text-stone-600 border border-[var(--rule)]"),
 ("본문", "absolute top-[248px] bottom-[88px] inset-x-0 overflow-y-auto scroll px-5 pt-1 pb-6 space-y-1.5"),
 ("섹션 머리(첫)", "flex items-baseline justify-between pt-1 pb-1"),
 ("섹션 제목", "text-[14px] font-bold"),
 ("섹션 보조", "text-[11px] text-stone-400"),
 ("행 카드", "bg-white rounded-2xl p-3.5 border border-[var(--rule)] flex items-start gap-3"),
 ("체크", "check w-6 h-6 rounded-full grid place-items-center mt-0.5 shrink-0"),
 ("태그 줄", "flex items-center gap-1.5 mb-0.5"),
 ("우선 태그", "text-[10px] font-bold text-[var(--clay)] uppercase tracking-wider"),
 ("행 제목", "text-[15px] leading-snug"),
 ("메타 줄", "flex items-center gap-3 mt-1.5 text-[11px] text-stone-500"),
 ("메타 항목", "flex items-center gap-1"),
 ("달력 글리프", "style=width:11px;height:11px"),
 ("섹션 머리", "flex items-baseline justify-between pt-3 pb-1"),
 ("스와이프 행 틀", "relative overflow-hidden rounded-2xl"),
 ("삭제 패널", "absolute inset-y-0 right-0 w-[74px] bg-[#9E2B3C] flex flex-col items-center justify-center gap-1 text-white"),
 ("삭제 라벨", "text-[12px] font-semibold"),
 ("밀린 행 카드", "relative -translate-x-[74px] bg-white rounded-2xl p-3.5 border border-[var(--rule)] flex items-start gap-3"),
 ("완료 섹션 제목", "text-[14px] font-bold text-stone-400"),
 ("완료 카드", "bg-white/50 rounded-2xl p-3.5 border border-[var(--rule)] flex items-start gap-3 opacity-60"),
 ("체크(완료)", "check done w-6 h-6 rounded-full grid place-items-center mt-0.5 shrink-0"),
 ("체크 글리프", "style=width:12px;height:12px"),
 ("완료 행 제목", "text-[15px] leading-snug line-through decoration-stone-400"),
 ("본문(빈 상태)", "absolute top-[198px] bottom-[88px] inset-x-0 overflow-y-auto scroll px-5 pt-1 pb-6 space-y-1.5"),
 ("빈 상태 안내", "py-5 text-[14px] text-stone-500 leading-relaxed"),
]
# 공용 인용
RR = "var rowRadius: CGFloat { switch self { case .personal: return DesignTokens.Radius.card"
INS = ".listRowInsets(EdgeInsets(top: DesignTokens.Spacing.cardGap / 2, leading: DesignTokens.Spacing.xl, bottom: DesignTokens.Spacing.cardGap / 2, trailing: DesignTokens.Spacing.xl))"
CARD_BG = ".padding(14) .background(DesignTokens.Color.card(tone))"
CARD_RR = ".padding(14) .background(DesignTokens.Color.card(tone)) .clipShape(RoundedRectangle(cornerRadius: area.rowRadius, style: .continuous))"
STROKE = ".stroke(DesignTokens.Color.rule(tone), lineWidth: 1)"
CHECK = 'Image(systemName: item.isDone ? "checkmark.square.fill" : "square")'
CHECK18 = CHECK + " .font(.system(size: 18))"
HDR = '} header: { Text("\\(title) · \\(items.count)")'
SECF = 'Text("\\(title) · \\(items.count)") .font(DesignTokens.Typography.font(size: DesignTokens.Typography.captionSm, weight: .bold))'
TITLE = "Text(item.title) .font(DesignTokens.Typography.font(size: DesignTokens.Typography.bodyLg, weight: .medium))"
SWIPE = ".swipeActions(edge: .trailing, allowsFullSwipe: false)"
LBL = 'Label("삭제", systemImage: "trash")'
S4X = " — S4(다짐·임시공간 같은 8자리)와 같은 사정이나 이 화면은 아직 대상이 아니다(허용 등재는 후속)"
S5X = " — S5(다짐·임시공간 보조 글자)와 같은 모양이나 이 화면은 아직 대상이 아니다(다크 목업 대조 뒤 등재 여부는 후속)"
def m(el, tok, mv, f, q, iv, ver, why):
    return (el, tok, mv, f, q, iv, ver, why)
def none(el, tok, mv, why):
    return (el, tok, mv, NA, NA, NA, "불일치", why)
def card(el, prefix):
    return [
     m(el, "bg-white", "#FFFFFF", TL, [CARD_BG], "#FFFFFF", "일치", f"{prefix} 배경 = 개인 card"),
     m(el, "rounded-2xl", "16", TL, [CARD_RR, RR], "16", "일치", f"{prefix} 라운드 = `rowRadius`(개인 `Radius.card` — 회사는 `Radius.key`)"),
     m(el, "p-3.5", "14", TL, [".padding(14)"], "14", "일치", f"{prefix} 안쪽 여백"),
     m(el, "border", "1", TL, [STROKE], "1", "일치", f"{prefix} 외곽선 두께"),
     m(el, "border-[var(--rule)]", "#EBD9CB", TL, [STROKE], "#EBD9CB", "일치", f"{prefix} 외곽선 색 = 개인 rule"),
     m(el, "gap-3", "12", TL, ["HStack(alignment: .top, spacing: DesignTokens.Spacing.md)"], "12", "일치", f"{prefix} 체크 ↔ 본문 간격 = `Spacing.md`"),
    ]
def check(el):
    return [
     m(el, "w-6", "24", TL, [CHECK18], "18", "불일치", "체크 크기 — 목업 24 원, 구현 SF Symbol 18pt"),
     m(el, "h-6", "24", TL, [CHECK18], "18", "불일치", "체크 크기"),
     m(el, "rounded-full", "full", TL, [CHECK], "시스템", "불일치", "체크 모양 — 목업은 clay 1.6 외곽선 원(`.check`), 구현은 모서리 둥근 사각 SF Symbol(`square` · `checkmark.square.fill`)"),
     none(el, "mt-0.5", "2", "체크 위 여백 — 구현은 `HStack(alignment: .top)` 위에 맞춤만 하고 내림 수식이 없다"),
    ]
M = [
 m("헤더", "px-5", "20", f"`{SH}` · `{TL}`", [".padding(.horizontal, DesignTokens.Spacing.xl)", STROKE + " ) .padding(.horizontal, DesignTokens.Spacing.xl)"], "20", "일치", "헤더 좌우 여백 = `Spacing.xl` — 목업 헤더 안의 검색 필드는 구현에서 헤더 밖 형제라 같은 `Spacing.xl` 을 따로 단다"),
 m("헤더", "pt-3", "12", SH, [".padding(.top, DesignTokens.Spacing.md)"], "12", "일치", "헤더 위 여백 = `Spacing.md`"),
 m("헤더", "pb-3", "12", TL, [".padding(.horizontal, DesignTokens.Spacing.xl) .padding(.bottom, DesignTokens.Spacing.sm)"], "8", "불일치", "헤더 블록 아래 여백 — 목업은 필터 칩 줄 아래 12, 구현은 헤더 블록 맨 아래(검색 필드) 아래 `Spacing.sm` 8"),
 none("라벨 줄", "gap-1.5", "6", "영역 점 ↔ 영역 라벨 간격 — 구현 헤더는 점을 그리지 않는다(`AreaLabel` 의 `showsDot` 기본 `false`, `ScreenHeader` 가 넘기지 않음)"),
 m("라벨 줄", "mb-1", "4", SH, ["VStack(alignment: .leading, spacing: 2)"], "2", "불일치", "라벨 줄 ↔ 제목 간격 — 구현은 공용 헤더 `VStack` 간격 2"),
 none("영역 점", "w-2", "8", "영역 점 — 구현 헤더에 없다"),
 none("영역 점", "h-2", "8", "영역 점 — 구현 헤더에 없다"),
 none("영역 점", "rounded-full", "full", "영역 점 — 구현 헤더에 없다"),
 none("영역 점", "bg-[var(--clay)]", "#B65A3C", "영역 점 — 구현 헤더에 없다"),
 m("영역 라벨(헤더)", "text-[11px]", "11", AL, ["size: DesignTokens.Typography.captionXs, weight: .bold, family: .sans"], "11", "일치", "`AreaLabel` 크기 = `captionXs`"),
 m("영역 라벨(헤더)", "uppercase", "uppercase", AL, [".textCase(.uppercase)"], "uppercase", "일치", "대문자 변환"),
 m("영역 라벨(헤더)", "tracking-[0.22em]", "0.22em", f"`{SH}` · `{AL}`", ["labelTracking: CGFloat = 2.4", "AreaLabel(area: area, tracking: labelTracking)", ".tracking(tracking)"], "2.4", "일치", "자간 — 0.22em × 11 = 2.42 → 2.4(`ScreenHeader` 기본값이 `AreaLabel` 까지 내려간다)"),
 m("영역 라벨(헤더)", "text-[var(--clay)]", "#B65A3C", AL, [".foregroundStyle(DesignTokens.Color.accent(area))"], "#B65A3C", "일치", "라벨 색 = 개인 accent(clay)"),
 m("영역 라벨(헤더)", "font-bold", "bold", AL, ["size: DesignTokens.Typography.captionXs, weight: .bold, family: .sans"], "bold", "일치", "`AreaLabel` 굵기"),
 m("제목", "text-[28px]", "28", SH, ["titleSize: CGFloat = 24,", "size: titleSize, weight: .bold, family: titleFamily"], "24", "불일치", "제목 크기 — 화면이 `titleSize` 를 넘기지 않아 공용 기본값 24"),
 m("제목", "font-bold", "bold", SH, ["size: titleSize, weight: .bold, family: titleFamily"], "bold", "일치", "제목 굵기"),
 m("제목", "tracking-tight", "-0.025em", SH, [".tracking(-0.025 * titleSize)"], "-0.025em", "일치", "제목 자간 −0.025em(글자 크기에 비례)"),
 m("요약 줄", "text-[12px]", "12", TL, ["let base = DesignTokens.Typography.font(size: DesignTokens.Typography.captionXs, weight: .semibold)"], "11", "불일치", "「N개 남음 · N개 완료」 크기 — 구현 `captionXs` 11"),
 m("요약 줄", "text-stone-500", "#78716C", TL, ['.foregroundStyle(DesignTokens.Color.ink(tone).opacity(0.55)) .accessibilityIdentifier("\\(idPrefix).summary")'], "#3D2A22/0.55", "불일치", "요약 줄 색 — 목업 stone, 구현 개인 ink 55%" + S5X),
 m("요약 줄", "mt-0.5", "2", TL, ["VStack(alignment: .trailing, spacing: 6)"], "6", "불일치", "요약 줄 위 간격 — 목업은 제목 아래 2, 구현은 헤더 오른쪽 추가 버튼 아래 6(자리 차이는 표 S 4)"),
 m("추가 버튼", "w-10", "40", TL, [".frame(width: 36, height: 36)"], "36", "불일치", "추가 버튼 크기 — 목업 40 원, 구현 36"),
 m("추가 버튼", "h-10", "40", TL, [".frame(width: 36, height: 36)"], "36", "불일치", "추가 버튼 크기"),
 m("추가 버튼", "rounded-full", "full", TL, [".clipShape(Circle())"], "full", "일치", "추가 버튼 모양 = 원"),
 m("추가 버튼", "bg-[var(--clay)]", "#B65A3C", TL, [".frame(width: 36, height: 36) .background(DesignTokens.Color.card(tone))"], "#FFFFFF", "불일치", "추가 버튼 채움 — 목업 clay 채움, 구현 card(흰) 바탕 + rule 외곽선"),
 m("추가 버튼", "text-white", "#FFFFFF", TL, [".clipShape(Circle()) .foregroundStyle(DesignTokens.Color.ink(tone))"], "#3D2A22", "불일치", "더하기 색 — 목업 흰색, 구현 개인 ink"),
 m("글리프 18(추가 · 삭제)", "width:18px", "18", TL, ['Image(systemName: "plus") .font(.system(size: 14, weight: .bold))'], "14", "불일치", "더하기 글리프 크기 — 목업 svg 18 × 18, 구현 SF Symbol 14pt"),
 m("글리프 18(추가 · 삭제)", "height:18px", "18", TL, ['Image(systemName: "plus") .font(.system(size: 14, weight: .bold))'], "14", "불일치", "더하기 글리프 크기"),
 m("글리프 18(추가 · 삭제)", "width:18px", "18", TL, [LBL], "시스템", "불일치", "휴지통 글리프 크기(스와이프된 행 — 같은 `style` 문자열이라 한 요소) — 시스템 스와이프 버튼" + S4X),
 m("글리프 18(추가 · 삭제)", "height:18px", "18", TL, [LBL], "시스템", "불일치", "휴지통 글리프 크기" + S4X),
 m("검색 필드", "mt-3", "12", SH, ["bottomPadding: CGFloat = DesignTokens.Spacing.sm,", ".padding(.bottom, bottomPadding)"], "8", "불일치", "제목 묶음 ↔ 검색 필드 간격 — 화면이 `bottomPadding` 을 넘기지 않아 공용 기본값 `Spacing.sm` 8"),
 m("검색 필드", "gap-2", "8", TL, ['HStack(spacing: DesignTokens.Spacing.sm) { Image(systemName: "magnifyingglass")'], "8", "일치", "돋보기 ↔ 입력 간격 = `Spacing.sm`"),
 m("검색 필드", "bg-white", "#FFFFFF", TL, [".padding(.vertical, 10) .background(DesignTokens.Color.card(tone))"], "#FFFFFF", "일치", "검색 필드 배경 = 개인 card"),
 m("검색 필드", "border", "1", TL, [STROKE + " ) .padding(.horizontal, DesignTokens.Spacing.xl)"], "1", "일치", "검색 필드 외곽선 두께"),
 m("검색 필드", "border-[var(--rule)]", "#EBD9CB", TL, [STROKE + " ) .padding(.horizontal, DesignTokens.Spacing.xl)"], "#EBD9CB", "일치", "검색 필드 외곽선 색 = 개인 rule"),
 m("검색 필드", "px-3", "12", TL, [".padding(.horizontal, DesignTokens.Spacing.md)"], "12", "일치", "검색 필드 좌우 여백 = `Spacing.md`"),
 m("검색 필드", "py-2", "8", TL, [".padding(.vertical, 10)"], "10", "불일치", "검색 필드 위아래 여백 — 구현 10"),
 m("검색 필드", "rounded-2xl", "16", TL, [".padding(.vertical, 10) .background(DesignTokens.Color.card(tone)) .clipShape(RoundedRectangle(cornerRadius: area.rowRadius, style: .continuous))", RR], "16", "일치", "검색 필드 라운드 = `rowRadius`(개인 16 — 목업 주석 「라운드만 개인 카드(16)」)"),
 m("검색 글리프", "width:14px", "14", TL, ['Image(systemName: "magnifyingglass")'], "시스템", "불일치", "돋보기 크기 — 구현 SF Symbol 에 크기 수식이 없어 시스템 기본 글꼴 크기를 따른다"),
 m("검색 글리프", "height:14px", "14", TL, ['Image(systemName: "magnifyingglass")'], "시스템", "불일치", "돋보기 크기"),
 m("검색 글리프", "text-stone-400", "#A8A29E", TL, ['Image(systemName: "magnifyingglass") .foregroundStyle(DesignTokens.Color.ink(tone).opacity(0.45))'], "#3D2A22/0.45", "불일치", "돋보기 색 — 목업 stone, 구현 개인 ink 45%" + S5X),
 m("검색 안내", "text-[13px]", "13", TL, ["TextField(area.searchPrompt, text: $viewModel.query) .font(DesignTokens.Typography.font(size: DesignTokens.Typography.body))"], "14", "불일치", "「개인 영역만 검색…」 크기 — 구현 `body` 14"),
 m("검색 안내", "text-stone-400", "#A8A29E", TL, ["TextField(area.searchPrompt, text: $viewModel.query)"], "시스템", "불일치", "자리표시 글자 색 — 구현은 시스템 placeholder 색(수식 없음)"),
]
for t, v in (("gap-1.5", "6"), ("mt-3", "12"), ("-mx-5", "-20"), ("px-5", "20")):
    M.append(none("필터 칩 줄", t, v, "필터 칩 줄 — 구현에 기한 필터(전체 · 오늘 · 이번 주 · 날짜 없음)가 없다"))
for t, v in (("px-3", "12"), ("py-1", "4"), ("rounded-full", "full"), ("text-[12px]", "12"), ("font-semibold", "semibold"), ("text-[var(--ink)]", "#3D2A22")):
    M.append(none("필터 칩(선택)", t, v, "선택된 필터 칩 — 구현에 필터가 없다"))
for t, v in (("px-3", "12"), ("py-1", "4"), ("rounded-full", "full"), ("text-[12px]", "12"), ("font-medium", "medium"), ("text-stone-600", "#57534E"), ("border", "1"), ("border-[var(--rule)]", "#EBD9CB")):
    M.append(none("필터 칩", t, v, "선택되지 않은 필터 칩 — 구현에 필터가 없다"))
for el in ("본문", "본문(빈 상태)"):
    if el == "본문":
        M.append(m(el, "px-5", "20", TL, [INS], "20", "일치", "행 좌우 여백 = 목록 행 인셋 leading·trailing `Spacing.xl`"))
    else:
        M.append(m(el, "px-5", "20", TL, [".padding(.vertical, DesignTokens.Spacing.xl) .listRowSeparator(.hidden)"], "시스템", "불일치", "빈 상태 안내 좌우 여백 — 빈 상태 행에는 `listRowInsets` 가 없어 시스템 `List` 기본 행 인셋"))
    M.append(none(el, "pt-1", "4", "목록 위 여백 — 구현 목록 맨 위는 시스템 `Section` 머리(또는 빈 상태 행)라 위 여백 수식이 없다(다짐·임시공간은 첫 행 인셋으로 맞춘다)"))
    M.append(none(el, "pb-6", "24", "목록 아래 여백 — 구현 마지막 행 인셋 아래는 `cardGap / 2` 3 그대로다(다짐·임시공간은 `isLast` 인셋 `Spacing.xxl`)"))
    M.append(m(el, "space-y-1.5", "6", TL, [INS], "6", "일치", "행 사이 간격 = `cardGap`(6, 인접 행 인셋 위·아래 `cardGap / 2` 의 합 — 다짐·임시공간 선례)"))
M += [
 m("섹션 머리(첫)", "pt-1", "4", TL, [HDR], "시스템", "불일치", "섹션 머리 위 여백 — 구현은 시스템 `Section` 머리 배치"),
 m("섹션 머리(첫)", "pb-1", "4", TL, [HDR], "시스템", "불일치", "섹션 머리 아래 여백 — 시스템 `Section` 머리"),
 m("섹션 제목", "text-[14px]", "14", TL, [SECF], "12", "불일치", "섹션 제목 크기 — 구현 `captionSm` 12"),
 m("섹션 제목", "font-bold", "bold", TL, [SECF], "bold", "일치", "섹션 제목 굵기"),
 none("섹션 보조", "text-[11px]", "11", "섹션 오른쪽 보조 글자(날짜 · 개수 · 「접기」) — 구현은 개수를 제목 안 「· N」 으로 붙이고 오른쪽 글자가 없다"),
 none("섹션 보조", "text-stone-400", "#A8A29E", "섹션 오른쪽 보조 글자 — 구현에 없다"),
]
M += card("행 카드", "행 카드")
M += check("체크")
M += [
 none("태그 줄", "gap-1.5", "6", "제목 위 태그 줄 — 구현은 우선순위를 메타 줄 문구(「높음」 등)로 그리고 태그 줄이 없다"),
 none("태그 줄", "mb-0.5", "2", "태그 줄 — 구현에 없다"),
]
for t, v in (("text-[10px]", "10"), ("font-bold", "bold"), ("text-[var(--clay)]", "#B65A3C"), ("uppercase", "uppercase"), ("tracking-wider", "0.05em")):
    M.append(none("우선 태그", t, v, "「우선」 태그 — 구현에 없다(우선순위는 메타 줄 문구)"))
M += [
 m("행 제목", "text-[15px]", "15", TL, [TITLE], "15", "일치", "행 제목 크기 = `bodyLg`"),
 none("행 제목", "leading-snug", "1.375", "행 제목 줄 높이 — 구현에 `lineHeight` 수식이 없다"),
 none("메타 줄", "gap-3", "12", "메타 항목 사이 간격 — 구현은 메타를 한 `Text` 에 ` · ` 로 이어 붙여 간격 수식이 없다"),
 m("메타 줄", "mt-1.5", "6", TL, ["VStack(alignment: .leading, spacing: 4)"], "4", "불일치", "제목 ↔ 메타 줄 간격 — 구현 4"),
 m("메타 줄", "text-[11px]", "11", TL, ["let base = DesignTokens.Typography.font(size: DesignTokens.Typography.captionSm)"], "12", "불일치", "메타 줄 크기 — 구현 `captionSm` 12"),
 m("메타 줄", "text-stone-500", "#78716C", TL, ["Text(meta) .font(metaFont) .foregroundStyle(DesignTokens.Color.ink(tone).opacity(0.55))"], "#3D2A22/0.55", "불일치", "메타 줄 색 — 목업 stone, 구현 개인 ink 55%" + S5X),
 none("메타 항목", "gap-1", "4", "달력 글리프 ↔ 기한 간격 — 구현 메타에 글리프가 없다"),
 none("달력 글리프", "width:11px", "11", "기한 앞 달력 글리프 — 구현에 없다"),
 none("달력 글리프", "height:11px", "11", "기한 앞 달력 글리프 — 구현에 없다"),
 m("섹션 머리", "pt-3", "12", TL, [HDR], "시스템", "불일치", "둘째 섹션부터의 머리 위 여백 — 시스템 `Section` 머리"),
 m("섹션 머리", "pb-1", "4", TL, [HDR], "시스템", "불일치", "섹션 머리 아래 여백 — 시스템 `Section` 머리"),
 m("스와이프 행 틀", "rounded-2xl", "16", TL, [SWIPE], "시스템", "불일치", "스와이프 행 라운드 — 시스템 `List` 가 그린다" + S4X),
 m("삭제 패널", "w-[74px]", "74", TL, [SWIPE], "시스템", "불일치", "삭제 패널 너비 — 시스템 스와이프 버튼 폭" + S4X),
 m("삭제 패널", "bg-[#9E2B3C]", "#9E2B3C", TL, [".tint(DesignTokens.Color.destructive(tone))"], "#9E2B3C", "일치", "삭제 패널 채움 = 개인 destructive(`tokens.md` §1.10)"),
 m("삭제 패널", "gap-1", "4", TL, [LBL], "시스템", "불일치", "휴지통 ↔ 라벨 간격 — 시스템 스와이프 버튼 배치" + S4X),
 m("삭제 패널", "text-white", "#FFFFFF", TL, [LBL], "시스템", "불일치", "패널 글자·글리프 색 — 시스템 스와이프 버튼 전경색" + S4X),
 m("삭제 라벨", "text-[12px]", "12", TL, [LBL], "시스템", "불일치", "「삭제」 크기 — 시스템 스와이프 버튼" + S4X),
 m("삭제 라벨", "font-semibold", "semibold", TL, [LBL], "시스템", "불일치", "「삭제」 굵기 — 시스템 스와이프 버튼" + S4X),
]
M += card("밀린 행 카드", "밀린 행 카드")
M += [
 m("완료 섹션 제목", "text-[14px]", "14", TL, [SECF], "12", "불일치", "「완료 · N」 크기 — 구현 `captionSm` 12"),
 m("완료 섹션 제목", "font-bold", "bold", TL, [SECF], "bold", "일치", "「완료 · N」 굵기"),
 m("완료 섹션 제목", "text-stone-400", "#A8A29E", TL, [".foregroundStyle(DesignTokens.Color.ink(tone).opacity(0.7)) .textCase(nil)"], "#3D2A22/0.7", "불일치", "「완료 · N」 색 — 목업 stone-400, 구현은 모든 섹션 머리가 개인 ink 70%"),
]
cc = card("완료 카드", "완료 카드")
cc[0] = m("완료 카드", "bg-white/50", "#FFFFFF/0.5", TL, [CARD_BG], "#FFFFFF", "불일치", "완료 카드 배경 — 목업 흰색 50%, 구현은 완료 행도 불투명 card")
M += cc
M += [
 m("완료 카드", "opacity-60", "0.6", TL, [".foregroundStyle(DesignTokens.Color.ink(tone).opacity(item.isDone ? 0.45 : 1))"], "0.45", "불일치", "완료 흐림 — 목업은 카드 전체 60%, 구현은 제목 글자만 45%"),
]
M += check("체크(완료)")
M += [
 m("체크 글리프", "width:12px", "12", TL, [CHECK], "시스템", "불일치", "완료 체크 표시 — 구현은 채운 사각 SF Symbol(`checkmark.square.fill`) 하나라 따로 그리는 체크 글리프가 없다"),
 m("체크 글리프", "height:12px", "12", TL, [CHECK], "시스템", "불일치", "완료 체크 표시"),
 m("완료 행 제목", "text-[15px]", "15", TL, [TITLE], "15", "일치", "완료 행 제목 크기 = `bodyLg`"),
 none("완료 행 제목", "leading-snug", "1.375", "완료 행 제목 줄 높이 — 구현에 `lineHeight` 수식이 없다"),
 m("빈 상태 안내", "py-5", "20", TL, [".padding(.vertical, DesignTokens.Spacing.xl) .listRowSeparator(.hidden)"], "20", "일치", "안내 위·아래 여백 = `Spacing.xl`(`emptyState` 의 `Group` — 진행 표시에도 걸린다)"),
 m("빈 상태 안내", "text-[14px]", "14", TL, ['Text("아직 할 일이 없습니다. 우상단 + 버튼으로 추가하세요.") .font(DesignTokens.Typography.font(size: DesignTokens.Typography.body))'], "14", "일치", "안내 크기 = `body`"),
 m("빈 상태 안내", "text-stone-500", "#78716C", TL, ['.foregroundStyle(DesignTokens.Color.ink(tone).opacity(0.55)) .accessibilityIdentifier("\\(idPrefix).empty.state")'], "#3D2A22/0.55", "불일치", "안내 색 — 목업 stone, 구현 개인 ink 55%" + S5X),
 none("빈 상태 안내", "leading-relaxed", "1.625", "안내 줄 높이 — 구현에 `lineHeight` 수식이 없다(임시공간은 `.lineHeight(.multiple(factor: 1.625))`)"),
 # 정방향 전용
 m(NA, NA, "0", TL, ["VStack(spacing: 0) { Rectangle()"], "0", "기본값 일치", "맨 위 영역 띠 · 헤더 · 검색 필드 · 목록 사이 간격 — 목업은 블록 사이 간격 수식이 없다(다짐·임시공간 선례)"),
 m(NA, NA, "0", SH, ["HStack(spacing: 0) { AreaLabel(area: area, tracking: labelTracking) labelAccessory }"], "0", "기본값 일치", "영역 라벨 줄 — 이 화면은 라벨 옆 부속이 없다(`EmptyView`)"),
 m(NA, NA, "0", TL, [".overlay(Circle().stroke(DesignTokens.Color.rule(tone), lineWidth: 1))"], "1", "불일치", "추가 버튼 외곽선 — 목업은 외곽선 없는 clay 채움 원"),
 m(NA, NA, "regular", TL, ["let base = DesignTokens.Typography.font(size: DesignTokens.Typography.captionXs, weight: .semibold)"], "semibold", "불일치", "요약 줄 굵기 — 목업은 굵기 클래스 없음(CSS 기본 400)"),
 m(NA, NA, "regular", TL, [TITLE], "medium", "불일치", "행 제목 굵기 — 목업은 굵기 클래스 없음(CSS 기본 400)"),
 m(NA, NA, "#3D2A22", TL, [".foregroundStyle(DesignTokens.Color.ink(tone).opacity(0.7)) .textCase(nil)"], "#3D2A22/0.7", "불일치", "「오늘」·「날짜 없음」 섹션 제목 색 — 목업은 색 클래스 없이 ink, 구현은 ink 70%"),
 m(NA, NA, NA, TL, ["Text(message) .font(DesignTokens.Typography.font(size: DesignTokens.Typography.captionXs))"], "11", "목업 대기", "오류 줄 크기 — 구현은 실패 시 목록 맨 위에 오류 글자 한 줄을 그린다(`todos.personal.error`), 목업은 이 상태를 그리지 않는다"),
 m(NA, NA, NA, TL, ['.foregroundStyle(DesignTokens.Color.destructive(tone)) .listRowBackground(Color.clear) .accessibilityIdentifier("\\(idPrefix).error")'], "#9E2B3C", "목업 대기", "오류 줄 색 = 개인 destructive — 목업 없음"),
 m(NA, NA, NA, TL, ["ProgressView().frame(maxWidth: .infinity)"], "시스템", "목업 대기", "불러오는 중 — 구현은 첫 불러오기 동안 빈 상태 자리에 진행 표시를 그린다, 목업은 이 상태를 그리지 않는다"),
]
S = [
 ("영역 점", '<span class="w-2 h-2 rounded-full bg-[var(--clay)]"></span>', NA, NA, "불일치", "목업 헤더는 영역 라벨 앞에 clay 점을 단다 — 구현 `ScreenHeader` 는 점 없이 라벨만"),
 ("영역 라벨", "PERSONAL</div>", SH, "AreaLabel(area: area, tracking: labelTracking)", "일치", "헤더 맨 위 — 영역 이름"),
 ("화면 제목", "내 일</h1>", TL, 'case .personal: return "내 일"', "일치", "라벨 아래 큰 제목"),
 ("요약 줄", "7개 남음 · 4개 완료</p>", TL, "Text(area.summary(open: viewModel.openCount, done: viewModel.doneCount))", "불일치", "목업은 제목 바로 아래(부제 자리), 구현은 헤더 오른쪽 추가 버튼 아래(오른쪽 맞춤)"),
 ("추가 버튼", '<button class="w-10 h-10 rounded-full bg-[var(--clay)] text-white grid place-items-center active:scale-95">', TL, '.accessibilityIdentifier("\\(idPrefix).add.button")', "일치", "헤더 오른쪽 끝 원형 버튼(수치·색 차이는 표 M)"),
 ("검색 필드", "<!-- search", TL, "TextField(area.searchPrompt, text: $viewModel.query)", "일치", "제목 묶음 아래 검색 필드 — 「개인 영역만 검색…」"),
 ("필터 칩", "<!-- filter pills -->", NA, NA, "불일치", "목업은 검색 아래 기한 필터 칩 넷(전체 · 오늘 · 이번 주 · 날짜 없음) — 구현에 없다"),
 ("섹션 머리", "<!-- section header -->", TL, 'section(title: area == .work ? "OPEN" : "할 일", items: viewModel.openItems)', "불일치", "목업은 미완료를 기한별 섹션(오늘 · 날짜 없음)으로 나누고 오른쪽에 날짜·개수를 단다 — 구현은 미완료 한 섹션 「할 일 · N」"),
 ("행 카드", "<!-- task with priority -->", TL, "TodoRow(area: area, item: item) {", "일치", "섹션 머리 아래 카드 — 체크 · 본문 순"),
 ("체크", '<button class="check w-6 h-6 rounded-full grid place-items-center mt-0.5 shrink-0"></button>', TL, CHECK, "일치", "카드 왼쪽 체크(모양·크기 차이는 표 M)"),
 ("우선 태그", "우선</span>", TL, 'parts.append(area == .work ? "P\\(workRank(priority))" : priority.displayName)', "불일치", "목업은 제목 위 clay 대문자 태그 「우선」 — 구현은 메타 줄 끝에 우선순위 이름(「높음」 등)"),
 ("행 제목", "엄마 생신 케이크 예약 — 후암동 어니언</p>", TL, "Text(item.title)", "일치", "카드 본문 첫 줄"),
 ("메타 줄", '<div class="flex items-center gap-3 mt-1.5 text-[11px] text-stone-500">', TL, "Text(meta)", "일치", "제목 아래 메타 한 줄(기한 · 메모)"),
 ("달력 글리프", '<rect x="3" y="4" width="18" height="18" rx="2"/>', NA, NA, "불일치", "목업은 기한 앞에 달력 글리프 — 구현 메타는 글자만"),
 ("스와이프 삭제", "<!-- 스와이프된 행", TL, SWIPE, "일치", "행을 왼쪽으로 밀면 오른쪽에 「삭제」"),
 ("완료 섹션", "<!-- completed -->", TL, 'section(title: area == .work ? "DONE" : "완료", items: viewModel.doneItems)', "일치", "목록 끝 「완료 · N」 섹션"),
 ("접기", "접기</button>", NA, NA, "불일치", "목업 완료 섹션 머리 오른쪽 「접기」 — 구현에 없다(완료 섹션은 늘 펼침)"),
 ("완료 행", '<button class="check done w-6 h-6 rounded-full grid place-items-center mt-0.5 shrink-0">', TL, ".strikethrough(item.isDone)", "일치", "완료 행 — 채운 체크 · 취소선 · 흐림"),
 ("빈 상태", "<!-- 빈 상태: 섹션·행 대신 안내 한 줄", TL, '.accessibilityIdentifier("\\(idPrefix).empty.state")', "일치", "항목이 없으면 섹션·행 대신 안내 한 줄(검색 필드는 남는다)"),
 ("불러오는 중", NA, TL, "ProgressView().frame(maxWidth: .infinity)", "목업 대기", "구현은 첫 불러오기 동안 안내 자리에 진행 표시 — 목업 프레임 없음"),
 ("오류 줄", NA, TL, '.accessibilityIdentifier("\\(idPrefix).error")', "목업 대기", "구현은 실패 시 목록 맨 위 destructive 글자 한 줄 — 목업 프레임 없음"),
]
