import { AdminPage } from "../features/admin/AdminPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { DebriefPage } from "../features/debrief/DebriefPage";
import { MatrixPage } from "../features/matrix/MatrixPage";
import { SessionPage } from "../features/session/SessionPage";
import { useHashRoute } from "./useHashRoute";

/**
 * Application shell: translucent warm-monochrome macOS toolbar over a #FBFBFA canvas.
 * Routes: #/ -> SessionPage; #/dashboard -> DashboardPage; #/results -> DebriefPage;
 * #/admin -> AdminPage; #/matrix/<id> -> MatrixPage.
 */
export function App() {
  const route = useHashRoute();

  const navItemClass = (active: boolean): string =>
    `px-3 py-1.5 rounded-lg text-[13px] typist-fluid ${
      active
        ? "bg-[#ECEAE3] text-[#111111] font-medium"
        : "text-[#666560] hover:text-[#111111] hover:bg-[#F5F4F0]"
    }`;

  return (
    <div className="min-h-screen bg-[#FBFBFA] text-[#111111] flex flex-col">
      <header className="sticky top-0 z-30 typist-glass-bar">
        <div className="mx-auto max-w-6xl px-6 h-12 flex items-center justify-between gap-4">
          <a href="#/" className="flex items-center gap-2.5 group">
            <svg
              width="18"
              height="18"
              viewBox="0 0 18 18"
              fill="none"
              aria-hidden="true"
              className="text-[#111111] shrink-0"
            >
              <rect
                x="1.75"
                y="2.75"
                width="14.5"
                height="12.5"
                rx="3"
                stroke="currentColor"
                strokeWidth="1.4"
              />
              <path
                d="M5 7H6.5M8.25 7H9.75M11.5 7H13M5.5 11.25H12.5"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
            <span className="text-[14px] font-semibold tracking-[-0.02em] text-[#111111]">
              Typist-ML
            </span>
            <span className="hidden sm:inline-block text-[11px] text-[#8A8883] border-l border-[#EAEAEA] pl-2.5">
              Keystroke Lab
            </span>
          </a>

          <nav aria-label="Primary navigation" className="flex items-center gap-1">
            <a href="#/" className={navItemClass(route.name === "demo")}>
              Session
            </a>
            <a href="#/dashboard" className={navItemClass(route.name === "dashboard")}>
              Dashboard
            </a>
            <a href="#/results" className={navItemClass(route.name === "debrief")}>
              Debrief
            </a>
            <a href="#/admin" className={navItemClass(route.name === "admin")}>
              Admin
            </a>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        {route.name === "admin" && <AdminPage initialParticipantId={route.participantId} />}
        {route.name === "dashboard" && (
          <DashboardPage initialParticipantId={route.participantId} initialTab={route.tab} />
        )}
        {route.name === "debrief" && <DebriefPage initialParticipantId={route.participantId} />}
        {route.name === "matrix" && (
          <MatrixPage key={route.sessionId} sessionId={route.sessionId} />
        )}
        {route.name === "demo" && <SessionPage />}
      </main>
    </div>
  );
}
