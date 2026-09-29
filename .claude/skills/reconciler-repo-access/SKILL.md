---
name: reconciler-repo-access
description: "reconciler 계열 스킬이 공유하는 dlddu/reconciler 레포 접근·레코드 편집·커밋 공통 규약과 reconciler_tool.py 헬퍼(스키마 검증·keyed upsert·id 할당)를 제공하는 기반 스킬. reconciler-tobe-modeler / reconciler-drift-detector / reconciler-work-planner / reconciler-work-review / reconciler-work-executor / reconciler-manual-approval / reconciler-task-schema-updater 가 레포를 클론·읽기·쓰기하거나 ToBeModel·ReconciliationTask 레코드를 편집·검증·커밋할 때 이 스킬의 규약과 헬퍼를 따른다. reconciler 레포에 무언가를 기록·커밋하는 작업이면 먼저 이 스킬로 레포를 확보하고 헬퍼를 준비할 것. 다른 reconciler-* 스킬이 반드시 참조하는 공용 스킬이다."
---

# reconciler 레포 접근 · 편집 · 커밋 (공용)

reconciler 계열 스킬(`reconciler-tobe-modeler`, `reconciler-drift-detector`,
`reconciler-work-planner`, `reconciler-work-review`,
`reconciler-work-executor`, `reconciler-manual-approval`, `reconciler-task-schema-updater`)은
모두 `dlddu/reconciler` 레포에 상태를 기록한다. 이 스킬은 그 레포를 열고, 레코드를
검증·편집하고, 안전하게 커밋하는 **공통 규약과 헬퍼**를 한곳에 모은 것이다. 각 워크플로
스킬은 자기 단계의 판단에만 집중하고, 아래의 기계적인 부분은 이 스킬과 그 헬퍼
`reconciler_tool.py`에 위임한다.

> **다른 스킬에서의 사용법**: 워크플로 스킬은 "레포 접근·편집·커밋은 `reconciler-repo-access`
> 스킬을 따른다"라고 적고, 이번 실행 전용 checkout 경로를 **프롬프트 인자 `$ARGUMENTS`**로 받아
> 이 스킬에 넘긴다(예: `/reconciler-data-plane:reconciler-drift-detector <checkout-dir>`). 아래 Step들의 레포
> 경로(`REPO`)는 그 인자값이다.
>
> - **왜 env가 아니라 인자인가**: 스케줄 러너가 `claude --bg`로 감지를 띄우면, 러너가 `exec` 직전
>   export한 env는 그 세션에 도달하지 못한다 — `--bg`는 프롬프트만 장수 claude **데몬**에 넘기고,
>   데몬이 **자기 자신의 env**로 에이전트 세션을 스폰하기 때문이다. 반면 **프롬프트는 그 경계를 넘어**
>   에이전트에 그대로 전달되므로, 러너는 실행별 격리 checkout 경로를 프롬프트 인자로 실어 보낸다.
>   이 인자가 없으면 여러 fire가 한 working tree를 공유해 서로의 sweep을 덮어쓴다(감지 루프가 깨지는 원인).
> - 번들 헬퍼는 checkout 경로 **옆**(`$(dirname "$REPO")/reconciler_tool.py`)에 복사한다 — 인자로 받은
>   경로에서 파생하므로 하드코딩·env가 없고, checkout **밖**이라 `git add`에 걸리지 않는다. 아래 **Step 1**을
>   실행하면 헬퍼가 그 경로(`$TOOL`)에 놓이므로, 이후 모든 스킬은 이 스킬의 설치 위치를 몰라도 그 경로로
>   헬퍼를 호출한다(`python3 "$TOOL" ...`). 즉, 레포 작업의 첫 단계는 항상 이 스킬의 Step 1이다.

## 레포 레이아웃

```
schemas/
  to-be-model.schema.json            # ToBeModel 스키마 (draft 2020-12)
  reconciliation-task.schema.json    # ReconciliationTask 스키마 (draft 2020-12)
data/                                # 운영 데이터 (스킬이 읽고 쓰는 실제 상태)
  to-be-models.json                  # ToBeModel 배열
  reconciliation-tasks/
    <toBeModelId>.json               # 해당 모델의 ReconciliationTask 배열
```

