# System Review (2026-02-28)

## 범위
- 관점: hallucination, 하드코딩, 안정성, 팩트 체크
- 대상: backend 핵심 실행 경로(API/LLM/워크플로우/무결성 엔진), frontend 스트리밍 훅

## 핵심 발견사항 (심각도 순)

### Critical
1. 기본 실행 경로에서 `retraction` 팩트체크가 사실상 비활성화
   - `DataIntegrityAuditor` 기본 생성 시 retraction client 미주입
   - checker는 client 존재 시에만 동작
   - 영향: W1/W8/수동 audit에서 retracted paper 누락 위험
   - 참조:
     - `backend/app/agents/registry.py:168`
     - `backend/app/agents/data_integrity_auditor.py:92`
     - `backend/app/engines/integrity/retraction_checker.py:49`

2. W7 수집 단계 스키마 불일치로 실제 본문 미검사
   - `KnowledgeManager` 출력은 `results` 중심인데, W7은 `texts`를 읽음
   - 결과적으로 query fallback 비중이 커져 탐지 정확도 저하
   - 참조:
     - `backend/app/workflows/runners/w7_integrity.py:249`
     - `backend/app/agents/knowledge_manager.py:44`
     - `backend/app/agents/knowledge_manager.py:113`

### High
3. 인용 환각 후검증이 `POST /direct-query`에만 있고 `GET /direct-query/stream`에는 없음
   - 프런트 기본 사용 경로가 stream이어서 방어 공백 발생
   - 참조:
     - `backend/app/api/v1/direct_query.py:476`
     - `backend/app/api/v1/direct_query.py:749`
     - `frontend/src/hooks/use-direct-query-stream.ts:45`

4. PMID 환각 검출 약함
   - source 추출 시 PMID가 구조적으로 보존되지 않음
   - 현재 로직은 source가 비어 있을 때만 PMID 경고
   - 참조:
     - `backend/app/api/v1/direct_query.py:149`
     - `backend/app/api/v1/direct_query.py:190`

5. W8 제목 기반 citation 복구 로직 비동기/동기 불일치
   - 동기 `PubMedClient.search`를 `await`하는 코드 경로 존재
   - 예외를 삼켜 fallback 분기가 무의미해질 수 있음
   - 참조:
     - `backend/app/workflows/runners/w8_paper_review.py:946`
     - `backend/app/integrations/pubmed.py:61`
     - `backend/app/workflows/runners/w8_paper_review.py:957`

### Medium
6. W8 novelty 체크의 도메인 하드코딩 편향
   - 우주생물학 랜드마크/연도 하드코딩
   - 일반 생의학 리뷰에서 오판 가능성
   - 참조:
     - `backend/app/workflows/runners/w8_paper_review.py:1054`
     - `backend/app/workflows/runners/w8_paper_review.py:1109`

7. 인증 기본값이 무인증(dev mode)
   - `BIOTEAM_API_KEY` 누락 시 전체 API 인증 우회
   - 참조:
     - `backend/app/config.py:18`
     - `backend/app/middleware/auth.py:48`

8. 고비용 엔드포인트 rate limit 우회
   - `/direct-query/stream`이 expensive endpoint 목록에 없음
   - 참조:
     - `backend/app/middleware/rate_limit.py:24`
     - `backend/app/api/v1/direct_query.py:568`

9. Crossref expression-of-concern 파싱 불완전 가능성
   - relation 해석 로직 제한적, 미구현 주석 잔존
   - 참조:
     - `backend/app/integrations/crossref.py:116`
     - `backend/app/integrations/crossref.py:123`

## 검증 결과
- 통과:
  - `pytest -q backend/tests/test_api/test_direct_query.py`
  - 결과: `23 passed`
- 환경 의존성으로 수집 실패:
  - `imagehash`, `python-multipart` 미설치 상태에서 일부 테스트 수집 중단

## 권장 우선순위
1. Retraction client 기본 주입 + 실패 시 degraded 상태를 명시적으로 기록
2. W7 COLLECT 스키마 수정(`results` 기반 텍스트 합성)
3. stream 경로에도 인용 후검증(`ungrounded_citations`) 동일 적용
4. PMID 검증용 source 인덱스 확장
5. W8 title lookup 비동기/동기 경로 정합성 수정

## 실행 상태 (2026-02-28)
- 완료(1): Retraction client 기본 주입 + degradation note 기록 반영
- 완료(2): W7 COLLECT 단계 `results` 기반 텍스트/DOI 수집으로 정합성 반영
- 완료(3): stream 경로 citation post-validation + `ungrounded_citations` payload 반영
- 완료(4): PMID source 인덱스 및 검증 로직 강화 반영
- 완료(5): W8 title lookup 비동기/동기 정합성(`asyncio.to_thread`) 반영

### 추가 검증
- `pytest -q backend/tests/test_api/test_direct_query.py` → `25 passed`
- `pytest -q backend/tests/test_workflows/test_w8_paper_review.py::TestW8Steps::test_step_count` → `1 passed`
- `pytest -q backend/tests/test_workflows/test_w8_paper_review.py::TestW8PaperReviewRunner::test_runner_init` → `1 passed`
- `pytest -q backend/tests/test_workflows/test_w7_integrity.py::test_retraction_check_no_dois backend/tests/test_workflows/test_w7_integrity.py::test_state_reset_between_runs` → `2 passed`
