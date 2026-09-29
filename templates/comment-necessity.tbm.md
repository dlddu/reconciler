# 템플릿: 주석 필요성 (comment-necessity)

한 레포에서 **주석은 필요 사유를 한 문장으로 댈 수 있는 것만 남긴다**를 기본으로 두는 모델.
정합 상태 = **판정 범위의 주석 중 필요 사유를 댈 수 없는 것이 없음**.

**필요성 시험**은 하나다 — *"이 주석을 지우면, 이 코드를 고치러 온 사람이 틀린 판단을 하거나 그 판단에
필요한 사실을 확인하는 데 상당한 비용을 치르는가?"* 예라면 그 결과(무엇을 틀리게 되는가, 무엇을 어디서
찾아야 하는가)를 적은 한 문장이 **필요 사유**다. 사유를 한 문장으로 댈 수 없으면 지운다 — 애매함은 보존의
근거가 아니다. 사유 없는 주석은 아무도 검증하지 않은 채 낡아 가고, 지운 주석은 git 이력에 남는다.

**언어 중립**이다. 판정 기준은 특정 언어의 주석 문법이나 문서화 관례가 아니라
"이 주석이 없으면 무엇을 잃는가"이며, 언어별로 달라지는 것은 주석 줄을 뽑는
패턴뿐이다 — 그 패턴도 모델마다 고르지 않고, 고정부의 언어군 표가 파일 이름으로 고른다.

> 2026-09-29 필요성 개정 전 유형 이름은 `comment-redundancy`(주석 비중복성, 복원 가능한 주석 제거)였다. 개정과
> 함께 모델 id도 `tbm_<slug>-comment-necessity`로 옮겼다(templates/README.md 「기존 모델과의 관계」).

## 판정 기준 (고정부)

- **사유는 결과를 말한다.** "중요함"·"참고용"·"나중에 필요할 수 있음"은 사유가 아니다 — 지웠을 때 누가
  무엇을 틀리게 되는지, 무엇을 어디서 다시 찾아야 하는지가 드러나야 한다.
- **시험 면제**: 기계가 읽는 주석(도구 공통 지시자 + `{{DIRECTIVE_EXTRA}}`). 지문·판정 모두에서 빠진다.
- **정책이 필요성을 선언한 부분**: doc 주석 수준(`{{DOC_COMMENT_POLICY}}`)이 요구하는 부분은 사유를 따로 대지
  않는다. 그 수준을 넘는 본문은 다시 시험을 받는다.
- **불필요의 흔한 유형**: 코드 재진술, 저장소 문서 재진술, PR·커밋 이력 재진술, 작업 흔적(누가·언제·끝난
  TODO·경위), 장식·구분선, 소감·추측, 주석 처리된 코드. 목록은 시험을 대신하지 않는다 — 목록에 없어도
  사유를 못 대면 지우고, 목록의 모양이어도 사유가 서면 남긴다.
- **더 나은 자리가 있으면 옮긴다.** 필요한 지식이라도 이름·타입·테스트·저장소 문서로 옮겨 코드가 스스로
  말하게 할 수 있으면 옮기고 주석은 지운다. 옮기는 변경은 같은 PR에 둔다.
- **틀린 주석**은 사유가 있으면 고치고, 없으면 지운다. 코드·문서와 어긋나면 주석이 틀린 것으로 본다.
- **유지는 기록으로 끝난다.** 남기는 주석(또는 같은 사유를 공유하는 묶음)마다 사유 한 문장을 그 패스의
  `passes/` 유지 목록에 적는다. 사유를 적지 않은 유지는 판정 완료가 아니다.

## 정책 디렉터리 (고정부)

정책은 파일 하나가 아니라 **`docs/comment-policy/` 디렉터리**에 역할별로 나눠 둔다. 판정 패스가
쌓일수록 한 파일에서는 정책 본문이 판정 기록에 묻히고, 이어 붙인 절이 엉뚱한 자리에 끼면서 구조가
무너진다. 세 부분은 바뀌는 리듬도 다르다 — 본문은 드물게 바뀌고, 원장은 패스마다 기계가 대조하는
상태로 갱신되며, 상세는 패스마다 새로 쌓인다.

```
docs/comment-policy/
├── README.md                  정책 본문 (진입점)
├── ledger.md                  판정 원장
└── passes/                    판정 상세 (패스 하나 = 파일 하나)
    └── <판정일>-<slug>.md
```

| 파일 | 담는 것 | 담지 않는 것 |
|---|---|---|
| `README.md` | 필요성 시험 · 유지 대상 · 운영 규칙 · 판정 절차 · 범위 밖(과 그 기계판 `comment-scope-exclude` 블록) · 지문 사각지대, `ledger.md`·`passes/`로 가는 링크 | 판정 이력, 개별 주석의 필요 사유 |
| `ledger.md` | 판정한 범위(파일 단위) · 그 범위의 현재 주석 줄 수 · 지문 · 판정 칸 · 결과 요약의 표, 원장 읽는 법 | 정책 규칙, 제거표·유지 목록 같은 상세, **손으로 적은 합계·잔량**, 경위·병합 재측정 노트 |
| `passes/<판정일>-<slug>.md` | 한 패스의 제거 목록(불필요 유형) · 유지 목록(주석·묶음마다 필요 사유 한 문장) · 이후의 증분 재판정 | 정책 규칙, 다른 패스의 기록 |

- **진입점은 `README.md`다.** 문서 허브나 다른 문서가 정책을 링크할 때는 이 파일을 가리킨다.
- `<판정일>`은 그 패스가 등재된 원장 행의 판정일, `<slug>`는 범위를 나타내는 소문자 kebab-case다.
  원장 행 순번을 쓰지 않는 것은 행이 합쳐지거나 빠질 때 파일 이름이 밀리지 않게 하기 위해서다.
  원장 행의 결과 칸은 요약 뒤에 해당 `passes/` 파일을 링크한다.
- 같은 범위의 **증분 재판정은 새 파일을 만들지 않고** 원래 패스 파일에 절을 더한다(원장 행이 같다).
- 유지한 주석이 없고 제거 내역이 결과 칸 요약과 task 기록으로 충분한 패스만 `passes/` 파일을 만들지 않는다 —
  유지가 하나라도 있으면 그 사유가 적힐 자리가 필요하다.
- 원장 게이트(아래 「원장 형식」)의 **파싱 대상은 `ledger.md`**다. 문서 본문 전체를 스캔하는 규칙
  (예: 줄 번호 좌표 금지)은 디렉터리 전체를 본다.
