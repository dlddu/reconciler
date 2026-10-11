#!/usr/bin/env python3
"""rct_20261011-0013 재생: 투두 검색 자리표시 글자 색 → ink 45% (허용 S5). 사용: apply.py <pocket-aide checkout>"""
import re, sys, os
root = sys.argv[1]
def rd(p): return open(os.path.join(root, p), encoding='utf-8').read()
def wr(p, s): open(os.path.join(root, p), 'w', encoding='utf-8').write(s)
def rep(s, old, new, n=1):
    c = s.count(old); assert c == n, (old[:80], c); return s.replace(old, new)

NEWTF = 'TextField(area.searchPrompt, text: $viewModel.query, prompt: Text(area.searchPrompt).foregroundStyle(DesignTokens.Color.ink(tone).opacity(0.45)))'
# 1) swift
p = 'ios/PocketAide/Todos/TodoListView.swift'
s = rd(p)
s = rep(s, '            TextField(area.searchPrompt, text: $viewModel.query)\n', '            ' + NEWTF + '\n')
wr(p, s)

# 2) structure map rows
p = 'docs/mockups/_structure-map.md'
s = rd(p)
OLDQ = '`TextField(area.searchPrompt, text: $viewModel.query)`'
NEWQ_S = '`TextField(area.searchPrompt, text: $viewModel.query, prompt:`'
FONT_OLD = '`TextField(area.searchPrompt, text: $viewModel.query) .font(DesignTokens.Typography.font(size: DesignTokens.Typography.bodySm))`'
FONT_NEW = '`' + NEWTF + ' .font(DesignTokens.Typography.font(size: DesignTokens.Typography.bodySm))`'
s = rep(s, FONT_OLD, FONT_NEW, 2)
COLQ = '`' + NEWTF + '`'
s = rep(s, '| 검색 안내 | `text-stone-400` | #A8A29E | `ios/PocketAide/Todos/TodoListView.swift` | ' + OLDQ + ' | 시스템 | 불일치 | 자리표시 글자 색 — 구현은 시스템 placeholder 색(수식 없음) |',
        '| 검색 안내 | `text-stone-400` | #A8A29E | `ios/PocketAide/Todos/TodoListView.swift` | ' + COLQ + ' | #3D2A22/0.45 | 허용 S5 | 자리표시 글자 색 — 목업 stone, 구현 `prompt:` 에 개인 ink 45%(`S5` — 다크 목업은 같은 자리를 돋보기와 같은 `#9C7A6A` 로 그린다) |')
s = rep(s, '| 검색 안내 | `text-stone-400` | #A8A29E | `ios/PocketAide/Todos/TodoListView.swift` | ' + OLDQ + ' | 시스템 | 불일치 | 안내 글자 색 — 구현은 시스템 `TextField` 자리표시자 색 |',
        '| 검색 안내 | `text-stone-400` | #A8A29E | `ios/PocketAide/Todos/TodoListView.swift` | ' + COLQ + ' | #1E2A3A/0.45 | 허용 S5 | 안내 글자 색 — 목업 stone, 구현 `prompt:` 에 회사 ink 45%(`S5` — 다크 목업은 같은 자리를 돋보기와 같은 `#7A8AA0` 로 그린다) |')
# 표 S 의 검색 필드 행 인용(닫는 괄호가 사라졌다)
s = rep(s, '| 검색 필드 | `<!-- search` | `ios/PocketAide/Todos/TodoListView.swift` | ' + OLDQ, '| 검색 필드 | `<!-- search` | `ios/PocketAide/Todos/TodoListView.swift` | ' + NEWQ_S)
s = rep(s, '| 검색 필드 | `<!-- search -->` | `ios/PocketAide/Todos/TodoListView.swift` | ' + OLDQ, '| 검색 필드 | `<!-- search -->` | `ios/PocketAide/Todos/TodoListView.swift` | ' + NEWQ_S)
assert OLDQ not in s

