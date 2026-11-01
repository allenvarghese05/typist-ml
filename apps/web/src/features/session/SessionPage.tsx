import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchParticipantTrend, type SessionTrendEntry } from "../../api/analysis";
import {
  assignParticipant,
  completeBlock,
  completeSession,
  createParticipant,
  fetchHealth,
  fetchParticipants,
  fetchPoolStatus,
  type HealthResponse,
  type ParticipantResponse,
  type PoolResponse,
  recordParticipantConsent,
  replenishPool,
  type SessionPlan,
  type SessionSummary,
  startBlock,
  startOrResumeSession,
} from "../../api/client";
import { EventBuffer, type EventTransport } from "../../telemetry/EventBuffer";
import { createCollectorSink } from "./collector";
import { DEMO_BLOCK_LABEL, DEMO_BLOCK_TEXT } from "./fixtures";
import { type BlockLifecycleEvent, TypingSurface } from "./TypingSurface";

const ACTIVE_PARTICIPANT_STORAGE_KEY = "typist.activeParticipantId";

export interface SessionPageProps {
  readonly fetchImpl?: typeof fetch;
  readonly eventTransport?: EventTransport;
}

type RunnerStage =
  | { readonly kind: "hub" }
  | {
      readonly kind: "ready";
      readonly plan: SessionPlan;
      readonly blockOrderIndex: number;
    }
  | {
      readonly kind: "typing";
      readonly plan: SessionPlan;
      readonly blockOrderIndex: number;
      readonly buffer: EventBuffer;
    }
  | {
      readonly kind: "saving";
      readonly label: string;
    }
  | {
      readonly kind: "summary";
      readonly plan: SessionPlan;
      readonly summary: SessionSummary;
    }
  | {
      readonly kind: "sandbox";
    };

function phaseDisplayTitle(phase: string): string {
  if (phase === "baseline") return "Baseline Assessment";
  if (phase === "practice") return "Blinded Practice";
  if (phase === "retest") return "Post-Practice Retest";
  return phase;
}

function statusBadgeStyle(status: string): string {
  switch (status) {
    case "done":
      return "bg-[#EDF3EC] text-[#2B5930] border-[#D7E6D5]";
    case "baseline":
    case "practice":
    case "retest":
      return "bg-[#EBF3FA] text-[#1F5E8B] border-[#CEE2F4]";
    case "assigned":
      return "bg-[#FBF3DB] text-[#8A5A00] border-[#EFE0B4]";
    case "withdrawn":
      return "bg-[#FDEBEB] text-[#9F2F2D] border-[#F5D0D2]";
    default:
      return "bg-[#F3F2EE] text-[#4A4945] border-[#E4E2DC]";
  }
}

