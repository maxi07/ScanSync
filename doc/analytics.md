# ScanSync Analytics

## Configuration

Analytics is opt-in. Set both `ANALYTICS_URL` (base URL, without `/event`) and
`ANALYTICS_API_KEY` in `.env`, then run `make start` to rebuild/recreate the
services. Both default to empty. Missing/blank credentials or an invalid URL
disable transmission. There is no built-in public collection endpoint.

Create a separate `scansync` project/API key in maexbert-analytics with
`make seed NAME=scansync`. Never put this key in a URL or commit it.
Use HTTPS outside a trusted local network.

Docker Compose passes the configuration to all six Python services. It also
sets `SCANSYNC_SERVICE` to `detection_service`, `metadata_service`, `ocr_service`,
`file_naming_service`, `upload_service`, or `web_service`. For a deployment
without Compose, set that name explicitly. `APP_VERSION` supplies the top-level
`app_version`; `make start` resolves it from Git, otherwise it defaults to `dev`.

All six Python services wait for RabbitMQ's application and TCP listeners to
be healthy before Compose starts them. The common RabbitMQ client also retries
temporary connection failures locally; a successful retry is not an analytics
failure. If all 10 connection attempts fail, one `queue.connection_failed`
event reports the client role, attempt count, and exception details.

The transport follows maexbert-analytics' JSON API, using only Python's standard
library so deployments do not need access to the private analytics repository.
Requests use `POST <ANALYTICS_URL>/event` with `X-API-KEY`, the identifying
`User-Agent: ScanSync/<app_version>`, a 1.5-second socket timeout and daemon
threads. HTTP redirects are not followed, so API keys are
not forwarded to a redirect target. Each process permits at most 16 concurrent
sends; events beyond that limit are dropped immediately. No event queue, persistence, retry,
shutdown flush, or ordering guarantee is provided.

The first delivery failure logs a local WARNING, at most once per Python
process until restart, even if several sends fail concurrently. The startup
`service.started` event normally exposes configuration problems immediately.
The warning contains only the endpoint origin and a technical reason, such as
HTTP 403, DNS resolution failure, TLS certificate verification failure, or a
timeout. It never includes API keys, URL paths/query strings, response bodies,
or raw exception messages. The warning is not sent to analytics and cannot
create a recursive error loop. Document processing and subsequent delivery
attempts continue; repeated delivery warnings are suppressed.

If the LAN endpoint works but the public HTTPS endpoint returns 403, check
the reverse proxy/WAF. Some bot-protection rules reject Python's default
User-Agent; ScanSync identifies itself explicitly rather than impersonating a
browser. If access remains blocked, allow backend requests to `POST /event`
without a browser challenge, while retaining API-key authentication and TLS
certificate verification. HTTP 401 instead indicates a rejected project key.

## Privacy And Correlation

Only explicitly allowed technical fields are sent. There are no filenames,
SMB/OneDrive paths, document hashes, OCR text, prompts, AI output, usernames,
email addresses, tenant/drive/folder IDs, request URLs, query strings, bodies,
headers, tokens, hostnames, or personal account IDs in analytics payloads.

The top-level `user_id` is a random, pseudonymous **installation ID**, not a
human user or PC name. Its format is `install_<32 lowercase hexadecimal digits>`.
The first background send atomically creates it in
`/app/data/analytics-installation-id`. All Python services and replicas share
that file through the existing `data` volume, so the ID survives restarts,
container rebuilds, and application updates. No host/MAC address or other
machine fingerprint is read. Disabled analytics never creates the file.

If the file cannot be created/read, or contains an invalid ID, events are still
sent without `user_id`. Deleting the ID file or its volume resets the identity
on the next send. Cloning the data volume also clones this ID; delete the ID
file in the clone when it should represent a separate installation. The ID is
not a secret or an authentication credential.

Every event includes `metadata.service`. Document events include a random
`metadata.document_id`, propagated from detection through RabbitMQ and the
processing item. Older queued items without this field use a truncated SHA-256
of their internal numeric job ID and creation timestamp, never a filename or
document hash. That compatibility ID cannot be joined to earlier random IDs.
This document ID is separate from the installation-level `user_id`.

