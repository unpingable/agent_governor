# SPDX-License-Identifier: Apache-2.0
"""Corpus-driven envelope tests.

Walks ``tests/fixtures/standing_envelopes/`` and feeds every fixture
through the same ``StandingReceipt.from_dict`` path the runtime uses.
The corpus is the anti-regression scar tissue chatty asked for in the
C3 follow-up: when somebody loosens deserialization by accident, a
fixture goes from rejected to accepted and the test fails.

Layout:

- ``good/*.json`` → must parse + round-trip
- ``bad/<violation_code>.json`` → must raise ``EnvelopeParseError``
  carrying that violation code
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.standing import (
    EnvelopeParseError,
    StandingReceipt,
    ViolationCode,
    canonical_json,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "standing_envelopes"
GOOD_DIR = FIXTURES_DIR / "good"
BAD_DIR = FIXTURES_DIR / "bad"


def _load(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


@pytest.mark.parametrize(
    "fixture_path",
    sorted(GOOD_DIR.glob("*.json")),
    ids=lambda p: p.stem,
)
def test_good_fixture_round_trips(fixture_path: Path) -> None:
    data = _load(fixture_path)
    receipt = StandingReceipt.from_dict(data)
    # canonical body byte-identical after round-trip.
    body_a = canonical_json(receipt.canonical_body())
    body_b = canonical_json(StandingReceipt.from_dict(receipt.to_dict()).canonical_body())
    assert body_a == body_b


def _code_for_fixture(fixture_path: Path) -> ViolationCode:
    """Filenames use ``<violation_code>[__<note>].json`` so multiple
    fixtures can target the same code without colliding."""

    stem = fixture_path.stem.split("__", 1)[0]
    return ViolationCode(stem)


@pytest.mark.parametrize(
    "fixture_path",
    sorted(BAD_DIR.glob("*.json")),
    ids=lambda p: p.stem,
)
def test_bad_fixture_rejected_with_named_code(fixture_path: Path) -> None:
    expected_code = _code_for_fixture(fixture_path)
    data = _load(fixture_path)
    with pytest.raises(EnvelopeParseError) as exc_info:
        StandingReceipt.from_dict(data)
    codes = [v.code for v in exc_info.value.violations]
    assert expected_code in codes, (
        f"fixture {fixture_path.name} should produce {expected_code.value}, "
        f"got {[c.value for c in codes]}"
    )


def test_corpus_is_non_empty() -> None:
    # Guard: an empty corpus would silently skip everything above.
    assert sorted(GOOD_DIR.glob("*.json")), "good corpus is empty"
    assert sorted(BAD_DIR.glob("*.json")), "bad corpus is empty"


def test_every_bad_fixture_filename_is_a_known_violation_code() -> None:
    # Adding a fixture under a typo'd code name would be silently
    # ignored. Catch that early. Filenames use
    # ``<violation_code>[__<note>].json`` to support multiple fixtures
    # per code (e.g. distinct AUTHORIZATION_CHECK_MALFORMED variants).
    valid_codes = {c.value for c in ViolationCode}
    for fixture in sorted(BAD_DIR.glob("*.json")):
        code_part = fixture.stem.split("__", 1)[0]
        assert code_part in valid_codes, (
            f"fixture {fixture.name} stem prefix {code_part!r} is not a "
            "valid ViolationCode value"
        )
