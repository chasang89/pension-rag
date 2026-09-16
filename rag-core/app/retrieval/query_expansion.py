"""검색 질의의 금융 약어를 법령 정식 명칭으로 확장한다.

법령 본문은 약어를 쓰지 않는다. 코퍼스 5,713청크에서 ISA·IRP는 한 번도 등장하지 않고
정식 명칭(개인종합자산관리계좌, 개인형퇴직연금제도)만 나온다. 사용자는 약어로 묻기 때문에
그대로 검색하면 BM25는 매칭 자체가 불가능하고 벡터 검색도 빗나간다.

색인 시점 동의어(nori synonym_graph) 대신 질의 시점 확장을 택했다.
사전을 고칠 때마다 전체 코퍼스를 재색인(약 28분)할 필요가 없기 때문이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 약어 → 법령 정식 명칭.
# 정식 명칭은 코퍼스에 실제로 등장하는 표기만 넣는다(tests/test_query_expansion.py에서 검증).
ABBREVIATIONS: dict[str, str] = {
    "ISA": "개인종합자산관리계좌",
    "IRP": "개인형퇴직연금제도",
    "DC": "확정기여형퇴직연금제도",
    "DB": "확정급여형퇴직연금제도",
}


def _abbreviation_pattern(abbr: str) -> re.Pattern[str]:
    # 앞뒤가 영문·숫자가 아닐 때만 약어로 본다.
    # 'ISA계좌', 'DC형'처럼 한글이 붙은 경우는 잡고, 'DBMS', 'CISA'는 거른다.
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(abbr)}(?![A-Za-z0-9])", re.IGNORECASE)


_PATTERNS = [(abbr, full, _abbreviation_pattern(abbr)) for abbr, full in ABBREVIATIONS.items()]


@dataclass(frozen=True)
class ExpandedQuery:
    original: str
    text: str
    # 적용된 (약어, 정식 명칭) 쌍. 로그나 응답에 "무엇으로 해석했는지" 보여줄 때 쓴다.
    expansions: tuple[tuple[str, str], ...]


def expand_query(query: str) -> ExpandedQuery:
    """약어 첫 등장 바로 뒤에 정식 명칭을 덧붙인다.

    약어를 지우지 않고 남기는 이유는 원 질의의 의미를 그대로 보존하기 위해서다.
    정식 명칭이 이미 질의에 있으면 덧붙이지 않는다.
    """
    text = query
    applied: list[tuple[str, str]] = []

    for abbr, full, pattern in _PATTERNS:
        if full in text or not pattern.search(text):
            continue
        text = pattern.sub(lambda m, full=full: f"{m.group(0)} {full} ", text, count=1)
        applied.append((abbr, full))

    text = re.sub(r"\s+", " ", text).strip()
    return ExpandedQuery(original=query, text=text, expansions=tuple(applied))
