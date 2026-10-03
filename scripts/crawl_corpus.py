"""Build a pinned corpus snapshot from docs.aws.amazon.com.

    python scripts/crawl_corpus.py                 # fetch (resumable) + convert
    python scripts/crawl_corpus.py --convert-only  # re-run HTML -> markdown from the raw cache, no network

Rules (CLAUDE.md): never write into a snapshot that already has a manifest.json; honour robots.txt
(including its Crawl-delay); descriptive User-Agent; raw HTML cached locally.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify

BASE = "https://docs.aws.amazon.com"
UA = "rag-eval-research-crawler/0.1 (personal learning project; abhijeet.singh@heraldlogic.com)"

# service -> (guide name, path prefix on docs.aws.amazon.com)
GUIDES = {
    "s3": ("Amazon S3 User Guide", "AmazonS3/latest/userguide"),
    "cloudfront": ("Amazon CloudFront Developer Guide", "AmazonCloudFront/latest/DeveloperGuide"),
    "lambda": ("AWS Lambda Developer Guide", "lambda/latest/dg"),
    "sqs": ("Amazon SQS Developer Guide", "AWSSimpleQueueService/latest/SQSDeveloperGuide"),
    "sns": ("Amazon SNS Developer Guide", "sns/latest/dg"),
    "iam": ("AWS IAM User Guide", "IAM/latest/UserGuide"),
    "dynamodb": ("Amazon DynamoDB Developer Guide", "amazondynamodb/latest/developerguide"),
}

# Top-level TOC sections excluded as API/SDK reference or changelog material (scope: guides only).
EXCLUDE_SECTIONS = {
    "code examples", "code examples using sdk", "document history", "documentation history",
    "amazon sns documentation history", "using apis", "java sdk examples", "api reference",
    "making http query requests",
}

# Elements that are page chrome, not content.
DROP_SELECTORS = [
    "#main-col-footer", "#doc-conventions", "#js_error_message", "#breadcrumbs", "#quick-feedback-yes",
    "#quick-feedback-no", ".awsdocs-page-header", ".awsdocs-page-utilities", "#next", "#previous",
    "awsdocs-copyright", ".awsdocs-filter-selector", "script", "style", "noscript", "nav",
]


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Fetcher:
    def __init__(self, delay_floor=1.0):
        self.rp = urllib.robotparser.RobotFileParser()
        text = self._raw(f"{BASE}/robots.txt").decode()
        self.rp.parse(text.splitlines())
        # robotparser drops a Crawl-delay that follows a blank line (true of AWS's file), so read it directly.
        delays = [float(d) for d in re.findall(r"(?im)^crawl-delay:\s*(\d+(?:\.\d+)?)", text)]
        self.delay = max([delay_floor, *delays])
        self.last = 0.0
        print(f"robots.txt crawl-delay -> using {self.delay}s between requests", flush=True)

    @staticmethod
    def _raw(url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()

    def get(self, url):
        if not self.rp.can_fetch(UA, url):
            raise PermissionError(f"robots.txt disallows {url}")
        for attempt in range(4):
            wait = self.delay - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            try:
                return self._raw(url)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(30 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    raise
                time.sleep(15 * (attempt + 1))


def toc_pages(toc, service):
    """Flatten a toc-contents.json into [(href, toc_title, top_section)], minus excluded sections."""
    pages, seen = [], set()

    def walk(node, top):
        href = node.get("href", "")
        if href and not href.startswith("http"):
            href = href.split("#")[0]
            if href.endswith(".html") and href not in seen:
                seen.add(href)
                pages.append((href, node.get("title", ""), top))
        for child in node.get("contents", []):
            walk(child, top)

    for section in toc["contents"]:
        if section.get("title", "").strip().lower() in EXCLUDE_SECTIONS:
            continue
        walk(section, section.get("title", ""))
    return pages


def to_markdown(html):
    soup = BeautifulSoup(html, "lxml")
    body = soup.select_one("#main-col-body") or soup.select_one("#main-content")
    if body is None:
        return None, None
    for sel in DROP_SELECTORS:
        for el in body.select(sel):
            el.decompose()
    for a in body.find_all("a"):  # heading anchors like <a id="x"></a>
        if not a.get_text(strip=True) and not a.find("img"):
            a.decompose()
    h1 = body.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else None
    md = markdownify(str(body), heading_style="ATX", bullets="-", code_language="", strip=["img"])
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return title, md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=f"snapshot-{dt.date.today().isoformat()}")
    ap.add_argument("--convert-only", action="store_true")
    ap.add_argument("--limit", type=int, help="fetch at most N pages per service (smoke test)")
    args = ap.parse_args()

    root = Path("corpus") / args.snapshot
    if (root / "manifest.json").exists():
        sys.exit(f"{root}/manifest.json exists: snapshots are pinned. Use a new dated folder.")
    raw = root / "_raw"
    plan, failures, missing = {}, [], []

    fetcher = None if args.convert_only else Fetcher()
    for service, (_, prefix) in GUIDES.items():
        toc_path = raw / service / "_toc.json"
        if not toc_path.exists():
            if fetcher is None:
                sys.exit(f"no cached TOC for {service}; run without --convert-only")
            toc_path.parent.mkdir(parents=True, exist_ok=True)
            toc_path.write_bytes(fetcher.get(f"{BASE}/{prefix}/toc-contents.json"))
        plan[service] = toc_pages(json.loads(toc_path.read_text()), service)
        if args.limit:
            plan[service] = plan[service][: args.limit]
    total = sum(len(v) for v in plan.values())
    print(f"{total} pages planned: " + ", ".join(f"{s}={len(p)}" for s, p in plan.items()), flush=True)

    # Phase 1: fetch into the raw cache (resumable: existing files are skipped).
    if fetcher:
        done = 0
        for service, pages in plan.items():
            prefix = GUIDES[service][1]
            for href, _, _ in pages:
                done += 1
                dest = raw / service / href
                meta = dest.with_suffix(".meta")
                if dest.exists():
                    continue
                try:
                    data = fetcher.get(f"{BASE}/{prefix}/{href}")
                except urllib.error.HTTPError as e:
                    if e.code == 404:  # listed in the TOC but gone: record, don't block the manifest
                        missing.append(f"{service}/{href}")
                        print(f"[{done}/{total}] 404 {service}/{href}", flush=True)
                        continue
                    failures.append({"service": service, "href": href, "error": repr(e)})
                    print(f"[{done}/{total}] FAIL {service}/{href}: {e!r}", flush=True)
                    continue
                except Exception as e:  # keep going; report at the end
                    failures.append({"service": service, "href": href, "error": repr(e)})
                    print(f"[{done}/{total}] FAIL {service}/{href}: {e!r}", flush=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                meta.write_text(stamp())
                if done % 25 == 0:
                    print(f"[{done}/{total}] {service}/{href}", flush=True)

    # Phase 2: convert + manifest.
    manifest, empty = [], []
    for service, pages in plan.items():
        guide, prefix = GUIDES[service]
        for href, toc_title, top in pages:
            src = raw / service / href
            if not src.exists():
                continue
            title, md = to_markdown(src.read_bytes())
            if md is None or len(md.strip()) < 50:
                empty.append(f"{service}/{href}")
                continue
            stem = href[: -len(".html")].lower()
            out = root / service / f"{stem}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(md, encoding="utf-8")
            meta = src.with_suffix(".meta")
            manifest.append({
                "url": f"{BASE}/{prefix}/{href}", "title": title or toc_title, "service": service,
                "guide": guide, "section": top, "path": f"{service}/{stem}",
                "fetched_at": meta.read_text() if meta.exists() else None,
                "content_hash": hashlib.sha256(md.encode()).hexdigest(), "chars": len(md),
            })

    stats = {}
    for m in manifest:
        s = stats.setdefault(m["service"], {"pages": 0, "chars": 0})
        s["pages"] += 1
        s["chars"] += m["chars"]
    for s in stats.values():
        s["est_tokens"] = s["chars"] // 4
    summary = {"snapshot": args.snapshot, "services": stats, "total_pages": len(manifest),
               "total_chars": sum(s["chars"] for s in stats.values()),
               "est_tokens": sum(s["est_tokens"] for s in stats.values()),
               "excluded_sections": sorted(EXCLUDE_SECTIONS), "failures": failures, "missing_404": missing, "empty_pages": empty}
    if failures and not args.convert_only:
        print(f"{len(failures)} fetch failures; rerun to retry them before the manifest is written.")
        (root / "failures.json").write_text(json.dumps(failures, indent=1))
        sys.exit(1)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (root / "stats.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
