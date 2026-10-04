# 템플릿: 데이터 모델 정합성 (data-model)

DB를 가진 레포에서 **데이터 모델 문서(`docs/data-model/`)** 가 실제 스키마·실제 쿼리·실제 인덱스와
어긋나지 않게 유지하는 모델. 문서는 세 장이고, 각 장이 서로 다른 실재와 짝을 이룬다.

| 문서 | 짝을 이루는 실재 | 충돌 시 이기는 쪽 |
|---|---|---|
| `erd.md` | 마이그레이션을 전부 적용한 스키마 | **스키마** |
| `query-patterns.md` 의 패턴·호출 지점 | 코드의 쿼리 지점 | 존재 여부는 **코드** |
| `query-patterns.md` 의 지원 인덱스 칸 | 빈 DB에서 엔진이 낸 쿼리 플랜 | **엔진** |

정합 상태 = **불변식 1 ∧ 불변식 2 ∧ 불변식 3**. 세 불변식 모두 문서가 실재를 **따라가는** 방향이다
— 이 유형에서 문서는 설계서가 아니라 지도다. 지도를 고치려고 땅을 바꾸지 않는다. 땅을 바꾸는 단 하나의
예외는 불변식 3의 인덱스 추가이고, 그것도 문서가 아니라 엔진 판정이 근거다.

판정은 사람이나 에이전트가 문서를 읽어서 하지 않고 **대상 레포에 둔 체커**가 한다. 체커가 대상 레포에
있어야 추출 규칙이 낡았을 때(새 쿼리 레이어, 새 디렉터리, 정적 추출이 놓치는 관용구) data plane이
**대상 레포 PR 하나로** 스스로 수렴시킬 수 있다 — 체커나 범위 선언이 모델(reconciler)에 있으면 규칙
개정마다 control plane 작업이 된다.

## 불변식 (고정부)

### 불변식 1 — ERD ↔ 실제 스키마 전단사

`erd.md`가 선언한 원소 집합 == 마이그레이션을 **전부** 적용한 결과의 원소 집합. 원소와 그 동일성은 다음과 같다.

| 원소 | 동일성 키 | 함께 같아야 하는 속성 |
|---|---|---|
| 테이블 | 이름 | — |
| 컬럼 | (테이블, 이름) | 타입, NULL 허용 |
| PK | (테이블, 컬럼 순서열) | — |
| FK | (테이블, 컬럼 순서열) → (참조 테이블, 참조 컬럼 순서열) | — |
| 인덱스 | (테이블, 컬럼·식 순서열, UNIQUE 여부, 부분 인덱스 조건) | 라벨(아래 「인덱스 라벨」) |

- **실제 스키마는 엔진이 말한다.** 빈 DB에 마이그레이션을 순서대로 전부 적용한 뒤 엔진 카탈로그(SQLite
  `PRAGMA table_info`·`index_list`·`foreign_key_list`, PostgreSQL `information_schema`·`pg_catalog`)에서
  읽는다. 마이그레이션 SQL 텍스트를 정규식으로 해석하지 않는다 — `ALTER`·재생성·삭제가 쌓이면 텍스트로는
  최종 상태를 알 수 없다.
- **타입**은 엔진 카탈로그가 보고하는 선언 타입 문자열을 정규화(대문자, 공백 1칸)한 것이다. 엔진이
  다르게 보고하는 동의어를 문서에서 다르게 적지 않는다.
- 스키마 관리용 테이블(마이그레이션 이력, 엔진 내부 테이블)은 README 블록 `schema-exclude:`로 뺀다.
- **충돌하면 스키마가 이긴다.** 적용된 마이그레이션은 사실이고 고칠 수 없으므로 ERD를 고친다. ERD에 맞추려고
  마이그레이션을 새로 쓰거나 기존 마이그레이션을 수정하지 않는다. 스키마를 바꾸고 싶다면 그것은 이 모델
  밖에서 마이그레이션을 먼저 쓰는 일이고, ERD는 그 결과를 따라온다.

### 불변식 2 — 쿼리 패턴 카탈로그 ↔ 코드 쿼리 지점 전단사

코드의 모든 쿼리는 카탈로그의 패턴 **하나**에 귀속되고, 카탈로그의 모든 패턴은 **실재하는** 호출 지점을
하나 이상 가진다.

- **귀속 키는 형태(shape)다.** 코드 주석 앵커(`// Q-12` 같은 표식)가 아니다. 앵커는 쿼리가 바뀌어도 그대로
  남아 거짓 귀속을 만들고, 앵커 없는 새 쿼리는 아무 데도 안 걸린다. 형태는 쿼리 텍스트에서 계산되므로
  쿼리가 바뀌면 귀속도 바뀐다(「형태」 절).
- 판정 단위는 (호출 지점, 형태) 쌍이다. 호출 지점 = `파일::함수`(메서드면 `파일::타입::메서드`).
  - 코드의 (지점, 형태)가 어느 패턴 행에도 없으면 **미등재 쿼리**.
  - 패턴 행이 적은 지점이 실재하지 않거나 그 지점에 그 형태의 쿼리가 없으면 **죽은 지점**. 살아 있는 지점이
    하나도 없는 패턴은 **죽은 패턴**.
  - 같은 형태를 두 행이 가지면 **귀속 모호**. 형태가 키이므로 행은 형태마다 하나다.
- **존재 여부에서는 코드가 이긴다.** 미등재 쿼리는 카탈로그에 더하고(같은 형태의 행이 있으면 그 행에 지점을
  더한다), 죽은 지점·죽은 패턴은 카탈로그에서 지운다. 카탈로그에 맞추려고 쿼리를 만들거나 지우지 않는다.