- 이 구조에서 벗어나야 하면 모델 definition의 "범위 밖 / 비고"에 이탈 내용과 사유를 적는다.

### 원장 형식 (고정부)

원장은 **행 단위 사실의 표**다. 여러 PR이 동시에 원장을 고쳐도 서로 다른 행만 건드리게 만드는 것이
이 형식의 목적이다 — 모든 PR이 같은 줄(합계·잔량 마커, 표 끝, 경위 노트)을 고치면 파일 집합이 서로소인
PR끼리도 반드시 충돌하고, 그 충돌을 피하려고 판정 슬라이스가 한두 행으로 쪼그라든다(2026-09 네 인스턴스
실측: planner 198건 중 66건이 자매 PR·합계 마커 충돌을 범위를 좁힌 근거로 적었다).

- **열**: 판정일 · 범위(파일 목록) · 현재 주석 줄 수 · 지문 · **판정** · 결과 요약(+`passes/` 링크).
  표면이 여럿이면(예: 줄 주석과 docstring) 표도 여럿이고 규칙은 같다.
- **판정** 칸은 그 행의 **현재 지문**에 대해 필요성 판정을 마쳤으면(유지분의 사유가 `passes/`에 적혔으면)
  `완료`, 아니면 `—`다. 진척은 산문이 아니라 이 칸이 진실이다. 게이트는 `완료`·`—`만 유효한 표기로 본다 —
  개정 전 표기(`①②③④` 등 복원 경로)는 옛 기준의 판정이므로 개정 뒤 첫 task가 `—`로 되돌린다.
- **범위 불변식**: 판정 대상 범위의 주석 줄을 가진 파일은 **정확히 한 행**에 속한다(행 사이 파일 집합은
  서로소, 합집합 = 실측 파일 집합). 행의 줄 수·지문은 실측과 같아야 한다.
- **합계·잔량을 저장하지 않는다.** 판정 완료 줄·행 수, 축별 미판정 수, 미등재 여부는 게이트가 표와 실측에서
  계산해 출력한다. 손으로 쓴 집계 값(마커·합계 행)은 원장에 두지 않는다.
- **판정하지 않은 주석을 들이는 PR**(자매 모델의 기능 PR 등)은 공유 값을 올리는 대신 **자기 파일의 행을
  더하거나 고치고 판정 칸을 `—`로** 둔다. 이미 판정된 행의 파일에 주석을 더하면 그 행의 줄 수·지문을
  갱신하고 판정 칸을 `—`로 되돌린다(증분만 판정했으면 그 결과를 적는다). 이것이 옛 「잔량 선언」의 자리다.
- **행 순서**는 범위의 첫 파일 경로의 사전순이다. 새 행을 표 끝에 덧붙이지 않는다 — 두 PR이 같은 자리에
  덧붙이면 충돌한다. 행은 순번이 아니라 **범위(첫 파일 경로)로 가리킨다**.
- **원장에는 표와 「읽는 법」 절만 둔다.** 경위, 병합·리베이스 재측정 기록, 인계 문단은 해당 패스의
  `passes/` 파일이나 PR 본문으로 간다.
- **게이트를 둔다**: `ledger.md`를 파싱해 위 불변식(파일 소속 유일·전수, 줄 수·지문 일치, 판정 칸 표기
  유효, 표·「읽는 법」 밖 산문 없음)을 CI에서 강제하고, 집계를 출력한다. 게이트는 미판정(`—`)을 실패로
  보지 않는다 — 판정하지 않았다는 사실을 행에 남기는 것은 정상이고, 그 행은 다음 판정 슬라이스가 가져간다.
- 게이트가 실측 파일 집합을 계산하는 **범위는 as-is 지문과 같은 규칙**(「범위 (고정부)」: 레포 전체 − 제외,
  같은 언어군, 같은 `comment-scope-exclude` 블록)을 쓴다. 게이트가 경로 목록을 따로 들고 있으면 둘이 갈라져,
  지문에는 있는데 원장 불변식은 모르는 파일이 생긴다.

## 범위 (고정부) — 레포 전체 − 제외

범위는 **포함 목록이 아니라 "레포 전체에서 제외를 뺀 것"**이다. 포함 목록은 레포가 자라며 생긴 새
디렉터리를 조용히 흘린다 — 그 안의 주석은 지문에 잡히지 않고, drift가 있어도 신호가 없다. 그리고
등록 시점의 판단이 경계로 굳어 모델마다 기준이 달라진다(같은 `scripts/`가 어느 모델에선 대상, 다른
모델에선 범위 밖이었다). 그래서 **무엇을 넣을지는 정하지 않고, 무엇을 뺄지만 원칙으로 정한다.**

제외는 다음 세 부류뿐이다. 이 밖의 이유(예: "CI 스크립트라서", "설정 파일이라서")로는 빼지 않는다.

| 부류 | 왜 빼는가 | 고정부가 빼는 것 | 대상 레포가 더 빼는 것 (예) |
|---|---|---|---|
| ① 문서 | 저장소 문서는 코드 사이의 주석이 아니라 별도 매체다. 정책 디렉터리도 여기 있어, 대상에 넣으면 정책이 자기 자신을 심사한다 | `docs/`, 모든 `*.md` | 문서 역할을 하는 다른 트리 |
| ② 편집 불가 | 지워도 재생성·재설치되어 판정할 의미가 없다 | 벤더·의존성·빌드 산출물 디렉터리, 락 파일, 머리 5줄에 `DO NOT EDIT`·`@generated` 표식이 있는 파일 | 표식 없는 codegen 출력 경로 |
| ③ 주석 문법 없음 | 주석이라는 개념이 없어 패턴이 무엇을 잡든 오탐이다 | 바이너리(`grep -I`), 아래 NONE 언어군(JSON·CSV·키 등 데이터) | 테스트 픽스처 데이터 |

- **고정부 제외**는 스크립트에 박혀 있고 유형 전체에 같다.
- **레포 고유 제외**는 모델이 아니라 **대상 레포의 `docs/comment-policy/README.md`**에 둔다. 본문의
  「범위 밖」 절 아래에 정보 문자열이 `comment-scope-exclude`인 코드 블록을 두고 한 줄에 ERE 하나를
  적는다. 줄마다 어느 부류(①②③)인지를 블록 바로 위 산문에 적는다 — 부류를 댈 수 없는 제외는 둘 수 없다.

  ````markdown
  ```comment-scope-exclude
  ^tests/e2e/fixtures/feeds/
  ```
  ````

  모델이 아니라 대상 레포에 두는 이유: 범위가 낡았을 때의 수정이 **대상 레포 PR로 끝나야** data plane이
  스스로 수렴시킬 수 있다(모델은 control plane만 고친다). 블록은 정책 디렉터리 안에 있으므로 블록이
  바뀌면 to-be 트리 해시도 바뀌어 재감지가 돈다.

