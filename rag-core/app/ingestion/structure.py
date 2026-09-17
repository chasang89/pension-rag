"""조문 전체 텍스트(content)에서 항·호·목 구조를 복원한다.

수집 스크립트는 API 응답을 파싱해 content(전체 텍스트)와 paragraphs(항 단위 구조)를
함께 저장했는데, paragraphs에는 목(가·나·다)을 넣지 않았다. 원본 응답은 보관하지 않았으므로
목까지 갖춘 구조는 content에서 다시 만든다. content는 항·호·목이 한 줄에 하나씩 들어 있어
줄머리 기호로 구분할 수 있다.

content에는 수집 단계의 결함이 하나 더 있다. 목 내용이 여러 줄이면 파이썬 목록 모양
문자열(`['가. …', '1) …']`)로 저장됐다. 이런 줄은 풀어서 각각 한 줄로 만든다.
"""

from __future__ import annotations

import ast
import re

# ①~⑳, ㉑~㉟, ㊱~㊿. 16번째 항부터는 법제처가 <16>, <17>로 표기하는 경우가 있다.
HANG_RE = re.compile(r"^(?:[①-⑳㉑-㉟㊱-㊿]|<\d+>)")
HO_RE = re.compile(r"^\d+(?:의\d+)?\.")
MOK_RE = re.compile(r"^[가-힣](?:의\d+)?\.")
_HANG_NO_RE = re.compile(r"^<\d+>")


def expand_lines(content: str) -> list[str]:
    """content를 줄 목록으로 만든다. 빈 줄은 버리고 목록 모양 줄은 풀어낸다."""
    lines: list[str] = []
    for raw in content.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("['", '["')):
            # 형식이 깨졌으면 조용히 넘기지 않고 예외로 드러낸다.
            items = ast.literal_eval(line)
            lines.extend(item.strip() for item in items if item and item.strip())
        else:
            lines.append(line)
    return lines


def _hang_no(line: str) -> str:
    matched = _HANG_NO_RE.match(line)
    return matched.group(0) if matched else line[0]


def build_paragraphs(body_lines: list[str]) -> tuple[list[dict], list[str]]:
    """조문 머리 줄을 뺀 나머지 줄로 항·호·목 구조를 만든다.

    반환값은 (paragraphs, 구조에 붙이지 못한 줄). 두 번째 값이 비어 있어야 정상이다.

    - 항 기호 없이 호부터 시작하면 번호 없는 항 하나로 묶는다(수집본 관례와 같음).
    - 기호가 없는 줄은 바로 앞 요소의 이어지는 줄로 보고 그 요소 텍스트에 줄바꿈으로 붙인다.
      목에 딸린 세목(1), 가))이나 표 그림 문자가 여기에 해당한다.
    """
    paragraphs: list[dict] = []
    orphans: list[str] = []

    for line in body_lines:
        if HANG_RE.match(line):
            paragraphs.append({"항번호": _hang_no(line), "항내용": line, "호": []})
        elif HO_RE.match(line):
            if not paragraphs:
                paragraphs.append({"항번호": "", "항내용": "", "호": []})
            paragraphs[-1]["호"].append({"호내용": line, "목": []})
        elif MOK_RE.match(line) and paragraphs and paragraphs[-1]["호"]:
            paragraphs[-1]["호"][-1]["목"].append(line)
        elif paragraphs and paragraphs[-1]["호"] and paragraphs[-1]["호"][-1]["목"]:
            moks = paragraphs[-1]["호"][-1]["목"]
            moks[-1] = f"{moks[-1]}\n{line}"
        elif paragraphs and paragraphs[-1]["호"]:
            ho = paragraphs[-1]["호"][-1]
            ho["호내용"] = f"{ho['호내용']}\n{line}"
        elif paragraphs and paragraphs[-1]["항내용"]:
            hang = paragraphs[-1]
            hang["항내용"] = f"{hang['항내용']}\n{line}"
        else:
            orphans.append(line)

    return paragraphs, orphans


def flatten(paragraphs: list[dict]) -> list[str]:
    """구조를 원래 줄 순서대로 펼친다. 복원이 정확한지 검증할 때 쓴다."""
    lines: list[str] = []
    for hang in paragraphs:
        if hang["항내용"]:
            lines.extend(hang["항내용"].split("\n"))
        for ho in hang["호"]:
            lines.extend(ho["호내용"].split("\n"))
            for mok in ho["목"]:
                lines.extend(mok.split("\n"))
    return lines


def rebuild_article(article: dict) -> tuple[dict, list[str]]:
    """조문 하나의 content와 paragraphs를 새로 만든다. 나머지 필드는 그대로 둔다.

    반환값은 (새 조문, 구조에 붙이지 못한 줄).
    """
    lines = expand_lines(article.get("content") or "")
    if not lines:
        return {**article, "content": "", "paragraphs": []}, []

    header, body = lines[0], lines[1:]
    paragraphs, orphans = build_paragraphs(body)
    rebuilt = {**article, "content": "\n".join(lines), "paragraphs": paragraphs}
    return rebuilt, orphans
