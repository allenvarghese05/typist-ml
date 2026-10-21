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

  it("parses everything else to the demo route", () => {
    expect(parseHash("")).toEqual({ name: "demo" });
    expect(parseHash("#")).toEqual({ name: "demo" });
    expect(parseHash("#/")).toEqual({ name: "demo" });
    expect(parseHash("#/other")).toEqual({ name: "demo" });
  });
});

function RouteProbe(): React.JSX.Element {
  const route = useHashRoute();
  return (
    <span data-testid="route">
      {route.name === "matrix" ? `matrix:${route.sessionId}` : "demo"}
    </span>
  );
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
  });
});