- 모델은 `data/to-be-models.json` 배열에 `id`로 관리한다.
- task는 **모델별 파일** `data/reconciliation-tasks/<toBeModelId>.json` 배열에
  `id`로 관리한다. 파일이 없으면 `[]`로 새로 만들고, 상위 디렉토리도 `mkdir -p`로 만든다.
- 운영 데이터는 모두 `data/` 아래에만 둔다.
- id 규약: 모델 `tbm_<slug>`, task `rct_<YYYYMMDD>-<NNNN>`.

## Step 1 — 레포 확보 + 헬퍼 준비 (read)

이미 checkout 경로(워크플로 스킬이 넘긴 프롬프트 인자 `$ARGUMENTS`)에 레포가 있으면 최신화만 한다.
없으면 클론한다. 하드코딩 PAT를 쓰지 말고 매번 MCP 도구 `k3s:github_app_installation_token`으로
단명 토큰을 받는다.

```
k3s:github_app_installation_token(repositories=["reconciler"],
                                  permissions={"contents":"read","metadata":"read"})
```

응답 마지막 줄 `GITHUB_TOKEN=ghs_...`에서 토큰만 꺼내 credential helper를 설정하고,
레포를 확보한 뒤 **이 스킬에 번들된 헬퍼를 고정 경로에 복사**한다(다른 스킬이 쓸 수 있게).

```bash
export GITHUB_TOKEN='ghs_...'            # 도구 응답에서 추출한 값
git config --global credential.helper store
printf 'https://x-access-token:%s@github.com\n' "$GITHUB_TOKEN" > ~/.git-credentials
chmod 600 ~/.git-credentials

# REPO = 워크플로 스킬이 프롬프트 인자($ARGUMENTS)로 넘긴 이번 실행 전용 checkout 경로. 스케줄
# 러너·워크플로가 실행마다 자기 전용 경로를 인자로 주므로 여러 run이 한 working tree를 공유하지 않는다.
# (claude --bg 세션은 러너가 exec 직전 export한 env가 도달하지 않으니 경로는 반드시 인자로 온다.)
REPO="$ARGUMENTS"
TOOL="$(dirname "$REPO")/reconciler_tool.py"   # checkout 경로에서 파생(레포 밖) — 하드코딩·env 없음, 커밋 안 걸림
mkdir -p "$(dirname "$REPO")"

if [ -d "$REPO/.git" ]; then
  git -C "$REPO" pull --rebase --quiet
else
  git clone --quiet https://github.com/dlddu/reconciler.git "$REPO"
fi

# 이 스킬 폴더에 번들된 헬퍼를 위 경로로 복사(idempotent). 이후 모든 reconciler-* 스킬은
# 그 경로로 헬퍼를 호출한다. cp 경로는 이 스킬 폴더 기준.
cp scripts/reconciler_tool.py "$TOOL"
```

> **동시성**: 쓰기 직전에 항상 `git pull --rebase` 하고, 커밋 후 곧바로 push 한다.
> 여러 task가 서로 다른 파일을 건드리므로 rebase로 대부분의 충돌을 피할 수 있다.
> 같은 task를 여러 워커가 동시에 집는 것은 아래 **task 점유(claim/lock)** 규약으로 막는다.

## Step 2 — 레코드 읽기 · 편집

스키마는 레포에 있으니 **프롬프트에 스키마를 복붙하지 말고 런타임에 파일을 읽어**
현재 계약을 따른다(단일 진실 공급원). 부분 업데이트·검증은 헬퍼를 쓴다.

```bash
REPO="$ARGUMENTS"                                 # 워크플로 스킬이 넘긴 checkout 경로(Step 1과 동일)
TOOL="$(dirname "$REPO")/reconciler_tool.py"      # Step 1과 동일 파생 경로
SCHEMA=$REPO/schemas/reconciliation-task.schema.json
FILE=$REPO/data/reconciliation-tasks/<toBeModelId>.json
mkdir -p "$(dirname "$FILE")"            # 운영 데이터 디렉토리 보장

# 다음 task id 뽑기
python3 "$TOOL" next-id --file "$FILE" --date "$(date +%Y%m%d)"

# 특정 필드만 병합(dict는 재귀 병합, 배열·스칼라는 통째 교체, null은 키 삭제)
python3 "$TOOL" upsert --file "$FILE" --id <rct_id> --schema "$SCHEMA" \
  --patch-json '{"status":"assessing","stateSummary":{"gap":"..."}}'

# 신규 레코드 생성
python3 "$TOOL" upsert --file "$FILE" --id <rct_id> --create --schema "$SCHEMA" \
  --patch /tmp/new_task.json
```

