from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .models import PlaceReviewSnippet


Requester = Callable[[str, dict[str, str], dict[str, Any], dict[str, str], float], Any]

DEFAULT_APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_APIFY_REVIEWS_ACTOR = "kaix~google-maps-reviews-scraper"


class ApifyReviewsError(Exception):
    pass


def default_db_path() -> Path:
    configured = os.getenv("ALLERNAV_REVIEWS_DB")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / ".data" / "apify_reviews.sqlite"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS review_records (
            place_id TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            source TEXT NOT NULL,
            reviews_json TEXT NOT NULL
        )
        """
    )
    return connection


def apify_configured() -> bool:
    return bool(os.getenv("APIFY_TOKEN", "").strip())


def reviews_limit() -> int:
    raw = os.getenv("APIFY_REVIEWS_LIMIT", "100")
    try:
        return max(1, min(500, int(raw)))
    except ValueError:
        return 100


def cache_ttl() -> timedelta:
    raw = os.getenv("APIFY_REVIEWS_CACHE_TTL_HOURS", "168")
    try:
        return timedelta(hours=max(1, int(raw)))
    except ValueError:
        return timedelta(hours=168)


def load_cached_reviews(
    place_id: str,
    *,
    max_age: timedelta | None = None,
    db_path: Path | None = None,
) -> list[PlaceReviewSnippet]:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT fetched_at, reviews_json FROM review_records WHERE place_id = ?",
            (place_id,),
        ).fetchone()

    if not row:
        return []

    if max_age is not None:
        try:
            fetched_at = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        except ValueError:
            return []
        if datetime.now(UTC) - fetched_at.astimezone(UTC) > max_age:
            return []

    try:
        payload = json.loads(row[1])
    except json.JSONDecodeError:
        return []
    return [PlaceReviewSnippet.model_validate(item) for item in payload if isinstance(item, dict)]


def save_reviews(
    place_id: str,
    reviews: list[PlaceReviewSnippet],
    *,
    db_path: Path | None = None,
) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO review_records (place_id, fetched_at, source, reviews_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(place_id) DO UPDATE SET
                fetched_at=excluded.fetched_at,
                source=excluded.source,
                reviews_json=excluded.reviews_json
            """,
            (
                place_id,
                datetime.now(UTC).isoformat(),
                "apify",
                json.dumps([review.model_dump() for review in reviews]),
            ),
        )


def default_requester(
    url: str,
    params: dict[str, str],
    body: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> Any:
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, params=params, json=body, headers=headers)
        response.raise_for_status()
        return response.json()