- **정적으로 형태를 뽑을 수 없는 지점**(동적 문자열 조립(Rust `format!`, Go 문자열 연결·`fmt.Sprintf`), 런타임에 고르는 테이블·정렬 등)은 「수동 형태」
  표에 지점별로 등재한다. 체커가 추출 불가로 보고한 지점 집합 == 수동 형태 표의 지점 집합(양방향). 수동
  형태도 패턴에 귀속되므로 그 지점은 패턴 행의 호출 지점에도 적힌다. 동적 조립이 형태를 여럿 만들면 형태마다
  한 행을 둔다.

### 불변식 3 — 패턴 ↔ 인덱스 지원

각 패턴은 자기를 지원하는 인덱스(PK·UNIQUE 포함)를 지목하거나 「풀스캔 허용」 사유를 적는다. 그리고 그
칸은 **엔진의 판정과 같아야 한다.**

- **판정은 문서의 주장으로 하지 않는다.** 체커가 마이그레이션으로 만든 **빈 DB**에서 패턴의 모든 지점 SQL
  (수동 형태는 대표 SQL)을 플랜하고, 테이블 접근마다 (테이블, 인덱스 라벨 | 풀스캔)을 얻는다.
  - **지원** = 인덱스 조건이 붙은 접근(SQLite `SEARCH … USING [COVERING] INDEX`·`USING INTEGER PRIMARY KEY`·
    `USING PRIMARY KEY`, PostgreSQL `Index Cond`가 있는 `Index Scan`·`Index Only Scan`·`Bitmap Index Scan`).
  - **풀스캔** = 그 밖의 모든 접근. 인덱스를 끼고 전체를 훑는 접근(SQLite `SCAN … USING INDEX`, `Index Cond`
    없는 `Index Scan`)도 풀스캔이다.
  - 지원 칸이 지목한 인덱스 ≠ 엔진이 쓴 인덱스, 지원 칸은 인덱스인데 엔진은 풀스캔, 지원 칸은 풀스캔 허용인데
    엔진은 인덱스를 씀 — 셋 다 drift다. 마지막 경우는 문서를 엔진 쪽(인덱스 지목)으로 고친다.
  - 같은 패턴의 지점들이 서로 다른 플랜을 받으면 drift다(형태가 같아도 식·함수 때문에 갈릴 수 있다). 지점을
    고치든 형태 정의를 정밀화하든 task가 정한다.
  - 접근 조건이 없는 쓰기(조건 없는 `INSERT`, `ON CONFLICT` 포함)는 지원 칸이 `—`이고 이 불변식에서 빠진다.
- **반대 방향도 본다.** 어떤 패턴의 플랜도 쓰지 않는 인덱스(PK 제외)는 「미사용 인덱스」 표에 등재한다.
  엔진이 실제로 쓰지 않는 인덱스 집합 == 미사용 인덱스 표의 집합(양방향). **등재만 하고 삭제하지 않는다** —
  무결성 제약, 운영 중 수동 조회, 곧 올 기능 같은 이 모델이 볼 수 없는 존재 이유가 있을 수 있고, 삭제는 사람의
  결정이다.
- **지원 인덱스가 없으면 해소 경로는 둘이다.**
  1. 인덱스를 추가하는 **마이그레이션 PR**을 낸다. 새 마이그레이션 파일만 더하고(기존 파일 수정 금지), 같은
     PR에서 ERD 인덱스 표와 카탈로그 지원 칸을 함께 고친다(불변식 1·3을 한 번에 닫는다).
  2. README의 **풀스캔 허용 기준**에 해당하면 사유를 적어 등재한다: `풀스캔 허용(F<n>): <구체 근거>`.
  고르는 규칙: 기존 기준 하나에 해당하면 2, 아니면 1. **기준을 새로 만들거나 넓히는 것은 사람의 결정**이다
  — data plane은 기준을 발명하지 않는다. 기준이 필요해 보이면 PR 설명에 제안만 남긴다.
- 빈 DB 플랜은 **지원 가능성**을 묻는 것이지 운영 성능을 묻는 것이 아니다. 데이터가 없으면 비용 기반
  플래너가 순차 스캔을 고르기 쉬우므로 체커는 엔진 설정으로 그 편향을 없앤다(「체커 계약」 C5).

## 형태 (고정부)

형태 = **(연산, 대상 테이블, 등치 조건 컬럼, 범위 조건, 정렬)**. 표기는 한 줄, 다섯 칸을 ` | `로 나눈다.

```text
<연산> <테이블[,테이블…]> | eq(<…>) | range(<…>) | order(<…>)
select messages | eq(session_id) | range(created_at) | order(created_at desc)
select messages,sessions | eq(messages.session_id=sessions.id, sessions.user_id) | - | order(messages.created_at desc)
update sessions | eq(id) | - | -
insert messages | - | - | -
```

| 칸 | 규칙 |
|---|---|
| 연산 | `select` · `insert` · `update` · `delete` · `upsert`(`INSERT … ON CONFLICT`·`REPLACE`). `SELECT … FOR UPDATE`는 `select`. |
| 대상 테이블 | `FROM`·`JOIN`·`UPDATE`·`DELETE FROM`·`INSERT INTO`의 테이블. 여럿이면 이름순으로 `,` 연결. 별칭은 테이블명으로 되돌린다. |
| eq | `=`·`IS`·`IN (…)`으로 비교되는 컬럼, 조인 등치는 `a.x=b.y`. `upsert`는 충돌 대상 컬럼. 이름순·중복 제거. |
| range | `<`·`<=`·`>`·`>=`·`BETWEEN`·`LIKE`로 비교되는 컬럼. 이름순·중복 제거. |
| order | `ORDER BY` 목록을 **원래 순서대로**, 각 항목에 `asc`/`desc`(생략 시 `asc`). |

