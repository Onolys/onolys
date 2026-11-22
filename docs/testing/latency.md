# Latency

**Audience:** contributors.

What is measured and where it is recorded. Staging numbers (upload to transcript, confirm to report, per audio second) are in [reference/staging-e2e.md](../reference/staging-e2e.md); at the time of the last staging run a 6.7 minute recording gave a report about 68 s after speaker confirm.

## Engine limit

`python -m onolys_miti.check` fails when the 95th percentile wall time of one run is over 90 s, or tokens per run are over 120,000 (`fixtures/thresholds.yaml`). It needs a key; run it with the live checks in [local-setup.md](local-setup.md#owner-live-checks).

## Routes

Per-route timeouts, retries and concurrency are route data ([llm-client.md](../implementation/llm-client.md)). Check cache hit ratios on a live run before changing caching settings: the provider may not share the cache across calls.
