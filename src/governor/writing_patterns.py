# SPDX-License-Identifier: Apache-2.0
"""
Writing Patterns — Regex pattern banks for writing governance.

Pure data module: compiled regex patterns consumed by scorers and detectors.
Zero logic, just pattern definitions. All patterns are case-insensitive.

Pattern banks organized by source spec:
- fic.md: HEDGE, SELF_REFERENCE, APOLOGY_META, COMMITTEE, MEANING_WORD
- nonfic.md: NORMATIVE, CAUSAL_HUMILITY, FALSIFIER, STRAWMAN, ANXIETY_HEDGE, GOVERNANCE_ARTIFACT
- anc.md: INSTRUCTION_FILLER, FAKE_CONFIDENCE, PREMATURE_CLOSURE, BUREAUCRATIC
- tone.md: INSTITUTIONAL_MARKER
- writingconstraints.md: BAD_EXIT, INFLATED_WEIGHT
"""

from __future__ import annotations

import re
from typing import Pattern

# =============================================================================
# Fiction patterns (fic.md)
# =============================================================================

# Hedge patterns: reduce perceived risk (Rp) by 0.05 each
HEDGE_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bmaybe\b", re.IGNORECASE),
    re.compile(r"\bperhaps\b", re.IGNORECASE),
    re.compile(r"\bpossibly\b", re.IGNORECASE),
    re.compile(r"\bsort of\b", re.IGNORECASE),
    re.compile(r"\bkind of\b", re.IGNORECASE),
    re.compile(r"\bsomewhat\b", re.IGNORECASE),
    re.compile(r"\bslightly\b", re.IGNORECASE),
    re.compile(r"\ba bit\b", re.IGNORECASE),
    re.compile(r"\barguably\b", re.IGNORECASE),
    re.compile(r"\bin some ways\b", re.IGNORECASE),
    re.compile(r"\bto some extent\b", re.IGNORECASE),
    re.compile(r"\bI think\b", re.IGNORECASE),
    re.compile(r"\bI believe\b", re.IGNORECASE),
    re.compile(r"\bI feel like\b", re.IGNORECASE),
    re.compile(r"\bIt seems\b", re.IGNORECASE),
    re.compile(r"\bIt appears\b", re.IGNORECASE),
    re.compile(r"\bI guess\b", re.IGNORECASE),
    re.compile(r"\bI suppose\b", re.IGNORECASE),
]

# Self-reference patterns: kill perceived risk (Rp) by 0.15 each
SELF_REFERENCE_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bas an AI\b", re.IGNORECASE),
    re.compile(r"\bI'm just a\b", re.IGNORECASE),
    re.compile(r"\bI'm only a\b", re.IGNORECASE),
    re.compile(r"\bI don't have feelings\b", re.IGNORECASE),
    re.compile(r"\bI can't really\b", re.IGNORECASE),
    re.compile(r"\bI don't actually\b", re.IGNORECASE),
    re.compile(r"\bI'm not capable of\b", re.IGNORECASE),
    re.compile(r"\bI should note\b", re.IGNORECASE),
    re.compile(r"\bI should mention\b", re.IGNORECASE),
    re.compile(r"\bI want to be clear\b", re.IGNORECASE),
    re.compile(r"\bI need to point out\b", re.IGNORECASE),
]

# Apology/meta patterns: trigger hard block (no rewrite)
APOLOGY_META_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bsorry\b", re.IGNORECASE),
    re.compile(r"\bapologi", re.IGNORECASE),
    re.compile(r"\bmy bad\b", re.IGNORECASE),
    re.compile(r"\bmy mistake\b", re.IGNORECASE),
    re.compile(r"\bthat joke\b", re.IGNORECASE),
    re.compile(r"\bdidn't land\b", re.IGNORECASE),
    re.compile(r"\blet me try\b", re.IGNORECASE),
    re.compile(r"\bI shouldn't have\b", re.IGNORECASE),
    re.compile(r"\bthat was\b", re.IGNORECASE),
    re.compile(r"\bI'll do better\b", re.IGNORECASE),
    re.compile(r"\bforgive me\b", re.IGNORECASE),
]

