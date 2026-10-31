// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { parseHash, useHashRoute } from "../useHashRoute";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("parseHash", () => {
  it("parses #/matrix/<id> to a matrix route with the decoded id", () => {
    expect(parseHash("#/matrix/abc")).toEqual({ name: "matrix", sessionId: "abc" });
    expect(parseHash("#/matrix/a%2Fb")).toEqual({ name: "matrix", sessionId: "a/b" });
  });

  it("parses #/admin and query params to admin route", () => {
    expect(parseHash("#/admin")).toEqual({ name: "admin", participantId: undefined });
    expect(parseHash("#/admin?participant=p-42")).toEqual({
      name: "admin",
      participantId: "p-42",
    });
  });

  it("parses #/dashboard with optional participant and tab", () => {
    expect(parseHash("#/dashboard")).toEqual({
      name: "dashboard",
      participantId: undefined,
      tab: undefined,
    });
    expect(parseHash("#/dashboard?participant=p-1&tab=trend")).toEqual({
      name: "dashboard",
      participantId: "p-1",
      tab: "trend",
    });
  });

  it("parses everything else to the demo route", () => {
    expect(parseHash("")).toEqual({ name: "demo" });
    expect(parseHash("#")).toEqual({ name: "demo" });
    expect(parseHash("#/")).toEqual({ name: "demo" });
    expect(parseHash("#/other")).toEqual({ name: "demo" });
  });
});

function RouteProbe(): React.JSX.Element {
  const route = useHashRoute();
  let label = "demo";
  if (route.name === "matrix") {
    label = `matrix:${route.sessionId}`;
  } else if (route.name === "admin") {
    label = `admin:${route.participantId ?? "none"}`;
  } else if (route.name === "dashboard") {
    label = `dashboard:${route.participantId ?? "none"}:${route.tab ?? "none"}`;
  }
  return <span data-testid="route">{label}</span>;
}

describe("useHashRoute", () => {
  it("re-renders when the hash changes", () => {
    render(<RouteProbe />);
    expect(screen.getByTestId("route")).toHaveTextContent("demo");
    act(() => {
      window.location.hash = "#/matrix/s9";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(screen.getByTestId("route")).toHaveTextContent("matrix:s9");
    act(() => {
      window.location.hash = "#/admin?participant=p-1";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(screen.getByTestId("route")).toHaveTextContent("admin:p-1");
  });
});
