# 템플릿: 주석 비중복성 (comment-redundancy)

한 레포에서 **주석은 코드·문서·이력 어느 쪽으로도 복원되지 않는 지식만 담는다**를
기본으로 두고, 읽는 사람이 다른 곳에서 확인할 수 있는 내용은 주석에 남기지 않는
모델. 정합 상태 = **주석에 남아 있는 내용의 집합 ∩ 복원 가능한 내용의 집합 = ∅**.

복원 경로는 넷이다 — **코드 자체 · 저장소 문서 · PR(제목·본문·리뷰 코멘트) ·
커밋 메시지**. 이 중 어디서든 확인되는 내용을 주석이 되풀이하면 drift다. 되풀이된
주석은 값이 없을 뿐 아니라, 원본만 고쳐질 때 조용히 거짓이 되기 때문이다.

**언어 중립**이다. 판정 기준은 특정 언어의 주석 문법이나 문서화 관례가 아니라
"이 문장이 다른 곳에서 복원되는가"이며, 언어별로 달라지는 것은 주석 줄을 뽑는
패턴(슬롯)뿐이다.

## 슬롯 표

대상 레포를 탐색해 확정한다. 확정 안 되는 값은 추측하지 말고 사용자에게 묻는다.

| 슬롯 | 의미 | 예 (session-platform / Go·TS) | 예 (단일 언어 Python) |
|---|---|---|---|
| `{{REPO}}` | owner/repo | `dlddu/session-platform` | `dlddu/econ-opinion-monitor` |
| `{{SLUG}}` | id·이름용 소문자 레포명 | `session-platform` | `econ-opinion-monitor` |
| `{{POLICY_SSOT}}` | 주석 정책의 위치 (파일 또는 파일 내 섹션) | `docs/comment-policy.md` | `CONTRIBUTING.md`의 "주석" 섹션 |
| `{{SCAN_SCOPE}}` | 판정 대상 소스 경로 목록 | `control-plane data-plane web/src web/e2e` | `src tests` |
| `{{SCOPE_EXCLUDE}}` | 스캔 제외 ERE (생성 코드·벤더·서드파티) | `(^|/)(vendor|node_modules|dist)/\|\.pb\.go$` | `(^\|/)(\.venv\|migrations)/` |
| `{{COMMENT_PATTERN}}` | 주석 줄 탐지 ERE (아래 언어군 표 참고) | `^[[:space:]]*(//\|/\*\|\*[^/])` | `^[[:space:]]*#` |
| `{{DIRECTIVE_EXCLUDE}}` | 기계가 읽는 주석 — 지문·판정 **모두** 제외 | `//go:\|nolint\|eslint-\|@ts-\|검증 AC:\|mock-exception:` | `#!\|# noqa\|# type:\|# pragma` |
| `{{DOC_COMMENT_POLICY}}` | public 식별자 doc 주석·모듈 주석의 처리 수준 | 1줄 doc + 패키지 주석 유지 | docstring 유지, 본문 재진술은 제거 |
| `{{KEEP_KINDS}}` | 이 레포에서 "복원 불가"로 인정하는 주석 종류 | 커널·런타임 제약, 온클러스터 검증 결과, 동시성 계약, 함정 | 외부 API의 문서화되지 않은 동작, 수치 근거 |
| `{{OUT_OF_SCOPE}}` | 대상이 아닌 것 | 라이선스 헤더, 생성 코드, `docs/`의 마크다운 본문 | 〃 (대상에 맞게) |
| `{{SIBLING_MODEL}}` | 같은 트리를 보는 자매 모델 [선택] | `tbm_session-platform-docs-impl` | — |
| `{{INITIAL_STATE}}` | 등록 시점 현황 (주석 줄 수, 눈에 띄는 중복 유형) | 주석 1,680줄 / 전체 18.7k LOC | — |
| `{{NOW_ISO}}` | 등록 시각 (UTC ISO 8601) | `date -u +%Y-%m-%dT%H:%M:%SZ` | 〃 |

### 언어군별 `{{COMMENT_PATTERN}}` 기본값