# Committee/negotiation patterns: reduce Rp by 0.12 each
COMMITTEE_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bon the one hand\b", re.IGNORECASE),
    re.compile(r"\bon the other hand\b", re.IGNORECASE),
    re.compile(r"\bI'm not sure whether\b", re.IGNORECASE),
    re.compile(r"\bit could be seen as\b", re.IGNORECASE),
    re.compile(r"\bI don't want to make light of\b", re.IGNORECASE),
    re.compile(r"\bsome might say\b", re.IGNORECASE),
    re.compile(r"\bothers might argue\b", re.IGNORECASE),
    re.compile(r"\bthere are arguments\b", re.IGNORECASE),
    re.compile(r"\bit's complicated\b", re.IGNORECASE),
    re.compile(r"\bit depends on\b", re.IGNORECASE),
    re.compile(r"\bto be fair\b", re.IGNORECASE),
    re.compile(r"\bhaving said that\b", re.IGNORECASE),
    re.compile(r"\bthat said\b", re.IGNORECASE),
    re.compile(r"\bat the same time\b", re.IGNORECASE),
]

# Meaning words: used in tragedy, must lag suffering
MEANING_WORD_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bbecause\b", re.IGNORECASE),
    re.compile(r"\btherefore\b", re.IGNORECASE),
    re.compile(r"\bthus\b", re.IGNORECASE),
    re.compile(r"\bmeans\b", re.IGNORECASE),
    re.compile(r"\brepresents\b", re.IGNORECASE),
    re.compile(r"\bsymbolizes\b", re.IGNORECASE),
    re.compile(r"\blesson\b", re.IGNORECASE),
    re.compile(r"\bpurpose\b", re.IGNORECASE),
    re.compile(r"\breason\b", re.IGNORECASE),
    re.compile(r"\bunderstand\b", re.IGNORECASE),
    re.compile(r"\brealize\b", re.IGNORECASE),
    re.compile(r"\bsignifies\b", re.IGNORECASE),
    re.compile(r"\bthe point is\b", re.IGNORECASE),
    re.compile(r"\bwhat this shows\b", re.IGNORECASE),
    re.compile(r"\bthis teaches\b", re.IGNORECASE),
]

# Banned phrases: hard block in fiction
BANNED_PHRASES: list[str] = [
    "as an AI",
    "I should note",
    "I want to be clear",
    "to be fair",
    "I think it's important to",
    "I don't want to",
    "I hope that helps",
    "Let me know if",
]


# =============================================================================
# Nonfiction patterns (nonfic.md)
# =============================================================================

# Normative markers: detect should/must language
NORMATIVE_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bshould\b", re.IGNORECASE),
    re.compile(r"\bmust\b", re.IGNORECASE),
    re.compile(r"\bneed to\b", re.IGNORECASE),
    re.compile(r"\bought to\b", re.IGNORECASE),
    re.compile(r"\bhave to\b", re.IGNORECASE),
    re.compile(r"\bimperative\b", re.IGNORECASE),
    re.compile(r"\bessential\b", re.IGNORECASE),
    re.compile(r"\brequire[ds]?\b", re.IGNORECASE),
    re.compile(r"\bit is (?:important|crucial|vital|necessary)\b", re.IGNORECASE),
    re.compile(r"\bwe (?:need|must|should|have to)\b", re.IGNORECASE),
]

# Causal humility: raises Re (epistemic risk exposure)
CAUSAL_HUMILITY_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bcorrelat(?:ed?|ion)\b", re.IGNORECASE),
    re.compile(r"\bassociat(?:ed?|ion)\b", re.IGNORECASE),
    re.compile(r"\bsuggests but does not prove\b", re.IGNORECASE),
    re.compile(r"\bconsistent with\b", re.IGNORECASE),
    re.compile(r"\bwe cannot (?:conclude|determine)\b", re.IGNORECASE),
    re.compile(r"\bcausation.*unclear\b", re.IGNORECASE),
    re.compile(r"\bidentification (?:problem|challenge)\b", re.IGNORECASE),
    re.compile(r"\bconfound", re.IGNORECASE),
]

# Falsifier patterns: raises Re
FALSIFIER_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bthis (?:would|could) (?:break|fail) if\b", re.IGNORECASE),
    re.compile(r"\bthis (?:depends|relies) on\b", re.IGNORECASE),
    re.compile(r"\bif.*were (?:not |un)true\b", re.IGNORECASE),
    re.compile(r"\bwould falsify\b", re.IGNORECASE),
    re.compile(r"\bevidence against.*would (?:be|include)\b", re.IGNORECASE),
    re.compile(r"\bboundary condition\b", re.IGNORECASE),
    re.compile(r"\bscope limit\b", re.IGNORECASE),
    re.compile(r"\bdoes not apply (?:to|when)\b", re.IGNORECASE),
]

