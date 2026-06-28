from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib import parse


MONTHS = {
    name.lower(): index
    for index, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}
PAGE_PATTERN = re.compile(r"(?:page|size)[\s_+\-]*(\d+)", re.IGNORECASE)
DATE_PATTERN = re.compile(
    rf"\b({'|'.join(MONTHS)})[\s_+\-]+(20\d{{2}})(?=\D|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MenuImage:
    url: str
    page_number: int
    group_key: str
    version: str | None
    position: int


@dataclass(frozen=True)
class MenuImageSet:
    source_url: str
    document_urls: list[str]
    version: str | None


class _ImageParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.images: list[tuple[str, str, int]] = []
        self._position = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        signal = " ".join((values.get("alt", ""), values.get("title", "")))
        candidates = [values.get("data-image"), values.get("data-src"), values.get("src")]
        candidates.extend(_srcset_urls(values.get("srcset", "")))
        for candidate in candidates:
            if not candidate:
                continue
            absolute = parse.urljoin(self.base_url, html.unescape(candidate.strip()))
            if _looks_like_menu_image(absolute, signal):
                self.images.append((absolute, signal, self._position))
                self._position += 1
                break


def discover_squarespace_menu_images(html_text: str, source_url: str) -> MenuImageSet | None:
    parser = _ImageParser(base_url=source_url)
    parser.feed(html_text)
    groups: dict[str, list[MenuImage]] = {}
    for url, _signal, position in parser.images:
        image = _menu_image(url, position)
        if image:
            groups.setdefault(image.group_key, []).append(image)
    if not groups:
        return None

    images = max(groups.values(), key=_group_priority)
    ordered = sorted(_dedupe_pages(images), key=lambda image: (image.page_number, image.position))
    version = next((image.version for image in ordered if image.version), None)
    return MenuImageSet(
        source_url=source_url,
        document_urls=[image.url for image in ordered],
        version=version,
    )


def _menu_image(url: str, position: int) -> MenuImage | None:
    try:
        parsed = parse.urlparse(url)
    except ValueError:
        return None
    filename = parse.unquote_plus(PurePosixPath(parsed.path).name)
    page_match = PAGE_PATTERN.search(filename)
    if not page_match:
        return None
    page_number = int(page_match.group(1))
    stem = PurePosixPath(filename).stem
    group_key = PAGE_PATTERN.sub("", stem)
    group_key = re.sub(r"[^a-z0-9]+", " ", group_key.lower()).strip()
    date_match = DATE_PATTERN.search(filename)
    version = None
    if date_match:
        version = f"{date_match.group(1).title()} {date_match.group(2)}"
    clean_url = parse.urlunparse(parsed._replace(query="", fragment=""))
    return MenuImage(
        url=clean_url,
        page_number=page_number,
        group_key=group_key,
        version=version,
        position=position,
    )


def _group_priority(images: list[MenuImage]) -> tuple[int, int, int, int, int]:
    dated = next((image.version for image in images if image.version), None)
    year = month = 0
    if dated:
        parsed = datetime.strptime(dated, "%B %Y")
        year, month = parsed.year, parsed.month
    pages = sorted({image.page_number for image in images})
    contiguous = int(bool(pages) and pages == list(range(1, max(pages) + 1)))
    return (int(bool(dated)), year, month, contiguous, len(pages))


def _dedupe_pages(images: list[MenuImage]) -> list[MenuImage]:
    pages: dict[int, MenuImage] = {}
    for image in images:
        pages.setdefault(image.page_number, image)
    return list(pages.values())


def _looks_like_menu_image(url: str, signal: str) -> bool:
    try:
        parsed = parse.urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    path = parse.unquote_plus(parsed.path).lower()
    if not path.endswith((".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")):
        return False
    return "menu" in f"{path} {signal.lower()}" and PAGE_PATTERN.search(path) is not None


def _srcset_urls(srcset: str) -> list[str]:
    output: list[tuple[int, str]] = []
    for entry in srcset.split(","):
        pieces = entry.strip().split()
        if not pieces:
            continue
        width = 0
        if len(pieces) > 1 and pieces[-1].endswith("w"):
            try:
                width = int(pieces[-1][:-1])
            except ValueError:
                width = 0
        output.append((width, pieces[0]))
    return [url for _width, url in sorted(output, reverse=True)]
