import { useEffect, useState } from "react";
import {
  fetchOverview,
  fetchParticipantResults,
  fetchParticipantTrend,
  type Overview,
  type ParticipantResults,
  type SessionTrendEntry,
} from "../../api/analysis";
import { GenerationTab } from "./GenerationTab";
import { MatrixTab } from "./MatrixTab";
import { OutcomesTab } from "./OutcomesTab";
import { OverheadTab } from "./OverheadTab";
import { TrendTab } from "./TrendTab";

export type DashboardTab = "outcomes" | "trend" | "matrix" | "generation" | "overhead";

export interface DashboardPageProps {
  readonly initialParticipantId?: string;
  readonly initialTab?: string;
  readonly fetchImpl?: typeof fetch;
}

interface OutcomesState {
  readonly status: "loading" | "ok" | "not-done" | "not-found" | "error";
  readonly results: ParticipantResults | null;
  readonly message?: string;
}

export function DashboardPage({
  initialParticipantId,
  initialTab,
  fetchImpl = fetch,
}: DashboardPageProps): React.JSX.Element {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<DashboardTab>(() => {
    const validTabs: DashboardTab[] = ["outcomes", "trend", "matrix", "generation", "overhead"];
    return validTabs.includes(initialTab as DashboardTab)
      ? (initialTab as DashboardTab)
      : "outcomes";
  });

  const [selectedParticipantId, setSelectedParticipantId] = useState<string>(
    initialParticipantId ?? "",
  );

  const [outcomesState, setOutcomesState] = useState<OutcomesState>({
    status: "loading",
    results: null,
  });

  const [trend, setTrend] = useState<readonly SessionTrendEntry[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);

  // Sync with initial props if they change
  useEffect(() => {
    if (initialTab) {
      const validTabs: DashboardTab[] = ["outcomes", "trend", "matrix", "generation", "overhead"];
      if (validTabs.includes(initialTab as DashboardTab)) {
        setActiveTab(initialTab as DashboardTab);
      }
    }
  }, [initialTab]);

  useEffect(() => {
    if (initialParticipantId) {
      setSelectedParticipantId(initialParticipantId);
    }
  }, [initialParticipantId]);

  // Load study-wide overview on mount
  useEffect(() => {
    let cancelled = false;
    setOverviewLoading(true);
    setOverviewError(null);

    fetchOverview(fetchImpl).then((res) => {
      if (cancelled) return;
      setOverviewLoading(false);
      if (res.status === "ok") {
        setOverview(res.overview);
        // If no participant was explicitly selected yet, select the first participant
        const firstParticipant = res.overview.participants[0];
        if (!initialParticipantId && firstParticipant) {
          setSelectedParticipantId(firstParticipant.id);
        }
      } else {
        setOverviewError(res.message);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [fetchImpl, initialParticipantId]);

  // Update hash when participant or tab changes
  const updateRoute = (newPid: string, newTab: DashboardTab) => {
    const params = new URLSearchParams();
    if (newPid) params.set("participant", newPid);
    if (newTab !== "outcomes") params.set("tab", newTab);
    const search = params.toString() ? `?${params.toString()}` : "";
    window.location.hash = `#/dashboard${search}`;
  };

  const handleParticipantChange = (newPid: string) => {
    setSelectedParticipantId(newPid);
    updateRoute(newPid, activeTab);
  };

  const handleTabChange = (newTab: DashboardTab) => {
    setActiveTab(newTab);
    updateRoute(selectedParticipantId, newTab);
  };

  // Fetch participant-specific outcomes & trend whenever selectedParticipantId changes
  useEffect(() => {
    if (!selectedParticipantId) {
      setOutcomesState({ status: "not-found", results: null });
      setTrend([]);
      return;
    }

    let cancelled = false;
    setOutcomesState({ status: "loading", results: null });
    setTrendLoading(true);

    fetchParticipantResults(selectedParticipantId, fetchImpl).then((res) => {
      if (cancelled) return;
      if (res.status === "ok") {
        setOutcomesState({ status: "ok", results: res.results });
      } else if (res.status === "not-done") {
        setOutcomesState({ status: "not-done", results: null, message: res.message });
      } else if (res.status === "not-found") {
        setOutcomesState({ status: "not-found", results: null });
      } else {
        setOutcomesState({ status: "error", results: null, message: res.message });
      }
    });

    fetchParticipantTrend(selectedParticipantId, fetchImpl).then((res) => {
      if (cancelled) return;
      setTrendLoading(false);
      if (res.status === "ok") {
        setTrend(res.trend);
      } else {
        setTrend([]);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [selectedParticipantId, fetchImpl]);

  if (overviewLoading) {
    return (
      <div className="p-8 max-w-6xl mx-auto text-center text-gray-500 animate-pulse">
        Loading analytical dashboard...
      </div>
    );
  }

  if (overviewError) {
    return (
      <div className="p-8 max-w-6xl mx-auto">
        <div className="p-4 bg-red-50 border border-red-200 rounded text-red-800">
          Error loading dashboard overview: {overviewError}
        </div>
      </div>
    );
  }

  const participants = overview?.participants ?? [];
  const currentParticipant = participants.find((p) => p.id === selectedParticipantId);

  // Completed sessions for the matrix tab (extracted from trend)
  const completedSessions = trend.map((s) => ({
    id: s.session_id,
    phase: s.phase,
    day_index: s.day_index,
  }));

  return (
    <div className="px-6 py-8 max-w-6xl mx-auto space-y-6">
      {/* Top Header: Title & Participant Selector */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-[#EAEAEA] pb-5">
        <div>
          <h1 className="text-2xl font-semibold text-[#111111]">Analysis Dashboard</h1>
          <p className="text-xs text-[#666560] mt-1">
            Pre-registered Bayesian Beta posteriors, bootstrap IKI intervals, and operational
            metrics.
          </p>
        </div>

        {participants.length > 0 ? (
          <div className="flex items-center gap-3">
            <label
              htmlFor="dashboard-participant-select"
              className="text-xs font-medium text-[#666560] shrink-0"
            >
              Participant:
            </label>
            <select
              id="dashboard-participant-select"
              aria-label="Participant selector"
              value={selectedParticipantId}
              onChange={(e) => handleParticipantChange(e.target.value)}
              className="text-xs border border-[#D9D7D0] rounded-lg px-3 py-1.5 bg-white text-[#111111] focus:outline-none focus:border-[#111111] font-mono"
            >
              {participants.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.alias} ({p.status}){p.is_builder ? " [Builder]" : ""}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div className="text-xs text-[#666560]">No participants enrolled yet.</div>
        )}
      </div>

      {/* Active Participant Info Banner */}
      {currentParticipant && (
        <div className="typist-card p-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="text-sm font-semibold text-[#111111]">{currentParticipant.alias}</div>
            <span className="inline-block px-2 py-0.5 rounded-md border border-[#E4E2DC] text-[11px] uppercase font-medium bg-[#F3F2EE] text-[#4A4945]">
              Status: {currentParticipant.status}
            </span>
            <span
              className={`inline-block px-2 py-0.5 rounded-md border text-[11px] font-medium ${
                currentParticipant.is_builder
                  ? "bg-[#F3F2EE] text-[#4A4945] border-[#E4E2DC]"
                  : "bg-[#EBF3FA] text-[#1F5E8B] border-[#CEE2F4]"
              }`}
            >
              {currentParticipant.is_builder ? "Builder (Unblinded)" : "Peer (Blinded)"}
            </span>
          </div>
          <div className="text-xs text-[#666560] font-mono tabular-nums">
            {currentParticipant.completed_sessions} completed session(s)
          </div>
        </div>
      )}

      {/* Tabs Navigation */}
      <div className="border-b border-[#EAEAEA]">
        <nav className="flex flex-wrap gap-6" aria-label="Dashboard Tabs">
          <button
            type="button"
            onClick={() => handleTabChange("outcomes")}
            className={`py-2.5 px-0.5 border-b-2 text-xs font-medium typist-fluid ${
              activeTab === "outcomes"
                ? "border-[#111111] text-[#111111]"
                : "border-transparent text-[#666560] hover:text-[#111111]"
            }`}
          >
            Outcomes &amp; Timing
          </button>
          <button
            type="button"
            onClick={() => handleTabChange("trend")}
            className={`py-2.5 px-0.5 border-b-2 text-xs font-medium typist-fluid ${
              activeTab === "trend"
                ? "border-[#111111] text-[#111111]"
                : "border-transparent text-[#666560] hover:text-[#111111]"
            }`}
          >
            Session Trend
          </button>
          <button
            type="button"
            onClick={() => handleTabChange("matrix")}
            className={`py-2.5 px-0.5 border-b-2 text-xs font-medium typist-fluid ${
              activeTab === "matrix"
                ? "border-[#111111] text-[#111111]"
                : "border-transparent text-[#666560] hover:text-[#111111]"
            }`}
          >
            Bigram Matrix
          </button>
          <button
            type="button"
            onClick={() => handleTabChange("generation")}
            className={`py-2.5 px-0.5 border-b-2 text-xs font-medium typist-fluid ${
              activeTab === "generation"
                ? "border-[#111111] text-[#111111]"
                : "border-transparent text-[#666560] hover:text-[#111111]"
            }`}
          >
            Drill Generation
          </button>
          <button
            type="button"
            onClick={() => handleTabChange("overhead")}
            className={`py-2.5 px-0.5 border-b-2 text-xs font-medium typist-fluid ${
              activeTab === "overhead"
                ? "border-[#111111] text-[#111111]"
                : "border-transparent text-[#666560] hover:text-[#111111]"
            }`}
          >
            Telemetry Overhead
          </button>
        </nav>
      </div>

      {/* Tab Panels */}
      <div>
        {activeTab === "outcomes" && (
          <OutcomesTab results={outcomesState.results} loadState={outcomesState} />
        )}
        {activeTab === "trend" && <TrendTab trend={trend} loading={trendLoading} />}
        {activeTab === "matrix" && <MatrixTab sessions={completedSessions} fetchImpl={fetchImpl} />}
        {activeTab === "generation" && <GenerationTab generation={overview?.generation ?? null} />}
        {activeTab === "overhead" && <OverheadTab overhead={overview?.overhead ?? null} />}
      </div>
    </div>
  );
}
