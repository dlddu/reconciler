# 템플릿: PR 수동 승인 라우팅 (pr-manual-approval)

한 레포에서 **어떤 PR이 사람의 승인을 받아야 하는가**를 기계 판정기가 가르고, 그 판정이
**코드베이스가 자라는 동안에도 낡지 않게** 유지하는 모델. 판정기는 관점(aspect)마다 하나씩
있고, PR이 그 관점의 위험에 **닿지 않았다고 확인되면** head 커밋에 commit status
`review/<관점>` = success를 붙인다. 닿았을 가능성이 있으면 아무것도 붙이지 않는다 — 사람이 본다.

정합 상태 = **불변식 1 ∧ 불변식 2**.

- **불변식 1 (라우팅 1:1)** — 정책이 선언한 수동 승인 관점의 집합 == 판정기로 구현된 관점의 집합,
  그리고 관점마다 정책의 규칙 ID 집합 == 판정기의 규칙 ID 집합. 판정기 없는 관점도, 정책에 없는
  판정기도 drift다. **"사람 승인이 필요한 케이스"를 추적·관리하는 축**이다.
- **불변식 2 (신선도)** — 규칙이 지목하는 경로가 실재하고, 코드의 위험 표면이 규칙이나 의도적
  제외로 빠짐없이 덮이며, 제외의 재개 조건이 아직 발동하지 않았고, 재검토 기한이 지나지 않았다.
  **수동 승인 프로세스가 outdated 되지 않도록 추적·관리하는 축**이다.

판정기 규칙은 "지금의 코드"를 전제로 쓰인다(파일 이름, 크레이트 이름, 디렉터리 배치). 코드가
옮겨가도 판정기는 조용히 success를 계속 붙이므로, 낡은 판정기는 **실패하지 않고 새는** 방식으로
망가진다. 불변식 2가 그 누수를 잡는 장치다.

## 프로세스 원칙 (고정부)

이 유형의 정체성. 등록하는 모든 관점의 판정기가 지켜야 하며, 불변식 1의 판정 항목(R3)이 된다.

| ID | 원칙 | 이유 |
|---|---|---|
| P1 긍정 확인 | 판정기는 **success만** 붙인다. "사람 리뷰 필요"는 status의 **부재**로 표현한다(failure·pending을 신호로 쓰지 않는다). | 기본값이 "사람이 본다"여야 판정기가 죽거나 안 돌았을 때도 안전하다. |
| P2 fail-closed | 판정이 불가능하면(파싱 실패·git 오류) status 없이 끝난다. | 판정 불가를 통과로 뭉개지 않는다. |
| P3 base 실행 | 판정기는 **PR이 아니라 base 쪽 코드**로 돈다(`pull_request_target` + base 체크아웃). PR의 코드는 실행하지 않고 diff 입력(데이터)으로만 쓴다. | PR이 판정기를 고쳐 자기에게 success를 붙이지 못하게. |
| P4 자기 참조 | 판정기·그 워크플로를 바꾸는 PR은 **그 관점의 사람 리뷰 대상**이다(규칙으로 명시). | P3 때문에 판정기 변경 PR은 옛 판정기로 판정된다 — 그 변경 자체는 사람 눈에 올린다. |
| P5 미탐 비대칭 | 판단이 갈리면 **사람 리뷰 쪽으로** 기운다(규칙을 넓게 잡는다). | 미탐(위험한데 success)은 운영 사고, 오탐(무해한데 리뷰)은 리뷰 한 번이다. |
| P6 명명 | status context는 `{{STATUS_PREFIX}}<관점>` 한 가지 형태를 쓴다. | as-is 지문이 판정기를 이 형태로 찾는다. |

## 정책 문서 (고정부)

정책은 **대상 레포의 `{{POLICY_SSOT}}` 한 파일**에 둔다. 판정기 코드의 헤더 주석이 아니라 문서가
SSOT다 — 헤더에만 있으면 판정기를 고치는 사람만 보고, 무엇이 사람 승인 대상인지 묻는 사람은 찾을
곳이 없다. 판정기는 규칙 ID로 정책을 **참조**하고 규칙 본문을 되풀이하지 않는다.

