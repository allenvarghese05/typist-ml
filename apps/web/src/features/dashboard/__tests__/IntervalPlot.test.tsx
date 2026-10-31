// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { IntervalPlot } from "../IntervalPlot";

afterEach(() => {
  cleanup();
});

describe("IntervalPlot", () => {
  it("renders N/A when values are null", () => {
    render(<IntervalPlot label="Test Arm" estimate={null} lower={null} upper={null} />);
    expect(screen.getByText("Test Arm")).toBeInTheDocument();
    expect(screen.getByText("N/A")).toBeInTheDocument();
  });

  it("renders SVG line and circle when estimate and bounds are provided", () => {
    render(
      <IntervalPlot
        label="Targeting Effect"
        estimate={-0.05}
        lower={-0.1}
        upper={0.01}
        unit=" rate"
      />,
    );
    expect(screen.getByText("Targeting Effect")).toBeInTheDocument();
    expect(screen.getByText("-0.050 rate")).toBeInTheDocument();
    expect(screen.getByText("[-0.100, 0.010]")).toBeInTheDocument();
    const svg = screen.getByRole("img");
    expect(svg).toBeInTheDocument();
  });

  it("applies correct accessibility aria-label", () => {
    render(
      <IntervalPlot
        label="LLM Arm"
        estimate={0.035}
        lower={0.01}
        upper={0.06}
        unit=" ms"
        higherIsBetter={true}
      />,
    );
    const svg = screen.getByRole("img");
    expect(svg).toHaveAttribute(
      "aria-label",
      "LLM Arm effect: 0.035 ms with 95% interval [0.010, 0.060]",
    );
    expect(screen.getByText("+0.035 ms")).toBeInTheDocument();
  });
});
