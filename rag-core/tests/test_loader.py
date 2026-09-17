import json
from collections import defaultdict

import pytest

from app.core.config import settings
from app.ingestion.loader import MAX_CHUNK_CHARS, _is_deleted, iter_chunks, lead_text, split_line


def _write_law(tmp_path, articles):
    path = tmp_path / "테스트법.json"
    path.write_text(
        json.dumps({"law_name": "테스트법", "law_id": "999", "source_url": "", "articles": articles}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _article(content, paragraphs, key="0014001", title="과세표준의 계산"):
    return {"article_no": "14", "article_key": key, "title": title, "content": content,
            "effective_date": "20260101", "paragraphs": paragraphs}


def _long_hang_article():
    """항 하나에 긴 호가 여러 개라 한 항이 여러 청크로 나뉘는 조문."""
    filler = "가" * 300
    hos = [{"호내용": f"{i}. 호 문장 {i} {filler}", "목": []} for i in range(1, 6)]
    # 6호는 짧고, 그 아래 긴 가목 때문에 다목이 다음 청크로 넘어가게 만든다.
    hos.append({"호내용": "6. 분리과세연금소득", "목": [
        "가. 퇴직소득을 연금수령하는 연금소득 " + "나" * 540,
        "다. 연 1천500만원 이하인 경우 그 연금소득",
    ]})
    lines = ["③ 다음 각 호의 소득은 합산하지 아니한다."]
    for ho in hos:
        lines.append(ho["호내용"])
        lines.extend(ho["목"])
    paragraphs = [{"항번호": "③", "항내용": lines[0], "호": hos}]
    return _article("제14조(과세표준의 계산)\n" + "\n".join(lines), paragraphs)


def test_긴_조문을_나눠도_목_내용이_청크에_들어간다(tmp_path):
    chunks = list(iter_chunks(_write_law(tmp_path, [_long_hang_article()])))

    assert any("연 1천500만원 이하" in c.text for c in chunks)


def test_한_항이_여러_청크로_나뉘면_본문이_제한_길이를_지킨다(tmp_path):
    chunks = list(iter_chunks(_write_law(tmp_path, [_long_hang_article()])))

    assert len(chunks) > 1
    for c in chunks:
        body = c.text.split("\n", 1)[1]
        assert len(body) <= MAX_CHUNK_CHARS


def test_뒤쪽_청크에도_짧은_항_문장이_문맥으로_붙는다(tmp_path):
    chunks = list(iter_chunks(_write_law(tmp_path, [_long_hang_article()])))

    assert all("③ 다음 각 호의 소득은 합산하지 아니한다." in c.text for c in chunks)


def test_목이_다른_청크로_넘어가면_소속_호_문장을_함께_붙인다(tmp_path):
    chunks = list(iter_chunks(_write_law(tmp_path, [_long_hang_article()])))

    mok_chunk = next(c for c in chunks if "연 1천500만원 이하" in c.text)
    assert "6. 분리과세연금소득" in mok_chunk.text
    # 6호 문장이 원래 자리와 목이 넘어간 청크, 두 곳에 있어야 반복해 붙인 것이다.
    assert sum("6. 분리과세연금소득" in c.text for c in chunks) >= 2


def test_항_번호_없는_조문의_머리_문장을_잃지_않는다(tmp_path):
    filler = "나" * 400
    hos = [{"호내용": f"{i}. 비과세 항목 {i} {filler}", "목": []} for i in range(1, 5)]
    content = "제12조(비과세소득) 다음 각 호의 소득에 대해서는 소득세를 과세하지 아니한다.\n" + "\n".join(
        h["호내용"] for h in hos
    )
    article = _article(content, [{"항번호": "", "항내용": "", "호": hos}], key="0012001", title="비과세소득")

    chunks = list(iter_chunks(_write_law(tmp_path, [article])))

    assert lead_text(article) == "다음 각 호의 소득에 대해서는 소득세를 과세하지 아니한다."
    assert all("다음 각 호의 소득에 대해서는 소득세를 과세하지 아니한다." in c.text for c in chunks)


def test_실제_코퍼스의_모든_줄이_청크_어딘가에_들어간다():
    """청킹 중 내용이 빠지지 않았음을 보증한다. 목 236개 조문 누락 사고를 막기 위한 안전망."""
    corpus_dir = settings.raw_corpus_dir
    paths = sorted(corpus_dir.glob("*.json")) if corpus_dir.is_dir() else []
    if not paths:
        pytest.skip("코퍼스가 없는 환경(gitignore 대상)")

    missing = []
    ids = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        texts_by_key = defaultdict(list)
        for chunk in iter_chunks(path):
            texts_by_key[chunk.article_key].append(chunk.text)
            ids.append(chunk.chunk_id)

        for article in data["articles"]:
            if _is_deleted(article):
                continue
            joined = "\n\n".join(texts_by_key[str(article["article_key"])])
            lines = article["content"].split("\n")
            required = [lead_text(article)] + lines[1:]
            for line in filter(None, (l.strip() for l in required)):
                for piece in split_line(line):
                    if piece not in joined:
                        missing.append((data["law_name"], lines[0][:30], piece[:40]))

    assert missing == [], f"청크에서 빠진 줄 {len(missing)}개, 예: {missing[:3]}"
    assert len(ids) == len(set(ids)), "chunk_id 중복"