Where a real exception exists, `error_type` is its class name and `traceback`
is a list of exception/cause entries, each with `error_type` and `frames`.
Frames contain only `module`, `function`, and `line`. The chain is limited to
5 exceptions and the last 24 frames per exception. Exception messages,
source text, absolute file paths, and local variables are intentionally omitted.
HTTP exceptions include their numeric `status_code` where available.
Operating-system exceptions include their numeric `error_code` (`errno`),
including when wrapped inside another exception's arguments. Logged exceptions
passed as logging arguments are captured even without `exc_info`.
Failures represented by return codes rather than exceptions have `reason`,
`status`, `error_code`, or `status_code`; they do not invent an exception class.

```json
{
  "event_name": "naming.failed",
  "user_id": "install_e1e4d44a94cd4a0f8ca92c9cc0663723",
  "app_version": "v1.4.2",
  "metadata": {
    "service": "file_naming_service",
    "document_id": "dc4bef2cd6f14b5487127878c646c239",
    "provider": "openai",
    "model": "gpt-6-luna",
    "duration_ms": 381,
    "fallback_used": true,
    "status_code": 401,
    "error_type": "AuthenticationError",
    "traceback": [
      {
        "error_type": "AuthenticationError",
        "frames": [
          { "module": "scansynclib.openai_helper", "function": "generate_filename_openai", "line": 140 }
        ]
      }
    ]
  }
}
```

## Event Catalog

Durations are integer milliseconds. Stage durations use a monotonic clock;
the total duration uses the detection timestamp across processes. File sizes
are bytes. Optional fields are omitted when unavailable.

| Event | Meaning | Additional Metadata |
| --- | --- | --- |
| `service.started` | Python service initializes shared logging | Common fields only |
| `service.error` | ERROR/CRITICAL log, uncaught process exception, or uncaught thread exception | `level`, `logger`, `location` (`module:function:line`), `operation`; exception/HTTP/OS fields when available |
| `document.detected` | A content group was published to metadata processing, including subsequently ignored housekeeping files | `size_bytes`, `extension`, `targets` (source copies) |
| `document.received` | Metadata accepts the group after ignoring directories, hidden/security/working files and the failed-documents folder | `size_bytes`, `extension`, `targets` (source copies) |
| `document.skipped` | Metadata rejects invalid/deleted input | `reason`: `invalid_file` or `source_deleted`, `duration_ms` |
| `document.failed` | Forwarding fails, OCR output is missing at upload, or upload fails | `reason`, `operation`, `queue_name` when known; exception fields when available |
| `document.completed` | Upload to every configured destination and final job update succeeded | `total_duration_ms`, `pages`, `targets` |
| `metadata.started` | Metadata job is created | Common document fields |
| `metadata.completed` | Metadata is collected and OCR is queued | `duration_ms`, `pages`, `targets` (OneDrive destinations) |
| `metadata.failed` | Metadata callback raises or publication to OCR fails | `reason` (`queue_publish`), `queue_name`, `duration_ms` for failed handoffs; exception fields and document ID when available |
| `ocr.started` | OCR stage begins | `pages`, `size_bytes`, `extension` |
| `ocr.completed` | OCR succeeds and output contains extractable text | `duration_ms`, `pages`, `language` (`eng+deu`), `status`, `error_code` (0) |
| `ocr.no_text` | OCR returns success but output has no extractable text | `duration_ms`, `pages`, `language`, `status`, `error_code` |
| `ocr.skipped` | Input format is unsupported | `duration_ms`, `pages`, `language`, `status`, exception fields |
| `ocr.failed` | OCR fails, output is missing, or the callback raises | `duration_ms`, `pages`, `language`, `status`, `error_code`, `operation`; exception fields when available |
| `naming.started` | OpenAI/Ollama naming helper starts | `provider`, `model` |
| `naming.completed` | AI output produces a successful filename | `provider`, `model`, `duration_ms`, `fallback_used` (false), `retries` |
| `naming.skipped` | Naming is disabled or lacks OCR input/text | `provider`, `model`, `reason`: `disabled`, `no_ocr_file`, `no_pdf_text`; `fallback_used` (true), `duration_ms` when applicable |
| `naming.failed` | Naming fails and the original name remains | `provider`, `model`, `duration_ms`, `fallback_used`, `retries`, `reason`, exception/HTTP fields when available |
| `naming.retried` | Another naming attempt is scheduled | `provider`, `model`, `attempt` (failed attempt, starting at 1), exception fields |
| `upload.started` | Document upload stage starts | `targets`, `size_bytes`, `extension` |
| `upload.target_started` | One destination is about to be uploaded | `attempt` (destination ordinal, starting at 1) |
| `upload.target_completed` | One destination upload succeeds | `attempt`, `duration_ms`, `status_code` when available |
| `upload.target_failed` | One destination upload fails | `attempt`, `duration_ms`, `status_code` from the failing request when available; omitted for failures without an HTTP response |
| `upload.request_failed` | A OneDrive request or local upload operation fails | `method` (`small`/`chunked`), `reason`, exception/HTTP fields |
| `upload.retried` | Upload retry is scheduled by the existing retry policy | `attempt`, exception fields |
| `upload.completed` | All destinations succeed | `duration_ms`, `targets`, `size_bytes`, `extension`, `retries` |
| `upload.failed` | A destination fails, no destinations exist, input is missing, or callback raises | `duration_ms`, `targets`, `successful_targets`, `failed_targets`, `size_bytes`, `extension`, `retries`, `reason`, `operation`; exception fields when available |
| `dependency.failed` | OpenAI key check or OneDrive token refresh fails | `provider`, `model`, `operation`, `reason`, exception/HTTP fields |
| `http.request_completed` | A top-level HTML page GET finishes with a 2xx status | `route` (Flask endpoint name), `method`, `status_code`, `duration_ms` |
| `http.request_failed` | Web request other than `/health` finishes with status 400 or above | Same fields; expected 4xx responses are not crashes |
| `queue.connection_failed` | RabbitMQ remains unreachable after all 10 connection attempts | `operation` (client role), `attempt` (10), `reason` (`broker_unavailable`), exception fields |
| `queue.connection_lost` | An established connection is lost during heartbeats or consumption | `operation`, `queue_name` when known, `reason` (`heartbeat_failed`, `consumer_disconnected`, `listener_disconnected`), exception fields |
| `queue.consumer_failed` | Consumer or web listener raises an unexpected error | `operation`, `queue_name` when known, exception fields |
| `queue.publish_failed` | Publish raises an unexpected error or both recovery attempts fail | `queue_name`, `attempt`, `reason` (`retry_exhausted`), exception fields |
| `queue.forward_failed` | A processing item cannot be forwarded | `queue_name`, document ID, `reason` (`publish_failed`) |
| `queue.message_rejected` | OCR, naming, or upload receives an invalid item | `queue_name`, `reason`; exception fields when available |

