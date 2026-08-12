# 템플릿: AC ↔ E2E 1:1 정합성 (ac-e2e)

한 레포 안에서 **PRD의 Acceptance Criteria**와 **e2e 테스트 파일**을 **완전
1:1(전단사)** 로 유지하는 모델. AC 하나당 그 AC만 주검증하는 전용 파일 정확히
1개, 모든 파일은 정확히 1개의 AC에 대응. 자동화가 곤란한 AC는 예외 목록으로
등재해 관리한다. AC가 스펙(SSOT)이다.

**개수·범위 숫자는 판정 기준에 넣지 않는다.** AC와 e2e 파일은 계속 추가·삭제되므로,
"AC 55개" 같은 숫자를 목표나 판정 기준에 박으면 하나가 늘어난 순간 definition이
사실과 어긋난다. 숫자는 definition의 "등록 시점 현황"에만 **스냅샷으로
라벨링해** 두고, 판정은 개수 독립적 서술로 쓴다. 대상이 늘면 to-be 버전이 바뀌어
재평가가 트리거되고, 새 항목도 자동으로 판정 대상에 들어온다.

## 슬롯 표

대상 레포를 탐색해 확정한다. 확정 안 되는 값은 추측하지 말고 사용자에게 묻는다.

| 슬롯 | 의미 | 예 (dear-baby) |
|---|---|---|
| `{{REPO}}` | owner/repo | `dlddu/dear-baby` |
| `{{SLUG}}` | id·이름용 소문자 레포명 | `dear-baby` |
| `{{AC_DOCS_PATH}}` | AC 정의 문서 경로(to-be 버전 범위) | `docs/prd` |
| `{{AC_SCHEME}}` | AC ID **체계**(개수 아님) | `AC-NNN-NN` |
| `{{E2E_PATH}}` | e2e 루트(as-is 버전 범위) | `e2e` |
| `{{E2E_UNIT}}` | 매칭 단위(파일 유형·위치) | `e2e/maestro/` 최상위 `*.yaml` (Maestro flow) |
| `{{NON_UNIT}}` | e2e 루트 안이지만 매칭 단위가 아닌 것 | `e2e/maestro/subflows/`(재사용 헬퍼) |
| `{{MAPPING_SSOT}}` | AC↔파일 매핑을 기계적으로 확인하는 곳 | flow 헤더 주석의 검증 대상 선언 (또는 test-*.md의 `자동화:` 필드) |
| `{{EXCEPTION_SSOT}}` | AC 예외·비-AC 파일 등재 위치 | `docs/doc-tracker.md`의 "e2e flow 매핑" 섹션 |
| `{{NON_AC_TYPES}}` | 허용하는 비-AC 파일 유형 [선택] | 엔지니어링 노트(ENG-XXX) 검증, 스모크/인프라(health) |
| `{{EXCEPTION_HINTS}}` | 예외 목록 후보(자동화 곤란 AC 유형) | 푸시 실수신, 실물 배송, AI 산출물 품질, 외부 OAuth |
| `{{TOBE_EXTRA}}` | to-be 버전에 함께 묶을 파일 [선택] | `docs/doc-tracker.md` blob 해시(예외 등재 변경도 감지) |
| `{{INITIAL_STATE}}` | 등록 시점 **스냅샷**: 다대다 정도, 공백·묶음·중복 예시 | AC 55 vs flow 21, 묶음·중복 존재, 25개 AC 공백 |
| `{{NOW_ISO}}` | 등록 시각 (UTC ISO 8601) | `date -u +%Y-%m-%dT%H:%M:%SZ` |

## 모델 JSON 골격

```json
{
  "id": "tbm_{{SLUG}}-ac-e2e",
  "metadata": {
    "name": "{{SLUG}} AC ↔ E2E 1:1 정합성",
    "description": "{{REPO}}에서 {{AC_DOCS_PATH}}의 AC({{AC_SCHEME}})와 {{E2E_UNIT}}를 완전 1:1(AC 1개 ↔ 파일 1개)로 유지한다. 자동화가 곤란한 AC는 {{EXCEPTION_SSOT}} 예외 목록으로 관리하며, 등재된 AC는 drift가 아니다.",
    "tags": ["{{SLUG}}", "ac", "e2e", "consistency"],
    "createdAt": "{{NOW_ISO}}"
  },
  "definition": "<definition 본문 템플릿을 채워 넣기>",
  "toBe": {
    "dataSource": { "type": "github", "repository": "{{REPO}}", "ref": "main", "subPath": "{{AC_DOCS_PATH}}" },
    "versionScript": { "runtime": "bash", "code": "<to-be 스크립트>", "timeoutSeconds": 60 }
  },
  "asIs": {
    "dataSource": { "type": "github", "repository": "{{REPO}}", "ref": "main", "subPath": "{{E2E_PATH}}" },
    "versionScript": { "runtime": "bash", "code": "<as-is 스크립트>", "timeoutSeconds": 60 }
  },
  "checkPolicy": { "intervalSeconds": 3600 }
}
```

