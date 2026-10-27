// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminPage } from "../AdminPage";

const mockParticipants = [
  {
    id: "p-1",
    alias: "pilot-1",
    status: "baseline",
    is_builder: false,
    is_blinded: true,
    created_at: "2026-10-20T00:00:00Z",
    consent_at: "2026-10-20T00:00:00Z",
  },
  {
    id: "p-2",
    alias: "pilot-2",
    status: "assigned",
    is_builder: false,
    is_blinded: true,
    created_at: "2026-10-20T00:00:00Z",
    consent_at: "2026-10-20T00:00:00Z",
  },
];

const mockHealth = {
  status: "ok",
  database: "ok",
  worker: { status: "ok" as const, heartbeat_age_s: 2.4 },
};

const mockPool = [
  {
    participant_id: "p-1",
    alias: "pilot-1",
    arms: [
      {
        arm: "control",
        ready_count: 6,
        target_count: 6,
        queued_count: 0,
        used_count: 0,
        deficit: 0,
        is_ready: true,
      },
    ],
  },
];

const mockJobs = [
  {
    id: "j-100",
    participant_id: "p-1",
    arm: "control",
    requested: 1,
    status: "done" as const,
    retries: 0,
    error: null,
    created_at: "2026-10-20T10:00:00Z",
    started_at: "2026-10-20T10:00:01Z",
    finished_at: "2026-10-20T10:00:02Z",
  },
];

const mockChecks = {
  participant_id: "p-1",
  alias: "pilot-1",
  status: "baseline",
  passed: true,
  checks: {
    seq_gaps: { passed: true, count: 0, details: [] },
    dwell_anomalies: { passed: true, negative_count: 0, over_1000ms_count: 0, details: [] },
    short_blocks: { passed: true, count: 0, details: [] },
    missing_keyups: {
      passed: true,
      total_events: 10,
      missing_count: 0,
      missing_share: 0,
      details: [],
    },
    in_progress_sessions: { passed: true, count: 0, details: [] },
  },
  trend: [],
};

function createMockFetch(overrides: { fail?: boolean } = {}): typeof fetch {
  return vi.fn().mockImplementation(async (url: string | URL | Request) => {
    const urlStr = String(url);
    if (overrides.fail) {
      return {
        ok: false,
        status: 500,
        json: async () => ({ detail: "Database connection failed" }),
      } as unknown as Response;
    }
    if (urlStr.includes("/health")) {
      return { ok: true, status: 200, json: async () => mockHealth } as unknown as Response;
    }
    if (urlStr.includes("/participants")) {
      return { ok: true, status: 200, json: async () => mockParticipants } as unknown as Response;
    }
    if (urlStr.includes("/pool")) {
      return { ok: true, status: 200, json: async () => mockPool } as unknown as Response;
    }
    if (urlStr.includes("/jobs")) {
      return { ok: true, status: 200, json: async () => mockJobs } as unknown as Response;
    }
    if (urlStr.includes("/checks")) {
      return { ok: true, status: 200, json: async () => mockChecks } as unknown as Response;
    }
    return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
  });
}

afterEach(() => {
  cleanup();
});

describe("AdminPage", () => {
  it("renders worker health status badge and loads participant", async () => {
    const fetchImpl = createMockFetch();
    await act(async () => {
      render(<AdminPage fetchImpl={fetchImpl} />);
    });

    const badge = screen.getByTestId("worker-status-badge");
    expect(badge).toHaveTextContent("Worker Active (heartbeat 2s ago)");

    expect(screen.getByTestId("participant-row-p-1")).toHaveTextContent("pilot-1");
    expect(screen.getByTestId("participant-row-p-2")).toHaveTextContent("pilot-2");
    expect(screen.getByTestId("pool-status-panel")).toBeInTheDocument();
  });

  it("switches tabs between pool, jobs, and data checks", async () => {
    const fetchImpl = createMockFetch();
    await act(async () => {
      render(<AdminPage fetchImpl={fetchImpl} />);
    });

    // Default tab is pool
    expect(screen.getByTestId("pool-status-panel")).toBeInTheDocument();

    // Click jobs tab
    await act(async () => {
      fireEvent.click(screen.getByTestId("tab-jobs"));
    });
    expect(screen.getByTestId("jobs-panel")).toBeInTheDocument();
    expect(screen.getByText("j-100")).toBeInTheDocument();

    // Click data checks tab
    await act(async () => {
      fireEvent.click(screen.getByTestId("tab-checks"));
    });
    expect(screen.getByTestId("data-checks-panel")).toBeInTheDocument();
    expect(screen.getByTestId("checks-summary-banner")).toHaveTextContent(
      "All 5 Data Checks Passed",
    );
  });

  it("displays error banner when an API request fails", async () => {
    const fetchImpl = createMockFetch({ fail: true });
    await act(async () => {
      render(<AdminPage fetchImpl={fetchImpl} />);
    });

    const banner = await screen.findByTestId("admin-error-banner");
    expect(banner).toHaveTextContent("Database connection failed");
  });
});
