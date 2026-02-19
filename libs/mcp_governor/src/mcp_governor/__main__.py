# SPDX-License-Identifier: Apache-2.0
"""Entry point: python -m mcp_governor config.toml"""

from __future__ import annotations

import sys

from mcp_governor.config import GatewayConfig
from mcp_governor.gateway import StdioGateway


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m mcp_governor <config.toml>", file=sys.stderr)
        sys.exit(1)

    config_path = sys.argv[1]
    try:
        config = GatewayConfig.from_toml(config_path)
    except Exception as e:
        print(f"Failed to load config: {e}", file=sys.stderr)
        sys.exit(1)

    gateway = StdioGateway(config)
    try:
        gateway.run()
    except KeyboardInterrupt:
        print("[mcp-governor] Interrupted", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
