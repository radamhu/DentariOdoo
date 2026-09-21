# Application HTTP availability

[Open the dashboard](https://adaminfo.grafana.net/d/application-http-availability/application-http-availability)

Synthetic Monitoring is initialized and all four checks are enabled. The dashboard
has separate, permanently titled **Production** and **Development** rows and
refreshes every 30 seconds. Its Prometheus data source is `grafanacloud-prom`;
the Synthetic Monitoring data source is `ffywrs39f2fwga`.

| Application | Environment | Check ID | URL |
| --- | --- | --- | --- |
| Dentari | Production | 90691 | https://dentari-prod-3040.apps.oec.sh/ |
| Adaminfo | Production | 90692 | https://adaminfo-prod-1240.apps.oec.sh/ |
| Dentari | Development | 90693 | https://dentari-dev-8780.apps.oec.sh/ |
| Adaminfo | Development | 90694 | https://adaminfo-dev-7360.apps.oec.sh/ |

## Check schedule and quota

Each URL is checked with HTTP GET every **5 minutes**, from **London (1)** and
**Frankfurt (14)**, with a 10-second timeout. Checks follow redirects and require
a final 2xx response and a valid TLS certificate. Each carries `app` and
`environment` labels.

Grafana rejected the original one-minute schedule with an execution-quota error:
100,000 maximum executions. Four URLs from two locations would require about
345,600 executions per 30 days. The deployed five-minute schedule requires about
69,120, retaining both probe locations within the current quota.

## Dashboard behavior

Each environment contains application status cards, last-result timestamps,
24-hour/7-day successful-check percentages, availability history, response times,
and HTTP response codes by probe.

- **UP:** both probes succeed.
- **DEGRADED:** one succeeds and one fails.
- **DOWN:** both fail.
- **UNKNOWN:** either probe has no result within the last 15 minutes.

The 15-minute window allows three scheduled intervals before results expire.
Queries retain samples across Prometheus's default lookback boundary and select
the latest configuration series for each probe. First results may take one check
interval. Last-result timestamps show the most recent result from either probe.

Percentages describe collected successful samples. Missing samples are excluded,
so they are not guaranteed wall-clock uptime percentages. New checks need time
to build a full 24-hour/7-day history. HTTP reachability does not verify every
internal application function.

Panel queries select explicit jobs and URLs, so Production and Development stay
separate even when labels change. Live metrics currently include `app` and
`environment` directly; no custom-label join is needed for these fixed panels.

## Saved configuration and validation

- `application-http-availability.json`: published dashboard, version 2.
- `http-checks.configured.json`: API responses for the four configured checks,
  including check and probe IDs.
- `http-checks.template.json`: reusable check payloads; add probe IDs before use.

Verified the saved check settings, read back the published dashboard, and executed
all 24 distinct PromQL expressions against the live metrics backend. Synthetic
query fixtures validated UP, DEGRADED, DOWN, missing-probe, and no-data states.
Evaluation 16 minutes beyond available samples verified UNKNOWN for every status
card without changing any application. Browser rendering was not inspected.

Live verification on 2026-09-21 at 09:19 UTC confirmed **UP** for all four
application/environment cards, with successful results from London and Frankfurt.

## Discord notifications

Contact point: **Application HTTP — Discord** (`app-http-discord`). The webhook
is stored in Grafana's protected contact-point settings, not in repository files.
Grafana successfully sent a labeled setup test through its current notification
API on 2026-09-21.

Four Grafana-managed rules live in **Application Monitoring / HTTP availability**.
Each evaluates its dashboard status query every minute and fires when the value
is **below 2 for one minute**: DOWN (0), DEGRADED (1), or UNKNOWN (-1).
Query errors and no-data conditions also use the Alerting state. The five-minute
probe schedule and 15-minute data-expiry window still apply; the one-minute
pending period is not a promise of one-minute outage detection.

Notifications include application, environment, URL, and a dashboard link.
Recovery notifications are enabled. The scoped route matches only
`notification_scope=application-http`; existing default routing is preserved.
It waits 30 seconds before an initial notification, groups by alert name,
application and environment, processes group changes every five minutes, and
repeats ongoing alerts every four hours.

Saved non-secret definitions:

- `http-alert-rules.json`: four rule definitions and threshold expressions.
- `discord-notification-route.json`: scoped Discord notification route.

Contact-point configuration, all four rules, evaluation interval and routing
were read back and verified. The Discord test returned `status: success`.
