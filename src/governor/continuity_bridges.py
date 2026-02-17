# SPDX-License-Identifier: Apache-2.0
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


def anchors_from_canon_events(events: list[dict]) -> list[Anchor]:
    """
    Build continuity anchors from canon event dicts.

    Each event becomes a CANON anchor (prompt enrichment only, no pattern
    matching -- lexical matching can't reliably detect contradiction of
    semantic facts).

    Expected dict keys: chapter, summary, characters, location, establishes.
    Skips events with empty summary.
    """
    anchors: list[Anchor] = []
    for idx, event in enumerate(events):
        summary = event.get("summary", "")
        if not summary:
            continue

        chapter = event.get("chapter", "?")
        characters = event.get("characters") or []
        location = event.get("location", "")
        establishes = event.get("establishes") or []

        desc = f"Chapter {chapter}: {summary}"
        if characters:
            desc += f". Characters: {', '.join(characters)}"
        if location:
            desc += f". Location: {location}"
        if establishes:
            desc += f". Establishes: {', '.join(establishes)}"

        anchors.append(Anchor(
            id=f"fiction_canon_event_{chapter}_{idx}",
            anchor_type=AnchorType.CANON,
            description=desc,
            severity=Severity.WARN,
            source="fiction_bridge",
        ))

    return anchors


def anchors_from_relationships(relationships: list[dict]) -> list[Anchor]:
    """
    Build continuity anchors from relationship dicts.

    Each relationship becomes a CANON anchor (prompt enrichment only).
    ID uses sorted character names for deterministic ordering.

    Expected dict keys: character_a, character_b, type, as_of_chapter, dynamics.
    Skips entries missing character_a or character_b.
    """
    anchors: list[Anchor] = []
    for rel in relationships:
        char_a = rel.get("character_a", "")
        char_b = rel.get("character_b", "")
        if not char_a or not char_b:
            continue

        rel_type = rel.get("type", "related")
        as_of = rel.get("as_of_chapter", "")
        dynamics = rel.get("dynamics") or []

        desc = f"{char_a} and {char_b}: {rel_type}"
        if as_of:
            desc += f" (as of chapter {as_of})"
        if dynamics:
            desc += f". Dynamics: {', '.join(dynamics)}"

        sorted_pair = sorted([char_a.lower().replace(" ", "_"),
                              char_b.lower().replace(" ", "_")])
        anchor_id = f"fiction_rel_{sorted_pair[0]}_{sorted_pair[1]}"

        anchors.append(Anchor(
            id=anchor_id,
            anchor_type=AnchorType.CANON,
            description=desc,
            severity=Severity.WARN,
            source="fiction_bridge",
        ))

    return anchors


_INACTIVE_THREAD_STATUSES = {"resolved", "abandoned"}


def anchors_from_plot_threads(threads: list[dict]) -> list[Anchor]:
    """
    Build continuity anchors from plot thread dicts.

    Only active threads become REQUIREMENT anchors (threads are narrative
    obligations, not just established facts). Threads with status in
    {"resolved", "abandoned"} are skipped.

    Expected dict keys: name, type, status, planted_chapter, characters,
                        payoff_deadline.
    """
    anchors: list[Anchor] = []
    for thread in threads:
        status = (thread.get("status") or "").lower()
        if status in _INACTIVE_THREAD_STATUSES:
            continue

        name = thread.get("name", "unknown")
        safe_name = name.lower().replace(" ", "_")
        thread_type = thread.get("type", "")
        planted = thread.get("planted_chapter", "")
        characters = thread.get("characters") or []
        deadline = thread.get("payoff_deadline", "")

        desc = f"Plot thread '{name}'"
        if thread_type:
            desc += f" ({thread_type})"
        if planted:
            desc += f", planted chapter {planted}"
        if characters:
            desc += f". Characters: {', '.join(characters)}"
        if deadline:
            desc += f". Payoff deadline: chapter {deadline}"
            # Check overdue: if planted chapter is known, compare
            if planted:
                try:
                    if int(planted) < int(deadline):
                        pass  # not overdue yet by definition
                except (ValueError, TypeError):
                    pass

        anchors.append(Anchor(
            id=f"fiction_thread_{safe_name}",
            anchor_type=AnchorType.REQUIREMENT,
            description=desc,
            severity=Severity.WARN,
            source="fiction_bridge",
        ))

    return anchors


