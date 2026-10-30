"""docs/analysis-plan.md, its definitions ADR and the README link (T0.6, T3.6).

Design doc section 15.1 lists what the analysis plan covers, and D20 pre-registers it before the
first practice session. T0.6 created the plan as an undated draft skeleton. T3.6 dates and
pre-registers it on 2026-10-30, freezing all M3 parameters before practice sessions commence.
"""

from pathlib import Path

import pytest

from typist.config import REPO_ROOT

PLAN = REPO_ROOT / "docs" / "analysis-plan.md"
ADR = REPO_ROOT / "docs" / "decisions" / "D23-analysis-plan-definitions.md"
README = REPO_ROOT / "README.md"
STATUS_LINE = "Status: pre-registered on 2026-10-30 (per D20)."
DESIGN_LINK = (
    "Design: [docs/design/Typist-ML_Technical_Design.pdf]"
    "(docs/design/Typist-ML_Technical_Design.pdf)"
)
PLAN_LINK = (
    "Analysis plan (draft, not yet pre-registered): [docs/analysis-plan.md](docs/analysis-plan.md)"
)
# One heading per section 15.1 bullet, in 15.1 order (T0.6 owner answer 1).
SECTION_15_1_HEADINGS = (
    "## Primary Outcome",
    "## Key Secondary Outcome",
    "## Exclusions",
    "## Exploratory Analysis",
    "## Pre-registration",
)
# Sections beyond 15.1 (T0.6 owner answers 3 and 5).
EXTRA_HEADINGS = (
    "## Study Design and Definitions",
    "## Secondary Measures from Section 3.5",
    "## Participants and Blinding",
    "## Two-Set Mode Contingency",
    "## Twelve-Bigram Fallback",
    "## Missed Days and the Three-Day Baseline Rule",
    "## Known Weaknesses and Limitations",
    "### Values to Be Fixed in T3.6",
    "## Deviations Log",
    "## Amendments",
)


def read_lines(path: Path) -> list[str]:
    """The file's lines, without line endings or trailing whitespace."""
    return [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()]


def headings(path: Path) -> list[str]:
    """The markdown heading lines of the file, in order."""
    return [line for line in read_lines(path) if line.startswith("#")]


def test_definitions_adr_exists_and_is_accepted() -> None:
    lines = read_lines(ADR)
    assert lines[0] == "# D23: Analysis plan exclusion definitions"
    assert "- Status: accepted" in lines
    assert "- Task: T0.6" in lines


def test_analysis_plan_exists() -> None:
    assert PLAN.is_file()


@pytest.mark.parametrize("heading", SECTION_15_1_HEADINGS)
def test_analysis_plan_has_each_section_15_1_heading_once(heading: str) -> None:
    assert headings(PLAN).count(heading) == 1


def test_section_15_1_headings_are_in_15_1_order() -> None:
    found = headings(PLAN)
    positions = [found.index(heading) for heading in SECTION_15_1_HEADINGS]
    assert positions == sorted(positions)


@pytest.mark.parametrize("heading", EXTRA_HEADINGS)
def test_analysis_plan_has_each_extra_heading_once(heading: str) -> None:
    assert headings(PLAN).count(heading) == 1


def test_analysis_plan_title_and_status_line() -> None:
    lines = read_lines(PLAN)
    assert lines[0] == "# Typist-ML Analysis Plan"
    assert lines[2] == STATUS_LINE
    assert lines.count(STATUS_LINE) == 1


def test_analysis_plan_is_dated() -> None:
    """T3.6 pre-registers and dates the analysis plan (D20, owner answers 1-2)."""
    lines = read_lines(PLAN)
    assert any(line == "Date: 2026-10-30" or line.startswith("Date: 2026-10-30") for line in lines)
    assert lines[2] == STATUS_LINE


def test_analysis_plan_contains_pre_registered_m3_values() -> None:
    """T3.6 freezes all 9 M3 values in the analysis plan (owner answers 4-9)."""
    text = PLAN.read_text(encoding="utf-8")
    assert "practice_days = 10" in text or "N = 10" in text
    assert "Primary N = 1 (builder only, unblinded)" in text
    assert "['control', 'heuristic', 'markov', 'llm']" in text or '["control", "heuristic", "markov", "llm"]' in text
    assert "[0.10, 0.40]" in text
    assert "08231374eeacb049a0eade7922910865b8fce912" in text
    assert "100,000" in text
    assert "20261030" in text
    assert "10,000 bootstrap resamples" in text
    assert "6 per set" in text


def test_readme_links_the_analysis_plan_next_to_the_design_doc() -> None:
    lines = read_lines(README)
    design = lines.index(DESIGN_LINK)
    assert lines[design + 1] == ""
    assert lines[design + 2] == PLAN_LINK
    assert lines.count(PLAN_LINK) == 1
