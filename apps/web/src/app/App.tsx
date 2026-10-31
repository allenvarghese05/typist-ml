import { useMemo } from "react";
import { AdminPage } from "../features/admin/AdminPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { DebriefPage } from "../features/debrief/DebriefPage";
import { MatrixPage } from "../features/matrix/MatrixPage";
import { createCollectorSink } from "../features/session/collector";
import { DEMO_BLOCK_LABEL, DEMO_BLOCK_TEXT } from "../features/session/fixtures";
import { TypingSurface } from "../features/session/TypingSurface";
import { useHashRoute } from "./useHashRoute";

/** Hash view switch: #/admin -> AdminPage; #/matrix/<id> -> MatrixPage; anything else -> TypingSurface demo. */
export function App() {
  const route = useHashRoute();
  const sink = useMemo(() => createCollectorSink(), []);

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <nav className="bg-gray-900 text-white px-6 py-2.5 flex items-center justify-between text-sm border-b border-gray-800">
        <div className="font-bold tracking-tight">Typist-ML</div>
        <div className="flex gap-4">
          <a
            href="#/"
            className={`hover:text-blue-400 transition-colors ${
              route.name === "demo" ? "text-blue-400 font-semibold" : "text-gray-300"
            }`}
          >
            Typing Demo
          </a>
          <a
            href="#/admin"
            className={`hover:text-blue-400 transition-colors ${
              route.name === "admin" ? "text-blue-400 font-semibold" : "text-gray-300"
            }`}
          >
            Admin Dashboard
          </a>
          <a
            href="#/dashboard"
            className={`hover:text-blue-400 transition-colors ${
              route.name === "dashboard" ? "text-blue-400 font-semibold" : "text-gray-300"
            }`}
          >
            Dashboard
          </a>
          <a
            href="#/results"
            className={`hover:text-blue-400 transition-colors ${
              route.name === "debrief" ? "text-blue-400 font-semibold" : "text-gray-300"
            }`}
          >
            Debrief
          </a>
        </div>
      </nav>

      <main className="flex-1">
        {route.name === "admin" && <AdminPage initialParticipantId={route.participantId} />}
        {route.name === "dashboard" && (
          <DashboardPage initialParticipantId={route.participantId} initialTab={route.tab} />
        )}
        {route.name === "debrief" && <DebriefPage initialParticipantId={route.participantId} />}
        {route.name === "matrix" && (
          <MatrixPage key={route.sessionId} sessionId={route.sessionId} />
        )}
        {route.name === "demo" && (
          <TypingSurface
            blockLabel={DEMO_BLOCK_LABEL}
            onLifecycle={sink.recordLifecycle}
            sink={sink}
            targetText={DEMO_BLOCK_TEXT}
          />
        )}
      </main>
    </div>
  );
}
