# 검산 블록 확장(추가만): 프레임 선택 · 하이픈 CSS 변수 · StatusColor 색 · rounded-t-[22px] · screen-approval SCREENS 항목
def patch_checker(t, rep):
    rep('''    {"slug": "screen-todo-work", "area": "work", "svg": True, "roots": ["absolute top-[54px] inset-x-0 px-5 pt-3 pb-3 z-20", "bottom-[88px] inset-x-0 overflow-y-auto scroll px-5 pt-2 pb-6 space-y-1.5"],
     "fwd": [("ios/PocketAide/Todos/TodoListView.swift", None, None),
             ("ios/PocketAide/Todos/TodoCheckBox.swift", None, None),
             ("ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift", "public var body", "public extension")]},
]''', '''    {"slug": "screen-todo-work", "area": "work", "svg": True, "roots": ["absolute top-[54px] inset-x-0 px-5 pt-3 pb-3 z-20", "bottom-[88px] inset-x-0 overflow-y-auto scroll px-5 pt-2 pb-6 space-y-1.5"],
     "fwd": [("ios/PocketAide/Todos/TodoListView.swift", None, None),
             ("ios/PocketAide/Todos/TodoCheckBox.swift", None, None),
             ("ios/Shared/Sources/DesignSystem/Components/ScreenHeader.swift", "public var body", "public extension")]},
    {"slug": "screen-approval", "area": "prMonitor", "svg": True, "frames": [7, 8],
     "roots": ["absolute top-[54px] inset-x-0 px-5 pt-3 pb-2 z-20", "absolute top-[104px] bottom-[88px]", "absolute z-50 inset-x-0 bottom-0 rounded-t-[22px]"],
     "fwd": [("ios/PocketAide/Approvals/ApprovalKeysView.swift", None, None)]},
]''')
    rep('''    root = dict(re.findall(r"--(\\w+):(#[0-9A-Fa-f]{6})", html))''',
        '''    root = dict(re.findall(r"--([\\w-]+):(#[0-9A-Fa-f]{6})", html))''')
    rep('''            super().__init__(); self.stack = []; self.depth = None; self.out = []''',
        '''            super().__init__(); self.stack = []; self.depth = None; self.out = []; self.frame = -1''')
    rep('''            if tag == "svg" and sc.get("svg"):''',
        '''            if "frame" in cls.split():
                self.frame += 1
            if tag == "svg" and sc.get("svg"):''')
    rep('''            elif any(r[6:] in st if r.startswith("style=") else r in cls for r in sc["roots"]):''',
        '''            elif any(r[6:] in st if r.startswith("style=") else r in cls for r in sc["roots"]) and self.frame in sc.get("frames", [self.frame]):''')
    rep('''        m = re.fullmatch(r"(?:\\[var\\(--(\\w+)\\)\\]|''', '''        m = re.fullmatch(r"(?:\\[var\\(--([\\w-]+)\\)\\]|''')
    rep('''"border-l-[3px]": "left 3",''', '''"border-l-[3px]": "left 3", "rounded-t-[22px]": "top 22",''')
    rep('''            if re.search(r"\\(\\.white\\)|Color\\.white\\b", joined):
                hexes.add("#FFFFFF")''', '''            if re.search(r"\\(\\.white\\)|Color\\.white\\b", joined):
                hexes.add("#FFFFFF")
            hexes |= {"#" + status[s] for s in re.findall(r"StatusColor\\.(\\w+)", joined) if s in status}''')
    rep('''const = dict(re.findall(r"static let (\\w+): CGFloat = ([\\d.]+)", tok))''',
        '''const = dict(re.findall(r"static let (\\w+): CGFloat = ([\\d.]+)", tok))
status = dict(re.findall(r"static let (\\w+) = adaptive\\(light: 0x([0-9A-F]{6})", tok))''')
