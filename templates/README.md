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
| `comment-necessity.tbm.md` | 주석 필요성 (필요 사유 없는 주석 제거) | 판정 범위의 모든 주석이 한 문장 필요 사유를 댈 수 있음 |
| `pr-manual-approval.tbm.md` | PR 수동 승인 정합성 | 판정기 하나·status 하나·ruleset required check로 이뤄진 단일 수동 승인 프로세스에서 정책 케이스 ↔ 판정기 ↔ 게이트의 정합(불변식 1), 그리고 케이스가 코드베이스를 따라가는가 — 앵커 실재·표면 포괄·제외 트립와이어·재검토 기한(불변식 2) |
| `data-model.tbm.md` | 데이터 모델 정합성 (ERD · 쿼리 패턴 · 인덱스) | `docs/data-model/`의 ERD ↔ 마이그레이션 적용 결과 전단사(불변식 1), 쿼리 패턴 카탈로그 ↔ 코드 쿼리 지점의 형태 기준 전단사(불변식 2), 패턴 ↔ 지원 인덱스를 빈 DB 쿼리 플랜으로 판정(불변식 3) — 판정은 대상 레포의 체커가 한다 |

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
**제품 기능을 만들지 않으며**, 산출물은 E2E 테스트·테스트 인프라·등재 문서다. 이 경계가
없으면 scenario-e2e 루프가 E2E를 쓰려고 화면·엔드포인트를 구현해 docs-impl과 같은
일을 두 번 하게 된다(2026-08 `tbm_econ-opinion-monitor-ac-e2e`의 AC3.7 슬라이스가
그 사례 — 당시 유형명은 ac-e2e였다). scenario-e2e의 "예외 목록"(E2E로 검증이 곤란
= 영구 면제)과 "구현 대기"(검증할 것이 아직 없음 = 임시 보류)는 성격이 다르므로
**별도 표**로 관리한다. 반대 방향도 고정부다: 기능은 있는데 **테스트 인프라**(픽스처·
하네스·E2E용 매니페스트·CI 배선·동작 무변경 테스트 진입점)가 없어 E2E를 못 쓰는 것은
구현 대기도 예외도 아닌 scenario-e2e 자신의 공백이며, 그 인프라를 만드는 것까지
scenario-e2e의 작업 범위다(e2e-mock-policy가 실환경 대체 수단을 직접 만드는 것과 같은
원칙). 이것을 구현 대기로 돌리면 인프라 부채가 해소 주체 없이 쌓인다.

docs-impl에서 **구현 의무를 만드는 문서는 AC와 사용자 여정 둘**이다(2026-09-28 개정).
여정 단계가 기술한 시스템 동작은 대응 AC가 없어도 미구현이면 drift이고, 같은 항목을
PRD·AC·테스트 문서가 기술하면 그쪽이 이긴다. 여정 전용 의무는 테스트 문서·E2E의 보호를
받지 않으므로 task가 「AC 미귀속 여정 의무」로 따로 목록화한다 — 그래서 scenario-e2e는
여전히 AC·시나리오만 보고, 여정 → 구현 사이는 docs-impl이 직접 본다. 생각·감정·측정
지표·여정이 스스로 범위 밖으로 표시한 것은 의무를 만들지 않는다.

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

