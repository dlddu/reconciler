# 템플릿: PR 수동 승인 (pr-manual-approval)

한 레포에서 **어떤 PR이 사람의 승인을 받아야 하는가**를 판정기 하나가 가르고, 그 판정이
**코드베이스가 자라는 동안에도 낡지 않게** 유지하는 모델. 수동 승인은 레포당 **하나의 프로세스**다
— 판정기 하나, status 하나, 케이스 목록 하나. 판정기는 PR이 어떤 수동 승인 케이스에도 **닿지 않았다고
확인되면** head 커밋에 commit status `{{STATUS_CONTEXT}}` = success를 붙이고, 닿았을 가능성이 있으면
아무것도 붙이지 않는다. 그 status는 기본 브랜치 ruleset의 **required status check**이므로, 붙지 않은
PR은 머지되지 않는다. 사람의 승인은 **사람이 PR을 검토한 뒤 같은 status를 직접 붙이는 것**(수동
status)이다 — 승인 경로는 이것 하나뿐이다.

정합 상태 = **불변식 1 ∧ 불변식 2**.

- **불변식 1 (케이스 · 신호 · 게이트 정합)** — 정책이 선언한 수동 승인 케이스 집합 == 판정기의 케이스
  집합이고, 그 판정이 **단 하나의** status로 나가며, ruleset이 **그 status를** 요구한다.
  **"사람 승인이 필요한 케이스"를 추적·관리하는 축**이다.
- **불변식 2 (신선도)** — 케이스가 지목하는 경로가 실재하고, 코드의 위험 표면이 케이스나 의도적
  제외로 빠짐없이 덮이며, 제외의 재개 조건이 아직 발동하지 않았고, 재검토 기한이 지나지 않았다.
  **수동 승인 프로세스가 outdated 되지 않도록 추적·관리하는 축**이다.

케이스는 "지금의 코드"를 전제로 쓰인다(파일 이름, 크레이트 이름, 디렉터리 배치). 코드가 옮겨가도
판정기는 조용히 success를 계속 붙이고 required check는 초록으로 통과하므로, 낡은 판정기는
**실패하지 않고 새는** 방식으로 망가진다. 불변식 2가 그 누수를 잡는 장치다.

## 프로세스 원칙 (고정부)

이 유형의 정체성. 불변식 1의 판정 항목(R3)이 된다.

| ID | 원칙 | 이유 |
|---|---|---|
| P1 단일 프로세스 | 수동 승인 판정은 **판정기 하나 · status 하나**로 나간다. 케이스가 늘면 판정기 안의 케이스를 늘리지, status나 판정기를 쪼개지 않는다. | 신호가 여럿이면 ruleset·정책·판정기가 서로 다른 부분집합을 보게 되고, 그 틈이 "아무도 요구하지 않는 판정"이 된다. |
| P2 긍정 확인 | 판정기는 **success만** 붙인다. "사람 승인 필요"는 status의 **부재**로 표현한다. | required check와 맞물려 기본값이 "머지 불가 → 사람"이 된다. 판정기가 죽거나 안 돌아도 안전하다. |
| P3 fail-closed | 판정이 불가능하면(파싱 실패·git 오류) status 없이 끝난다. | 판정 불가를 통과로 뭉개지 않는다. |
| P4 base 실행 | 판정기는 **PR이 아니라 base 쪽 코드**로 돈다(`pull_request_target` + base 체크아웃). PR의 코드는 실행하지 않고 diff 입력(데이터)으로만 쓴다. | PR이 판정기를 고쳐 자기에게 success를 붙이지 못하게. |
| P5 자기 참조 | 판정기·그 워크플로·정책 문서를 바꾸는 PR은 **수동 승인 케이스**다(케이스로 명시). | P4 때문에 판정기 변경 PR은 옛 판정기로 판정된다 — 그 변경 자체는 사람 눈에 올린다. |
| P6 미탐 비대칭 | 판단이 갈리면 **사람 승인 쪽으로** 기운다(케이스를 넓게 잡는다). | 미탐(위험한데 success → 자동 머지 가능)은 운영 사고, 오탐(무해한데 승인 대기)은 승인 한 번이다. |
| P7 수동 status | 사람 승인은 **항상 수동 status**다: 사람이 PR을 검토한 뒤 head 커밋에 **같은 context `{{STATUS_CONTEXT}}`** = success를 붙인다. 사람이 직접 붙이든, 그 자리에서 **사람의 지시를 받아 도는 승인 전용 도구**로 붙이든 같다 — 수동인 것은 손이 아니라 **판단**이다. description은 `수동 승인`으로 시작하고 승인자를 적는다. ruleset bypass·관리자 머지·required check 해제는 승인 경로가 아니다. | status는 커밋에 붙으므로 승인 뒤 새 푸시가 오면 head가 바뀌어 **승인이 자동으로 무효**가 되고, 판정기가 다시 판정한다 — 승인이 검토한 코드에 묶인다. bypass는 코드에 아무 흔적을 남기지 않아 어떤 PR이 사람을 거쳤는지 사후에 알 수 없다. |
| P8 승인의 주체는 사람이다 | `{{STATUS_CONTEXT}}`를 붙이는 것은 **그 PR을 검토한 사람**뿐이다. 판정기 워크플로를 제외하면, **사람 없이 도는 것**(스케줄 트리거·CI 잡·루프(reconciler)의 무인 fire)은 붙이지 않는다. 사람이 승인하며 쓰는 도구는 그 사람의 손이되, **승인 전용**이어야 한다 — 붙일 수 있는 context가 승인 네임스페이스로 제한되고(접두사 허용목록 등), 무인 경로에서 불리지 않는다. required check는 **특정 앱(integration)에 고정하지 않는다**. | 사람 승인을 형식으로 만드는 것은 **판단이 빠지는 것**이지 명령줄이 끼는 것이 아니다. 반대로 사람이 쓰는 도구를 금지하면 승인이 `gh api` 손타이핑으로만 가능해져, 절차가 지켜지지 않거나 bypass로 샌다. 도구를 승인 네임스페이스로 가두는 것은 그 도구가 **다른 required check를 위조하지 못하게** 하는 선이다. required check가 특정 앱에 고정되면 사람이 PAT로 붙인 status든 도구가 앱 신원으로 붙인 status든 한쪽이 인정되지 않아 P7이 불가능해진다. |

