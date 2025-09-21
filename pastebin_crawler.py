"""Pastebin crawler utility.

This module provides a small command line tool that downloads the most
recent public pastes from https://pastebin.com/archive and optionally the raw
content of each paste.  Results are emitted as JSON either to STDOUT or to a
user supplied output file.  The implementation is intentionally lightweight so
that it can be used as a building block for larger tooling.

Example usage
-------------

    python pastebin_crawler.py --limit 5 --output pastes.json

The script will pause between HTTP requests (one second by default) to avoid
placing unnecessary load on Pastebin.  See ``python pastebin_crawler.py
--help`` for the complete list of options.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from typing import Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


ARCHIVE_URL = "https://pastebin.com/archive"
RAW_URL_TEMPLATE = "https://pastebin.com/raw/{paste_id}"


logger = logging.getLogger("pastebin_crawler")


@dataclass
class PasteMetadata:
    """Metadata describing a paste listed on the archive page."""

    paste_id: str
    title: str
    url: str
    author: Optional[str]
    added: Optional[str]
    syntax: Optional[str]


@dataclass
class Paste:
    """A container that couples metadata with optional content."""

    metadata: PasteMetadata
    content: Optional[str] = None


class PastebinCrawler:
    """High level API for collecting public Pastebin entries."""

    def __init__(self, delay: float = 1.0, session: Optional[requests.Session] = None) -> None:
        self.delay = delay
        self.session = session or requests.Session()
        # Pastebin rejects requests without a user agent, so we provide one.
        self.session.headers.setdefault(
            "User-Agent",
            "PastebinCrawler/1.0 (+https://pastebin.com/archive)",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def crawl(self, limit: Optional[int] = None, fetch_content: bool = True) -> List[Paste]:
        """Return a list of :class:`Paste` objects from the archive page.

        Args:
            limit: Maximum number of pastes to return.  ``None`` means that all
                items present on the archive page are processed.
            fetch_content: When ``True`` the crawler retrieves the raw content
                for each paste.  When ``False`` only the metadata is returned.
        """

        pastes: List[Paste] = []
        for metadata in self.iter_archive(limit=limit):
            content: Optional[str] = None
            if fetch_content:
                try:
                    content = self.fetch_raw_content(metadata.paste_id)
                except requests.RequestException as exc:  # pragma: no cover - network failure path
                    logger.warning("Failed to download paste %s: %s", metadata.paste_id, exc)
            pastes.append(Paste(metadata=metadata, content=content))
        return pastes

    def iter_archive(self, limit: Optional[int] = None) -> Iterable[PasteMetadata]:
        """Yield :class:`PasteMetadata` objects from the archive page."""

        response = self.session.get(ARCHIVE_URL, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        table = soup.find("table", class_="maintable")
        if table is None:
            raise RuntimeError("Unable to locate the archive table on the page.")

        count = 0
        for row in table.find_all("tr"):
            headers = row.find_all("th")
            if headers:
                # Skip the header row.
                continue

            cells = row.find_all("td")
            if not cells:
                continue

            link = cells[0].find("a")
            if not link or not link.get("href"):
                continue

            href = link["href"].strip()
            paste_id = href.lstrip("/")
            url = urljoin(ARCHIVE_URL, href)

            metadata = PasteMetadata(
                paste_id=paste_id,
                title=link.text.strip() or paste_id,
                url=url,
                author=_get_text_or_none(cells, 1),
                added=_get_text_or_none(cells, 2),
                syntax=_get_text_or_none(cells, 3),
            )

            logger.debug("Discovered paste %s", paste_id)
            yield metadata

            count += 1
            if limit is not None and count >= limit:
                break

            if self.delay:
                time.sleep(self.delay)

    def fetch_raw_content(self, paste_id: str) -> str:
        """Return the raw content for *paste_id*."""

        url = RAW_URL_TEMPLATE.format(paste_id=paste_id)
        logger.debug("Fetching raw paste %s", paste_id)
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        return response.text


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------

def _get_text_or_none(cells: List[object], index: int) -> Optional[str]:
    """Return the stripped text of ``cells[index]`` if present."""

    if index >= len(cells):
        return None
    text = cells[index].get_text(strip=True)
    return text or None


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch recent public pastes from Pastebin")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of pastes to fetch (default: 10)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to wait between HTTP requests (default: 1.0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Optional path to a JSON file that will receive the crawler output",
    )
    parser.add_argument(
        "--skip-content",
        action="store_true",
        help="Do not download the raw paste contents. Only metadata will be returned.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase logging verbosity (use -vv for debug logging)",
    )
    return parser.parse_args(argv)


def _run_cli(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    _configure_logging(args.verbose)

    crawler = PastebinCrawler(delay=args.delay)
    try:
        pastes = crawler.crawl(limit=args.limit, fetch_content=not args.skip_content)
    except requests.RequestException as exc:  # pragma: no cover - network failure path
        logger.error("Network error while crawling Pastebin: %s", exc)
        return 1
    except Exception as exc:  # pragma: no cover - unexpected error path
        logger.error("Unexpected error: %s", exc)
        return 1

    payload = [asdict(paste) for paste in pastes]
    output_text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output_text)
            handle.write("\n")
        logger.info("Wrote %d paste(s) to %s", len(payload), args.output)
    else:
        sys.stdout.write(output_text)
        sys.stdout.write("\n")

    return 0


def main() -> None:
    sys.exit(_run_cli())


if __name__ == "__main__":
    main()
