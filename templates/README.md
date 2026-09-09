# ToBeModel 템플릿

반복 등록되는 정합성 유형을 표준화한 템플릿 모음. 새 대상 레포에 같은 유형의
모델을 등록할 때, 매번 처음부터 작성하지 않고 이 템플릿을 인스턴스화한다.
(등록 절차 자체는 `reconciler-tobe-modeler` 스킬을 따른다 — 이 템플릿은 그
스킬이 "무엇을 채울지"를 표준화한 것이다.)

## 템플릿 목록

| 파일 | 유형 | 대상 |
|---|---|---|
| `docs-impl.tbm.md` | 제품 문서 ↔ 구현 정합성 | 제품 문서(`docs/`)가 기술하는 의도된 동작과 실제 구현 코드의 일치 |
| `scenario-e2e.tbm.md` | 테스트 시나리오 ↔ E2E 1:1 정합성 | 테스트 문서의 시나리오와 E2E 테스트 파일의 완전 1:1(전단사) 매칭 |
| `e2e-mock-policy.tbm.md` | E2E 모킹 최소화 | 모킹 정책·허용목록과 코드에 실재하는 모킹 지점의 양방향 1:1(불변식 1), 그리고 차단 요인이 해소 계획을 갖는가(불변식 2) |
| `mockup-render.tbm.md` | 목업 ↔ 구현 렌더링 정합성 | 목업이 정의한 화면과 이미 구현된 화면의 시각적 일치(코드 정적 대조) |
| `journey-mockup.tbm.md` | 사용자 여정 ↔ 목업 1:1 정합성 | 여정 문서와 여정 mockup 페이지의 여정·단계 두 층위 완전 1:1(전단사) |
| `comment-redundancy.tbm.md` | 주석 비중복성 (복원 가능한 주석 제거) | 코드·문서·PR·커밋 이력으로 복원되는 내용이 주석에 남아 있지 않음 |

한 레포에 docs-impl·scenario-e2e 두 유형을 등록하는 것이 기본이며, 이때 역할
분담은: **docs-impl**은 "문서 ↔ 구현 코드"의 일치를, **scenario-e2e**는 "테스트
문서의 시나리오 ↔ E2E 테스트 파일"의 1:1 매칭을 본다. docs-impl의 as-is 범위에서
E2E 디렉터리를 제외하고, 서로를 "범위 밖 / 비고"에서 교차 참조한다(템플릿에
반영되어 있음).

**scenario-e2e는 PRD·AC를 읽지 않는다.** 매칭 공간은 시나리오와 E2E 파일 둘뿐이고,
"모든 AC가 시나리오로 커버되는가"도 "시나리오가 참조하는 AC가 실재하는가"도 이
유형의 판정 대상이 아니다 — 그 층은 제품 문서 체계(doc-tracker·`product-doc-engineer`)의
몫이다. 그래서 PRD만 바뀌면 이 유형은 트리거되지 않고, 새 AC는 테스트 문서에
시나리오로 내려오는 순간부터 판정 대상이 된다. to-be 범위가 테스트 문서로 좁혀지는
것이 이 경계의 실질이다.

두 유형의 경계에서 **미구현의 취급**이 고정부다: 시나리오가 기술한 기능이 아직
구현되지 않아 E2E가 관측할 대상이 없으면 그것은 scenario-e2e의 drift가 **아니라**
docs-impl의 미구현이다. scenario-e2e는 그 시나리오를 "구현 대기"로 등재해 넘기고
**제품 코드를 만들지 않으며**, 산출물은 E2E 테스트와 등재 문서뿐이다. 이 경계가
없으면 scenario-e2e 루프가 E2E를 쓰려고 화면·엔드포인트를 구현해 docs-impl과 같은
일을 두 번 하게 된다(2026-08 `tbm_econ-opinion-monitor-ac-e2e`의 AC3.7 슬라이스가
그 사례 — 당시 유형명은 ac-e2e였다). scenario-e2e의 "예외 목록"(E2E로 검증이 곤란
= 영구 면제)과 "구현 대기"(검증할 것이 아직 없음 = 임시 보류)는 성격이 다르므로
**별도 표**로 관리한다.

**e2e-mock-policy**는 E2E를 가진 레포에 선택적으로 얹는 세 번째 유형으로,
scenario-e2e가 "시나리오마다 E2E가 있는가"를 본다면 이쪽은 "그 E2E가 실환경을
실제로 구동하는가"를 본다. 같은 E2E 트리를 보므로 as-is에 **트리 해시를 쓰지 않고**
모킹 지점만 추출해 지문화한다 — scenario-e2e와의 중복 트리거를 피하기 위한 고정부다.

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

**comment-redundancy**는 어느 레포에나 얹을 수 있는 여섯 번째 유형으로, 앞의
다섯과 **화살표 방향이 반대**다. docs-impl이 "문서가 기술한 것이 코드에
있는가"(문서 → 코드의 누락)를 본다면, 이쪽은 "코드·문서·이력이 이미 말한 것이
주석에 또 있는가"(코드 → 주석의 중복)를 본다. 같은 소스 트리를 보므로 두 모델이
함께 트리거되는 구간이 있지만, as-is 지문이 **주석 줄에만 한정**되어 있어
판정 대상이 겹치지 않는다. 이 유형은 주석의 **정확성**도, 문서·커밋 메시지
자체의 품질도 보지 않는다 — 오직 중복만 본다. 그리고 다른 유형들이 예외를 줄이는
방향으로 기우는 것과 달리, **판단이 갈리면 주석을 남기는 쪽으로 기운다**: 중복
주석의 비용은 작지만 유일한 지식을 지우면 회복되지 않는다는 비대칭 때문이다.
언어 중립이며, 언어마다 달라지는 것은 주석 줄을 뽑는 패턴 슬롯뿐이다.

