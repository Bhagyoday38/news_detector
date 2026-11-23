from concurrent.futures import ThreadPoolExecutor
from html import unescape
import logging
import re
from typing import NamedTuple
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

import requests


logger = logging.getLogger(__name__)
MAX_FEED_BYTES = 1_000_000
MAX_FEED_ITEMS = 100
MAX_MATCHES = 5
REQUEST_TIMEOUT = (3.05, 5)
MIN_MATCH_TERMS = 2
MIN_MATCH_SCORE = 0.25


class RSSFeed(NamedTuple):
    name: str
    url: str
    host: str


class FactCheck(NamedTuple):
    title: str
    url: str
    source: str
    summary: str
    published: str


class FactCheckSearchResult(NamedTuple):
    matches: tuple
    checked_sources: tuple
    failed_sources: tuple


class NewsArticle(NamedTuple):
    title: str
    url: str
    source: str
    published: str


class NewsSearchResult(NamedTuple):
    articles: tuple
    checked_sources: tuple
    failed_sources: tuple


FACT_CHECK_FEEDS = (
    RSSFeed(
        "Snopes",
        "https://www.snopes.com/fact-check/feed/",
        "www.snopes.com",
    ),
)
NEWS_FEEDS = (
    RSSFeed(
        "The Guardian",
        "https://www.theguardian.com/world/rss",
        "www.theguardian.com",
    ),
    RSSFeed(
        "Al Jazeera",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "www.aljazeera.com",
    ),
    RSSFeed(
        "Deutsche Welle",
        "https://rss.dw.com/xml/rss-en-all",
        "www.dw.com",
    ),
    RSSFeed(
        "France 24",
        "https://www.france24.com/en/rss",
        "www.france24.com",
    ),
    RSSFeed(
        "CNBC",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "www.cnbc.com",
    ),
    RSSFeed(
        "Euronews",
        "https://www.euronews.com/rss?format=mrss&level=theme&name=news",
        "www.euronews.com",
    ),
)
SOURCE_NAMES = tuple(feed.name for feed in FACT_CHECK_FEEDS)
NEWS_SOURCE_NAMES = tuple(feed.name for feed in NEWS_FEEDS)

_STOP_WORDS = frozenset(
    {
        "about", "after", "again", "against", "also", "and", "are", "because",
        "been", "before", "being", "but", "can", "could", "did", "does", "for",
        "from", "had", "has", "have", "her", "here", "his", "how", "into",
        "its", "may", "more", "most", "not", "our", "out", "over", "said",
        "says", "she", "should", "some", "than", "that", "the", "their",
        "them", "then", "there", "these", "they", "this", "those", "through",
        "under", "was", "were", "what", "when", "where", "which", "while",
        "who", "will", "with", "would", "you", "your",
    }
)
_HTML_TAG = re.compile(r"<[^>]*>")
_TOKEN = re.compile(r"[^\W_]{3,}", re.UNICODE)


def _clean_text(value):
    return " ".join(_HTML_TAG.sub(" ", unescape(value or "")).split())


def _terms(text):
    return {
        token
        for token in _TOKEN.findall(_clean_text(text).casefold())
        if token not in _STOP_WORDS
    }


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].casefold()


def _field_text(element, names):
    for child in element:
        name = _local_name(child.tag)
        if name not in names:
            continue
        if name == "link":
            if child.get("rel", "alternate") not in {"", "alternate"}:
                continue
            value = child.get("href") or "".join(child.itertext())
        else:
            value = "".join(child.itertext())
        if value.strip():
            return value.strip()
    return ""


def _safe_link(raw_link, feed):
    try:
        parsed = urlsplit(urljoin(feed.url, raw_link.strip()))
        if (
            parsed.scheme != "https"
            or parsed.hostname != feed.host
            or parsed.username
            or parsed.password
            or parsed.port is not None
        ):
            return ""
    except ValueError:
        return ""
    return parsed.geturl()


def _download_feed(feed):
    chunks = []
    size = 0
    with requests.get(
        feed.url,
        headers={"User-Agent": "SignalCheck/1.0"},
        timeout=REQUEST_TIMEOUT,
        stream=True,
    ) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=16_384):
            if not chunk:
                continue
            size += len(chunk)
            if size > MAX_FEED_BYTES:
                raise ValueError("RSS feed exceeded the size limit.")
            chunks.append(chunk)
    return b"".join(chunks)


