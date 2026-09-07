"""전역 설정. 환경변수 기반으로 로드한다."""

import os
from dataclasses import dataclass
from pathlib import Path

# app/core/config.py -> app/ -> rag-core/
_RAG_CORE_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    es_url: str = os.getenv("ES_URL", "http://localhost:9200")
    es_index: str = os.getenv("ES_INDEX", "pension_docs")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    # bge-m3의 dense 벡터는 1024차원이다. 모델을 바꾸면 반드시 같이 바꿔야 하며,
    # 인덱스 매핑에 그대로 쓰이므로 기존 인덱스는 재생성이 필요하다.
    embedding_dims: int = int(os.getenv("EMBEDDING_DIMS", "1024"))
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")
    rrf_k: int = int(os.getenv("RRF_K", "60"))
    bm25_top_k: int = int(os.getenv("BM25_TOP_K", "50"))
    vector_top_k: int = int(os.getenv("VECTOR_TOP_K", "30"))
    final_top_k: int = int(os.getenv("FINAL_TOP_K", "10"))
    # 컨테이너에서는 /app/data로 마운트되고, 호스트에서는 rag-core/data를 쓴다.
    data_dir: Path = Path(os.getenv("DATA_DIR", str(_RAG_CORE_ROOT / "data")))

    @property
    def raw_corpus_dir(self) -> Path:
        return self.data_dir / "raw_corpus"


settings = Settings()
