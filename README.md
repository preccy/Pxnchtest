# Pastebin Crawler

This repository contains a lightweight command line utility for collecting the
latest public pastes that appear on [Pastebin](https://pastebin.com/archive).
The tool is intentionally simple so that it can serve as a starting point for
custom automation, security research, or archival scripts.

## Features

* Scrapes the public archive page for metadata (title, author, syntax, etc.).
* Optionally downloads the raw content of each discovered paste.
* Emits JSON to STDOUT or a user supplied file for easy downstream
  consumption.
* Supports rate limiting between requests and configurable logging verbosity.

## Installation

The crawler only depends on `requests` and `beautifulsoup4`.  They can be
installed with pip:

```bash
python -m pip install -r requirements.txt
```

## Usage

```bash
python pastebin_crawler.py --limit 5 --output pastes.json
```

Key options:

* `--limit`: Maximum number of pastes to retrieve (default: 10).
* `--delay`: Number of seconds to wait between HTTP requests (default: 1.0).
* `--skip-content`: When supplied, the crawler will only collect metadata.
* `--verbose` / `-v`: Increase logging verbosity (use twice for debug logging).

Run `python pastebin_crawler.py --help` to view the full CLI reference.

## Ethical considerations

Be mindful of Pastebin's terms of service and robots.txt directives when
running automated scrapers.  This script includes a configurable delay between
requests to reduce load on the service, but you should still exercise
responsible usage.
