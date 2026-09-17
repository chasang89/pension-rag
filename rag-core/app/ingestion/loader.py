"""법령 JSON을 읽어 색인 단위(청크)로 쪼갠다.

입력은 scripts/rebuild_structure.py가 만든 코퍼스다. 조문마다 content(전체 텍스트)와
paragraphs(항 > 호 > 목 구조)가 있다.

청킹 정책:
  - 짧은 조문(1,200자 이하)은 조(條) 단위로 통째로 한 청크. 법령 인용 단위가 조이기 때문이다.
  - 긴 조문은 항(項)마다 나눈다. 항도 길면 호·목 줄 단위로 묶어서 나누고,
    한 줄이 그래도 길면 겹침을 두고 글자 수로 자른다.
  - 한 항이 여러 청크로 나뉘면 뒤쪽 청크에 짧은 항 문장과 소속 호 문장을 다시 붙여 문맥을 잇는다.
  - "삭제" 조문은 건너뛴다.

어떤 경우에도 조문의 모든 줄이 청크 어딘가에 들어가야 한다(tests/test_loader.py에서 검증).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

# 조문 하나가 이 길이를 넘으면 항 단위로 쪼갠다. 항 청크 본문도 이 길이를 넘지 않게 묶는다.
MAX_CHUNK_CHARS = 1200
# 한 줄이 MAX_CHUNK_CHARS를 넘어 강제로 자를 때 문맥 유지를 위해 겹치는 구간.
HARD_SPLIT_OVERLAP = 100
# 한 항·호가 여러 청크로 나뉠 때, 이 길이 이하인 항 문장·호 문장은 뒤쪽 청크에도 반복해 붙인다.
CONTEXT_REPEAT_MAX = 200

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


@dataclass
class _Line:
    text: str
    # 항 문장 줄이면 True. 뒤쪽 청크에 문맥으로 다시 붙일지 판단할 때 쓴다.
    is_hang_head: bool = False
    # 호에 딸린 줄(목·이어지는 줄)이면 그 호의 첫 줄.
    ho_head: str | None = None


def _is_deleted(article: dict) -> bool:
    """'삭제 <2009.12.31>'처럼 내용이 비워진 조문인지 판단한다."""
    content = (article.get("content") or "").strip()
    if not content:
        return True
    if article.get("paragraphs"):
        return False
    # 항이 없고 본문에 '삭제'만 있는 경우
    return "삭제" in content and len(content) < 60


def _hard_split(text: str, limit: int = MAX_CHUNK_CHARS) -> Iterator[str]:
    """limit을 넘는 텍스트를 겹침을 두고 자른다."""
    start = 0
    while start < len(text):
        end = start + limit
        yield text[start:end]
        if end >= len(text):
            return
        start = end - HARD_SPLIT_OVERLAP


def split_line(line: str) -> list[str]:
    """한 줄을 청크에 넣을 조각으로 만든다. 대부분은 줄 그대로 한 조각이다."""
    return list(_hard_split(line)) if len(line) > MAX_CHUNK_CHARS else [line]


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


def lead_text(article: dict) -> str:
    """본문 첫 줄에서 조문 표기·제목을 뺀 나머지.

    항 번호 없이 바로 호가 이어지는 조문은 "다음 각 호의 소득에 대해서는 …" 같은
    머리 문장이 첫 줄에 붙어 있다. 긴 조문을 항 단위로 자를 때 이 문장을 잃지 않도록 따로 꺼낸다.
    """
    lines = (article.get("content") or "").split("\n")
    first = lines[0].strip() if lines else ""
    label = _article_label(article)
    title = (article.get("title") or "").strip()
    for prefix in ([f"{label}({title})"] if title else []) + [label]:
        if first.startswith(prefix):
            return first[len(prefix):].strip()
    return first


def _hang_units(hang: dict) -> list[_Line]:
    """항 하나를 청크에 담을 줄 목록으로 펼친다."""
    units = [_Line(line, is_hang_head=True) for line in hang["항내용"].split("\n") if hang["항내용"]]
    for ho in hang["호"]:
        ho_lines = ho["호내용"].split("\n")
        first = ho_lines[0]
        units.append(_Line(first))
        units.extend(_Line(line, ho_head=first) for line in ho_lines[1:])
        for mok in ho["목"]:
            units.extend(_Line(line, ho_head=first) for line in mok.split("\n"))
    return units


def _pack(units: list[_Line], hang_head: list[str]) -> list[str]:
    """줄들을 MAX_CHUNK_CHARS 이내 본문으로 묶는다.

    새 본문을 시작할 때 짧은 항 문장(hang_head)과 소속 호 문장을 앞에 다시 붙인다.
    """
    head_ctx = hang_head if len("\n".join(hang_head)) <= CONTEXT_REPEAT_MAX else []
    bodies: list[str] = []
    current: list[str] = []
    filled = False  # current에 문맥이 아닌 실제 줄이 하나라도 들어갔는지

    for unit in units:
        for piece in split_line(unit.text):
            if filled and len("\n".join(current + [piece])) > MAX_CHUNK_CHARS:
                bodies.append("\n".join(current))
                current = [] if unit.is_hang_head else list(head_ctx)
                if unit.ho_head and len(unit.ho_head) <= CONTEXT_REPEAT_MAX:
                    current.append(unit.ho_head)
                filled = False
            current.append(piece)
            filled = True

    if filled:
        bodies.append("\n".join(current))
    return bodies


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
        header = _article_header(law_name, article)
        content = (article.get("content") or "").strip()

        base = dict(
            law_name=law_name,
            law_id=law_id,
            article_no=str(article.get("article_no") or ""),
            article_key=article_key,
            article_title=(article.get("title") or "").strip(),
            effective_date=str(article.get("effective_date") or ""),
            source_url=source_url,
        )

        # 짧은 조문은 통째로 하나의 청크
        if len(content) <= MAX_CHUNK_CHARS:
            yield Chunk(chunk_id=f"{law_id}-{article_key}", text=f"{header}\n{content}", **base)
            continue

        lead = lead_text(article)
        # 머리 문장이 짧으면 모든 청크에, 길면 첫 청크에만 붙인다.
        lead_everywhere = bool(lead) and len(lead) <= CONTEXT_REPEAT_MAX
        first_chunk = True

        def prefix() -> str:
            nonlocal first_chunk
            use_lead = lead and (lead_everywhere or first_chunk)
            first_chunk = False
            return f"{header}\n{lead}" if use_lead else header

        paragraphs = article.get("paragraphs") or []

        # 구조 정보가 없는 긴 조문: 첫 줄 이후를 줄 단위로 묶는다.
        if not paragraphs:
            rest = [_Line(line) for line in content.split("\n")[1:] if line.strip()]
            if not rest:
                # 긴 첫 줄 하나뿐인 조문. 머리말 뒤에 붙이지 말고 줄 자체를 자른다.
                lead, lead_everywhere = "", False
                rest = [_Line(content)]
            for seq, body in enumerate(_pack(rest, hang_head=[]), start=1):
                yield Chunk(chunk_id=f"{law_id}-{article_key}-s{seq}", text=f"{prefix()}\n{body}", **base)
            continue

        for seq, hang in enumerate(paragraphs, start=1):
            hang_head = hang["항내용"].split("\n") if hang["항내용"] else []
            bodies = _pack(_hang_units(hang), hang_head)
            for sub, body in enumerate(bodies, start=1):
                suffix = f"p{seq}" if len(bodies) == 1 else f"p{seq}s{sub}"
                yield Chunk(chunk_id=f"{law_id}-{article_key}-{suffix}", text=f"{prefix()}\n{body}", **base)


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