**comment-necessity**는 어느 레포에나 얹을 수 있는 여섯 번째 유형으로, 앞의
다섯과 **화살표 방향이 반대**다. docs-impl이 "문서가 기술한 것이 코드에
있는가"(문서 → 코드의 누락)를 본다면, 이쪽은 "코드에 붙은 주석 하나하나가 존재
이유를 대는가"를 본다. 같은 소스 트리를 보므로 두 모델이
함께 트리거되는 구간이 있지만, as-is 지문이 **주석 줄에만 한정**되어 있어
판정 대상이 겹치지 않는다. 이 유형은 주석의 정확성을 따로 검사하지 않고, 문서·커밋
메시지 자체의 품질도 보지 않는다. 그리고 **입증 책임이 주석에 있다**: "이 주석을 지우면
고치러 온 사람이 틀린 판단을 하거나 확인에 상당한 비용을 치르는가"에 한 문장 사유를
댈 수 없으면 지운다 — 사유 없는 주석은 검증되지 않은 채 낡고, 지운 주석은 git 이력에
남기 때문이다(2026-09-29 전에는 "복원 가능한 주석 제거"였고 판단이 갈리면 남겼다).
언어 중립이며, 언어별 주석 패턴은 슬롯이 아니라 파일 이름으로 고르는 고정부 언어군 표다. 범위도
포함 목록이 아니라 **레포 전체 − 제외 세 부류**(① 문서 ② 편집 불가 ③ 주석 문법 없음)이고, 레포
고유 제외는 모델이 아니라 대상 레포 정책 본문의 `comment-scope-exclude` 블록에 둔다 — 포함 목록은 새
디렉터리를 조용히 흘리고, 제외가 대상 레포에 있어야 범위 수정이 data plane의 PR로 끝나기 때문이다. 정책은 파일 하나가 아니라
`docs/comment-policy/` 디렉터리에 본문(`README.md`)·원장(`ledger.md`)·판정 상세(`passes/`)로
나눠 두고 to-be는 그 디렉터리의 트리 해시로 본다 — 패스가 쌓이며 한 파일에서 본문이 판정 기록에
묻히던 것을 구조로 막는 고정부다.

**pr-manual-approval**은 PR 수동 승인 게이트를 둔 레포에 얹는 일곱 번째 유형으로, 앞의 여섯이
**레포의 내용**을 본다면 이쪽은 **레포에 들어오는 변경의 경로**를 본다 — 어떤 PR이 사람 승인을
거쳐야 하는가. 수동 승인은 레포당 **하나의 프로세스**다: 판정기 하나가 정책의 케이스 어디에도 닿지
않았다고 확인할 때만 status 하나에 success를 붙이고, 기본 브랜치 ruleset이 그 status를 required로
요구한다(판정기·status를 케이스별로 쪼개지 않는 것이 고정부 P1). status context는 슬롯이고, 이름이 케이스를 가리키면 케이스가
넓어질 때마다 워크플로·ruleset·정책을 동시에 건드리는 개명이 필요해지므로 케이스 중립 이름을
쓴다(예: `review/manual-approval`). 사람의 승인은 **항상 수동 status**
— 사람이 검토 후 같은 status를 붙인다(P7). 직접 붙이든 그 자리에서 사람이 지시한 승인 전용 도구로
붙이든 같다 — 수동인 것은 손이 아니라 판단이다. 그래서 사람 없이 도는 것은 붙이지 않고, 승인에 쓰는
도구는 승인 네임스페이스 밖의 context를 붙일 수 없어야 하며, required check는 특정 앱에 고정하지
않는다(P8). bypass는 승인 경로가 아니다. 정책 문서(프로세스 표 · 케이스 ·
표면/앵커 블록 · 의도적 제외 · 미탐 원장)가 SSOT이고 판정기 헤더 주석은 SSOT가 아니다. 불변식 1이
정책↔판정기↔ruleset 정합을, 불변식 2가 **케이스의 신선도**를 본다: 낡은 판정기는 실패하지 않고
조용히 success를 붙여 required check를 통과시키며 새기 때문에, 케이스가 지목한 경로의 실재(anchors)와
위험 신호가 새 파일에 나타나는 순간(surface)을 지문화하고, 지문이 볼 수 없는 사각지대는 재검토 기한
(최장 90일, `recheckAfter`)으로 덮는다. ruleset은 레포 밖 설정이지만 **일부러 지문에 넣지 않았다** — 호스트
게이트가 `versionScript.env`를 읽지 않아 무인증 호출이 되고, versionScript가 비0으로 끝나면
fail-closed 래퍼가 모든 모델의 감지를 건너뛰기 때문이다. 게이트 정합(R5)은 판정할 때마다 API로
조회한다. 표면·앵커 블록을 모델이 아니라
**대상 레포의 정책 문서**에 두는 것도 고정부다 — 표면이 낡았을 때의 수정이 대상 레포 PR로 끝나야
data plane이 스스로 수렴시킬 수 있다. 판정기 헤더가 정책을 되풀이하면 comment-necessity의 제거 대상이 되므로,
케이스 본문은 정책 문서에 두고 판정기에는 케이스 ID와 링크만 남기는 쪽으로 두 모델이 수렴한다.