## 고정부와 가변부

각 템플릿은 두 부분으로 나뉜다:

- **고정부** — 유형의 정체성. drift 판정 기준, 충돌 시 기본 방향(무엇이
  SSOT인가), 추적 방식(트리 해시), 기본값(checkPolicy 등). 개별 모델에서
  임의로 바꾸지 않는다. 판정 기준 자체를 바꾸고 싶으면 **템플릿을 고치는
  커밋을 별도로** 만들어 유형 전체에 반영한다(템플릿이 유형의 SSOT).
  대상 특성상 불가피하게 이탈해야 하면, 모델 definition의 "범위 밖 / 비고"에
  이탈 내용과 사유를 명시한다.
- **스냅샷(숫자)** — 개수·번호 범위는 **어느 템플릿에서도 판정 기준에 넣지 않는다.**
  대상(시나리오·목업·E2E 파일)은 계속 늘고 줄기 때문에, "시나리오 54개"·"목업 M-01~M-42"
  같은 숫자를 목표나 판정 기준에 박으면 하나가 추가된 순간 definition이 사실과 어긋난다.
  숫자는 definition의 "등록 시점 현황"에만 **스냅샷으로 라벨링**해 두고, 판정은
  개수 독립적 서술("모든 시나리오는…", "(시나리오 수 − 예외 수) = (파일 수)")로 쓴다. 대상이
  늘면 버전이 바뀌어 재평가가 트리거되고 새 항목은 자동으로 판정 대상이 되므로,
  현황 숫자 갱신은 각 task의 몫이다.
- **가변부(슬롯)** — `{{SLOT}}` 표기. 대상 레포·경로·시나리오 식별 체계·예외처럼 레포마다
  달라지는 값. 각 템플릿의 슬롯 표를 보고 **대상 레포를 실제로 탐색해** 채운다.
  탐색으로 확정되지 않는 값은 추측하지 말고 사용자에게 묻는다.

## 공통 규약 (템플릿 공통 기본값)

| 항목 | 규약 |
|---|---|
| id | `tbm_<slug>-docs-impl` / `tbm_<slug>-scenario-e2e` / `tbm_<slug>-e2e-mock-policy` / `tbm_<slug>-mockup-render` / `tbm_<slug>-journey-mockup` / `tbm_<slug>-comment-redundancy` (slug = 소문자 레포명) |
| metadata.name | `<slug> 제품 문서 ↔ 구현 정합성` / `<slug> 테스트 시나리오 ↔ E2E 1:1 정합성` / `<slug> E2E 모킹 최소화 (정책 ↔ 실제 모킹 지점)` / `<slug> 목업 ↔ 구현 렌더링 정합성` / `<slug> 사용자 여정 ↔ 목업 1:1 정합성` / `<slug> 주석 비중복성 (복원 가능한 주석 제거)` |
| metadata.tags | `[<slug>, docs, implementation, consistency]` / `[<slug>, test-scenario, e2e, consistency]` / `[<slug>, e2e, mocking, test-policy, consistency]` / `[<slug>, mockup, ui, design-system, consistency]` / `[<slug>, journey, mockup, ux, consistency]` / `[<slug>, comments, documentation, consistency]` (+ 필요 시 도구·언어 태그: maestro, playwright, go, python 등) |
| checkPolicy | `{"intervalSeconds": 3600}` |
| versionScript | bash, `set -euo pipefail`, 결정적(타임스탬프·랜덤 금지). docs-impl·scenario-e2e는 `git rev-parse "HEAD:<path>"` 트리 해시(글롭이면 `ls-tree` 지문, 복수면 라벨 조합), `timeoutSeconds: 60`. e2e-mock-policy는 트리 해시 대신 grep 지문(sha256)을 쓰고 `timeoutSeconds: 120`. mockup-render는 트리 해시에 빌드 산출물 blob 해시를 더해 조합하고 `timeoutSeconds: 60`. journey-mockup은 트리 해시에 인덱스·허브 blob 해시를 더해 조합하되 부재는 `absent`로 표기하고 `timeoutSeconds: 60`. comment-redundancy는 e2e-mock-policy와 같은 grep 지문(sha256)을 쓰되 주석 줄만 추출하고 `timeoutSeconds: 120` |
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

템플릿 도입 이전에 등록된 모델들은 표현이 조금씩 다르다(definition 구성 차이 등).
**기존 id는 유지하는 것이 기본이다**(task 파일이 id를 참조). 다만 해당 모델의
definition을 크게 개정할 일이 생기면 템플릿 구조로 수렴시키는 것을 권장한다.

예외적으로 **유형 자체가 개명되면 id도 함께 옮긴다**: 2026-09 `ac-e2e` →
`scenario-e2e` 개정에서 기존 7개 모델(`tbm_<slug>-ac-e2e`,
`tbm_<slug>-ac-e2e-1to1`)을 `tbm_<slug>-scenario-e2e`로 개명하고
`data/reconciliation-tasks/<id>.json` 파일명과 각 task의 `toBeModelId`를 함께
옮겼다. id를 옮길 때는 이 셋을 반드시 한 커밋에서 같이 바꿔야 이력이 끊기지 않는다.