def anchors_from_code_decisions(decisions: list[dict]) -> list[Anchor]:
    """
    Build continuity anchors from governor decision dicts.

    Only active decisions (not superseded) become CANON anchors (prompt
    enrichment only). Handles supersession filtering internally.

    Expected dict keys: topic, choice, rationale, superseded_by.
    Skips entries with no topic.
    """
    anchors: list[Anchor] = []
    for dec in decisions:
        topic = dec.get("topic", "")
        if not topic:
            continue
        # Skip superseded decisions
        if dec.get("superseded_by") is not None:
            continue

        safe_topic = topic.lower().replace(" ", "_")
        choice = dec.get("choice", "")
        rationale = dec.get("rationale", "")

        desc = f"Decision: {topic}"
        if choice:
            desc += f" = {choice}"
        if rationale:
            desc += f". Rationale: {rationale}"

        anchors.append(Anchor(
            id=f"code_decision_{safe_topic}",
            anchor_type=AnchorType.CANON,
            description=desc,
            severity=Severity.WARN,
            source="code_bridge",
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
        canon_events: list[dict]
        relationships: list[dict]
        threads: list[dict]
    """
    anchors: list[Anchor] = []
    anchors.extend(anchors_from_characters(bible_data.get("characters") or []))
    anchors.extend(anchors_from_banned_tropes(bible_data.get("banned_tropes") or []))
    anchors.extend(anchors_from_world_rules(bible_data.get("world_rules") or []))

    tone = bible_data.get("tone")
    if tone:
        anchors.extend(anchors_from_tone_settings(tone))

    anchors.extend(anchors_from_canon_events(bible_data.get("canon_events") or []))
    anchors.extend(anchors_from_relationships(bible_data.get("relationships") or []))
    anchors.extend(anchors_from_plot_threads(bible_data.get("threads") or []))

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


# =============================================================================
# Writing module bridges (W5g)
# =============================================================================


def anchors_from_governance_rules(regime: str) -> list[Anchor]:
    """
    Build continuity anchors from governance rules for a regime.

    Creates PROHIBITION anchors that catch governance visibility artifacts
    (banned phrases, institutional markers) that should never appear in output.
    These are patterns that violate the meta-constraint: governance must
    never surface in-band.

    Args:
        regime: The active writing regime (e.g., "comedy", "research", "instruction")

    Returns:
        List of PROHIBITION anchors with severity=CORRECT
    """
    from .writing_patterns import (
        APOLOGY_META_PATTERNS,
        COMMITTEE_PATTERNS,
        SELF_REFERENCE_PATTERNS,
    )

    anchors: list[Anchor] = []
    regime_lower = regime.lower()

    # Core governance patterns that apply to all regimes
    # These are patterns that reveal the author is managing the audience
    forbidden_patterns: list[str] = []

    # Self-reference patterns are always forbidden (reveal AI nature)
    for pattern in SELF_REFERENCE_PATTERNS:
        forbidden_patterns.append(pattern.pattern)

    # For fiction regimes, committee patterns kill perceived risk
    fiction_regimes = {"comedy", "tragedy", "horror", "romance", "drama", "sincerity"}
    if regime_lower in fiction_regimes:
        for pattern in COMMITTEE_PATTERNS[:5]:  # Most egregious ones
            forbidden_patterns.append(pattern.pattern)
        for pattern in APOLOGY_META_PATTERNS[:5]:  # Meta patterns kill fiction
            forbidden_patterns.append(pattern.pattern)

    if forbidden_patterns:
        anchors.append(Anchor(
            id=f"writing_governance_{regime_lower}",
            anchor_type=AnchorType.PROHIBITION,
            description=f"Governance artifacts forbidden in {regime} regime",
            forbidden_patterns=forbidden_patterns,
            severity=Severity.CORRECT,
            source="writing_bridge",
        ))

    return anchors


def anchors_from_tone_envelope(regime: str) -> list[Anchor]:
    """
    Build continuity anchors from tone envelope for a regime.

    Creates STYLE anchors with envelope descriptions as prompt enrichment.
    These inform the LLM of the appropriate tone range but don't pattern match.

    Args:
        regime: The active writing regime

    Returns:
        List of STYLE anchors with severity=WARN (prompt enrichment only)
    """
    from .writing_tone import REGIME_ENVELOPES

    anchors: list[Anchor] = []
    regime_lower = regime.lower()

    envelope = REGIME_ENVELOPES.get(regime_lower)
    if envelope:
        # Format envelope as guidance
        desc_parts = [f"Tone envelope for {regime_lower}:"]
        dim_names = ["formality", "temperature", "density", "velocity", "distance", "certainty"]
        for name in dim_names:
            bounds = getattr(envelope, name)
            desc_parts.append(f"  {name}: {bounds[0]:.1f}-{bounds[1]:.1f}")

        anchors.append(Anchor(
            id=f"writing_tone_{regime_lower}",
            anchor_type=AnchorType.STYLE,
            description="\n".join(desc_parts),
            severity=Severity.WARN,
            source="writing_bridge",
        ))

    return anchors


def anchors_from_regime_constraints(regime: str) -> list[Anchor]:
    """
    Build continuity anchors from per-regime constraints.

    Creates PROHIBITION/REQUIREMENT anchors from regime-specific failure modes
    and constraint patterns.

    Args:
        regime: The active writing regime

    Returns:
        List of anchors capturing regime-specific constraints
    """
    from .writing_patterns import (
        BAD_EXIT_PATTERNS,
        FAKE_CONFIDENCE_PATTERNS,
        HEDGE_PATTERNS,
        PREMATURE_CLOSURE_PATTERNS,
    )

    anchors: list[Anchor] = []
    regime_lower = regime.lower()

    # Regime-specific patterns
    if regime_lower in {"comedy", "horror", "romance"}:
        # Fiction regimes: hedges kill perceived risk
        # Use fewer patterns for targeted enforcement
        hedge_patterns = [p.pattern for p in HEDGE_PATTERNS[:6]]
        anchors.append(Anchor(
            id=f"writing_constraint_{regime_lower}_hedges",
            anchor_type=AnchorType.STYLE,
            description=f"Excessive hedging reduces impact in {regime_lower} regime",
            forbidden_patterns=hedge_patterns,
            severity=Severity.WARN,
            source="writing_bridge",
        ))

    if regime_lower == "horror":
        # Horror: premature closure kills unresolved threat
        closure_patterns = [p.pattern for p in PREMATURE_CLOSURE_PATTERNS]
        anchors.append(Anchor(
            id="writing_constraint_horror_closure",
            anchor_type=AnchorType.PROHIBITION,
            description="Premature closure kills horror tension",
            forbidden_patterns=closure_patterns,
            severity=Severity.WARN,
            source="writing_bridge",
        ))

    if regime_lower in {"instruction", "debugging"}:
        # Instruction/debugging: fake confidence undermines trust
        fake_patterns = [p.pattern for p in FAKE_CONFIDENCE_PATTERNS]
        anchors.append(Anchor(
            id=f"writing_constraint_{regime_lower}_fake_confidence",
            anchor_type=AnchorType.PROHIBITION,
            description="Fake confidence reduces actionability",
            forbidden_patterns=fake_patterns,
            severity=Severity.WARN,
            source="writing_bridge",
        ))

    # Bad exit patterns apply to all regimes
    exit_patterns = [p.pattern for p in BAD_EXIT_PATTERNS]
    anchors.append(Anchor(
        id=f"writing_constraint_{regime_lower}_exit",
        anchor_type=AnchorType.PROHIBITION,
        description="Bad exit patterns damage lasting impression",
        forbidden_patterns=exit_patterns,
        severity=Severity.WARN,
        source="writing_bridge",
    ))

    return anchors


def anchors_from_structural_constraints(regime: str) -> list[Anchor]:
    """
    Build continuity anchors from structural constraints.

    Creates anchors from the 11 structural constraint categories
    (audience, commitment, authority, silence, repetition, error posture,
    exit shape, temporal consistency, moral weight, legibility, premature solution).

    Args:
        regime: The active writing regime

    Returns:
        List of anchors for structural constraints
    """
    from .writing_patterns import INFLATED_WEIGHT_PATTERNS

    anchors: list[Anchor] = []
    regime_lower = regime.lower()

    # Moral weight inflation applies to all regimes
    weight_patterns = [p.pattern for p in INFLATED_WEIGHT_PATTERNS]
    anchors.append(Anchor(
        id=f"writing_structural_{regime_lower}_weight",
        anchor_type=AnchorType.STYLE,
        description="Inflated moral weight damages credibility",
        forbidden_patterns=weight_patterns,
        severity=Severity.WARN,
        source="writing_bridge",
    ))

    return anchors


def anchors_from_writing_modules(
    regime: str,
    include_governance: bool = True,
    include_tone: bool = True,
    include_regime_constraints: bool = True,
    include_structural: bool = True,
) -> list[Anchor]:
    """
    Master factory: build all writing module anchors for a regime.

    Combines governance rules, tone envelopes, regime constraints, and
    structural constraints into a unified anchor list.

    Args:
        regime: The active writing regime
        include_governance: Whether to include governance visibility anchors
        include_tone: Whether to include tone envelope anchors
        include_regime_constraints: Whether to include regime-specific constraints
        include_structural: Whether to include structural constraints

    Returns:
        Combined list of anchors from all writing modules
    """
    anchors: list[Anchor] = []

    if include_governance:
        anchors.extend(anchors_from_governance_rules(regime))
    if include_tone:
        anchors.extend(anchors_from_tone_envelope(regime))
    if include_regime_constraints:
        anchors.extend(anchors_from_regime_constraints(regime))
    if include_structural:
        anchors.extend(anchors_from_structural_constraints(regime))

    return anchors