**data-model**은 DB를 가진 레포에 얹는 여덟 번째 유형으로, `docs/data-model/`의 세 문서가 각자의 실재와 짝을
이룬다 — `erd.md`는 마이그레이션을 전부 적용한 스키마와, `query-patterns.md`는 코드의 쿼리 지점과 빈 DB의 쿼리
플랜과. 앞의 유형들이 대개 문서를 SSOT로 두고 코드를 맞춘다면 이쪽은 **문서가 실재를 따라간다**: 충돌하면 스키마가
이기고(적용된 마이그레이션은 사실이고 고칠 수 없으니 ERD를 고친다), 쿼리의 존재는 코드가 이기며, 인덱스 지원은
문서의 주장이 아니라 엔진이 판정한다. 땅을 바꾸는 유일한 경로는 지원 인덱스가 없을 때의 인덱스 추가 마이그레이션이고,
그 대안인 「풀스캔 허용」의 기준은 사람이 소유한다. 반대 방향의 미사용 인덱스는 등재만 하고 지우지 않는다. 귀속 키는
코드 주석 앵커가 아니라 **형태**(연산, 대상 테이블, 등치 조건 컬럼, 범위 조건, 정렬)이고, 정적으로 형태를 뽑을 수 없는
지점은 「수동 형태」 표로 간다. **체커를 대상 레포에 두는 것**과 그 체커와 versionScript가 **같은 범위 블록**
(README의 `data-model-scope`)을 읽는 것이 고정부다 — 추출 규칙이 낡았을 때 data plane이 대상 레포 PR 하나로
수렴시킬 수 있어야 하고, 범위 선언이 두 벌이면 지문과 판정이 서로 다른 코드를 본다. 그래서 이 유형의 versionScript에는
슬롯이 없다. 경계: `docs/data-model/`은 docs-impl의 to-be(`docs/` 트리)에도 들지만 판정은 이 유형이 전담하고, ERD가
의미를 위임한 코드 문서 주석은 comment-necessity에서 필요 사유를 가지며, 이 유형이 내는 인덱스 마이그레이션 PR은
pr-manual-approval의 마이그레이션 케이스에 걸려 사람 승인을 거칠 수 있다(정상 경로). 운영 성능·정렬 지원·ERD 밖
스키마 속성(기본값·CHECK·FK 동작·트리거·뷰)은 범위 밖이며 넣으려면 템플릿 개정이다.

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
  판정은 개수 독립적 서술("모든 시나리오는…", "(시나리오 수 − 예외 수) = (파일 수)")로 쓴다.
  대상이 늘면 버전이 바뀌어 재평가가 트리거되고 새 항목은 자동으로 판정 대상이 된다.
  등록 시점 현황을 두는 템플릿은 숫자를 definition의 "등록 시점 현황"에만 **스냅샷으로
  라벨링**해 두고, 현황 숫자 갱신은 각 task의 몫이다. docs-impl은 등록 시점 현황을 두지 않는다.
- **가변부(슬롯)** — `{{SLOT}}` 표기. 대상 레포·경로·시나리오 식별 체계·예외처럼 레포마다
  달라지는 값. 각 템플릿의 슬롯 표를 보고 **대상 레포를 실제로 탐색해** 채운다.
  탐색으로 확정되지 않는 값은 추측하지 말고 사용자에게 묻는다.

## 공통 규약 (템플릿 공통 기본값)

