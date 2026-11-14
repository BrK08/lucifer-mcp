# 📦 KURULUM & KULLANIM REHBERİ — Lucifer MCP

> **Bu rehber kime yazıldı?** `https://github.com/BrK08/lucifer-mcp` reposunu yeni bulan ve ChatGPT, Claude, Gemini, Cursor, VS Code veya Antigravity ile Lucifer'ı tam yetkili yönetmek isteyen herkese.
>
> 🇺🇸 For the English guide, see [INSTALL.md](INSTALL.md)

<div align="center">
👑 <b>mr_berk</b> sürümü · <b>63 MCP aracı</b> · <b>6.833 gerçek eşya ID'si</b> · <b>3.808 tarif</b>
</div>

---

## ⚡ EN HIZLI YOL — Tek Komutla Kurulum (`start_mcp.py`)

Hiçbir JSON ayar dosyasıyla uğraşmadan **ChatGPT Web, Claude Web/Mobil veya Gemini**'ye bağlamak için:

```powershell
git clone https://github.com/BrK08/lucifer-mcp.git
cd lucifer-mcp
pip install -r requirements.txt
python start_mcp.py
```

1. **Uzak HTTPS Tüneli (ChatGPT / Claude Web için tek seferlik):**
   Bilgisayarında `cloudflared` yüklü değilse tek komutla kurabilirsin:
   ```powershell
   winget install Cloudflare.cloudflared
   ```
   `python start_mcp.py` çalıştırıldığında ekrana iki adres yazdırılır:
   - `Local MCP URL   : http://127.0.0.1:8828/mcp`
   - `Remote MCP URL  : https://xxxx.trycloudflare.com/mcp`
2. Ekrandaki `https://xxxx.trycloudflare.com/mcp` adresini kopyalayıp **ChatGPT → Ayarlar → Connectors → Add custom MCP server** (veya **Claude → Settings → Connectors**) kısmına yapıştır.
3. Aşağıdaki **Adım 5**'teki tek satır Lua köprüsünü Lucifer **Executor** sekmesinde çalıştır.

---

## ✅ Gereksinimler

| # | Gereksinim | Kontrol Yöntemi |
|---|---|---|
| 1 | **Lucifer Multibot v2.88 p2** | Lucifer açılıyor ve Bots / Executor sekmeleri görünüyor |
| 2 | **Python 3.10+** | Terminalde `python --version` çıktısı 3.10 ve üstü |
| 3 | **MCP destekleyen bir AI istemcisi** | ChatGPT (Connectors), Claude Desktop / Web, Cursor, VS Code, Antigravity |
| 4 | *(Web ChatGPT / Claude için opsiyonel)* **`cloudflared`** | `cloudflared --version` |

> ⚠️ **Sorumluluk Uyarısı:** Growtopia kullanım koşulları üçüncü parti bot kullanımını yasaklar. Scriptleri önce test botlarında deneyin, ana hesaplarınızda riskli otomasyon çalıştırmayın.

---

## Adım 1 — Python Kurulumu (Yoksa)

1. https://www.python.org/downloads/ adresinden Python 3.10+ indir.
2. Kurulum ekranında **"Add python.exe to PATH" ✅** kutucuğunu mutlaka işaretle.
3. Yeni bir PowerShell / CMD penceresinde doğrula:
   ```bat
   python --version
   ```

---

## Adım 2 — Projeyi İndir

**Seçenek A — Git ile (önerilen):**
```bat
git clone https://github.com/BrK08/lucifer-mcp.git C:\lucifer-mcp
cd C:\lucifer-mcp
```

**Seçenek B — ZIP olarak:**
GitHub'da yeşil **`<> Code` → `Download ZIP`** butonuna tıkla, `C:\lucifer-mcp` klasörüne çıkart ve o klasörde terminal aç.

---

## Adım 3 — Kütüphaneleri Kur

```bat
pip install -r requirements.txt
```

