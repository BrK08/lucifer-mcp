"""
Multi-Tenant Token & Identity Manager for Lucifer Cloud Relay & Discord Bot.
Maps each Discord user (owner_id) to an isolated bridge token (luci_...)
so hundreds of users can safely control only their own Lucifer bots.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_TENANT_PATH = Path(__file__).resolve().parent.parent / "data" / "user_tenants.json"


class TenantManager:
    """Thread-safe persistent mapping between Discord owner_id and bridge tokens."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = Path(storage_path) if storage_path else DEFAULT_TENANT_PATH
        self._lock = threading.RLock()
        self._users: Dict[str, Dict[str, Any]] = {}
        self._token_to_user: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            self._users.clear()
            self._token_to_user.clear()
            if not self.storage_path.exists():
                return
            try:
                raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
                users = raw.get("users", {}) if isinstance(raw, dict) else {}
                if isinstance(users, dict):
                    for uid, rec in users.items():
                        if not isinstance(rec, dict):
                            continue
                        token = str(rec.get("token", "")).strip()
                        secret_key = str(rec.get("secret_key", "")).strip().upper()
                        uid_str = str(uid).strip()
                        if not uid_str or not token:
                            continue
                        if not secret_key:
                            secret_key = self._new_secret_key()
                        self._users[uid_str] = {
                            "owner_id": uid_str,
                            "token": token,
                            "secret_key": secret_key,
                            "alias": str(rec.get("alias", "")),
                            "lang": "tr" if str(rec.get("lang", "en")).lower().startswith("tr") else "en",
                            "created_at": float(rec.get("created_at", 0.0) or 0.0),
                            "updated_at": float(rec.get("updated_at", 0.0) or 0.0),
                            "last_seen_at": float(rec.get("last_seen_at", 0.0) or 0.0),
                        }
                        self._token_to_user[token] = uid_str
                        self._token_to_user[secret_key] = uid_str
                        self._token_to_user[secret_key.lower()] = uid_str
            except Exception:
                self._users = {}
                self._token_to_user = {}

    def _save(self) -> None:
        with self._lock:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "updated_at": time.time(),
                "users": self._users,
            }
            tmp_path = self.storage_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp_path, self.storage_path)

    @staticmethod
    def _new_token() -> str:
        return f"luci_{secrets.token_urlsafe(24)}"

    @staticmethod
    def _new_secret_key() -> str:
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        return f"LUCI-{part1}-{part2}"

    def get_or_create_token(self, owner_id: str, alias: str = "") -> str:
        """Return existing token for owner_id or generate a fresh unique token."""
        uid = str(owner_id or "").strip()
        if not uid:
            raise ValueError("owner_id cannot be empty")
        with self._lock:
            existing = self._users.get(uid)
            if existing and existing.get("token"):
                dirty = False
                if not existing.get("secret_key"):
                    sk = self._new_secret_key()
                    while sk in self._token_to_user:
                        sk = self._new_secret_key()
                    existing["secret_key"] = sk
                    self._token_to_user[sk] = uid
                    self._token_to_user[sk.lower()] = uid
                    dirty = True
                if alias and alias != existing.get("alias"):
                    existing["alias"] = str(alias)
                    dirty = True
                if dirty:
                    existing["updated_at"] = time.time()
                    self._save()
                return str(existing["token"])

            now = time.time()
            token = self._new_token()
            while token in self._token_to_user:
                token = self._new_token()

            secret_key = self._new_secret_key()
            while secret_key in self._token_to_user:
                secret_key = self._new_secret_key()

            self._users[uid] = {
                "owner_id": uid,
                "token": token,
                "secret_key": secret_key,
                "alias": str(alias or ""),
                "lang": "en",
                "created_at": now,
                "updated_at": now,
                "last_seen_at": 0.0,
            }
            self._token_to_user[token] = uid
            self._token_to_user[secret_key] = uid
            self._token_to_user[secret_key.lower()] = uid
            self._save()
            return token

    def get_or_create_secret_key(self, owner_id: str, alias: str = "") -> str:
        """Return personal short secret key (LUCI-XXXX-XXXX) for owner_id, creating if missing."""
        uid = str(owner_id or "").strip()
        if not uid:
            raise ValueError("owner_id cannot be empty")
        with self._lock:
            self.get_or_create_token(uid, alias=alias)
            rec = self._users.get(uid, {})
            sk = str(rec.get("secret_key", "")).strip().upper()
            if not sk:
                sk = self._new_secret_key()
                while sk in self._token_to_user:
                    sk = self._new_secret_key()
                rec["secret_key"] = sk
                self._token_to_user[sk] = uid
                self._token_to_user[sk.lower()] = uid
                rec["updated_at"] = time.time()
                self._save()
            return sk

    def regenerate_token(self, owner_id: str, alias: str = "") -> str:
        """Revoke old token & secret_key for owner_id and issue brand new ones."""
        uid = str(owner_id or "").strip()
        if not uid:
            raise ValueError("owner_id cannot be empty")
        with self._lock:
            existing = self._users.get(uid)
            if existing:
                old_token = existing.get("token")
                if old_token and self._token_to_user.get(old_token) == uid:
                    self._token_to_user.pop(old_token, None)
                old_sk = str(existing.get("secret_key", "")).strip()
                if old_sk:
                    if self._token_to_user.get(old_sk) == uid:
                        self._token_to_user.pop(old_sk, None)
                    if self._token_to_user.get(old_sk.lower()) == uid:
                        self._token_to_user.pop(old_sk.lower(), None)
            now = time.time()
            new_token = self._new_token()
            while new_token in self._token_to_user:
                new_token = self._new_token()

            new_secret = self._new_secret_key()
            while new_secret in self._token_to_user:
                new_secret = self._new_secret_key()

            created_at = float(existing.get("created_at", now)) if existing else now
            final_alias = str(alias or (existing.get("alias", "") if existing else ""))
            final_lang = str(existing.get("lang", "en")) if existing else "en"
            self._users[uid] = {
                "owner_id": uid,
                "token": new_token,
                "secret_key": new_secret,
                "alias": final_alias,
                "lang": "tr" if final_lang.lower().startswith("tr") else "en",
                "created_at": created_at,
                "updated_at": now,
                "last_seen_at": float(existing.get("last_seen_at", 0.0)) if existing else 0.0,
            }
            self._token_to_user[new_token] = uid
            self._token_to_user[new_secret] = uid
            self._token_to_user[new_secret.lower()] = uid
            self._save()
            return new_token

    def get_token(self, owner_id: str) -> Optional[str]:
        """Return token for owner_id if already registered."""
        uid = str(owner_id or "").strip()
        if not uid:
            return None
        with self._lock:
            rec = self._users.get(uid)
            return str(rec["token"]) if rec and rec.get("token") else None

    def get_user_record(self, owner_id: str) -> Optional[Dict[str, Any]]:
        """Return a safe copy of tenant metadata for owner_id."""
        uid = str(owner_id or "").strip()
        if not uid:
            return None
        with self._lock:
            rec = self._users.get(uid)
            return dict(rec) if rec else None

    def resolve_user_by_token(self, token: Optional[str]) -> Optional[str]:
        """Resolve an incoming bridge owner_token or short secret_key to its Discord owner_id."""
        tok = str(token or "").strip()
        if not tok:
            return None
        with self._lock:
            uid = self._token_to_user.get(tok) or self._token_to_user.get(tok.upper())
            if not uid:
                return None
            rec = self._users.get(uid)
            if rec is not None:
                rec["last_seen_at"] = time.time()
            return uid

    def is_valid_token(self, token: Optional[str]) -> bool:
        """Check whether token maps to a known tenant."""
        return self.resolve_user_by_token(token) is not None

    def set_user_alias(self, owner_id: str, alias: str) -> None:
        """Update stored display alias for a registered owner_id."""
        uid = str(owner_id or "").strip()
        if not uid:
            return
        with self._lock:
            rec = self._users.get(uid)
            if rec is None:
                self.get_or_create_token(uid, alias=alias)
                return
            rec["alias"] = str(alias or "")
            rec["updated_at"] = time.time()
            self._save()

    @staticmethod
    def _normalize_lang(lang: Optional[str], default: str = "en") -> str:
        raw = str(lang or "").strip().lower()
        if raw.startswith("tr") or raw.startswith("türk") or raw.startswith("turk"):
            return "tr"
        if raw.startswith("en") or raw.startswith("ing"):
            return "en"
        return "tr" if str(default).lower().startswith("tr") else "en"

    def get_user_lang(self, owner_id: Optional[str], default: str = "en") -> str:
        """Return preferred UI language ('en' or 'tr') for owner_id, defaulting to 'en'."""
        fallback = self._normalize_lang(default, default="en")
        uid = str(owner_id or "").strip()
        if not uid:
            return fallback
        with self._lock:
            rec = self._users.get(uid)
            if not rec:
                return fallback
            return self._normalize_lang(rec.get("lang"), default=fallback)

    def set_user_lang(self, owner_id: str, lang: str, alias: str = "") -> str:
        """Persist preferred UI language ('en' or 'tr') for owner_id and return normalized code."""
        uid = str(owner_id or "").strip()
        norm = self._normalize_lang(lang, default="en")
        if not uid:
            return norm
        with self._lock:
            rec = self._users.get(uid)
            if rec is None:
                self.get_or_create_token(uid, alias=alias)
                rec = self._users.get(uid)
            if rec is not None:
                rec["lang"] = norm
                if alias and not rec.get("alias"):
                    rec["alias"] = str(alias)
                rec["updated_at"] = time.time()
                self._save()
        return norm

    def list_tenants(self) -> List[Dict[str, Any]]:
        """Return tenant metadata without exposing raw bridge tokens."""
        with self._lock:
            results: List[Dict[str, Any]] = []
            for rec in self._users.values():
                tok = str(rec.get("token", ""))
                masked = f"{tok[:9]}...{tok[-4:]}" if len(tok) > 14 else "***"
                results.append(
                    {
                        "owner_id": rec.get("owner_id", ""),
                        "alias": rec.get("alias", ""),
                        "token_preview": masked,
                        "created_at": rec.get("created_at", 0.0),
                        "updated_at": rec.get("updated_at", 0.0),
                        "last_seen_at": rec.get("last_seen_at", 0.0),
                    }
                )
            return results

    def get_stats(self) -> Dict[str, Any]:
        """Return high-level multi-tenant usage metrics."""
        now = time.time()
        with self._lock:
            total = len(self._users)
            active_24h = sum(
                1 for r in self._users.values()
                if now - float(r.get("last_seen_at", 0.0) or 0.0) <= 86400
            )
            return {
                "total_tenants": total,
                "active_last_24h": active_24h,
            }


