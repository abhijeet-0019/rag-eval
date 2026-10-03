# Corpus

Pinned snapshots of AWS documentation. One dated folder per crawl; never re-crawl over an existing snapshot.
Gold labels in `eval/questions.jsonl` refer to a specific snapshot.

Current: `snapshot-2026-10-03/` (built by `scripts/crawl_corpus.py`; counts in its `stats.json`, per-page metadata in `manifest.json`).

## Source: GitHub `awsdocs` org checked first (as of 2026-10-03)

No usable markdown source exists for any of the seven guides, so all were crawled from docs.aws.amazon.com.

| Service | Repo | Archived | Last commit | Repo license | Usable doc source? |
|---|---|---|---|---|---|
| S3 | `amazon-s3-developer-guide` (also `-user-guide`) | yes | 2021-01-20 | CC-BY-SA-4.0 docs / modified MIT code (GitHub reports NOASSERTION) | `doc_source/` exists but 5+ years stale, and is the old developer guide, not the current User Guide |
| CloudFront | `amazon-cloudfront-developer-guide` | yes | 2023-06-15 | same | no, content deleted |
| Lambda | `aws-lambda-developer-guide` | no | 2025-08-26 (last commit; GitHub `pushed_at` says 2026-04-08) | MIT-0 | no, only samples/templates/IAM policies, no guide text |
| SQS | `amazon-sqs-developer-guide` | yes | 2023-06-15 | CC-BY-SA-4.0 docs / modified MIT code | no, content deleted |
| SNS | `amazon-sns-developer-guide` | yes | 2023-06-16 | same | no, content deleted |
| IAM | `iam-user-guide` | yes | 2023-06-15 | MIT-0 | no, content deleted |
| DynamoDB | `amazon-dynamodb-developer-guide` | yes | 2023-06-15 | CC-BY-SA-4.0 docs / modified MIT code | no, content deleted |

AWS retired the GitHub doc sources in June 2023 ("Retiring the AWS Documentation on GitHub").

## Crawl method
- Page list: each guide's `toc-contents.json`, minus sections that are API/SDK code-example listings or changelogs
  (`EXCLUDE_SECTIONS` in the script; also recorded in `stats.json`).
- robots.txt honoured. It declares `Crawl-delay: 5` for all agents, which is stricter than the 1 req/s in the project
  brief, so 5 s between requests is used. User-Agent identifies the project and contact.
- Raw HTML cached in `snapshot-*/_raw/` (git-ignored); converted to markdown from the main content column only.

## License and terms
- docs.aws.amazon.com [AWS Site Terms](https://aws.amazon.com/terms/): "documentation (e.g., user guides, developer
  guides, other publications) is licensed under CC-BY-SA-4.0, while any code therein is licensed under MIT-0."
- The same Site Terms, under "License and site access", grant personal use and exclude "any use of data mining, robots,
  or similar data gathering and extraction tools" and commercial use. robots.txt does permit these paths (with the
  crawl delay), and the docs-specific licence above is permissive, but the two are in tension. This crawl is a
  personal, non-commercial learning project; do not extend it to anything commercial without checking.
- CC-BY-SA-4.0 requires attribution and share-alike if redistributed.

**Repo policy:** page content is **not committed** (`.gitignore` excludes the per-service folders and `_raw/`).
`manifest.json`, `stats.json` and this README are committed. Every manifest entry carries the source URL, so the
corpus can be re-fetched, but the live site changes: keep the local snapshot backed up, since gold labels depend on it.
If the repo is ever made public with content included, add attribution and the CC-BY-SA-4.0 notice first.
