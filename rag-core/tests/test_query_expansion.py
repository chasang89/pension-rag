import pytest

from app.core.config import settings
from app.retrieval.query_expansion import ABBREVIATIONS, expand_query


def test_약어_뒤에_정식_명칭을_붙인다():
    result = expand_query("ISA 계좌 비과세 혜택 요건")

    assert result.text == "ISA 개인종합자산관리계좌 계좌 비과세 혜택 요건"
    assert result.expansions == (("ISA", "개인종합자산관리계좌"),)


def test_대소문자를_가리지_않는다():
    assert "개인형퇴직연금제도" in expand_query("irp 납입 한도").text


def test_한글이_붙은_약어도_잡는다():
    assert expand_query("ISA계좌 만기").text == "ISA 개인종합자산관리계좌 계좌 만기"
    assert "확정기여형퇴직연금제도" in expand_query("DC형 퇴직연금").text


@pytest.mark.parametrize("query", ["DBMS 설정", "CISA 자격증", "IRPS 코드"])
def test_다른_단어_안의_글자는_약어로_보지_않는다(query):
    result = expand_query(query)

    assert result.text == query
    assert result.expansions == ()


def test_정식_명칭이_이미_있으면_중복으로_붙이지_않는다():
    query = "ISA 개인종합자산관리계좌 비과세"

    assert expand_query(query).text == query


def test_약어가_여러_개면_모두_확장한다():
    result = expand_query("IRP랑 ISA 중 뭐가 유리해")

    assert {abbr for abbr, _ in result.expansions} == {"IRP", "ISA"}


def test_약어가_없으면_질의를_바꾸지_않는다():
    result = expand_query("연금소득 분리과세 기준")

    assert result.text == "연금소득 분리과세 기준"
    assert result.expansions == ()


def test_사전의_정식_명칭은_모두_코퍼스에_실제로_등장한다():
    """코퍼스에 없는 표기로 확장하면 검색에 아무 도움이 안 된다. 사전 수정 시 안전망."""
    corpus_dir = settings.raw_corpus_dir
    if not corpus_dir.is_dir():
        pytest.skip("코퍼스가 없는 환경(gitignore 대상)")

    from app.ingestion.loader import iter_chunks

    texts = [c.text for p in sorted(corpus_dir.glob("*.json")) for c in iter_chunks(p)]
    missing = [full for full in ABBREVIATIONS.values() if not any(full in t for t in texts)]

    assert missing == []
