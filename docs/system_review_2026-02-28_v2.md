# System Review v2 (2026-02-28)

## 범위
- 관점: hallucination, 하드코딩, 안정성, 팩트 체크
- 대상: `AI_Scientist_team` 백엔드 핵심 경로(Direct Query, Citation Validator, RCMXT, LLM Layer, Auth/RateLimit)

## 진행 현황 (2026-02-28)
- 완료: 1) PMID 환각 검증 강화
- 완료: 2) Citation author-only 검증 제거
- 완료: 3) SSE 경로 citation post-validation 적용
- 완료: 4) `seed_papers` DOI/PMID 우선순위 + SSE 파라미터 지원
- 완료: 5) Circuit Breaker HALF_OPEN 단일 probe 제한
- 보류: 6) 비용/제한값 하드코딩의 설정화(호환성 범위 검토 필요)

## 핵심 발견사항 (심각도 순)

### High
1. PMID 환각 검증 우회 가능
   - `sources`가 비어 있을 때만 PMID를 `ungrounded`로 처리
   - `sources`가 존재하면 가짜 PMID가 있어도 경고 누락 가능
   - 참조:
     - `backend/app/api/v1/direct_query.py:164`
     - `backend/app/api/v1/direct_query.py:190`

2. Citation 검증에서 `first_author`만으로도 verified 처리됨
   - DOI/PMID/제목이 틀려도 저자 성(last name) 일치만으로 통과 가능
   - 거짓 인용이 clean으로 오검증될 리스크
   - 참조:
     - `backend/app/engines/citation_validator.py:135`
     - `backend/app/engines/citation_validator.py:146`
     - `backend/app/workflows/runners/w1_literature.py:751`

### Medium
3. SSE direct-query 경로에는 citation post-validation 미적용
   - POST 경로는 `_validate_answer_citations()` 수행
   - SSE 경로는 토큰 스트리밍 후 `done` 반환, `ungrounded_citations` 없음
   - 참조:
     - `backend/app/api/v1/direct_query.py:474`
     - `backend/app/api/v1/direct_query.py:718`

4. `seed_papers` 문서/모델은 DOI/PMID인데 실제 우선순위는 DOI만 반영
   - `seed_papers` 입력 설명은 DOI 중심 + 코드 주석은 DOI/PMID
   - 구현은 `metadata.doi` 매칭만 수행
   - SSE 엔드포인트는 `seed_papers` 파라미터 자체가 없음
   - 참조:
     - `backend/app/api/v1/direct_query.py:58`
     - `backend/app/api/v1/direct_query.py:212`
     - `backend/app/api/v1/direct_query.py:568`

5. Circuit Breaker HALF_OPEN probe 제한 불일치
   - 주석은 "one probe request"인데 실제는 HALF_OPEN에서 연속 허용
   - 장애 회복 구간에서 요청 급증 시 안정성 저하 가능
   - 참조:
     - `backend/app/llm/layer.py:67`
     - `backend/app/llm/layer.py:104`

### Low
6. 비용/제한값 하드코딩으로 정책 변경 시 드리프트 위험
   - Direct Query timeout/cost cap 상수 고정
   - 모델 토큰 단가도 코드 내부 고정
   - 참조:
     - `backend/app/api/v1/direct_query.py:37`
     - `backend/app/api/v1/direct_query.py:38`
     - `backend/app/llm/layer.py:640`

## 재현 확인 요약
- `_validate_answer_citations()`에서 fake PMID 누락 재현 확인
- `CitationValidator.validate(inline_refs=...)`에서 fake DOI + author 매칭 통과 재현 확인
- `_prioritize_context_by_seed_papers()`에서 PMID seed 미반영 재현 확인
- `CircuitBreaker` HALF_OPEN 상태에서 연속 `allow_request=True` 재현 확인

## 테스트 실행 요약
- `./.venv/bin/pytest backend/tests/test_api/test_direct_query.py backend/tests/test_engines/test_citation_validator.py backend/tests/test_engines/test_rcmxt_scorer.py backend/tests/test_engines/test_rcmxt_scorer_llm.py -q`
  - 결과: `104 passed`
- `./.venv/bin/pytest backend/tests/test_workflows/test_w1_literature.py backend/tests/test_security/test_auth_middleware.py backend/tests/test_security/test_rate_limit.py backend/tests/test_security/test_circuit_breaker.py backend/tests/test_agents/test_knowledge_manager.py backend/tests/test_infra/test_health_and_main.py -q`
  - 결과: `52 passed`
