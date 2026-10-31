// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { GenerationOverview } from "../../../api/analysis";
import { GenerationTab } from "../GenerationTab";

afterEach(() => {
  cleanup();
});

const MOCK_GENERATION: GenerationOverview = {
  arms: [
    {
      arm: "control",
      drills_count: 5,
      attempts_count: 5,
      acceptance_rate: 1.0,
      attempts_per_drill: 1.0,
      mean_target_density: 0.0,
      mean_word_length: 4.8,
      mean_real_word_ratio: 1.0,
      tokens_per_sec: null,
      mean_gen_ms: null,
      peak_memory_mb: null,
    },
    {
      arm: "llm",
      drills_count: 8,
      attempts_count: 16,
      acceptance_rate: 0.5,
      attempts_per_drill: 2.0,
      mean_target_density: 0.22,
      mean_word_length: 4.2,
      mean_real_word_ratio: 0.99,
      tokens_per_sec: 28.4,
      mean_gen_ms: 380.0,
      peak_memory_mb: 1250.0,
    },
  ],
  total_drills: 13,
  total_attempts: 21,
};

describe("GenerationTab", () => {
  it("renders empty state when generation is null", () => {
    render(<GenerationTab generation={null} />);
    expect(screen.getByText("No generation audit data available.")).toBeInTheDocument();
  });

  it("renders arms summary table and LLM operational metrics", () => {
    render(<GenerationTab generation={MOCK_GENERATION} />);

    // Total counts
    expect(screen.getByText("13")).toBeInTheDocument();
    expect(screen.getByText("21")).toBeInTheDocument();

    // Table rows
    expect(screen.getByText("control")).toBeInTheDocument();
    expect(screen.getByText("llm")).toBeInTheDocument();
    expect(screen.getByText("Calibrated")).toBeInTheDocument();
    expect(screen.getByText("22.0%")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();

    // LLM operational metrics
    expect(screen.getByText("28.4 tok/s")).toBeInTheDocument();
    expect(screen.getByText("380.0 ms")).toBeInTheDocument();
    expect(screen.getByText("1250.0 MB")).toBeInTheDocument();
  });
});