def fetch_apify_reviews(
    place_id: str,
    *,
    requester: Requester | None = None,
    db_path: Path | None = None,
) -> list[PlaceReviewSnippet]:
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        return []

    base_url = os.getenv("APIFY_API_BASE_URL", DEFAULT_APIFY_BASE_URL).strip() or DEFAULT_APIFY_BASE_URL
    actor = os.getenv("APIFY_REVIEWS_ACTOR", DEFAULT_APIFY_REVIEWS_ACTOR).strip() or DEFAULT_APIFY_REVIEWS_ACTOR
    actor_path = quote(actor.replace("/", "~"), safe="~")
    url = f"{base_url.rstrip('/')}/actors/{actor_path}/run-sync-get-dataset-items"
    params = {
        "token": token,
    }
    body: dict[str, Any] = {
        "urls": [google_maps_place_url(place_id)],
        "maxReviews": reviews_limit(),
        "sort": os.getenv("APIFY_REVIEWS_SORT", "newest").strip() or "newest",
        "language": os.getenv("APIFY_LANGUAGE", "en").strip() or "en",
        "region": os.getenv("APIFY_REGION", "US").strip() or "US",
        "proxyConfiguration": {"useApifyProxy": True},
    }
    search_query = os.getenv("APIFY_REVIEWS_SEARCH_QUERY", "").strip()
    if search_query:
        body["searchQuery"] = search_query
    newer_than = os.getenv("APIFY_REVIEWS_NEWER_THAN", "").strip()
    if newer_than:
        body["reviewsNewerThan"] = newer_than
    older_than = os.getenv("APIFY_REVIEWS_OLDER_THAN", "").strip()
    if older_than:
        body["reviewsOlderThan"] = older_than

    try:
        raw_payload = (requester or default_requester)(
            url,
            params,
            body,
            {"Content-Type": "application/json"},
            float(os.getenv("APIFY_TIMEOUT_SECONDS", "60")),
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise ApifyReviewsError(str(exc)) from exc

    reviews = parse_apify_reviews(raw_payload)
    save_reviews(place_id, reviews, db_path=db_path)
    return reviews


def load_or_fetch_reviews(
    place_id: str,
    *,
    requester: Requester | None = None,
    db_path: Path | None = None,
) -> list[PlaceReviewSnippet]:
    cached = load_cached_reviews(place_id, max_age=cache_ttl(), db_path=db_path)
    if cached:
        return cached
    if not apify_configured():
        return []
    try:
        return fetch_apify_reviews(place_id, requester=requester, db_path=db_path)
    except ApifyReviewsError:
        return []


def parse_apify_reviews(payload: Any) -> list[PlaceReviewSnippet]:
    reviews: list[PlaceReviewSnippet] = []
    for raw_review in flatten_reviews(payload):
        text = first_string(raw_review, "text", "reviewText", "review_text", "originalText", "translatedText")
        if not text:
            continue
        review_id = (
            first_string(raw_review, "reviewId", "review_id", "id", "reviewUrl", "review_url", "url")
            or f"apify-{len(reviews)}"
        )
        reviews.append(
            PlaceReviewSnippet(
                review_id=review_id,
                author_name=first_string(
                    raw_review,
                    "authorName",
                    "reviewerName",
                    "userName",
                    "name",
                    "author_title",
                    "autor_name",
                    "author_name",
                ),
                rating=parse_rating(
                    first_value(raw_review, "rating", "stars", "reviewRating", "review_rating"),
                ),
                text=text,
                publish_time=parse_publish_time(raw_review),
                relative_publish_time=first_string(
                    raw_review,
                    "relativePublishTimeDescription",
                    "relativeDate",
                    "relative_publish_time",
                ),
            )
        )
    return dedupe_reviews(reviews)


def flatten_reviews(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        flattened: list[dict[str, Any]] = []
        for item in payload:
            flattened.extend(flatten_reviews(item))
        return flattened
    if not isinstance(payload, dict):
        return []

    if first_string(payload, "text", "reviewText", "review_text", "originalText", "translatedText"):
        return [payload]

    flattened: list[dict[str, Any]] = []
    for key in ("reviews", "reviewsData", "reviews_data", "userReviews", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            flattened.extend(flatten_reviews(value))
    return flattened


def google_maps_place_url(place_id: str) -> str:
    return f"https://www.google.com/maps/place/?q=place_id:{quote(place_id, safe='')}"


def first_value(raw_review: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw_review.get(key)
        if value not in (None, ""):
            return value
    return None


def clean_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def first_string(raw_review: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = clean_string(raw_review.get(key))
        if value:
            return value
    return None


def parse_rating(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def parse_publish_time(raw_review: dict[str, Any]) -> str | None:
    timestamp = first_value(raw_review, "timestamp", "review_timestamp")
    if isinstance(timestamp, (int, float)):
        seconds = timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
        return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
    if isinstance(timestamp, str):
        try:
            parsed_timestamp = float(timestamp)
            seconds = parsed_timestamp / 1000 if parsed_timestamp > 10_000_000_000 else parsed_timestamp
            return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
        except ValueError:
            pass

    datetime_utc = first_string(
        raw_review,
        "publishedAtDate",
        "publishedAt",
        "reviewDate",
        "date",
        "review_datetime_utc",
    )
    if not datetime_utc:
        return None
    for pattern in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(datetime_utc, pattern).replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue
    return datetime_utc


def dedupe_reviews(reviews: list[PlaceReviewSnippet]) -> list[PlaceReviewSnippet]:
    output: list[PlaceReviewSnippet] = []
    seen: set[str] = set()
    for review in reviews:
        key = review.review_id or review.text
        if key in seen:
            continue
        seen.add(key)
        output.append(review)
    return output