| 항목 | 규약 |
|---|---|
| id | `tbm_<slug>-docs-impl` / `tbm_<slug>-scenario-e2e` / `tbm_<slug>-e2e-mock-policy` / `tbm_<slug>-mockup-render` / `tbm_<slug>-journey-mockup` / `tbm_<slug>-comment-necessity` / `tbm_<slug>-pr-manual-approval` / `tbm_<slug>-data-model` (slug = 소문자 레포명) |
| metadata.name | `<slug> 제품 문서 ↔ 구현 정합성` / `<slug> 테스트 시나리오 ↔ E2E 1:1 정합성` / `<slug> E2E 모킹 최소화 (정책 ↔ 실제 모킹 지점)` / `<slug> 목업 ↔ 구현 렌더링 정합성` / `<slug> 사용자 여정 ↔ 목업 1:1 정합성` / `<slug> 주석 필요성 (필요 사유 없는 주석 제거)` / `<slug> PR 수동 승인 정합성` / `<slug> 데이터 모델 정합성 (ERD · 쿼리 패턴 · 인덱스)` |
| metadata.tags | `[<slug>, docs, implementation, consistency]` / `[<slug>, test-scenario, e2e, consistency]` / `[<slug>, e2e, mocking, test-policy, consistency]` / `[<slug>, mockup, ui, design-system, consistency]` / `[<slug>, journey, mockup, ux, consistency]` / `[<slug>, comments, documentation, consistency]` / `[<slug>, pr, review, manual-approval, ci, consistency]` / `[<slug>, data-model, schema, erd, query, index, consistency]` (+ 필요 시 도구·언어 태그: maestro, playwright, go, python 등) |
| versionScript | bash, `set -euo pipefail`, 결정적(타임스탬프·랜덤 금지). docs-impl·scenario-e2e는 `git rev-parse "HEAD:<path>"` 트리 해시(글롭이면 `ls-tree` 지문, 복수면 라벨 조합), `timeoutSeconds: 60`. e2e-mock-policy는 트리 해시 대신 grep 지문(sha256)을 쓰고 `timeoutSeconds: 120`. mockup-render는 트리 해시에 빌드 산출물 blob 해시를 더해 조합하고 `timeoutSeconds: 60`. journey-mockup은 트리 해시에 인덱스·허브 blob 해시를 더해 조합하되 부재는 `absent`로 표기하고 `timeoutSeconds: 60`. comment-necessity는 as-is에 레포 전체 − 제외에서 언어군별로 뽑은 주석 줄과 미분류 파일 경로의 grep 지문(sha256)을 쓰고 `timeoutSeconds: 120`, to-be는 `docs/comment-policy` 트리 해시(부재는 `absent`)에 `timeoutSeconds: 60`. pr-manual-approval은 to-be에 정책 문서 blob hash(부재는 `absent`, `timeoutSeconds: 60`), as-is에 `judges=…;surface=…;anchors=…` 라벨 조합(판정기 blob hash · 정책이 선언한 표면의 토큰형 grep 지문 · 앵커 실재 여부 — git 체크아웃만 쓰고 네트워크를 부르지 않는다)에 `timeoutSeconds: 120`. data-model은 to-be에 `docs/data-model` 트리 해시(부재는 `absent`, `timeoutSeconds: 60`), as-is에 `schema=…;queries=…;checker=…` 라벨 조합(마이그레이션 트리 해시 · README `data-model-scope` 블록 범위에서 쿼리 줄의 grep 지문 · 체커 해시 — 블록 부재는 `absent`, 깨지면 `malformed`, 슬롯 없음)에 `timeoutSeconds: 120` |
| lastObservedVersion/At | 등록 시 생략(첫 감지 sweep이 채운다) |

## 인스턴스화 절차

1. **대상 파악**: 대상 레포를 클론·탐색해 슬롯 표의 값을 확정한다
   (문서 경로, AC ID 체계, 구현/E2E 디렉터리, 예외 후보, 템플릿이 두는 경우 등록 시점 현황).
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

같은 달의 comment-redundancy **정책 디렉터리 개정**은 유형 이름이 그대로라 **id를 옮기지 않았다**.
기존 모델의 `toBe`(subPath·versionScript)와 definition만 새 구조로 고치고 `lastObservedVersion`은
건드리지 않는다 — 전환 뒤 첫 감지에서 to-be가 옛 blob hash에서 `absent`로 바뀐 것이 트리거가 되고,
그 task가 대상 레포의 단일 파일을 디렉터리로 옮긴다. 대상 레포에서 이 모델의 task가 실행 중이면
실행자의 수렴 검증이 바뀐 스크립트를 읽지 않도록 그 task가 닫힌 뒤에 전환한다.