# Strawman indicators: bad alternative engagement
STRAWMAN_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bsome (?:people|argue|say) that\b", re.IGNORECASE),
    re.compile(r"\bthe (?:naive|simple|obvious) view\b", re.IGNORECASE),
    re.compile(r"\bone might (?:think|believe)\b", re.IGNORECASE),
    re.compile(r"\ba common mistake is\b", re.IGNORECASE),
    re.compile(r"\bcritics (?:often|sometimes|typically)\b", re.IGNORECASE),
]

# Anxiety hedges: lower Re
ANXIETY_HEDGE_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bI could be wrong\b", re.IGNORECASE),
    re.compile(r"\bthis is just my (?:opinion|view|take)\b", re.IGNORECASE),
    re.compile(r"\bI'm (?:not|no) expert\b", re.IGNORECASE),
    re.compile(r"\btake this with.*salt\b", re.IGNORECASE),
    re.compile(r"\byour mileage may vary\b", re.IGNORECASE),
    re.compile(r"\bI'm not (?:saying|claiming)\b", re.IGNORECASE),
    re.compile(r"\bdon't @ me\b", re.IGNORECASE),
    re.compile(r"\bplease don't\b", re.IGNORECASE),
]

# Governance artifacts: categorized by type (nonfic.md §5.1)
GOVERNANCE_ARTIFACT_PATTERNS: dict[str, list[Pattern[str]]] = {
    "preemptive_defense": [
        re.compile(r"\bbefore (?:you|anyone) (?:say|come|argue)\b", re.IGNORECASE),
        re.compile(r"\bI know (?:some|many) will disagree\b", re.IGNORECASE),
        re.compile(r"\bthis (?:may|might) be controversial\b", re.IGNORECASE),
    ],
    "virtue_seals": [
        re.compile(r"\bit'?s important to (?:acknowledge|recognize|note)\b", re.IGNORECASE),
        re.compile(r"\bwe must (?:acknowledge|recognize)\b", re.IGNORECASE),
        re.compile(r"\bI want to be clear that\b", re.IGNORECASE),
    ],
    "balance_theater": [
        re.compile(r"\bon the one hand.*on the other hand\b", re.IGNORECASE | re.DOTALL),
        re.compile(r"\bthere are valid points on both sides\b", re.IGNORECASE),
        re.compile(r"\breasonable people (?:can )?disagree\b", re.IGNORECASE),
    ],
    "empty_rigor": [
        re.compile(r"\bstudies show\b", re.IGNORECASE),
        re.compile(r"\bresearch indicates\b", re.IGNORECASE),
        re.compile(r"\bexperts agree\b", re.IGNORECASE),
    ],
    "responsible_framing": [
        re.compile(r"\bit would be irresponsible to\b", re.IGNORECASE),
        re.compile(r"\bwe have a responsibility to\b", re.IGNORECASE),
        re.compile(r"\bthe responsible view is\b", re.IGNORECASE),
    ],
    "meta_writing": [
        re.compile(r"\bit'?s important to say\b", re.IGNORECASE),
        re.compile(r"\bI need to be careful here\b", re.IGNORECASE),
        re.compile(r"\bthis requires nuance\b", re.IGNORECASE),
    ],
}


# =============================================================================
# Ancillary regime patterns (anc.md)
# =============================================================================

# Instruction filler: lowers actionability (Ap)
INSTRUCTION_FILLER_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bthis is a great way to\b", re.IGNORECASE),
    re.compile(r"\byou'll (?:love|enjoy|appreciate)\b", re.IGNORECASE),
    re.compile(r"\blet's (?:dive into|explore|get started)\b", re.IGNORECASE),
    re.compile(r"\bbefore we begin, (?:let me|I want to)\b", re.IGNORECASE),
    re.compile(r"\bit's (?:important|worth noting) that\b", re.IGNORECASE),
]