Queue telemetry is limited to failures. Successful connections, consumption,
publishing, forwarding, recovered publish retries, and queue depth are not sent.
There is no background queue sampler or extra monitoring connection. Use
document/OCR/naming/upload events for document throughput and completion rates.

Internal Pika logs remain local: their low-level connection messages are not
forwarded as separate `service.error` events. The shared RabbitMQ client and web
listener report actionable structured failures instead. A failure already sent
as a specific queue or stage event is not sent again by the generic logging
handler. Unsupported OCR input remains `ocr.skipped`, not `service.error`.
Native Samba/RabbitMQ/Redis container logs are not forwarded; Python-side
errors interacting with those services are.

Successful HTTP events count page navigations, not every resource request.
Static assets, icons, SSE streams, JSON/API polling, AJAX/fetch requests,
HEAD/POST requests, redirects, and 304 responses do not produce success events.
`Sec-Fetch-Dest` must be `document` when present; requests without that header
use the HTML GET response as the fallback, unless marked `XMLHttpRequest`.
Health probes to `/health` are excluded from request timing and both HTTP events,
regardless of their response status. Other HTTP responses with status 400 or above
still produce `http.request_failed`, including failed asset and background
requests. No request URLs or headers are included in either event payload.

## Counting Rules And Limitations

- Count distinct `document_id` values per event, not all pipeline events. A
  grouped document with several identical source copies is one document;
  `document.received.targets` reports the number of source copies.
- Use `document.received`, not `document.detected`, as the document funnel's
  entry. Detection also sees internal files moved into the failed directory;
  metadata ignores those instead of counting them as another incoming scan.
