#!/usr/bin/env python3
"""
Lucifer v2.88 p2 MCP — One-Command Auto-Setup & Launcher (mr_berk edition)
==========================================================================
Run simply:
    python start_mcp.py

What it does automatically:
  1) Locates or creates a local `scripts/` folder (and any detected Lucifer script folder)
     and copies `bridge/lucifer_bridge.lua` into it.
  2) Starts (or attaches to) the Lucifer HTTP Relay on http://127.0.0.1:8829.
  3) Opens a free Cloudflare Quick Tunnel (`https://xxxx.trycloudflare.com/mcp`)
     if `cloudflared` is installed (unless `--no-tunnel` is passed).
  4) Prints ready-to-paste bilingual (EN + TR) URLs for ChatGPT, Claude, Gemini,
     Cursor, Antigravity, plus the 1-line Lucifer Executor bridge snippet.
  5) Starts the FastMCP Streamable HTTP server on http://127.0.0.1:8828/mcp.

Use `python start_mcp.py --stdio` for IDE / Claude Desktop stdio integration.
"""
from __future__ import annotations

import argparse
import builtins
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG_PATH = ROOT / "config.json"
EXAMPLE_CONFIG_PATH = ROOT / "config.example.json"
BRIDGE_SRC = ROOT / "bridge" / "lucifer_bridge.lua"


def load_server_config() -> dict:
    for path in (CONFIG_PATH, EXAMPLE_CONFIG_PATH):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data.get("server", {}) or {}
            except Exception:
                pass
    return {"host": "127.0.0.1", "mcp_port": 8828, "relay_port": 8829}


def detect_lucifer_script_dirs() -> List[Path]:
    """Finds local/user Lucifer script directories and ensures ROOT/scripts exists."""
    candidates: List[Path] = []

    env_dir = os.environ.get("LUCIFER_SCRIPT_DIR", "").strip()
    if env_dir:
        candidates.append(Path(env_dir))

    local_scripts = ROOT / "scripts"
    local_scripts.mkdir(parents=True, exist_ok=True)
    candidates.append(local_scripts)

    home = Path.home()
    for maybe in (
        home / "Desktop" / "Lucifer" / "scripts",
        home / "Desktop" / "lucifer" / "scripts",
        home / "Documents" / "Lucifer" / "scripts",
    ):
        if maybe.parent.is_dir():
            maybe.mkdir(parents=True, exist_ok=True)
            candidates.append(maybe)

    local_app = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app:
        gt_scripts = Path(local_app) / "Growtopia" / "Script"
        if gt_scripts.parent.is_dir() and gt_scripts.is_dir():
            candidates.append(gt_scripts)

    dedup: List[Path] = []
    seen = set()
    for p in candidates:
        try:
            resolved = str(p.resolve())
        except Exception:
            resolved = str(p)
        if resolved not in seen:
            seen.add(resolved)
            dedup.append(p)
    return dedup


def deploy_bridge_to_detected_dirs(quiet: bool = False) -> List[str]:
    """Copies bridge/lucifer_bridge.lua to detected script folders."""
    deployed: List[str] = []
    if not BRIDGE_SRC.exists():
        return deployed
    for folder in detect_lucifer_script_dirs():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            dst = folder / "lucifer_bridge.lua"
            shutil.copy2(BRIDGE_SRC, dst)
            deployed.append(str(dst))
        except Exception as e:
            if not quiet:
                print(f"[LuciferMCP] Bridge copy warning ({folder}): {e}", file=sys.stderr)
    return deployed


