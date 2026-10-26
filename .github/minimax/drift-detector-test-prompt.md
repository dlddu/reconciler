`reconciler-drift-detector` 스킬(`{{SKILL_DIR}}/SKILL.md`)을 읽고 그 절차대로 이번 감지 판정을 끝까지 수행하라.

- reconciler 체크아웃 경로: `{{REPO_DIR}}` (이 경로에서만 작업한다)
- 러너가 점유한 task: task_id=`{{TASK_ID}}`, model_id=`{{MODEL_ID}}`, claim_reason=`{{CLAIM_REASON}}`, 점유 커밋=`{{CLAIM_COMMIT}}`
- 드라이런: `RECONCILER_DRY_RUN=1` — 커밋까지만 하고 push는 하지 않는다.
- MCP 서버 `k3s`가 연결돼 있다.

끝나면 최종 판정(status)과 근거를 짧게 보고하라.
