"""
Lucifer Multibot — GLServer (Google Login Server) Client & Manager
Handles glServer.exe integration, dynamic accessKey/port management,
Google OAuth status diagnostics, and Google Login Captcha solving solutions.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional
import aiohttp

from core.enums import GoogleStatus, describe_google_status


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")


class GLServerClient:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 4580,
        access_key: str = "",
    ):
        self.host = host
        self.port = port
        self.access_key = access_key
        self.load_from_config()

    @property
    def connection_string(self) -> str:
        """Format expected by Lucifer Gmaillog settings: host:port:access_key"""
        return f"{self.host}:{self.port}:{self.access_key}"

    def set_connection_string(self, conn_str: str) -> Dict[str, Any]:
        """
        Parses and sets the connection string.
        Accepts:
          - "localhost:4580:7240504ea8616251570bd27f1e987576284694014472fa5d9c53329ebfcde3ec"
          - "127.0.0.1:4580:KEY"
          - "4580:KEY"
          - "KEY"
        """
        raw = conn_str.strip()
        parts = raw.split(":")

        if len(parts) == 3:
            self.host = parts[0].strip() or "localhost"
            try:
                self.port = int(parts[1].strip())
            except ValueError:
                self.port = 4580
            self.access_key = parts[2].strip()
        elif len(parts) == 2:
            try:
                self.port = int(parts[0].strip())
                self.access_key = parts[1].strip()
            except ValueError:
                self.host = parts[0].strip()
                self.access_key = parts[1].strip()
        elif len(parts) == 1:
            self.access_key = parts[0].strip()
        else:
            return {"success": False, "error": "Invalid connection string format."}

        self.save_to_config()
        return {
            "success": True,
            "host": self.host,
            "port": self.port,
            "access_key": self.access_key,
            "connection_string": self.connection_string,
        }

    def load_from_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    gl = data.get("glserver", {})
                    if "host" in gl:
                        self.host = gl["host"]
                    if "port" in gl:
                        self.port = int(gl["port"])
                    if "access_key" in gl and gl["access_key"]:
                        self.access_key = gl["access_key"]
            except Exception as e:
                print(f"[GLServer] Could not load config: {e}")

    def save_to_config(self):
        data: Dict[str, Any] = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data["glserver"] = {
            "host": self.host,
            "port": self.port,
            "access_key": self.access_key,
            "connection_string": self.connection_string,
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[GLServer] Could not save config: {e}")

    async def check_health(self) -> Dict[str, Any]:
        """Checks if glServer.exe is reachable on its configured port."""
        url = f"http://{self.host}:{self.port}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.5)) as resp:
                    return {
                        "online": True,
                        "status_code": resp.status,
                        "connection_string": self.connection_string,
                        "message": "glServer is reachable.",
                    }
        except Exception as e:
            return {
                "online": False,
                "connection_string": self.connection_string,
                "message": f"glServer unreachable at {url}: {e}",
            }

    @staticmethod
    def diagnose_google_status(status_code: int) -> Dict[str, Any]:
        """Returns diagnostic advice for a given bot:google_status() return value."""
        desc = describe_google_status(status_code)
        solution = ""

        if status_code in (GoogleStatus.MISSING_SERVER, GoogleStatus.MISSING_LOCAL_SERVER):
            solution = "glServer.exe calismiyor! glServer.exe dosyasini acip konsola 'server' yazin ve cikan adresi Lucifer Gmaillog ayarlarina yapistirin."
        elif status_code == GoogleStatus.INVALID_KEY:
            solution = "AccessKey hatali! glServer.exe konsolundaki anahtari kopyalayip Lucifer'a yeniden yapistirin."
        elif status_code == GoogleStatus.CAPTCHA_REQUIRED:
            solution = (
                "Google robot dogrulamasi istedi. glServer.exe icinde 'selectedSolver: 0' kaldigi icin 'Couldn't Solve Captcha' hatasi aldiniz. "
                "Cozum icin: 'set useHeadless False' ve 'set userInteraction True' yapip manuel cozdurun VEYA 'set selectedSolver 1' (CapSolver) secin."
            )
        elif status_code == GoogleStatus.PHONE_REQUIRED:
            solution = "Google telefon numarasi onayi istedi. Gmail hesabina manuel girip telefon dogrulamasini tamamlayin."
        elif status_code == GoogleStatus.OTP_REQUIRED:
            solution = "Google 2FA / Authenticator kodu istedi. Hesapta 2FA varsa tek seferlik kod girilmelidir."
        elif status_code == GoogleStatus.RECOVERY_REQUIRED:
            solution = "Google kurtarma e-postasi istedi. Gmail ayarlarinizdaki kurtarma e-postasini kontrol edin."
        elif status_code == GoogleStatus.INVALID_CREDENTIALS:
            solution = "Gmail adresi veya sifresi hatali. login.json icindeki mail/sifre alanini kontrol edin."
        elif status_code == GoogleStatus.ACCOUNT_DISABLED:
            solution = "Bu Google hesabi Google tarafindan kapatilmis/devre disi birakilmis."
        elif status_code == GoogleStatus.IDLE:
            solution = "Bosta, henuz istek gonderilmedi veya islem basariyla bitti."
        elif status_code == GoogleStatus.PROCESSING:
            solution = "glServer su anda Google giris token'ini aliyor, lutfen bekleyin."

        return {
            "status_code": status_code,
            "status_name": GoogleStatus(status_code).name if status_code in GoogleStatus._value2member_map_ else "UNKNOWN",
            "description": desc,
            "solution": solution,
        }

    @staticmethod
    def parse_http_response(raw_text: str) -> Dict[str, Any]:
        """
        Parses raw HTTP Response outputs from Lucifer / glServer logs such as:
          Status: 200
          Body: {"statusCode":13,"status":"captcharequired","id":"berk.webops@gmail.com","data":"Couldn't Solve Captcha."}
        """
        body_match = re.search(r'Body:\s*({.*})', raw_text)
        if not body_match:
            try:
                data = json.loads(raw_text.strip())
            except Exception:
                return {"error": "Could not find or parse JSON body in the provided text."}
        else:
            try:
                data = json.loads(body_match.group(1).strip())
            except Exception:
                return {"error": "Invalid JSON format in response body."}

        status_code = data.get("statusCode", 0)
        status_str = data.get("status", "")
        account_id = data.get("id", "")
        detail_data = data.get("data", "")

        diagnosis = GLServerClient.diagnose_google_status(status_code)

        actionable_steps = []
        if status_code == 13 or "captcharequired" in status_str:
            actionable_steps = [
                "glServer.exe konsol penceresini acin.",
                "UCRETSIZ COZUM (Tavsiye): Asagidaki komutlari sirayla girin:",
                "  > set useHeadless False",
                "  > set userInteraction True",
                "  > set saveProfile True",
                "Bu sayede tarayici penceresi ekranda acilir, Google Captcha ciktiginda siz tek tikla cozersiniz ve profil kaydedildigi icin bir daha Captcha sormaz!",
                "OTOMATIK COZUM (CapSolver):",
                "  > set selectedSolver 1",
                "  glserver klasorundeki 'capsolver/assets/config.json' icine API anahtarinizi yazin.",
                "OTOMATIK COZUM (CapMonster):",
                "  > set selectedSolver 2",
                "  glserver klasorundeki 'capmonster/assets/config.json' icine API anahtarinizi yazin.",
            ]
        elif status_code == 15 or "recoveryrequired" in status_str:
            actionable_steps = [
                "1. ADIM (En Hızlı Çözüm): Telefonunuzdan veya normal tarayıcınızdan https://myaccount.google.com/security adresine gidin.",
                "   'Son güvenlik etkinlikleri' (Recent security activity) altında bu giriş denemesini bulun ve 'Evet, bendim' (Yes, it was me) onayını verin.",
                "   Bu onay Google'ın bu IP adresini güvenli tanımasını sağlar ve kurtarma kodu sorma engelini anında kaldırır!",
                "2. ADIM (Hesap Formatı): Lucifer Hesaplar sekmesinde hesabı 'email:şifre:kurtarma_epostası' formatında girin.",
                "   Kurtarma maili yazılmadığında glServer elementi bulamaz ('Couldn't locate recovery mail address') ve kodu beklemeden hata fırlatıp kapanır.",
                "3. ADIM (glServer Ayarı): glServer.exe konsolunda 'set useHeadless False', 'set userInteraction True', 'set saveProfile True' komutlarının aktif olduğundan emin olun.",
            ]

        return {
            "account": account_id,
            "status_code": status_code,
            "status_str": status_str,
            "error_detail": detail_data,
            "description": diagnosis.get("description"),
            "solution": diagnosis.get("solution"),
            "actionable_steps": actionable_steps,
        }

    @staticmethod
    def get_captcha_guide() -> Dict[str, Any]:
        """Comprehensive guide on solving Google Login Captchas in glServer vs in-game Captchas."""
        return {
            "title": "Google Login Captcha Çözüm Rehberi (glServer v1.6)",
            "why_it_happens": (
                "Lucifer'daki genel 'Captcha Settings' sekmesi yalnizca oyun ici Growtopia bulmacalarini cozer. "
                "Google girisindeki reCAPTCHA dogrulamasi ise 'glServer.exe' tarafindan acilan tarayicida gerceklesir. "
                "glServer'da varsayilan olarak 'selectedSolver: 0 (none)' ve 'userInteraction: False' oldugu icin "
                "Google robot sinamasi sordugunda glServer bunu cozemez ve 'Couldn't Solve Captcha' hatasi doner."
            ),
            "method_free": {
                "name": "1. Yöntem: Ücretsiz & Manuel Etkileşim (En Sağlam & Sıfır Maliyet)",
                "steps": [
                    "glServer.exe konsoluna girin.",
                    "set useHeadless False  -> (Tarayiciyi gorunur yapar)",
                    "set userInteraction True  -> (Captcha gelince bekler)",
                    "set saveProfile True  -> (Basarili girisi kaydeder, bir daha sormaz)",
                    "Lucifer'da botu Connect yapin. Ekranda acilan Google penceresindeki Captcha'yi elle tiklayip cozun.",
                    "Oturum 'chrome' klasorune kaydedilecektir; sonraki girislerde tek tikla direkt baglanir!",
                ],
            },
            "method_capsolver": {
                "name": "2. Yöntem: CapSolver ile Otomatik Çözüm",
                "steps": [
                    "glServer.exe konsoluna yazin: set selectedSolver 1",
                    "glserver klasorundeki 'capsolver/assets/config.json' (veya config.json) dosyasini acin.",
                    "apiKey alanina CapSolver anahtarinizi yapistirip kaydedin.",
                    "glServer otomatik olarak arka planda eklentiyle Captcha'yi cozer.",
                ],
            },
            "method_capmonster": {
                "name": "3. Yöntem: CapMonster ile Otomatik Çözüm",
                "steps": [
                    "glServer.exe konsoluna yazin: set selectedSolver 2",
                    "glserver klasorundeki 'capmonster/assets/config.json' dosyasina ClientKey yapistirin.",
                ],
            },
            "method_minirpa": {
                "name": "4. Yöntem: MiniRPA (Yerel Çözücü)",
                "steps": [
                    "glServer.exe konsoluna yazin: set selectedSolver 3",
                    "glserver v1.6 icindeki yerel minirpa modulu devreye girer.",
                ],
            },
        }


# Global singleton instance
glserver_client = GLServerClient(
    host="localhost",
    port=4580,
    access_key="7240504ea8616251570bd27f1e987576284694014472fa5d9c53329ebfcde3ec",
)