def start_cloudflared(port: int) -> Tuple[Optional[subprocess.Popen], Optional[str]]:
    """Starts cloudflared quick tunnel if installed and captures the HTTPS /mcp URL."""
    cf_bin = shutil.which("cloudflared")
    if not cf_bin:
        return None, None
    proc = subprocess.Popen(
        [cf_bin, "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    found_url: List[Optional[str]] = [None]

    def _reader() -> None:
        pat = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        if proc.stdout is None:
            return
        for line in proc.stdout:
            m = pat.search(line)
            if m and not found_url[0]:
                found_url[0] = m.group(0) + "/mcp"

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    for _ in range(30):
        if found_url[0] or proc.poll() is not None:
            break
        time.sleep(0.5)
    return proc, found_url[0]


def _protect_stdio_stream() -> None:
    """
    In stdio MCP mode, stdout is strictly reserved for JSON-RPC frames.
    Route all incidental print() calls and logging output to stderr so no
    dependency log or startup banner ever corrupts the MCP protocol stream.
    """
    orig_stdout = sys.stdout
    orig_print = builtins.print

    def _stderr_print(*args, **kwargs):
        target = kwargs.get("file")
        if target is None or target is orig_stdout:
            kwargs["file"] = sys.stderr
        return orig_print(*args, **kwargs)

    builtins.print = _stderr_print

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    root_logger.addHandler(stderr_handler)


def _print_connection_banner(
    host: str,
    mcp_port: int,
    relay_port: int,
    tunnel_url: Optional[str],
    lang: str = "both",
) -> None:
    local_mcp_url = f"http://{host}:{mcp_port}/mcp"
    bridge_url = f"http://127.0.0.1:{relay_port}/bridge.lua"
    oneliner = (
        f'local c = HttpClient.new(); c.url = "{bridge_url}"; '
        f"local r = c:request(); load(r and r.body or c.content)()"
    )

    print("\n" + "=" * 76)
    print("  LUCIFER v2.88 p2 MCP — READY TO CONNECT (mr_berk edition)")
    print("=" * 76)
    print(f"  Local MCP URL   : {local_mcp_url}")
    if tunnel_url:
        print(f"  Remote MCP URL  : {tunnel_url}   <-- Paste into ChatGPT / Claude Connectors!")
    else:
        print("  Remote Tunnel   : Not active (install `cloudflared` for ChatGPT/Claude Web HTTPS)")
    print("-" * 76)

    if lang in ("en", "both"):
        print("  [EN] IN-GAME BRIDGE SETUP (Run once in Lucifer -> Executor tab):")
        print(f"    {oneliner}")
        print("  [EN] Or open `scripts/lucifer_bridge.lua` inside Lucifer and press Execute.")
    if lang == "both":
        print("-" * 76)
    if lang in ("tr", "both"):
        print("  [TR] OYUN İÇİ KÖPRÜ KURULUMU (Lucifer -> Executor sekmesinde 1 kez çalıştır):")
        print(f"    {oneliner}")
        print("  [TR] Veya `scripts/lucifer_bridge.lua` dosyasını açıp Execute tuşuna bas.")
    print("=" * 76 + "\n")


def main() -> None:
    srv_cfg = load_server_config()

    parser = argparse.ArgumentParser(
        description="Lucifer v2.88 p2 MCP Auto-Setup & Launcher (HTTP + Tunnel default, or --stdio)"
    )
    transport_grp = parser.add_mutually_exclusive_group()
    transport_grp.add_argument(
        "--stdio",
        action="store_true",
        help="Run FastMCP over stdio JSON-RPC (for Claude Desktop / Cursor / Antigravity config)",
    )
    transport_grp.add_argument(
        "--http",
        action="store_true",
        help="Run FastMCP over Streamable HTTP transport (default when no transport flag is given)",
    )
    parser.add_argument(
        "--host",
        default=str(srv_cfg.get("host") or "127.0.0.1"),
        help="Bind host for HTTP mode and local RelayServer (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--mcp-port",
        "--port",
        dest="mcp_port",
        type=int,
        default=int(srv_cfg.get("mcp_port") or 8828),
        help="MCP HTTP port (default: 8828)",
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
    parser.add_argument(
        "--no-tunnel",
        action="store_true",
        help="Do not open a cloudflared HTTPS tunnel in HTTP mode",
    )
    parser.add_argument(
        "--lang",
        choices=("en", "tr", "both"),
        default="both",
        help="Language for terminal connection banner: en, tr, or both (default: both)",
    )
    args = parser.parse_args()

    use_stdio = bool(args.stdio)
    if use_stdio:
        _protect_stdio_stream()

    deployed_paths = deploy_bridge_to_detected_dirs(quiet=use_stdio)

    from mcp_server.server import (
        configure_external_relay_url,
        ensure_relay_started,
        mcp,
    )

    if use_stdio:
        if args.relay_url:
            configure_external_relay_url(args.relay_url)
            print(f"[LuciferMCP] Configured external relay: {args.relay_url}", file=sys.stderr)
        elif not args.no_relay:
            relay_info = ensure_relay_started(host=args.host, port=args.relay_port)
            print(
                f"[LuciferMCP] Relay mode={relay_info.get('mode')} url={relay_info.get('url')}",
                file=sys.stderr,
            )
        if deployed_paths:
            print(f"[LuciferMCP] Bridge copied to: {deployed_paths[0]}", file=sys.stderr)
        print("[LuciferMCP] Starting FastMCP stdio transport (ready for AI assistant).", file=sys.stderr)
        mcp.run(transport="stdio")
        return

    print("=" * 76)
    print("  LUCIFER MCP — ONE-COMMAND AUTO SETUP & LAUNCHER (mr_berk edition)")
    print("=" * 76)
    if deployed_paths:
        print(f"[1/4] Bridge deployed  : {', '.join(deployed_paths)}")
    else:
        print("[1/4] Bridge warning   : bridge/lucifer_bridge.lua not found")

    if args.relay_url:
        configure_external_relay_url(args.relay_url)
        print(f"[2/4] External Relay   : {args.relay_url}")
    elif not args.no_relay:
        relay_info = ensure_relay_started(host=args.host, port=args.relay_port)
        print(f"[2/4] Lucifer Relay    : {relay_info.get('url')} ({relay_info.get('mode')})")
    else:
        print("[2/4] Lucifer Relay    : Skipped (--no-relay)")

    cf_proc = None
    tunnel_url = None
    if not args.no_tunnel:
        print("[3/4] Cloudflare HTTPS : Starting quick tunnel for ChatGPT/Claude Web...")
        cf_proc, tunnel_url = start_cloudflared(args.mcp_port)
        if tunnel_url:
            print(f"      Tunnel Ready     : {tunnel_url}")
        else:
            print("      Note: `cloudflared` not found or tunnel timed out; local MCP endpoint is active.")
    else:
        print("[3/4] Cloudflare HTTPS : Skipped (--no-tunnel)")

    print(f"[4/4] FastMCP Server   : http://{args.host}:{args.mcp_port}/mcp")
    _print_connection_banner(args.host, args.mcp_port, args.relay_port, tunnel_url, lang=args.lang)

    try:
        mcp.run(transport="http", host=args.host, port=args.mcp_port)
    except KeyboardInterrupt:
        print("\n[LuciferMCP] Shutting down...")
    finally:
        if cf_proc and cf_proc.poll() is None:
            cf_proc.terminate()


if __name__ == "__main__":
    main()