### 언어군 (고정부)

파일은 **이름으로** 언어군 하나에 든다(위에서부터 처음 맞는 군). 견본 접미사(`.example`·`.sample`·
`.template`·`.tmpl`·`.tpl`·`.dist`·`.in`·`.j2`)는 떼고 본 확장자로 가른다.

| 언어군 | 대표 파일 | 주석 줄 ERE |
|---|---|---|
| C | Go·Rust·Java·Kotlin·Swift·C/C++·C#·JS/TS(JSX 포함)·CSS/SCSS·proto, `go.mod`, `tsconfig*.json`·`.jsonc` | `^[[:space:]]*(//\|/\*\|\*([[:space:]]\|$)\|\{/\*)` |
| HASH | Python·Ruby·Shell·Perl·R·YAML·TOML·Terraform/HCL·ini/cfg, `Makefile`·`*.mk`, `Dockerfile*`, `.gitignore`류, `.env*`, `requirements*.txt` | `^[[:space:]]*#` |
| DASH | SQL·Lua·Haskell·Elm·Ada | `^[[:space:]]*--` |
| MIXED | HTML·Vue·Svelte·Astro (마크업 안에 스크립트) | `^[[:space:]]*(<!--\|//\|/\*\|\*([[:space:]]\|$)\|\{/\*)` |
| MARKUP | XML·SVG·plist·XSD/XSL | `^[[:space:]]*<!--` |
| NONE | JSON·JSONL·CSV/TSV·TXT·avsc·스냅샷·골든·PEM/키·patch, `LICENSE`·`.nvmrc`류 | (스캔 안 함 — 제외 ③) |

- 확장자로 못 가른 텍스트 파일은 **첫 줄이 `#!`이면 HASH**로 본다(확장자 없는 스크립트).
- 그래도 남는 텍스트 파일은 **미분류**다. 미분류 파일은 경로가 지문에 들어가므로 생기거나 사라지면
  감지가 돈다 — 범위가 레포 성장을 따라가지 못할 때 조용히 새지 않게 하는 장치다. 해소는 두 갈래다:
  데이터·자산이면 대상 레포의 `comment-scope-exclude` 블록에 더하고(data plane이 PR로 끝낸다), 표에
  없는 **새 언어**면 이 표를 고치는 템플릿 커밋이 필요하다(control plane — task는 필요를 보고만 한다).
- 블록 주석 연속 줄은 `\*([[:space:]]|$)`로 잡는다. `\*[^/]`를 쓰지 않는 것은 포인터 역참조
  (`*p = x`)와 셸 `case`의 `*)`를 오탐하기 때문이다.
- `--`를 C 언어군에 넣지 않는 것은 CSS 커스텀 프로퍼티(`--bg-base`)와 PEM 경계 줄을 오탐하기 때문이다.
  언어군이 파일 이름으로 갈리므로 `--`는 DASH 파일에만 적용된다.
- 문자열 리터럴 안의 `//` 같은 오탐은 남는다. 결정적이기만 하면 무해하다 — 실제 판정은 task가 파일을
  읽어서 한다.

### 표면 (고정부) — L · D · E

언어군 패턴은 **줄머리** 주석만 잡는다. 그래서 지문은 표면 셋의 합이다. 하나라도 빠지면 그 표면의 주석만
바뀐 변경에 감지가 돌지 않고, task는 사각지대를 「범위 밖」으로 넘기는 것밖에 할 수 없다(2026-09-18~26
econ-opinion-monitor에서 20여 개 task가 docstring·줄 끝 주석을 같은 문장으로 되풀이해 넘긴 끝에 이 절이 생겼다).

| 표면 | 무엇 | 추출 | 해시 줄 |
|---|---|---|---|
| **L** 줄머리 주석 | 언어군 패턴에 걸리는 줄 | `grep` (위 표) | `경로:본문` |
| **D** docstring 본문 | Python 모듈·클래스·함수(async 포함) docstring, `inspect.cleandoc` 정리 후 줄 단위 | `ast` | `D:경로:본문` |
| **E** 줄 끝·줄 중간 주석 | 코드 **뒤에** 오는 주석 | Python `tokenize` · C 언어군(`//`·`/* */`, CSS는 `/* */`만)·HASH 일부(`#`)·DASH(`--`)는 문자열 상태를 따라가는 줄 스캐너 | `E:경로:본문` |

- **L이 원장이 세는 표면이다.** 첫 진단 줄 `lines=… files=… unclassified=…`은 L만 센다. D·E는 둘째 진단 줄
  `docstring=줄/파일 eol=줄/파일 unparsed=N`에 따로 나온다 — 원장은 표면마다 표를 둔다(「원장 형식」).
- 세 표면 모두 줄 번호·식별자 이름을 담지 않는다. 주석이 파일 안에서 옮겨 가거나 함수 이름이 바뀌어도 값은 그대로다.
- 기계가 읽는 주석은 E에서도 뺀다(같은 `DIRECTIVE`). 지시자 **뒤에 붙은 사유**(`# shellcheck disable=X # 이유`,
  `// eslint-disable-line r -- 이유`)는 사람의 문장이므로 E로 남긴다. 고정부가 더 빼는 것: `go.mod`·`go.work`의
  `// indirect`(go mod tidy가 쓰고 읽는다), Makefile 타깃 줄의 `## 설명`(`make help`가 읽는다).
- E를 보지 않는 파일: MIXED·MARKUP 언어군, 그리고 줄 중간 `#`이 주석이 아닌 HASH 파일(`Dockerfile*`·
  `Containerfile`·`.gitignore`류·`CODEOWNERS`·`.editorconfig`·`.env*`·ini/cfg/conf·`Caddyfile`·`*.sed`).
- 파싱에 실패한 파일(`ast`·`tokenize` 오류, UTF-8 아님)은 `X:` 줄로 해시에 들고 `unparsed`로 세진다.
  **`unparsed`가 0이 아니면 그 파일의 D·E가 빠진 것이므로 모델 건강 문제**다(control plane이 고친다).
- D·E 추출은 `python3`에 기댄다. 없으면 스크립트가 비0으로 끝난다 — 두 표면이 빠진 지문으로 조용히 떨어지지 않게.

## 슬롯 표

대상 레포를 탐색해 확정한다. 확정 안 되는 값은 추측하지 말고 사용자에게 묻는다. 범위와 언어별 패턴은
슬롯이 아니다(위 고정부).

