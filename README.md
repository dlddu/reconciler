# reconciler

as-is 상태와 to-be(목표) 상태를 비교해, 버전이 바뀔 때마다 정합성 작업을 만들어 실행·검증하는 시스템의 스키마와 운영 데이터.

## 엔티티

- **ToBeModel** — 목표 상태의 마크다운 정의와 as-is/to-be 데이터 소스, 소스별 버전 계산 스크립트.
  각 `versionScript`는 stdout 마지막 줄을 버전 문자열로 사용한다
  (github = 커밋 SHA + 하위 디렉터리 tree hash, k8s = deployment revision + 이미지, monitor = 최신 alert event id).
- **ReconciliationTask** — as-is/to-be 버전이 바뀔 때마다 생성되는 작업.
  요약 → 판단 → 계획 → (사용자 검토) → 실행 → 검증 순으로 필드가 채워진다.

## 구조

```
schemas/
  to-be-model.schema.json           # ToBeModel JSON 스키마 (draft 2020-12)
  reconciliation-task.schema.json   # ReconciliationTask JSON 스키마 (draft 2020-12)
data/                               # 운영 데이터 (스킬이 런타임에 생성·기록, 초기엔 비어 있음)
  to-be-models.json                 # ToBeModel (배열)
  reconciliation-tasks/             # task: to-be 모델(toBeModelId)별로 파일 분리
    <toBeModelId>.json
index.html                          # data/ 브라우징용 정적 웹페이지 (GitHub Pages)
.nojekyll                           # Pages가 data/*.json을 그대로 서빙하도록 Jekyll 우회
```

## 데이터 브라우저 (GitHub Pages)

`index.html`은 의존성 없는 단일 파일 정적 페이지로, `data/`의 ToBeModel과
모델별 ReconciliationTask를 읽어 목록·상세로 보여준다. `to-be-models.json`을
불러온 뒤 각 모델 id로 `reconciliation-tasks/<id>.json`을 상대경로로 fetch하므로
외부 API·CDN이 필요 없다. 마크다운 정의 렌더링, 상태 배지, 검색, 라이트/다크
테마, 원본 JSON 보기를 지원한다.

- **GitHub Pages 활성화**: 저장소 Settings → Pages → *Deploy from a branch* →
  브랜치의 `/(root)` 선택. 페이지는 `data/`를 상대경로로 읽으므로 반드시
  루트에서 서빙해야 한다(`/docs` 아님). 배포 후 `https://<owner>.github.io/<repo>/`.
- **로컬 확인**: `python3 -m http.server` 실행 후 `http://localhost:8000/` 접속.
  `file://`로 직접 열면 브라우저 보안정책상 `data/`를 못 읽으니 서버로 열 것.
