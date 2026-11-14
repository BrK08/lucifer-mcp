#!/usr/bin/env python3
"""
Lucifer Multibot MCP Server — Root Entrypoint (mr_berk edition)
Modeled for seamless stdio (Claude Desktop / Cursor / VS Code / Antigravity)
and Streamable HTTP (ChatGPT / Claude Web Connectors via start_mcp.py or --http).

Usage:
  python server.py                  # stdio MCP + background Relay on 8829
  python server.py --http           # Streamable HTTP MCP on 8828 + Relay on 8829
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from start_mcp import (  # noqa: E402
    _protect_stdio_stream,
    deploy_bridge_to_detected_dirs,
    load_server_config,
)


def main() -> None:
    srv_cfg = load_server_config()

    parser = argparse.ArgumentParser(
        description="Lucifer v2.88 p2 FastMCP Server (stdio default, or --http)"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run Streamable HTTP transport instead of stdio JSON-RPC",
    )
    parser.add_argument(
        "--host",
        default=str(srv_cfg.get("host") or "127.0.0.1"),
        help="Bind host for HTTP mode and local RelayServer (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        "--mcp-port",
        dest="mcp_port",
        type=int,
        default=int(srv_cfg.get("mcp_port") or 8828),
        help="HTTP port when running with --http (default: 8828)",
    )
    parser.add_argument(
        "--relay-port",
        type=int,
        default=int(srv_cfg.get("relay_port") or 8829),
        help="Lucifer HTTP Relay port (default: 8829)",
    )
    parser.add_argument(
        "--relay-url",
        default=None,
        help="Connect to an existing remote RelayServer URL instead of starting locally",
    )
    parser.add_argument(
        "--no-relay",
        action="store_true",
        help="Do not auto-start the local RelayServer",
    )
    args = parser.parse_args()

    if not args.http:
        _protect_stdio_stream()

    deployed = deploy_bridge_to_detected_dirs(quiet=True)
    if deployed:
        print(f"[LuciferMCP] Bridge synced to: {', '.join(deployed)}", file=sys.stderr)

    from mcp_server.server import (
        configure_external_relay_url,
        ensure_relay_started,
        mcp,
    )

    if args.relay_url:
        configure_external_relay_url(args.relay_url)
        print(f"[LuciferMCP] Using external relay: {args.relay_url}", file=sys.stderr)
    elif not args.no_relay:
        relay_info = ensure_relay_started(host=args.host, port=args.relay_port)
        print(
            f"[LuciferMCP] Relay mode={relay_info.get('mode')} url={relay_info.get('url')}",
            file=sys.stderr,
        )

    if args.http:
        print(
            f"[LuciferMCP] Starting FastMCP HTTP transport at http://{args.host}:{args.mcp_port}/mcp",
            file=sys.stderr,
        )
        mcp.run(transport="http", host=args.host, port=args.mcp_port)
    else:
        print("[LuciferMCP] Starting FastMCP stdio transport (ready).", file=sys.stderr)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
