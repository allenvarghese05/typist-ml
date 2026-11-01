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
  let workerBadgeColor = "bg-[#FDEBEB] text-[#9F2F2D] border-[#F5D0D2]";
  if (health?.worker) {
    const age = health.worker.heartbeat_age_s;
    const ageText = age !== null ? `${Math.round(age)}s ago` : "unknown";
    if (health.worker.status === "ok") {
      workerBadgeText = `Worker Active (heartbeat ${ageText})`;
      workerBadgeColor = "bg-[#EDF3EC] text-[#2B5930] border-[#D7E6D5]";
    } else if (health.worker.status === "stale") {
      workerBadgeText = `Worker Stale (heartbeat ${ageText})`;
      workerBadgeColor = "bg-[#FBF3DB] text-[#8A5A00] border-[#EFE0B4]";
    }
  }

  const selectedParticipant = participants.find((p) => p.id === selectedId);

  return (
    <div className="min-h-screen bg-[#FBFBFA] flex flex-col" data-testid="admin-page">
      {/* Top Banner with Health Status */}
      <div className="mx-auto w-full max-w-6xl px-6 pt-8 pb-5 border-b border-[#EAEAEA] flex flex-wrap justify-between items-end gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[#111111]">Typist-ML Pilot Command Centre</h1>
          <p className="text-xs text-[#666560] mt-1">
            Participant management, drill pool replenishment, worker monitor &amp; data auditing
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span
            className={`px-2.5 py-1 text-xs font-medium rounded-md border font-mono ${workerBadgeColor}`}
            data-testid="worker-status-badge"
          >
            {workerBadgeText}
          </span>
        </div>
      </div>

      {/* Global Error Alert */}
      {error && (
        <div className="mx-auto w-full max-w-6xl px-6 mt-4">
          <div
            className="p-4 bg-[#FDEBEB] border border-[#F5D0D2] text-[#9F2F2D] rounded-lg text-xs flex justify-between items-center"
            data-testid="admin-error-banner"
          >
            <span>{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-xs font-semibold text-[#9F2F2D] underline ml-4"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Main Workspace Layout */}
      <div className="mx-auto w-full max-w-6xl flex-1 px-6 py-6 flex flex-col md:flex-row gap-6">
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
              <div className="flex gap-6 border-b border-[#EAEAEA]">
                <button
                  type="button"
                  onClick={() => setActiveTab("pool")}
                  className={`py-2.5 px-0.5 text-xs font-medium border-b-2 typist-fluid ${
                    activeTab === "pool"
                      ? "border-[#111111] text-[#111111]"
                      : "border-transparent text-[#666560] hover:text-[#111111]"
                  }`}
                  data-testid="tab-pool"
                >
                  Drill Pool Buffer
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("jobs")}
                  className={`py-2.5 px-0.5 text-xs font-medium border-b-2 typist-fluid ${
                    activeTab === "jobs"
                      ? "border-[#111111] text-[#111111]"
                      : "border-transparent text-[#666560] hover:text-[#111111]"
                  }`}
                  data-testid="tab-jobs"
                >
                  Generation Jobs ({jobs.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("checks")}
                  className={`py-2.5 px-0.5 text-xs font-medium border-b-2 typist-fluid ${
                    activeTab === "checks"
                      ? "border-[#111111] text-[#111111]"
                      : "border-transparent text-[#666560] hover:text-[#111111]"
                  }`}
                  data-testid="tab-checks"
                >
                  Data Quality &amp; Trends
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
            <div className="p-12 text-center typist-card text-sm text-[#666560]">
              Select or enroll a participant to manage drill pools and inspect data checks.
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