문서는 다음 절을 가진다(제목 문구는 레포 언어에 맞춰도 되나 절의 역할과 **기계 판독 블록의
형식**은 고정이다).

1. **원칙** — P1~P6을 이 레포 기준으로 한 단락. 이 템플릿으로의 링크로 대신해도 된다.
2. **관점 레지스트리** — 표. 관점 하나 = 행 하나.

   | 관점 | status context | 판정기 | 워크플로 | 보는 위험 | 규칙 | 소비자 | 마지막 재검토 | 다음 재검토 |
   |---|---|---|---|---|---|---|---|---|

   - `규칙`: 규칙 ID 범위(예: `D1~D6`). 관점마다 **서로 다른 접두**를 쓴다.
   - `소비자`: 이 status를 읽는 쪽 — branch protection·ruleset의 required check, 자동 머지 봇,
     또는 "사람 관례(리뷰어가 status를 보고 생략)". 소비자가 없으면 판정기는 장식이다.
   - `다음 재검토`: ISO 날짜, **마지막 재검토로부터 최장 90일**.
3. **관점별 규칙** — 관점마다 `###` 절 하나에 다음을 둔다.
   - 규칙 표: `ID | 대상 | 이유`. 판정기는 같은 ID를 판정 근거 라벨로 쓴다.
   - **위험 표면 블록** — as-is 지문이 읽는 기계 판독 블록. 이 관점의 위험이 코드에 나타나는 모양.
     ````text
     ```surface <관점>
     scope: <git ls-files 경로 목록, 공백 구분>
     exclude: <제외 ERE — 생략 가능>
     ere: <위험 신호 토큰 ERE>
     ```
     ````
   - **앵커 블록** — 규칙이 이름으로 지목하는 경로(글롭 허용), 한 줄에 하나.
     ````text
     ```anchors <관점>
     backend/migrations
     deploy/**/pvc*.yaml
     ```
     ````
   - **의도적 제외 표**: `대상 | 사유 | 재개 조건 | 소관`. `재개 조건`은 **코드에서 관측 가능한
     리터럴**로 쓴다(예: "`frontend/src`에 `localStorage` 등장"). "필요해지면" 같은 서술은 조건이 아니다.
4. **미탐 원장** — 표: `PR | 관점 | 놓친 것 | 보강 규칙 ID | 기록일`. 사람이 success가 붙은 PR에서
   그 관점의 위험을 뒤늦게 발견하면 여기에 행을 더한다. 원장은 비어 있는 것이 정상이다.

표면·앵커 블록을 모델(reconciler)이 아니라 **정책 문서에** 두는 것이 고정부다. 표면이 낡았을 때
고치는 일이 대상 레포의 PR로 끝나야 루프(data plane)가 스스로 수렴시킬 수 있다 — 모델에 두면
표면 개정마다 control plane 작업이 된다.

## 슬롯 표

대상 레포를 탐색해 확정한다. 확정 안 되는 값은 추측하지 말고 사용자에게 묻는다.