function readStoredParticipantId(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_PARTICIPANT_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredParticipantId(id: string): void {
  try {
    window.localStorage.setItem(ACTIVE_PARTICIPANT_STORAGE_KEY, id);
  } catch {
    // ignore storage errors in restricted contexts
  }
}

export function SessionPage({
  fetchImpl = fetch,
  eventTransport,
}: SessionPageProps): React.JSX.Element {
  const [participants, setParticipants] = useState<readonly ParticipantResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [trend, setTrend] = useState<readonly SessionTrendEntry[]>([]);
  const [pool, setPool] = useState<PoolResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Enrollment drawer / form state
  const [showEnrollForm, setShowEnrollForm] = useState(false);
  const [newAlias, setNewAlias] = useState("");
  const [newKeyboard, setNewKeyboard] = useState("");
  const [newIsBuilder, setNewIsBuilder] = useState(false);

  // Consent keyboard input
  const [consentKeyboard, setConsentKeyboard] = useState("");

  // Active runner stage
  const [stage, setStage] = useState<RunnerStage>({ kind: "hub" });
  const sandboxSink = useMemo(() => createCollectorSink(), []);
  const activeBufferRef = useRef<EventBuffer | null>(null);

  // Dispose any active EventBuffer on unmount
  useEffect(() => {
    return () => {
      activeBufferRef.current?.dispose();
      activeBufferRef.current = null;
    };
  }, []);

  const loadWorkspace = useCallback(
    async (preferredParticipantId?: string) => {
      try {
        setError(null);
        const [parts, healthRes] = await Promise.all([
          fetchParticipants(fetchImpl),
          fetchHealth(fetchImpl).catch(() => null),
        ]);
        setParticipants(parts);
        setHealth(healthRes);

        let chosenId = preferredParticipantId ?? "";
        if (!chosenId || !parts.some((p) => p.id === chosenId)) {
          const stored = readStoredParticipantId();
          if (stored && parts.some((p) => p.id === stored)) {
            chosenId = stored;
          } else {
            const firstActive = parts.find((p) => p.status !== "done" && p.status !== "withdrawn");
            chosenId = firstActive?.id ?? parts[0]?.id ?? "";
          }
        }

        setSelectedId(chosenId);
        if (chosenId) {
          writeStoredParticipantId(chosenId);
        } else {
          setShowEnrollForm(true);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [fetchImpl],
  );

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  const currentParticipant = useMemo(
    () => participants.find((p) => p.id === selectedId) ?? null,
    [participants, selectedId],
  );

  const loadParticipantContext = useCallback(
    async (participant: ParticipantResponse) => {
      const [trendRes, poolRes] = await Promise.all([
        fetchParticipantTrend(participant.id, fetchImpl),
        participant.status === "assigned" || participant.status === "practice"
          ? fetchPoolStatus(participant.id, fetchImpl)
              .then((rows) => rows[0] ?? null)
              .catch(() => null)
          : Promise.resolve(null),
      ]);
      if (trendRes.status === "ok") {
        setTrend(trendRes.trend);
      } else {
        setTrend([]);
      }
      setPool(poolRes);
    },
    [fetchImpl],
  );

  useEffect(() => {
    if (!currentParticipant) {
      setTrend([]);
      setPool(null);
      return;
    }
    setConsentKeyboard(currentParticipant.keyboard_label ?? "");
    void loadParticipantContext(currentParticipant);
  }, [currentParticipant, loadParticipantContext]);

  // Poll drill pool quietly while in 'assigned' status and drills are still generating
  const poolNeedsPolling = useMemo(() => {
    if (stage.kind !== "hub" || !currentParticipant) return false;
    if (currentParticipant.status !== "assigned") return false;
    if (!pool) return true;
    const everyArmReadyForNext =
      pool.arms.length > 0 && pool.arms.every((arm) => arm.ready_count >= 2);
    const anyQueued = pool.arms.some((arm) => arm.queued_count > 0);
    return !everyArmReadyForNext || anyQueued;
  }, [stage.kind, currentParticipant, pool]);

  useEffect(() => {
    if (!poolNeedsPolling || !currentParticipant) return;
    const handle = window.setInterval(() => {
      fetchPoolStatus(currentParticipant.id, fetchImpl)
        .then((rows) => {
          setPool(rows[0] ?? null);
        })
        .catch(() => {
          // ignore transient poll failure
        });
    }, 2500);
    return () => {
      window.clearInterval(handle);
    };
  }, [poolNeedsPolling, currentParticipant, fetchImpl]);

  // Computed study counts from chronological trend
  const completedBaseline = trend.filter((t) => t.phase === "baseline").length;
  const completedPractice = trend.filter((t) => t.phase === "practice").length;
  const completedRetest = trend.filter((t) => t.phase === "retest").length;
  const totalCompleted = completedBaseline + completedPractice + completedRetest;

  // Blinded pool readiness metrics (never exposes arm names on SessionPage — D18)
  const blindedPoolStats = useMemo(() => {
    if (!pool || pool.arms.length === 0) {
      return {
        canStartPractice: false,
        readyDrills: 0,
        targetDrills: 0,
        queuedDrills: 0,
        readySlots: 0,
        totalSlots: 0,
      };
    }
    const readyDrills = pool.arms.reduce((acc, a) => acc + a.ready_count, 0);
    const targetDrills = pool.arms.reduce((acc, a) => acc + a.target_count, 0);
    const queuedDrills = pool.arms.reduce((acc, a) => acc + a.queued_count, 0);
    const readySlots = pool.arms.filter((a) => a.ready_count >= 2).length;
    return {
      canStartPractice: readySlots === pool.arms.length,
      readyDrills,
      targetDrills,
      queuedDrills,
      readySlots,
      totalSlots: pool.arms.length,
    };
  }, [pool]);

  const handleSelectParticipant = (id: string) => {
    activeBufferRef.current?.dispose();
    activeBufferRef.current = null;
    setStage({ kind: "hub" });
    setSelectedId(id);
    writeStoredParticipantId(id);
    setError(null);
  };

  const handleEnrollSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newAlias.trim();
    if (!trimmed) return;
    try {
      setBusyAction("enroll");
      setError(null);
      const created = await createParticipant(trimmed, newIsBuilder, fetchImpl, newKeyboard);
      setNewAlias("");
      setNewKeyboard("");
      setNewIsBuilder(false);
      setShowEnrollForm(false);
      await loadWorkspace(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyAction(null);
    }
  };

  const handleConsent = async () => {
    if (!currentParticipant) return;
    try {
      setBusyAction("consent");
      setError(null);
      await recordParticipantConsent(currentParticipant.id, consentKeyboard, fetchImpl);
      await loadWorkspace(currentParticipant.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyAction(null);
    }
  };

  const handleFreezeAndReplenish = async () => {
    if (!currentParticipant) return;
    try {
      setBusyAction("assign");
      setError(null);
      await assignParticipant(currentParticipant.id, fetchImpl);
      await replenishPool(currentParticipant.id, fetchImpl);
      await loadWorkspace(currentParticipant.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyAction(null);
    }
  };

  const handleQueueDrills = async () => {
    if (!currentParticipant) return;
    try {
      setBusyAction("replenish");
      setError(null);
      await replenishPool(currentParticipant.id, fetchImpl);
      const rows = await fetchPoolStatus(currentParticipant.id, fetchImpl);
      setPool(rows[0] ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyAction(null);
    }
  };

  const handleLaunchSession = async () => {
    if (!currentParticipant) return;
    try {
      setBusyAction("start-session");
      setError(null);
      const plan = await startOrResumeSession(
        currentParticipant.id,
        {
          client_info: {
            userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "unknown",
            viewport:
              typeof window !== "undefined" ? `${window.innerWidth}x${window.innerHeight}` : "",
          },
        },
        fetchImpl,
      );

      const firstIncompleteIdx = plan.blocks.findIndex((b) => b.ended_at === null);
      if (firstIncompleteIdx === -1) {
        // All blocks already finished on an open session -> finalize immediately
        setStage({ kind: "saving", label: "Computing session metrics..." });
        const summary = await completeSession(plan.session_id, fetchImpl);
        await loadWorkspace(currentParticipant.id);
        setStage({ kind: "summary", plan, summary });
        return;
      }

      setStage({
        kind: "ready",
        plan,
        blockOrderIndex: firstIncompleteIdx,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyAction(null);
    }
  };

  const beginBlock = useCallback(
    async (plan: SessionPlan, blockOrderIndex: number) => {
      const block = plan.blocks[blockOrderIndex];
      if (!block) return;
      try {
        setBusyAction("begin-block");
        setError(null);
        if (block.started_at === null) {
          await startBlock(block.block_id, fetchImpl).catch(() => {
            // If resumed block already had started_at set on backend, continue cleanly
          });
        }
        activeBufferRef.current?.dispose();
        const buffer = new EventBuffer({
          blockId: block.block_id,
          ...(eventTransport ? { transport: eventTransport } : {}),
        });
        activeBufferRef.current = buffer;
        setStage({
          kind: "typing",
          plan,
          blockOrderIndex,
          buffer,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusyAction(null);
      }
    },
    [fetchImpl, eventTransport],
  );

  // Allow pressing Enter on the "ready" briefing card to launch the block fluidly
  useEffect(() => {
    if (stage.kind !== "ready" || busyAction !== null) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Enter" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        void beginBlock(stage.plan, stage.blockOrderIndex);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [stage, busyAction, beginBlock]);

  const handleTypingLifecycle = useCallback(
    (event: BlockLifecycleEvent) => {
      if (event.kind !== "complete") return;
      if (stage.kind !== "typing") return;

      const { plan, blockOrderIndex, buffer } = stage;
      const block = plan.blocks[blockOrderIndex];
      if (!block) return;

      void (async () => {
        try {
          setStage({
            kind: "saving",
            label:
              blockOrderIndex + 1 < plan.blocks.length
                ? `Saving ${block.label}...`
                : "Computing session telemetry & bigram attribution...",
          });

          // Drain pending keyups & flush final batch before completing block/session
          await Promise.race([
            buffer.drain(),
            new Promise<void>((resolve) => {
              window.setTimeout(resolve, 2500);
            }),
          ]);
          buffer.dispose();
          if (activeBufferRef.current === buffer) {
            activeBufferRef.current = null;
          }

          await completeBlock(block.block_id, fetchImpl).catch(() => {
            // Ignore 409 if block was already marked complete
          });

          const nextIdx = blockOrderIndex + 1;
          if (nextIdx < plan.blocks.length) {
            setStage({
              kind: "ready",
              plan,
              blockOrderIndex: nextIdx,
            });
            return;
          }

          const summary = await completeSession(plan.session_id, fetchImpl);
          await loadWorkspace(plan.participant_id);
          setStage({
            kind: "summary",
            plan,
            summary,
          });
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
          setStage({ kind: "hub" });
        }
      })();
    },
    [stage, fetchImpl, loadWorkspace],
  );

  // ---------------------------------------------------------------------------
  // Stage Views: Active Typing, Block Briefing, Saving, Summary, Sandbox
  // ---------------------------------------------------------------------------

  if (stage.kind === "typing") {
    const block = stage.plan.blocks[stage.blockOrderIndex];
    if (!block) return <div />;
    return (
      <div className="mx-auto max-w-4xl px-6 py-6" data-testid="live-typing-stage">
        <div className="mx-auto max-w-3xl flex flex-wrap items-center justify-between gap-3 px-1 pb-2">
          <div className="flex items-center gap-2.5 text-xs text-[#666560]">
            <span className="font-medium text-[#111111]">
              {phaseDisplayTitle(stage.plan.phase)}
            </span>
            <span className="text-[#D9D7D0]">/</span>
            <span className="font-mono">Session {stage.plan.day_index}</span>
            <span className="text-[#D9D7D0]">/</span>
            <span className="font-mono">
              {block.label} of {stage.plan.blocks.length}
            </span>
          </div>
          <button
            type="button"
            onClick={() => {
              stage.buffer.flush();
              stage.buffer.dispose();
              activeBufferRef.current = null;
              setStage({ kind: "hub" });
            }}
            className="text-xs text-[#666560] hover:text-[#111111] px-2.5 py-1 rounded-md hover:bg-[#EFEEE9] typist-fluid"
          >
            Pause &amp; Return to Studio
          </button>
        </div>

        <TypingSurface
          key={block.block_id}
          blockLabel={block.label}
          targetText={block.target_text}
          sink={stage.buffer}
          onLifecycle={handleTypingLifecycle}
        />
      </div>
    );
  }

  if (stage.kind === "ready") {
    const block = stage.plan.blocks[stage.blockOrderIndex];
    if (!block) return <div />;
    const isInterBlock = stage.blockOrderIndex > 0;
    return (
      <div className="mx-auto max-w-2xl px-6 py-14" data-testid="block-ready-stage">
        <div className="typist-card p-8 sm:p-10 space-y-6">
          <div className="flex items-center justify-between gap-4 border-b border-[#EAEAEA] pb-5">
            <div>
              <div className="text-xs font-medium text-[#666560]">
                {phaseDisplayTitle(stage.plan.phase)} · Session {stage.plan.day_index}
              </div>
              <h1 className="mt-1 text-2xl font-semibold text-[#111111]">
                {isInterBlock
                  ? `${stage.plan.blocks[stage.blockOrderIndex - 1]?.label ?? "Previous block"} saved — Ready for ${block.label}`
                  : `${block.label} Ready`}
              </h1>
            </div>
            <span className="font-mono text-xs px-2.5 py-1 rounded-md bg-[#F5F4F0] border border-[#EAEAEA] text-[#4A4945] tabular-nums">
              {stage.blockOrderIndex + 1} / {stage.plan.blocks.length}
            </span>
          </div>

          {stage.plan.blocks.length > 1 && (
            <section className="grid grid-cols-4 gap-2" aria-label="Session block progress">
              {stage.plan.blocks.map((b, idx) => {
                const done = idx < stage.blockOrderIndex || b.ended_at !== null;
                const current = idx === stage.blockOrderIndex;
                return (
                  <div
                    key={b.block_id}
                    className={`rounded-md px-3 py-2 border text-xs font-mono ${
                      done
                        ? "bg-[#EDF3EC] border-[#D7E6D5] text-[#2B5930]"
                        : current
                          ? "bg-[#111111] border-[#111111] text-white font-medium"
                          : "bg-[#F5F4F0] border-[#EAEAEA] text-[#8A8883]"
                    }`}
                  >
                    {b.label}
                  </div>
                );
              })}
            </section>
          )}

          <div className="typist-inset p-4 space-y-2 text-xs text-[#666560] leading-relaxed">
            <div className="flex items-center justify-between text-[#111111] font-medium">
              <span>Passage length</span>
              <span className="font-mono tabular-nums">
                {block.target_text.length.toLocaleString()} characters
              </span>
            </div>
            <p>
              Place your fingers on the home row before starting. Once the block opens, pausing for
              more than 10 seconds abandons the attempt per protocol rule D26.
            </p>
          </div>

          {error && (
            <div className="rounded-lg border border-[#F5D0D2] bg-[#FDEBEB] px-4 py-3 text-xs text-[#9F2F2D]">
              {error}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-4 pt-2">
            <button
              type="button"
              onClick={() => setStage({ kind: "hub" })}
              className="typist-btn-secondary px-4 py-2 text-xs"
            >
              Back to Studio
            </button>

            <div className="flex items-center gap-3">
              <span className="hidden sm:inline-flex items-center gap-1.5 text-xs text-[#666560]">
                Press <kbd className="typist-kbd">Return</kbd> or
              </span>
              <button
                type="button"
                disabled={busyAction === "begin-block"}
                onClick={() => void beginBlock(stage.plan, stage.blockOrderIndex)}
                className="typist-btn-primary px-5 py-2.5 text-sm"
                data-testid="begin-block-btn"
              >
                {busyAction === "begin-block" ? "Opening..." : `Begin ${block.label}`}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (stage.kind === "saving") {
    return (
      <div className="mx-auto max-w-xl px-6 py-20 text-center" data-testid="session-saving-stage">
        <div className="typist-card p-10 space-y-3">
          <div className="mx-auto h-5 w-5 rounded-full border-2 border-[#D9D7D0] border-t-[#111111] animate-spin" />
          <p className="text-sm font-medium text-[#111111]">{stage.label}</p>
          <p className="text-xs text-[#666560]">
            Persisting keystroke batches and computing authoritative Python bigram attribution.
          </p>
        </div>
      </div>
    );
  }

  if (stage.kind === "summary") {
    const { summary, plan } = stage;
    return (
      <div className="mx-auto max-w-3xl px-6 py-12" data-testid="session-summary-card">
        <div className="typist-card p-8 sm:p-10 space-y-8">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#EAEAEA] pb-6">
            <div>
              <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-md border border-[#D7E6D5] bg-[#EDF3EC] text-[11px] font-medium text-[#2B5930]">
                Saved to local SQLite
              </div>
              <h1 className="mt-2.5 text-2xl font-semibold text-[#111111]">
                {phaseDisplayTitle(plan.phase)} · Session {plan.day_index} Complete
              </h1>
              <p className="mt-1 text-xs text-[#666560] font-mono">
                Session ID: {summary.session_id}
              </p>
            </div>
            <a
              href={`#/matrix/${encodeURIComponent(summary.session_id)}`}
              className="typist-btn-secondary px-3.5 py-2 text-xs"
            >
              Inspect Bigram Heatmap
            </a>
          </div>

          {/* 4-column hairline-divided KPI strip (app-screens.md §5) */}
          <div className="grid grid-cols-2 sm:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-[#EAEAEA] border border-[#EAEAEA] rounded-lg bg-[#FBFBFA]">
            <div className="p-4 sm:p-5">
              <div className="text-xs text-[#666560]">Session Speed</div>
              <div
                className="mt-1.5 text-3xl font-normal text-[#111111] font-mono tabular-nums"
                data-testid="summary-wpm"
              >
                {summary.wpm !== null ? summary.wpm.toFixed(1) : "—"}
                <span className="ml-1 text-xs text-[#8A8883] font-sans">WPM</span>
              </div>
            </div>
            <div className="p-4 sm:p-5">
              <div className="text-xs text-[#666560]">First-Attempt Accuracy</div>
              <div
                className="mt-1.5 text-2xl font-normal text-[#111111] font-mono tabular-nums"
                data-testid="summary-accuracy"
              >
                {summary.accuracy !== null ? `${(summary.accuracy * 100).toFixed(1)}%` : "—"}
              </div>
            </div>
            <div className="p-4 sm:p-5">
              <div className="text-xs text-[#666560]">Bigrams Measured</div>
              <div
                className="mt-1.5 text-2xl font-normal text-[#111111] font-mono tabular-nums"
                data-testid="summary-bigrams"
              >
                {summary.bigram_count}
              </div>
            </div>
            <div className="p-4 sm:p-5">
              <div className="text-xs text-[#666560]">Blocks Completed</div>
              <div className="mt-1.5 text-2xl font-normal text-[#111111] font-mono tabular-nums">
                {summary.blocks}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <a
              href={`#/dashboard?participant=${encodeURIComponent(plan.participant_id)}&tab=trend`}
              className="typist-btn-secondary px-4 py-2 text-xs"
            >
              View Session Trend
            </a>
            <button
              type="button"
              onClick={() => setStage({ kind: "hub" })}
              className="typist-btn-primary px-5 py-2.5 text-sm"
              data-testid="summary-continue-btn"
            >
              Continue
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (stage.kind === "sandbox") {
    return (
      <div className="mx-auto max-w-4xl px-6 py-6" data-testid="sandbox-stage">
        <div className="mx-auto max-w-3xl flex flex-wrap items-center justify-between gap-3 px-1 pb-2">
          <div className="flex items-center gap-2.5 text-xs">
            <span className="px-2 py-0.5 rounded border border-[#EFE0B4] bg-[#FBF3DB] text-[#8A5A00] font-medium">
              Warm-up Sandbox · Unrecorded
            </span>
            <span className="text-[#666560]">
              Keystrokes in sandbox mode are not saved to SQLite.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setStage({ kind: "hub" })}
            className="typist-btn-secondary px-3 py-1.5 text-xs"
          >
            Return to Study Session
          </button>
        </div>

        <TypingSurface
          blockLabel={DEMO_BLOCK_LABEL}
          onLifecycle={sandboxSink.recordLifecycle}
          sink={sandboxSink}
          targetText={DEMO_BLOCK_TEXT}
        />
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Default Hub View: Protocol Strip + Active Participant Session Launchpad
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-16 text-center text-sm text-[#666560]">
        Loading study workspace...
      </div>
    );
  }

  const protocolSlots = [
    { index: 1, phase: "baseline", dayInPhase: 1, short: "B1" },
    { index: 2, phase: "baseline", dayInPhase: 2, short: "B2" },
    ...Array.from({ length: 10 }, (_, i) => ({
      index: 3 + i,
      phase: "practice",
      dayInPhase: i + 1,
      short: `P${i + 1}`,
    })),
    { index: 13, phase: "retest", dayInPhase: 1, short: "R1" },
    { index: 14, phase: "retest", dayInPhase: 2, short: "R2" },
  ];

  return (
    <div className="mx-auto max-w-5xl px-6 py-8 space-y-6" data-testid="session-studio-page">
      {/* Header Row: Title & Participant Profile Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-[#EAEAEA] pb-5">
        <div>
          <div className="text-xs font-medium text-[#666560]">Within-Subject Typing Study</div>
          <h1 className="mt-0.5 text-2xl font-semibold text-[#111111]">Session Studio</h1>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {participants.length > 0 && (
            <div className="flex items-center gap-2">
              <label htmlFor="studio-participant-select" className="text-xs text-[#666560]">
                Profile
              </label>
              <select
                id="studio-participant-select"
                aria-label="Active study profile"
                value={selectedId}
                onChange={(e) => handleSelectParticipant(e.target.value)}
                className="text-xs font-mono border border-[#D9D7D0] rounded-lg px-3 py-1.5 bg-white text-[#111111] focus:outline-none focus:border-[#111111]"
                data-testid="studio-participant-select"
              >
                {participants.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.alias} ({p.status}){p.is_builder ? " · builder" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          <button
            type="button"
            onClick={() => setShowEnrollForm((v) => !v)}
            className="typist-btn-secondary px-3 py-1.5 text-xs"
            data-testid="toggle-enroll-btn"
          >
            {showEnrollForm ? "Close New Profile" : "New Profile"}
          </button>

          <button
            type="button"
            onClick={() => setStage({ kind: "sandbox" })}
            className="typist-btn-secondary px-3 py-1.5 text-xs"
            data-testid="open-sandbox-btn"
          >
            Warm-up Sandbox
          </button>
        </div>
      </div>

      {/* Global Error Alert */}
      {error && (
        <div
          className="rounded-lg border border-[#F5D0D2] bg-[#FDEBEB] px-4 py-3 text-xs text-[#9F2F2D] flex items-center justify-between gap-4"
          role="alert"
          data-testid="studio-error-banner"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="font-medium underline shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Quick Inline Profile Enrollment Sheet */}
      {showEnrollForm && (
        <form
          onSubmit={(e) => void handleEnrollSubmit(e)}
          className="typist-card p-6 space-y-4"
          data-testid="studio-enroll-form"
        >
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-[#111111]">Enroll Study Profile</h2>
              <p className="text-xs text-[#666560] mt-0.5">
                Creates an isolated local participant record in SQLite to track your 14 sessions.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="block space-y-1">
              <span className="text-xs font-medium text-[#111111]">Participant Alias</span>
              <input
                type="text"
                required
                placeholder="e.g. allen-study"
                value={newAlias}
                onChange={(e) => setNewAlias(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-[#D9D7D0] rounded-lg bg-white text-[#111111] focus:outline-none focus:border-[#111111]"
                data-testid="studio-alias-input"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs font-medium text-[#111111]">
                Keyboard Label <span className="text-[#8A8883] font-normal">(optional)</span>
              </span>
              <input
                type="text"
                placeholder="e.g. MacBook Pro Internal"
                value={newKeyboard}
                onChange={(e) => setNewKeyboard(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-[#D9D7D0] rounded-lg bg-white text-[#111111] focus:outline-none focus:border-[#111111]"
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
            <label className="inline-flex items-center gap-2 text-xs text-[#666560] cursor-pointer">
              <input
                type="checkbox"
                checked={newIsBuilder}
                onChange={(e) => setNewIsBuilder(e.target.checked)}
                className="rounded border-[#D9D7D0]"
              />
              <span>Mark as builder profile (keep unchecked for standard single-blind run)</span>
            </label>

            <button
              type="submit"
              disabled={!newAlias.trim() || busyAction === "enroll"}
              className="typist-btn-primary px-4 py-2 text-xs"
              data-testid="studio-create-profile-btn"
            >
              {busyAction === "enroll" ? "Creating..." : "Create Profile"}
            </button>
          </div>
        </form>
      )}

      {/* Signature Element: 14-Session Protocol Ledger + Active Action Card */}
      {currentParticipant ? (
        <div className="space-y-6">
          {/* 14-Session Protocol Strip */}
          <div className="typist-card p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <span className="text-sm font-semibold text-[#111111]">
                  {currentParticipant.alias}
                </span>
                <span
                  className={`px-2 py-0.5 rounded-md border text-[11px] font-medium capitalize ${statusBadgeStyle(
                    currentParticipant.status,
                  )}`}
                >
                  {currentParticipant.status}
                </span>
                {currentParticipant.keyboard_label && (
                  <span className="text-xs text-[#666560] font-mono">
                    · {currentParticipant.keyboard_label}
                  </span>
                )}
              </div>

              <div className="text-xs font-mono text-[#666560] tabular-nums">
                {totalCompleted} / 14 sessions recorded
              </div>
            </div>

            <div className="grid grid-cols-7 sm:grid-cols-14 gap-1.5" data-testid="protocol-strip">
              {protocolSlots.map((slot) => {
                const matchingEntry =
                  slot.phase === "baseline"
                    ? trend.filter((t) => t.phase === "baseline")[slot.dayInPhase - 1]
                    : slot.phase === "practice"
                      ? trend.filter((t) => t.phase === "practice")[slot.dayInPhase - 1]
                      : trend.filter((t) => t.phase === "retest")[slot.dayInPhase - 1];

                const isDone = matchingEntry !== undefined;
                const isNext = !isDone && slot.index === totalCompleted + 1;
                const tooltip = matchingEntry
                  ? `${phaseDisplayTitle(slot.phase)} ${slot.dayInPhase}: ${
                      matchingEntry.wpm !== null ? `${matchingEntry.wpm.toFixed(1)} WPM` : "—"
                    } · ${
                      matchingEntry.accuracy !== null
                        ? `${(matchingEntry.accuracy * 100).toFixed(1)}%`
                        : "—"
                    }`
                  : `${phaseDisplayTitle(slot.phase)} ${slot.dayInPhase}`;

                return (
                  <div
                    key={slot.short}
                    title={tooltip}
                    className={`h-11 rounded-md border flex flex-col items-center justify-center font-mono text-[11px] tabular-nums ${
                      isDone
                        ? "bg-[#111111] border-[#111111] text-white"
                        : isNext && currentParticipant.status !== "done"
                          ? "bg-white border-[1.5px] border-[#111111] text-[#111111] font-semibold"
                          : "bg-[#F5F4F0] border-[#EAEAEA] text-[#8A8883]"
                    }`}
                  >
                    <span>{slot.short}</span>
                  </div>
                );
              })}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-[#666560] pt-1">
              <span>
                B1–B2: Baseline (Form A) · P1–P10: Blinded Practice · R1–R2: Retest (Form B)
              </span>
              {currentParticipant.alias === "pilot-builder" &&
                currentParticipant.status === "done" && (
                  <button
                    type="button"
                    onClick={() => setShowEnrollForm(true)}
                    className="font-medium text-[#111111] underline underline-offset-2"
                  >
                    Viewing completed pilot fixture — click New Profile to start your own study
                  </button>
                )}
            </div>
          </div>

          {/* Primary Lifecycle Action Card */}
          {currentParticipant.status === "enrolled" && (
            <div className="typist-card p-8 space-y-5" data-testid="consent-card">
              <div>
                <div className="text-xs font-medium text-[#666560]">
                  Step 1 of 4 · Informed Consent
                </div>
                <h2 className="mt-1 text-xl font-semibold text-[#111111]">
                  Local Keystroke Telemetry &amp; Study Protocol
                </h2>
                <p className="mt-2 text-sm text-[#666560] leading-relaxed">
                  Typist-ML records key-down and key-up timestamps, key identities, and inter-key
                  intervals strictly into your local SQLite database (<code>data/typist.db</code>).
                  No data leaves this machine, and practice drill arms remain single-blinded until
                  all 14 sessions conclude.
                </p>
              </div>

              <div className="max-w-sm space-y-1">
                <label
                  htmlFor="consent-keyboard-input"
                  className="text-xs font-medium text-[#111111]"
                >
                  Keyboard Hardware Label{" "}
                  <span className="text-[#8A8883] font-normal">(optional)</span>
                </label>
                <input
                  id="consent-keyboard-input"
                  type="text"
                  placeholder="e.g. Apple Magic Keyboard"
                  value={consentKeyboard}
                  onChange={(e) => setConsentKeyboard(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-[#D9D7D0] rounded-lg bg-white text-[#111111] focus:outline-none focus:border-[#111111]"
                />
              </div>

              <div className="pt-1">
                <button
                  type="button"
                  disabled={busyAction === "consent"}
                  onClick={() => void handleConsent()}
                  className="typist-btn-primary px-5 py-2.5 text-sm"
                  data-testid="record-consent-btn"
                >
                  {busyAction === "consent"
                    ? "Recording Consent..."
                    : "Record Consent & Begin Baseline"}
                </button>
              </div>
            </div>
          )}

          {currentParticipant.status === "baseline" && completedBaseline < 2 && (
            <div className="typist-card p-8 space-y-5" data-testid="baseline-launch-card">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1.5 max-w-xl">
                  <div className="text-xs font-medium text-[#666560]">
                    Baseline Assessment · Session {completedBaseline + 1} of 2
                  </div>
                  <h2 className="text-xl font-semibold text-[#111111]">
                    Shared Form A Passage (Part {completedBaseline + 1})
                  </h2>
                  <p className="text-sm text-[#666560] leading-relaxed">
                    Type a balanced English prose passage (~2,700 characters) at your natural pace
                    so Python attribution can rank your baseline bigram error rates and inter-key
                    intervals.
                  </p>
                </div>

                <button
                  type="button"
                  disabled={busyAction === "start-session"}
                  onClick={() => void handleLaunchSession()}
                  className="typist-btn-primary px-6 py-3 text-sm shrink-0"
                  data-testid="start-session-btn"
                >
                  {busyAction === "start-session"
                    ? "Preparing..."
                    : `Start Baseline ${completedBaseline + 1} of 2`}
                </button>
              </div>
            </div>
          )}

          {currentParticipant.status === "baseline" && completedBaseline >= 2 && (
            <div className="typist-card p-8 space-y-5" data-testid="assign-launch-card">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1.5 max-w-xl">
                  <div className="text-xs font-medium text-[#2B5930]">
                    Baseline Complete · 2 of 2 Recorded
                  </div>
                  <h2 className="text-xl font-semibold text-[#111111]">
                    Freeze Weak Bigrams &amp; Generate Practice Pool
                  </h2>
                  <p className="text-sm text-[#666560] leading-relaxed">
                    Ranks your candidate bigrams, deals the top 16 into balanced sets A–D in snake
                    order, composes your matched Form B retest passages, and queues your first 3
                    days of practice drills.
                  </p>
                </div>

                <button
                  type="button"
                  disabled={busyAction === "assign"}
                  onClick={() => void handleFreezeAndReplenish()}
                  className="typist-btn-primary px-6 py-3 text-sm shrink-0"
                  data-testid="freeze-assign-btn"
                >
                  {busyAction === "assign"
                    ? "Freezing & Queueing..."
                    : "Freeze Bigrams & Queue Drills"}
                </button>
              </div>
            </div>
          )}

          {currentParticipant.status === "assigned" && (
            <div className="typist-card p-8 space-y-5" data-testid="assigned-pool-card">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1.5 max-w-xl">
                  <div className="text-xs font-medium text-[#666560]">
                    {blindedPoolStats.canStartPractice
                      ? "Practice Pool Ready · Session 1 of 10"
                      : "Synthesizing Blinded Practice Pool"}
                  </div>
                  <h2 className="text-xl font-semibold text-[#111111]">
                    {blindedPoolStats.canStartPractice
                      ? "Ready to Begin Practice Session 1"
                      : "Preparing Personalized Practice Blocks"}
                  </h2>
                  <p className="text-sm text-[#666560] leading-relaxed">
                    {blindedPoolStats.canStartPractice
                      ? "Your blinded practice blocks are ready. Each practice session rotates four 600-character blocks in a cyclic Latin square."
                      : "The local worker is generating and validating your personalized practice blocks across all study sets."}
                  </p>
                </div>

                {blindedPoolStats.canStartPractice ? (
                  <button
                    type="button"
                    disabled={busyAction === "start-session"}
                    onClick={() => void handleLaunchSession()}
                    className="typist-btn-primary px-6 py-3 text-sm shrink-0"
                    data-testid="start-session-btn"
                  >
                    {busyAction === "start-session"
                      ? "Opening..."
                      : "Start Practice Session 1 of 10"}
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={busyAction === "replenish"}
                    onClick={() => void handleQueueDrills()}
                    className="typist-btn-secondary px-4 py-2 text-xs shrink-0"
                  >
                    {busyAction === "replenish" ? "Queueing..." : "Top Up Drill Queue"}
                  </button>
                )}
              </div>

              <div className="typist-inset p-4 space-y-2">
                <div className="flex items-center justify-between text-xs font-mono text-[#4A4945] tabular-nums">
                  <span>
                    Blinded block groups ready: {blindedPoolStats.readySlots} /{" "}
                    {blindedPoolStats.totalSlots || 4}
                  </span>
                  <span>
                    {blindedPoolStats.readyDrills} ready · {blindedPoolStats.queuedDrills} queued
                  </span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-[#E4E2DC] overflow-hidden">
                  <div
                    className="h-full bg-[#111111] transition-[width] duration-300 ease-out"
                    style={{
                      width: `${
                        blindedPoolStats.targetDrills > 0
                          ? Math.min(
                              100,
                              (blindedPoolStats.readyDrills / blindedPoolStats.targetDrills) * 100,
                            )
                          : 0
                      }%`,
                    }}
                  />
                </div>
                {health && health.worker.status !== "ok" && !blindedPoolStats.canStartPractice && (
                  <p className="text-xs text-[#8A5A00] pt-1">
                    Worker status is {health.worker.status}. Ensure <code>just dev</code> (or{" "}
                    <code>typist worker</code>) is running so queued drills complete.
                  </p>
                )}
              </div>
            </div>
          )}

          {currentParticipant.status === "practice" && (
            <div className="typist-card p-8 space-y-5" data-testid="practice-launch-card">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1.5 max-w-xl">
                  <div className="text-xs font-medium text-[#666560]">
                    Blinded Practice · Session {Math.min(completedPractice + 1, 10)} of 10
                  </div>
                  <h2 className="text-xl font-semibold text-[#111111]">
                    4 Blinded Blocks (Latin-Square Rotation)
                  </h2>
                  <p className="text-sm text-[#666560] leading-relaxed">
                    Complete Blocks 1 through 4 (~600 characters per block). Block identities stay
                    hidden until after Retest Session 2 to preserve single-blind integrity.
                  </p>
                </div>

                <button
                  type="button"
                  disabled={busyAction === "start-session"}
                  onClick={() => void handleLaunchSession()}
                  className="typist-btn-primary px-6 py-3 text-sm shrink-0"
                  data-testid="start-session-btn"
                >
                  {busyAction === "start-session"
                    ? "Opening..."
                    : `Start Practice ${Math.min(completedPractice + 1, 10)} of 10`}
                </button>
              </div>
            </div>
          )}

          {currentParticipant.status === "retest" && (
            <div className="typist-card p-8 space-y-5" data-testid="retest-launch-card">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1.5 max-w-xl">
                  <div className="text-xs font-medium text-[#666560]">
                    Final Evaluation · Retest {Math.min(completedRetest + 1, 2)} of 2
                  </div>
                  <h2 className="text-xl font-semibold text-[#111111]">
                    Matched Form B Passage (Part {Math.min(completedRetest + 1, 2)})
                  </h2>
                  <p className="text-sm text-[#666560] leading-relaxed">
                    Completing both Form B retest passages completes your 14-session study and opens
                    your unblinded debrief and Bayesian targeting-effect analysis.
                  </p>
                </div>

                <button
                  type="button"
                  disabled={busyAction === "start-session"}
                  onClick={() => void handleLaunchSession()}
                  className="typist-btn-primary px-6 py-3 text-sm shrink-0"
                  data-testid="start-session-btn"
                >
                  {busyAction === "start-session"
                    ? "Opening..."
                    : `Start Retest ${Math.min(completedRetest + 1, 2)} of 2`}
                </button>
              </div>
            </div>
          )}

          {currentParticipant.status === "done" && (
            <div className="typist-card p-8 space-y-5" data-testid="done-debrief-card">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1.5 max-w-xl">
                  <div className="text-xs font-medium text-[#2B5930]">
                    Protocol Complete · All 14 Sessions Recorded
                  </div>
                  <h2 className="text-xl font-semibold text-[#111111]">
                    Unblinded Study Debrief Ready
                  </h2>
                  <p className="text-sm text-[#666560] leading-relaxed">
                    All baseline, practice, and retest telemetry for{" "}
                    <span className="font-medium text-[#111111]">{currentParticipant.alias}</span>{" "}
                    is complete. Inspect your unmasked generator mappings and confirmatory Bayesian
                    targeting effects.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2.5 shrink-0">
                  <a
                    href={`#/dashboard?participant=${encodeURIComponent(currentParticipant.id)}`}
                    className="typist-btn-secondary px-4 py-2.5 text-xs"
                  >
                    Analysis Dashboard
                  </a>
                  <a
                    href={`#/results/${encodeURIComponent(currentParticipant.id)}`}
                    className="typist-btn-primary px-5 py-2.5 text-sm"
                    data-testid="open-debrief-link"
                  >
                    Open Study Debrief
                  </a>
                </div>
              </div>
            </div>
          )}

          {/* Compact Recent Sessions Table (when sessions exist) */}
          {trend.length > 0 && (
            <div className="typist-card p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-[#111111]">Recorded Sessions</h3>
                <a
                  href={`#/dashboard?participant=${encodeURIComponent(currentParticipant.id)}&tab=trend`}
                  className="text-xs text-[#666560] hover:text-[#111111] underline underline-offset-2"
                >
                  Full trajectory
                </a>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-[#4A4945]">
                  <thead className="border-b border-[#EAEAEA] text-[11px] text-[#666560]">
                    <tr>
                      <th className="py-2 pr-4 font-medium">Phase</th>
                      <th className="py-2 px-4 font-medium text-right">Session</th>
                      <th className="py-2 px-4 font-medium text-right">Speed</th>
                      <th className="py-2 px-4 font-medium text-right">Accuracy</th>
                      <th className="py-2 pl-4 font-medium text-right">Matrix</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#F1F0EC] font-mono tabular-nums">
                    {trend
                      .slice(-5)
                      .reverse()
                      .map((entry) => (
                        <tr key={entry.session_id} className="hover:bg-[#FBFBFA]">
                          <td className="py-2.5 pr-4 font-sans capitalize text-[#111111]">
                            {entry.phase}
                          </td>
                          <td className="py-2.5 px-4 text-right text-[#666560]">
                            Day {entry.day_index}
                          </td>
                          <td className="py-2.5 px-4 text-right text-[#111111]">
                            {entry.wpm !== null ? `${entry.wpm.toFixed(1)} WPM` : "—"}
                          </td>
                          <td className="py-2.5 px-4 text-right text-[#111111]">
                            {entry.accuracy !== null
                              ? `${(entry.accuracy * 100).toFixed(1)}%`
                              : "—"}
                          </td>
                          <td className="py-2.5 pl-4 text-right font-sans">
                            <a
                              href={`#/matrix/${encodeURIComponent(entry.session_id)}`}
                              className="text-[#111111] hover:underline underline-offset-2"
                            >
                              Heatmap
                            </a>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="typist-card p-10 text-center space-y-3">
          <h2 className="text-lg font-semibold text-[#111111]">No Study Profile Enrolled Yet</h2>
          <p className="text-sm text-[#666560] max-w-md mx-auto">
            Create your local participant profile above to begin Baseline Session 1, or launch the
            Warm-up Sandbox for unrecorded practice.
          </p>
        </div>
      )}
    </div>
  );
}
