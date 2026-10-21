import { useMemo } from "react";
import { MatrixPage } from "../features/matrix/MatrixPage";
import { createCollectorSink } from "../features/session/collector";
import { DEMO_BLOCK_LABEL, DEMO_BLOCK_TEXT } from "../features/session/fixtures";
import { TypingSurface } from "../features/session/TypingSurface";
import { useHashRoute } from "./useHashRoute";

/** Hash view switch: #/matrix/<id> -> the bigram matrix; anything else -> the M1 TypingSurface demo. */
export function App() {
  const route = useHashRoute();
  const sink = useMemo(() => createCollectorSink(), []);
  if (route.name === "matrix") {
    return (
      <main className="min-h-screen bg-white">
        <MatrixPage key={route.sessionId} sessionId={route.sessionId} />
      </main>
    );
  }
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
