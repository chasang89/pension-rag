"""수집본의 content에서 항·호·목 구조를 복원해 코퍼스 JSON을 다시 만든다.

data/raw_corpus/*.json.bak(수집 원본)을 읽어 같은 이름의 *.json으로 저장한다.
원본 .bak 파일은 건드리지 않는다.

실행:
  cd rag-core
  python scripts/rebuild_structure.py            # 검증 후 저장
  python scripts/rebuild_structure.py --dry-run  # 검증만
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.ingestion.structure import flatten, rebuild_article  # noqa: E402


def _legacy_view(paragraphs: list[dict]) -> list[tuple]:
    """새 구조를 수집본 paragraphs 모양(항번호, 항내용, 호내용 목록)으로 줄인다."""
    return [(p["항번호"], p["항내용"], [h["호내용"] for h in p["호"]]) for p in paragraphs]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="검증만 하고 파일은 쓰지 않는다")
    args = parser.parse_args()

    sources = sorted(settings.raw_corpus_dir.glob("*.json.bak"))
    if not sources:
        print(f"원본(.json.bak)이 없습니다: {settings.raw_corpus_dir}")
        return 1

    problems = 0
    totals = {"조문": 0, "목": 0, "구조 있는 조문": 0, "기존 구조와 일치": 0}

    for src in sources:
        data = json.loads(src.read_text(encoding="utf-8"))
        new_articles = []

        for article in data["articles"]:
            rebuilt, orphans = rebuild_article(article)
            new_articles.append(rebuilt)
            totals["조문"] += 1
            totals["목"] += sum(len(h["목"]) for p in rebuilt["paragraphs"] for h in p["호"])
            head = (rebuilt["content"].split("\n") or [""])[0][:30]

            # 1) 구조에 붙이지 못한 줄이 없어야 한다
            if orphans:
                problems += 1
                print(f"[붙일 곳 없는 줄] {data['law_name']} {head}: {orphans[:2]}")

            # 2) 구조를 펼치면 content의 머리 줄 다음 줄들과 정확히 같아야 한다
            lines = rebuilt["content"].split("\n")
            if not orphans and flatten(rebuilt["paragraphs"]) != lines[1:]:
                problems += 1
                print(f"[펼친 결과 불일치] {data['law_name']} {head}")

            # 3) 기존 paragraphs가 있던 조문은 항·호가 그대로 복원돼야 한다(목만 추가)
            old = article.get("paragraphs") or []
            if old:
                totals["구조 있는 조문"] += 1
                if _legacy_view(rebuilt["paragraphs"]) == [(p["항번호"], p["항내용"], p["호"]) for p in old]:
                    totals["기존 구조와 일치"] += 1
                else:
                    problems += 1
                    print(f"[기존 구조와 다름] {data['law_name']} {head}")

        if not args.dry_run:
            out = src.with_suffix("")  # 소득세법.json.bak → 소득세법.json
            out.write_text(
                json.dumps({**data, "articles": new_articles}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    print("-" * 60)
    print(
        f"조문 {totals['조문']}개 / 복원한 목 {totals['목']}개 / "
        f"기존 구조와 일치 {totals['기존 구조와 일치']}/{totals['구조 있는 조문']} / 문제 {problems}건"
    )
    if args.dry_run:
        print("--dry-run: 파일을 쓰지 않았습니다.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