- e2e 도구 태그(예: `maestro`, `playwright`)를 tags에 추가해도 된다.
- `{{TOBE_EXTRA}}`를 쓰면(예외 등재가 AC 문서 밖에 있을 때 권장)
  `toBe.dataSource`의 `subPath`는 빼고 to-be 스크립트를 조합형으로 쓴다.

## versionScript

**to-be** (AC 문서 트리 해시 — `{{TOBE_EXTRA}}` 없으면 단일형, 있으면 조합형):

```bash
#!/usr/bin/env bash
# to-be = AC 정의 문서. {{AC_DOCS_PATH}} 하위 트리 해시만 사용 → 그 밖 변경은 무시된다.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
git rev-parse "HEAD:{{AC_DOCS_PATH}}"
```

```bash
#!/usr/bin/env bash
# to-be = AC 집합({{AC_DOCS_PATH}}) + 예외/매핑 등재({{TOBE_EXTRA}}).
# 이 둘 밖의 문서·코드 변경은 무시된다.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
p="$(git rev-parse "HEAD:{{AC_DOCS_PATH}}")"
t="$(git rev-parse "HEAD:{{TOBE_EXTRA}}")"
printf 'ac:%s reg:%s\n' "$p" "$t"
```

**as-is** (e2e 트리 해시):

```bash
#!/usr/bin/env bash
# as-is = e2e 테스트 구현. {{E2E_PATH}}/ 하위 트리 해시만 사용 → 그 밖 변경은 무시된다.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
git rev-parse "HEAD:{{E2E_PATH}}"
```

## definition 본문 템플릿

`[선택]` 표시 블록은 해당 없으면 통째로 삭제. `<!-- 지침 -->`은 모두 제거.

