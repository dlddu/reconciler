직전 턴이 모델 제공자 쪽 오류(재시도 가능)로 중간에 끊겼다. 같은 세션이니 앞의 지시와 지금까지의 대화는 그대로 유효하다 — `reconciler-work-planner` 스킬 절차대로 이번 계획을 끝까지 이어서 수행하라.

- 러너가 점유한 task: task_id=`{{TASK_ID}}`, model_id=`{{MODEL_ID}}`, 점유 커밋=`{{CLAIM_COMMIT}}`
- 끊긴 지점의 도구 호출은 끝났는지 알 수 없다. 이어서 하기 전에 **현재 상태를 직접 다시 확인**하라: reconciler 체크아웃(`./reconciler`)의 `git status`·`git log`와 원격 기본 브랜치, 그 task의 status·attempts, 대상 레포 작업 디렉터리(`./targets`)의 브랜치·커밋과 원격 브랜치·열린 PR.
- 이미 끝난 단계(커밋·push·PR)는 다시 하지 않는다. 같은 PR을 새로 열지 않는다. 확인된 상태에서 남은 단계만 한다.

끝나면 최종 status, 계획 요약, 위험도, PR 링크를 짧게 보고하라.
