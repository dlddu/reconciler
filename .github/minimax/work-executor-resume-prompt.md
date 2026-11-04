직전 턴이 모델 제공자 쪽 오류(재시도 가능)로 중간에 끊겼다. 같은 세션이니 앞의 지시와 지금까지의 대화는 그대로 유효하다 — `reconciler-work-executor` 스킬 절차대로 이번 실행·검증을 끝까지 이어서 수행하라.

- 러너가 점유한 task: task_id=`{{TASK_ID}}`, model_id=`{{MODEL_ID}}`, 점유 커밋=`{{CLAIM_COMMIT}}`
- 끊긴 지점의 도구 호출은 끝났는지 알 수 없다. 이어서 하기 전에 **현재 상태를 직접 다시 확인**하라: reconciler 체크아웃(`./reconciler`)의 `git status`·`git log`와 원격 기본 브랜치, 그 task의 status·마지막 attempt의 `execution`·`verification`, 대상 레포의 PR 상태(열림·머지됨·head)와 기본 브랜치.
- 이미 끝난 동작(머지·push·커밋)은 다시 하지 않는다. 확인된 상태에서 남은 단계만 한다.

끝나면 최종 status와 핵심 근거(실행 결과·검증 check)를 짧게 보고하라.