## 정책 문서 (고정부)

정책은 **대상 레포의 `{{POLICY_SSOT}}` 한 파일**에 둔다. 판정기 코드의 헤더 주석이 아니라 문서가
SSOT다 — 헤더에만 있으면 판정기를 고치는 사람만 보고, 무엇이 사람 승인 대상인지 묻는 사람은 찾을
곳이 없다. 판정기는 케이스 ID로 정책을 **참조**하고 케이스 본문을 되풀이하지 않는다.

문서는 다음 절을 가진다(제목 문구는 레포 언어에 맞춰도 되나 절의 역할과 **기계 판독 블록의
형식**은 고정이다).

1. **프로세스** — 한 표로 프로세스 자체를 적는다.

   | 항목 | 값 |
   |---|---|
   | status context | `{{STATUS_CONTEXT}}` |
   | 판정기 | 판정기 경로 |
   | 워크플로 | 워크플로 경로 |
   | 게이트 | 기본 브랜치 ruleset의 required status check (ruleset 이름) |
   | 사람 승인 | 수동 status (P7 고정) — 승인할 수 있는 사람, status를 붙이는 방법(예: `gh api` 한 줄, 또는 승인 전용 도구와 그 도구가 붙일 수 있는 context 범위) |
   | 마지막 재검토 | ISO 날짜 |
   | 다음 재검토 | ISO 날짜, **마지막 재검토로부터 최장 90일** |

2. **수동 승인 케이스** — 표: `ID | 대상 | 이유`. 케이스 하나 = 행 하나. 판정기는 같은 ID를 판정
   근거 라벨로 쓴다. P5의 자기 참조 케이스가 반드시 한 행으로 있다.
3. **위험 표면 블록** — as-is 지문이 읽는 기계 판독 블록. 수동 승인 케이스의 위험이 코드에 나타나는
   모양. `scope`·`ere`는 여러 줄 둘 수 있다(scope는 합집합, ere는 `|`로 합쳐진다) — 케이스 성격이
   다르면 줄을 나눠 적는 것을 권장한다.
   ````text
   ```surface
   scope: <git ls-files 경로 목록, 공백 구분>
   exclude: <제외 ERE — 생략 가능>
   ere: <위험 신호 토큰 ERE>
   ```
   ````
4. **앵커 블록** — 케이스가 이름으로 지목하는 경로(글롭 허용), 한 줄에 하나.
   ````text
   ```anchors
   backend/migrations
   deploy/**/pvc*.yaml
   ```
   ````
5. **의도적 제외** — 표: `대상 | 사유 | 재개 조건 | 소관`. `재개 조건`은 **코드에서 관측 가능한
   리터럴**로 쓴다(예: "`frontend/src`에 `localStorage` 등장"). "필요해지면" 같은 서술은 조건이 아니다.
6. **미탐 원장** — 표: `PR | 놓친 것 | 보강 케이스 ID | 기록일`. 사람이 success가 붙은 PR에서 수동
   승인이 필요했던 변경을 뒤늦게 발견하면 여기에 행을 더한다. 원장은 비어 있는 것이 정상이다.

