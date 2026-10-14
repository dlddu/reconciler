# screen-approval 「설정 — 자동 응답·호출자 키」·「키 발급 — 원문 1회 표시」 두 프레임 구조·수치 대응표 행 데이터 (rct_20261011-0015)
F = "ios/PocketAide/Approvals/ApprovalKeysView.swift"
NA = "—"
E = [
 ("헤더", "absolute top-[54px] inset-x-0 px-5 pt-3 pb-2 z-20 bg-[var(--bg)]/95 flex items-center justify-between"),
 ("뒤로 버튼", "flex items-center gap-1 text-[15px] text-[var(--accent)]"),
 ("뒤로 글리프", "style=width:10px;height:16px"),
 ("본문", "absolute top-[104px] bottom-[88px] inset-x-0 overflow-y-auto scroll px-5 pt-3 pb-6"),
 ("제목", "text-[18px] font-bold mb-3"),
 ("섹션 머리", "mb-2 mt-1 flex items-center gap-2"),
 ("섹션 막대", "w-1 h-3 bg-[var(--accent)]"),
 ("섹션 제목", "text-[11px] font-bold tracking-wide stamp uppercase text-[var(--accent)]"),
 ("섹션 선", "flex-1 h-px bg-[var(--rule)]"),
 ("모드 카드", "bg-white border border-[var(--rule)] rounded-md overflow-hidden mb-4"),
 ("모드 행(첫)", "flex items-center justify-between px-3.5 py-3 text-[14px]"),
 ("모드 행", "flex items-center justify-between px-3.5 py-3 text-[14px] border-t border-[var(--rule)]"),
 ("키 목록 카드", "bg-white border border-[var(--rule)] rounded-md overflow-hidden"),
 ("키 행(첫)", "px-3.5 py-3"),
 ("키 칩", "stamp text-[10.5px] font-bold px-2 py-0.5 rounded-[2px] bg-[var(--soft)] text-[var(--accent-strong)]"),
 ("폐기 버튼", "text-[12px] font-bold text-[var(--destructive)]"),
 ("메타 줄", "stamp text-[10.5px] text-stone-500 mt-1.5"),
 ("키 행", "px-3.5 py-3 border-t border-[var(--rule)]"),
 ("폐기된 키 행", "px-3.5 py-3 border-t border-[var(--rule)] opacity-60"),
 ("폐기된 키 칩", "stamp text-[10.5px] font-bold px-2 py-0.5 rounded-[2px] border border-stone-300 text-stone-500 line-through"),
 ("폐기 시각", "stamp text-[10.5px] text-stone-500"),
 ("발급 버튼", "w-full mt-3 py-3 rounded-[10px] border border-dashed border-[var(--accent)] text-[var(--accent)] text-[14px] font-bold"),
 ("키 카드(발급 프레임)", "bg-white border border-[var(--rule)] rounded-md px-3.5 py-3"),
 ("발급 시트", "absolute z-50 inset-x-0 bottom-0 rounded-t-[22px] bg-white px-5 pt-3 pb-10"),
 ("시트 손잡이", "w-9 h-1 rounded-full bg-stone-300 mx-auto mb-4"),
 ("시트 제목", "text-[17px] font-bold"),
 ("시트 라벨", "block text-[11px] text-stone-500 mt-3"),
 ("이름 칸", "w-full mt-1 px-3 py-2.5 rounded-md border border-[var(--rule)] text-[14px] stamp bg-[var(--bg)]"),
 ("원문 칸", "mt-1 px-3 py-2.5 rounded-md border border-[var(--accent)] bg-[var(--soft)] stamp text-[12px] break-all"),
 ("경고 문구", "text-[11.5px] text-[var(--destructive)] mt-2 leading-relaxed"),
 ("버튼 줄", "flex gap-2.5 mt-4"),
 ("복사 버튼", "flex-1 py-3 rounded-[10px] border border-[var(--accent)] bg-[var(--accent)] text-white text-[15px] font-bold"),
 ("완료 버튼", "flex-1 py-3 rounded-[10px] border border-[var(--rule)] bg-white text-[15px]"),
]
# 공용 인용
NAV = ["navigationBarTitleDisplayMode(.inline)"]
SHEET = [".presentationDetents([.medium, .large])"]
PADX = [".padding(.horizontal, DesignTokens.Spacing.xl)"]
TITLE = [".font(DesignTokens.Typography.font(size: 18, weight: .bold))"]
SEC_T = [".font(.system(size: DesignTokens.Typography.captionXs, weight: .bold, design: .monospaced))"]
ACC_FG = [".foregroundStyle(DesignTokens.Color.accent(Self.area))"]
CARD_BG = [".background(DesignTokens.Color.card(Self.area))"]
RULE6 = ["RoundedRectangle(cornerRadius: 6, style: .continuous) .stroke(DesignTokens.Color.rule(Self.area), lineWidth: 1)"]
ACC6 = ["RoundedRectangle(cornerRadius: 6, style: .continuous) .stroke(DesignTokens.Color.accent(Self.area), lineWidth: 1)"]
CLIP6 = [".clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))"]
ROW_PX = [".padding(.horizontal, 14)"]
ROW_PY = [".padding(.vertical, DesignTokens.Spacing.md)"]
DIV = ["Rectangle() .fill(DesignTokens.Color.rule(Self.area)) .frame(height: 1)"]
CHIP_F = [".font(.system(size: 10.5, weight: .bold, design: .monospaced))"]
CHIP_PX = [".padding(.horizontal, DesignTokens.Spacing.sm)"]
CHIP_PY = [".padding(.vertical, 2)"]
CHIP_CLIP = [".clipShape(RoundedRectangle(cornerRadius: 2, style: .continuous))"]
CHIP_FG = [".foregroundStyle(key.isRevoked ? DesignTokens.Color.ink(Self.area).opacity(0.55) : DesignTokens.StatusColor.arrivalGlow)"]
CHIP_ST = ["RoundedRectangle(cornerRadius: 2, style: .continuous) .stroke(key.isRevoked ? DesignTokens.Color.rule(Self.area) : Color.clear, lineWidth: 1)"]
META_F = [".font(.system(size: 10.5, design: .monospaced))"]
INK55 = [".foregroundStyle(DesignTokens.Color.ink(Self.area).opacity(0.55))"]
FAIL = [".foregroundStyle(DesignTokens.StatusColor.failure)"]
ISSUE_ST = ["RoundedRectangle(cornerRadius: 10, style: .continuous) .stroke(DesignTokens.Color.accent(Self.area), style: StrokeStyle(lineWidth: 1, dash: [4, 3]))"]
ISSUE_F = [".font(DesignTokens.Typography.font(size: DesignTokens.Typography.body, weight: .bold))"]
TOP_MD = [".padding(.top, DesignTokens.Spacing.md)"]
FIELD_PX = [".padding(.horizontal, DesignTokens.Spacing.md)"]
FIELD_PY = [".padding(.vertical, 10)"]
LBL_B = [".padding(.bottom, DesignTokens.Spacing.xs)"]
BTN_F = [".font(DesignTokens.Typography.font(size: DesignTokens.Typography.bodyLg, weight: primary ? .bold : .regular))"]
BTN_ST = ["RoundedRectangle(cornerRadius: 10, style: .continuous) .stroke(primary ? DesignTokens.Color.accent(Self.area) : DesignTokens.Color.rule(Self.area), lineWidth: 1)"]
BTN_BG = [".background(primary ? DesignTokens.Color.accent(Self.area) : DesignTokens.Color.card(Self.area))"]
BTN_FG = [".foregroundStyle(primary ? Color.white : DesignTokens.Color.ink(Self.area))"]
BTN_CLIP = [".clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))"]
NAVW = "시스템 내비게이션 바의 뒤로 버튼(`NavigationStack` 푸시 — 구현 수식 없음). 허용목록에 이 자리 항목이 아직 없다"
MODE = "「자동 응답 모드」 섹션(AC9)은 아직 구현되지 않았다(`_impl-map.md` `ApprovalKeysView.swift` 행)"
STONE = "구현은 영역 `ink` 55%(prMonitor 라이트 `#221F33`) — `S1`·`S5` 와 같은 규약이지만 두 항목의 대상에 승인 화면이 없다"
SHEETW = "발급 시트는 시스템 `.sheet`(`presentationDetents`) — 모서리·손잡이·아래 여백을 시스템이 그린다. 허용목록에 이 자리 항목이 아직 없다"
M = [
 # 헤더 — 시스템 내비게이션 바
 ("헤더", "bg-[var(--bg)]/95", "#EEEDF5/0.95", F, NAV, "시스템", "불일치", NAVW),
 ("헤더", "pb-2", "8", F, NAV, "시스템", "불일치", NAVW),
 ("헤더", "pt-3", "12", F, NAV, "시스템", "불일치", NAVW),
 ("헤더", "px-5", "20", F, NAV, "시스템", "불일치", NAVW),
 ("뒤로 버튼", "gap-1", "4", F, NAV, "시스템", "불일치", NAVW),
 ("뒤로 버튼", "text-[15px]", "15", F, NAV, "시스템", "불일치", NAVW),
 ("뒤로 버튼", "text-[var(--accent)]", "#5B4DB8", F, NAV, "시스템", "불일치", NAVW),
 ("뒤로 글리프", "height:16px", "16", F, NAV, "시스템", "불일치", NAVW),
 ("뒤로 글리프", "width:10px", "10", F, NAV, "시스템", "불일치", NAVW),
 # 본문
 ("본문", "pb-6", "24", F, [".padding(.bottom, DesignTokens.Spacing.xxl)"], "24", "일치", "스크롤 본문 아래 여백"),
 ("본문", "pt-3", "12", F, TOP_MD, "12", "일치", "스크롤 본문 위 여백(본문 `VStack` 의 `.padding(.top, …)`)"),
 ("본문", "px-5", "20", F, PADX, "20", "일치", "본문 좌우 여백"),
 ("본문", NA, "0", F, ["VStack(alignment: .leading, spacing: 0)"], "0", "기본값 일치", "본문·시트 세로 쌓기 간격 0 — 목업 블록 흐름(간격 클래스 없음)"),
 ("제목", "font-bold", "bold", F, TITLE, "bold", "일치", "「승인 게이트 설정」 굵기"),
 ("제목", "mb-3", "12", F, [".padding(.bottom, DesignTokens.Spacing.md)"], "12", "일치", "제목 아래 여백"),
 ("제목", "text-[18px]", "18", F, TITLE, "18", "일치", "제목 크기"),
 # 섹션 머리
 ("섹션 머리", "gap-2", "8", F, ["HStack(spacing: DesignTokens.Spacing.sm)"], "8", "일치", "막대 · 제목 · 선 사이 간격"),
 ("섹션 머리", "mb-2", "8", F, [".padding(.bottom, DesignTokens.Spacing.sm)"], "8", "일치", "섹션 머리 아래 여백"),
 ("섹션 머리", "mt-1", "4", NA, NA, NA, "불일치", "섹션 머리 위 여백 — 구현은 제목 아래 여백 12 뒤에 바로 놓는다(실효 12 vs 목업 12+4)"),
 ("섹션 막대", "bg-[var(--accent)]", "#5B4DB8", F, [".fill(DesignTokens.Color.accent(Self.area))"], "#5B4DB8", "일치", "막대 색"),
 ("섹션 막대", "h-3", "12", F, [".frame(width: 4, height: 12)"], "12", "일치", "막대 높이"),
 ("섹션 막대", "w-1", "4", F, [".frame(width: 4, height: 12)"], "4", "일치", "막대 폭"),
 ("섹션 제목", "font-bold", "bold", F, SEC_T, "bold", "일치", "「호출자 키」 굵기"),
 ("섹션 제목", "text-[11px]", "11", F, SEC_T, "11", "일치", "섹션 제목 크기(`captionXs`)"),
 ("섹션 제목", "text-[var(--accent)]", "#5B4DB8", F, ACC_FG, "#5B4DB8", "일치", "섹션 제목 색"),
 ("섹션 제목", "tracking-wide", "0.025em", NA, NA, NA, "불일치", "자간 수식 없음(목업 11 × 0.025em = 0.3)"),
 ("섹션 제목", "uppercase", "uppercase", NA, NA, NA, "불일치", "대문자 변환 수식 없음(`.textCase(.uppercase)` 부재 — 한글 문구라 렌더 차이는 없다)"),
 ("섹션 선", "bg-[var(--rule)]", "#D8D5E4", F, DIV, "#D8D5E4", "일치", "섹션 머리 오른쪽 1pt 선 색"),
 # 자동 응답 모드 — 미구현
 ("모드 카드", "bg-white", "#FFFFFF", NA, NA, NA, "불일치", MODE),
 ("모드 카드", "border", "1", NA, NA, NA, "불일치", MODE),
 ("모드 카드", "border-[var(--rule)]", "#D8D5E4", NA, NA, NA, "불일치", MODE),
 ("모드 카드", "mb-4", "16", NA, NA, NA, "불일치", MODE),
 ("모드 카드", "rounded-md", "6", NA, NA, NA, "불일치", MODE),
 ("모드 행(첫)", "px-3.5", "14", NA, NA, NA, "불일치", MODE),
 ("모드 행(첫)", "py-3", "12", NA, NA, NA, "불일치", MODE),
 ("모드 행(첫)", "text-[14px]", "14", NA, NA, NA, "불일치", MODE),
 ("모드 행", "border-[var(--rule)]", "#D8D5E4", NA, NA, NA, "불일치", MODE),
 ("모드 행", "border-t", "top 1", NA, NA, NA, "불일치", MODE),
 ("모드 행", "px-3.5", "14", NA, NA, NA, "불일치", MODE),
 ("모드 행", "py-3", "12", NA, NA, NA, "불일치", MODE),
 ("모드 행", "text-[14px]", "14", NA, NA, NA, "불일치", MODE),
 # 키 목록
 ("키 목록 카드", "bg-white", "#FFFFFF", F, CARD_BG, "#FFFFFF", "일치", "키 목록 카드 바탕(prMonitor `card` 라이트)"),
 ("키 목록 카드", "border", "1", F, RULE6, "1", "일치", "카드 외곽선 굵기"),
 ("키 목록 카드", "border-[var(--rule)]", "#D8D5E4", F, RULE6, "#D8D5E4", "일치", "카드 외곽선 색"),
 ("키 목록 카드", "rounded-md", "6", F, CLIP6, "6", "일치", "카드 라운드"),
 ("키 행(첫)", "px-3.5", "14", F, ROW_PX, "14", "일치", "키 행 좌우 여백"),
 ("키 행(첫)", "py-3", "12", F, ROW_PY, "12", "일치", "키 행 위아래 여백"),
 ("키 칩", "bg-[var(--soft)]", "#DDDAEB", F, [".background(key.isRevoked ? Color.clear : DesignTokens.Color.soft(Self.area))"], "#DDDAEB", "일치", "살아 있는 키 칩 바탕"),
 ("키 칩", "font-bold", "bold", F, CHIP_F, "bold", "일치", "키 칩 굵기"),
 ("키 칩", "px-2", "8", F, CHIP_PX, "8", "일치", "칩 좌우 여백"),
 ("키 칩", "py-0.5", "2", F, CHIP_PY, "2", "일치", "칩 위아래 여백"),
 ("키 칩", "rounded-[2px]", "2", F, CHIP_CLIP, "2", "일치", "칩 라운드"),
 ("키 칩", "text-[10.5px]", "10.5", F, CHIP_F, "10.5", "일치", "칩 글자 크기"),
 ("키 칩", "text-[var(--accent-strong)]", "#3D2F8E", F, CHIP_FG, "#3D2F8E", "일치", "살아 있는 키 칩 글자 색(`StatusColor.arrivalGlow` 라이트 = 목업 `--accent-strong`)"),
 ("폐기 버튼", "font-bold", "bold", F, [".font(DesignTokens.Typography.font(size: DesignTokens.Typography.captionSm, weight: .bold))"], "bold", "일치", "「폐기」 굵기"),
 ("폐기 버튼", "text-[12px]", "12", F, [".font(DesignTokens.Typography.font(size: DesignTokens.Typography.captionSm, weight: .bold))"], "12", "일치", "「폐기」 크기(`captionSm`)"),
 ("폐기 버튼", "text-[var(--destructive)]", "#9C3F2D", F, FAIL, "#9C3F2D", "일치", "「폐기」 색(`StatusColor.failure` 라이트 = 목업 `--destructive`)"),
 ("메타 줄", "mt-1.5", "6", F, ["VStack(alignment: .leading, spacing: 6)"], "6", "일치", "칩 줄 ↔ 메타 줄 간격"),
 ("메타 줄", "text-[10.5px]", "10.5", F, META_F, "10.5", "일치", "메타 줄 크기"),
 ("메타 줄", "text-stone-500", "#78716C", F, INK55, "#221F33/0.55", "불일치", STONE),
 ("키 행", "border-[var(--rule)]", "#D8D5E4", F, DIV, "#D8D5E4", "일치", "둘째 행부터 위 1pt 구분선 색(행 사이 `Rectangle` 한 수식)"),
 ("키 행", "border-t", "top 1", F, DIV, "top 1", "일치", "둘째 행부터 위 1pt 구분선(`index > 0` 일 때 행 위에 그린다)"),
 ("키 행", "px-3.5", "14", F, ROW_PX, "14", "일치", "키 행 좌우 여백"),
 ("키 행", "py-3", "12", F, ROW_PY, "12", "일치", "키 행 위아래 여백"),
 ("폐기된 키 행", "border-[var(--rule)]", "#D8D5E4", F, DIV, "#D8D5E4", "일치", "폐기된 키 행 위 구분선 색"),
 ("폐기된 키 행", "border-t", "top 1", F, DIV, "top 1", "일치", "폐기된 키 행 위 1pt 구분선"),
 ("폐기된 키 행", "opacity-60", "0.6", F, [".opacity(key.isRevoked ? 0.6 : 1)"], "0.6", "일치", "폐기된 키 행 전체 흐림"),
 ("폐기된 키 행", "px-3.5", "14", F, ROW_PX, "14", "일치", "키 행 좌우 여백"),
 ("폐기된 키 행", "py-3", "12", F, ROW_PY, "12", "일치", "키 행 위아래 여백"),
 ("폐기된 키 칩", "border", "1", F, CHIP_ST, "1", "일치", "폐기된 키 칩 외곽선 굵기"),
 ("폐기된 키 칩", "border-stone-300", "#D6D3D1", F, CHIP_ST, "#D8D5E4", "불일치", "폐기된 칩 외곽선 — 구현은 영역 `rule`"),
 ("폐기된 키 칩", "font-bold", "bold", F, CHIP_F, "bold", "일치", "칩 굵기"),
 ("폐기된 키 칩", "px-2", "8", F, CHIP_PX, "8", "일치", "칩 좌우 여백"),
 ("폐기된 키 칩", "py-0.5", "2", F, CHIP_PY, "2", "일치", "칩 위아래 여백"),
 ("폐기된 키 칩", "rounded-[2px]", "2", F, CHIP_CLIP, "2", "일치", "칩 라운드"),
 ("폐기된 키 칩", "text-[10.5px]", "10.5", F, CHIP_F, "10.5", "일치", "칩 글자 크기"),
 ("폐기된 키 칩", "text-stone-500", "#78716C", F, CHIP_FG, "#221F33/0.55", "불일치", STONE),
 ("폐기 시각", "text-[10.5px]", "10.5", F, META_F, "10.5", "일치", "「폐기됨 MM/dd」 크기"),
 ("폐기 시각", "text-stone-500", "#78716C", F, INK55, "#221F33/0.55", "불일치", STONE),
 ("발급 버튼", "border", "1", F, ISSUE_ST, "1", "일치", "점선 외곽선 굵기"),
 ("발급 버튼", "border-[var(--accent)]", "#5B4DB8", F, ISSUE_ST, "#5B4DB8", "일치", "점선 외곽선 색"),
 ("발급 버튼", "border-dashed", "dashed", F, ISSUE_ST, "dashed", "일치", "점선(`StrokeStyle(dash:)`)"),
 ("발급 버튼", "font-bold", "bold", F, ISSUE_F, "bold", "일치", "「+ 호출자 키 발급」 굵기"),
 ("발급 버튼", "mt-3", "12", F, TOP_MD, "12", "일치", "키 목록 ↔ 발급 버튼 간격"),
 ("발급 버튼", "py-3", "12", F, ROW_PY, "12", "일치", "발급 버튼 위아래 여백"),
 ("발급 버튼", "rounded-[10px]", "10", F, ISSUE_ST, "10", "일치", "발급 버튼 라운드"),
 ("발급 버튼", "text-[14px]", "14", F, ISSUE_F, "14", "일치", "발급 버튼 글자 크기(`body`)"),
 ("발급 버튼", "text-[var(--accent)]", "#5B4DB8", F, ACC_FG, "#5B4DB8", "일치", "발급 버튼 글자 색"),
 ("키 카드(발급 프레임)", "bg-white", "#FFFFFF", F, CARD_BG, "#FFFFFF", "일치", "시트 뒤 키 목록 카드 — 설정 프레임과 같은 `keyList`"),
 ("키 카드(발급 프레임)", "border", "1", F, RULE6, "1", "일치", "카드 외곽선 굵기"),
 ("키 카드(발급 프레임)", "border-[var(--rule)]", "#D8D5E4", F, RULE6, "#D8D5E4", "일치", "카드 외곽선 색"),
 ("키 카드(발급 프레임)", "px-3.5", "14", F, ROW_PX, "14", "일치", "키 행 좌우 여백"),
 ("키 카드(발급 프레임)", "py-3", "12", F, ROW_PY, "12", "일치", "키 행 위아래 여백"),
 ("키 카드(발급 프레임)", "rounded-md", "6", F, CLIP6, "6", "일치", "카드 라운드"),
 # 발급 시트
 ("발급 시트", "bg-white", "#FFFFFF", F, CARD_BG, "#FFFFFF", "일치", "시트 바탕(`ApprovalKeyIssueSheet` 의 `.background(…card…)`)"),
 ("발급 시트", "pb-10", "40", NA, NA, NA, "불일치", "시트 아래 여백 수식 없음 — 구현은 `Spacer(minLength: 0)` 로 남는 높이를 비운다"),
 ("발급 시트", "pt-3", "12", F, [".padding(.top, DesignTokens.Spacing.xl)"], "20", "불일치", "시트 위 여백 — 목업은 손잡이(4 + 아래 16)를 안에 그리고 12, 구현은 손잡이를 시스템이 그리고 20"),
 ("발급 시트", "px-5", "20", F, PADX, "20", "일치", "시트 좌우 여백"),
 ("발급 시트", "rounded-t-[22px]", "top 22", F, SHEET, "시스템", "불일치", SHEETW),
 ("시트 손잡이", "bg-stone-300", "#D6D3D1", F, SHEET, "시스템", "불일치", SHEETW),
 ("시트 손잡이", "h-1", "4", F, SHEET, "시스템", "불일치", SHEETW),
 ("시트 손잡이", "mb-4", "16", F, SHEET, "시스템", "불일치", SHEETW),
 ("시트 손잡이", "rounded-full", "full", F, SHEET, "시스템", "불일치", SHEETW),
 ("시트 손잡이", "w-9", "36", F, SHEET, "시스템", "불일치", SHEETW),
 ("시트 제목", "font-bold", "bold", F, [".font(DesignTokens.Typography.font(size: 17, weight: .bold))"], "bold", "일치", "시트 제목 굵기"),
 ("시트 제목", "text-[17px]", "17", F, [".font(DesignTokens.Typography.font(size: 17, weight: .bold))"], "17", "일치", "시트 제목 크기"),
 ("시트 라벨", "mt-3", "12", F, TOP_MD, "12", "일치", "라벨 위 여백(`label(_:)` 의 `.padding(.top, …)`)"),
 ("시트 라벨", "text-[11px]", "11", F, [".font(DesignTokens.Typography.font(size: DesignTokens.Typography.captionXs))"], "11", "일치", "「호출자 이름」·「키 원문」 크기"),
 ("시트 라벨", "text-stone-500", "#78716C", F, INK55, "#221F33/0.55", "불일치", STONE),
 ("이름 칸", "bg-[var(--bg)]", "#EEEDF5", F, [".background(DesignTokens.Color.surface(Self.area))"], "#EEEDF5", "일치", "이름 칸 바탕(prMonitor `surface`)"),
 ("이름 칸", "border", "1", F, RULE6, "1", "일치", "이름 칸 외곽선 굵기"),
 ("이름 칸", "border-[var(--rule)]", "#D8D5E4", F, RULE6, "#D8D5E4", "일치", "이름 칸 외곽선 색"),
 ("이름 칸", "mt-1", "4", F, LBL_B, "4", "일치", "라벨 ↔ 칸 간격(`label(_:)` 아래 여백 한 수식)"),
 ("이름 칸", "px-3", "12", F, FIELD_PX, "12", "일치", "칸 좌우 여백"),
 ("이름 칸", "py-2.5", "10", F, FIELD_PY, "10", "일치", "칸 위아래 여백"),
 ("이름 칸", "rounded-md", "6", F, RULE6, "6", "일치", "칸 라운드"),
 ("이름 칸", "text-[14px]", "14", F, [".font(.system(size: DesignTokens.Typography.body, design: .monospaced))"], "14", "일치", "이름 글자 크기(고정폭)"),
 ("원문 칸", "bg-[var(--soft)]", "#DDDAEB", F, [".background(DesignTokens.Color.soft(Self.area))"], "#DDDAEB", "일치", "원문 칸 바탕"),
 ("원문 칸", "border", "1", F, ACC6, "1", "일치", "원문 칸 외곽선 굵기"),
 ("원문 칸", "border-[var(--accent)]", "#5B4DB8", F, ACC6, "#5B4DB8", "일치", "원문 칸 외곽선 색"),
 ("원문 칸", "mt-1", "4", F, LBL_B, "4", "일치", "라벨 ↔ 칸 간격"),
 ("원문 칸", "px-3", "12", F, FIELD_PX, "12", "일치", "칸 좌우 여백"),
 ("원문 칸", "py-2.5", "10", F, FIELD_PY, "10", "일치", "칸 위아래 여백"),
 ("원문 칸", "rounded-md", "6", F, ACC6, "6", "일치", "칸 라운드"),
 ("원문 칸", "text-[12px]", "12", F, [".font(.system(size: DesignTokens.Typography.captionSm, design: .monospaced))"], "12", "일치", "원문 글자 크기(고정폭)"),
 ("경고 문구", "leading-relaxed", "1.625", NA, NA, NA, "불일치", "줄 높이 수식 없음"),
 ("경고 문구", "mt-2", "8", F, [".padding(.top, DesignTokens.Spacing.sm)"], "8", "일치", "원문 칸 ↔ 경고 간격"),
 ("경고 문구", "text-[11.5px]", "11.5", F, [".font(DesignTokens.Typography.font(size: 11.5))"], "11.5", "일치", "경고 크기"),
 ("경고 문구", "text-[var(--destructive)]", "#9C3F2D", F, FAIL, "#9C3F2D", "일치", "경고 색"),
 ("버튼 줄", "gap-2.5", "10", F, ["HStack(spacing: 10)"], "10", "일치", "「복사」 ↔ 「완료」 간격"),
 ("버튼 줄", "mt-4", "16", F, [".padding(.top, DesignTokens.Spacing.lg)"], "16", "일치", "경고 ↔ 버튼 줄 간격"),
 ("복사 버튼", "bg-[var(--accent)]", "#5B4DB8", F, BTN_BG, "#5B4DB8", "일치", "주 버튼 바탕"),
 ("복사 버튼", "border", "1", F, BTN_ST, "1", "일치", "주 버튼 외곽선 굵기"),
 ("복사 버튼", "border-[var(--accent)]", "#5B4DB8", F, BTN_ST, "#5B4DB8", "일치", "주 버튼 외곽선 색"),
 ("복사 버튼", "font-bold", "bold", F, BTN_F, "bold", "일치", "주 버튼 굵기"),
 ("복사 버튼", "py-3", "12", F, ROW_PY, "12", "일치", "버튼 위아래 여백"),
 ("복사 버튼", "rounded-[10px]", "10", F, BTN_CLIP, "10", "일치", "버튼 라운드"),
 ("복사 버튼", "text-[15px]", "15", F, BTN_F, "15", "일치", "버튼 글자 크기(`bodyLg`)"),
 ("복사 버튼", "text-white", "#FFFFFF", F, BTN_FG, "#FFFFFF", "일치", "주 버튼 글자 색"),
 ("완료 버튼", "bg-white", "#FFFFFF", F, BTN_BG, "#FFFFFF", "일치", "보조 버튼 바탕(`card`)"),
 ("완료 버튼", "border", "1", F, BTN_ST, "1", "일치", "보조 버튼 외곽선 굵기"),
 ("완료 버튼", "border-[var(--rule)]", "#D8D5E4", F, BTN_ST, "#D8D5E4", "일치", "보조 버튼 외곽선 색"),
 ("완료 버튼", "py-3", "12", F, ROW_PY, "12", "일치", "버튼 위아래 여백"),
 ("완료 버튼", "rounded-[10px]", "10", F, BTN_CLIP, "10", "일치", "버튼 라운드"),
 ("완료 버튼", "text-[15px]", "15", F, BTN_F, "15", "일치", "버튼 글자 크기"),
 ("완료 버튼", NA, "regular", F, BTN_F, "regular", "기본값 일치", "보조 버튼 굵기 — 목업은 굵기 클래스 없음(400)"),
 ("완료 버튼", NA, "#221F33", F, BTN_FG, "#221F33", "기본값 일치", "보조 버튼 글자 색 — 목업은 색 클래스 없이 프레임 `ink` 상속"),
 # 구현만 그리는 상태
 (NA, NA, NA, F, [".padding(.vertical, DesignTokens.Spacing.lg)"], "16", "목업 대기", "키 0건 안내·불러오는 중 진행 표시의 위아래 여백 — 목업에 빈 목록·불러오는 중 상태가 없다"),
 (NA, NA, NA, F, [".font(DesignTokens.Typography.font(size: DesignTokens.Typography.captionSm, weight: .semibold))"], "semibold", "목업 대기", "키 0건 안내 · 목록 조회 오류 배너 「다시 시도」 굵기 — 목업에 두 상태가 없다"),
]
S = [
 ("뒤로 「승인」", '<button class="flex items-center gap-1 text-[15px] text-[var(--accent)]">', F, "navigationBarTitleDisplayMode(.inline)", "일치", "승인 탭에서 푸시된 화면 — 시스템 내비게이션 바의 뒤로 버튼"),
 ("제목 「승인 게이트 설정」", '<h2 class="text-[18px] font-bold mb-3">승인 게이트 설정</h2>', F, 'Text("승인 게이트 설정")', "일치", "본문 첫 요소"),
 ("「자동 응답 모드」 섹션 머리", "자동 응답 모드</h2>", NA, NA, "불일치", MODE),
 ("모드 선택지 세 줄", '<input type="radio" name="mode" checked', NA, NA, "불일치", MODE),
 ("「호출자 키」 섹션 머리", "호출자 키</h2>", F, 'Text("호출자 키")', "일치", "제목 다음(구현은 자동 응답 섹션이 없어 바로 온다)"),
 ("키 목록 카드", '<div class="bg-white border border-[var(--rule)] rounded-md overflow-hidden">', F, "ForEach(Array(viewModel.keys.enumerated()), id: \\.element.id) { index, key in", "일치", "키마다 한 행, 둘째 행부터 위 구분선"),
 ("키 행 — 칩 · 「폐기」", '<button class="text-[12px] font-bold text-[var(--destructive)]">폐기</button>', F, 'Button("폐기") { revoking = key }', "일치", "칩 왼쪽 · 버튼 오른쪽, 아래 메타 줄"),
 ("폐기된 키 행 — 「폐기됨 MM/dd」", "폐기됨 10/03", F, "if let revoked = ApprovalKeyFormatting.revokedLabel(key) {", "일치", "폐기 버튼 자리에 폐기 시각"),
 ("「+ 호출자 키 발급」", "+ 호출자 키 발급</button>", F, 'Text("+ 호출자 키 발급")', "일치", "키 목록 아래"),
 ("시트 뒤 딤", 'style="background:rgba(34,31,51,.35)"', F, ".sheet(isPresented: $showsIssueSheet, onDismiss: { viewModel.finishIssuing() }, content: {", "일치", "시스템 시트가 뒤 화면을 흐린다"),
 ("발급 시트", '<div class="absolute z-50 inset-x-0 bottom-0 rounded-t-[22px] bg-white px-5 pt-3 pb-10">', F, ".sheet(isPresented: $showsIssueSheet, onDismiss: { viewModel.finishIssuing() }, content: {", "일치", "아래에서 올라오는 시트"),
 ("시트 손잡이", '<div class="w-9 h-1 rounded-full bg-stone-300 mx-auto mb-4"></div>', F, ".presentationDetents([.medium, .large])", "일치", "높이 단계가 둘이라 시스템 손잡이가 보인다"),
 ("시트 제목", '<div class="text-[17px] font-bold">', F, "Text(ApprovalKeyFormatting.issuedTitle)", "일치", "시트 첫 요소"),
 ("「호출자 이름」 라벨 · 칸", "호출자 이름</label>", F, 'label("호출자 이름") Text(issued.key.name)', "일치", "제목 다음"),
 ("「키 원문」 라벨 · 칸", "키 원문</label>", F, 'label("키 원문") Text(issued.secret)', "일치", "이름 칸 다음"),
 ("원문 경고", "이 화면을 닫으면 원문을 다시 볼 수 없습니다", F, "Text(ApprovalKeyFormatting.secretWarning)", "일치", "원문 칸 다음"),
 ("「복사」 · 「완료」", "복사</button>", F, 'sheetButton(copied ? "복사됨" : "복사", primary: true, id: "approval.keys.issued.copy")', "일치", "주 버튼 왼쪽 · 보조 버튼 오른쪽"),
]
