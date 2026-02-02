"""
Continuity Bridges: mode-specific anchor factories.

Transforms fiction, nonfiction, and puppet domain objects into continuity
Anchors for one-shot gating via ContinuityChecker. Follows the adapters.py
pattern: bridge code is mapping logic, not engine logic.

Design principles:
1. All factories accept plain dicts (from .to_dict()) -- zero cross-imports
   to fiction_governor or nonfiction_governor packages.
2. Only imports from governor.continuity (Anchor, AnchorType, Severity).
3. Gracefully handles missing/None fields (partial dicts are fine).
4. Each factory returns a list[Anchor]; master factories combine sub-factories.
"""

from __future__ import annotations

from .continuity import Anchor, AnchorType, Severity


# =============================================================================
# Fiction bridges
# =============================================================================


def anchors_from_characters(characters: list[dict]) -> list[Anchor]:
    """
    Build continuity anchors from fiction character dicts.

    For each character:
    - anti_patterns -> PROHIBITION anchor (severity=CORRECT)
    - voice.avoid -> PERSONA anchor (severity=WARN)

    Skips characters with neither anti_patterns nor voice.avoid.
    """
    anchors: list[Anchor] = []
    for char in characters:
        name = char.get("name", "unknown")
        safe_name = name.lower().replace(" ", "_")

        anti_patterns = char.get("anti_patterns") or []
        if anti_patterns:
            anchors.append(Anchor(
                id=f"fiction_char_{safe_name}_anti",
                anchor_type=AnchorType.PROHIBITION,
                description=f"Character '{name}' must never: {', '.join(anti_patterns)}",
                forbidden_patterns=list(anti_patterns),
                severity=Severity.CORRECT,
                source="fiction_bridge",
            ))

        voice = char.get("voice") or {}
        voice_avoid = voice.get("avoid") or []
        if voice_avoid:
            anchors.append(Anchor(
                id=f"fiction_char_{safe_name}_voice",
                anchor_type=AnchorType.PERSONA,
                description=f"Character '{name}' voice must avoid: {', '.join(voice_avoid)}",
                forbidden_patterns=list(voice_avoid),
                severity=Severity.WARN,
                source="fiction_bridge",
            ))

    return anchors


def anchors_from_banned_tropes(tropes: list[dict]) -> list[Anchor]:
    """
    Build continuity anchors from banned trope dicts.

    For each trope with non-empty patterns:
    - patterns -> PROHIBITION anchor with forbidden_patterns
    - severity "error" -> REJECT, "warning" -> WARN
    """
    severity_map = {"error": Severity.REJECT, "warning": Severity.WARN}
    anchors: list[Anchor] = []

    for trope in tropes:
        patterns = trope.get("patterns") or []
        if not patterns:
            continue

        name = trope.get("name", "unknown")
        safe_name = name.lower().replace(" ", "_")
        reason = trope.get("reason", "")
        raw_severity = trope.get("severity", "warning")
        sev = severity_map.get(raw_severity, Severity.WARN)

        desc = f"Banned trope '{name}'"
        if reason:
            desc += f": {reason}"

        anchors.append(Anchor(
            id=f"fiction_trope_{safe_name}",
            anchor_type=AnchorType.PROHIBITION,
            description=desc,
            forbidden_patterns=list(patterns),
            severity=sev,
            source="fiction_bridge",
        ))

    return anchors


def anchors_from_world_rules(rules: list[dict]) -> list[Anchor]:
    """
    Build continuity anchors from world rule dicts.

    Each rule becomes a CANON anchor with description only (prompt enrichment,
    not hard pattern matching -- lexical matching can't reliably enforce
    semantic world rules).
    """
    anchors: list[Anchor] = []
    for rule in rules:
        name = rule.get("name", "unknown")
        safe_name = name.lower().replace(" ", "_")
        rule_text = rule.get("rule", "")
        category = rule.get("category", "")

        desc = f"World rule '{name}'"
        if category:
            desc += f" ({category})"
        desc += f": {rule_text}"

        anchors.append(Anchor(
            id=f"fiction_rule_{safe_name}",
            anchor_type=AnchorType.CANON,
            description=desc,
            severity=Severity.WARN,
            source="fiction_bridge",
        ))

    return anchors


def anchors_from_tone_settings(tone: dict) -> list[Anchor]:
    """
    Build continuity anchors from fiction tone settings dict.

    - avoid list -> STYLE anchor with forbidden_patterns (severity=CORRECT)
    - not_genres list -> STYLE anchor with forbidden_concepts (severity=WARN)

    Skips if both are empty/missing.
    """
    anchors: list[Anchor] = []

    avoid = tone.get("avoid") or []
    if avoid:
        anchors.append(Anchor(
            id="fiction_tone_avoid",
            anchor_type=AnchorType.STYLE,
            description=f"Tone: avoid {', '.join(avoid)}",
            forbidden_patterns=list(avoid),
            severity=Severity.CORRECT,
            source="fiction_bridge",
        ))

    not_genres = tone.get("not_genres") or []
    if not_genres:
        anchors.append(Anchor(
            id="fiction_tone_not_genres",
            anchor_type=AnchorType.STYLE,
            description=f"Not these genres: {', '.join(not_genres)}",
            forbidden_concepts=list(not_genres),
            severity=Severity.WARN,
            source="fiction_bridge",
        ))

    return anchors


