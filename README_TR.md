<div align="center">

# 😈 LUCIFER MCP

### Growtopia Lucifer v2.88 p2 İçin Tam Erişimli Yapay Zeka Kontrolü & Lua Araç Seti (MCP)

**Geliştirici: `mr_berk`**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastMCP](https://img.shields.io/badge/FastMCP-2.x-green.svg)](https://gofastmcp.com)
[![Lucifer](https://img.shields.io/badge/Lucifer-v2.88%20p2-purple.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)

**63 MCP aracı** · **6.833 gerçek eşya ID'si** · **3.808 birleştirme/mass tarifi** · **44 BotStatus & 21 GoogleStatus kodu** · **1:1 canlı dünya minimapi** · **Senkron Lua çalıştırma & `[Logs]` okuma**

*SAHTE DEĞİL — GERÇEK LUCIFER v2.88 p2 RUNTIME DÖKÜMÜ VE `items.dat` VERİLERİYLE HAZIRLANDI*

🌐 **Language / Dil:** 🇺🇸 **[English Guide (README.md)](README.md)** | 🇹🇷 **Türkçe (Şu anki)**

📚 Dokümantasyon:
- [KURULUM.md](KURULUM.md) — Adım adım Türkçe kurulum rehberi
- [INSTALL.md](INSTALL.md) — Step-by-step English setup guide
- [AGENTS.md](AGENTS.md) — Yapay zekalar için otomatik kurulum & kural dosyası
- [AI_EGITIM.md](AI_EGITIM.md) — Türkçe Lucifer v2.88 p2 AI eğitim paketi
- [AI_TRAINING.md](AI_TRAINING.md) — English Lucifer v2.88 p2 AI training pack
- [GUNCELLEME.md](GUNCELLEME.md) / [UPDATING.md](UPDATING.md) — Güncelleme rehberleri

</div>

---

## 🤖 Linki Kopyala → Yapay Zekaya At (Doğrudan Çalışsın!)

`https://github.com/BrK08/lucifer-mcp` linkini bir yapay zekaya gönderdiğinde iki senaryodan biri devreye girer:

- **Terminal Yetkisi Olan Yapay Zeka (Antigravity, Cursor, Claude Code, Windsurf, Cline):** [`AGENTS.md`](AGENTS.md) dosyasını okuyarak repoyu kendisi indirir, bağımlılıkları kurar, `python start_mcp.py` komutunu çalıştırır ve sana yalnızca Lucifer **Executor** sekmesine yapıştıracağın tek satır kodu verir.
- **Bulut / Web Yapay Zeka (ChatGPT, Claude.ai Web/Mobil, Gemini Web):** Önce bilgisayarında çalıştırman gereken 3 kısa komutu adım adım anlatır (`https://xxxx.trycloudflare.com/mcp` bağlantısını alman için); ayrıca daha MCP bağlamadan bile [`AI_EGITIM.md`](AI_EGITIM.md) dosyasını okuyarak %100 gerçek Lucifer v2.88 p2 scriptleri yazabilir.

---

## Bu proje nedir?

**Lucifer MCP**, yapay zeka asistanını Model Context Protocol (MCP) aracılığıyla doğrudan **Growtopia Lucifer Multibot v2.88 p2** uygulamasına bağlar. Bağlantı kurulduğunda yapay zeka botlarını tıpkı arayüzü kullanan bir insan gibi yönetebilir:

- Senkron Lua kodu çalıştırır (`luci_eval_sync`), `return` değerlerini ve canlı `[Console]` / `[Logs]` çıktılarını okur
- Dünyadaki oyuncuları, karoları, `TileExtra` ağaç büyüme sürelerini, yerdeki eşyaları ve 1:1 dünya minimap görselini analiz eder
- Yürüme, pathfinding, blok koyma/kırma, wrench, kapıdan girme, Magplant çekme, mağaza alımı ve ham paket gönderme işlemlerini doğrudan uygular
- `Rotation`, `WorldManager`, `ProxyManager`, `AutoFarm`, `Trash & Pack` ve `GLServer` Google Login ayarlarını yönetir
- **6.833 gerçek Growtopia eşya ID'si** ve **3.808 birleştirme/mass tarifi** içinde anında arama yapar
- Kod çalıştırmadan önce Türkçe karakter (ASCII) ve ban riski kontrolü yapar (`luci_code_analyze`, `luci_auto_test`)

---

## Hızlı Başlangıç (Tek Komut)

### 1) İndir ve Kur

```bash
git clone https://github.com/BrK08/lucifer-mcp.git
cd lucifer-mcp
pip install -r requirements.txt
```

### 2) MCP Sunucusunu Başlat (Relay + Cloudflare HTTPS Tüneli Dahil)

```bash
python start_mcp.py
```

`start_mcp.py` çalıştırıldığında otomatik olarak:
1. `scripts/lucifer_bridge.lua` köprü dosyasını hazırlar/kopyalar
2. `http://127.0.0.1:8829` üzerinde Lucifer HTTP Relay sunucusunu başlatır
3. Sistemde `cloudflared` varsa ChatGPT / Claude Web bağlantısı için ücretsiz `https://xxxx.trycloudflare.com/mcp` HTTPS tünelini açar
4. `http://127.0.0.1:8828/mcp` adresinde FastMCP sunucusunu ayağa kaldırır

*(Claude Desktop, Cursor veya Antigravity gibi masaüstü `stdio` istemcileri için `python server.py` veya `python start_mcp.py --stdio` kullanılır.)*

### 3) Yapay Zekayı Bağla

- **ChatGPT / Claude Web Connectors:** Ekranda yazan `https://xxxx.trycloudflare.com/mcp` URL'sini **Settings → Connectors → Add custom MCP** alanına yapıştır.
- **Claude Desktop / Cursor / VS Code / Antigravity:** Kopyala-yapıştır JSON ayarları için [KURULUM.md](KURULUM.md) rehberine bak.

### 4) Lucifer İçinde Köprüyü Çalıştır (Tek Satır)

**Lucifer v2.88 p2 → Executor** sekmesini açıp şu tek satırı çalıştır:

```lua
local c = HttpClient.new(); c.url = "http://127.0.0.1:8829/bridge.lua"; local r = c:request(); load(r and r.body or c.content)()
```

*(Veya `scripts/lucifer_bridge.lua` dosyasını açıp **Execute** butonuna bas.)*

---

## Dahil Edilen Araçlar (63 MCP Aracı)

| Kategori | Araçlar | Görevi |
|---|---|---|
| **Canlı Script & Log** | `luci_eval_sync`, `luci_run_script`, `luci_stop_script`, `luci_auto_test`, `luci_get_console_and_logs`, `luci_get_bot_logs`, `luci_code_analyze` | Senkron Lua çalıştırma, canlı konsol/[Logs] okuma, ASCII ve ban riski analizi |
| **Dünya, Karo & Harita** | `luci_inspect_world`, `luci_inspect_tile`, `luci_world_count_item`, `luci_render_world_map` | Oyuncular, yerdeki objeler, TileExtra okuma, eşya sayımı, 1:1 PNG minimap |
| **Filo & Envanter** | `luci_fleet_status`, `luci_bot_list`, `luci_bot_inventory`, `luci_fleet_census` | Çoklu bot durumu, gem, ping, seviye ve tüm filo envanter taraması |
| **İnsan Gibi Etkileşim** | `luci_warp`, `luci_say`, `luci_move`, `luci_find_path`, `luci_find_world_path`, `luci_enter_door`, `luci_leave_world`, `luci_respawn`, `luci_place_block`, `luci_punch_tile`, `luci_wrench`, `luci_activate_tile`, `luci_collect`, `luci_drop_item`, `luci_trash_item`, `luci_equipment`, `luci_buy`, `luci_retrieve`, `luci_send_packet`, `luci_send_raw_packet` | Yürüme, yol bulma, kırma/koyma, wrench, kapı, Magplant, eşya giyme, paketler |
| **Bot & Alt Sistemler** | `luci_add_bot`, `luci_remove_bot`, `luci_connect_bot`, `luci_disconnect_bot`, `luci_update_bot_identity`, `luci_set_automation`, `luci_set_setting`, `luci_setup_farm`, `luci_configure_rotation`, `luci_world_manager`, `luci_configure_subsystem`, `luci_proxy_manager`, `luci_set_bot_proxy`, `luci_assign_proxies_bulk`, `luci_proxy_next`, `luci_trash_and_pack_manager` | Hesap ekleme/çıkarma, AutoFarm/AntiMod, Rotation, WorldManager, ProxyManager |
| **Eşya DB, Doküman & GLServer** | `luci_search_item`, `luci_item_details`, `luci_api_docs`, `luci_file_system`, `luci_analyze_risk`, `luci_diagnose_status`, `luci_bot_google_status`, `luci_glserver_info`, `luci_glserver_set`, `luci_glserver_captcha_guide`, `luci_glserver_parse_response`, `luci_relay_info` | 6.833 eşya & splicing tarifi arama, API döküm araması, dosya sistemi, GLServer teşhisi |

---

## Sorumluluk Bildirimi

Bu proje eğitim, araştırma ve geliştirici otomasyonu amacıyla [MIT Lisansı](LICENSE) altında sunulmuştur. Growtopia kullanım koşulları üçüncü parti botları yasaklar; tüm sorumluluk kullanıcıya aittir.

<div align="center">

### 👑 mr_berk

`Lucifer MCP` — 63 araç · 6.833 gerçek Growtopia eşya ID'si · 3.808 tarif

</div>
