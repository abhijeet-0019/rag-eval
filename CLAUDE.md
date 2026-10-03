# RAG Eval: hybrid search over the AWS docs

Abhijeet (platform engineer moving into AI engineering) is building a retrieval project to learn RAG properly and to have evidence for AI-engineer interviews. The deliverable is **a results table**, not an app: dense vs BM25 vs hybrid (RRF) vs hybrid + reranker, scored with recall@k and MRR on a hand-written eval set over a pinned snapshot of AWS documentation.

Design discussion, concept questions and eval-set review happen in a separate Claude project ("keeping up with coding"). This repo is for building and running things. The concepts (chunking, BM25, RRF, reranking, recall@k, MRR, dev/test split) are explained in the "RAG Retrieval Glossary" doc in that project.

## Non-negotiables
- **The eval set is Abhijeet's own work.** Never write, rewrite or "improve" questions or gold labels. If he asks for a review, flag problems (ambiguous gold, duplicate questions, leaked wording) and let him fix them.
- **The test split stays locked.** Questions carry `"split": "dev"` or `"test"`, fixed before experiments. During development run only on dev. Never print, inspect or tune against test results. The test run happens once, at the end, via `python -m src.run_eval --split test --final`, which must refuse to run unless the config is committed and must log that it was run.
- **The corpus is a pinned snapshot.** Never re-crawl over an existing snapshot. A new crawl goes into a new dated folder. Gold labels refer to a specific snapshot.
- **Gold labels are passage-level** (doc path + section heading), never chunk IDs, so chunk size can vary without breaking labels. A retrieved chunk is a hit if it overlaps the gold section.
- **Every run is recorded** in `runs/` as one JSON line: timestamp, snapshot, chunking params, embedding model name, retriever settings, k, split, metrics (overall and per question type), latency.
- **Implement the core pieces by hand**: BM25, RRF, cosine top-k, recall@k, MRR. Libraries only for the embedding model, the reranker model and (as a sanity check) comparing his BM25 against `rank_bm25`. He learns from first principles and wants the why.
- Keep changes small and targeted. Be concise and direct.

## Scope
Services: S3, CloudFront, Lambda, SQS, SNS, IAM, DynamoDB. Developer or user guides only. Exclude API references and CLI references. Cross-account, cross-region and cross-AZ access questions are a deliberate focus, so pages on resource-based policies, IAM policy evaluation, bucket/queue/topic/function policies, replication and global tables must be included.

## Layout
```
corpus/snapshot-YYYY-MM-DD/<service>/<page>.md   one file per docs page
corpus/snapshot-YYYY-MM-DD/manifest.json         url, title, service, guide, fetched_at, content_hash
eval/questions.jsonl                             one question per line (schema below)
src/chunking.py embed.py bm25.py fuse.py rerank.py metrics.py run_eval.py
runs/results.jsonl                               append-only run log
```

## Eval question schema
```json
{"id": "q017", "question": "How do I serve files from a private S3 bucket through CloudFront?",
 "gold": [{"doc": "cloudfront/private-content-restricting-access-to-s3", "section": "Origin access control (OAC)"}],
 "type": "conceptual", "split": "dev"}
```
Types: `identifier`, `conceptual`, `vague`, `multi-section`. Split is stratified per type, roughly 60% dev and 40% test.

## First task: build the corpus snapshot (do only this, then stop and report)
1. Check whether the services' guides exist as markdown under the `awsdocs` GitHub organisation. For each of the seven, report: repo exists, archived or not, last commit date, license. Do not assume.
2. Where a current repo exists, use it. Otherwise crawl that guide's pages from docs.aws.amazon.com: respect robots.txt, one request per second at most, a descriptive User-Agent, cache raw HTML locally.
3. Convert each page's main content to markdown, keeping headings, code blocks and tables. Drop navigation and footers.
4. Write `manifest.json` and a stats summary: pages per service, total characters, estimated tokens.
5. Check the license and terms of what you fetched, note them in `corpus/README.md`, and do not commit raw content to a public repo unless the license allows it.
6. Do not start chunking, embedding or anything else. Report the stats and any services with thin or odd coverage.