def anchors_from_fiction_bible(bible_data: dict) -> list[Anchor]:
    """
    Master factory: build all fiction anchors from a bible data dict.

    Expected keys (all optional):
        characters: list[dict]
        world_rules: list[dict]
        banned_tropes: list[dict]
        tone: dict
    """
    anchors: list[Anchor] = []
    anchors.extend(anchors_from_characters(bible_data.get("characters") or []))
    anchors.extend(anchors_from_banned_tropes(bible_data.get("banned_tropes") or []))
    anchors.extend(anchors_from_world_rules(bible_data.get("world_rules") or []))

    tone = bible_data.get("tone")
    if tone:
        anchors.extend(anchors_from_tone_settings(tone))

    return anchors


# =============================================================================
# Nonfiction bridges
# =============================================================================


def anchors_from_concepts(concepts: list[dict]) -> list[Anchor]:
    """
    Build continuity anchors from nonfiction concept dicts.

    For each concept with anti_patterns:
    - anti_patterns -> DEFINITION anchor with forbidden_patterns (severity=CORRECT)
    """
    anchors: list[Anchor] = []
    for concept in concepts:
        anti_patterns = concept.get("anti_patterns") or []
        if not anti_patterns:
            continue

        term = concept.get("term", "unknown")
        safe_term = term.lower().replace(" ", "_")

        anchors.append(Anchor(
            id=f"nf_concept_{safe_term}",
            anchor_type=AnchorType.DEFINITION,
            description=f"Concept '{term}': do not use {', '.join(anti_patterns)}",
            forbidden_patterns=list(anti_patterns),
            severity=Severity.CORRECT,
            source="nonfiction_bridge",
        ))

    return anchors


def anchors_from_positions(positions: list[dict]) -> list[Anchor]:
    """
    Build continuity anchors from nonfiction position dicts.

    Only includes positions where superseded_by is None (current positions).
    Each becomes a CANON anchor with description=claim (prompt enrichment,
    not hard pattern matching).
    """
    anchors: list[Anchor] = []
    for pos in positions:
        if pos.get("superseded_by") is not None:
            continue

        pos_id = pos.get("id", "unknown")
        # Use last 8 chars of UUID for readable id
        safe_id = str(pos_id).replace("-", "")[-8:]
        claim = pos.get("claim", "")

        anchors.append(Anchor(
            id=f"nf_position_{safe_id}",
            anchor_type=AnchorType.CANON,
            description=claim,
            severity=Severity.WARN,
            source="nonfiction_bridge",
        ))

    return anchors


def anchors_from_nonfiction_corpus(corpus_data: dict) -> list[Anchor]:
    """
    Master factory: build all nonfiction anchors from corpus data dict.

    Expected keys (all optional):
        concepts: list[dict]
        positions: list[dict]
    """
    anchors: list[Anchor] = []
    anchors.extend(anchors_from_concepts(corpus_data.get("concepts") or []))
    anchors.extend(anchors_from_positions(corpus_data.get("positions") or []))
    return anchors


# =============================================================================
# Puppet bridge
# =============================================================================


def anchors_from_puppet_profile(profile_dict: dict) -> list[Anchor]:
    """
    Build continuity anchors from a puppet profile dict.

    - voice.forbidden_phrases -> PERSONA anchor with forbidden_patterns (severity=CORRECT)
    - voice.required_ticks -> PERSONA anchor with required_patterns (severity=WARN)

    Skips if voice section is missing or both lists are empty.
    """
    puppet_id = profile_dict.get("puppet_id", "unknown")
    voice = profile_dict.get("voice") or {}
    anchors: list[Anchor] = []

    forbidden = voice.get("forbidden_phrases") or []
    if forbidden:
        anchors.append(Anchor(
            id=f"puppet_{puppet_id}_forbidden",
            anchor_type=AnchorType.PERSONA,
            description=f"Puppet '{puppet_id}': forbidden phrases",
            forbidden_patterns=list(forbidden),
            severity=Severity.CORRECT,
            source="puppet_bridge",
        ))

    required = voice.get("required_ticks") or []
    if required:
        anchors.append(Anchor(
            id=f"puppet_{puppet_id}_required",
            anchor_type=AnchorType.PERSONA,
            description=f"Puppet '{puppet_id}': required ticks",
            required_patterns=list(required),
            severity=Severity.WARN,
            source="puppet_bridge",
        ))

    return anchors
