# BioTeam-AI 오류/할루시네이션 점검 보고서 (2026-02-27)

## 범위
- 프론트엔드 정적 품질: lint/build
- 백엔드 기능 품질: 코어 테스트 스위트
- 할루시네이션 리스크: LLM 응답 가드, 문서-코드 일치성, 구현-스펙 일치성

## 실행 검증 결과
- `frontend`
  - `npm run lint` 통과
  - `npm run build` 통과
- `backend (core)`
  - `uv run pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_integrations/test_semantic_scholar.py -q`
  - 결과: `1538 passed, 5 skipped`
- `backend (full)`
  - `uv run pytest tests/ -q`
  - 결과: benchmark 수집 단계 실패 (`pysprite`, `pandas` 미설치)

## 핵심 이슈 (심각도 순)

### 1) High — Direct Query hallucination 방지 미흡 (사후 검증 부재)
- 현상: 프롬프트에 “근거 없는 인용 금지” 지시는 있으나, 생성된 답변의 DOI/인용을 `memory_context`와 대조하는 검증 로직이 없음.
- 영향: 모델이 지시를 어기면 잘못된 인용이 그대로 반환될 수 있음.
- 근거 파일:
  - `backend/app/api/v1/direct_query.py:364`
  - `backend/app/api/v1/direct_query.py:388`
  - `backend/app/api/v1/direct_query.py:404`

### 2) Medium — `seed_papers` 필드가 선언만 되고 파이프라인에서 실사용되지 않음
- 현상: API 스키마/함수 인자로는 존재하지만 검색·랭킹·프롬프트 주입 등 실질 로직 연결이 없음.
- 영향: 사용자 관점에서 기능이 동작한다고 오해할 수 있음(기능적 hallucination).
- 근거 파일:
  - `backend/app/api/v1/direct_query.py:56`
  - `backend/app/api/v1/direct_query.py:251`
  - `backend/app/api/v1/direct_query.py:455`

### 3) Medium — SSE short-lived token(120s) + 자동 재연결 경로의 불일치 가능성
- 현상: 프론트는 최초 연결 시 토큰 1회 발급 후 사용. 네트워크 단절 후 자동 재연결 시 새 토큰 발급 없이 기존 URL 기반 재시도에 의존.
- 영향: 토큰 만료 후 재연결 실패 가능성.
- 근거 파일:
  - `backend/app/security/stream_token.py:22`
  - `frontend/src/hooks/use-sse.ts:34`
  - `frontend/src/hooks/use-sse.ts:50`

### 4) Medium — 전체 테스트 명령이 optional benchmark 의존성 미설치 시 실패
- 현상: benchmark 모듈 import 시 `pysprite`, `pandas`가 없으면 collection error.
- 영향: CI/로컬에서 “전체 테스트” 기대와 실제가 달라짐.
- 근거 파일:
  - `backend/tests/benchmarks/test_benchmark_grim.py:15`
  - `backend/tests/benchmarks/test_benchmark_statcheck.py:17`

### 5) Low — 문서와 실제 코드 상태 일부 불일치
- 현상: README에 워크플로 범위(W1-W6), 테스트 수(725) 등 구 수치가 남아 있음.
- 영향: 사용자 신뢰도/온보딩 정확도 저하.
- 근거 파일:
  - `README.md:40`
  - `README.md:132`
  - `README.md:188`

## 권장 조치
1. Direct Query 응답 후검증 추가
   - 답변에서 DOI/PMID 패턴 추출 → `sources`/`memory_context`에 없는 항목 제거 또는 경고 처리.
2. `seed_papers` 실연결 또는 필드 제거
   - 검색 우선순위 가중치, 강제 포함 컨텍스트, 또는 미구현 표시 중 하나로 정리.
3. SSE 재연결 시 토큰 재발급 경로 보강
   - `onerror`에서 연결 종료 후 재발급+재연결 루프 구현(백오프 포함).
4. 테스트 프로파일 분리
   - `core`/`benchmarks` marker 분리, benchmark 의존성 extras 정의.
5. README 수치·범위 최신화
   - 워크플로 범위, 테스트 수, 엔드포인트/보안 흐름을 코드와 동기화.

## 결론
- 현재 코어 기능은 실행 품질이 높고(코어 테스트 통과), 주요 리스크는 “할루시네이션 통제의 사후 검증 부족”과 “문서/옵션 의존성 정합성”에 집중됨.
- 즉시 대응 우선순위는 `1 → 3 → 2`를 권장.