2026-09-26 comment-redundancy **원장 형식 개정**(손으로 쓴 합계·잔량 제거, 판정 축 칸, 행 소속 불변식,
슬라이스 예산)은 버전 스크립트를 바꾸지 않고 definition만 고쳤다. 그래서 개정 자체는 트리거가 되지 않는다 —
열린 task가 있는 모델은 그 슬라이스의 착지로 생기는 다음 감지가, 열린 task가 없는 모델은 수동 트리거가 개정을
읽는다. 각 모델의 「개정 메모」가 이전의 완료 기준이고, 개정 전에 열린 task는 이전을 떠맡지 않는다.

2026-09-26 comment-redundancy **범위 개정**(포함 목록 → 레포 전체 − 제외)도 같은 규칙을 따른다. 기존 모델의
`asIs`(subPath 제거·versionScript 교체)와 definition만 고치고 id와 `lastObservedVersion`은 그대로 둔다 —
전환 뒤 첫 감지에서 as-is 지문이 바뀐 것이 트리거가 되고, 그 task가 새로 범위에 든 파일의 판정과
(필요하면) 대상 레포의 `comment-scope-exclude` 블록 신설, 그리고 원장 게이트가 실측 파일 집합을 계산하는
범위를 새 규칙으로 맞추는 일을 맡는다. 새 범위의 줄 수가 크게 느는 것은
예상된 것이다. 이 모델의 task가 열려 있는 동안은 전환하지 않는다(위와 같은 이유).

2026-09-26 comment-redundancy **지문 표면 개정**(L 줄머리 주석에 D Python docstring 본문 · E 줄 끝·줄 중간 주석을
더함)도 id와 `lastObservedVersion`을 그대로 둔다. L 표면과 첫 진단 줄은 바이트 그대로라 원장·게이트가 세는 값과
`lines=` 값·델타로 적힌 완료 기준은 전환 전후 같다 — 어긋나는 것은 해시 절대값뿐이다. 그래서 이 개정은 사용자
지시로 **열린 task가 있는 채** 네 모델을 함께 전환했다(범위 개정과 같은 의도적 예외). 전환 뒤 첫 감지 task가
대상 레포 정책 본문의 사각지대 서술과 원장의 D·E 표면 표를 들인다.

2026-09-29 **필요성 개정**은 유형 자체를 바꿨다 — 판정 기준을 "복원 가능한가"에서 "한 문장 필요 사유를 댈 수
있는가"로, 애매하면 남기던 기본값을 사유를 못 대면 지우는 쪽으로, 원장의 판정 축 `①②③④`를 판정 칸 `완료`/`—`로.
그래서 `ac-e2e` → `scenario-e2e`와 같이 **id를 옮겼다**: 템플릿 `comment-redundancy.tbm.md` → `comment-necessity.tbm.md`,
네 모델 `tbm_<slug>-comment-redundancy` → `tbm_<slug>-comment-necessity`, task 파일명과 각 task의 `toBeModelId`를
한 커밋에서 옮기고, 자매 모델 definition의 교차 참조도 같은 커밋에서 고쳤다. 위 문단들의 `comment-redundancy`는 당시
이름이다. task 본문 안의 옛 id 언급은 이력이라 고치지 않는다. `lastObservedVersion`은 그대로 옮기고, versionScript
출력도 그대로라(제외 ① 설명 주석만 고침) 개정 자체는 트리거가 되지 않는다 — 모델마다 수동 트리거로 첫 감지를 연다.
그 task가 대상 레포 정책 본문(필요성 시험·유지 대상)과 원장 게이트의 판정 표기를 새 형식으로 바꾸고, 기존 행을 모두
`—`로 되돌리고, 대상 레포 안의 옛 모델 id 참조를 고친다(각 모델의 「개정 메모 (2026-09-29)」가 완료 기준). 옛 기준의
`①②③④`는 새 기준의 판정 완료가 아니다 — 복원 불가로 남긴 주석도 필요 사유를 다시 대야 한다. 전환 시점에 네 모델
모두 열린 task가 없었다.

## doc-tracker 경로 해석

