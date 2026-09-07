"""Elasticsearch 인덱스 생성과 색인.

한국어 형태소 분석(nori)과 dense_vector를 한 인덱스에 두어
BM25와 kNN을 같은 문서 집합에서 섞을 수 있게 한다(하이브리드 검색).
"""

from __future__ import annotations

import logging

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from app.core.config import settings
from app.ingestion.loader import Chunk

logger = logging.getLogger(__name__)


def build_mapping() -> dict:
    return {
        "settings": {
            "analysis": {
                "analyzer": {
                    "korean": {
                        "type": "custom",
                        "tokenizer": "nori_tokenizer",
                        "filter": ["nori_part_of_speech", "lowercase"],
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "law_name": {
                    "type": "keyword",
                    "fields": {"text": {"type": "text", "analyzer": "korean"}},
                },
                "law_id": {"type": "keyword"},
                "article_no": {"type": "keyword"},
                "article_key": {"type": "keyword"},
                "article_title": {"type": "text", "analyzer": "korean"},
                "text": {"type": "text", "analyzer": "korean"},
                "effective_date": {"type": "keyword"},
                "source_url": {"type": "keyword"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": settings.embedding_dims,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        },
    }


def get_client() -> Elasticsearch:
    return Elasticsearch(settings.es_url, request_timeout=60)


def ensure_index(client: Elasticsearch, recreate: bool = False) -> None:
    """인덱스가 없으면 만든다. recreate면 지우고 다시 만든다."""
    index = settings.es_index
    exists = client.indices.exists(index=index)

    if exists and recreate:
        logger.info("기존 인덱스 삭제: %s", index)
        client.indices.delete(index=index)
        exists = False

    if not exists:
        logger.info("인덱스 생성: %s (dims=%d)", index, settings.embedding_dims)
        client.indices.create(index=index, body=build_mapping())
        return

    # 이미 있는 인덱스의 차원이 설정과 다르면 색인이 통째로 실패하므로 미리 막는다.
    mapping = client.indices.get_mapping(index=index)
    props = mapping[index]["mappings"].get("properties", {})
    current = props.get("embedding", {}).get("dims")
    if current is not None and current != settings.embedding_dims:
        raise ValueError(
            f"인덱스 '{index}'의 embedding 차원은 {current}인데 설정은 "
            f"{settings.embedding_dims}입니다. --recreate로 재생성하세요."
        )


def index_chunks(
    client: Elasticsearch, chunks: list[Chunk], vectors: list[list[float]]
) -> tuple[int, list]:
    """청크와 벡터를 묶어 bulk 색인한다.

    chunk_id를 문서 _id로 쓰므로 같은 코퍼스를 다시 돌려도 중복이 쌓이지 않는다.
    """
    if len(chunks) != len(vectors):
        raise ValueError(f"청크 {len(chunks)}개와 벡터 {len(vectors)}개가 맞지 않습니다.")

    actions = [
        {
            "_op_type": "index",
            "_index": settings.es_index,
            "_id": chunk.chunk_id,
            "_source": {**chunk.to_doc(), "embedding": vector},
        }
        for chunk, vector in zip(chunks, vectors)
    ]

    succeeded, errors = bulk(client, actions, raise_on_error=False, stats_only=False)
    return succeeded, errors
