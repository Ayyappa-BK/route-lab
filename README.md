# Route Lab

An inference reliability sandbox with two local providers, failure injection, a circuit breaker, and a trace ledger. The dashboard makes routing and recovery behavior visible without needing cloud accounts.

## Run locally

Use Python 3.11+ and Node.js 24 with npm. Python has no third-party dependencies. From the cloned repository root:

```sh
cd frontend
npm ci
npm run build
cd ..
python3 backend/server.py
```

Open http://localhost:8314. On Windows, use `py` in place of `python3`. The Python server serves both the compiled React app and the REST API. No API keys, downloaded model weights, or paid services are needed. The first npm install requires internet access.

For frontend development, keep the Python server running and use a second terminal:

```sh
cd frontend
npm run dev
```

Vite runs at http://localhost:8414 and proxies `/api` to the Python server. Set `PORT` to change the backend port; update `frontend/vite.config.ts` if you also use the development proxy. The backend binds to localhost by default.

## Try it

1. Send a healthy request and check its route and latency.
2. Set primary failures to 100%, apply the controls, and run 12 requests.
3. The first three primary attempts fail and fall back. The circuit then opens, sending later requests directly to the fallback.
4. Restore failures to 0%, apply, wait three seconds, and send a request. A successful half-open probe closes the circuit.

The burst button sends 12 sequential requests so the state transitions are readable. The API also supports concurrent callers, with eight admission slots.

## How it works

`backend/domain.py` owns admission control, provider calls, circuit state, and metrics. Both providers execute a small lexicon sentiment classifier; they simulate a service boundary, not a remote model deployment. Primary failures and latency are configurable; the fallback uses a fixed 8 ms delay.

Three consecutive primary failures open the circuit. After a three-second cooldown, exactly one request may probe the primary. Other callers use fallback while the probe is in flight. A failed probe reopens the circuit; a successful probe closes it. There are no retries, so a failed primary adds at most one fallback call.

A lock protects circuit state and the rolling 200-request ledger; provider work occurs outside it. A bounded semaphore rejects callers when eight requests are already active. The p95 uses the nearest-rank statistic over completed requests. The fallback share includes both failed primary attempts and calls that skip an open circuit.

Metrics and configuration reset on restart. The dashboard refreshes after each action or through the Refresh button; it does not stream other callers' events. Trace IDs identify local requests. They are not distributed OpenTelemetry traces.

The frontend is React and TypeScript; Vite builds static assets. The Python standard-library HTTP server validates JSON requests, limits payloads to 2 MB, and emits request-duration logs. Errors appear inline in the interface. React renders user text as text rather than HTML.

## API

`GET /api/health` returns a liveness check. `GET /api/state` returns the current dashboard state.

```text
POST /api/configure
{"failure_rate":1,"latency_ms":100}

POST /api/infer
{"text":"The sync is fast and great"}
```

POST endpoints expect `Content-Type: application/json`. Invalid inputs return HTTP 400 with an `error` field. Oversized requests return 413. These endpoints have no authentication and are intended for local use; the standard-library server is not a production ingress server.

## Checks

```sh
python3 -m unittest discover -s backend -p 'test_*.py' -v
cd frontend
npm ci
npm run build
```

Tests exercise domain behavior and HTTP validation. The frontend build includes strict TypeScript checking. GitHub Actions runs both on pushes and pull requests.

## Docker

```sh
docker build -t route-lab .
docker run --rm -p 127.0.0.1:8314:8314 route-lab
```

The image builds the frontend and serves it from Python under a non-root user. Docker is optional.

## Platform engineering focus

This project covers inference endpoints, reliability controls, failure drills, and observability surfaces. A remote provider adapter, request deadlines, and exported telemetry are useful follow-up work.

## Layout

```text
backend/                 API server, domain logic, and tests
frontend/src/            React interface and styles
frontend/package-lock.json  Reproducible dependency installation
data/                    Bundled fixtures
.github/workflows/       Build and test checks
```

MIT licensed. See `LICENSE`.
