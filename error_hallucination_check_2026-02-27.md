# AI_Scientist_team 오류/환각(Hallucination) 점검 리포트

점검 일시: 2026-02-27  
점검 범위: `AI_Scientist_team` (코드 수정 없이 실행/정적 리뷰)

## 주요 발견 사항

### 1) High: 런타임 NameError 가능 (`logger` 미정의)
- 위치: `backend/app/api/v1/digest.py:307`
- 내용: 이메일 전송 실패 시 `logger.error(...)` 호출하지만 모듈 내 `logger` 정의가 없음.
- 영향: 원래 예외 대신 `NameError`로 500 응답 가능.

### 2) Medium: README 테스트 안내와 실제 실행 범위 불일치
- 위치: `README.md:188-190`, `backend/tests/test_integrations/test_pubmed.py`
- 내용: README는 live-API integration 제외라고 쓰지만 예시 명령은 PubMed live 테스트를 제외하지 않음.
- 영향: 오프라인/제한 환경에서 문서 지시대로 실행 시 실패 가능.

### 3) Medium: 통합 테스트의 오프라인 내성 부족
- 위치: `backend/tests/test_integrations/test_semantic_scholar.py:25`, `backend/app/integrations/semantic_scholar.py:127`
- 내용: `search()`가 오류 시 빈 리스트 반환인데 테스트는 예외 기반 skip만 처리.
- 영향: 네트워크 불가 환경에서 `assert len(papers) > 0` 실패.

### 4) Medium: 벤치마크 테스트 하드코딩 숫자 불일치
- 위치: `backend/tests/benchmarks/test_system_coordination.py:40`, `backend/app/agents/registry.py`
- 내용: 기대 에이전트 수 `21` 하드코딩, 실제 등록 수 `23`.
- 영향: 벤치마크 테스트 실패.

### 5) Low: README 내 에이전트 구성/수치 문서 불일치
- 위치: `README.md:49`, `README.md:222`, `backend/app/agents/registry.py`
- 내용: 상단 표(7개) / 하단 구조(22개) / 실제 코드(23개) 불일치.
- 영향: 문서 신뢰도 저하, 운영 혼선 가능.

## 실행 결과 요약

- 백엔드(벤치마크 제외): `1539 passed, 5 skipped, 5 failed`
  - 실패 5건: `test_integrations`의 live API 의존 테스트(PubMed/Semantic Scholar)
- 벤치마크: `271 passed, 6 skipped, 1 failed`
  - 실패 1건: 에이전트 수 하드코딩 불일치
- 프론트엔드: `npm run lint` 통과, `npm run build` 통과
- Ruff: 33개 이슈(실제 코드 오류 포함)로 린트 게이트 실패 상태

## 즉시 수정 권장 순서

1. `digest.py`의 `logger` 미정의 수정 (우선순위 최고)
2. 통합 테스트의 live/offline 분리 및 skip 조건 정리
3. README 테스트 명령/에이전트 수치 문서 정합성 수정
4. 벤치마크의 에이전트 수 하드코딩 제거 또는 동적 검증으로 변경

