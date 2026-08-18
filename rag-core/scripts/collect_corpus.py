"""
PensionRAG - 법제처 Open API 코퍼스 수집 스크립트

연금·절세(IRP/ISA/연금저축/퇴직연금) 관련 법령 조문을 법제처 Open API에서
수집해서 로컬 JSON으로 저장한다. ingestion 파이프라인(청킹→임베딩→색인)의 입력 데이터.

실행:
  cd rag-core
  python scripts/collect_corpus.py
"""

import os
import re
import time
import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict, field

import requests
from dotenv import load_dotenv

# 프로젝트 루트의 .env 로드 (rag-core/scripts/ 기준 두 단계 위)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

LAW_API_KEY = os.getenv("LAW_API_KEY")
if not LAW_API_KEY:
    raise RuntimeError("LAW_API_KEY가 없습니다. 프로젝트 루트 .env를 확인하세요.")

BASE_URL = "http://www.law.go.kr/DRF"
SEARCH_URL = f"{BASE_URL}/lawSearch.do"
VIEW_URL = f"{BASE_URL}/lawService.do"

REQUEST_INTERVAL_SEC = 0.5

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw_corpus"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 1차 수집 대상 (연금·절세 핵심 법령)
TARGET_LAWS = [
    "소득세법",
    "소득세법 시행령",
    "조세특례제한법",
    "조세특례제한법 시행령",
    "근로자퇴직급여 보장법",
    "근로자퇴직급여 보장법 시행령",
    "국민연금법",
    "국민연금법 시행령",
]


@dataclass
class Article:
    """조문 1건. RAG 청킹 단위의 기본 후보."""
    article_no: str          # 조문번호 (예: "12")
    article_key: str         # 조문키 (예: "0001200") - 고유 식별자
    title: str               # 조문제목 (예: "비과세소득")
    content: str             # 조문 전체 텍스트 (본문 + 항/호/목 통합)
    effective_date: str      # 조문시행일자
    paragraphs: list = field(default_factory=list)  # 항 단위 구조 보존


@dataclass
class LawDocument:
    law_name: str
    law_id: str              # 법령ID (예: "001565")
    mst: str                 # 법령일련번호 (본문 조회용 키)
    law_type: str            # 법령구분명 (법률/대통령령/부령)
    department: str
    promulgation_date: str
    enforcement_date: str
    source_url: str
    articles: list


def clean_text(text) -> str:
    """API 응답의 이스케이프 문자, 과도한 공백 정리.
    법제처 API는 내용이 여러 줄일 때 list로 주는 경우가 있어 함께 처리한다."""
    if not text:
        return ""
    if isinstance(text, list):
        text = "\n".join(str(t) for t in text if t)
    if not isinstance(text, str):
        text = str(text)
    text = text.replace('\\"', '"')
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def as_list(value) -> list:
    """API가 항목 1개일 때 dict, 여러 개일 때 list로 주는 문제 보정."""
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    return []


