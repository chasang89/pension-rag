"""bge-m3 임베딩.

모델이 크기 때문에(최초 다운로드 약 2GB) 프로세스당 한 번만 로드한다.
코사인 유사도로 검색하므로 정규화된 벡터를 만든다.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_model():
    # import 시점에 torch를 끌어오지 않도록 함수 안에서 import한다.
    from sentence_transformers import SentenceTransformer

    logger.info("임베딩 모델 로드: %s", settings.embedding_model)
    return SentenceTransformer(settings.embedding_model)


def embed(texts: list[str], batch_size: int = 8) -> list[list[float]]:
    """텍스트 목록을 정규화된 dense 벡터로 변환한다."""
    if not texts:
        return []

    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )

    dims = vectors.shape[1]
    if dims != settings.embedding_dims:
        raise ValueError(
            f"임베딩 차원 불일치: 모델은 {dims}차원인데 설정은 "
            f"{settings.embedding_dims}차원입니다. EMBEDDING_DIMS를 맞추고 "
            f"인덱스를 재생성하세요."
        )

    return vectors.tolist()
