# PensionRAG

연금·절세(IRP · ISA · 연금저축 · 퇴직연금) 특화 문서 검색 RAG 시스템

"IRP 세액공제 한도가 얼마예요?" 같은 질문에 법령·감독규정·안내자료 원문을 근거로 인용해 답합니다.

## 왜 만들었나

11년간 은행·카드·증권 도메인(신한카드 AML/여전법 규제 대응, KB 마이데이터, 한국예탁결제원 전자증권)에서
Java/Spring Boot 기반 금융 시스템을 개발해왔습니다. 규제·상품 정보가 법령·시행령·감독규정·약관에 흩어져 있어
매번 찾기 번거로웠던 경험을, 현재 진행 중인 퇴직연금 프로젝트를 계기로 RAG 시스템으로 풀어봤습니다.

## 아키텍처

```
Client
  │
  ▼
Gateway (Kotlin + Spring Boot)   ← 인증, 라우팅, 요청 검증
  │
  ▼
RAG Core (Python + FastAPI + LangChain)
  │
  ├── Ingestion: 업로드 → 텍스트 추출 → 청킹 → 임베딩 → 색인
  └── Retrieval: 질문 → BM25(nori)+벡터 하이브리드 → RRF 융합
        → CrossEncoder 재순위 → LLM 답변 생성(근거 인용)
  │
  ▼
Elasticsearch 8 (텍스트 + 벡터 동시 저장)
```

상세 스펙은 [`docs/research/연금절세_RAG_스펙_v2.md`](./docs/research/연금절세_RAG_스펙_v2.md) 참고.

## 기술 스택

| 레이어 | 기술 |
|---|---|
| 게이트웨이 | Kotlin, Spring Boot |
| RAG 코어 | Python, FastAPI, LangChain |
| 검색 | Elasticsearch 8 (nori 분석기) |
| 임베딩 | bge-m3 (한국어 벤치마크 후 확정) |
| 재순위 | CrossEncoder |
| LLM | Claude / OpenAI API |
| 배포 | Docker Compose → AWS EC2 (t3.medium) |

## 프로젝트 구조

```
gateway/       Kotlin + Spring Boot 게이트웨이
rag-core/      Python + FastAPI RAG 코어 서비스
  app/
    api/         API 라우트
    core/        설정, 공통 로직
    ingestion/   문서 등록 파이프라인
    retrieval/   검색/답변 파이프라인
    domain/      연금·세제 도메인 엔티티/용어 사전
infra/docker/  Docker Compose 정의
docs/
  research/    스펙, 개념 정리 문서
  decisions/   설계 의사결정 기록 (ADR)
scripts/       운영/배포 스크립트
```

## 개발 상태

프로젝트 초기 단계. 진행 상황은 커밋 로그와 `docs/decisions/`에 기록합니다.

## 라이선스

TBD