# 3) 집계 재계산(행 판정에서 직접 센다 — 자매 PR 과 섞여도 맞는 값)
lines = s.split('\n')
counts = {}; cur = None
for ln in lines:
    m = re.match(r'^## 표 ([EMS]) — .*\(`(screen-[a-z-]+)`\)', ln)
    if m: cur = (m.group(2), m.group(1)); continue
    if ln.startswith('## '): cur = None; continue
    if cur and cur[1] in 'MS' and ln.startswith('|') and not ln.startswith('|---'):
        cells = [c.strip() for c in ln.strip('|').split('|')]
        j = cells[-2] if cur[1] == 'M' else cells[-2]
        if j in ('판정',): continue
        key = '허용' if j.startswith('허용') else j
        counts.setdefault(cur, {}).setdefault(key, 0); counts[cur][key] += 1
for scr in ('screen-todo-personal', 'screen-todo-work'):
    M = counts[(scr, 'M')]; S = counts[(scr, 'S')]
    for tbl, d in (('M', M), ('S', S)):
        for j, n in d.items():
            pat = re.compile(r'^\| `%s` \| %s \| %s \| \d+ \|$' % (scr, tbl, re.escape(j)), re.M)
            assert len(pat.findall(s)) == 1, (scr, tbl, j)
            s = pat.sub('| `%s` | %s | %s | %d |' % (scr, tbl, j, n), s)
    pat = re.compile(r'^(남은 구조·수치 drift\(`%s` [^)]*\): 표 M `불일치` )\d+(행 · `목업 대기` )\d+(행, 표 S `불일치` )\d+(행 · `목업 대기` )\d+(행\.)$' % scr, re.M)
    assert len(pat.findall(s)) == 1, scr
    s = pat.sub(lambda m: '%s%d%s%d%s%d%s%d%s' % (m.group(1), M.get('불일치', 0), m.group(2), M.get('목업 대기', 0), m.group(3), S.get('불일치', 0), m.group(4), S.get('목업 대기', 0), m.group(5)), s)
    print(scr, 'M', M, 'S', S)
wr(p, s)

# 4) _deviations S5
p = 'docs/mockups/_deviations.md'
s = rd(p)
s = rep(s, '투두 탭 본체는 화면마다 다섯 자리다 — 요약 줄(「7개 남음 · 4개 완료」·「12 OPEN · 8 DONE · …」) `text-stone-500`, 검색 돋보기 글리프 `text-stone-400`,',
           '투두 탭 본체는 화면마다 여섯 자리다 — 요약 줄(「7개 남음 · 4개 완료」·「12 OPEN · 8 DONE · …」) `text-stone-500`, 검색 돋보기 글리프 `text-stone-400`, 검색 자리표시 글자(「개인 영역만 검색…」·「회사 영역만 검색…」) `text-stone-400`,')
s = rep(s, '`ink(tone)` `.opacity(0.45)`(돋보기)·', '`ink(tone)` `.opacity(0.45)`(돋보기 · 검색 `TextField` 의 `prompt:`)·')
s = rep(s, '두 투두 화면의 다른 stone 자리는 대상이 아니다(`불일치` 로 남는다). 검색 안내 자리표시 글자는 구현이 시스템 자리표시자 색이고, 회사 백로그 섹션 제목',
           '두 투두 화면의 다른 stone 자리는 대상이 아니다(`불일치` 로 남는다). 회사 백로그 섹션 제목')
s = rep(s, '투두는 같은 다섯 자리를 개인 다크 톤 `#C9A595`(요약 줄 · 메타 줄 · 빈 상태 안내)·`#9C7A6A`(돋보기 · 완료 섹션 제목)로,\n  회사 다크 톤 `#A8B5C7`(요약 줄 · 메타 줄 · 빈 상태 안내)·`#7A8AA0`(돋보기 · 완료 섹션 제목)으로',
           '투두는 같은 여섯 자리를 개인 다크 톤 `#C9A595`(요약 줄 · 메타 줄 · 빈 상태 안내)·`#9C7A6A`(돋보기 · 검색 자리표시 글자 · 완료 섹션 제목)로,\n  회사 다크 톤 `#A8B5C7`(요약 줄 · 메타 줄 · 빈 상태 안내)·`#7A8AA0`(돋보기 · 검색 자리표시 글자 · 완료 섹션 제목)으로')
wr(p, s)
print('applied')
