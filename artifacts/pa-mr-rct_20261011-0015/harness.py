# 사용: python3 harness.py <md> [dump]  — md 의 검산 블록을 실행; dump 면 screen-approval want 출력
import re, sys, pathlib
md = pathlib.Path(sys.argv[1]).read_text()
code = md.split("## 검산", 1)[1].split("python3 - <<'EOF'\n", 1)[1].split("\nEOF\n", 1)[0]
if len(sys.argv) > 2:
    code = code.split("# --- 대조 ---")[0] + '''
sc = [s for s in SCREENS if s["slug"] == "screen-approval"][0]
html, want, conv, asset, same = measure(sc)
for sig, toks in want.items():
    print(repr(sig))
    for t in sorted(toks):
        print("   ", t, "=>", conv(t))
'''
exec(compile(code, "check", "exec"), {"__name__": "__main__"})
