# ToBeModel 템플릿

반복 등록되는 정합성 유형을 표준화한 템플릿 모음. 새 대상 레포에 같은 유형의
모델을 등록할 때, 매번 처음부터 작성하지 않고 이 템플릿을 인스턴스화한다.
(등록 절차 자체는 `reconciler-tobe-modeler` 스킬을 따른다 — 이 템플릿은 그
스킬이 "무엇을 채울지"를 표준화한 것이다.)

## 템플릿 목록

| 파일 | 유형 | 대상 |
|---|---|---|
| `docs-impl.tbm.md` | 제품 문서 ↔ 구현 정합성 | 제품 문서(`docs/`)가 기술하는 의도된 동작과 실제 구현 코드의 일치 |
| `ac-e2e.tbm.md` | AC ↔ E2E 1:1 정합성 | PRD의 Acceptance Criteria와 E2E 테스트 파일의 완전 1:1(전단사) 매칭 |
| `e2e-mock-policy.tbm.md` | E2E 모킹 최소화 | 모킹 정책·허용목록과 코드에 실재하는 모킹 지점의 양방향 1:1 |
| `mockup-render.tbm.md` | 목업 ↔ 구현 렌더링 정합성 | 목업이 정의한 화면과 이미 구현된 화면의 시각적 일치(코드 정적 대조) |
| `journey-mockup.tbm.md` | 사용자 여정 ↔ 목업 1:1 정합성 | 여정 문서와 여정 mockup 페이지의 여정·단계 두 층위 완전 1:1(전단사) |

한 레포에 docs-impl·ac-e2e 두 유형을 등록하는 것이 기본이며, 이때 역할 분담은:
**docs-impl**은 "문서 ↔ 구현 코드"의 일치를, **ac-e2e**는 "AC ↔ E2E 테스트
파일"의 1:1 매칭을 본다. docs-impl의 as-is 범위에서 E2E 디렉터리를 제외하고,
서로를 "범위 밖 / 비고"에서 교차 참조한다(템플릿에 반영되어 있음).

**e2e-mock-policy**는 E2E를 가진 레포에 선택적으로 얹는 세 번째 유형으로,
ac-e2e가 "AC마다 E2E가 있는가"를 본다면 이쪽은 "그 E2E가 실환경을 실제로
구동하는가"를 본다. 같은 E2E 트리를 보므로 as-is에 **트리 해시를 쓰지 않고**
모킹 지점만 추출해 지문화한다 — ac-e2e와의 중복 트리거를 피하기 위한 고정부다.

**mockup-render**는 목업(디자인 시안)을 가진 레포에 얹는 네 번째 유형으로,
docs-impl이 "문서가 기술한 동작이 구현되었는가"를 본다면 이쪽은 "**이미 구현된
화면이 목업대로 보이는가**"를 본다. docs-impl의 to-be에도 "UI가 목업·디자인
시스템과 일치" 항목이 있어 겹치므로, **화면 단위 시각 대조는 mockup-render가
전담**하고 **미구현 화면은 docs-impl이 담당**하는 것이 두 유형의 경계다(양쪽
템플릿의 "범위 밖 / 비고"에서 교차 참조한다). 판정은 코드 정적 대조이며 실행
스크린샷 픽셀 비교는 이 유형의 범위 밖이다 — 픽셀 비교를 도입하려면 유형의
정체성이 바뀌므로 템플릿을 고치는 커밋으로 처리한다.

**journey-mockup**은 목업을 가진 레포에 얹는 다섯 번째 유형으로, mockup-render의
**한 칸 앞**을 본다. 사슬은 `여정 문서 → 여정 mockup → 구현 화면`이고,
journey-mockup이 앞 칸(여정이 mockup에 빠짐없이 담겼는가 = **식별자 집합 대조**),
mockup-render가 뒤 칸(그 mockup대로 구현됐는가 = **시각 대조**)을 담당한다. 같은
목업 트리를 둘 다 보므로 목업 변경은 양쪽을 함께 트리거하지만, 판정 대상이 달라
중복 계상되지 않는다. 이 유형은 목업의 시각 품질을 보지 않고, 여정이 어떤 가치를
달성하는지도 보지 않는다. 판정 표면은 둘이다 — **여정 1개 ↔ 페이지 1개, 문서 단계
집합 == 페이지 단계 집합**(집합 대조)과, 그 페이지가 **클릭되는 제품 프로토타입인가**
(충실도). 후자를 빼면 정적 스냅샷을 문서 껍데기에 담은 물건이 만점을 받으므로,
규칙 5가 실제 입력 요소·화면 내 전진 배선·정상 경로 밖 상태를 요구하고 DOM 하네스
CI 게이트로 집행한다. 여백과 색은 여전히 보지 않는다.

## 고정부와 가변부

각 템플릿은 두 부분으로 나뉜다:

- **고정부** — 유형의 정체성. drift 판정 기준, 충돌 시 기본 방향(무엇이
  SSOT인가), 추적 방식(트리 해시), 기본값(checkPolicy 등). 개별 모델에서
  임의로 바꾸지 않는다. 판정 기준 자체를 바꾸고 싶으면 **템플릿을 고치는
  커밋을 별도로** 만들어 유형 전체에 반영한다(템플릿이 유형의 SSOT).
  대상 특성상 불가피하게 이탈해야 하면, 모델 definition의 "범위 밖 / 비고"에
  이탈 내용과 사유를 명시한다.