| 슬롯 | 의미 | 예 (session-platform / Go·TS) | 예 (단일 언어 Python) |
|---|---|---|---|
| `{{REPO}}` | owner/repo | `dlddu/session-platform` | `dlddu/econ-opinion-monitor` |
| `{{SLUG}}` | id·이름용 소문자 레포명 | `session-platform` | `econ-opinion-monitor` |
| `{{DIRECTIVE_EXTRA}}` | 이 레포 고유의 기계가 읽는 주석(CI 파서 마커 등) — 지문·판정 **모두** 제외. 도구 공통 지시자(빌드 태그·린터·shebang·타입 체커 등)는 고정부에 이미 있다 | `검증 AC:\|mock-exception:\|mockup:` | `검증 시나리오:` |
| `{{REPO_EXCLUDE_SEED}}` | 등록 시 대상 레포 `comment-scope-exclude` 블록에 들어가야 할 줄과 부류 — 모델이 아니라 **첫 task의 범위**로 넘긴다 | (없음) | `^tests/fixtures/` (③ 픽스처 데이터) |
| `{{DOC_COMMENT_POLICY}}` | public 식별자 doc 주석·모듈 주석의 처리 수준 | 1줄 doc + 패키지 주석 유지 | docstring 유지, 본문 재진술은 제거 |
| `{{KEEP_KINDS}}` | 이 레포에서 흔한 필요 사유 — 사유를 대는 예시이지 시험 면제 목록이 아니다 | 커널·런타임 제약, 온클러스터 검증 결과, 동시성 계약, 함정 | 외부 API의 문서화되지 않은 동작, 수치 근거 |
| `{{SIBLING_MODEL}}` | 같은 트리를 보는 자매 모델 [선택] | `tbm_session-platform-docs-impl` | — |
| `{{SLICE_BUDGET}}` | task 하나가 가져가는 주석 줄 수 예산(definition 「판정 슬라이스」) | `400` | `400` |
| `{{INITIAL_STATE}}` | 등록 시점 현황 (주석 줄 수, 눈에 띄는 불필요 유형) | 주석 1,680줄 / 전체 18.7k LOC | — |
| `{{NOW_ISO}}` | 등록 시각 (UTC ISO 8601) | `date -u +%Y-%m-%dT%H:%M:%SZ` | 〃 |

## 모델 JSON 골격

```json
{
  "id": "tbm_{{SLUG}}-comment-necessity",
  "metadata": {
    "name": "{{SLUG}} 주석 필요성 (필요 사유 없는 주석 제거)",
    "description": "{{REPO}}의 주석은 필요 사유를 한 문장으로 댈 수 있는 것만 남긴다. 사유를 댈 수 없는 주석은 drift.",
    "tags": ["{{SLUG}}", "comments", "documentation", "consistency"],
    "createdAt": "{{NOW_ISO}}"
  },
  "definition": "<definition 본문 템플릿을 채워 넣기>",
  "toBe": {
    "dataSource": { "type": "github", "repository": "{{REPO}}", "ref": "main", "subPath": "docs/comment-policy" },
    "versionScript": { "runtime": "bash", "code": "<to-be 스크립트>", "timeoutSeconds": 60 }
  },
  "asIs": {
    "dataSource": { "type": "github", "repository": "{{REPO}}", "ref": "main" },
    "versionScript": { "runtime": "bash", "code": "<as-is 스크립트>", "timeoutSeconds": 120 }
  }
}
```

- `asIs.dataSource`에는 `subPath`를 두지 않는다. 범위는 레포 전체 − 제외이고, 스크립트가 진실이다.
- 주 언어 태그(`go`, `python`, `typescript` 등)를 tags에 추가해도 된다.

## versionScript

**to-be** — 정책 디렉터리의 지문. 정책 본문·원장·판정 상세가 바뀔 때만 값이 변하고 코드 변경에는
반응하지 않는다. 디렉터리가 **없는 상태도 유효한 관측**이므로 `absent`로 표현한다(빈 해시로
뭉개지 않는다).

```bash
#!/usr/bin/env bash
# to-be = 주석 정책 디렉터리(docs/comment-policy)의 tree hash. 아직 없으면 'absent'.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
git rev-parse --verify --quiet "HEAD:docs/comment-policy" || echo "absent"
```

- **`README.md`만 해싱하지 않는다.** 판정 패스는 주석을 하나도 지우지 않고 원장·상세만 바꾼 채
  끝날 수 있다("전부 유지"로 끝난 패스). as-is가 그대로인 그런 패스 뒤에도 to-be는 움직여야 미판정
  잔여를 다시 보는 감지가 돈다 — 본문만 보면 그 재감지 경로가 끊긴다.
- 단일 파일(예: `docs/comment-policy.md`)이나 다른 문서의 한 섹션에 정책을 두던 레포는 전환 직후
  to-be가 `absent`로 관측된다. 오류가 아니라 "정해진 자리에 정책이 없다"는 올바른 신호이고, 그
  task가 이 디렉터리로의 이전을 맡는다.

**as-is** — 코드에 실재하는 주석의 지문. **트리 해시를 쓰지 않는다**: 주석과
무관한 코드 변경에 반응하면 자매 모델(`{{SIBLING_MODEL}}`)과 중복 트리거되고
노이즈가 커진다. 「범위 (고정부)」대로 레포 전체에서 제외를 빼고, 언어군별로 주석 줄만
뽑아 정규화·정렬·해시한다. 슬롯은 `{{REPO}}`·`{{DIRECTIVE_EXTRA}}` 둘뿐이고 나머지는 **그대로** 붙인다
(런타임에 공유 라이브러리가 없으므로 인라인 복사가 원본이다).