def search_law(law_name: str) -> dict | None:
    """법령명으로 검색해서 MST(법령일련번호) 등 기본 정보 획득."""
    params = {
        "OC": LAW_API_KEY,
        "target": "law",
        "type": "JSON",
        "query": law_name,
        "search": 1,
    }
    resp = requests.get(SEARCH_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    laws = as_list(data.get("LawSearch", {}).get("law"))
    if not laws:
        logger.warning(f"'{law_name}' 검색 결과 없음")
        return None

    # 법령명 완전 일치 우선 (시행령/시행규칙이 함께 잡히므로)
    exact = next(
        (l for l in laws if l.get("법령명한글", "").strip() == law_name),
        None,
    )
    if not exact:
        logger.warning(f"'{law_name}' 완전 일치 없음, 첫 결과 사용: {laws[0].get('법령명한글')}")
        exact = laws[0]
    return exact


def fetch_law_detail(mst: str) -> dict:
    """MST로 법령 본문(조문 포함) 조회."""
    params = {"OC": LAW_API_KEY, "target": "law", "type": "JSON", "MST": mst}
    resp = requests.get(VIEW_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_article_content(jo: dict) -> tuple[str, list]:
    """
    조문 텍스트를 하나로 합친다.

    법제처 응답 특성:
      - 짧은 조문: 조문내용에 전체가 들어있음 (예: 제1조 목적)
      - 항이 있는 조문: 조문내용은 제목 수준만 있고 실제 내용은 항/호/목에 존재
    따라서 조문내용 + 항 + 호 + 목을 모두 이어붙여야 온전한 텍스트가 된다.
    """
    parts = []
    paragraphs = []

    base = clean_text(jo.get("조문내용", ""))
    if base:
        parts.append(base)

    for hang in as_list(jo.get("항")):
        hang_text = clean_text(hang.get("항내용", ""))
        if hang_text:
            parts.append(hang_text)

        ho_texts = []
        for ho in as_list(hang.get("호")):
            ho_text = clean_text(ho.get("호내용", ""))
            if ho_text:
                parts.append(ho_text)
                ho_texts.append(ho_text)

            # 목(가/나/다) 단위까지 존재하는 경우
            for mok in as_list(ho.get("목")):
                mok_text = clean_text(mok.get("목내용", ""))
                if mok_text:
                    parts.append(mok_text)

        paragraphs.append({
            "항번호": hang.get("항번호", ""),
            "항내용": hang_text,
            "호": ho_texts,
        })

    return "\n".join(parts), paragraphs


def parse_articles(detail: dict) -> list[Article]:
    """법령 본문 응답에서 조문 목록 추출. '전문'(장·절 제목)은 제외."""
    articles = []
    jo_list = as_list(detail.get("법령", {}).get("조문", {}).get("조문단위"))

    for jo in jo_list:
        # 조문여부: "조문" = 실제 조문 / "전문" = 장·절 제목 등 구조 요소
        if jo.get("조문여부") != "조문":
            continue

        content, paragraphs = build_article_content(jo)
        if not content:
            continue

        articles.append(Article(
            article_no=str(jo.get("조문번호", "")),
            article_key=str(jo.get("조문키", "")),
            title=clean_text(jo.get("조문제목", "")),
            content=content,
            effective_date=str(jo.get("조문시행일자", "")),
            paragraphs=paragraphs,
        ))

    return articles


def collect_one(law_name: str) -> LawDocument | None:
    logger.info(f"수집 시작: {law_name}")

    basic = search_law(law_name)
    if not basic:
        return None
    time.sleep(REQUEST_INTERVAL_SEC)

    mst = str(basic.get("법령일련번호", ""))
    if not mst:
        logger.warning(f"'{law_name}' 법령일련번호 없음, 건너뜀")
        return None

    detail = fetch_law_detail(mst)
    time.sleep(REQUEST_INTERVAL_SEC)

    articles = parse_articles(detail)
    logger.info(f"  -> 조문 {len(articles)}건")

    return LawDocument(
        law_name=basic.get("법령명한글", law_name),
        law_id=str(basic.get("법령ID", "")),
        mst=mst,
        law_type=basic.get("법령구분명", ""),
        department=basic.get("소관부처명", ""),
        promulgation_date=str(basic.get("공포일자", "")),
        enforcement_date=str(basic.get("시행일자", "")),
        source_url=f"https://www.law.go.kr/lsInfoP.do?lsiSeq={mst}",
        articles=[asdict(a) for a in articles],
    )


def main():
    results, failed = [], []

    for law_name in TARGET_LAWS:
        try:
            doc = collect_one(law_name)
            if doc:
                results.append(doc)
            else:
                failed.append(law_name)
        except (requests.RequestException, ValueError) as e:
            logger.error(f"'{law_name}' 실패: {e}")
            failed.append(law_name)

    for doc in results:
        filename = doc.law_name.replace(" ", "_") + ".json"
        out_path = OUTPUT_DIR / filename
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(asdict(doc), f, ensure_ascii=False, indent=2)
        logger.info(f"저장: {out_path.name} (조문 {len(doc.articles)}건)")

    total_articles = sum(len(d.articles) for d in results)
    logger.info(f"완료: 법령 {len(results)}건, 조문 총 {total_articles}건, 실패 {len(failed)}건")
    if failed:
        logger.warning(f"실패 목록: {failed}")


if __name__ == "__main__":
    main()