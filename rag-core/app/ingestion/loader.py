"""법령 JSON을 읽어 색인 단위(청크)로 쪼갠다.

수집 스크립트(scripts/collect_corpus.py)가 이미 조·항·호까지 파싱해두었으므로
여기서는 원문 파싱을 하지 않고 청킹 정책만 담당한다.

청킹 정책:
  - 기본은 조(條) 단위. 법령 검색에서 인용 단위가 조이기 때문이다.
  - 조문이 너무 길면 항(項) 단위로 나눈다. 항 하나가 그래도 길면 글자 수로 자른다.
  - "삭제" 조문은 건너뛴다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator

# 조문 하나가 이 길이를 넘으면 항 단위로 쪼갠다.
MAX_CHUNK_CHARS = 1200
# 항 하나가 이 길이를 넘으면 강제로 자른다. 자를 때 문맥 유지를 위해 겹치는 구간을 둔다.
HARD_SPLIT_OVERLAP = 100

_DELETED_RE = re.compile(r"^\s*제[^(]*\(?\s*\)?\s*삭제")
# 본문 첫 줄의 조문 표기. 가지번호(제1조의2)까지 잡는다.
_ARTICLE_LABEL_RE = re.compile(r"^제\d+조(?:의\d+)?")


@dataclass
class Chunk:
    """ES에 색인되는 최소 단위."""

    chunk_id: str
    law_name: str
    law_id: str
    article_no: str
    article_key: str
    article_title: str
    text: str
    effective_date: str
    source_url: str

    def to_doc(self) -> dict:
        return asdict(self)


def _is_deleted(article: dict) -> bool:
    """'삭제 <2009.12.31>'처럼 내용이 비워진 조문인지 판단한다."""
    content = (article.get("content") or "").strip()
    if not content:
        return True
    if article.get("paragraphs"):
        return False
    # 항이 없고 본문에 '삭제'만 있는 경우
    return "삭제" in content and len(content) < 60


def _paragraph_text(paragraph: dict) -> str:
    """항 하나를 '항내용 + 호 목록' 형태의 평문으로 만든다."""
    parts = [(paragraph.get("항내용") or "").strip()]
    parts.extend((item or "").strip() for item in paragraph.get("호") or [])
    return "\n".join(p for p in parts if p)


def _hard_split(text: str, limit: int) -> Iterator[str]:
    """limit을 넘는 텍스트를 겹침을 두고 자른다."""
    start = 0
    while start < len(text):
        end = start + limit
        yield text[start:end]
        if end >= len(text):
            return
        start = end - HARD_SPLIT_OVERLAP


def _article_label(article: dict) -> str:
    """'제1조', '제1조의2' 같은 조문 표기를 만든다.

    article_no는 가지번호('의2')를 담지 못해 제1조와 제1조의2가 똑같이 '1'로 나온다.
    본문 첫 줄이 항상 정식 표기로 시작하므로 그쪽을 우선 사용한다.
    """
    content = (article.get("content") or "").lstrip()
    matched = _ARTICLE_LABEL_RE.match(content)
    if matched:
        return matched.group(0)
    return f"제{article.get('article_no')}조"


def _article_header(law_name: str, article: dict) -> str:
    """검색 문맥을 위해 각 청크 앞에 붙이는 머리말."""
    title = (article.get("title") or "").strip()
    head = f"{law_name} {_article_label(article)}"
    return f"{head}({title})" if title else head


def iter_chunks(law_path: Path) -> Iterator[Chunk]:
    """법령 JSON 파일 하나를 청크 스트림으로 변환한다."""
    data = json.loads(law_path.read_text(encoding="utf-8"))

    law_name = data["law_name"]
    law_id = str(data.get("law_id") or "")
    source_url = data.get("source_url") or ""

    for article in data.get("articles") or []:
        if _is_deleted(article):
            continue

        article_key = str(article.get("article_key") or "")
        article_no = str(article.get("article_no") or "")
        title = (article.get("title") or "").strip()
        effective_date = str(article.get("effective_date") or "")
        header = _article_header(law_name, article)
        content = (article.get("content") or "").strip()

        base = dict(
            law_name=law_name,
            law_id=law_id,
            article_no=article_no,
            article_key=article_key,
            article_title=title,
            effective_date=effective_date,
            source_url=source_url,
        )

        # 짧은 조문은 통째로 하나의 청크
        if len(content) <= MAX_CHUNK_CHARS:
            yield Chunk(
                chunk_id=f"{law_id}-{article_key}",
                text=f"{header}\n{content}",
                **base,
            )
            continue

        # 긴 조문은 항 단위로 분할. 항 정보가 없으면 글자 수로 자른다.
        paragraphs = article.get("paragraphs") or []
        if not paragraphs:
            for seq, piece in enumerate(_hard_split(content, MAX_CHUNK_CHARS), start=1):
                yield Chunk(
                    chunk_id=f"{law_id}-{article_key}-s{seq}",
                    text=f"{header}\n{piece}",
                    **base,
                )
            continue

        for seq, paragraph in enumerate(paragraphs, start=1):
            body = _paragraph_text(paragraph)
            if not body:
                continue
            if len(body) <= MAX_CHUNK_CHARS:
                yield Chunk(
                    chunk_id=f"{law_id}-{article_key}-p{seq}",
                    text=f"{header}\n{body}",
                    **base,
                )
            else:
                for sub, piece in enumerate(_hard_split(body, MAX_CHUNK_CHARS), start=1):
                    yield Chunk(
                        chunk_id=f"{law_id}-{article_key}-p{seq}s{sub}",
                        text=f"{header}\n{piece}",
                        **base,
                    )


def resolve_law_paths(corpus_dir: Path, names: list[str] | None) -> list[Path]:
    """법령 이름 목록을 실제 파일 경로로 바꾼다. names가 비면 전체를 반환한다."""
    all_paths = sorted(corpus_dir.glob("*.json"))
    if not names:
        return all_paths

    by_stem = {p.stem: p for p in all_paths}
    resolved, missing = [], []
    for name in names:
        path = by_stem.get(name)
        if path is None:
            missing.append(name)
        else:
            resolved.append(path)
    if missing:
        available = ", ".join(sorted(by_stem))
        raise FileNotFoundError(
            f"코퍼스를 찾을 수 없습니다: {', '.join(missing)}\n사용 가능: {available}"
        )
    return resolved
