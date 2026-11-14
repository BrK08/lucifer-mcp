"""
Lucifer Multibot — Strategic Safety Advisor & Consequence Evaluator
Analyzes user automation requests, credentials, IP/proxy density, and delays
BEFORE execution. Warns about ban hazards (http_block 13, location_banned 5)
and demands confirmation on high-risk operations.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class SafetyAdvisor:
    """Evaluates risks and consequences of Lucifer multibot operations."""

    @staticmethod
    def evaluate_login_request(
        accounts: List[Dict[str, str]],
        proxy_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Analyzes account login requests for IP overload, proxy adequacy,
        and determines the correct login method for each account.
        """
        total = len(accounts)
        warnings: List[str] = []
        recommendations: List[str] = []
        account_methods: List[Dict[str, str]] = []

        # 1. Determine login methods
        google_count = 0
        legacy_count = 0
        for acc in accounts:
            username = (acc.get("username") or acc.get("email") or acc.get("name") or "").strip()
            if "@gmail.com" in username.lower() or "@googlemail.com" in username.lower():
                google_count += 1
                account_methods.append({
                    "account": username,
                    "method": "google_oauth",
                    "engine": "glServer.exe",
                    "note": "Lucifer Gmaillog Settings üzerinden accessKey ile bağlanmalı."
                })
            else:
                legacy_count += 1
                account_methods.append({
                    "account": username,
                    "method": "legacy_growid",
                    "engine": "Growtopia Direct Auth",
                    "note": "Klasik GrowID + Şifre ile bağlanır."
                })

        # 2. IP / Proxy Density Analysis
        requires_confirmation = False
        risk_level = "LOW"

        if proxy_count == 0:
            if total > 2:
                risk_level = "CRITICAL"
                requires_confirmation = True
                warnings.append(
                    f"⚠️ **ACİL BAN RİSKİ:** Hiçbir proxy olmadan tek bir ev IP'sinden {total} adet bot bağlamaya çalışıyorsunuz!"
                )
                warnings.append(
                    "Ubisoft/Growtopia sunucuları tek bir IP'den 2'den fazla eşzamanlı bağlantı gördüğünde "
                    "IP adresinizi 'http_block (Status 13)' veya 'location_banned (Status 5)' ile tamamen engelleyebilir."
                )
                recommendations.append(
                    "En az 1 bot / 1 proxy olacak şekilde Lucifer ProxyManager sekmesine proxy ekleyin."
                )
                recommendations.append(
                    "Eğer proxy yoksa botları sırayla ve aralarında en az 30 saniye bırakarak sokun."
                )
            elif total == 2:
                risk_level = "MEDIUM"
                warnings.append("ℹ️ Tek IP üzerinden 2 bot sınır değerdir; 3. bot eklenirse ban riski doğar.")
        else:
            bots_per_proxy = total / max(1, proxy_count)
            if bots_per_proxy > 2.5:
                risk_level = "MEDIUM"
                warnings.append(
                    f"⚠️ Proxy başına ortalama {bots_per_proxy:.1f} bot düşüyor. Güvenli sınır proxy başına maksimum 2 bottur."
                )

        if google_count > 0:
            recommendations.append(
                f"Tespit edilen {google_count} Google hesabı için glServer.exe açık olmalı ve "
                "konsolda 'set useHeadless False, set userInteraction True, set saveProfile True' girilmiş olmalıdır."
            )

        return {
            "risk_level": risk_level,
            "requires_confirmation": requires_confirmation,
            "total_accounts": total,
            "google_accounts": google_count,
            "legacy_accounts": legacy_count,
            "proxies_available": proxy_count,
            "account_methods": account_methods,
            "warnings": warnings,
            "recommendations": recommendations,
            "confirmation_message": (
                f"🚨 **DİKKAT:** Tek IP'de {total} bot yüksek ban riski taşır. "
                "Yine de proxiesiz devam etmek istiyor musunuz? (Evet / Hayır)"
            ) if requires_confirmation else None
        }

    @staticmethod
    def evaluate_delay_safety(delay_ms: int, action: str = "hit") -> Dict[str, Any]:
        """Evaluates whether an action delay violates Growtopia's speed/CPS thresholds."""
        thresholds = {
            "hit": (160, 220),
            "punch": (160, 220),
            "place": (130, 180),
            "warp": (3000, 5000),
            "collect": (140, 200),
            "drop": (250, 400),
            "trash": (250, 400),
        }
        min_safe, recommended = thresholds.get(action.lower(), (150, 200))

        if delay_ms < min_safe:
            return {
                "safe": False,
                "risk_level": "CRITICAL",
                "delay_ms": delay_ms,
                "min_safe_ms": min_safe,
                "recommended_ms": recommended,
                "warning": (
                    f"⛔ HIZ SINIRI AŞILDI: '{action}' eylemi için {delay_ms}ms çok hızlıdır! "
                    f"Growtopia sunucu kontrolleri {min_safe}ms altını anında autoban ile cezalandırır. "
                    f"Güvenli değer: {recommended}ms (±25ms jitter)."
                )
            }

        return {
            "safe": True,
            "risk_level": "LOW",
            "delay_ms": delay_ms,
            "recommended_ms": recommended,
            "warning": None
        }

    @staticmethod
    def evaluate_mass_warp(bot_count: int, target_world: str) -> Dict[str, Any]:
        """Evaluates risks of warping multiple bots into a single world."""
        if bot_count > 3:
            return {
                "risk_level": "MEDIUM",
                "requires_staggering": True,
                "warning": (
                    f"⚠️ {bot_count} botun aynı anda '{target_world}' dünyasına aynı saniyede ışınlanması "
                    "Growtopia sunucu anti-raid ve moderator alarmlarını tetikleyebilir."
                ),
                "solution": "Botları 4-7 saniyelik kademeli aralıklarla (staggered warp) ışınlayın."
            }
        return {"risk_level": "LOW", "requires_staggering": False, "warning": None}


safety_advisor = SafetyAdvisor()
