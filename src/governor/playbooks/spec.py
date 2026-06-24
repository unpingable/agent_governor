# SPDX-License-Identifier: Apache-2.0
"""Restricted-YAML parse → typed ``PlaybookSpec`` (Slice 0).

The authoring surface is a *restricted* YAML dialect: a friendly skin over a
typed AST, never a place where formatting becomes meaning. Unsupported
constructs **refuse with a typed error**; they are never silently coerced. The
restrictions enforced here (the dialect's load-bearing "no" list):

  * no anchors / aliases   (``&a`` / ``*a``)        → ``RestrictedYAMLError``
  * no merge keys          (``<<``)                  → ``RestrictedYAMLError``
  * no duplicate keys                                → ``RestrictedYAMLError``
  * no custom / non-safe tags (``!foo`` / ``!!python``) → ``RestrictedYAMLError``
  * string fields that arrive coerced (``name: yes`` → bool) are refused at the
    type gate → ``PlaybookSchemaError``  (a fuller no-implicit-resolver loader is
    deferred; Slice 0 enforces it at the typed boundary)

Slice 0 knows exactly one schema (``governed-playbook.v0``) and one shape:
``schema / kind / name / steps[{id, action, target}]``. Unknown keys, missing
keys, wrong types, and unknown schemas all refuse. No reactors, pipelines, or
imports — those are later slices and must not leak in by accident.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

SCHEMA_V0 = "governed-playbook.v0"
PARSER_VERSION = "playbook-parser.v0"

_TOP_KEYS = frozenset({"schema", "kind", "name", "steps"})
_STEP_KEYS = frozenset({"id", "action", "target"})

_MERGE_TAG = "tag:yaml.org,2002:merge"


class PlaybookError(Exception):
    """Base for all playbook-authoring refusals."""


class RestrictedYAMLError(PlaybookError):
    """The source used a YAML construct outside the restricted dialect."""


class PlaybookSchemaError(PlaybookError):
    """The (valid restricted-YAML) document does not match the playbook shape."""


class RestrictedSafeLoader(yaml.SafeLoader):
    """A SafeLoader that REFUSES the constructs the restricted dialect forbids.

    SafeLoader already refuses arbitrary/custom tags (``ConstructorError``); this
    subclass additionally refuses anchors, aliases, merge keys, and duplicate
    mapping keys — each of which SafeLoader otherwise accepts or silently
    resolves.
    """

    def compose_node(self, parent, index):  # type: ignore[override]
        # An alias references an anchor; reject before resolution.
        if self.check_event(yaml.events.AliasEvent):
            event = self.peek_event()
            raise RestrictedYAMLError(
                f"YAML aliases are not permitted (*{event.anchor})"
            )
        # The upcoming node's start event carries its anchor (pyyaml stores the
        # anchor on the event, not the composed node). Reject any anchored node.
        event = self.peek_event()
        if event is not None and getattr(event, "anchor", None) is not None:
            raise RestrictedYAMLError(
                f"YAML anchors are not permitted (&{event.anchor})"
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):  # type: ignore[override]
        # Merge keys would fold another mapping in implicitly — refuse.
        for key_node, _ in node.value:
            if getattr(key_node, "tag", None) == _MERGE_TAG:
                raise RestrictedYAMLError("YAML merge keys (<<) are not permitted")
        # Duplicate keys silently overwrite under SafeLoader — refuse instead.
        seen: set = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
            except TypeError as exc:
                raise RestrictedYAMLError(
                    f"non-scalar mapping key is not permitted: {key!r}"
                ) from exc
            if duplicate:
                raise RestrictedYAMLError(f"duplicate mapping key: {key!r}")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


@dataclass(frozen=True)
class PlaybookStep:
    id: str
    action: str
    target: str


@dataclass(frozen=True)
class PlaybookSpec:
    schema: str
    kind: str
    name: str
    steps: tuple[PlaybookStep, ...]


def _require_str(value: object, field: str) -> str:
    # NOTE: bool is an int subclass but not a str, so ``name: true`` (coerced to
    # a YAML bool) is refused here — the implicit-bool guard at the typed boundary.
    if not isinstance(value, str):
        raise PlaybookSchemaError(
            f"{field} must be a string, got {type(value).__name__}: {value!r}"
        )
    return value


def parse_playbook(source: str | bytes) -> PlaybookSpec:
    """Parse restricted-YAML ``source`` into a typed ``PlaybookSpec``, or refuse.

    Raises ``RestrictedYAMLError`` for dialect violations and
    ``PlaybookSchemaError`` for shape/type violations. Never returns a partial or
    coerced spec.
    """
    try:
        data = yaml.load(source, Loader=RestrictedSafeLoader)  # noqa: S506 - restricted loader
    except PlaybookError:
        raise
    except yaml.constructor.ConstructorError as exc:
        # Unknown / unsafe tags (``!foo``, ``!!python/...``) land here.
        raise RestrictedYAMLError(f"unsupported YAML tag/construct: {exc}") from exc
    except yaml.YAMLError as exc:
        raise PlaybookSchemaError(f"invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise PlaybookSchemaError(
            f"playbook must be a mapping at the top level, got "
            f"{type(data).__name__}"
        )

    keys = set(data)
    unknown = keys - _TOP_KEYS
    if unknown:
        raise PlaybookSchemaError(f"unknown top-level key(s): {sorted(unknown)}")
    missing = _TOP_KEYS - keys
    if missing:
        raise PlaybookSchemaError(f"missing required key(s): {sorted(missing)}")

    schema = _require_str(data["schema"], "schema")
    if schema != SCHEMA_V0:
        raise PlaybookSchemaError(
            f"unsupported schema {schema!r}; this parser knows only {SCHEMA_V0!r}"
        )
    kind = _require_str(data["kind"], "kind")
    name = _require_str(data["name"], "name")

    raw_steps = data["steps"]
    if not isinstance(raw_steps, list):
        raise PlaybookSchemaError(
            f"steps must be a list, got {type(raw_steps).__name__}"
        )
    if not raw_steps:
        raise PlaybookSchemaError("steps must be a non-empty list")

    steps: list[PlaybookStep] = []
    for i, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise PlaybookSchemaError(
                f"step[{i}] must be a mapping, got {type(raw).__name__}"
            )
        sk = set(raw)
        unknown_sk = sk - _STEP_KEYS
        if unknown_sk:
            raise PlaybookSchemaError(
                f"step[{i}] has unknown key(s): {sorted(unknown_sk)}"
            )
        missing_sk = _STEP_KEYS - sk
        if missing_sk:
            raise PlaybookSchemaError(
                f"step[{i}] is missing key(s): {sorted(missing_sk)}"
            )
        steps.append(
            PlaybookStep(
                id=_require_str(raw["id"], f"step[{i}].id"),
                action=_require_str(raw["action"], f"step[{i}].action"),
                target=_require_str(raw["target"], f"step[{i}].target"),
            )
        )

    return PlaybookSpec(schema=schema, kind=kind, name=name, steps=tuple(steps))
