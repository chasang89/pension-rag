from app.ingestion.structure import build_paragraphs, expand_lines, flatten, rebuild_article


def test_목을_호_아래에_넣는다():
    paragraphs, orphans = build_paragraphs([
        "③ 다음 각 호의 소득은 합산하지 아니한다.",
        "9. 다음 각 목에 해당하는 연금소득",
        "가. 퇴직소득을 연금수령하는 연금소득",
        "다. 연 1천500만원 이하인 경우 그 연금소득",
        "10. 삭제<2013.1.1>",
    ])

    ho9, ho10 = paragraphs[0]["호"]
    assert ho9["목"] == ["가. 퇴직소득을 연금수령하는 연금소득", "다. 연 1천500만원 이하인 경우 그 연금소득"]
    assert ho10 == {"호내용": "10. 삭제<2013.1.1>", "목": []}
    assert orphans == []


def test_목록_모양_줄을_풀어낸다():
    content = "제12조(비과세소득)\n1. 근로소득\n['머. 출산 지원금', '1) 출생일 이후 지급', '2) 6세 이하']"

    assert expand_lines(content) == [
        "제12조(비과세소득)", "1. 근로소득", "머. 출산 지원금", "1) 출생일 이후 지급", "2) 6세 이하",
    ]


def test_기호_없는_줄은_바로_앞_목에_이어붙인다():
    paragraphs, orphans = build_paragraphs(["1. 근로소득", "머. 출산 지원금", "1) 출생일 이후 지급"])

    assert paragraphs[0]["호"][0]["목"] == ["머. 출산 지원금\n1) 출생일 이후 지급"]
    assert orphans == []


def test_16번째_항부터의_꺾쇠_표기도_항으로_본다():
    paragraphs, _ = build_paragraphs(["⑮ 열다섯째 항", "<16> 열여섯째 항"])

    assert [p["항번호"] for p in paragraphs] == ["⑮", "<16>"]


def test_항_없이_호부터_시작하면_번호_없는_항으로_묶는다():
    paragraphs, _ = build_paragraphs(["1. 첫째 호", "2. 둘째 호"])

    assert paragraphs[0]["항번호"] == ""
    assert paragraphs[0]["항내용"] == ""
    assert [h["호내용"] for h in paragraphs[0]["호"]] == ["1. 첫째 호", "2. 둘째 호"]


def test_짧은_조문은_구조가_비어_있다():
    rebuilt, orphans = rebuild_article({"content": "제1조(목적) 이 법은 …", "paragraphs": []})

    assert rebuilt["paragraphs"] == []
    assert orphans == []


def test_펼치면_원래_줄_순서와_같다():
    content = "제14조(과세표준)\n③ 다음 각 호\n9. 연금소득\n['가. 퇴직소득', '1) 세목']\n10. 삭제\n<16> 항"
    rebuilt, _ = rebuild_article({"content": content, "paragraphs": []})

    lines = rebuilt["content"].split("\n")
    assert flatten(rebuilt["paragraphs"]) == lines[1:]
