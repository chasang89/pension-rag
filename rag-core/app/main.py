"""PensionRAG - RAG Core Service

FastAPI 엔트리포인트. 문서 등록(ingestion)과 검색/답변(retrieval) API를 제공한다.
"""

from fastapi import FastAPI

app = FastAPI(
    title="PensionRAG Core",
    description="연금·절세 도메인 특화 RAG 코어 서비스",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


# TODO: app.api 라우터 등록
# from app.api import ingestion_router, retrieval_router
# app.include_router(ingestion_router.router, prefix="/ingestion")
# app.include_router(retrieval_router.router, prefix="/retrieval")