# Fake confidence: lowers actionability and trust
FAKE_CONFIDENCE_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bsimply\b", re.IGNORECASE),
    re.compile(r"\bjust\b", re.IGNORECASE),
    re.compile(r"\beasily\b", re.IGNORECASE),
    re.compile(r"\ball you (?:need to|have to) do\b", re.IGNORECASE),
    re.compile(r"\bit's (?:easy|simple|straightforward)\b", re.IGNORECASE),
]

# Premature closure: lowers fault isolation (Fi)
PREMATURE_CLOSURE_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bthe (?:problem|issue|cause) is\b", re.IGNORECASE),
    re.compile(r"\bclearly\b", re.IGNORECASE),
    re.compile(r"\bobviously\b", re.IGNORECASE),
    re.compile(r"\bthe only (?:solution|fix|answer)\b", re.IGNORECASE),
]

# Bureaucratic contamination
BUREAUCRATIC_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bpursuant to\b", re.IGNORECASE),
    re.compile(r"\bin accordance with\b", re.IGNORECASE),
    re.compile(r"\bas per (?:the|our)\b", re.IGNORECASE),
    re.compile(r"\bit is (?:the )?policy (?:of|that)\b", re.IGNORECASE),
    re.compile(r"\bstakeholders\b", re.IGNORECASE),
    re.compile(r"\bleverage (?:synergies|opportunities)\b", re.IGNORECASE),
    re.compile(r"\bgoing forward\b", re.IGNORECASE),
    re.compile(r"\bat this time\b", re.IGNORECASE),
    re.compile(r"\bplease be advised\b", re.IGNORECASE),
    re.compile(r"\bthis (?:communication|email|document) is\b", re.IGNORECASE),
]

# Good diagnostic patterns (raise Fi)
GOOD_DIAGNOSTIC_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bif.*then we (?:would|should) (?:see|expect)\b", re.IGNORECASE),
    re.compile(r"\bthis rules out\b", re.IGNORECASE),
    re.compile(r"\bthis is consistent with (?:but doesn't prove)\b", re.IGNORECASE),
    re.compile(r"\bhypothesis:?\s", re.IGNORECASE),
    re.compile(r"\bdifferential:?\s", re.IGNORECASE),
    re.compile(r"\bwe can (?:test|check|verify) by\b", re.IGNORECASE),
]

# Moralizing patterns (negotiation failure)
MORALIZING_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\byou (?:should|need to) (?:understand|realize|see)\b", re.IGNORECASE),
    re.compile(r"\bthe right thing to do\b", re.IGNORECASE),
    re.compile(r"\bmorally,\b", re.IGNORECASE),
    re.compile(r"\bit's (?:wrong|unfair) (?:that|to)\b", re.IGNORECASE),
    re.compile(r"\bhow could you\b", re.IGNORECASE),
]

# Gotcha patterns (negotiation failure)
GOTCHA_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bbut you (?:said|agreed|admitted)\b", re.IGNORECASE),
    re.compile(r"\bthat contradicts\b", re.IGNORECASE),
    re.compile(r"\bso (?:you're|you are) saying\b", re.IGNORECASE),
    re.compile(r"\bwhich is it\b", re.IGNORECASE),
    re.compile(r"\byou can't have it both ways\b", re.IGNORECASE),
]

# Manipulation patterns (negotiation failure)
MANIPULATION_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\blet me help you (?:see|understand)\b", re.IGNORECASE),
    re.compile(r"\bif you really cared\b", re.IGNORECASE),
    re.compile(r"\ba reasonable person would\b", re.IGNORECASE),
    re.compile(r"\bsurely you (?:can|must) (?:see|agree)\b", re.IGNORECASE),
    re.compile(r"\bdon't you think\b", re.IGNORECASE),
]


# =============================================================================
# Tone patterns (tone.md)
# =============================================================================

