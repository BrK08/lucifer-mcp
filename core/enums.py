"""
Lucifer Multibot v2.88 p2 — Complete Enumerations Reference
100% extracted from real Lucifer runtime dump.
"""
from __future__ import annotations
from enum import IntEnum
from typing import Dict, Optional


class Action(IntEnum):
    MOVE = 0
    COLLECT = 1
    HIT = 2
    PLACE = 3
    HARVEST = 4
    PLANT = 5
    WARP = 6
    DROP = 7
    TRASH = 8


class BotStatus(IntEnum):
    OFFLINE = 0
    ONLINE = 1
    WRONG_PASSWORD = 2
    ACCOUNT_BANNED = 3
    ACCOUNT_SUSPENDED = 4
    LOCATION_BANNED = 5
    VERSION_UPDATE = 6
    ADVANCED_ACCOUNT_PROTECTION = 7
    SERVER_OVERLOAD = 8
    TOO_MANY_LOGIN = 9
    MAINTENANCE = 10
    SERVER_BUSY = 11
    GUEST_LIMIT = 12
    HTTP_BLOCK = 13
    BAD_NAME_LENGTH = 14
    INVALID_ACCOUNT = 15
    UBI_DISABLED = 16
    ACCOUNT_RESTRICTED = 17
    NETWORK_RESTRICTED = 18
    ERROR_CONNECTING = 19
    LOGON_FAIL = 20
    CAPTCHA_REQUESTED = 21
    MOD_ENTERED = 22
    PLAYER_ENTERED = 23
    HIGH_LOAD = 24
    HIGH_PING = 25
    CHANGING_SUBSERVER = 26
    STOPPED = 27
    GETTING_SERVER_DATA = 28
    BYPASSING_SERVER_DATA = 29
    COULD_NOT_WARP = 30
    BAD_INVENTORY = 31
    BAD_GATEWAY = 32
    SERVER_ISSUE = 33
    RETRIEVING_TOKEN = 34
    TWO_FACTOR = 35
    GOOGLE_LOGON_FAIL = 36
    STEAM_LOGON_FAIL = 38
    LINKING_STEAM = 39
    STEAM_NOT_LINKED = 40
    SOLVING_CAPTCHA = 41
    FAILED_CAPTCHA = 42
    BANWAVE_DETECTED = 43
    SMS_ERROR = 44


BOT_STATUS_DESCRIPTIONS: Dict[int, str] = {
    0: "Offline (Kapali)",
    1: "Online (Oyunda)",
    2: "Wrong Password (Hatali Sifre)",
    3: "Account Banned (Hesap Banlandi)",
    4: "Account Suspended (Hesap Askida)",
    5: "Location Banned (IP/Konum Banli)",
    6: "Version Update (Growtopia Guncellemesi Gerekli)",
    7: "Advanced Account Protection (AAP Acik, Dogrulama Gerek)",
    8: "Server Overload (Sunucu Asiri Yuklu)",
    9: "Too Many Login (Cok Fazla Giris Denemesi)",
    10: "Maintenance (Sunucu Bakimda)",
    11: "Server Busy (Sunucu Mesgul)",
    12: "Guest Limit (Misafir Hesabi Limiti Asildi)",
    13: "HTTP Block (IP Adresi growtopia1.com Tarafindan Engellendi)",
    14: "Bad Name Length (Isim Uzunlugu Gecersiz)",
    15: "Invalid Account (Gecersiz Hesap)",
    16: "Ubi Disabled (Ubisoft Girisi Devre Disi)",
    17: "Account Restricted (Hesap Kisitlandi)",
    18: "Network Restricted (Ag Kisitlandi)",
    19: "Error Connecting (Baglanti Hatasi)",
    20: "Logon Fail (Giris Basarisiz)",
    21: "Captcha Requested (Captcha Dogrulamasi Istendi)",
    22: "Mod Entered (Moderator Dunyaya Girdi!)",
    23: "Player Entered (Oyuncu Dunyaya Girdi)",
    24: "High Load (Yuksek Yuk)",
    25: "High Ping (Yuksek Gecikme)",
    26: "Changing Subserver (Alt Sunucuya Geciliyor)",
    27: "Stopped (Durduruldu)",
    28: "Getting Server Data (Sunucu Verisi Aliniyor)",
    29: "Bypassing Server Data (Sunucu Verisi Atlatiliyor)",
    30: "Could Not Warp (Dunyaya Isinlanamadi)",
    31: "Bad Inventory (Envanter Hatasi)",
    32: "Bad Gateway (Kapi Hatasi)",
    33: "Server Issue (Sunucu Sorunu)",
    34: "Retrieving Token (Token Aliniyor)",
    35: "Two Factor (2FA Dogrulama Gerek)",
    36: "Google Logon Fail (Google Girisi Basarisiz)",
    38: "Steam Logon Fail (Steam Girisi Basarisiz)",
    39: "Linking Steam (Steam Hesabi Baglaniyor)",
    40: "Steam Not Linked (Steam Bagli Degil)",
    41: "Solving Captcha (Captcha Cozuluyor)",
    42: "Failed Captcha (Captcha Cozulemedi)",
    43: "Banwave Detected (Ban Dalgasi Algilandi!)",
    44: "SMS Error (SMS Dogrulama Hatasi)",
}


