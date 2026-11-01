`reconciler-work-planner` 스킬(`{{SKILL_DIR}}/SKILL.md`, MiniMax 플러그인 `reconciler-data-plane`)을 읽고 그 절차대로 이번 계획을 끝까지 수행하라. 스킬의 `$SKILL_DIR`은 `{{SKILL_DIR}}`이다.

- reconciler 체크아웃 경로: `{{REPO_DIR}}` (reconciler 기록은 이 경로에서만 한다)
- 러너가 점유한 task: task_id=`{{TASK_ID}}`, model_id=`{{MODEL_ID}}`, from_status=`{{FROM_STATUS}}`, 점유 커밋=`{{CLAIM_COMMIT}}`
- 대상 레포 작업 디렉터리: `{{WORK_DIR}}`
- MCP 서버 `k3s`가 연결돼 있다.

끝나면 최종 status, 계획 요약, 위험도, PR 링크를 짧게 보고하라.