```bash
#!/usr/bin/env bash
# as-is = 판정 대상 주석의 지문. 주석이 추가·수정·삭제되거나, 어느 언어군에도 들지 않는 텍스트 파일이
# 생기고 사라질 때만 값이 변한다. 트리 해시를 쓰지 않으므로 주석과 무관한 코드 변경에는 반응하지 않는다.
# 범위는 포함 목록이 아니라 「레포 전체 − 제외」다 — 새 디렉터리는 등록 없이 자동으로 스캔된다.
# 표면은 셋이다: L 줄머리 주석(언어군 패턴 — 원장이 세는 표면, 첫 진단 줄이 이것만 센다),
# D Python docstring 본문(ast), E 코드 뒤에 오는 줄 끝·줄 중간 주석(Python은 tokenize, 나머지는 줄 스캐너).
# 세 표면 모두 줄 번호·식별자 이름을 담지 않는다 — 주석이 파일 안에서 옮겨 가거나 함수 이름이 바뀌어도 값은 그대로다.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
export LC_ALL=C

# ── 제외 (템플릿 고정부) ── 세 부류만 제외한다.
#  ① 문서: 저장소 문서는 코드 사이의 주석이 아니라 별도 매체이고, 정책 디렉터리도 여기 있다.
#  ② 편집 불가: 벤더·의존성·빌드 산출물·락 파일, 그리고 생성 표식(DO NOT EDIT · @generated)이 머리에 있는 파일.
#  ③ 주석 문법이 없는 데이터·자산: 아래 NONE 언어군과 바이너리(grep -I).
FIXED_EXCLUDE='^docs/|\.md$|(^|/)(vendor|node_modules|dist|build|target|\.venv|venv|__pycache__|\.next|coverage)/|(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|go\.sum|uv\.lock|poetry\.lock|Cargo\.lock|Pipfile\.lock)$'
# ── 제외 (대상 레포 소유) ── docs/comment-policy/README.md 의 ```comment-scope-exclude 블록(한 줄에 ERE 하나).
# 레포 고유의 ①②③(예: codegen 출력 경로, 테스트 픽스처 데이터)은 모델이 아니라 이 블록에 적는다 —
# 정책 문서를 고치는 대상 레포 PR만으로 범위가 수렴하게 하기 위해서다. 블록이 없으면 고정부만 적용한다.
REPO_EXCLUDE=$(git show HEAD:docs/comment-policy/README.md 2>/dev/null \
  | awk '/^```comment-scope-exclude[[:space:]]*$/{f=1;next} f&&/^```/{f=0} f&&NF' | paste -sd'|' - || true)
EXCLUDE="$FIXED_EXCLUDE${REPO_EXCLUDE:+|$REPO_EXCLUDE}"
# 블록의 ERE가 깨졌으면 빈 범위로 조용히 뭉개지 않고 실패한다(감지 오류로 드러나게).
rc=0; printf '' | grep -E -- "$EXCLUDE" >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 2 ] || { echo "invalid ERE in comment-scope-exclude block" >&2; exit 1; }

# ── 기계가 읽는 주석 ── 지문·판정 모두에서 제외. 앞부분은 도구 공통(고정부), 뒤는 레포 고유(슬롯).
DIRECTIVE=':#!|//go:|nolint|eslint-|@ts-|prettier-ignore|/// <reference|istanbul ignore|c8 ignore|# ?noqa|# ?type:|# ?pragma|# ?pylint:|# ?fmt:|shellcheck |# ?syntax=|yaml-language-server:|{{DIRECTIVE_EXTRA}}'

# ── 언어군 (템플릿 고정부) ── 파일명 ERE → 주석 줄 ERE. 한 파일은 위에서부터 처음 맞는 군 하나에 든다.
# 견본 접미사(.example 등)는 떼고 본 확장자로 가른다(secret.yaml.example → # 언어군).
SUF='(\.(example|sample|template|tmpl|tpl|dist|in|j2))?$'
C_FILES='\.(go|rs|java|kt|kts|scala|groovy|gradle|swift|c|h|cc|cpp|hpp|cs|m|js|jsx|mjs|cjs|ts|tsx|mts|cts|css|scss|less|proto|jsonc)'"$SUF"'|(^|/)(go\.mod|go\.work|tsconfig[^/]*\.json|jsconfig[^/]*\.json|\.devcontainer/[^/]*\.json)$'
C_PATTERN='^[[:space:]]*(//|/\*|\*([[:space:]]|$)|\{/\*)'
HASH_FILES='\.(py|pyi|rb|sh|bash|zsh|fish|pl|r|ya?ml|toml|tf|tfvars|hcl|cfg|conf|ini|mk|dockerfile|nix|awk|sed)'"$SUF"'|(^|/)(Makefile|GNUmakefile|Dockerfile[^/]*|Containerfile|Caddyfile|\.gitignore|\.dockerignore|\.gitattributes|\.helmignore|\.editorconfig|\.env[^/]*|CODEOWNERS|requirements[^/]*\.txt)$'
HASH_PATTERN='^[[:space:]]*#'
DASH_FILES='\.(sql|lua|hs|elm|ada|adb)'"$SUF"
DASH_PATTERN='^[[:space:]]*--'
MIXED_FILES='\.(html?|vue|svelte|astro)'"$SUF"
MIXED_PATTERN='^[[:space:]]*(<!--|//|/\*|\*([[:space:]]|$)|\{/\*)'
MARKUP_FILES='\.(xml|svg|xhtml|plist|xsd|xsl)'"$SUF"
MARKUP_PATTERN='^[[:space:]]*<!--'
NONE_FILES='\.(json|jsonl|ndjson|csv|tsv|txt|avsc|snap|golden|pem|crt|key|pub|patch|diff|log|lock|sum|mod|map|http)'"$SUF"'|(^|/)(LICENSE[^/]*|NOTICE|AUTHORS|\.nvmrc|\.node-version|\.python-version|\.tool-versions|\.gitkeep|py\.typed)$'

LIST=$(git ls-files | grep -vE "$EXCLUDE" | sort | xargs -r -d '\n' grep -Il '' 2>/dev/null | sort || true)
GENERATED=$(printf '%s\n' "$LIST" | sed '/^$/d' | while IFS= read -r f; do
  head -n5 -- "$f" | grep -qE 'DO NOT EDIT|@generated' && printf '%s\n' "$f"; done || true)
[ -n "$GENERATED" ] && LIST=$(comm -23 <(printf '%s\n' "$LIST") <(printf '%s\n' "$GENERATED"))

REST="$LIST"; OUT=""; TAGGED=""
scan() {  # $1 = 파일명 ERE, $2 = 주석 줄 ERE(비면 스캔 없이 소거만), $3 = D·E 표면 스캐너 태그(비면 L만)
  local take; take=$(printf '%s\n' "$REST" | grep -E "$1" || true)
  REST=$(printf '%s\n' "$REST" | grep -vE "$1" || true)
  [ -n "$2" ] && [ -n "$take" ] && OUT+=$(printf '%s\n' "$take" | xargs -r -d '\n' grep -EH -e "$2" || true)$'\n'
  [ -n "${3:-}" ] && [ -n "$take" ] && TAGGED+=$(printf '%s\n' "$take" | sed "s/^/$3\t/")$'\n'
  return 0
}
scan "$C_FILES" "$C_PATTERN" C
scan "$HASH_FILES" "$HASH_PATTERN" HASH
scan "$DASH_FILES" "$DASH_PATTERN" DASH
scan "$MIXED_FILES" "$MIXED_PATTERN"
scan "$MARKUP_FILES" "$MARKUP_PATTERN"
scan "$NONE_FILES" ""
# 확장자로 못 가른 텍스트 파일: shebang이 있으면 # 언어군, 없으면 미분류.
SHEBANG=$(printf '%s\n' "$REST" | sed '/^$/d' | while IFS= read -r f; do
  head -c2 -- "$f" | grep -q '^#!' && printf '%s\n' "$f"; done || true)