İsteğe bağlı test doğrulaması:
```bat
python -m unittest discover -s tests -v
```

---

## Adım 4 — Yapay Zekayı Bağla

### Seçenek A — ChatGPT Web / Claude.ai Web & Mobil (Cloudflare HTTPS Tüneli)

Terminalde şu komutu çalıştır (botu kullanırken pencere açık kalsın):
```bat
python start_mcp.py
```
Ekranda çıkan `https://xxxx.trycloudflare.com/mcp` adresini kopyala ve ChatGPT / Claude **Connectors** ayarlarına ekle.

---

### Seçenek B — Claude Desktop (`stdio` modu — tünel gerekmez)

Windows'ta `%APPDATA%\Claude\claude_desktop_config.json` (macOS'ta `~/Library/Application Support/Claude/claude_desktop_config.json`) dosyasına ekle:

```json
{
  "mcpServers": {
    "lucifer-mcp": {
      "command": "python",
      "args": ["C:\\lucifer-mcp\\server.py"]
    }
  }
}
```

Claude Desktop'ı kapatıp yeniden aç; arka planda `8829` Relay sunucusu otomatik olarak başlar.

---

### Seçenek C — Cursor / Antigravity / VS Code / Windsurf (`stdio` modu)

İstemcinin MCP ayar dosyasına (`mcp_config.json`, `.cursor/mcp.json` veya `.vscode/mcp.json`) ekle:

```json
{
  "mcpServers": {
    "lucifer-mcp": {
      "command": "python",
      "args": ["C:\\lucifer-mcp\\start_mcp.py", "--stdio"]
    }
  }
}
```

*(Aynı anda birden fazla AI penceresinden bağlanmak istersen bir terminalde `python start_mcp.py` çalıştırman yeterlidir; diğer MCP istemcileri `8829` portundaki aktif Relay'i otomatik görür ve ona bağlanır.)*

---

## Adım 5 — Lucifer Oyun İçi Köprüyü Aktifleştir

1. **Lucifer v2.88 p2** içinde **Executor** (`</>`) sekmesini aç.
2. Aşağıdaki tek satırlık Lua kodunu yapıştır ve **Execute** butonuna bas:
   ```lua
   local c = HttpClient.new(); c.url = "http://127.0.0.1:8829/bridge.lua"; local r = c:request(); load(r and r.body or c.content)()
   ```
   *(Alternatif: `start_mcp.py` tarafından oluşturulan `scripts/lucifer_bridge.lua` dosyasını seçip Execute basabilirsin.)*
3. Lucifer **[Console]** / **[Logs]** sekmesinde şu mesajı gördüğünde bağlantı hazırdır:
   `LUCIFER MULTIBOT BRIDGE STARTED (v2.5)`

Artık yapay zekana normal konuşma diliyle emir verebilirsin:
- *"Hangi botlarım çevrimiçi, hangi dünyadalar ve toplam kaç gem var?"*
- *"Şu anki dünyayı incele ve hasata hazır kaç tane Pepper Tree olduğunu söyle."*
- *"Tüm botları `MYFARM` dünyasına gönder ve canlı minimap çiz."*
- *"Door massı yapmak istiyorum, hangi seedler lazım ve botlarımın çantasında ne kadar var?"*

---

## 🔑 Opsiyonel — `glServer.exe` Google Login Captcha Ayarı

Google Login botlarında `"Couldn't Solve Captcha."` hatası alıyorsan:
1. `glServer.exe` konsoluna şu 3 komutu yaz:
   ```cmd
   set useHeadless False
   set userInteraction True
   set saveProfile True
   ```
2. Ardından `server` yazıp çıkan `localhost:4580:<accessKey>` satırını Lucifer'daki **Gmaillog Settings** bölümüne gir (veya AI'a `luci_glserver_set` ile kaydettir).
3. İlk girişte açılan tarayıcıdan Captcha'yı bir kez elle doğrula; profil kaydedildiği için sonraki girişlerde tekrar sormaz.
