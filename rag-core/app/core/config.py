"""전역 설정. 환경변수 기반으로 로드한다."""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    es_url: str = os.getenv("ES_URL", "http://localhost:9200")
    es_index: str = os.getenv("ES_INDEX", "pension_docs")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")
    rrf_k: int = int(os.getenv("RRF_K", "60"))
    bm25_top_k: int = int(os.getenv("BM25_TOP_K", "50"))
    vector_top_k: int = int(os.getenv("VECTOR_TOP_K", "30"))
    final_top_k: int = int(os.getenv("FINAL_TOP_K", "10"))


settings = Settings()
