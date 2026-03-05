# SPDX-License-Identifier: Apache-2.0
"""CuratedGroup: Click group with categorized help.

Shows a small curated set of commands by default, with a footer pointing
to ``--help-all`` for the full 100+ command list.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import click


# Curated categories — order matters (printed top to bottom).
# Commands listed here appear in the curated help; everything else is hidden
# behind --help-all.
CATEGORIES: OrderedDict[str, list[str]] = OrderedDict([
    ("Operator",  ["status", "doctor", "trace", "explain", "operator", "receipts", "check"]),
    ("Workflow",  ["init", "propose", "verify", "apply", "wrap", "serve", "ci"]),
    ("Config",    ["envelope", "profile", "intent", "session", "config"]),
    ("Debug",     ["rpc"]),
    ("Advanced",  ["advanced"]),
])

# Flat set for fast membership test
_CURATED_NAMES: set[str] = set()
for _names in CATEGORIES.values():
    _CURATED_NAMES.update(_names)


class CuratedGroup(click.Group):
    """Click group that shows categorized help by default.

    When ``ctx.obj["help_all"]`` is truthy, falls back to the standard
    flat listing (``super().format_commands()``).
    """

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        # If --help-all was passed, show everything
        obj = ctx.ensure_object(dict)
        if obj.get("help_all"):
            super().format_commands(ctx, formatter)
            return

        # Build curated sections
        commands = self.list_commands(ctx)
        cmd_map: dict[str, click.BaseCommand] = {}
        for name in commands:
            cmd = self.get_command(ctx, name)
            if cmd is not None:
                cmd_map[name] = cmd

        for category, names in CATEGORIES.items():
            rows: list[tuple[str, str]] = []
            for name in names:
                cmd = cmd_map.get(name)
                if cmd is None:
                    continue
                help_text = cmd.get_short_help_str(limit=formatter.width)
                rows.append((name, help_text))
            if rows:
                with formatter.section(category):
                    formatter.write_dl(rows)

        # Footer
        formatter.write_paragraph()
        formatter.write_text(
            "Run 'governor advanced --help' for all commands."
        )
