"""색인 파이프라인 실행 진입점.

  # 소득세법 하나만
  python -m app.ingestion.pipeline --laws 소득세법 --recreate

  # 전체
  python -m app.ingestion.pipeline --all
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from app.core.config import settings
from app.ingestion import embedder, indexer
from app.ingestion.loader import Chunk, iter_chunks, resolve_law_paths

logger = logging.getLogger("ingestion")

# 임베딩과 색인을 함께 처리하는 단위. 메모리를 아끼려고 전체를 모아두지 않는다.
BATCH_SIZE = 64


def _batched(items, size):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def run(law_names: list[str] | None, recreate: bool, limit: int | None) -> int:
    corpus_dir = settings.raw_corpus_dir
    if not corpus_dir.is_dir():
        logger.error("코퍼스 디렉터리가 없습니다: %s", corpus_dir)
        return 1

    paths = resolve_law_paths(corpus_dir, law_names)
    logger.info("대상 법령 %d개, 인덱스=%s", len(paths), settings.es_index)

    client = indexer.get_client()
    if not client.ping():
        logger.error("Elasticsearch에 연결할 수 없습니다: %s", settings.es_url)
        return 1

    indexer.ensure_index(client, recreate=recreate)

    total_chunks = 0
    total_failed = 0
    started = time.time()

    for path in paths:
        law_started = time.time()
        chunks: list[Chunk] = list(iter_chunks(path))
        if limit:
            chunks = chunks[:limit]

        if not chunks:
            logger.warning("%s: 청크가 없습니다", path.stem)
            continue

        law_indexed = 0
        for batch in _batched(chunks, BATCH_SIZE):
            vectors = embedder.embed([c.text for c in batch])
            succeeded, errors = indexer.index_chunks(client, batch, vectors)
            law_indexed += succeeded
            if errors:
                total_failed += len(errors)
                logger.error("%s: 색인 실패 %d건, 첫 건=%s", path.stem, len(errors), errors[0])

        total_chunks += law_indexed
        logger.info(
            "%s: 청크 %d개 색인 (%.1f초)", path.stem, law_indexed, time.time() - law_started
        )

    client.indices.refresh(index=settings.es_index)
    count = client.count(index=settings.es_index)["count"]

    logger.info("-" * 60)
    logger.info(
        "완료: %d개 색인, 실패 %d건, 총 %.1f초 / 인덱스 문서 수=%d",
        total_chunks,
        total_failed,
        time.time() - started,
        count,
    )
    return 1 if total_failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="법령 코퍼스를 Elasticsearch에 색인한다")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--laws", nargs="+", help="법령 파일명(확장자 제외). 예: 소득세법")
    group.add_argument("--all", action="store_true", help="코퍼스 전체")
    parser.add_argument("--recreate", action="store_true", help="인덱스를 지우고 다시 만든다")
    parser.add_argument("--limit", type=int, help="법령당 최대 청크 수 (테스트용)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    return run(law_names=None if args.all else args.laws, recreate=args.recreate, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