- 조건의 왼쪽이 컬럼이 아니라 식이면(`lower(email) = ?`) 식 텍스트를 정규화해 그대로 쓴다 — `eq(lower(email))`.
  식은 인덱스 사용 여부를 바꾸므로 컬럼으로 뭉개지 않는다.
- `OR`로 묶인 조건, `!=`·`NOT`·`NOT IN`은 형태에 넣지 않는다. 지원 여부는 어차피 엔진이 판정한다.
- 선택 컬럼, `LIMIT`·`OFFSET`, `GROUP BY`, 집계, `RETURNING`은 형태가 아니다.
- 빈 칸은 `-`. 식별자는 소문자, 따옴표 제거. 테이블이 하나면 컬럼명만, 여럿이면 `테이블.컬럼`.
- 서브쿼리·CTE·`UNION`은 바깥 쿼리와 한 형태로 합친다(테이블·조건 합집합, `테이블.컬럼` 표기). 체커가 합칠 수
  없으면 추출 불가로 보고하고, 그 지점은 수동 형태로 간다.

### 인덱스 라벨

카탈로그 지원 칸과 ERD 인덱스 표가 같은 이름으로 인덱스를 부르기 위한 규칙.

- 마이그레이션이 이름을 준 인덱스 → 그 이름(`idx_messages_session_created`).
- PK → `PK(<테이블>)`.
- 제약에서 엔진이 만든 이름 없는 UNIQUE(SQLite `sqlite_autoindex_*`, PostgreSQL 자동 이름 `*_key`) →
  `UNIQUE(<테이블>.<컬럼>,…)`.
- 조인 패턴의 지원 칸은 테이블마다: `messages: idx_messages_session_created; sessions: PK(sessions)`.

## 대상 레포 배치 (고정부)

```
docs/data-model/
  README.md          # 형태 정의 · 풀스캔 허용 기준 · 추출 제외 범위 · 체커
  erd.md             # mermaid erDiagram + 엔티티별 구조 표 (의미는 코드 문서 주석 링크)
  query-patterns.md  # ID | 형태 | 지원 인덱스 또는 허용 사유 | 호출 지점(파일::함수)
```

경로는 모든 인스턴스에서 같다(슬롯이 아니다). 제목 문구는 레포 언어에 맞춰도 되지만 **표의 열과 기계
판독 블록의 형식은 고정**이다 — 체커가 읽는다.

### `README.md`

1. **형태 정의** — 이 템플릿의 「형태」 절을 따른다는 선언과, 레포 고유의 정규화(쿼리 레이어의 관용구, 식
   정규화 예)만 덧붙인다. 템플릿 규칙을 바꾸지 않는다 — 바꾸려면 템플릿 개정이다.