def _parse_feed(feed):
    content = _download_feed(feed)
    if re.search(br"<!\s*(?:doctype|entity)\b", content, re.IGNORECASE):
        raise ValueError("RSS feed contains unsupported XML declarations.")

    root = ET.fromstring(content)
    if _local_name(root.tag) not in {"rss", "feed", "rdf"}:
        raise ValueError("RSS feed has an unsupported XML format.")

    entries = []
    for element in root.iter():
        if _local_name(element.tag) not in {"item", "entry"}:
            continue
        title = _clean_text(_field_text(element, {"title"}))[:300]
        link = _safe_link(_field_text(element, {"link"}), feed)
        if not title or not link:
            continue
        summary = _clean_text(
            _field_text(element, {"description", "summary", "encoded", "content"})
        )[:2_000]
        published = _clean_text(
            _field_text(element, {"pubdate", "published", "updated"})
        )[:100]
        entries.append(FactCheck(title, link, feed.name, summary, published))
        if len(entries) >= MAX_FEED_ITEMS:
            break
    return entries


def _match_score(query_terms, fact_check):
    best_score = 0
    for text in (fact_check.title, fact_check.summary):
        candidate_terms = _terms(text)
        overlap = len(query_terms & candidate_terms)
        if overlap < MIN_MATCH_TERMS:
            continue
        score = overlap / min(len(query_terms), len(candidate_terms))
        best_score = max(best_score, score)
    return best_score


def find_related_fact_checks(article):
    query_terms = _terms(article)
    checked_sources = []
    failed_sources = []
    scored_matches = []

    for feed in FACT_CHECK_FEEDS:
        try:
            entries = _parse_feed(feed)
        except (requests.RequestException, ET.ParseError, ValueError) as error:
            logger.warning("Fact-check feed %s failed: %s", feed.name, error)
            failed_sources.append(feed.name)
            continue

        checked_sources.append(feed.name)
        for entry in entries:
            score = _match_score(query_terms, entry)
            if score >= MIN_MATCH_SCORE:
                scored_matches.append((score, entry))

    scored_matches.sort(key=lambda result: (-result[0], result[1].title.casefold()))
    matches = []
    seen_urls = set()
    for _, entry in scored_matches:
        if entry.url in seen_urls:
            continue
        matches.append(entry)
        seen_urls.add(entry.url)
        if len(matches) == MAX_MATCHES:
            break

    return FactCheckSearchResult(
        tuple(matches),
        tuple(checked_sources),
        tuple(failed_sources),
    )


def find_related_news(article):
    query_terms = _terms(article)
    checked_sources = []
    failed_sources = []
    scored_matches = []

    with ThreadPoolExecutor(max_workers=min(4, len(NEWS_FEEDS))) as executor:
        feed_entries = executor.map(_parse_news_feed, NEWS_FEEDS)
        for feed, entries in zip(NEWS_FEEDS, feed_entries):
            if entries is None:
                failed_sources.append(feed.name)
                continue

            checked_sources.append(feed.name)
            for entry in entries:
                score = _match_score(query_terms, entry)
                if score >= MIN_MATCH_SCORE:
                    scored_matches.append((score, entry))

    scored_matches.sort(key=lambda result: (-result[0], result[1].title.casefold()))
    articles = []
    seen_urls = set()
    for _, entry in scored_matches:
        if entry.url in seen_urls:
            continue
        articles.append(
            NewsArticle(
                entry.title,
                entry.url,
                entry.source,
                entry.published,
            )
        )
        seen_urls.add(entry.url)
        if len(articles) == MAX_MATCHES:
            break

    return NewsSearchResult(
        tuple(articles),
        tuple(checked_sources),
        tuple(failed_sources),
    )


def _parse_news_feed(feed):
    try:
        return _parse_feed(feed)
    except (requests.RequestException, ET.ParseError, ValueError) as error:
        logger.warning("News feed %s failed: %s", feed.name, error)
        return None