| 슬롯 | 의미 | 예 (feature-doc) |
|---|---|---|
| `{{REPO}}` | owner/repo | `dlddu/feature-doc` |
| `{{SLUG}}` | id·이름용 소문자 레포명 | `feature-doc` |
| `{{POLICY_SSOT}}` | 정책 문서 경로 | `docs/review-policy.md` |
| `{{STATUS_PREFIX}}` | status context 접두 | `review/` |
| `{{CONTEXT_ERE}}` | 워크플로에서 context 선언을 찾는 ERE. **작은따옴표를 쓰지 않는다**(스크립트가 작은따옴표로 감싼다) | `context[^a-z/]{1,4}review/[a-z0-9-]+` |
| `{{JUDGE_REF_ERE}}` | 워크플로가 부르는 판정기 경로를 뽑는 ERE | `tools/[A-Za-z0-9_./-]+\.(py\|js\|mjs\|sh)` |
| `{{ASPECTS}}` | 등록 시점 관점 목록과 각 판정기 | `data-format` — `tools/check-data-format-change.py` (D1~D6), `.github/workflows/data-format-review.yml` |
| `{{CONSUMER}}` | status 소비자 | (인스턴스화 시 확인 — ruleset required check / 자동 머지 / 사람 관례) |
| `{{SIBLING_MODEL}}` | 판정기 헤더를 함께 보는 자매 모델 [선택] | `tbm_feature-doc-comment-redundancy` |
| `{{INITIAL_STATE}}` | 등록 시점 현황 | 정책 문서 없음 · 판정기 1개(규칙은 헤더 주석에만) · 소비자 미확인 |
| `{{NOW_ISO}}` | 등록 시각 (UTC ISO 8601) | `date -u +%Y-%m-%dT%H:%M:%SZ` |

## 모델 JSON 골격

```json
{
  "id": "tbm_{{SLUG}}-pr-manual-approval",
  "metadata": {
    "name": "{{SLUG}} PR 수동 승인 라우팅 정합성",
    "description": "{{REPO}}에서 사람 승인이 필요한 PR 관점을 {{POLICY_SSOT}}가 선언하고, 관점마다 판정기가 위험 무접촉을 확인하면 {{STATUS_PREFIX}}<관점> = success를 붙인다. 정책↔판정기 1:1(불변식 1)과 규칙의 신선도 — 앵커 실재·표면 포괄·제외 트립와이어·재검토 기한(불변식 2)을 추적한다.",
    "tags": ["{{SLUG}}", "pr", "review", "manual-approval", "ci", "consistency"],
    "createdAt": "{{NOW_ISO}}"
  },
  "definition": "<definition 본문 템플릿을 채워 넣기>",
  "toBe": {
    "dataSource": { "type": "github", "repository": "{{REPO}}", "ref": "main", "subPath": "{{POLICY_SSOT}}" },
    "versionScript": { "runtime": "bash", "code": "<to-be 스크립트>", "timeoutSeconds": 60 }
  },
  "asIs": {
    "dataSource": { "type": "github", "repository": "{{REPO}}", "ref": "main" },
    "versionScript": { "runtime": "bash", "code": "<as-is 스크립트>", "timeoutSeconds": 120 }
  },
  "checkPolicy": { "intervalSeconds": 3600 }
}
```

- as-is는 워크플로·판정기·정책이 선언한 표면을 가로지르므로 `asIs.dataSource.subPath`를 두지 않는다
  (스크립트가 진실).

## versionScript

**to-be** — 정책 문서의 blob hash. 문서가 **없는 상태도 유효한 관측**이므로 `absent`로 표현한다.

```bash
#!/usr/bin/env bash
# to-be = 수동 승인 정책 문서의 blob hash. 아직 없으면 'absent'.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
git rev-parse --verify --quiet "HEAD:{{POLICY_SSOT}}" || echo "absent"
```

**as-is** — 세 성분의 라벨 조합 `judges=…;surface=…;anchors=…`. 각 성분은 서로 다른 낡음을 잡는다.

| 성분 | 무엇의 지문인가 | 무엇에 반응하나 | 반응하지 않는 것 |
|---|---|---|---|
| `judges` | `{{CONTEXT_ERE}}`에 걸리는 워크플로 + 그 워크플로가 부르는 판정기의 blob hash | 판정기 추가·삭제·규칙 수정 | 다른 워크플로 변경 |
| `surface` | 정책의 ```` ```surface ```` 블록마다 (관점, 파일, 토큰) 쌍 집합 | 위험 신호가 **새 파일에 나타나거나 사라짐**, 새 종류의 토큰 등장 | 이미 표면인 파일 안의 로직·주석 변경 |
| `anchors` | 정책의 ```` ```anchors ```` 블록 경로별 실재 여부(present/absent) | 규칙이 지목한 경로의 삭제·이동 | 앵커 파일의 내용 변경 |