`--schema`를 주면 병합 결과가 스키마를 위반할 때 **쓰기를 거부**한다. 커밋 전 항상 통과시킨다.

헬퍼 서브커맨드: `validate`(배열 검증), `check-schema`(스키마 유효성 + 샘플 검증),
`upsert`(id 기준 딥머지), `get`(id로 조회), `next-id`(다음 id 발급). 인자는
`python3 "$TOOL" <subcommand> -h`로 확인한다.

### 스키마에 없는 필드가 필요할 때

`ReconciliationTask`/`ToBeModel` 스키마는 `additionalProperties:false`이므로 정의되지 않은
필드를 넣으면 검증에서 막힌다. 스키마는 **control plane**(`reconciler-control-plane` 번들)만
바꾼다: task 필드는 **reconciler-task-schema-updater**, 모델 필드는 **reconciler-tobe-modeler**가
단일 소유자다. 이렇게 해야 스키마가 단일 소유자를 갖고 최소 상태를 유지한다.

**data plane 스킬(`reconciler-drift-detector`·`reconciler-work-planner`·`reconciler-work-review`·
`reconciler-work-executor`)은 스키마를 수정하지 않는다.** 스키마 소유 스킬을 부르지도, 스키마
파일을 직접 고치지도 않는다. 필요한 필드가 없으면 기존 필드 안에서 표현하고(대개 `reason`·
`notes`·`comment` 같은 서술 필드), 그걸로도 기록할 수 없어 단계를 진행할 수 없으면 점유를
원래 미점유 값으로 되돌려 lock을 푼 뒤 **어떤 필드가 왜 필요한지**를 사용자 보고에 남기고
종료한다. 확장은 사람이 control plane 스킬로 한다.

## task 점유(claim/lock) — 여러 워커의 동시 처리 방지

정합성 루프는 여러 워커가 동시에 돌 수 있다. 한 task를 두 워커가 같이 집어 중복
계획·중복 실행하는 것을 막기 위해, **단계 진입을 상태 기반 lock으로 처리한다.** `status`
값을 세 부류로 나눈다:

- **미점유(대기) 상태** — 다음 단계 워커가 집어갈 수 있는 인수인계 지점:
  `action_required`(planner 대기), `planned`(reconciler-work-review 대기 — 검토 판단 전),
  `approved`(reconciler-work-executor 대기 — 검토를 통과한 실행 대기. 단, `review.manualApproval`이 있으면
  대상 레포의 사람 승인 status가 `sha`에 붙은 뒤에야 executor가 집는다 — 그 status는 사람 세션의
  reconciler-manual-approval이 사람의 답을 받아 붙인다). 재작업 진입점인
  `review_rejected`/`failed`도 planner 관점에선 미점유로 본다.
- **점유(lock) 상태** — 한 워커가 그 단계를 붙잡고 처리 중이라는 표시:
  `assessing`(detector), `planning`(planner),
  `reviewing`(reconciler-work-review), `executing`/`verifying`(reconciler-work-executor).
- **종료 상태** — `no_action_needed`/`succeeded`/`cancelled`.

`approved`에서 나가는 전이는 둘뿐이다: executor의 점유(`approved → executing`)와, `review.manualApproval`이
있는 건을 사람이 거부했을 때 reconciler-manual-approval이 쓰는 `approved → review_rejected`. 후자는 그
context의 최신 status가 아직 success가 **아닐** 때만 쓴다 — executor는 success 전에는 집지 않으므로, 기록
직전에 이 조건을 재확인하면 두 전이는 경쟁하지 않는다.

**claim 규약(compare-and-set)**: 미점유 상태의 task를 처리하려면, 무거운 실제 작업(계획
수립·실행 등)을 시작하기 **전에** 먼저 원자적으로 점유 상태로 전이해 lock을 잡는다.

1. `git pull --rebase` 로 최신화한다.
2. 대상 task의 `status`가 **여전히 기대한 미점유 값인지** 재확인한다
   (planner는 `action_required`, reconciler-work-review는 `planned`,
   reconciler-work-executor는 `approved`).
3. 맞으면 점유 상태로 upsert(`--schema` 검증) → commit → **곧바로 push**. 이 push가 곧
   lock이다. 성공해야만 다음 단계의 실제 작업을 시작한다.