표면·앵커 블록을 모델(reconciler)이 아니라 **정책 문서에** 두는 것이 고정부다. 표면이 낡았을 때
고치는 일이 대상 레포의 PR로 끝나야 루프(data plane)가 스스로 수렴시킬 수 있다 — 모델에 두면
표면 개정마다 control plane 작업이 된다.

## 슬롯 표

대상 레포를 탐색해 확정한다. 확정 안 되는 값은 추측하지 말고 사용자에게 묻는다.

| 슬롯 | 의미 | 예 (feature-doc) |
|---|---|---|
| `{{REPO}}` | owner/repo | `dlddu/feature-doc` |
| `{{STATUS_CONTEXT}}` | 수동 승인 판정 status context (하나). **케이스를 가리키는 이름은 피한다** — 케이스가 넓어질 때마다 개명해야 하고, 개명은 워크플로·ruleset·정책을 동시에 건드린다 | `review/manual-approval` (레포 현행은 `review/data-format`이라 첫 task에서 개명) |
| `{{CONTEXT_ERE}}` | 워크플로에서 승인 계열 context 선언을 찾는 ERE. 이름 하나가 아니라 `{{STATUS_CONTEXT}}`가 속한 **계열**을 잡는다 — 그래야 두 번째 신호가 생길 때(P1 위반) 지문이 움직인다. **작은따옴표를 쓰지 않는다** | `context[^a-z/]{1,4}review/[a-z0-9-]+` (`context=review/x`·`context: review/x`·`"context": "review/x"`를 모두 잡는다) |
| `{{SLUG}}` | id·이름용 소문자 레포명 | `feature-doc` |
| `{{POLICY_SSOT}}` | 정책 문서 경로 | `docs/review-policy.md` |
| `{{JUDGE_REF_ERE}}` | 워크플로가 부르는 판정기 경로를 뽑는 ERE | `tools/[A-Za-z0-9_./-]+\.(py\|js\|mjs\|sh)` |
| `{{JUDGE}}` | 판정기 · 워크플로 · 등록 시점 케이스 ID | `tools/check-data-format-change.py` · `.github/workflows/data-format-review.yml` · D1~D6 |
| `{{RULESET}}` | 게이트 ruleset | `default` (id 23666120, 기본 브랜치, required: `ci-gate`(integration 15368)·`review/data-format`(integration 없음) — **첫 task에서 `{{STATUS_CONTEXT}}`로 개명**) |
| `{{TOKEN_REF}}` | ruleset 조회용 토큰 참조 (사실상 필수) | `secretRef:<이름>` — 공개 레포는 무토큰으로도 읽히지만 무인증 한도(60/h)를 egress 전체가 공유해 등록 전 실측에서 소진됐다. metadata:read 권한이면 충분하다 |
| `{{SIBLING_MODEL}}` | 판정기 헤더를 함께 보는 자매 모델 [선택] | `tbm_feature-doc-comment-necessity` |
| `{{INITIAL_STATE}}` | 등록 시점 현황 | 정책 문서 없음 · 케이스는 판정기 헤더 주석에만 · status가 `review/data-format`(개명 필요) · ruleset은 이미 required(integration 미고정) · 수동 status 절차 미기재 |
| `{{NOW_ISO}}` | 등록 시각 (UTC ISO 8601) | `date -u +%Y-%m-%dT%H:%M:%SZ` |

### 개명 순서

정한 `{{STATUS_CONTEXT}}`가 레포의 현행 이름과 다르면 첫 task에서 개명한다. 순서를 지키지
않으면 열린 PR이 전부 막히므로 반드시 이 순서로 한다.

1. ruleset의 required status check에 새 이름을 **추가**한다(옛 이름은 둔 채). 사람이 한다.
2. 판정기 워크플로의 context를 새 이름으로 바꾼다. 워크플로 파일이라 GitHub App 권한으로는 push가
   막힐 수 있어 사람 손이 필요할 수 있다.
3. 열린 PR들이 새 status를 받은 뒤(필요하면 빈 커밋으로 재판정), ruleset에서 옛 이름을 뺀다.
4. 정책 문서의 프로세스 표와 수동 status 명령을 새 이름으로 고친다.

2와 3 사이에는 계열 context가 둘이라 R2가 일시적으로 위반 상태다. task의 계획에 그 구간을 적고,
같은 task 안에서 닫는다.

## 모델 JSON 골격

