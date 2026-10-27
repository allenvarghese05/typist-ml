import { useCallback, useEffect, useState } from "react";
import {
  assignParticipant,
  type ChecksResponse,
  createJob,
  createParticipant,
  fetchChecks,
  fetchHealth,
  fetchJobs,
  fetchParticipants,
  fetchPoolStatus,
  type HealthResponse,
  type JobResponse,
  type ParticipantResponse,
  type PoolResponse,
  replenishPool,
} from "../../api/client";
import { DataChecks } from "./DataChecks";
import { JobsTable } from "./JobsTable";
import { ParticipantList } from "./ParticipantList";
import { PoolStatus } from "./PoolStatus";

export interface AdminPageProps {
  readonly initialParticipantId?: string;
  readonly fetchImpl?: typeof fetch;
}

type Tab = "pool" | "jobs" | "checks";

export function AdminPage({
  initialParticipantId,
  fetchImpl = fetch,
}: AdminPageProps): React.JSX.Element {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [participants, setParticipants] = useState<readonly ParticipantResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialParticipantId ?? null);
  const [activeTab, setActiveTab] = useState<Tab>("pool");
  const [pool, setPool] = useState<PoolResponse | null>(null);
  const [jobs, setJobs] = useState<readonly JobResponse[]>([]);
  const [checks, setChecks] = useState<ChecksResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load health & participants on mount
  const loadInitial = useCallback(async () => {
    try {
      const [h, parts] = await Promise.all([
        fetchHealth(fetchImpl).catch(() => null),
        fetchParticipants(fetchImpl),
      ]);
      setHealth(h);
      setParticipants(parts);
      if (parts.length > 0) {
        setSelectedId((current) => {
          if (current && parts.some((p) => p.id === current)) {
            return current;
          }
          if (initialParticipantId && parts.some((p) => p.id === initialParticipantId)) {
            return initialParticipantId;
          }
          return parts[0]?.id ?? null;
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [fetchImpl, initialParticipantId]);

  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

  // Load details for selected participant
  const loadParticipantData = useCallback(
    async (pid: string) => {
      try {
        setError(null);
        const [poolRes, jobsRes, checksRes] = await Promise.all([
          fetchPoolStatus(pid, fetchImpl).then((res) => res[0] ?? null),
          fetchJobs({ participant_id: pid }, fetchImpl),
          fetchChecks(pid, fetchImpl).catch(() => null),
        ]);
        setPool(poolRes);
        setJobs(jobsRes);
        setChecks(checksRes);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [fetchImpl],
  );

  useEffect(() => {
    if (selectedId) {
      void loadParticipantData(selectedId);
    } else {
      setPool(null);
      setJobs([]);
      setChecks(null);
    }
  }, [selectedId, loadParticipantData]);

  const handleSelectParticipant = (pid: string) => {
    setSelectedId(pid);
    window.location.hash = `#/admin?participant=${encodeURIComponent(pid)}`;
  };

  const handleCreateParticipant = async (alias: string, isBuilder: boolean) => {
    try {
      setError(null);
      const newPart = await createParticipant(alias, isBuilder, fetchImpl);
      const updated = await fetchParticipants(fetchImpl);
      setParticipants(updated);
      handleSelectParticipant(newPart.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleAssignParticipant = async (pid: string) => {
    try {
      setError(null);
      await assignParticipant(pid, fetchImpl);
      const updated = await fetchParticipants(fetchImpl);
      setParticipants(updated);
      await loadParticipantData(pid);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleReplenishPool = async () => {
    if (!selectedId) return;
    try {
      setError(null);
      await replenishPool(selectedId, fetchImpl);
      await loadParticipantData(selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleEnqueueDrills = async (arm: string, requested: number) => {
    if (!selectedId) return;
    try {
      setError(null);
      await createJob({ participant_id: selectedId, arm, requested }, fetchImpl);
      await loadParticipantData(selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleRefreshJobs = async () => {
    if (!selectedId) return;
    try {
      setError(null);
      const updatedJobs = await fetchJobs({ participant_id: selectedId }, fetchImpl);
      setJobs(updatedJobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleRetryJob = async (job: JobResponse) => {
    if (!selectedId) return;
    await handleEnqueueDrills(job.arm, job.requested);
  };

  // Worker badge styling
  let workerBadgeText = "Worker Inactive";
  let workerBadgeColor = "bg-red-100 text-red-800 border-red-200";
  if (health?.worker) {
    const age = health.worker.heartbeat_age_s;
    const ageText = age !== null ? `${Math.round(age)}s ago` : "unknown";
    if (health.worker.status === "ok") {
      workerBadgeText = `Worker Active (heartbeat ${ageText})`;
      workerBadgeColor = "bg-green-100 text-green-800 border-green-200";
    } else if (health.worker.status === "stale") {
      workerBadgeText = `Worker Stale (heartbeat ${ageText})`;
      workerBadgeColor = "bg-yellow-100 text-yellow-800 border-yellow-200";
    }
  }

  const selectedParticipant = participants.find((p) => p.id === selectedId);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col" data-testid="admin-page">
      {/* Top Banner with Health Status */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex flex-wrap justify-between items-center gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Typist-ML Pilot Command Centre</h1>
          <p className="text-xs text-gray-500">
            Participant management, drill pool replenishment, worker monitor & data auditing
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span
            className={`px-3 py-1 text-xs font-semibold rounded-full border ${workerBadgeColor}`}
            data-testid="worker-status-badge"
          >
            {workerBadgeText}
          </span>
        </div>
      </header>

      {/* Global Error Alert */}
      {error && (
        <div
          className="mx-6 mt-4 p-4 bg-red-50 border border-red-200 text-red-800 rounded-lg text-sm flex justify-between items-center"
          data-testid="admin-error-banner"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-xs font-semibold text-red-600 hover:text-red-900 ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Workspace Layout */}
      <main className="flex-1 p-6 flex flex-col md:flex-row gap-6">
        {/* Left Column: Participant Selector */}
        <aside className="w-full md:w-80 shrink-0">
          <ParticipantList
            participants={participants}
            selectedId={selectedId}
            onSelect={handleSelectParticipant}
            onCreate={handleCreateParticipant}
            onAssign={handleAssignParticipant}
          />
        </aside>

        {/* Right Column: Tab Panels */}
        <section className="flex-1 flex flex-col gap-4">
          {selectedParticipant ? (
            <>
              {/* Tab Navigation */}
              <div className="flex border-b border-gray-200 bg-white px-4 rounded-t-lg">
                <button
                  type="button"
                  onClick={() => setActiveTab("pool")}
                  className={`py-3 px-4 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === "pool"
                      ? "border-blue-600 text-blue-600"
                      : "border-transparent text-gray-500 hover:text-gray-700"
                  }`}
                  data-testid="tab-pool"
                >
                  Drill Pool Buffer
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("jobs")}
                  className={`py-3 px-4 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === "jobs"
                      ? "border-blue-600 text-blue-600"
                      : "border-transparent text-gray-500 hover:text-gray-700"
                  }`}
                  data-testid="tab-jobs"
                >
                  Generation Jobs ({jobs.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("checks")}
                  className={`py-3 px-4 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === "checks"
                      ? "border-blue-600 text-blue-600"
                      : "border-transparent text-gray-500 hover:text-gray-700"
                  }`}
                  data-testid="tab-checks"
                >
                  Data Quality & Trends
                </button>
              </div>

              {/* Tab Contents */}
              <div>
                {activeTab === "pool" && (
                  <PoolStatus
                    pool={pool}
                    onReplenish={handleReplenishPool}
                    onEnqueue={handleEnqueueDrills}
                  />
                )}
                {activeTab === "jobs" && (
                  <JobsTable jobs={jobs} onRefresh={handleRefreshJobs} onRetry={handleRetryJob} />
                )}
                {activeTab === "checks" && <DataChecks checksResponse={checks} />}
              </div>
            </>
          ) : (
            <div className="p-12 text-center bg-white border border-gray-200 rounded-lg text-gray-500">
              Select or enroll a participant to manage drill pools and inspect data checks.
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