- Count `ocr.completed` for searchable OCR output, `naming.completed` for AI
  naming, and `document.completed` for fully synchronized documents.
- Group naming successes by `provider` and `model`. Skips/fallbacks do not count
  as AI-named documents. A failed naming stage may still upload successfully.
- Use `upload.target_completed` for destination throughput, not document count.
  Partial success has successful target events but no `document.completed`.
  No destinations is a failed upload, not a successful synchronization.
- Count `http.request_completed` for successful page navigations. One normal
  page load is one event, regardless of its assets or SSE connection. Reloads
  count again; this is not a unique-visitor or human-user metric.
- `service.error`, stage failures, and request failures may describe the same
  incident. Do not sum them as independent failed documents. Use stage events
  for the funnel and general errors for debugging.
- Failed publication/forwarding from metadata, OCR, or naming marks the document
  failed and moves its source to the failed-documents folder. Metadata emits no
  completion event when the OCR handoff returns false. Successfully completed
  OCR/naming work remains distinguishable from a subsequent failed handoff.
- Upload status codes belong to the current request, never a previous chunk or
  upload attempt. A network failure without a response omits `status_code` even
  if a previous chunk received HTTP 202; its exception remains available in the
  corresponding `upload.request_failed` event.
- Delivery is best-effort. Restart, network outage, saturation, and RabbitMQ
  redelivery can cause missing or duplicate events. The analytics database is
  not an audit log. A success event means the relevant application call
  succeeded, not that RabbitMQ publisher confirms or analytics ingestion did.
- Completion rates should join received and completed IDs for the same cohort;
  dividing today's completions by today's arrivals is not a cohort rate.
- Total time starts when detection publishes the document group, after its
  existing duplicate-detection wait, and includes subsequent queue waits.
  It does not measure time inside the physical scanner. OCRmyPDF may preserve
  existing text layers; no per-page skipped-layer measurement is emitted.
- Existing upload functions return false for most HTTP/network failures rather
  than raising. Their existing retry policy is unchanged: `retries` counts
  actual scheduled retries only, and may be zero despite a failed request.
- `service.error` without an active exception has a code location but no
  exception traceback. Local log output is unchanged and remains local.

## SQL Examples

These PostgreSQL examples use the existing `events` table in maexbert-analytics
and assume the API key belongs to project `scansync`. Add Grafana time filters
and deployment/version filters as needed.

Incoming documents per installation (not per human user):

```sql
SELECT user_id, count(DISTINCT metadata->>'document_id') AS documents
FROM events
WHERE project = 'scansync' AND event_name = 'document.received'
  AND user_id IS NOT NULL
GROUP BY user_id;
```

Filter the queries below by `user_id` to compare installations. Older events
and events sent without access to the identity file have no installation ID.

Documents received, OCRed, AI-named and synchronized per day:

```sql
SELECT date_trunc('day', created_at) AS time, event_name,
       count(DISTINCT metadata->>'document_id') AS documents
FROM events
WHERE project = 'scansync'
  AND event_name IN ('document.received', 'ocr.completed',
                     'naming.completed', 'document.completed')
GROUP BY 1, 2 ORDER BY 1;
```

AI naming by provider and exact configured model:

```sql
SELECT metadata->>'provider' AS provider, metadata->>'model' AS model,
       count(DISTINCT metadata->>'document_id') AS documents
FROM events
WHERE project = 'scansync' AND event_name = 'naming.completed'
GROUP BY 1, 2;
```

OCR latency percentiles (also applicable to naming/upload stage durations):

```sql
SELECT percentile_cont(ARRAY[0.5, 0.95, 0.99])
       WITHIN GROUP (ORDER BY (metadata->>'duration_ms')::double precision) AS latency_ms
FROM events
WHERE project = 'scansync' AND event_name = 'ocr.completed';
```

Pipeline failures grouped by actual exception class or non-exception reason:

```sql
SELECT event_name,
       coalesce(metadata->>'error_type', metadata->>'reason',
                metadata->>'status', 'no_exception') AS failure,
       metadata->>'status_code' AS http_status,
       count(DISTINCT metadata->>'document_id') AS documents
FROM events
WHERE project = 'scansync'
  AND event_name IN ('metadata.failed', 'ocr.failed', 'naming.failed', 'upload.failed')
GROUP BY 1, 2, 3;
```
