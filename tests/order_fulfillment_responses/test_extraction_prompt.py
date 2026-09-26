"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Verifies source-level extraction-prompt parity across independent demos.
"""

from pathlib import Path
import re

ROOT_DIR = Path(__file__).resolve().parents[2]


def prompt_from_source(path: Path, prefix: str, suffix: str) -> str:
    """Extract a triple-quoted prompt body from a Python source file.

    Args:
        path: Module source file to inspect without importing it.
        prefix: Literal assignment prefix before the prompt content.
        suffix: Literal text that starts the excluded trailing portion.

    Returns:
        Prompt body before the selected suffix.

    Raises:
        AssertionError: The expected prompt assignment is absent.
    """
    source = path.read_text(encoding="utf-8")
    match = re.search(
        re.escape(prefix) + r"(.*?)" + re.escape(suffix), source, flags=re.DOTALL
    )
    assert match is not None
    return match.group(1)


def test_responses_prompt_matches_demo_002_except_schema_line():
    """Keep all extraction rules and examples aligned without cross-importing."""
    original = prompt_from_source(
        ROOT_DIR / "demos/order_fulfillment/nodes.py",
        'EXTRACTION_PROMPT = f"""',
        "Return JSON matching this schema:",
    )
    responses = prompt_from_source(
        ROOT_DIR / "demos/order_fulfillment_responses/nodes.py",
        'EXTRACTION_PROMPT = """',
        '"""\n\n\ndef strict_order_schema',
    )
    assert responses == original