```bash
#!/usr/bin/env bash
# as-is = 수동 승인 라우팅의 실재 상태 지문. judges · surface · anchors 세 성분의 라벨 조합.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
export LC_ALL=C
POLICY='{{POLICY_SSOT}}'
CONTEXT_ERE='{{CONTEXT_ERE}}'
JUDGE_REF_ERE='{{JUDGE_REF_ERE}}'
h() { sha256sum | cut -c1-16; }

# ① judges — 라우팅 status 를 붙이는 워크플로와, 그 워크플로가 부르는 판정기의 blob 해시.
WFS=$(git ls-files -- '.github/workflows/*.yml' '.github/workflows/*.yaml' | sort \
  | xargs -r grep -lE "$CONTEXT_ERE" || true)
REFS=$(printf '%s\n' "$WFS" | grep . | xargs -r grep -EHo "$JUDGE_REF_ERE" | cut -d: -f2- | sort -u || true)
JUDGES=$(for f in $WFS $REFS; do
  printf '%s %s\n' "$f" "$(git rev-parse --verify --quiet "HEAD:$f" || echo absent)"; done | sort -u)
CTX=$(printf '%s\n' "$WFS" | grep . | xargs -r grep -Eho "$CONTEXT_ERE" | sort -u || true)

# 정책 문서에서 ```<kind> <관점>``` 펜스 블록을 뽑는다. 출력: "<관점>\t<본문 줄>".
blocks() {
  git show "HEAD:$POLICY" 2>/dev/null | awk -v k="$1" '
    !f && $0 ~ "^```" k " " { f = 1; id = $2; next }
    f && /^```/ { f = 0; next }
    f && NF { print id "\t" $0 }' || true
}

# ② surface — 정책이 관점별로 선언한 위험 표면(scope · exclude · ere)에 걸리는 (관점, 파일, 토큰) 집합.
SURFACE=""
for id in $(blocks surface | cut -f1 | sort -u); do
  B=$(blocks surface | awk -F'\t' -v i="$id" '$1 == i { print $2 }')
  scope=$(printf '%s\n' "$B" | sed -n 's/^scope:[[:space:]]*//p')
  excl=$(printf '%s\n' "$B" | sed -n 's/^exclude:[[:space:]]*//p'); excl=${excl:-'^$'}
  ere=$(printf '%s\n' "$B" | sed -n 's/^ere:[[:space:]]*//p')
  [ -n "$scope" ] && [ -n "$ere" ] || { SURFACE+="$id malformed"$'\n'; continue; }
  # shellcheck disable=SC2086
  SURFACE+=$({ git ls-files -- $scope | grep -vE "$excl" | sort \
      | xargs -r grep -IEHo "$ere" || true; } | sort -u | sed "s|^|$id |")$'\n'
done

# ③ anchors — 정책의 규칙이 이름으로 지목하는 경로(글롭 허용)의 실재 여부. 내용 변경에는 반응하지 않는다.
ANCHORS=$(blocks anchors | while IFS=$'\t' read -r id p; do
  if [ -n "$(git ls-files -- ":(glob)$p" | head -n1)" ]; then s=present; else s=absent; fi
  printf '%s %s %s\n' "$id" "$p" "$s"; done | sort -u)

[ -n "$(git rev-parse --verify --quiet "HEAD:$POLICY" || true)" ] || { SURFACE=absent; ANCHORS=absent; }
echo "contexts=$(printf '%s' "$CTX" | grep -c . || true) judges=$(printf '%s' "$JUDGES" | grep -c . || true) surface_hits=$(printf '%s' "$SURFACE" | grep -c . || true) anchors_absent=$(printf '%s' "$ANCHORS" | grep -c ' absent$' || true)"
printf 'judges=%s;surface=%s;anchors=%s\n' \
  "$(printf '%s' "$JUDGES" | h)" "$(printf '%s' "$SURFACE" | h)" "$(printf '%s' "$ANCHORS" | h)"
```

