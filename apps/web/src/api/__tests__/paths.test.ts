import { describe, expect, it } from "vitest";
import { API_BASE, apiPath } from "../paths";

describe("apiPath", () => {
  it("prefixes an endpoint with the API base path", () => {
    expect(API_BASE).toBe("/api/v1");
    expect(apiPath("/health")).toBe("/api/v1/health");
    expect(apiPath("/sessions/42/events")).toBe("/api/v1/sessions/42/events");
  });

  it("rejects an endpoint without a leading slash", () => {
    expect(() => apiPath("health")).toThrow(RangeError);
    expect(() => apiPath("")).toThrow(RangeError);
  });
});