`product-doc-engineer`는 문서 체계 상태 추적을 **폴더 아래 월별 파일**(`<x>-doc-tracker/` +
`index.md` + `YYYY-MM.md`)로 관리한다. 여러 유형이 tracker 안의 섹션(e2e 매핑·예외·구현 대기 표,
모킹 경계 레지스트리, 여정 mockup 예외, 목업↔구현 편차 허용목록 등)을 SSOT로 쓰므로 규약은 다음과 같다.

- **경로 슬롯 `{{TRACKER_DIR}}`에는 tracker 폴더**(`docs/doc-tracker`)를 적는다. 모델이 읽는 대상은
  그 폴더의 **가장 최근 `YYYY-MM.md`**다(`index.md`가 아니다).
- 버전에는 **등재 섹션만** 잘라 sha256을 쓴다. 파일 전체나 폴더 트리 해시를 쓰지 않는다 — 월 파일은
  요약·위험·변경 이력이 매번 바뀌고, 월 경로 자체도 달마다 바뀐다. 등재 섹션은
  `<!-- registry: <tbm id> -->` 표식과 함께 롤오버 때 **바이트 그대로 이월**되므로(스킬 규약),
  등재 내용이 같으면 해시도 같다.
- 섹션 = 제목 줄부터 같은 레벨 이상의 다음 제목 직전까지(하위 제목 포함, 코드 블록 안 `#` 줄 무시).
  제목은 **접두 일치**로 찾는다. 폴더·월 파일·섹션이 없으면 `absent`(조용한 상수 금지).
- 등록할 때 대상 레포의 그 섹션에 표식(`<!-- registry: tbm_<slug> -->`)이 달려 있는지 확인하고,
  없으면 첫 task 범위에 표식 추가를 넣는다. definition에는 "최신 월 파일의 「<섹션>」"으로 적는다.

versionScript에는 아래 조각을 `set -euo pipefail` 바로 다음에 **그대로** 붙이고 쓴다(런타임에
공유 라이브러리가 없으므로 인라인 복사가 원본이다).

```bash
# ── doc-tracker 등재 섹션 해석 (templates/README.md 「doc-tracker 경로 해석」 공통 조각) ──
# tracker = 폴더 아래 월별 파일. 가장 최근 YYYY-MM.md 에서 등재 섹션만 잘라 해시한다.
# 등재 섹션은 product-doc-engineer 규약상 롤오버 때 바이트 그대로 이월되므로, 달이 바뀌어도
# 섹션 내용이 같으면 해시가 같다(월 파일 경로는 버전에 넣지 않는다).
tracker_month() {  # $1 = tracker 폴더 → 최신 월 파일 경로(없으면 빈 출력)
  local f
  f="$(git ls-tree --name-only "HEAD:$1" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}\.md$' | LC_ALL=C sort | tail -n1 || true)"
  if [ -n "$f" ]; then printf '%s/%s\n' "$1" "$f"; fi
}
tracker_section() {  # $1 = 파일 경로, $2 = 제목 접두(예: '## e2e 매핑') → 섹션 본문
  # 섹션 = 제목 줄부터 같은 레벨 이상(# 개수 ≤)의 다음 제목 직전까지. 코드 블록 안의 # 줄은 제목이 아니다.
  git show "HEAD:$1" 2>/dev/null | awk -v t="$2" '
    /^(```|~~~)/ { fence = !fence }
    function lvl(s) { match(s, /^#+/); return RLENGTH }
    !f && !fence && index($0, t) == 1 { f = 1; L = lvl($0); print; next }
    f && !fence && /^#+ / && lvl($0) <= L { exit }
    f { print }' || true
}
tracker_registry_hash() {  # $1 = tracker 폴더, $2 = 등재 섹션 제목 접두 → sha256 | absent
  local m sec
  m="$(tracker_month "$1")"
  if [ -z "$m" ]; then echo absent; return; fi
  sec="$(tracker_section "$m" "$2")"
  if [ -z "$sec" ]; then echo absent; return; fi
  printf '%s' "$sec" | sha256sum | cut -d' ' -f1
}
# ── /doc-tracker 등재 섹션 해석 ──
```

사용 예(scenario-e2e 조합형의 reg 성분):

```bash
t="$(tracker_registry_hash '{{TRACKER_DIR}}' '{{REG_TITLE}}')"
```
