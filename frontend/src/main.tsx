import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
interface Trace {
  trace: string;
  route: "primary" | "fallback";
  primary_failed: boolean;
  latency_ms: number;
  label: string;
  time: number;
}
interface Result extends Trace {
  model: string;
  breaker: string;
}
interface Dashboard {
  config: {
    failure_rate: number;
    latency_ms: number;
    cooldown_seconds: number;
  };
  breaker: { state: string; failures: number };
  events: Trace[];
  metrics: {
    requests: number;
    fallback_rate: number;
    primary_failures: number;
    p95_ms: number;
  };
}
type Api = { state: Dashboard; infer: Result; configure: Dashboard };
type Action = Exclude<keyof Api, "state">;
async function api<K extends keyof Api>(
  path: K,
  body?: Record<string, unknown>,
): Promise<Api[K]> {
  const response = await fetch(
    `/api/${path}`,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : undefined,
  );
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "Request failed");
  return value;
}
function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="stat">
      <b>{value}</b>
      <span>{label}</span>
    </div>
  );
}
function App() {
  const [state, setState] = useState<Partial<Dashboard>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api("state")
      .then(setState)
      .catch((e) => setError(e.message));
  }, []);
  async function run(path: Action, body: Record<string, unknown>) {
    setBusy(true);
    setError("");
    try {
      const data = await api(path, body);
      setResult(path === "infer" ? (data as Result) : null);
      setState(await api("state"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  const [text, setText] = useState(
    "The sync is fast and the experience is great.",
  );
  const [failure, setFailure] = useState(0);
  const [latency, setLatency] = useState(35);
  async function burst() {
    setBusy(true);
    setError("");
    try {
      for (let i = 0; i < 12; i++) {
        setResult(await api("infer", { text }));
        setState(await api("state"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  const events = state.events || [];
  const max = Math.max(1, ...events.map((e) => e.latency_ms));
  const points = events
    .map(
      (e, i: number) =>
        `${(i * 600) / Math.max(1, events.length - 1)},${95 - (e.latency_ms / max) * 85}`,
    )
    .join(" ");
  return (
    <>
      <header>
        <strong>Route Lab</strong>
        <span>Inference reliability / failure drill</span>
      </header>
      <main>
        <div className="eyebrow">Route · observe · recover</div>
        <h1>Make the failure visible.</h1>
        <p>
          Two local inference providers, a bounded request window, and a circuit
          breaker you can stress on demand.
        </p>
        <div className="stats">
          <Stat
            value={state.breaker?.state || "closed"}
            label="Primary circuit breaker"
          />
          <Stat
            value={`${state.metrics?.p95_ms || 0} ms`}
            label="p95 end-to-end latency"
          />
          <Stat
            value={`${((state.metrics?.fallback_rate || 0) * 100).toFixed(0)}%`}
            label="Fallback share of recent requests"
          />
        </div>
        <div className="grid">
          <section className="panel">
            <h2>Failure controls</h2>
            <label htmlFor="failure">
              Primary failure probability: {(failure * 100).toFixed(0)}%
            </label>
            <input
              id="failure"
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={failure}
              onChange={(e) => setFailure(Number(e.target.value))}
            />
            <label htmlFor="latency">Primary latency: {latency} ms</label>
            <input
              id="latency"
              type="range"
              min="0"
              max="500"
              step="5"
              value={latency}
              onChange={(e) => setLatency(Number(e.target.value))}
            />
            <div className="row">
              <button
                disabled={busy}
                onClick={() =>
                  void run("configure", {
                    failure_rate: failure,
                    latency_ms: latency,
                  })
                }
              >
                Apply controls
              </button>
            </div>
            <p>
              Active: {((state.config?.failure_rate || 0) * 100).toFixed(0)}%
              failures · {state.config?.latency_ms ?? 35} ms delay
            </p>
            <label htmlFor="text">Inference text</label>
            <input
              id="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={5000}
            />
            <div className="row">
              <button
                disabled={busy}
                onClick={() => void run("infer", { text })}
              >
                Send request
              </button>
              <button
                disabled={busy}
                className="secondary"
                onClick={() => void burst()}
              >
                {busy ? "Working…" : "Run 12 requests"}
              </button>
              <button
                disabled={busy}
                className="secondary"
                onClick={() =>
                  api("state")
                    .then(setState)
                    .catch((e) => setError(e.message))
                }
              >
                Refresh
              </button>
            </div>
            <p>
              Set failures to 100%, apply, then run a burst. Restore 0%, wait
              three seconds, and send a recovery probe.
            </p>
            {result?.trace && (
              <div className="passage">
                <span className="badge">
                  {result.route} · {result.trace}
                </span>
                <p>
                  {result.label} · {result.latency_ms} ms · {result.breaker}
                </p>
              </div>
            )}
          </section>
          <section className="panel">
            <h2>Request latency</h2>
            <svg
              viewBox="0 0 600 100"
              role="img"
              aria-label="Recent request latency, normalized to maximum"
            >
              <polyline
                points={points}
                fill="none"
                stroke="var(--accent)"
                strokeWidth="2"
              />
            </svg>
            <p>
              {state.metrics?.requests || 0} requests in the window ·{" "}
              {state.metrics?.primary_failures || 0} primary failures · chart
              max {max.toFixed(0)} ms
            </p>
            <h2>Trace ledger</h2>
            <table>
              <thead>
                <tr>
                  <th>Trace</th>
                  <th>Route</th>
                  <th>Latency</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {[...events]
                  .reverse()
                  .slice(0, 15)
                  .map((e) => (
                    <tr key={e.trace}>
                      <td>
                        <code>{e.trace.slice(0, 8)}</code>
                      </td>
                      <td>
                        {e.route}
                        {e.primary_failed ? " ↳ failed" : ""}
                      </td>
                      <td>{e.latency_ms} ms</td>
                      <td>{e.label}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </section>
        </div>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <footer>
          200-request window · 8 concurrent slots · opens after 3 failures ·
          single recovery probe
        </footer>
      </main>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
