# cron-alert-analyzer

Receives `K8sCronJobFailed` webhooks from Alertmanager, fetches the failed Job
logs, asks LiteLLM for a concise diagnosis, and posts the result to the Telegram
`Crons` topic.

## Delivery contract

- Telegram delivery validates both HTTP status and JSON `ok=true`.
- Network errors, HTTP 429, and HTTP 5xx are retried up to three attempts.
- Permanent HTTP 4xx errors are recorded without retry.
- `httpx`/`httpcore` request logging is disabled and application log handlers
  redact both Telegram and LiteLLM credentials.
- Delivery and LLM outcomes are exposed at `GET /metrics` and scraped by the
  `cron-alert-analyzer` `VMServiceScrape`.

## AgentGateway exemption

`GET /metrics` is deliberately not published through AgentGateway/MCP. It is a
Prometheus scrape endpoint, not an agent-facing API capability: it is read-only,
contains only aggregate counters, timestamps, and build identity, and exposes no
logs, credentials, private data, or mutation. The backing Service is `ClusterIP`
and no Ingress, IngressRoute, Gateway, or HTTPRoute publishes it. The only
supported consumer is the in-cluster `VMServiceScrape`; adding it to the normal
tool plane would broaden access without a valid agent use case.

Verification for this exemption is part of the deployment gate: server-side
manifest validation, negative search for public routes selecting the Service,
cluster-local `/metrics` scrape, and VictoriaMetrics series presence.

## Tests

Run inside the built image so dependency versions match production:

```bash
docker run --rm \
  -v "$PWD/cron-alert-analyzer/tests:/tests:ro" \
  --entrypoint python \
  cron-alert-analyzer:test \
  -m unittest discover -s /tests -v
```