지문의 목적은 **결정성과 변경 민감도**이지 완전한 파서가 아니다. 오탐은 트리거를
조금 늘릴 뿐 판정을 왜곡하지 않는다 — 실제 판정은 task가 파일을 읽어서 한다.

| 언어군 | 주석 시작 | ERE |
|---|---|---|
| C 계열 (Go·Rust·Java·C/C++·C#·JS/TS·Swift·Kotlin) | `//`, `/* */` | `^[[:space:]]*(//\|/\*\|\*[^/])` |
| 스크립트·설정 (Python·Ruby·Shell·Perl·R·YAML·Terraform) | `#` | `^[[:space:]]*#` |
| SQL·Haskell·Lua·Ada | `--` | `^[[:space:]]*--` |
| Lisp 계열·ini·어셈블리 | `;` | `^[[:space:]]*;` |
| 마크업 (HTML·XML·Vue·Svelte) | `<!-- -->` | `^[[:space:]]*<!--` |
| 혼합 레포 | 위의 합집합 | `^[[:space:]]*(//\|#\|--\|/\*\|\*[^/]\|<!--)` |

주의:
- `#`는 C 전처리기·shebang과, `*`는 포인터 역참조·곱셈 줄바꿈과 겹친다.
  겹치는 것들은 `{{DIRECTIVE_EXCLUDE}}`나 `{{SCOPE_EXCLUDE}}`로 걸러낸다.
- 문자열 리터럴 안의 `//` 같은 오탐은 남는다. 결정적이기만 하면 무해하다.
- 줄 끝 주석(`x := 1 // 이유`)은 줄 시작 패턴에 걸리지 않는다. 그 층위까지 보려면
  패턴에 `[^[:space:]].*//`를 더하되, 오탐이 크게 늘어난다는 점을 감수한다.

## 모델 JSON 골격

```json
{
  "id": "tbm_{{SLUG}}-comment-redundancy",
  "metadata": {
    "name": "{{SLUG}} 주석 비중복성 (복원 가능한 주석 제거)",
    "description": "{{REPO}}의 주석은 코드·저장소 문서·PR·커밋 메시지 어느 쪽으로도 복원되지 않는 지식만 담는다. 복원 가능한 내용을 되풀이하는 주석은 drift.",
    "tags": ["{{SLUG}}", "comments", "documentation", "consistency"],
    "createdAt": "{{NOW_ISO}}"
  },
  "definition": "<definition 본문 템플릿을 채워 넣기>",
  "toBe": {
    "dataSource": { "type": "github", "repository": "{{REPO}}", "ref": "main", "subPath": "{{POLICY_SSOT의 파일 경로}}" },
    "versionScript": { "runtime": "bash", "code": "<to-be 스크립트>", "timeoutSeconds": 60 }
  },
  "asIs": {
    "dataSource": { "type": "github", "repository": "{{REPO}}", "ref": "main", "subPath": "{{SCAN_SCOPE}}" },
    "versionScript": { "runtime": "bash", "code": "<as-is 스크립트>", "timeoutSeconds": 120 }
  },
  "checkPolicy": { "intervalSeconds": 3600 }
}
```

- `{{SCAN_SCOPE}}`가 단일 디렉터리가 아니면 `asIs.dataSource.subPath`는 생략하고
  스크립트가 경로 목록을 직접 다룬다(스크립트가 진실).
- 주 언어 태그(`go`, `python`, `typescript` 등)를 tags에 추가해도 된다.

## versionScript

**to-be** — 주석 정책의 지문. 정책이 바뀔 때만 값이 변해야 한다. 문서가 **없는
상태도 유효한 관측**이므로 `absent`로 표현한다(빈 해시로 뭉개지 않는다).

*A. 전용 문서형* — 정책이 파일 하나를 통째로 차지할 때:

```bash
#!/usr/bin/env bash
# to-be = 주석 정책 문서의 blob hash. 아직 없으면 'absent'.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
git rev-parse --verify --quiet "HEAD:{{POLICY_SSOT}}" || echo "absent"
```

*B. 섹션 추출형* — 정책이 더 큰 문서(CONTRIBUTING 등) 안의 한 섹션일 때. 섹션이
사라지거나 제목이 바뀌면 추출이 비어 `absent`가 되고, 이는 "정책이 사라졌다"는
올바른 drift 신호다:

```bash
#!/usr/bin/env bash
# to-be = <문서>의 "<섹션 제목>" 섹션만 추출한 sha256. 같은 문서의 다른 섹션 변경은 무시된다.
set -euo pipefail
export LC_ALL=C
SEC=$(git show "HEAD:{{POLICY_SSOT의 파일}}" 2>/dev/null \
  | awk '/^## <섹션 제목>/{f=1; print; next} f && /^## /{exit} f{print}')
if [ -z "$SEC" ]; then echo "absent"; exit 0; fi
printf '%s' "$SEC" | sha256sum | cut -d' ' -f1
```

**as-is** — 코드에 실재하는 주석의 지문. **트리 해시를 쓰지 않는다**: 주석과
무관한 코드 변경에 반응하면 자매 모델(`{{SIBLING_MODEL}}`)과 중복 트리거되고
노이즈가 커진다. 주석 줄만 뽑아 정규화·정렬·해시한다.

```bash
#!/usr/bin/env bash
# as-is = 판정 대상 주석의 지문. 주석이 추가·수정·삭제될 때만 값이 변한다.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
export LC_ALL=C
PATTERN='{{COMMENT_PATTERN}}'
DIRECTIVE='{{DIRECTIVE_EXCLUDE}}'
HITS=$({ git ls-files -- {{SCAN_SCOPE}} | grep -vE '{{SCOPE_EXCLUDE}}' | sort \
        | xargs -r grep -EH "$PATTERN" || true; } \
  | grep -vE "$DIRECTIVE" \
  | sed 's/[[:space:]]\+/ /g' | sed 's/^ //; s/ $//' \
  | sort)
echo "lines=$(printf '%s' "$HITS" | grep -c . || true) files=$(printf '%s' "$HITS" | cut -d: -f1 | sort -u | grep -c . || true)"
printf '%s' "$HITS" | sha256sum | cut -d' ' -f1
```

- `grep -EH`는 줄 번호를 붙이지 않으므로 **같은 파일 안에서 주석이 이동해도 값이
  변하지 않는다**. 파일이 바뀌면 변한다 — 그때는 문맥이 실제로 달라진 것이다.
- `sort -u`가 아니라 `sort`다. 같은 문구가 여러 곳에 복사되는 것 자체가 이 유형이
  보려는 신호이므로 중복을 접지 않는다.
- 주석이 **하나도 없는** 상태의 지문은 빈 입력 sha256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`로 고정된다.
- 마지막 줄만 버전이므로 `lines=…` 진단 줄은 값에 영향을 주지 않는다.
- `{{DIRECTIVE_EXCLUDE}}`는 지문에서도 빼야 한다. 기계가 읽는 주석은 정책 대상이
  아닌데, 지문에 넣으면 빌드 태그 하나가 늘 때마다 재평가가 돈다.

인스턴스화할 때 대상 레포에서 한 번 돌려 세 가지를 확인한다 — 같은 트리에서 **두 번
돌려 값이 같은가**(결정성), **코드만 바꿨을 때 값이 그대로인가**(무관한 변경에
둔감), **주석만 바꿨을 때 값이 달라지는가**(민감). 세 번째가 깨지면 패턴이 그 언어의
주석을 잡지 못하고 있다는 뜻이다.

## definition 본문 템플릿

`[선택]` 표시 블록은 해당 없으면 통째로 삭제. `<!-- 지침 -->`은 모두 제거.

```markdown
# {{SLUG}} 주석 비중복성

## 목표
`{{REPO}}`의 주석은 **코드·저장소 문서·PR·커밋 메시지 어느 쪽으로도 복원되지 않는 지식**만 담는다. 읽는 사람이 다른 곳에서 확인할 수 있는 내용을 주석이 되풀이하면 drift다. 되풀이된 주석은 값이 없을 뿐 아니라, 원본만 고쳐질 때 조용히 거짓이 되기 때문이다.

## 무엇이 "맞는 상태"인가 (SSOT)
- **복원 경로는 넷**이다: ① 코드 자체 ② 저장소 문서 ③ PR 제목·본문·리뷰 코멘트 ④ 커밋 메시지. 이 중 어디서든 확인되는 내용은 주석의 자리가 아니다.
- **정책의 SSOT**는 {{POLICY_SSOT}}다. 유지 대상({{KEEP_KINDS}})과 doc 주석 수준({{DOC_COMMENT_POLICY}}), 기계가 읽는 주석 목록을 담는다.
- **실제 상태의 SSOT**는 {{SCAN_SCOPE}} 범위의 주석이다.
- 정합 상태 = 그 주석들 중 **복원 가능한 내용을 담은 것이 없음**.

## 유지 대상 (이 밖은 제거 후보)
- **기계가 읽는 주석** — 빌드 태그, 린터 지시자, CI 파서 마커. 정책 대상이 아니며 판정에서 제외한다: {{DIRECTIVE_EXCLUDE}}
- **doc 주석** — {{DOC_COMMENT_POLICY}}
- **복원 불가능한 지식** — {{KEEP_KINDS}}

## 충돌 시 기본 방향
코드·문서·이력이 SSOT다. 주석이 그것들과 어긋나면 **주석이 틀린 것으로 본다** — 주석은 아무도 검증하지 않기 때문이다.

- 복원 가능하면 → 주석을 지운다. 원본이 부실해서 복원이 안 되는 것이면, 주석을 남기는 대신 **원본(문서·이름·커밋 메시지)을 고친다**.
- 복원 불가능하면 → 남긴다.
- **애매하면 남긴다.** 이 유형은 제거 쪽으로 기울지 않는다. 중복 주석의 비용은 작지만, 유일한 지식을 담은 주석을 지우면 그 지식은 어디에도 남지 않는다. 비용이 비대칭이므로 판단이 갈리는 주석은 보존하고 그 사실을 task에 남긴다.

## 추적 방식 (요약)
- **to-be** = {{POLICY_SSOT}}의 지문. 없으면 `absent`. 정책이 바뀔 때만 변한다.
- **as-is** = {{SCAN_SCOPE}}에서 주석 줄만 추출·정규화·정렬한 sha256 지문. 트리 해시를 쓰지 않으므로 주석과 무관한 코드 변경에는 반응하지 않고<!-- [선택] --> (자매 모델 `{{SIBLING_MODEL}}`과의 중복 트리거 회피)<!-- --> 주석이 추가·수정·삭제될 때만 변한다.

## 초기 상태 메모 (등록 시점 {{NOW_ISO}})
{{INITIAL_STATE}} <!-- 지침: 주석 줄 수와 전체 LOC, 눈에 띄는 중복 유형(문서 재진술·선언 재진술·작업 흔적 등)을 남긴다. 격차가 크면 "첫 task는 (1) 정책 문서 정비 (2) 기존 주석의 복원 가능성 판정을 다루게 된다 — 큰 초기 격차는 예상된 것"을 포함 -->

## 범위 밖 / 비고
- {{OUT_OF_SCOPE}}는 대상이 아니다.
- **문서·커밋 메시지 자체의 품질**은 이 모델이 보지 않는다. 다만 "주석을 지우려면 원본을 고쳐야 한다"는 판정은 그 원본을 고치는 작업을 낳을 수 있고, 그건 정상이다.
- **주석의 정확성**(코드와 맞는가)도 이 모델의 판정 표면이 아니다. 이쪽은 중복만 본다 — 다만 되풀이된 주석이 낡아 틀려 있으면 그것은 제거 근거를 강화한다.
- 특정 주석이 "정말 복원 가능한지"의 최종 판단은 각 task(planner)의 몫이고, 이 모델은 복원 경로 넷과 유지 대상이라는 **판단 기준**만 고정한다.
- 지문의 사각지대: `{{COMMENT_PATTERN}}`에 걸리지 않는 주석(줄 끝 주석, 언어 특유 문법)은 보이지 않는다. 그런 주석이 늘어나는 레포라면 패턴을 넓히는 것을 다음 task에서 다룬다.
```