2. **풀스캔 허용 기준** — 표 `ID | 기준 | 관측 가능한 근거`. ID는 `F1`, `F2` …. 근거는 코드나 스키마에서
   확인할 수 있는 것으로 쓴다(예: "행 수 상한이 시드 마이그레이션·코드 상수로 고정", "관리자 수동 실행
   경로에서만 호출"). **사람이 소유한다.**
3. **추출 제외 범위** — 무엇을 왜 빼는지의 서술과, 체커·versionScript가 **함께** 읽는 블록 하나:

   ````text
   ```data-model-scope
   migrations: migrations
   checker: tools/data-model-check
   scope: crates/*/src
   exclude: (^|/)tests?/|/fixtures/
   site: sqlx::query(_as|_scalar)?(::<[^>]*>)?!?\(
   sql: \b(FROM|JOIN|INTO|DELETE FROM) [a-z_]+\b|\bUPDATE [a-z_]+( +SET\b| *\\?$)|\bWHERE\b|\b(AND|OR) \(?[a-z_.()]+ *(=|<|>|!=|IN |IS |LIKE|BETWEEN)|\bORDER BY\b|\bON CONFLICT\b
   schema-exclude: ^(_sqlx_migrations|sqlite_sequence)$
   ```
   ````

   | 키 | 의미 | 여러 줄 |
   |---|---|---|
   | `migrations` | 마이그레이션 디렉터리 | 한 줄 |
   | `checker` | 체커 경로(파일 또는 디렉터리) | 한 줄 |
   | `scope` | 쿼리를 찾는 `git ls-files` 경로 목록, 공백 구분 | 합집합 |
   | `exclude` | scope에서 빼는 경로 ERE | `\|`로 합침 |
   | `site` | 쿼리 지점 토큰 ERE. **이 ERE에 걸리는 줄은 체커가 반드시 지점 후보로 본다** | `\|`로 합침 |
   | `sql` | 쿼리 텍스트 줄 ERE(지문 전용 — 형태가 바뀌면 버전이 바뀌게). **형태를 싣는 줄만** 잡는다: 테이블(`FROM`·`JOIN`·`INTO`·`UPDATE`·`DELETE FROM` 뒤 식별자), 조건(`WHERE`, `AND`/`OR` 뒤 비교), `ORDER BY`, `ON CONFLICT`. 선택 컬럼·`VALUES`·`SET` 줄은 형태가 아니라 넣지 않는다 — 넣으면 주석의 SQL 단어나 `DELETE /api/…` 같은 HTTP 문구까지 걸려 무관한 트리거가 생긴다 | `\|`로 합침 |
   | `schema-exclude` | 불변식 1에서 빼는 테이블 이름 ERE(체커 전용) | `\|`로 합침 |

   제외는 **쿼리가 아닌 것**(테스트·픽스처·생성물·마이그레이션 자체)만 뺀다. 제품 경로의 쿼리를 체커가
   어려워한다는 이유로 빼지 않는다 — 그건 수동 형태로 간다.
4. **체커** — 실행 명령, 엔진과 버전, CI 위치와 모드, 종료 코드의 뜻.

### `erd.md`

- **다이어그램** — ` ```mermaid ` 펜스의 `erDiagram` 하나. **엔티티와 관계만** 적고 속성은 적지 않는다(구조
  표와 두 벌이 된다). FK 하나 = 관계 하나, 라벨은 FK 컬럼. 카디널리티는 FK에서 기계적으로 정한다: 부모 쪽은
  FK가 NOT NULL이면 `||`, NULL 허용이면 `|o`, 자식 쪽은 FK 컬럼이 UNIQUE면 `o|` 아니면 `o{`.
- **엔티티** — 테이블마다 `### \`<테이블>\`` 제목과:
  - `의미:` 한 줄 — 대응 도메인 타입의 **코드 문서 주석으로 가는 링크**. 의미 문장은 ERD에 쓰지 않는다.
  - 컬럼 표 `컬럼 | 타입 | NULL | 키`. NULL은 `YES`/`NO`, 키는 `PK` · `FK → <테이블>.<컬럼>` · 빈칸.
  - 인덱스 표 `인덱스 | 컬럼 | UNIQUE | 조건`. 라벨은 「인덱스 라벨」, 컬럼은 순서대로, 조건은 부분 인덱스
    `WHERE` 식 또는 `-`. PK는 컬럼 표의 `키`로 표현하고 인덱스 표에 다시 적지 않는다.

### `query-patterns.md`

- **패턴** — 표 `ID | 형태 | 지원 인덱스 또는 허용 사유 | 호출 지점`.
  - ID는 사람이 부르기 위한 안정 라벨(`Q-01` …)이고 **귀속 키가 아니다**. 지워진 ID는 재사용하지 않는다.
  - 형태는 「형태」 표기 그대로, 백틱 안에.
  - 지원 칸은 인덱스 라벨 · `풀스캔 허용(F<n>): <근거>` · `—`(접근 조건 없는 쓰기) 중 하나.
  - 호출 지점은 `파일::함수`를 `, `로 나열. 파일은 레포 루트 상대 경로.
- **수동 형태** — 표 `호출 지점 | 패턴 ID | 대표 SQL | 추출 불가 사유`. 대표 SQL은 자리표시자(`?`·`$1`)를 쓴
  실행 가능한 SQL이다 — 불변식 3의 플랜이 이 SQL로 돈다. 사유는 "동적 `format!`으로 정렬 컬럼 선택"처럼 무엇이
  정적 추출을 막는지 쓴다.
- **미사용 인덱스** — 표 `인덱스 | 테이블 | 비고`. 비고는 아는 존재 이유(무결성 제약 등) 또는 `-`.

## 체커 계약 (고정부)

체커의 구현 언어·도구는 레포가 정한다. 지켜야 하는 것은 다음이다.

| ID | 계약 |
|---|---|
| C1 위치 | 대상 레포 안, README 블록 `checker:` 경로. 실행 명령은 README 「체커」 절. 그 레포의 PR로 고친다. |
| C2 입력 | README 블록, `docs/data-model/` 세 파일, 마이그레이션, scope − exclude 소스. 범위 선언은 **블록 한 곳**에서만 읽는다(체커 코드에 범위를 따로 하드코딩하지 않는다 — versionScript와 두 벌이 된다). |
| C3 스키마 관측 | 빈 DB에 마이그레이션을 순서대로 **전부** 적용하고(up/down 쌍이면 up만, 레포의 마이그레이션 도구와 같은 순서로) 엔진 카탈로그로 실제 스키마를 읽는다. 마이그레이션 적용이 실패하면 판정 불가. |
| C4 지점 추출 | `site` ERE에 걸리는 줄을 모두 지점 후보로 보고 각각을 (지점, 형태, SQL)로 산출하거나 (지점, 추출 불가 사유)로 산출한다. **조용히 건너뛰는 후보는 없다.** 지문(`site`)이 보는 줄과 체커가 보는 줄이 어긋나지 않게 하는 계약이다. |
| C5 플랜 | 지점 SQL·대표 SQL을 C3의 빈 DB에서 플랜한다. SQLite는 `ANALYZE` 없이 `EXPLAIN QUERY PLAN`. PostgreSQL은 `enable_seqscan = off`로 빈 테이블의 순차 스캔 편향을 없애고, 자리표시자는 일반 플랜으로(16 이상 `EXPLAIN (GENERIC_PLAN)`, 그 아래는 `plan_cache_mode = force_generic_plan` + `PREPARE`/`EXPLAIN EXECUTE`에 NULL). 엔진 버전은 운영 엔진에 맞추고 리포트에 적는다. |
| C6 출력 | 위반을 불변식·항목별로 사람이 읽는 형태로, `--json`이면 기계 판독형으로 낸다. 종료 코드 **0 정합 · 1 위반 · 2 판정 불가**(엔진 없음, 마이그레이션 실패, 문서·블록 파싱 실패). 판정 불가를 0으로 뭉개지 않는다. |
| C7 읽기 전용 | 문서와 코드를 고치지 않는다. 대신 위반마다 **기대하는 행**(ERD 표 행, 카탈로그 행, 미사용 인덱스 행)을 출력해 수정 PR이 그것을 옮겨 적게 한다. |
| C8 결정성 | 같은 커밋 → 같은 출력. 모든 목록을 정렬한다. |
| C9 CI | PR과 기본 브랜치에서 돈다. 머지 차단 여부는 `{{CI_MODE}}`. 판정 불가(2)는 모드와 관계없이 실패로 표시한다. |

## 슬롯 표

대상 레포를 탐색해 확정한다. 확정 안 되는 값은 추측하지 말고 사용자에게 묻는다. versionScript에는 슬롯이
**없다** — 두 스크립트는 고정 경로 `docs/data-model`과 README 블록만 읽는다. 아래 슬롯 중 블록에 들어갈 값은
definition의 초기 상태 메모에 **첫 task가 만들 블록의 초안**으로 남긴다.

| 슬롯 | 의미 | 예 (가상의 Rust · sqlx · SQLite 레포) |
|---|---|---|
| `{{REPO}}` | owner/repo | `dlddu/example` |
| `{{SLUG}}` | id·이름용 소문자 레포명 | `example` |
| `{{DB_ENGINE}}` | 운영 DB 엔진과 버전 | SQLite 3.45 (`libsqlite3-sys` bundled) |
| `{{QUERY_LAYER}}` | 쿼리를 내는 코드 레이어와 정적 추출의 단서·장애물 | `sqlx::query!`·`query_as!` 매크로(SQL 리터럴), 목록 필터를 `format!`으로 조립하는 지점 있음 |
| `{{SCOPE_DRAFT}}` | README 블록 초안(`migrations`·`checker`·`scope`·`exclude`·`site`·`sql`·`schema-exclude`) | 위 「`README.md`」 절의 예시 블록 |
| `{{CHECKER_RUN}}` | 체커 실행 명령(초안) | `python3 tools/data-model-check/check.py --json` |
| `{{CI_MODE}}` | 체커 CI의 머지 차단 여부: `gate` 또는 `report` | 첫 수렴 전 `report`, 세 불변식이 처음 참이 된 뒤 `gate` 권장 |
| `{{SIBLING_MODELS}}` | 경계를 맞출 자매 모델 [선택] | `tbm_example-docs-impl` · `tbm_example-comment-necessity` · `tbm_example-pr-manual-approval` |
| `{{INITIAL_STATE}}` | 등록 시점 현황(스냅샷) | `docs/data-model/` 없음 · 마이그레이션 14개 · 테이블 9개 · `query!` 지점 약 40곳 · 체커 없음 |
| `{{NOW_ISO}}` | 등록 시각 (UTC ISO 8601) | `date -u +%Y-%m-%dT%H:%M:%SZ` |

## 모델 JSON 골격

```json
{
  "id": "tbm_{{SLUG}}-data-model",
  "metadata": {
    "name": "{{SLUG}} 데이터 모델 정합성 (ERD · 쿼리 패턴 · 인덱스)",
    "description": "{{REPO}}의 docs/data-model/이 실재와 어긋나지 않는 상태를 추적한다: ERD ↔ 마이그레이션 적용 결과 전단사(불변식 1, 스키마가 이김), 쿼리 패턴 카탈로그 ↔ 코드 쿼리 지점 형태 기준 전단사(불변식 2, 존재는 코드가 이김), 패턴 ↔ 지원 인덱스를 빈 DB 쿼리 플랜으로 판정(불변식 3, 엔진이 이김). 판정은 대상 레포의 체커가 한다.",
    "tags": ["{{SLUG}}", "data-model", "schema", "erd", "query", "index", "consistency"],
    "createdAt": "{{NOW_ISO}}"
  },
  "definition": "<definition 본문 템플릿을 채워 넣기>",
  "toBe": {
    "dataSource": { "type": "github", "repository": "{{REPO}}", "ref": "main", "subPath": "docs/data-model" },
    "versionScript": { "runtime": "bash", "code": "<to-be 스크립트>", "timeoutSeconds": 60 }
  },
  "asIs": {
    "dataSource": { "type": "github", "repository": "{{REPO}}", "ref": "main" },
    "versionScript": { "runtime": "bash", "code": "<as-is 스크립트>", "timeoutSeconds": 120 }
  }
}
```

- as-is는 마이그레이션·체커·쿼리 범위를 가로지르고 그 경로를 README 블록에서 읽으므로
  `asIs.dataSource.subPath`를 두지 않는다(스크립트가 진실).
- `env`는 두지 않는다. 두 스크립트 모두 git 체크아웃만 쓰고 네트워크·빌드·체커 실행을 하지 않는다 —
  versionScript가 비0으로 끝나면 fail-closed 래퍼가 그 fire의 **모든 모델 감지**를 건너뛰기 때문이다
  (pr-manual-approval 템플릿 「ruleset을 지문에 넣지 않는 이유」와 같은 제약).

## versionScript

**to-be** — `docs/data-model` 트리 해시. 디렉터리가 **없는 상태도 유효한 관측**이므로 `absent`를 출력한다.

```bash
#!/usr/bin/env bash
# to-be = 데이터 모델 문서(docs/data-model) 트리 해시. 디렉터리가 없으면 'absent'.
# 런타임이 dataSource.repository@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
git rev-parse --verify --quiet "HEAD:docs/data-model" || echo "absent"
```

**as-is** — 세 성분의 라벨 조합 `schema=…;queries=…;checker=…`. 경로·범위는 README의 `data-model-scope`
블록에서 읽는다.

| 성분 | 무엇의 지문인가 | 무엇에 반응하나 | 반응하지 않는 것 |
|---|---|---|---|
| `schema` | `migrations:` 디렉터리 트리 해시 | 마이그레이션 추가·변경(불변식 1·3) | 코드 변경 |
| `queries` | scope − exclude 파일에서 `site`·`sql` ERE에 걸리는 줄의 (파일, 공백 정규화한 줄) 목록 sha256 | 쿼리 지점의 추가·삭제·SQL 변경, 쿼리가 든 파일의 이동(불변식 2·3) | 줄 번호 이동, 들여쓰기, 쿼리와 무관한 줄 |
| `checker` | `checker:` 경로의 blob/트리 해시 | 추출 규칙·플랜 규칙 개정 — 같은 코드라도 판정이 달라질 수 있다 | — |

```bash
#!/usr/bin/env bash
# as-is = 데이터 모델의 실재 지문. schema · queries · checker 세 성분의 라벨 조합.
# 경로·범위는 docs/data-model/README.md 의 ```data-model-scope 블록에서 읽는다(체커와 같은 선언).
# git 체크아웃만 쓴다 — 네트워크·빌드·체커 실행 없음. 블록의 ERE 는 grep 에만 쓰이고 셸로 평가되지 않는다.
# 런타임이 dataSource.repository@ref(main)를 체크아웃한 상태를 가정한다.
set -euo pipefail
export LC_ALL=C
README='docs/data-model/README.md'
h() { sha256sum | cut -c1-16; }

B=$(git show "HEAD:$README" 2>/dev/null | awk '
  !f && ($0 == "```data-model-scope" || index($0, "```data-model-scope ") == 1) { f = 1; next }
  f && /^```/ { f = 0; next }
  f && NF { print }' || true)
if [ -z "$B" ]; then
  echo "scope=absent"
  echo "schema=absent;queries=absent;checker=absent"
  exit 0
fi

val() { printf '%s\n' "$B" | sed -n "s/^$1:[[:space:]]*//p"; }
ere_ok() {  # 비어 있지 않고 grep -E 가 받아들이는 ERE 인가(rc 2 = 문법 오류)
  local rc=0
  [ -n "$1" ] || return 1
  printf 'x\n' | grep -Eq -- "$1" 2>/dev/null || rc=$?
  [ "$rc" -le 1 ]
}
rev() { if [ -n "$1" ]; then git rev-parse --verify --quiet "HEAD:$1" || echo absent; else echo malformed; fi; }

MIG=$(val migrations | head -n1)
CHK=$(val checker | head -n1)
SCOPE=$(val scope | tr '\n' ' ')
EXCL=$(val exclude | paste -sd'|' -); EXCL=${EXCL:-'^$'}
SITE=$(val site | paste -sd'|' -)
SQL=$(val sql | paste -sd'|' -)

SCHEMA=$(rev "$MIG")
CHECKER=$(rev "$CHK")

if [ -z "${SCOPE// /}" ] || ! ere_ok "$SITE" || ! ere_ok "$SQL" || ! ere_ok "$EXCL"; then
  QUERIES=malformed; Q=''
else
  # (파일, 줄) — 줄 번호를 빼고 공백을 1칸으로 접는다. 같은 줄이 여러 번 나오면 그 수만큼 남긴다(sort, -u 아님).
  # shellcheck disable=SC2086
  Q=$({ git ls-files -- $SCOPE | grep -vE -- "$EXCL" | sort \
        | xargs -r grep -IEH -- "$SITE|$SQL" || true; } \
      | sed -E 's/[[:space:]]+/ /g; s/^([^:]*): /\1:/; s/ $//' | sort)
  QUERIES=$(printf '%s' "$Q" | h)
fi

case "$SCHEMA" in absent|malformed) NMIG=0 ;; *) NMIG=$(git ls-tree -r --name-only "HEAD:$MIG" | grep -c . || true) ;; esac
case "$QUERIES" in malformed) NSITE=0 ;; *) NSITE=$(printf '%s\n' "$Q" | grep -cE -- "$SITE" || true) ;; esac
case "$CHECKER" in absent|malformed) CS=$CHECKER ;; *) CS=present ;; esac
echo "migrations=$NMIG site_lines=$NSITE query_lines=$(printf '%s' "$Q" | grep -c . || true) checker=$CS"
printf 'schema=%s;queries=%s;checker=%s\n' "$SCHEMA" "$QUERIES" "$CHECKER"
```

주의:
- 마지막 줄만 버전이다. `migrations=… site_lines=…` 진단 줄은 값에 영향을 주지 않는다.
- README 블록이 없으면 세 성분이 모두 `absent`다. 등록 직후에는 to-be도 `absent`이므로 첫 감지가 곧
  문서·블록·체커를 만드는 task가 되고, 블록이 생기는 순간 세 성분이 함께 움직여 다음 판정이 트리거된다.
- 블록의 키가 비거나 ERE가 grep 문법 오류면 그 성분은 `malformed`다. 조용히 빈 집합이 되지 않게 하는
  장치이며, 판정에서 C2·C6 위반(블록 파싱 실패)으로 센다.
- `queries`는 쿼리 **줄**의 지문이라 다음은 보지 못한다: 함수 이름 변경(호출 지점 칸이 낡는다), 다른 파일의
  상수로 조립되는 테이블·컬럼 이름, `site`·`sql` ERE에 걸리지 않는 쿼리 빌더 DSL. 앞의 둘은 체커가 판정할
  때와 CI(C9)에서 잡히고, 마지막은 `site` ERE를 넓히는 대상 레포 PR로 고친다(C4가 그 ERE를 체커와 공유한다).
- 같은 파일의 무관한 줄이 `sql` ERE에 걸리면 노이즈 트리거가 생긴다. 예시 ERE는 2026-10-04 feature-doc(Rust)·pocket-aide(Go)
  실측에서 주석 줄 히트 0이었다(SQL 단어를 모두 잡는 ERE는 주석 4~6줄이 걸렸다). 잦으면 블록의 `sql` ERE를 좁힌다 — 대상 레포 PR로 끝난다.
- 등록 전에 대상 레포에서 두 스크립트를 실제로 돌려 값이 나오는지, 들여쓰기·줄 이동에 흔들리지 않는지,
  SQL 한 글자 변경에 흔들리는지 확인한다(블록이 아직 없으면 `absent` 출력만 확인).

## definition 본문 템플릿

`[선택]` 표시 블록은 해당 없으면 통째로 삭제. `<!-- 지침 -->`은 모두 제거.

```markdown
# {{SLUG}} 데이터 모델 정합성 (ERD · 쿼리 패턴 · 인덱스)

## 목표
`{{REPO}}`({{DB_ENGINE}})의 `docs/data-model/`이 실재를 정확히 그리는 지도로 유지된다: ERD는 마이그레이션을 전부 적용한 스키마와 같고, 쿼리 패턴 카탈로그는 코드의 모든 쿼리 지점을 형태로 빠짐없이 덮으며, 각 패턴의 인덱스 지원 주장은 빈 DB 쿼리 플랜이 확인한 것과 같다. 판정은 대상 레포의 체커가 하고, 문서는 실재를 따라간다.

## 무엇이 "맞는 상태"인가 (SSOT)
- **스키마의 SSOT**는 마이그레이션을 전부 적용한 빈 DB의 엔진 카탈로그다. ERD는 그 반영물이다.
- **쿼리 존재의 SSOT**는 코드다(쿼리 레이어: {{QUERY_LAYER}}). 카탈로그는 그 반영물이다.
- **인덱스 지원의 SSOT**는 빈 DB에서 엔진이 낸 쿼리 플랜이다. 카탈로그의 지원 칸은 그 반영물이다.
- **판정 규칙의 SSOT**는 `docs/data-model/README.md`(형태 정의 · 풀스캔 허용 기준 · 추출 제외 범위와 `data-model-scope` 블록 · 체커)와 reconciler `templates/data-model.tbm.md`의 고정부다. 풀스캔 허용 기준은 사람이 소유한다.
- 정합 상태 = **불변식 1 ∧ 불변식 2 ∧ 불변식 3**.

## 불변식 1 — ERD ↔ 실제 스키마 전단사
`erd.md`의 테이블·컬럼(타입·NULL)·PK·FK·인덱스 집합 == 마이그레이션을 전부 적용한 결과의 집합(동일성 키는 템플릿 「불변식 1」 표). mermaid 다이어그램의 엔티티 집합·관계 집합도 구조 표의 테이블·FK와 같다. 엔티티의 의미는 코드 문서 주석 링크로만 둔다.
- 충돌하면 **스키마가 이긴다**: ERD를 고친다. ERD에 맞추려고 마이그레이션을 쓰거나 기존 마이그레이션을 고치지 않는다.

## 불변식 2 — 쿼리 패턴 카탈로그 ↔ 코드 쿼리 지점 전단사
코드의 (호출 지점, 형태) 쌍마다 그 형태를 가진 카탈로그 행이 정확히 하나 있고 그 행이 그 지점을 적고 있다. 카탈로그의 모든 행은 실재하는 지점을 하나 이상 가진다.
- 귀속 키는 **형태** = (연산, 대상 테이블, 등치 조건 컬럼, 범위 조건, 정렬)이다. 코드 주석 앵커를 쓰지 않는다.
- 존재 여부에서는 **코드가 이긴다**: 미등재 쿼리는 카탈로그에 더하고, 죽은 지점·죽은 패턴은 지운다.
- 정적으로 형태를 뽑을 수 없는 지점은 「수동 형태」 표에 등재한다. 체커의 추출 불가 지점 집합 == 수동 형태 표의 지점 집합.

## 불변식 3 — 패턴 ↔ 인덱스 지원
각 패턴은 지원 인덱스(PK·UNIQUE 포함)를 지목하거나 `풀스캔 허용(F<n>): <근거>`를 적고, 그 칸은 체커가 빈 DB에서 돌린 쿼리 플랜의 판정과 같다. 어떤 패턴도 쓰지 않는 인덱스(PK 제외)는 「미사용 인덱스」 표와 양방향으로 같다.
- 판정은 **문서의 주장이 아니라 엔진**으로 한다.
- 미사용 인덱스는 **등재만** 하고 삭제하지 않는다.
- 지원 인덱스가 없으면: README의 기존 풀스캔 허용 기준 하나에 해당하면 사유를 적어 등재하고, 아니면 인덱스를 추가하는 **새 마이그레이션 PR**을 낸다(같은 PR에서 ERD 인덱스 표·카탈로그 지원 칸 갱신). 기준을 새로 만들거나 넓히는 것은 사람의 결정이다.

## 판정 절차
1. 대상 레포 main 체크아웃에서 README 「체커」 절의 명령(`{{CHECKER_RUN}}`)을 돌리고 `--json` 리포트를 읽는다.
2. 종료 코드 0이면 세 불변식 정합, 1이면 리포트의 위반 항목이 gap이다.
3. 종료 코드 2(판정 불가)거나 체커가 없으면 그 자체가 gap이다(체커 계약 C1~C9 미충족). 판정 환경에 엔진이 없어서만 못 돌린 경우에 한해, 같은 main 커밋의 CI 체커 결과(C9)를 판정으로 쓸 수 있다. 엔진 판정 없이 불변식 3을 정합으로 닫지 않는다.
4. 체커 리포트와 별개로, 체커가 README 블록 밖의 범위를 하드코딩하고 있지 않은지(C2), `site` ERE에 걸리는 줄을 빠짐없이 다루는지(C4)를 읽어 확인한다 — 체커 자신이 낡는 것은 체커가 보고하지 않는다.

## 판정 규칙
불변식 1~3 또는 체커 계약 C1~C9 중 **하나라도** 위반이면 `action_required`. 전부 충족이면 `no_action_needed`로 닫되, `stateSummary`에 테이블 수 · 패턴 수 · 수동 형태 수 · 풀스캔 허용 수 · 미사용 인덱스 수 · 엔진과 버전 · 체커 종료 코드를 남긴다. 숫자는 스냅샷이며 판정 기준이 아니다.

## 판정 슬라이스
초기 격차가 크면 task 하나가 불변식 순서대로 가져간다: (1) README·블록·체커 골격과 ERD(불변식 1) → (2) 카탈로그와 수동 형태(불변식 2) → (3) 지원 칸·미사용 인덱스와 필요한 인덱스 마이그레이션(불변식 3). 불변식 3은 불변식 2의 카탈로그를 전제로 하므로 순서를 바꾸지 않는다. PR이 머지되면 버전이 바뀌어 다음 감지가 남은 슬라이스를 이어받는다.

## 충돌 시 기본 방향
- ERD ↔ 스키마 → **스키마가 이긴다.** ERD를 고친다.
- 카탈로그 ↔ 코드의 존재 → **코드가 이긴다.** 카탈로그를 더하거나 지운다. 형태가 다르면 카탈로그의 형태를 체커가 뽑은 형태로 고친다.
- 지원 칸 ↔ 엔진 → **엔진이 이긴다.** 지원 칸을 플랜에 맞춘다. 지원이 없으면 위 두 해소 경로 중 하나.
- 체커가 추출을 못 하는 새 관용구 → 먼저 체커(C4)를 고칠 수 있는지 보고, 정말 정적으로 불가능한 지점만 수동 형태로 등재한다. 수동 형태 표를 체커 결함의 하치장으로 쓰지 않는다.
- 범위 블록을 좁혀 위반을 없애지 않는다 — 제외는 쿼리가 아닌 것만이다.
- 미사용 인덱스를 지우지 않는다.

## 추적 방식 (요약)
- **to-be** = `docs/data-model` 트리 해시. 디렉터리가 없으면 `absent`.
- **as-is** = `schema=…;queries=…;checker=…`. schema는 마이그레이션 디렉터리 트리 해시, queries는 scope − exclude에서 `site`·`sql` ERE에 걸리는 줄의 (파일, 정규화한 줄) sha256, checker는 체커 경로의 해시. 경로·범위는 README `data-model-scope` 블록에서 읽고, 블록이 없으면 세 성분 모두 `absent`, 깨지면 그 성분이 `malformed`.
- 두 스크립트 모두 git 체크아웃만 쓴다. 판정(체커 실행·쿼리 플랜)은 감지 단계에서 한다.

## 초기 상태 메모 (등록 시점 {{NOW_ISO}})
{{INITIAL_STATE}} 이 문단의 숫자는 **스냅샷일 뿐 판정 기준이 아니다**.
첫 task가 만들 `data-model-scope` 블록 초안:
{{SCOPE_DRAFT}}
<!-- 지침: docs/data-model/ 유무, 마이그레이션 디렉터리와 개수, 테이블 수, 쿼리 레이어와 동적 조립 지점의 예, 체커·CI 유무, 등록 전 as-is 진단 줄을 남긴다. 문서가 없으면 "첫 task는 판정 슬라이스 (1)부터 시작한다 — 큰 초기 격차는 예상된 것"을 포함 -->

## 범위 밖 / 비고
- **운영 성능**은 보지 않는다. 빈 DB 플랜은 인덱스가 그 형태를 **지원할 수 있는가**를 묻는다. 운영 통계에서 플래너가 실제로 고르는 플랜, 쿼리 지연, 인덱스 크기·쓰기 비용은 범위 밖이다.
- **정렬 지원**은 판정하지 않는다. 지원은 접근 조건 기준이고, 플랜에 별도 정렬 단계(SQLite `USE TEMP B-TREE FOR ORDER BY`, PostgreSQL `Sort`)가 있어도 drift가 아니다. 체커는 리포트에 표시만 한다. 정렬 지원을 판정에 넣으려면 템플릿 개정이다.
- ERD에 없는 스키마 속성 — 기본값, `CHECK`, FK의 `ON DELETE`/`ON UPDATE` 동작, 트리거, 뷰 — 는 불변식 1의 원소가 아니다. 넣으려면 템플릿 개정이다.
- 스키마 설계의 좋고 나쁨(정규화, 네이밍)은 보지 않는다. 이 모델은 지도가 땅과 같은지만 본다.
- 인덱스 추가 마이그레이션의 **운영 적용 방식**(대용량 테이블의 잠금, PostgreSQL `CREATE INDEX CONCURRENTLY`와 트랜잭션 밖 실행)은 판정 대상이 아니라 그 PR의 계획에서 다룬다.
- <!-- [선택] --> 제품 문서 ↔ 구현 정합(`tbm_{{SLUG}}-docs-impl`)의 to-be는 `docs/` 트리라 `docs/data-model/` 변경에도 트리거되지만, 데이터 모델 문서의 판정은 이 모델이 전담한다. <!-- -->
- <!-- [선택] --> ERD가 의미를 위임한 코드 문서 주석은 주석 필요성 모델(`tbm_{{SLUG}}-comment-necessity`)에서 필요 사유를 갖는다 — 지우면 ERD의 의미 링크가 빈 곳을 가리킨다. <!-- -->
- <!-- [선택] --> 이 모델이 내는 인덱스 추가 마이그레이션 PR은 PR 수동 승인 모델(`tbm_{{SLUG}}-pr-manual-approval`)의 마이그레이션 케이스에 걸릴 수 있다. 그 경우 리뷰가 `review.manualApproval`을 남기고 사람 승인 뒤에 실행된다 — 정상 경로다. <!-- -->
- <!-- 지침: 노이즈 비고 — queries 지문에 걸리는 무관한 줄, README 서술 수정이 to-be를 바꾸는 것 등 — 을 대상에 맞게 1~2줄 작성 -->
```
