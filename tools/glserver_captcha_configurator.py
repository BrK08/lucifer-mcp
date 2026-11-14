"""
glServer v1.6 — Captcha Solver Configurator & Diagnostic Helper
Helps users set up CapSolver, CapMonster, or Free Interactive mode for Google Login.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional


def find_glserver_dir(base_hint: Optional[str] = None) -> Optional[str]:
    candidates = []
    if base_hint and os.path.isdir(base_hint):
        candidates.append(base_hint)

    # Common Windows locations
    user_home = os.path.expanduser("~")
    candidates.extend([
        os.path.join(user_home, "Downloads", "glserver v1.6", "gl_server_1.6"),
        os.path.join(user_home, "Downloads", "gl_server_1.6"),
        os.path.join(user_home, "Desktop", "glserver v1.6", "gl_server_1.6"),
        os.path.join(user_home, "Desktop", "gl_server_1.6"),
        ".",
    ])

    for c in candidates:
        if os.path.isfile(os.path.join(c, "glServer.exe")):
            return os.path.abspath(c)
    return None


def configure_capsolver(gl_dir: str, api_key: str) -> bool:
    target_config = os.path.join(gl_dir, "capsolver", "assets", "config.json")
    if not os.path.isfile(target_config):
        alt = os.path.join(gl_dir, "capsolver", "config.json")
        if os.path.isfile(alt):
            target_config = alt

    data = {"apiKey": api_key, "appId": "glServer", "enabledForRecaptcha": True}
    os.makedirs(os.path.dirname(target_config), exist_ok=True)
    try:
        with open(target_config, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[OK] CapSolver API key saved to: {target_config}")
        print("-> In glServer.exe console, run: set selectedSolver 1")
        return True
    except Exception as e:
        print(f"[ERR] Could not write config: {e}")
        return False


def configure_capmonster(gl_dir: str, client_key: str) -> bool:
    target_config = os.path.join(gl_dir, "capmonster", "assets", "config.json")
    if not os.path.isfile(target_config):
        alt = os.path.join(gl_dir, "capmonster", "config.json")
        if os.path.isfile(alt):
            target_config = alt

    data = {"clientKey": client_key, "enabledForRecaptcha": True}
    os.makedirs(os.path.dirname(target_config), exist_ok=True)
    try:
        with open(target_config, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[OK] CapMonster ClientKey saved to: {target_config}")
        print("-> In glServer.exe console, run: set selectedSolver 2")
        return True
    except Exception as e:
        print(f"[ERR] Could not write config: {e}")
        return False


def print_free_interactive_guide():
    print("=" * 65)
    print("  GLSERVER v1.6 — UCRETSIZ & SIFIR MALIYETLI MANUEL COZUM MODU")
    print("=" * 65)
    print("API anahtari almaniza veya para odemenize GEREK YOKTUR!")
    print("\n1) glServer.exe konsol penceresini acin ve su 3 komutu girin:")
    print("   > set useHeadless False")
    print("   > set userInteraction True")
    print("   > set saveProfile True")
    print("\n2) Lucifer Multibot'ta Gmail botunuzu secip 'Connect' basin.")
    print("3) Ekranda Chrome/Edge tarayicisi acilacak ve Google Captcha soracaktir.")
    print("4) Ekranda cikan Captcha'yi elle cozun ve ilerleyin.")
    print("5) Giris tamamlandiginda oturum 'chrome' klasorune kaydedilir.")
    print("   -> Sonraki girislerde Google bu tarayiciyi tanir ve BIR DAHA CAPTCHA SORMAZ!")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="glServer Captcha Configurator")
    parser.add_argument("--dir", help="Path to gl_server_1.6 folder")
    parser.add_argument("--capsolver", help="CapSolver API Key (sets selectedSolver 1)")
    parser.add_argument("--capmonster", help="CapMonster ClientKey (sets selectedSolver 2)")
    parser.add_argument("--free", action="store_true", help="Print free manual mode commands")

    args = parser.parse_args()

    if args.free or (not args.capsolver and not args.capmonster):
        print_free_interactive_guide()
        return

    gl_dir = find_glserver_dir(args.dir)
    if not gl_dir:
        print("[!] Could not auto-locate gl_server_1.6 directory. Use --dir <path>")
        sys.exit(1)

    print(f"[*] Found glServer directory: {gl_dir}")

    if args.capsolver:
        configure_capsolver(gl_dir, args.capsolver)
    elif args.capmonster:
        configure_capmonster(gl_dir, args.capmonster)


if __name__ == "__main__":
    main()
