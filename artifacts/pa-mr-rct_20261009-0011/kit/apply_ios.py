import sys
def rep(path, old, new):
    s=open(path).read(); c=s.count(old); assert c==1,(path,c,old[:60]); open(path,'w').write(s.replace(old,new))
SH='ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift'
rep(SH,"""    private let subtitle: String?
    private let bottomPadding: CGFloat""","""    private let subtitle: String?
    private let subtitleIdentifier: String
    private let subtitleMonospaced: Bool
    private let bottomPadding: CGFloat""")
rep(SH,"""        subtitle: String? = nil,
        bottomPadding: CGFloat = DesignTokens.Spacing.sm,
        @ViewBuilder labelAccessory""","""        subtitle: String? = nil,
        subtitleIdentifier: String = "screen.header.subtitle",
        subtitleMonospaced: Bool = false,
        bottomPadding: CGFloat = DesignTokens.Spacing.sm,
        @ViewBuilder labelAccessory""")
rep(SH,"""        self.subtitle = subtitle
        self.bottomPadding""","""        self.subtitle = subtitle
        self.subtitleIdentifier = subtitleIdentifier
        self.subtitleMonospaced = subtitleMonospaced
        self.bottomPadding""")
rep(SH,"""                        .foregroundStyle(DesignTokens.Color.ink(area).opacity(0.55))
                        .accessibilityIdentifier("screen.header.subtitle")""","""                        .foregroundStyle(DesignTokens.Color.ink(area).opacity(0.55))
                        .monospaced(subtitleMonospaced)
                        .accessibilityIdentifier(subtitleIdentifier)""")
TL='ios/PocketAide/Todos/TodoListView.swift'
rep(TL,"""    private var header: some View {
        ScreenHeader(area: tone, title: area.screenTitle) {
            VStack(alignment: .trailing, spacing: 6) {
                Button {
                    sheetMode = .create
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 14, weight: .bold))
                        .frame(width: 36, height: 36)
                        .background(DesignTokens.Color.card(tone))
                        .overlay(Circle().stroke(DesignTokens.Color.rule(tone), lineWidth: 1))
                        .clipShape(Circle())
                        .foregroundStyle(DesignTokens.Color.ink(tone))
                }
                .accessibilityIdentifier("\\(idPrefix).add.button")
                Text(area.summary(open: viewModel.openCount, done: viewModel.doneCount))
                    .font(summaryFont)
                    .foregroundStyle(DesignTokens.Color.ink(tone).opacity(0.55))
                    .accessibilityIdentifier("\\(idPrefix).summary")
            }
        }
    }

    private var summaryFont: Font {
        let base = DesignTokens.Typography.font(size: DesignTokens.Typography.captionXs, weight: .semibold)
        return area == .work ? base.monospaced() : base
    }
""","""    private var header: some View {
        ScreenHeader(
            area: tone,
            title: area.screenTitle,
            titleSize: 28,
            subtitle: area.summary(open: viewModel.openCount, done: viewModel.doneCount),
            subtitleIdentifier: "\\(idPrefix).summary",
            subtitleMonospaced: area == .work,
            bottomPadding: DesignTokens.Spacing.md
        ) {
            EmptyView()
        } trailing: {
            Button {
                sheetMode = .create
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 18, weight: .bold))
                    .frame(width: 40, height: 40)
                    .background(DesignTokens.Color.accent(tone))
                    .clipShape(Circle())
                    .foregroundStyle(.white)
            }
            .accessibilityIdentifier("\\(idPrefix).add.button")
        }
    }
""")
rep(TL,"""            TextField(area.searchPrompt, text: $viewModel.query)
                .font(DesignTokens.Typography.font(size: DesignTokens.Typography.body))""","""            TextField(area.searchPrompt, text: $viewModel.query)
                .font(DesignTokens.Typography.font(size: DesignTokens.Typography.bodySm))""")
rep(TL,"""        .padding(.horizontal, DesignTokens.Spacing.md)
        .padding(.vertical, 10)
        .background(DesignTokens.Color.card(tone))""","""        .padding(.horizontal, DesignTokens.Spacing.md)
        .padding(.vertical, DesignTokens.Spacing.sm)
        .background(DesignTokens.Color.card(tone))""")
rep(TL,"""                .stroke(DesignTokens.Color.rule(tone), lineWidth: 1)
        )
        .padding(.horizontal, DesignTokens.Spacing.xl)
        .padding(.bottom, DesignTokens.Spacing.sm)""","""                .stroke(DesignTokens.Color.rule(tone), lineWidth: 1)
        )
        .padding(.horizontal, DesignTokens.Spacing.xl)
        .padding(.bottom, DesignTokens.Spacing.md)""")
print("ios ok")
