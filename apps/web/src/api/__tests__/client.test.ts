import { describe, expect, it, vi } from "vitest";
import {
  assignParticipant,
  createJob,
  createParticipant,
  fetchChecks,
  fetchHealth,
  fetchJobs,
  fetchParticipants,
  fetchPoolStatus,
  replenishPool,
} from "../client";

function mockFetch(status = 200, body: unknown = {}): typeof fetch {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response);
}

describe("api/client", () => {
  it("fetchHealth sends GET to /api/v1/health", async () => {
    const fetchFn = mockFetch(200, {
      status: "ok",
      database: "ok",
      worker: { status: "ok", heartbeat_age_s: 1.2 },
    });
    const result = await fetchHealth(fetchFn);
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/v1/health",
      expect.objectContaining({ headers: { "Content-Type": "application/json" } }),
    );
    expect(result.worker.status).toBe("ok");
  });

  it("fetchParticipants sends GET to /api/v1/participants", async () => {
    const fetchFn = mockFetch(200, [{ id: "p-1", alias: "pilot-1" }]);
    const result = await fetchParticipants(fetchFn);
    expect(fetchFn).toHaveBeenCalledWith("/api/v1/participants", expect.anything());
    expect(result).toHaveLength(1);
    expect(result[0]?.id).toBe("p-1");
  });

  it("createParticipant sends POST with alias and is_builder", async () => {
    const fetchFn = mockFetch(201, { id: "p-2", alias: "builder-user", is_builder: true });
    const result = await createParticipant("builder-user", true, fetchFn);
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/v1/participants",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ alias: "builder-user", is_builder: true }),
      }),
    );
    expect(result.id).toBe("p-2");
  });

  it("assignParticipant sends POST to /api/v1/admin/participants/:id/assign", async () => {
    const fetchFn = mockFetch(200, {
      participant_id: "p-1",
      status: "assigned",
      frozen_bigrams: 16,
      mapping: { A: "control" },
      form_b_composed: true,
    });
    const result = await assignParticipant("p-1", fetchFn);
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/v1/admin/participants/p-1/assign",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.status).toBe("assigned");
  });

  it("fetchPoolStatus supports optional participantId filter", async () => {
    const fetchFn = mockFetch(200, []);
    await fetchPoolStatus(undefined, fetchFn);
    expect(fetchFn).toHaveBeenCalledWith("/api/v1/admin/pool", expect.anything());

    await fetchPoolStatus("p-1", fetchFn);
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/v1/admin/pool?participant_id=p-1",
      expect.anything(),
    );
  });

  it("replenishPool sends POST to /api/v1/admin/pool/replenish", async () => {
    const fetchFn = mockFetch(200, [{ id: "j-1", status: "pending" }]);
    const result = await replenishPool("p-1", fetchFn);
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/v1/admin/pool/replenish",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ participant_id: "p-1" }),
      }),
    );
    expect(result).toHaveLength(1);
  });

  it("fetchJobs formats query parameters properly", async () => {
    const fetchFn = mockFetch(200, []);
    await fetchJobs({ participant_id: "p-1", status: "pending", limit: 20 }, fetchFn);
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/v1/admin/jobs?participant_id=p-1&status=pending&limit=20",
      expect.anything(),
    );
  });

  it("createJob sends POST to /api/v1/admin/jobs", async () => {
    const fetchFn = mockFetch(201, [{ id: "j-2", status: "pending" }]);
    const result = await createJob(
      { participant_id: "p-1", arm: "control", requested: 2 },
      fetchFn,
    );
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/v1/admin/jobs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ participant_id: "p-1", arm: "control", requested: 2 }),
      }),
    );
    expect(result).toHaveLength(1);
  });

  it("fetchChecks sends GET to /api/v1/admin/checks/:id", async () => {
    const fetchFn = mockFetch(200, {
      participant_id: "p-1",
      alias: "pilot-1",
      status: "assigned",
      passed: true,
      checks: {},
      trend: [],
    });
    const result = await fetchChecks("p-1", fetchFn);
    expect(fetchFn).toHaveBeenCalledWith("/api/v1/admin/checks/p-1", expect.anything());
    expect(result.passed).toBe(true);
  });

  it("throws error with detail on failed HTTP status", async () => {
    const fetchFn = mockFetch(404, { detail: "Participant not found" });
    await expect(fetchChecks("missing", fetchFn)).rejects.toThrow("Participant not found");
  });
});