주의:
- 마지막 줄만 버전이다. `contexts=… judges=…` 진단 줄은 값에 영향을 주지 않는다.
- 정책 문서가 없으면 `surface`·`anchors`는 상수 `absent`의 해시가 되고 `judges`만 움직인다 — 문서가
  생기는 순간 두 성분이 함께 바뀌어 첫 신선도 판정이 트리거된다.
- 블록 형식이 깨지면(scope 또는 ere 누락) 그 관점은 `<관점> malformed`로 지문에 들어간다. 조용히
  빈 집합이 되지 않게 하는 장치이며, 판정에서 R4 위반으로 센다.
- 표면 ERE는 대상 레포의 문서에서 읽혀 `grep`에만 쓰인다. 문서의 어떤 줄도 셸로 평가되지 않는다.
- 표면은 **토큰형**(파일·토큰 쌍, `sort -u`)이다. 같은 파일 안의 등장 횟수는 반영되지 않는다 — 그
  대가로 이미 표면인 파일의 일상적 수정에는 흔들리지 않고, "새 파일이 위험 표면이 되었다"는 순간에만
  반응한다. 그 순간이 규칙이 낡을 수 있는 순간이다.
- 등록 전에 대상 레포에서 스크립트를 실제로 돌려 값이 나오는지, 무관한 변경에 값이 흔들리지 않는지 확인한다.

## definition 본문 템플릿

`[선택]` 표시 블록은 해당 없으면 통째로 삭제. `<!-- 지침 -->`은 모두 제거.

