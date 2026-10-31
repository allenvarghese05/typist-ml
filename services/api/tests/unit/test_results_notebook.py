"""Unit tests for notebooks/03_results.ipynb structure and JSON validity (T4.3)."""

import ast
import json
from pathlib import Path

import pytest


def test_results_notebook_structure_and_json_validity() -> None:
    nb_path = Path(__file__).resolve().parents[4] / "notebooks" / "03_results.ipynb"
    assert nb_path.exists(), f"Notebook missing at {nb_path}"

    content = nb_path.read_text(encoding="utf-8")
    data = json.loads(content)

    assert data.get("nbformat") == 4
    cells = data.get("cells", [])
    assert len(cells) >= 10

    cell_types = {cell["cell_type"] for cell in cells}
    assert "markdown" in cell_types
    assert "code" in cell_types

    md_sources = ["".join(cell["source"]) for cell in cells if cell["cell_type"] == "markdown"]
    all_md = "\n".join(md_sources)

    assert "# Typist-ML: Pilot Results & Outcome Analysis" in all_md
    assert "D01" in all_md
    assert "D05" in all_md
    assert "D18" in all_md
    assert "D20" in all_md
    assert "set_error_rate_change.png" in all_md

    # Validate Python code syntax across all code cells
    for idx, cell in enumerate(cells):
        if cell["cell_type"] == "code":
            code_text = "".join(cell["source"])
            try:
                ast.parse(code_text)
            except SyntaxError as err:
                pytest.fail(f"SyntaxError in notebook code cell {idx}: {err}")
