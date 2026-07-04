"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  DatabaseZap,
  Loader2,
  Play,
  RefreshCw,
  Settings2,
  TriangleAlert,
} from "lucide-react";

type Scenario = {
  key: string;
  name: string;
  industry: string;
  description: string;
  product_signal: string;
  apps: number;
  endpoints: number;
  consumers: number;
};

type IngestResult = {
  requests: number;
  logs: number;
  spans: number;
  written_requests: number;
  written_logs: number;
  written_spans: number;
  scenarios: string[];
  apps: string[];
  seed: number;
  accelerator_backend: string;
  used_gpu: boolean;
  generated_at: string;
  mode: string;
};

interface SyntheticDataContentProps {
  projectSlug: string;
}

const COUNT_PRESETS = [1000, 5000, 25000];

export default function SyntheticDataContent({ projectSlug }: SyntheticDataContentProps) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [count, setCount] = useState(5000);
  const [days, setDays] = useState(14);
  const [seed, setSeed] = useState("");
  const [accelerator, setAccelerator] = useState<"auto" | "cpu" | "gpu">("auto");
  const [includeLogs, setIncludeLogs] = useState(true);
  const [includeSpans, setIncludeSpans] = useState(true);
  const [ensureApps, setEnsureApps] = useState(true);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<IngestResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`/api/projects/${projectSlug}/synthetic/scenarios`);
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error || "Failed to load scenarios");
        const items = Array.isArray(body.scenarios) ? body.scenarios : [];
        if (cancelled) return;
        setScenarios(items);
        setSelected((prev) => prev.length ? prev : items.slice(0, 2).map((item: Scenario) => item.key));
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load scenarios");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectSlug]);

  const selectedScenarios = useMemo(
    () => scenarios.filter((scenario) => selected.includes(scenario.key)),
    [scenarios, selected],
  );

  const toggleScenario = (key: string) => {
    setSelected((prev) => (
      prev.includes(key)
        ? prev.filter((item) => item !== key)
        : [...prev, key]
    ));
  };

  const runIngest = async () => {
    if (selected.length === 0 || running) return;
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch(`/api/projects/${projectSlug}/synthetic/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_keys: selected,
          count,
          days,
          seed: seed.trim() ? Number(seed) : null,
          accelerator,
          include_logs: includeLogs,
          include_spans: includeSpans,
          ensure_apps: ensureApps,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || "Synthetic ingest failed");
      setResult(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Synthetic ingest failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="synthetic-page">
      <div className="synthetic-header">
        <div>
          <h1 className="synthetic-title">Synthetic Data</h1>
          <p className="synthetic-subtitle">Generate local request, log, consumer, and trace data for this project.</p>
        </div>
        <Link href={`/projects/${projectSlug}/traffic`} className="settings-btn">
          <RefreshCw size={16} />
          Traffic
        </Link>
      </div>

      {error && (
        <div className="synthetic-alert synthetic-alert-error">
          <TriangleAlert size={16} />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="synthetic-loading">
          <Loader2 size={22} className="animate-spin" />
          <span>Loading scenarios...</span>
        </div>
      ) : (
        <div className="synthetic-layout">
          <section className="synthetic-main">
            <div className="synthetic-section-head">
              <div>
                <h2>Scenarios</h2>
                <p>{selected.length} selected</p>
              </div>
              <button
                type="button"
                className="settings-btn settings-btn-sm"
                onClick={() => setSelected(scenarios.map((scenario) => scenario.key))}
              >
                Select all
              </button>
            </div>

            <div className="synthetic-scenario-grid">
              {scenarios.map((scenario) => {
                const isSelected = selected.includes(scenario.key);
                return (
                  <button
                    key={scenario.key}
                    type="button"
                    className={`synthetic-scenario ${isSelected ? "synthetic-scenario-selected" : ""}`}
                    onClick={() => toggleScenario(scenario.key)}
                  >
                    <span className="synthetic-scenario-top">
                      <span className="synthetic-scenario-name">{scenario.name}</span>
                      <span className="synthetic-check">
                        {isSelected && <CheckCircle2 size={16} />}
                      </span>
                    </span>
                    <span className="synthetic-scenario-industry">{scenario.industry}</span>
                    <span className="synthetic-scenario-meta">
                      {scenario.apps} apps / {scenario.endpoints} endpoints / {scenario.consumers} consumers
                    </span>
                  </button>
                );
              })}
            </div>
          </section>

          <aside className="synthetic-panel">
            <div className="synthetic-panel-title">
              <Settings2 size={16} />
              Run
            </div>

            <label className="synthetic-field">
              <span>Events</span>
              <input
                type="number"
                min={1}
                max={50000}
                value={count}
                onChange={(event) => setCount(Math.max(1, Math.min(50000, Number(event.target.value) || 1)))}
              />
            </label>

            <div className="synthetic-presets">
              {COUNT_PRESETS.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={count === value ? "synthetic-preset synthetic-preset-active" : "synthetic-preset"}
                  onClick={() => setCount(value)}
                >
                  {value.toLocaleString()}
                </button>
              ))}
            </div>

            <label className="synthetic-field">
              <span>Days</span>
              <input
                type="number"
                min={1}
                max={365}
                value={days}
                onChange={(event) => setDays(Math.max(1, Math.min(365, Number(event.target.value) || 1)))}
              />
            </label>

            <label className="synthetic-field">
              <span>Accelerator</span>
              <select value={accelerator} onChange={(event) => setAccelerator(event.target.value as "auto" | "cpu" | "gpu")}>
                <option value="auto">Auto</option>
                <option value="cpu">CPU</option>
                <option value="gpu">GPU</option>
              </select>
            </label>

            <label className="synthetic-field">
              <span>Seed</span>
              <input
                type="number"
                value={seed}
                placeholder="Rotating"
                onChange={(event) => setSeed(event.target.value)}
              />
            </label>

            <label className="synthetic-toggle">
              <input type="checkbox" checked={ensureApps} onChange={(event) => setEnsureApps(event.target.checked)} />
              <span>Create scenario apps</span>
            </label>
            <label className="synthetic-toggle">
              <input type="checkbox" checked={includeLogs} onChange={(event) => setIncludeLogs(event.target.checked)} />
              <span>Logs</span>
            </label>
            <label className="synthetic-toggle">
              <input type="checkbox" checked={includeSpans} onChange={(event) => setIncludeSpans(event.target.checked)} />
              <span>Traces</span>
            </label>

            <button
              type="button"
              className="settings-btn settings-btn-primary synthetic-run"
              disabled={running || selected.length === 0}
              onClick={runIngest}
            >
              {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {running ? "Generating..." : "Generate data"}
            </button>
          </aside>
        </div>
      )}

      {result && (
        <section className="synthetic-result">
          <div className="synthetic-result-head">
            <DatabaseZap size={18} />
            <div>
              <h2>Data written</h2>
              <p>{result.mode} / {result.accelerator_backend} / seed {result.seed}</p>
            </div>
          </div>
          <div className="synthetic-result-grid">
            <div><span>{result.written_requests.toLocaleString()}</span><label>Requests</label></div>
            <div><span>{result.written_logs.toLocaleString()}</span><label>Logs</label></div>
            <div><span>{result.written_spans.toLocaleString()}</span><label>Spans</label></div>
            <div><span>{result.apps.length.toLocaleString()}</span><label>Apps</label></div>
          </div>
          <div className="synthetic-result-actions">
            <Link href={`/projects/${projectSlug}/traffic`} className="settings-btn settings-btn-primary">Open Traffic</Link>
            <Link href={`/projects/${projectSlug}/endpoints`} className="settings-btn">Open Request logs</Link>
            <Link href={`/projects/${projectSlug}/consumers`} className="settings-btn">Open Consumers</Link>
          </div>
        </section>
      )}

      {!loading && selectedScenarios.length > 0 && (
        <div className="synthetic-selection">
          <span>Selected</span>
          <strong>{selectedScenarios.map((scenario) => scenario.name).join(", ")}</strong>
        </div>
      )}
    </div>
  );
}
