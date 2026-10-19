import { useMemo } from "react";
import { createCollectorSink } from "../features/session/collector";
import { DEMO_BLOCK_LABEL, DEMO_BLOCK_TEXT } from "../features/session/fixtures";
import { TypingSurface } from "../features/session/TypingSurface";

/** Milestone 1 demo: one typing block fed from a fixture, rows caught by an in-memory sink. */
export function App() {
  const sink = useMemo(() => createCollectorSink(), []);
  return (
    <main className="min-h-screen bg-white">
      <TypingSurface
        blockLabel={DEMO_BLOCK_LABEL}
        onLifecycle={sink.recordLifecycle}
        sink={sink}
        targetText={DEMO_BLOCK_TEXT}
      />
    </main>
  );
}