```markdown
# {{SLUG}} PR 수동 승인 라우팅 정합성

## 목표
`{{REPO}}`에서 **사람의 승인이 필요한 PR**을 관점별 판정기가 가른다. 판정기는 PR이 그 관점의 위험에 닿지 않았다고 확인될 때만 `{{STATUS_PREFIX}}<관점>` = success를 붙이고, 그 밖에는 아무것도 붙이지 않아 사람에게 보낸다. 이 모델은 (1) **무엇이 사람 승인 대상인가**가 정책과 판정기 사이에서 어긋나지 않는지, (2) **판정기 규칙이 코드베이스의 현재 모양을 따라가는지**를 추적한다.

## 무엇이 "맞는 상태"인가 (SSOT)
- **정책의 SSOT**는 `{{POLICY_SSOT}}`다: 관점 레지스트리 · 관점별 규칙(표면·앵커 블록 포함) · 의도적 제외 · 미탐 원장.
- **구현의 SSOT**는 `{{STATUS_PREFIX}}` status를 붙이는 워크플로와 그것이 부르는 판정기다.
- **현실의 SSOT**는 코드다: 정책의 표면 블록에 걸리는 파일들과 앵커 블록이 지목한 경로들.
- 정합 상태 = **불변식 1 ∧ 불변식 2**. 어느 하나만 참인 것은 정합이 아니다.

## 프로세스 원칙
P1 긍정 확인(success만, 부재 = 사람) · P2 fail-closed · P3 base 실행(`pull_request_target`, PR 코드 비실행) · P4 판정기 자기 변경은 사람 리뷰 · P5 판단이 갈리면 사람 쪽 · P6 context는 `{{STATUS_PREFIX}}<관점>`. (정의: reconciler `templates/pr-manual-approval.tbm.md`)

## 등록 시점 관점 (스냅샷)
{{ASPECTS}} <!-- 지침: 관점 · 판정기 · 워크플로 · 규칙 ID 범위를 목록으로. 판정 기준이 아니라 스냅샷이다 — 관점이 늘면 버전이 바뀌어 재평가된다 -->

## 불변식 1 — 라우팅 1:1 ("사람 승인이 필요한 케이스"의 추적·관리)

- **R1 관점 1:1** — 레지스트리의 관점 집합 == 워크플로에서 발견되는 `{{STATUS_PREFIX}}<관점>` context 집합. 레지스트리에만 있는 관점(판정기 없음 → 그 관점은 늘 사람 리뷰로 가지만, 정책은 자동 판정이 있다고 말한다)도, 판정기에만 있는 관점(정책에 없는 자동 생략)도 drift다. 후자가 더 위험하다.
- **R2 규칙 1:1** — 관점마다 정책 규칙 표의 ID 집합 == 판정기가 판정 근거로 쓰는 ID 집합. 판정기의 규칙 본문이 정책과 다르면(대상 경로·패턴이 다르면) drift이며 **정책이 SSOT**다.
- **R3 원칙 준수** — 각 판정기가 P1~P6을 지킨다. 특히 P3(워크플로 트리거·체크아웃 ref·PR 코드 비실행)와 P4(판정기·워크플로 자기 경로가 규칙에 포함)는 파일을 읽어 확인한다.
- **R4 문서 완비** — 레지스트리 각 행이 모든 칸을 채우고, 관점마다 규칙 표·surface 블록·anchors 블록이 **기계 판독 가능한 형식으로** 있다. as-is 진단에 `malformed`가 보이면 위반이다.
- **R5 소비자 정합** — 레지스트리의 `소비자` 칸이 실제와 맞는다. required check·자동 머지 봇이 요구하는 context 집합이 레지스트리와 다르면 drift다. <!-- 지침: {{CONSUMER}}가 레포 밖(GitHub ruleset·branch protection)이면 as-is 지문에 잡히지 않으므로 "R5는 재검토(O4) 때 사람이 확인"이라고 적는다 -->

## 불변식 2 — 신선도 ("수동 승인 프로세스가 outdated 되지 않도록" 추적·관리)

낡은 판정기는 실패하지 않는다. 규칙이 지목한 파일이 옮겨가면 그 규칙은 영원히 걸리지 않고, 위험이 새 자리에 나타나면 아무 규칙도 그것을 보지 않는다. 두 경우 모두 판정기는 **계속 success를 붙인다**. 그래서 신선도는 판정기 통과 여부가 아니라 아래 항목으로 잰다.

- **O1 앵커 실재** — anchors 블록의 모든 경로가 present. absent인 앵커는 **죽은 규칙**이다: 판정기와 정책을 새 위치로 옮기거나, 위험 자체가 사라졌으면 규칙을 지운다.
- **O2 표면 포괄** — surface 블록에 걸리는 모든 (파일, 토큰)이 그 관점의 어떤 규칙에 덮이거나 의도적 제외 표에 있다. 어느 쪽도 아니면 **새는 표면**이다: 규칙을 넓히는 것이 기본 방향이다(P5).
- **O3 제외 트립와이어** — 의도적 제외마다 재개 조건이 관측 가능한 리터럴로 적혀 있고(서술만 있으면 미비), 그 조건이 코드에서 아직 참이 아니다. 조건이 참이 되면 제외를 풀고 규칙을 더하는 것이 작업이다.
- **O4 재검토 기한** — 레지스트리 각 행의 `다음 재검토`가 오늘 이후이고 `마지막 재검토`로부터 90일 이내다. 기한이 지나면 그 관점의 표면 블록 자체가 여전히 위험을 다 담는지(ERE가 모르는 새 저장 기술·새 디렉터리가 없는지)를 **사람의 눈으로** 다시 보고 날짜를 갱신한다. 표면 ERE가 모르는 위험은 지문이 영원히 볼 수 없으므로, 이 기한이 그 사각지대의 유일한 안전망이다.
- **O5 미탐 수렴** — 미탐 원장의 행마다 `보강 규칙 ID`가 있고 그 ID가 규칙 표와 판정기에 실재한다. 보강 없이 기록만 된 미탐은 gap이다.

## 판정 규칙
R1~R5 · O1~O5 중 **하나라도** 위반이면 `action_required`. 전부 충족이면 `no_action_needed`로 닫되, `stateSummary`에 관점 수 · 표면 히트 수 · 제외 수 · 미탐 원장 행 수를 남기고 **가장 이른 `다음 재검토`**를 `assessment.recheckAfter`로 적는다 — 버전이 안 바뀌어도 기한이 오면 다시 보게 하는 장치다(O4는 시간이 만드는 drift라 지문이 스스로 움직이지 않는다).

## 충돌 시 기본 방향
- 정책 ↔ 판정기 불일치 → **정책이 SSOT**. 판정기를 정책에 맞춘다. 판정기 쪽이 옳아 보이면 정책을 먼저 고치는 PR을 내고, 그 PR은 P4에 따라 사람 리뷰를 받는다.
- 판정기에만 있는 관점 → 정책에 등재할지 판정기를 내릴지는 사람이 정한다. 그때까지 판정기의 success는 정책 밖의 자동 생략이다 — task에 **최우선 gap**으로 적는다.
- 새는 표면·죽은 앵커 → **규칙을 넓히는 쪽**(P5). 오탐이 늘어나는 것은 비용으로 받아들인다.
- 제외의 재개 조건이 발동 → 제외 행을 지우고 규칙을 더한다. 제외를 연장하려면 새 재개 조건을 쓴다(조건 없는 연장은 조용한 영구 면제다).
- 판단이 갈리면 **사람 리뷰 쪽으로** 기운다.

## 추적 방식 (요약)
- **to-be** = `{{POLICY_SSOT}}`의 blob hash. 없으면 `absent`.
- **as-is** = `judges=…;surface=…;anchors=…`. judges는 `{{STATUS_PREFIX}}` context를 붙이는 워크플로와 그 판정기의 blob hash, surface는 정책 surface 블록에 걸리는 (관점, 파일, 토큰) 집합, anchors는 정책 anchors 블록 경로의 실재 여부. 정책 문서가 없으면 surface·anchors는 `absent`.
- **O4 재검토 기한**은 지문이 아니라 `recheckAfter`로 추적한다.

## 초기 상태 메모 (등록 시점 {{NOW_ISO}})
{{INITIAL_STATE}} <!-- 지침: 정책 문서 유무, 판정기 수와 규칙이 지금 어디에 적혀 있는지(헤더 주석 등), 소비자 확인 여부, 등록 전 as-is 진단 줄을 남긴다. 정책 문서가 없으면 "첫 task는 판정기 헤더의 규칙을 {{POLICY_SSOT}}로 옮겨 레지스트리·표면·앵커 블록을 만들고, 판정기 헤더는 정책 참조로 줄인다 — 큰 초기 격차는 예상된 것"을 포함 -->

## 범위 밖 / 비고
- 판정기 규칙의 **의미적 정확성**(이 SQL이 정말 스키마를 바꾸는가)은 보지 않는다. 그것은 사람 리뷰의 몫이고, 이 모델은 "무엇이 사람에게 가는가"의 경계만 본다.
- 개별 PR의 판정 결과나 리뷰 품질은 대상이 아니다. 미탐은 사람이 발견해 원장에 적을 때만 이 모델에 들어온다(발견 즉시 수동 트리거를 권장).
- 관점을 **새로 만들지** 여부(예: 인증·권한 변경에도 사람 승인을 요구할지)는 사람의 결정이다. 이 모델은 선언된 관점을 지키게 할 뿐, 관점을 발명하지 않는다.
- 지문의 사각지대: surface ERE가 모르는 형태로 나타나는 위험(새 저장 기술, 새 디렉터리)과 레포 밖의 소비자 설정(ruleset)은 보이지 않는다. O4 재검토 기한이 그 안전망이다.
- <!-- [선택] --> 판정기 헤더 주석이 정책 문서의 규칙을 되풀이하면 자매 모델 `{{SIBLING_MODEL}}`(주석 비중복성)의 대상이 된다. 규칙 본문의 SSOT는 정책 문서이고, 판정기에는 규칙 ID와 정책 링크만 남기는 것이 두 모델이 수렴하는 모양이다.<!-- -->
```