```json
{
  "id": "tbm_{{SLUG}}-pr-manual-approval",
  "metadata": {
    "name": "{{SLUG}} PR 수동 승인 정합성",
    "description": "{{REPO}}의 PR 수동 승인은 판정기 하나가 {{POLICY_SSOT}}의 케이스에 닿지 않았다고 확인할 때만 {{STATUS_CONTEXT}} = success를 붙이고, 기본 브랜치 ruleset이 그 status를 required로 요구하는 단일 프로세스다. 케이스·신호·게이트 정합(불변식 1)과 케이스의 신선도 — 앵커 실재·표면 포괄·제외 트립와이어·재검토 기한(불변식 2)을 추적한다.",
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
    "versionScript": { "runtime": "bash", "code": "<as-is 스크립트>", "timeoutSeconds": 120, "env": { "GITHUB_TOKEN": "{{TOKEN_REF}}" } }
  }
}
```

- as-is는 워크플로·판정기·ruleset·정책이 선언한 표면을 가로지르므로 `asIs.dataSource.subPath`를 두지
  않는다(스크립트가 진실).
- 스크립트는 `GITHUB_TOKEN`이 없으면 무인증으로 읽지만, 무인증 한도가 공유되어 소진되면 감지가 매번 실패한다. `env`는 빼지 않는다.

## versionScript

**to-be** — 정책 문서의 blob hash. 문서가 **없는 상태도 유효한 관측**이므로 `absent`로 표현한다.

```bash
#!/usr/bin/env bash
# to-be = 수동 승인 정책 문서의 blob hash. 아직 없으면 'absent'.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
git rev-parse --verify --quiet "HEAD:{{POLICY_SSOT}}" || echo "absent"
```

**as-is** — 네 성분의 라벨 조합 `judges=…;ruleset=…;surface=…;anchors=…`. 각 성분은 서로 다른 어긋남을 잡는다.

| 성분 | 무엇의 지문인가 | 무엇에 반응하나 | 반응하지 않는 것 |
|---|---|---|---|
| `judges` | `{{CONTEXT_ERE}}`에 걸리는 워크플로 + 그 워크플로가 부르는 판정기의 blob hash | 케이스 수정, **두 번째 판정기·두 번째 신호의 등장**(P1) | 다른 워크플로 변경 |
| `ruleset` | 기본 브랜치에 적용되는 required status check (context, 고정 integration) 집합(레포·조직 ruleset 합산) | 승인 status가 required에서 빠짐·개명·다른 context 추가·**특정 앱에 고정됨** | ruleset의 다른 규칙(삭제 금지 등) |
| `surface` | 정책 ```` ```surface ```` 블록에 걸리는 (파일, 토큰) 쌍 집합 | 위험 신호가 **새 파일에 나타나거나 사라짐**, 새 종류의 토큰 등장 | 이미 표면인 파일 안의 로직·주석 변경 |
| `anchors` | 정책 ```` ```anchors ```` 블록 경로별 실재 여부(present/absent) | 케이스가 지목한 경로의 삭제·이동 | 앵커 파일의 내용 변경 |

