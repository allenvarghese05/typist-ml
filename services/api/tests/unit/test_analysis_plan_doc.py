"""docs/analysis-plan.md, its definitions ADR and the README link (T0.6).

Design doc section 15.1 lists what the analysis plan covers, and D20 pre-registers it before the
first practice session. T0.6 creates the plan as an undated draft (owner answers 1, 3 to 5 and 7).
T3.6 dates and pre-registers it, and updates STATUS_LINE and test_analysis_plan_is_not_dated_yet
in the same pull request.
"""

from pathlib import Path

import pytest

from typist.config import REPO_ROOT

PLAN = REPO_ROOT / "docs" / "analysis-plan.md"
ADR = REPO_ROOT / "docs" / "decisions" / "D23-analysis-plan-definitions.md"
README = REPO_ROOT / "README.md"
STATUS_LINE = (
    "Status: draft skeleton — not pre-registered."
    " Pre-registration (dated, per D20) happens in T3.6."
)
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


def test_analysis_plan_is_not_dated_yet() -> None:
    # Owner answer 4: no frozen date in T0.6; T3.6 writes the pre-registration date.
    assert not any(line.startswith(("Date:", "- Date:")) for line in read_lines(PLAN))