# Institutional markers categorized by voice type
INSTITUTIONAL_MARKER_PATTERNS: dict[str, list[Pattern[str]]] = {
    "hr_voice": [
        re.compile(r"\bprofessional(?:ly)?\b", re.IGNORECASE),
        re.compile(r"\bappropriate(?:ly)?\b", re.IGNORECASE),
        re.compile(r"\brespectful(?:ly)?\b", re.IGNORECASE),
        re.compile(r"\bconstructive(?:ly)?\b", re.IGNORECASE),
        re.compile(r"\bproductive(?:ly)?\b", re.IGNORECASE),
    ],
    "legal_voice": [
        re.compile(r"\bmeasured\b", re.IGNORECASE),
        re.compile(r"\bcareful(?:ly)?\b", re.IGNORECASE),
        re.compile(r"\bcautious(?:ly)?\b", re.IGNORECASE),
        re.compile(r"\bprudent(?:ly)?\b", re.IGNORECASE),
        re.compile(r"\badvisable\b", re.IGNORECASE),
    ],
    "committee_voice": [
        re.compile(r"\bbalanced\b", re.IGNORECASE),
        re.compile(r"\bnuanced\b", re.IGNORECASE),
        re.compile(r"\bcomprehensive(?:ly)?\b", re.IGNORECASE),
        re.compile(r"\bthorough(?:ly)?\b", re.IGNORECASE),
        re.compile(r"\bholistic(?:ally)?\b", re.IGNORECASE),
    ],
    "condescension_voice": [
        re.compile(r"\baccessible\b", re.IGNORECASE),
        re.compile(r"\bsimpl(?:e|y|ified)\b", re.IGNORECASE),
        re.compile(r"\beasy to understand\b", re.IGNORECASE),
        re.compile(r"\bfor (?:beginners|everyone)\b", re.IGNORECASE),
    ],
    "fear_voice": [
        re.compile(r"\bI (?:want|need) to be (?:clear|careful)\b", re.IGNORECASE),
        re.compile(r"\bI should (?:note|mention|acknowledge)\b", re.IGNORECASE),
        re.compile(r"\bwith (?:all )?(?:due )?respect\b", re.IGNORECASE),
        re.compile(r"\bI don't (?:want|mean) to\b", re.IGNORECASE),
    ],
}


# =============================================================================
# Structural constraint patterns (writingconstraints.md)
# =============================================================================

# Bad exit patterns: commitment escalation or empty gestures
BAD_EXIT_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bin conclusion\b", re.IGNORECASE),
    re.compile(r"\bto summarize\b", re.IGNORECASE),
    re.compile(r"\bhope (?:this|that) helps\b", re.IGNORECASE),
    re.compile(r"\blet me know if\b", re.IGNORECASE),
    re.compile(r"\bfeel free to\b", re.IGNORECASE),
    re.compile(r"\bdon't hesitate\b", re.IGNORECASE),
    re.compile(r"\bI hope (?:this|I've)\b", re.IGNORECASE),
    re.compile(r"\bwe must (?:all )?(?:act|do|remember)\b", re.IGNORECASE),
    re.compile(r"\bthe (?:important|key) (?:thing|point|takeaway) is\b", re.IGNORECASE),
]

# Inflated weight patterns: declaring importance instead of demonstrating
INFLATED_WEIGHT_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bit(?:'s| is) (?:important|crucial|vital|essential) (?:to|that)\b", re.IGNORECASE),
    re.compile(r"\bwe (?:must|need to) (?:remember|recognize|acknowledge)\b", re.IGNORECASE),
    re.compile(r"\bthis (?:matters|is significant) because\b", re.IGNORECASE),
    re.compile(r"\bthe stakes (?:are|here)\b", re.IGNORECASE),
    re.compile(r"\bI (?:need|want) to be (?:clear|careful|honest)\b", re.IGNORECASE),
]


# =============================================================================
# Utility functions
# =============================================================================


def count_pattern_matches(text: str, patterns: list[Pattern[str]]) -> int:
    """Count total number of pattern matches in text.

    Counts each match, not just each pattern (a pattern can match multiple times).
    """
    total = 0
    for pattern in patterns:
        total += len(pattern.findall(text))
    return total


def find_pattern_matches(text: str, patterns: list[Pattern[str]]) -> list[str]:
    """Find all pattern matches in text, returning matched strings."""
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(pattern.findall(text))
    return matches


def check_any_pattern(text: str, patterns: list[Pattern[str]]) -> bool:
    """Return True if any pattern matches in text."""
    for pattern in patterns:
        if pattern.search(text):
            return True
    return False


def count_categorized_patterns(
    text: str, categorized: dict[str, list[Pattern[str]]]
) -> dict[str, int]:
    """Count matches for each category in a categorized pattern dict."""
    return {
        category: count_pattern_matches(text, patterns)
        for category, patterns in categorized.items()
    }
