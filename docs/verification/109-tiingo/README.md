# #109 private real-source verification

The sanitized acquisition summary records the actual local web/API → durable queue
→ supervised worker → immutable snapshot run on2026-10-28. All20 selected stocks
were fetched, with400 price sessions and next-opening calendar lookahead. Source
response SHA-256 values were independently recomputed from retained bytes and
verified against the captured evidence. No prices, symbols, metadata bodies, token
or real-data screenshots are published here. Private artifacts remain in the
operator-owned local Docker volume.

The initial run failed safely on ambiguous provider metadata. Diagnosis found five
ambiguous tickers in100 requested candidates; the adapter now excludes every
occurrence of each ambiguous ticker, independently of response order. The next
complete run succeeded without handpicked fallback identities.42 captured reads
include the anonymous directory and41 authenticated requests.

The API correctly rejected real evaluation before the approved12:30Z cutoff.
Post-cutoff candidate/UI, pinned-rerun and restart verification remain pending;
this acquisition proof alone does not establish the integrated release gate.
Default offline and synthetic parser fixtures remain separate from real evidence.
