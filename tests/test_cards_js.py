"""Guards for the dashboard card file (no browser needed)."""

from __future__ import annotations

import re
from pathlib import Path

CARDS = Path(__file__).parents[1] / "custom_components" / "mg_ismart_india" / "www" / "mg-cards.js"
# Called with a dot or defined by the browser / Home Assistant, not in this file.
KNOWN = {
    "if", "for", "while", "switch", "catch", "return", "function", "typeof", "super",
    "setTimeout", "clearTimeout", "Number", "String", "Boolean", "Object", "Error", "Math", "JSON",
    # class methods
    "build", "setConfig", "hass", "getCardSize", "getGridOptions", "getStubConfig", "getConfigForm",
}


def test_every_helper_the_cards_call_is_defined() -> None:
    text = CARDS.read_text()
    code = re.sub(r"/\*.*?\*/|//[^\n]*|`(?:\\.|[^`])*`|\"(?:\\.|[^\"])*\"", "", text, flags=re.S)
    defined = set(re.findall(r"function\s+(\w+)", code)) | set(
        re.findall(r"const\s+(\w+)\s*=\s*(?:\(|async\b|\w+\s*=>)", code)
    )
    code = code.replace("...", " ")  # spread: ...helper(x) is a plain call
    called = set(re.findall(r"(?<![\w.$])([a-z]\w*)\(", code))
    missing = sorted(called - defined - KNOWN)
    assert not missing, f"mg-cards.js calls undefined functions: {missing}"


def test_card_version_matches_manifest() -> None:
    import json

    manifest = json.loads((CARDS.parents[1] / "manifest.json").read_text())
    assert f'const VERSION = "{manifest["version"]}";' in CARDS.read_text()