tenant_manager = TenantManager()


_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{4,128}$")
_SAFE_URL_RE = re.compile(r"^https?://[A-Za-z0-9.\-:]{1,180}(?:/[A-Za-z0-9._~/-]*)?$")


def sanitize_bridge_token(token: Optional[str]) -> str:
    """Allow only URL-safe ASCII token characters before injecting into Lua."""
    raw = str(token or "").strip()
    return raw if _SAFE_TOKEN_RE.match(raw) else ""


def sanitize_server_url(url: Optional[str]) -> str:
    """Validate base HTTP/HTTPS relay URL before injecting into Lua."""
    raw = str(url or "").strip().rstrip("/")
    return raw if _SAFE_URL_RE.match(raw) else ""


def render_bridge_lua(
    bridge_path: Path,
    token: Optional[str] = None,
    server_url: Optional[str] = None,
) -> str:
    """Load lucifer_bridge.lua and safely inject OWNER_TOKEN and SERVER_URL."""
    content = bridge_path.read_text(encoding="utf-8")
    safe_token = sanitize_bridge_token(token)
    safe_url = sanitize_server_url(server_url)

    if safe_token:
        content = re.sub(
            r'local\s+OWNER_TOKEN\s*=\s*"[^"]*"',
            f'local OWNER_TOKEN = "{safe_token}"',
            content,
            count=1,
        )
    if safe_url:
        content = re.sub(
            r'local\s+SERVER_URL\s*=\s*"[^"]*"',
            f'local SERVER_URL = "{safe_url}"',
            content,
            count=1,
        )
    return content

