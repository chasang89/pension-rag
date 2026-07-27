# ADR 0001: 프로젝트 시작 및 주제/스택 확정

- 날짜: 2026-07-28
- 상태: 확정

## 배경

정규직 이직용 포트폴리오 1호 프로젝트. 금융권 11년 경력(은행·카드·증권)을 살릴 수 있는 도메인으로
연금·절세(IRP/ISA/연금저축/퇴직연금) 문서 검색 RAG를 선택.

## 결정

- **주제**: 연금·절세 특화 RAG (PensionRAG)
- **스택**: Kotlin+Spring Boot 게이트웨이 / Python+FastAPI+LangChain RAG 코어 / Elasticsearch 8 하이브리드 검색
- **임베딩**: BGE-small(영어 중심) 대신 bge-m3(다국어) 채택 — 한국어 문서 검색 품질 확보 목적.
  실제 채택 전 한국어 임베딩 벤치마크로 재검증 예정
- **MQ**: Kafka 등 메시지 큐는 도입하지 않음 — 개인 프로젝트 규모(t3.medium)에 리소스 부담 대비 이득이
  적다고 판단
- **참고 레퍼런스**: elasticsearch-labs(검색 코어), kotaemon(경량 구조), langchain-kr(한국어 구현 패턴),
  AutoRAG 벤치마크(토크나이저/임베딩 선정), RAGFlow(대형 아키텍처 비교), lexdiff(청킹 반론 방어 논리)

## 근거

상세 스펙: [`../research/연금절세_RAG_스펙_v2.md`](../research/연금절세_RAG_스펙_v2.md)