class GoogleStatus(IntEnum):
    IDLE = 0
    PROCESSING = 1
    BAD_SERVER = 2
    BAD_CONNECTION = 3
    INVALID_KEY = 4
    MISSING_SERVER = 5
    MISSING_LOCAL_SERVER = 6
    TIMEOUT = 7
    DRIVER_CLOSED = 8
    INIT_ERROR = 9
    INVALID_CREDENTIALS = 10
    INVALID_SECRET = 11
    ACCOUNT_DISABLED = 12
    CAPTCHA_REQUIRED = 13
    PHONE_REQUIRED = 14
    RECOVERY_REQUIRED = 15
    OTP_REQUIRED = 16
    INVALID_CHALLENGE = 17
    COULDNT_VERIFY = 18
    UNKNOWN_URL = 19
    REDIRECT = 21


GOOGLE_STATUS_DESCRIPTIONS: Dict[int, str] = {
    0: "Bosta (Hazir)",
    1: "Isleniyor (Google Token Aliniyor)",
    2: "Gecersiz Sunucu (glServer yaniti gecersiz)",
    3: "Kotu Baglanti (glServer ile iletisim kurulamadi)",
    4: "Gecersiz Key (AccessKey hatali! glServer.exe konsolundaki anahtari girin)",
    5: "Sunucu Bulunamadi (glServer.exe calismiyor veya kapali)",
    6: "Yerel Sunucu Eksik (glServer localhost baglantisi yok)",
    7: "Zaman Asimi (Google yanit vermedi)",
    8: "Tarayici Kapatildi (Selenium/Headless driver kapandi)",
    9: "Baslatma Hatasi (glServer baslatilamadi)",
    10: "Gecersiz Kimlik Bilgileri (Gmail veya sifre yanlis)",
    11: "Gecersiz Gizli Anahtar (Secret key hatali)",
    12: "Hesap Devre Disi (Google hesabi kilitlenmis/kapatilmis)",
    13: "Captcha Gerekli (Google girisinde Captcha istendi)",
    14: "Telefon Dogrulamasi Gerekli (Google SMS/Arama onayi istedi)",
    15: "Kurtarma E-postasi Gerekli (Google kurtarma e-postasi istedi)",
    16: "2FA / OTP Kodu Gerekli (Google Authenticator kodu girilmeli)",
    17: "Gecersiz Guvenlik Sinamasi (Google Challenge hatasi)",
    18: "Dogrulanamadi (Google kimligi teyit edemedi)",
    19: "Bilinmeyen URL (Beklenmeyen Google yonlendirmesi)",
    21: "Yonlendirildi (OAuth redirect tamamlandi)",
}


class Platform(IntEnum):
    WINDOWS = 0
    IOS = 1
    MACOS = 2
    ANDROID = 4
    UBICONNECT = 13
    STEAM = 15
    APPLE = 69


class Event(IntEnum):
    VARIANTLIST = 0
    UPDATE_PACKET = 1
    TRACK_PACKET = 2
    GENERIC_TEXT = 3
    GAME_MESSAGE = 4
    GOT_PUNCHED = 5
    MOD_ENTER = 6
    RENDER = 7


class Role(IntEnum):
    FARM = 0
    BUILD = 1
    SURG = 2
    FISH = 3
    COOK = 4
    STARTOPIA = 5


class GeigerArea(IntEnum):
    NULL = 0
    RED = 1
    YELLOW = 2
    GREEN = 3
    RAPID = 4
    PRIZE = 5


class RotationStatus(IntEnum):
    SCANNING_WORLD = 0
    HARVESTING_TREES = 1
    FARMING_BLOCK = 2
    PLANTING_SEEDS = 3
    DROPPING_SEEDS = 4
    DROPPING_PACKS = 5
    FILLING_SEEDS = 6
    HARVESTING_ROOTS = 7
    COLLECTING_FOSSILS = 8
    CLEARING_OBJECTS = 9
    REACHING_LEVEL = 10
    CLEARING_HISTORY = 11
    CREATING_HOME_WORLD = 12


class RotationWorldStatus(IntEnum):
    NONE = 0
    PROCESSING = 1
    READY = 2
    INVALID = 3
    INACCESSIBLE = 4
    BURNT = 5
    TOXIC = 6


class StorageType(IntEnum):
    PACK = 0
    SEED = 1


class ProxyType(IntEnum):
    NONE = 0
    HTTP = 1
    HTTPS = 2
    SOCKS5 = 3


class Bubble(IntEnum):
    NONE = 0
    TALK = 1
    BRB = 2


def describe_bot_status(status_id: int) -> str:
    return BOT_STATUS_DESCRIPTIONS.get(status_id, f"Bilinmeyen Durum ({status_id})")


def describe_google_status(status_id: int) -> str:
    return GOOGLE_STATUS_DESCRIPTIONS.get(status_id, f"Bilinmeyen Google Durumu ({status_id})")