```bash
#!/usr/bin/env bash
# as-is = 수동 승인 프로세스의 실재 상태 지문. judges · ruleset · surface · anchors 네 성분의 라벨 조합.
# 런타임이 dataSource.repository({{REPO}})@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
export LC_ALL=C
POLICY='{{POLICY_SSOT}}'
CONTEXT_ERE='{{CONTEXT_ERE}}'
JUDGE_REF_ERE='{{JUDGE_REF_ERE}}'
REPO='{{REPO}}'
h() { sha256sum | cut -c1-16; }

# ① judges — 승인 신호 status 를 붙이는 워크플로와, 그 워크플로가 부르는 판정기의 blob 해시.
#    신호 형태(CONTEXT_ERE)에 걸리는 워크플로를 모두 찾으므로, 두 번째 판정기·두 번째 context 가 생기면 값이 바뀐다.
WFS=$(git ls-files -- '.github/workflows/*.yml' '.github/workflows/*.yaml' | sort \
  | xargs -r grep -lE "$CONTEXT_ERE" || true)
REFS=$(printf '%s\n' "$WFS" | grep . | xargs -r grep -EHo "$JUDGE_REF_ERE" | cut -d: -f2- | sort -u || true)
JUDGES=$(for f in $WFS $REFS; do
  printf '%s %s\n' "$f" "$(git rev-parse --verify --quiet "HEAD:$f" || echo absent)"; done | sort -u)
CTX=$(printf '%s\n' "$WFS" | grep . | xargs -r grep -Eho "$CONTEXT_ERE" | sort -u || true)

# ② ruleset — 기본 브랜치에 실제로 적용되는 required status check (context, 고정 integration) 집합(레포·조직 ruleset 합산).
#    integration 이 고정되면 사람이 붙인 수동 status 가 인정되지 않으므로(P8) 고정 여부도 지문에 넣는다.
#    레포 밖 설정이라 git 으로는 안 보인다. 읽지 못하면 조용히 상수를 내지 않고 실패한다.
BR=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||' || true)
BR=${BR:-main}
AUTH=(); [ -n "${GITHUB_TOKEN:-}" ] && AUTH=(-H "Authorization: Bearer $GITHUB_TOKEN")
RULES=$(curl -fsS "${AUTH[@]}" -H 'Accept: application/vnd.github+json' \
  "https://api.github.com/repos/$REPO/rules/branches/$BR") || { echo "ruleset unreadable" >&2; exit 1; }
REQUIRED=$(printf '%s' "$RULES" | python3 -c '
import json, sys
ctx = {c["context"] + " integration=" + str(c.get("integration_id", "any"))
       for r in json.load(sys.stdin) if r.get("type") == "required_status_checks"
       for c in r.get("parameters", {}).get("required_status_checks", [])}
print("\n".join(sorted(ctx)))')

# 정책 문서에서 ```<kind> 펜스 블록의 본문 줄을 뽑는다(같은 kind 블록이 여럿이면 이어 붙인다).
block() {
  git show "HEAD:$POLICY" 2>/dev/null | awk -v k="$1" '
    !f && ($0 == "```" k || index($0, "```" k " ") == 1) { f = 1; next }
    f && /^```/ { f = 0; next }
    f && NF { print }' || true
}

# ③ surface — 정책이 선언한 위험 표면(scope · exclude · ere)에 걸리는 (파일, 토큰) 집합.
#    scope·ere 줄은 여러 개 둘 수 있다(scope 는 합집합, ere 는 | 로 합친다).
S=$(block surface)
scope=$(printf '%s\n' "$S" | sed -n 's/^scope:[[:space:]]*//p' | tr '\n' ' ')
ere=$(printf '%s\n' "$S" | sed -n 's/^ere:[[:space:]]*//p' | paste -sd'|' -)
excl=$(printf '%s\n' "$S" | sed -n 's/^exclude:[[:space:]]*//p' | paste -sd'|' -); excl=${excl:-'^$'}
if [ -z "${scope// /}" ] || [ -z "$ere" ]; then SURFACE=malformed
else
  # shellcheck disable=SC2086
  SURFACE=$({ git ls-files -- $scope | grep -vE "$excl" | sort \
      | xargs -r grep -IEHo "$ere" || true; } | sort -u)
fi

# ④ anchors — 케이스 규칙이 이름으로 지목하는 경로(글롭 허용)의 실재 여부. 내용 변경에는 반응하지 않는다.
ANCHORS=$(block anchors | while IFS= read -r p; do
  if [ -n "$(git ls-files -- ":(glob)$p" | head -n1)" ]; then s=present; else s=absent; fi
  printf '%s %s\n' "$p" "$s"; done | sort -u)

[ -n "$(git rev-parse --verify --quiet "HEAD:$POLICY" || true)" ] || { SURFACE=absent; ANCHORS=absent; }
echo "contexts=$(printf '%s' "$CTX" | grep -c . || true) required=$(printf '%s' "$REQUIRED" | grep -c . || true) judges=$(printf '%s' "$JUDGES" | grep -c . || true) surface_hits=$(printf '%s' "$SURFACE" | grep -c . || true) anchors_absent=$(printf '%s' "$ANCHORS" | grep -c ' absent$' || true)"
printf 'judges=%s;ruleset=%s;surface=%s;anchors=%s\n' \
  "$(printf '%s' "$JUDGES" | h)" "$(printf '%s' "$REQUIRED" | h)" "$(printf '%s' "$SURFACE" | h)" "$(printf '%s' "$ANCHORS" | h)"
```

주의:
- 마지막 줄만 버전이다. `contexts=… required=… judges=…` 진단 줄은 값에 영향을 주지 않는다.
  `contexts`가 1이 아니면 P1 위반이다.
- **ruleset을 읽지 못하면 비0으로 종료한다**(조용한 상수 금지). 일시 장애로 지문이 뒤집혀 가짜 task가
  생기는 것보다 감지 한 번을 건너뛰는 것이 낫다. 레포가 비공개면 `{{TOKEN_REF}}`가 필수다.
- 정책 문서가 없으면 `surface`·`anchors`는 상수 `absent`의 해시가 되고 `judges`·`ruleset`만 움직인다 —
  문서가 생기는 순간 두 성분이 함께 바뀌어 첫 신선도 판정이 트리거된다.
- surface 블록이 깨지면(scope 또는 ere 없음) 지문은 `malformed`가 된다. 조용히 빈 집합이 되지 않게 하는
  장치이며, 판정에서 R4 위반으로 센다.
- 표면 ERE는 대상 레포의 문서에서 읽혀 `grep`에만 쓰인다. 문서의 어떤 줄도 셸로 평가되지 않는다.
- 표면은 **토큰형**(파일·토큰 쌍, `sort -u`)이다. 같은 파일 안의 등장 횟수는 반영되지 않는다 — 그
  대가로 이미 표면인 파일의 일상적 수정에는 흔들리지 않고, "새 파일이 위험 표면이 되었다"는 순간에만
  반응한다. 그 순간이 케이스가 낡을 수 있는 순간이다.
- 등록 전에 대상 레포에서 스크립트를 실제로 돌려 값이 나오는지, 무관한 변경에 값이 흔들리지 않는지 확인한다.

## definition 본문 템플릿

`[선택]` 표시 블록은 해당 없으면 통째로 삭제. `<!-- 지침 -->`은 모두 제거.

```markdown
# {{SLUG}} PR 수동 승인 정합성

## 목표
`{{REPO}}`의 PR 수동 승인은 **하나의 프로세스**다. 판정기 하나가 PR이 수동 승인 케이스 어디에도 닿지 않았다고 확인될 때만 `{{STATUS_CONTEXT}}` = success를 붙이고, 기본 브랜치 ruleset이 그 status를 required로 요구한다. 붙지 않은 PR은 사람이 검토한 뒤 **같은 status를 직접 붙여(수동 status)** 승인해야 머지된다. 이 모델은 (1) **무엇이 사람 승인 대상인가**가 정책·판정기·ruleset 사이에서 어긋나지 않는지, (2) **케이스가 코드베이스의 현재 모양을 따라가는지**를 추적한다.

## 무엇이 "맞는 상태"인가 (SSOT)
- **정책의 SSOT**는 `{{POLICY_SSOT}}`다: 프로세스 표 · 수동 승인 케이스 · 표면/앵커 블록 · 의도적 제외 · 미탐 원장.
- **구현의 SSOT**는 `{{STATUS_CONTEXT}}`를 붙이는 워크플로와 그것이 부르는 판정기다.
- **게이트의 SSOT**는 기본 브랜치에 적용되는 ruleset의 required status check다.
- **현실의 SSOT**는 코드다: 정책의 surface 블록에 걸리는 파일들과 anchors 블록이 지목한 경로들.
- 정합 상태 = **불변식 1 ∧ 불변식 2**. 어느 하나만 참인 것은 정합이 아니다.

## 프로세스 원칙
P1 단일 프로세스(판정기 하나 · status 하나) · P2 긍정 확인(success만, 부재 = 사람) · P3 fail-closed · P4 base 실행(`pull_request_target`, PR 코드 비실행) · P5 판정기·워크플로·정책 변경은 수동 승인 케이스 · P6 판단이 갈리면 사람 쪽 · P7 사람 승인은 항상 수동 status(같은 context, description `수동 승인`, bypass는 경로가 아님 — 사람이 직접 붙이든 그 지시로 도는 승인 전용 도구로 붙이든 같다) · P8 승인의 주체는 사람이고, 사람 없이 도는 것은 붙이지 않으며, 승인에 쓰는 도구는 승인 네임스페이스로 제한되고, required check는 특정 앱에 고정하지 않는다. (정의: reconciler `templates/pr-manual-approval.tbm.md`)

## 등록 시점 프로세스 (스냅샷)
- 판정기: {{JUDGE}}
- 게이트: {{RULESET}}
- 사람 승인: 수동 status (P7)
<!-- 지침: 판정 기준이 아니라 스냅샷이다. 케이스 수·ID 범위는 여기에만 적고 판정 기준에 넣지 않는다 -->

## 불변식 1 — 케이스 · 신호 · 게이트 정합 ("사람 승인이 필요한 케이스"의 추적·관리)

- **R1 케이스 1:1** — 정책 케이스 표의 ID 집합 == 판정기가 판정 근거로 쓰는 ID 집합. 판정기의 케이스 본문(대상 경로·패턴)이 정책과 다르면 drift이며 **정책이 SSOT**다. 판정기에만 있는 케이스는 정책 밖의 판정, 정책에만 있는 케이스는 **판정기가 보지 않는 수동 승인 케이스**(= 새는 케이스)다 — 후자가 더 위험하다.
- **R2 신호 단일성** — `review/…` 계열 context가 워크플로 전체에서 정확히 하나(`{{STATUS_CONTEXT}}`)이고, 그것을 붙이는 판정기도 하나다(as-is 진단 `contexts=1`). 두 번째 판정기·두 번째 status가 생기면 P1 위반이다: 그 판정을 기존 판정기의 케이스로 합친다.
- **R3 원칙 준수** — 판정기가 P2~P6을 지킨다. 특히 P4(워크플로 트리거·체크아웃 ref·PR 코드 비실행)와 P5(판정기·워크플로·정책 문서 자기 경로가 케이스에 포함)는 파일을 읽어 확인한다.
- **R4 문서 완비** — 프로세스 표의 모든 칸이 채워져 있고, 케이스 표·surface 블록·anchors 블록이 **기계 판독 가능한 형식으로** 있다. as-is 지문의 surface가 `malformed`면 위반이다.
- **R5 게이트 정합** — 기본 브랜치의 required status check에 `{{STATUS_CONTEXT}}`가 **있고**, 그 항목이 **특정 앱(integration)에 고정되어 있지 않으며**(as-is `integration=any`, P8), `{{CONTEXT_ERE}}` 계열의 다른 context는 **없다**. 앱에 고정되면 수동 status가 인정되지 않아 수동 승인 케이스 PR이 영원히 막힌다. 빠지면 수동 승인 프로세스가 통째로 꺼진 것이다(판정기는 돌지만 아무도 요구하지 않는다). 정책의 프로세스 표 `게이트` 칸이 실제 ruleset과 맞아야 한다.
- **R6 수동 status 절차** — 정책 프로세스 표의 `사람 승인` 칸이 수동 status 절차(승인할 수 있는 사람, 붙이는 명령)를 담고 있다. 판정기 워크플로 밖에서 **사람 없이 도는 것**(다른 워크플로·스케줄 스크립트·루프 설정)이 `{{STATUS_CONTEXT}}`를 붙이면 P8 위반이다 — as-is `judges`가 `{{CONTEXT_ERE}}`에 걸리는 모든 워크플로를 보므로 레포 안의 것은 R2로 함께 드러난다. **사람이 승인하며 쓰는 도구는 판정기도 자동화도 아니다**(P7) — 다만 레포 밖에 살아 지문이 보지 못하므로, 그 도구와 **그 도구가 붙일 수 있는 context 범위**를 프로세스 표의 `사람 승인` 칸에 적는 것이 그 도구에 대한 유일한 추적 지점이다. 범위가 승인 네임스페이스를 넘으면(다른 required check까지 쓸 수 있으면) P8 위반이다. ruleset bypass 목록이 비어 있는지는 admin 권한이 필요해 지문에 들어가지 않는다 — O4 재검토 때 사람이 확인하고 날짜를 남긴다.

## 불변식 2 — 신선도 ("수동 승인 프로세스가 outdated 되지 않도록" 추적·관리)

낡은 판정기는 실패하지 않는다. 케이스가 지목한 파일이 옮겨가면 그 케이스는 영원히 걸리지 않고, 위험이 새 자리에 나타나면 아무 케이스도 그것을 보지 않는다. 두 경우 모두 판정기는 **계속 success를 붙이고 required check는 초록으로 통과한다**. 그래서 신선도는 판정기 통과 여부가 아니라 아래 항목으로 잰다.

- **O1 앵커 실재** — anchors 블록의 모든 경로가 present. absent인 앵커는 **죽은 케이스**다: 판정기와 정책을 새 위치로 옮기거나, 위험 자체가 사라졌으면 케이스를 지운다.
- **O2 표면 포괄** — surface 블록에 걸리는 모든 (파일, 토큰)이 어떤 케이스에 덮이거나 의도적 제외 표에 있다. 어느 쪽도 아니면 **새는 표면**이다: 케이스를 넓히는 것이 기본 방향이다(P6).
- **O3 제외 트립와이어** — 의도적 제외마다 재개 조건이 관측 가능한 리터럴로 적혀 있고(서술만 있으면 미비), 그 조건이 코드에서 아직 참이 아니다. 조건이 참이 되면 제외를 풀고 케이스를 더하는 것이 작업이다.
- **O4 재검토 기한** — 프로세스 표의 `다음 재검토`가 오늘 이후이고 `마지막 재검토`로부터 90일 이내다. 기한이 지나면 surface 블록 자체가 여전히 위험을 다 담는지(ERE가 모르는 새 저장 기술·새 디렉터리가 없는지)와 R6(bypass 목록이 비어 있는지)을 **사람의 눈으로** 다시 보고 날짜를 갱신한다. 표면 ERE가 모르는 위험은 지문이 영원히 볼 수 없으므로, 이 기한이 그 사각지대의 유일한 안전망이다.
- **O5 미탐 수렴** — 미탐 원장의 행마다 `보강 케이스 ID`가 있고 그 ID가 케이스 표와 판정기에 실재한다. 보강 없이 기록만 된 미탐은 gap이다.

## 판정 규칙
R1~R6 · O1~O5 중 **하나라도** 위반이면 `action_required`. 전부 충족이면 `no_action_needed`로 닫되, `stateSummary`에 케이스 수 · 표면 히트 수 · 제외 수 · 미탐 원장 행 수 · required check 목록을 남기고 **`다음 재검토`**를 `assessment.recheckAfter`로 적는다 — 버전이 안 바뀌어도 기한이 오면 다시 보게 하는 장치다(O4는 시간이 만드는 drift라 지문이 스스로 움직이지 않는다).

## 충돌 시 기본 방향
- 정책 ↔ 판정기 불일치 → **정책이 SSOT**. 판정기를 정책에 맞춘다. 판정기 쪽이 옳아 보이면 정책을 먼저 고치는 PR을 내고, 그 PR은 P5에 따라 수동 승인을 받는다.
- 승인 status가 required에서 빠짐(R5) → **최우선 gap**. ruleset은 레포 밖 설정이라 루프가 직접 고치지 않는다 — 사람에게 복구를 요청하고 task를 막아 둔다.
- 두 번째 판정기·status(R2) → 기존 판정기의 케이스로 합친다. 쪼갠 채로 ruleset에 추가해 맞추지 않는다.
- 새는 표면·죽은 앵커 → **케이스를 넓히는 쪽**(P6). 오탐(승인 대기) 증가는 비용으로 받아들인다.
- 제외의 재개 조건이 발동 → 제외 행을 지우고 케이스를 더한다. 제외를 연장하려면 새 재개 조건을 쓴다(조건 없는 연장은 조용한 영구 면제다).
- 승인 status가 특정 앱에 고정됨(R5) → 고정을 푼다. 판정기 신뢰를 위해 고정하고 싶다면 P7·P8과 충돌하므로 템플릿 개정 사안이다.
- 수동 status 대신 bypass로 머지된 흔적이 보이면 → 그 PR을 미탐 원장과 같은 무게로 다룬다(사후 검토 후 원장에 기록).
- 판단이 갈리면 **사람 승인 쪽으로** 기운다.

## 추적 방식 (요약)
- **to-be** = `{{POLICY_SSOT}}`의 blob hash. 없으면 `absent`.
- **as-is** = `judges=…;ruleset=…;surface=…;anchors=…`. judges는 `{{CONTEXT_ERE}}` 계열 context를 붙이는 워크플로와 그 판정기의 blob hash, ruleset은 기본 브랜치 required status check (context, 고정 integration) 집합(GitHub API, 읽기 실패 시 비0 종료), surface는 정책 surface 블록에 걸리는 (파일, 토큰) 집합, anchors는 정책 anchors 블록 경로의 실재 여부. 정책 문서가 없으면 surface·anchors는 `absent`.
- **O4 재검토 기한**과 **R6의 bypass 목록 확인**은 지문이 아니라 `recheckAfter`와 재검토로 추적한다.

## 초기 상태 메모 (등록 시점 {{NOW_ISO}})
{{INITIAL_STATE}} <!-- 지침: 정책 문서 유무, 케이스가 지금 어디에 적혀 있는지(헤더 주석 등), 현재 required check 목록과 integration 고정 여부, 수동 status 절차 기재 여부, 등록 전 as-is 진단 줄을 남긴다. 정책 문서가 없으면 "첫 task는 판정기 헤더의 케이스를 {{POLICY_SSOT}}로 옮겨 프로세스 표·케이스 표·표면/앵커 블록을 만들고, 판정기 헤더는 정책 참조로 줄인다 — 큰 초기 격차는 예상된 것"을 포함 -->

## 범위 밖 / 비고
- 케이스의 **의미적 정확성**(이 SQL이 정말 스키마를 바꾸는가)은 보지 않는다. 그것은 사람 승인의 몫이고, 이 모델은 "무엇이 사람에게 가는가"의 경계만 본다.
- 개별 PR의 판정 결과나 승인 품질은 대상이 아니다. 미탐은 사람이 발견해 원장에 적을 때만 이 모델에 들어온다(발견 즉시 수동 트리거를 권장).
- 케이스를 **새로 만들지** 여부(예: 인증·권한 변경에도 사람 승인을 요구할지)는 사람의 결정이다. 이 모델은 선언된 케이스를 지키게 할 뿐, 케이스를 발명하지 않는다.
- 개별 PR이 수동 status로 승인됐는지(승인자·시점)의 감사는 대상이 아니다. status 이력은 GitHub에 남으므로 필요할 때 조회한다.
- 판정기가 `.github/workflows/`에 있으므로, 워크플로 수정이 필요한 task는 GitHub App의 workflows 권한 유무에 따라 사람 손이 필요할 수 있다.
- 지문의 사각지대: surface ERE가 모르는 형태로 나타나는 위험(새 저장 기술, 새 디렉터리)과 ruleset bypass 목록은 보이지 않는다. O4 재검토 기한이 그 안전망이다.
- <!-- [선택] --> 판정기 헤더 주석이 정책 문서의 케이스를 되풀이하면 자매 모델 `{{SIBLING_MODEL}}`(주석 필요성)의 대상이 된다. 케이스 본문의 SSOT는 정책 문서이고, 판정기에는 케이스 ID와 정책 링크만 남기는 것이 두 모델이 수렴하는 모양이다.<!-- -->
```