- **스냅샷(숫자)** — 개수·번호 범위는 **어느 템플릿에서도 판정 기준에 넣지 않는다.**
  대상(AC·목업·E2E 파일)은 계속 늘고 줄기 때문에, "AC 55개"·"목업 M-01~M-42" 같은
  숫자를 목표나 판정 기준에 박으면 하나가 추가된 순간 definition이 사실과 어긋난다.
  숫자는 definition의 "등록 시점 현황"에만 **스냅샷으로 라벨링**해 두고, 판정은
  개수 독립적 서술("모든 AC는…", "(AC 수 − 예외 수) = (파일 수)")로 쓴다. 대상이
  늘면 버전이 바뀌어 재평가가 트리거되고 새 항목은 자동으로 판정 대상이 되므로,
  현황 숫자 갱신은 각 task의 몫이다.
- **가변부(슬롯)** — `{{SLOT}}` 표기. 대상 레포·경로·AC 체계·예외처럼 레포마다
  달라지는 값. 각 템플릿의 슬롯 표를 보고 **대상 레포를 실제로 탐색해** 채운다.
  탐색으로 확정되지 않는 값은 추측하지 말고 사용자에게 묻는다.

## 공통 규약 (템플릿 공통 기본값)

| 항목 | 규약 |
|---|---|
| id | `tbm_<slug>-docs-impl` / `tbm_<slug>-ac-e2e` / `tbm_<slug>-e2e-mock-policy` / `tbm_<slug>-mockup-render` / `tbm_<slug>-journey-mockup` (slug = 소문자 레포명) |
| metadata.name | `<slug> 제품 문서 ↔ 구현 정합성` / `<slug> AC ↔ E2E 1:1 정합성` / `<slug> E2E 모킹 최소화 (정책 ↔ 실제 모킹 지점)` / `<slug> 목업 ↔ 구현 렌더링 정합성` / `<slug> 사용자 여정 ↔ 목업 1:1 정합성` |
| metadata.tags | `[<slug>, docs, implementation, consistency]` / `[<slug>, ac, e2e, consistency]` / `[<slug>, e2e, mocking, test-policy, consistency]` / `[<slug>, mockup, ui, design-system, consistency]` / `[<slug>, journey, mockup, ux, consistency]` (+ 필요 시 도구 태그: maestro, playwright 등) |
| checkPolicy | `{"intervalSeconds": 3600}` |
| versionScript | bash, `set -euo pipefail`, 결정적(타임스탬프·랜덤 금지). docs-impl·ac-e2e는 `git rev-parse "HEAD:<path>"` 트리 해시(복수면 라벨 조합), `timeoutSeconds: 60`. e2e-mock-policy는 트리 해시 대신 grep 지문(sha256)을 쓰고 `timeoutSeconds: 120`. mockup-render는 트리 해시에 빌드 산출물 blob 해시를 더해 조합하고 `timeoutSeconds: 60`. journey-mockup은 트리 해시에 인덱스·허브 blob 해시를 더해 조합하되 부재는 `absent`로 표기하고 `timeoutSeconds: 60` |
| lastObservedVersion/At | 등록 시 생략(첫 감지 sweep이 채운다) |

## 인스턴스화 절차

1. **대상 파악**: 대상 레포를 클론·탐색해 슬롯 표의 값을 확정한다
   (문서 경로, AC ID 체계·개수, 구현/E2E 디렉터리, 예외 후보, 등록 시점 현황).
2. **조립**: JSON 골격의 슬롯을 채우고, definition 본문 템플릿을 채워 `definition`
   필드에 넣는다. `[선택]` 블록은 해당 없으면 통째로 삭제하고, `<!-- 지침 -->`
   주석은 모두 제거한다. definition·versionScript.code처럼 개행이 많은 문자열은
   **python의 `json.dump`로 조립**해 이스케이프 실수를 없앤다.
3. **잔존 검사**: 완성본에 슬롯이나 지침이 남아 있으면 안 된다.
   ```bash
   grep -n '{{\|<!--' /tmp/model.json && echo 'unresolved slots!' || echo ok
   ```
4. **검증·등록**: `reconciler-repo-access` 규약대로 헬퍼로 upsert(스키마 검증 포함).
   ```bash
   python3 "$TOOL" upsert --file "$REPO/data/to-be-models.json" \
     --id tbm_<slug>-<type> --create \
     --schema "$REPO/schemas/to-be-model.schema.json" --patch /tmp/model.json
   ```
5. **커밋**: `model(tbm_<slug>-<type>): register from <type> template`

## 기존 모델과의 관계

템플릿 도입 이전에 등록된 모델들은 표현이 조금씩 다르다(예: id 접미사
`-ac-e2e-1to1`, definition 구성 차이). **기존 id는 유지한다**(task 파일이
id를 참조). 다만 해당 모델의 definition을 크게 개정할 일이 생기면 템플릿
구조로 수렴시키는 것을 권장한다.
