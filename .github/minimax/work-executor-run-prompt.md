`reconciler-work-executor` 스킬(`{{SKILL_DIR}}/SKILL.md`)을 읽고 그 절차대로 이번 실행·검증을 끝까지 수행하라. 스킬의 `$SKILL_DIR`은 `{{SKILL_DIR}}`이다.

- reconciler 체크아웃 경로: `{{REPO_DIR}}` (reconciler 기록은 이 경로에서만 쓴다)
- 러너가 점유한 task: task_id=`{{TASK_ID}}`, model_id=`{{MODEL_ID}}`, 점유 커밋=`{{CLAIM_COMMIT}}`
- {{ENV_NOTE}}

끝나면 최종 status와 핵심 근거(실행 결과·검증 check)를 짧게 보고하라.