if [ -n "$SHEBANG" ]; then
  OUT+=$(printf '%s\n' "$SHEBANG" | xargs -r -d '\n' grep -EH -e "$HASH_PATTERN" || true)$'\n'
  TAGGED+=$(printf '%s\n' "$SHEBANG" | sed 's/^/SHEBANG\t/')$'\n'
  REST=$(comm -23 <(printf '%s\n' "$REST" | sed '/^$/d') <(printf '%s\n' "$SHEBANG"))
fi
# 미분류는 지문에 경로로 넣는다 — 범위가 레포 성장을 따라가지 못하면 조용히 새지 않고 감지가 돈다.
# 해소는 두 갈래: 데이터·자산이면 대상 레포의 comment-scope-exclude 블록에, 새 언어면 템플릿 언어군에.
UNCLASSIFIED=$(printf '%s\n' "$REST" | sed '/^$/d')

# ── D·E 표면 (템플릿 고정부) ── L이 줄머리 패턴이라 못 보는 주석. MIXED·MARKUP 언어군과 줄 끝 `#`이 주석이
# 아닌 HASH 파일(Dockerfile·.gitignore류·.env·ini/cfg)은 E를 보지 않는다. 기계가 읽는 주석은 여기서도 뺀다.
# 파싱에 실패한 파일은 `X:` 줄로 남아 unparsed로 세진다 — 조용히 표면에서 빠지지 않게 하기 위해서다.
DE_PY=$(cat <<'PY'
import ast, io, os, re, sys, tokenize
DIR = re.compile(os.environ["DIRECTIVE"].replace(":#!|", "", 1))
SUF = re.compile(r"\.(example|sample|template|tmpl|tpl|dist|in|j2)$")
HASH_E_EXT = {"sh", "bash", "zsh", "fish", "rb", "pl", "r", "yaml", "yml", "toml", "tf", "tfvars", "hcl", "mk", "nix", "awk"}
MAKE = re.compile(r"^(Makefile|GNUmakefile)$|\.mk$")
OPEN_OK = set(" \t=([{,:")
out = []

def emit(kind, path, text):
    t = re.sub(r"\s+", " ", text).strip()
    if t and not (kind == "E" and DIR.search(t)):
        out.append(f"{kind}:{path}:{t}")

def rescue(path, comment, tail):
    # 지시자 줄 뒤에 붙은 사유(`# shellcheck disable=X # 이유`, `// eslint-disable-line r -- 이유`)는
    # L이 지시자와 함께 버리므로 E로 남긴다 — 사유는 기계가 읽지 않는 사람의 문장이다.
    if DIR.search(comment):
        m = re.search(tail, comment[1:])
        if m:
            emit("E", path, comment[1 + m.start():])

def py(path, src):
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        out.append(f"X:{path}:ast"); tree = None
    if tree is not None:
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                for line in (ast.get_docstring(n, clean=True) or "").splitlines():
                    emit("D", path, line)
    lines = src.splitlines()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                r, c = tok.start
                if lines[r - 1][:c].strip():
                    emit("E", path, tok.string)
                else:
                    rescue(path, tok.string, r"\s#\s")
    except (tokenize.TokenError, IndentationError, SyntaxError):
        out.append(f"X:{path}:tokenize")

def marker_lang(path, src, marker, quotes, make=False):
    # `#`·`--` 계열 줄 스캐너. 줄머리 주석은 L 몫이라 건너뛰고, 코드 뒤 주석만 E로 낸다.
    for line in src.splitlines():
        s = line.lstrip()
        if s.startswith(marker):
            rescue(path, s, r"\s" + re.escape(marker) + r"\s")
            continue
        q = None; i = 0
        while i < len(line):
            ch = line[i]
            if q:
                if ch == "\\" and q == '"':
                    i += 2; continue
                if ch == q:
                    q = None
            elif ch in quotes and (i == 0 or line[i - 1] in OPEN_OK):
                q = ch
            elif line.startswith(marker, i) and (marker != "#" or line[i - 1] in " \t"):
                c = line[i:]
                if not (make and re.match(r"^##( |$)", c)):
                    emit("E", path, c)
                break
            i += 1

def slash_lang(path, src, line_comments):
    # C 언어군 줄 스캐너. 문자열(" ' `)과 블록 주석 상태를 줄을 넘어 따라간다. ' "는 줄 끝에서 닫는다.
    q = None; block = False
    for line in src.splitlines():
        s = line.lstrip()
        if q in ('"', "'"):
            q = None
        lead = not block and q is None and s.startswith(("//", "/*", "*", "{/*"))
        if lead and s.startswith("//"):
            rescue(path, s[1:], r"\s(--|//)\s")
        i = 0; code = False
        while i < len(line):
            ch = line[i]; nx = line[i + 1] if i + 1 < len(line) else ""
            if block:
                if ch == "*" and nx == "/":
                    block = False; i += 2; continue
                i += 1; continue
            if q:
                if ch == "\\":
                    i += 2; continue
                if ch == q:
                    q = None
                i += 1; continue
            if ch == "\\":
                i += 2; code = True; continue
            if line_comments and ch == "/" and nx == "/":
                if code and not lead:
                    emit("E", path, line[i:])
                break
            if ch == "/" and nx == "*":
                end = line.find("*/", i + 2)
                if code and not lead:
                    emit("E", path, line[i:] if end < 0 else line[i:end + 2])
                if end < 0:
                    block = True; break
                i = end + 2; continue
            if ch in "\"'`":
                q = ch
            if not ch.isspace() and ch != "{":
                code = True
            i += 1

for rec in sys.stdin.read().splitlines():
    if "\t" not in rec:
        continue
    tag, path = rec.split("\t", 1)
    try:
        src = open(path, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        out.append(f"X:{path}:read"); continue
    name = SUF.sub("", os.path.basename(path))
    ext = name.rsplit(".", 1)[1].lower() if "." in name else ""
    if tag == "C":
        n = len(out)
        slash_lang(path, src, ext != "css")
        if name in ("go.mod", "go.work"):
            # `// indirect`는 go mod tidy가 쓰고 읽는 표식이다(기계가 읽는 주석).
            out[n:] = [o for o in out[n:] if not o.endswith(":// indirect")]
    elif tag == "DASH":
        marker_lang(path, src, "--", "'\"")
    elif tag in ("HASH", "SHEBANG"):
        if ext in ("py", "pyi") or (tag == "SHEBANG" and "python" in src.split("\n", 1)[0]):
            py(path, src)
        elif tag == "SHEBANG" or ext in HASH_E_EXT or MAKE.search(name) or name.startswith("requirements"):
            marker_lang(path, src, "#", "'\"", make=bool(MAKE.search(name)))
print("\n".join(out))
PY
)
DE=$(printf '%s' "$TAGGED" | sed '/^$/d' | DIRECTIVE="$DIRECTIVE" python3 -c "$DE_PY" | sed '/^$/d' | sort)

HITS=$({ printf '%s' "$OUT" | sed '/^$/d' | grep -vE "$DIRECTIVE" || true; } \
  | sed 's/[[:space:]]\+/ /g' | sed 's/^ //; s/ $//' | sort)
UNCL_LINES=$(printf '%s\n' "$UNCLASSIFIED" | sed '/^$/d; s/^/unclassified:/')
echo "lines=$(printf '%s' "$HITS" | grep -c . || true) files=$(printf '%s' "$HITS" | cut -d: -f1 | sort -u | grep -c . || true) unclassified=$(printf '%s' "$UNCLASSIFIED" | grep -c . || true)"
surf() { local s; s=$(printf '%s\n' "$DE" | grep "^$1:" || true)
  printf '%s/%s' "$(printf '%s' "$s" | grep -c . || true)" "$(printf '%s' "$s" | cut -d: -f2 | sort -u | grep -c . || true)"; }
echo "docstring=$(surf D) eol=$(surf E) unparsed=$(printf '%s\n' "$DE" | grep -c '^X:' || true)"
{ printf '%s\n' "$HITS"; printf '%s\n' "$UNCL_LINES"; printf '%s\n' "$DE"; } | sed '/^$/d' | sort | sha256sum | cut -d' ' -f1
```

- `grep -EH`는 줄 번호를 붙이지 않으므로 **같은 파일 안에서 주석이 이동해도 값이
  변하지 않는다**. 파일이 바뀌면 변한다 — 그때는 문맥이 실제로 달라진 것이다.
- `sort -u`가 아니라 `sort`다. 같은 문구가 여러 곳에 있어도 주석마다 따로 필요 사유를 대야 하므로,
  복사본이 하나 늘거나 줄어도 지문이 움직이게 중복을 접지 않는다.
- 해시 입력은 주석 줄과 `unclassified:<경로>` 줄의 합이다. 둘 다 **하나도 없는** 상태의 지문은 빈 입력
  sha256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`다 — 정상 레포에서 이 값이
  나오면 범위가 무너진 것이다.
- 감지기는 **stdout 전체**를 저장·비교한다. 진단 두 줄(`lines=… files=… unclassified=…`,
  `docstring=… eol=… unparsed=…`)도 비교에 들어가지만 모든 수는 해시 입력에서 파생되므로 해시와 따로 움직이지 않는다.
- 해시 입력은 L 주석 줄 · `unclassified:<경로>` 줄 · `D:`·`E:`·`X:` 줄의 합이다(「표면 (고정부)」).
- 레포 고유 제외 블록의 ERE가 깨졌으면 **비0으로 종료**한다. 빈 범위의 지문으로 조용히 떨어지면 모든
  주석이 한꺼번에 사라진 것처럼 보이기 때문이다.
- 기계가 읽는 주석은 지문에서도 뺀다. 정책 대상이 아닌데 지문에 넣으면 빌드 태그 하나가 늘 때마다
  재평가가 돈다. 고정부 목록에 없는 도구 지시자가 대상 레포에 쓰이면 `{{DIRECTIVE_EXTRA}}`에 더한다.

인스턴스화할 때 대상 레포에서 한 번 돌려 다섯 가지를 확인한다 — 같은 트리에서 **두 번
돌려 값이 같은가**(결정성), **코드만 바꿨을 때 값이 그대로인가**(무관한 변경에
둔감 — 문자열 안의 `#`·`//`, docstring 가진 함수의 이름 변경 포함), **주석만 바꿨을 때 값이 달라지는가**(민감 —
줄머리·docstring·줄 끝 주석 각각), **`unclassified=0`인가**, 그리고 **`unparsed=0`인가**. 세 번째가
깨지면 언어군 표가 그 언어의 주석을 잡지 못하고 있다는 뜻이다. 네 번째가 0이 아니면 등록 전에 그
파일들을 부류(①②③)로 가르거나 언어군을 더해 두고, 레포 고유 제외는 `{{REPO_EXCLUDE_SEED}}`로 적는다.

## definition 본문 템플릿

`[선택]` 표시 블록은 해당 없으면 통째로 삭제. `<!-- 지침 -->`은 모두 제거.

```markdown
# {{SLUG}} 주석 필요성

## 목표
`{{REPO}}`의 주석은 **필요 사유를 한 문장으로 댈 수 있는 것**만 남긴다. 사유를 댈 수 없는 주석은 drift다. 사유 없는 주석은 아무도 검증하지 않은 채 낡아 가고, 읽는 사람의 주의를 필요한 주석과 나눠 가진다.

## 무엇이 "맞는 상태"인가 (SSOT)
- **필요성 시험**: "이 주석을 지우면, 이 코드를 고치러 온 사람이 틀린 판단을 하거나 그 판단에 필요한 사실을 확인하는 데 상당한 비용을 치르는가?" 예라면 그 결과를 적은 한 문장이 필요 사유다(판정 기준의 SSOT는 reconciler `templates/comment-necessity.tbm.md`의 「판정 기준 (고정부)」 절).
- **정책의 SSOT**는 `docs/comment-policy/` 디렉터리다. 본문 `README.md`에 필요성 시험·유지 대상·doc 주석 수준·기계가 읽는 주석 목록을 두고, 판정 원장은 `ledger.md`, 판정 상세(제거 목록·유지 사유)는 `passes/<판정일>-<slug>.md`에 둔다. 세 역할을 한 파일에 섞지 않는다.
- **실제 상태의 SSOT**는 레포 전체에서 제외 세 부류(① 문서 ② 편집 불가 ③ 주석 문법 없음)를 뺀 범위의 주석이다. 레포 고유 제외는 정책 본문의 `comment-scope-exclude` 블록에 부류와 함께 둔다(범위 규칙의 SSOT는 reconciler `templates/comment-necessity.tbm.md`의 「범위 (고정부)」 절).
- 정합 상태 = 그 주석들 중 **필요 사유를 댈 수 없는 것이 없음**.

## 유지 대상 (이 밖은 제거)
- **기계가 읽는 주석** — 시험 면제. 지문·판정 모두에서 제외한다: 도구 공통 지시자(템플릿 고정부) + {{DIRECTIVE_EXTRA}}
- **doc 주석** — {{DOC_COMMENT_POLICY}}. 이 수준이 요구하는 부분은 사유를 따로 대지 않고, 수준을 넘는 본문은 시험을 받는다.
- **필요 사유가 있는 주석** — 이 레포에서 흔한 사유: {{KEEP_KINDS}}. 예시이지 면제가 아니다 — 이 종류라도 주석마다 사유를 댄다.

## 판정 규칙
- **사유를 한 문장으로 댈 수 없으면 지운다.** 애매함은 보존의 근거가 아니다. 지운 주석은 git 이력에 남는다.
- **사유는 결과를 말한다.** "중요함"·"참고용"·"나중에 필요할 수 있음"은 사유가 아니다.
- **불필요의 흔한 유형**: 코드 재진술, 저장소 문서 재진술, PR·커밋 이력 재진술, 작업 흔적(누가·언제·끝난 TODO·경위), 장식·구분선, 소감·추측, 주석 처리된 코드. 목록은 시험을 대신하지 않는다.
- **더 나은 자리가 있으면 옮긴다.** 필요한 지식이라도 이름·타입·테스트·저장소 문서로 옮겨 코드가 스스로 말하게 할 수 있으면 옮기고 주석은 지운다. 옮기는 변경은 같은 PR에 둔다.
- **틀린 주석**은 사유가 있으면 고치고, 없으면 지운다. 코드·문서와 어긋나면 주석이 틀린 것으로 본다.
- **유지는 기록으로 끝난다.** 남기는 주석(또는 같은 사유를 공유하는 묶음)마다 사유 한 문장을 `passes/` 유지 목록에 적는다. 사유를 적지 않은 유지는 판정 완료가 아니다.

## 판정 슬라이스 (task 하나가 가져가는 범위)
- **크기**: 판정 칸이 `완료`가 아닌 행을 파일 공유로 묶은 덩어리 단위로, 주석 **{{SLICE_BUDGET}}줄**까지 채워 가져간다. 덩어리 하나가 예산을 넘으면 그 덩어리만 가져간다. 예산보다 작게 끝내려면 그 사유(남은 대상이 없음, 파일이 겹치는 열린 PR 등)를 계획에 적는다.
- **좁히는 사유가 아닌 것**: 판단이 어려운 주석 — 사유를 대지 못하면 지우는 것으로 판정이 끝난다. 원장 합계·표 끝 충돌 — 원장 형식상 공유 줄이 없다. 파일이 실제로 겹치는 열린 PR이 있을 때만 그 덩어리를 뺀다.
- 한 번에 한 task만 점유하는 규칙은 그대로다. 대신 한 task가 크게 가져간다.

## 추적 방식 (요약)
- **to-be** = `docs/comment-policy/`의 tree hash. 없으면 `absent`. 정책 본문·원장·판정 상세가 바뀔 때만 변한다.
- **as-is** = 레포 전체 − 제외에서 주석을 세 표면(L 줄머리 주석 · D Python docstring 본문 · E 줄 끝·줄 중간 주석)으로 추출·정규화·정렬하고 미분류 파일 경로를 더한 sha256 지문. 원장이 세는 것은 L이고, D·E는 표면별 표로 따로 센다. 트리 해시를 쓰지 않으므로 주석과 무관한 코드 변경에는 반응하지 않고<!-- [선택] --> (자매 모델 `{{SIBLING_MODEL}}`과의 중복 트리거 회피)<!-- --> 주석이 추가·수정·삭제되거나 미분류 파일이 생기고 사라질 때만 변한다. 새 디렉터리는 등록 없이 자동으로 범위에 든다.

## 초기 상태 메모 (등록 시점 {{NOW_ISO}})
{{INITIAL_STATE}} <!-- 지침: 주석 줄 수와 전체 LOC, 눈에 띄는 불필요 유형(재진술·작업 흔적·장식 등)을 남긴다. 격차가 크면 "첫 task는 (1) `docs/comment-policy/` 정비 (2) 기존 주석의 필요성 판정을 다루게 된다 — 큰 초기 격차는 예상된 것"을 포함. {{REPO_EXCLUDE_SEED}}가 있으면 "첫 task가 README.md에 `comment-scope-exclude` 블록으로 옮긴다"와 그 줄·부류를 적는다 -->

## 범위 밖 / 비고
- 범위 밖은 「범위 (고정부)」의 제외 세 부류와 대상 레포 `comment-scope-exclude` 블록뿐이다. 그 밖의 경로(CI 워크플로·배포 매니페스트·검사 스크립트·설정 파일 포함)는 주석 문법이 있으면 대상이다.
- **문서·커밋 메시지 자체의 품질**은 이 모델이 보지 않는다. 다만 "더 나은 자리로 옮긴다"는 판정은 문서·이름을 고치는 작업을 낳을 수 있고, 그건 정상이다.
- **주석의 정확성**을 따로 검사하지 않는다. 판정 중 틀린 주석을 만나면 「판정 규칙」대로 고치거나 지운다.
- 특정 주석의 필요 사유가 성립하는지의 최종 판단은 각 task(planner)의 몫이고, 이 모델은 필요성 시험과 유지 대상이라는 **판단 기준**만 고정한다.
- 지문의 사각지대(템플릿 「표면 (고정부)」 기준): MIXED·MARKUP 파일과 줄 중간 `#`이 주석이 아닌 HASH 파일의 줄 끝 주석, `*`로 시작하지 않는 블록 주석 연속 줄, Python 밖의 docstring 성격 문자열, 줄 스캐너의 문자열 추적 한계(JS 정규식 리터럴, JSX 텍스트의 따옴표·`//`, Rust 수명 표기). 오탐·누락 모두 결정적이다.
- **표면 소유권.** 표면과 도구 공통 지시자는 템플릿 고정부(control plane)라 data plane task가 고칠 수 없다. task는 위 목록에 **없는** 사각지대가 실제로 발화했거나 등재된 사각지대가 판정을 틀리게 만든 실례가 있을 때만 그것을 기록하고, **이미 등재된 사각지대를 task마다 다시 인계하지 않는다.**
```