4. 2에서 이미 다른 값이면(다른 워커가 먼저 집었다는 뜻) 그 task는 물러나고, 다른 대상을
   잡거나 상태만 보고한다.

push가 rebase 충돌로 실패하면 다시 `pull --rebase` 후 2부터 재시도한다. 이렇게 "먼저
점유 push한 워커가 이긴다". 계획을 마치거나 실행을 끝내면 다시 미점유(다음 단계 대기) 또는
종료 상태로 전이해 lock을 놓는다.

**모든 단계 스킬은 한 번에 한 건만 점유한다(single in-flight).** 미점유 대상이 여러 건이어도
정확히 하나만 골라 집고, 그 건이 lock을 놓을 때까지 다음 대상을 건드리지 않는다.

**detector의 claim은 예외적으로 "생성 시점" compare-and-set이다.** detector가 집는 대상은 아직
task가 없는 모델이라 뒤집을 status가 없다. 그래서 기준이 status가 아니라 **모델의
`lastObservedVersion`**이다: 그 값이 여전히 이전 값 그대로인지(=아무도 이 변화로 task를 만들지
않았는지) 재확인한 뒤, **task 생성(`assessing`)과 `lastObservedVersion` 갱신을 한 커밋으로 묶어
즉시 push**한다. 둘을 나누면 중복 task가 생기거나(모델 갱신 지연) 변화가 영영 묻힌다(task 누락).

**재확인 유예는 시각이 지나면 재진입점이 된다.** detector가 `assessing` + `assessment.recheckAfter`
로 파킹한 task는, 그 시각 전까지는 점유로 보고 아무도 건드리지 않는다. 시각이 지나면 다음 detector
실행이 이어받는데, status가 그대로라 compare-and-set 기준은 **`recheckAfter` 값**이다(과거 값 그대로면
`null`로 지우는 커밋을 push해 재진입 lock을 잡는다). 그래서 파킹할 때 `recheckAfter` 없이 두면
아무도 풀 수 없는 lock이 된다.

## Step 3 — 커밋 · 푸시 (write)

푸시에는 `contents:write` 토큰이 필요하다. 커밋 직전에 재발급한다.

```
k3s:github_app_installation_token(repositories=["reconciler"],
                                  permissions={"contents":"write","metadata":"read"})
```

```bash
export GITHUB_TOKEN='ghs_...'            # write 토큰
printf 'https://x-access-token:%s@github.com\n' "$GITHUB_TOKEN" > ~/.git-credentials
chmod 600 ~/.git-credentials

cd "$ARGUMENTS"                                   # 워크플로 스킬이 넘긴 checkout 경로(Step 1과 동일)
git add -A
git -c user.name='reconciler-bot' -c user.email='reconciler@dlddu.dev' \
    commit -m "<커밋 메시지>" --quiet
git pull --rebase --quiet && git push --quiet
```

### 커밋 메시지 규약

`<phase>(<toBeModelId>/<rct_id>): <요약>` 형태로, 단계별 접두사를 쓴다.

- `model(tbm_...): ...` — 모델 추가/수정
- `detect(tbm_.../rct_...): summarize state` / `assess action` — 감지 단계
- `plan(tbm_.../rct_...): ...` / `prepare PR` / `write guide` — 계획 단계
- `execute(tbm_.../rct_...): review / run / verify` — 실행 단계
- `approve(tbm_.../rct_...): reject` — 사람 승인 거부(reconciler-manual-approval). 승인은 대상 레포 status라 커밋이 없다
- `schema(reconciliation-task): add <field>` — 스키마 변경

각 하위 단계를 **개별 커밋**으로 남기면 이력이 곧 감사 로그가 된다.

## 보안 가드 (반드시 지킨다)

- 토큰 값을 응답·로그·커밋 메시지·`bash_tool`의 `description`에 절대 넣지 않는다.
  (`echo $GITHUB_TOKEN` 금지, description은 "set up git credentials"처럼 일반적으로.)
- 1시간 초과 작업은 토큰 만료를 가정하고 재발급한다(`401 Bad credentials`).
- 레포의 `.env`·비밀키를 발견해도 값을 출력하지 않는다.
- 대상 서비스 레포(예: flux-cd-apps)에 PR을 만드는 경우, 그 레포용 토큰을 따로 발급한다.