```markdown
# {{SLUG}} AC ↔ E2E 1:1 정합성

## 목표
`{{REPO}}` 레포에서 **PRD의 Acceptance Criteria(`{{AC_DOCS_PATH}}`의 {{AC_SCHEME}})** 와 **e2e 테스트({{E2E_UNIT}})** 를 **완전 1:1(전단사)** 로 유지한다: 예외 목록에 등재되지 않은 모든 AC는 자신을 주검증하는 파일을 정확히 1개 가지며, 모든 매칭 단위 파일은 정확히 1개의 AC를 주검증한다. 따라서 (AC 수 − 예외 수) = (AC 매칭 파일 수).

## 무엇이 "맞는 상태"인가 (SSOT)
- **AC의 SSOT**는 `{{AC_DOCS_PATH}}`다 (등록 시점: {{AC_SCHEME}}).
- **e2e 매칭 단위**는 {{E2E_UNIT}}다. {{NON_UNIT}}은 매칭 단위가 아니다.
- **AC ↔ 파일 매핑의 확인 지점**은 {{MAPPING_SSOT}}이며, 매핑은 여기서 기계적으로 확인 가능해야 한다.
- **예외·비-AC 매핑 등재의 SSOT**는 {{EXCEPTION_SSOT}}다.

## 1:1 매칭 규칙 (판정 기준)
1. **AC → 파일 유일**: 예외 목록에 없는 모든 AC는 자신을 주검증 대상으로 선언한 파일을 **정확히 1개** 가진다. 0개면 누락, 2개 이상이면 중복 — 둘 다 drift.
2. **파일 → AC 유일**: 모든 매칭 단위 파일은 **정확히 1개**의 AC만 주검증 대상으로 선언한다. 여러 AC를 묶은 파일은 분리 대상(drift). 셋업 과정에서 다른 AC의 화면·경로를 경유하는 것은 검증으로 세지 않는다 — 선언된 검증 대상만 센다.
3. **비-AC 파일 허용 유형**: AC 대신 {{NON_AC_TYPES}}를 검증 대상으로 선언한 파일은 허용하되, {{EXCEPTION_SSOT}}에 등재되어야 한다. 어디에도 매핑되지 않은 파일은 고아(drift). <!-- [선택] 비-AC 파일을 허용하지 않으면 "AC를 선언하지 않은 파일은 모두 고아(drift)다"로 교체 -->
4. **AC 예외 목록**: e2e로 자동 검증이 곤란한 AC(예: {{EXCEPTION_HINTS}})는 {{EXCEPTION_SSOT}}에 **AC별 사유와 대체 검증 수단**(수동 QA, 단위/통합 테스트 등)을 적어 등재한다. 등재된 AC는 파일이 없어도 drift가 아니다. 등재 없이 파일만 없는 AC는 drift.
5. **참조 무결성**: 파일이 존재하지 않는 AC를 참조하거나, 예외 목록이 존재하지 않는 AC를 등재하고 있으면 drift.
6. **집계 일치**: {{EXCEPTION_SSOT}}의 매칭 집계(AC 수·파일 수·공백 목록)가 1~5의 실제 상태와 일치해야 한다. <!-- [선택] 집계 표를 두지 않으면 삭제 -->

파일명을 AC 코드에 맞추는 규칙은 강제하지 않고 task 단계에서 정한다. 단, AC↔파일 매핑은 {{MAPPING_SSOT}}에서 기계적으로 확인 가능해야 한다.

## 충돌 시 기본 방향
AC(PRD)가 스펙(SSOT)이다.
- AC에 전용 파일이 없으면 → 전용 파일을 신설한다(여러 AC를 겸하는 기존 파일은 AC별로 분할).
- 한 AC에 파일이 여러 개면 → 전용 파일 1개로 병합한다.
- AC 없는 고아 파일이 나타나면 → 의도된 동작이면 PRD에 AC를 신설해 문서화하고, 아니면 파일을 제거하거나 허용 유형으로 재매핑한다.
어느 쪽인지는 각 task에서 판단(planner)하며, 변경 시 {{MAPPING_SSOT}}·{{EXCEPTION_SSOT}}를 함께 갱신한다.

## 추적 방식 (요약)
- **to-be** = github `{{REPO}}` `{{AC_DOCS_PATH}}` 하위 트리 해시<!-- [선택] TOBE_EXTRA 쓰면 --> + `{{TOBE_EXTRA}}` blob 해시 조합(AC 집합 또는 예외/매핑 등재가 바뀌면 변함).
- **as-is** = github `{{REPO}}` `{{E2E_PATH}}` 하위 트리 해시(파일 추가·수정·삭제 시 변함).
- 어느 한쪽 버전이 바뀌면 task가 생성되어 1:1 매칭을 재검증한다.

## 초기 상태 메모 (등록 시점 {{NOW_ISO}})
{{INITIAL_STATE}} 이 문단의 숫자는 **스냅샷일 뿐 판정 기준이 아니다** — AC나 파일이 추가·삭제되면 어느 한쪽 버전이 바뀌어 재평가가 트리거되고, 새 AC도 자동으로 1:1 판정 대상이 된다. 판정은 항상 개수 독립적 불변식 "(AC 수 − 예외 수) = (AC 매칭 파일 수)"로 한다. 현황 숫자 갱신은 각 task의 몫이다. <!-- 지침: 현재 AC 수 vs 파일 수, 묶음/중복/공백의 구체 예를 남긴다. 다대다면 "첫 task는 (1) 매핑 표·예외 목록 확정 (2) 묶음 분리·중복 정리 (3) 누락 AC의 파일 신설 또는 예외 등재를 다루게 된다 — 큰 초기 격차는 예상된 것"을 포함 -->

## 범위 밖 / 비고
- 단위·통합 테스트는 이 루프의 매칭 단위가 아니다(예외 목록의 "대체 검증 수단"으로 언급될 수는 있음).
- AC 문구와 e2e 단언 내용의 의미적 일치(테스트가 AC를 "제대로" 검증하는가)는 task 단계의 판단 사항이며, 이 모델의 버전 추적은 변경 감지까지만 담당한다.
- **문서 ↔ 구현 코드의 정합성은 별도 모델 `tbm_{{SLUG}}-docs-impl`이 담당**한다. 이 모델은 AC ↔ e2e 파일 매칭만 본다. <!-- [선택] 쌍 모델을 등록하지 않으면 삭제 -->
- <!-- 지침: 노이즈 비고 — to-be 범위 안의 무관한 변경(예: tracker의 다른 섹션 갱신)도 재검증을 트리거할 수 있음(무해), 노이즈가 크면 범위 축소 가능 — 을 대상에 맞게 1~2줄 작성 -->
```
