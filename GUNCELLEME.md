# 🔄 Güncelleme & Lucifer Sürüm Uyumluluğu Rehberi — Lucifer MCP

> **Kısa cevap:** Çoğu Lucifer güncellemesinde hiçbir şey bozulmaz — çünkü Lucifer MCP doğrudan Lua katmanında (`bridge/lucifer_bridge.lua`) konuşur ve tüm eşya/API verileri kolayca yenilenebilen JSON/Markdown dosyalarında tutulur.

<div align="center">
👑 <b>mr_berk</b> sürümü · <b>63 MCP aracı</b> · <b>6.833 gerçek eşya ID'si</b> · <b>3.808 tarif</b>
</div>

---

## 1. Lucifer MCP'yi Güncelleme (`git pull`)

```bash
cd lucifer-mcp
git pull
pip install -r requirements.txt
```

Ardından `python start_mcp.py` komutunu (veya Claude Desktop / Cursor gibi stdio istemcisini) yeniden başlatıp Lucifer Executor'da tek satır köprüyü tekrar çalıştır.

---

## 2. Yeni Lucifer Sürümü Çıktığında

| Senaryo | Ne olur | Ne yapılır |
|---|---|---|
| **Küçük Lucifer güncellemesi** | Mevcut Lua köprüsü aynen çalışmaya devam eder | Hızlı kontrol yap (`luci_fleet_status`, `luci_eval_sync("return 1+1")`) |
| **Oyuna yeni eşyalar eklendiyse** | Yeni item ID'leri `items.json` içinde eksik kalabilir | `tools/generate_gt_items.py` ile `data/items.json` ve `data/recipes.json` yenilenir |
| **Lucifer'a yeni Lua metotları eklendiyse** | Doküman aramasında görünmez | `tools/lucifer_api_dumper.lua` Lucifer içinde çalıştırılıp `docs/` güncellenir |

---

## 3. Güncelleme Sonrası 2 Dakikalık Sağlık Kontrolü

1. `python start_mcp.py` başlat.
2. **Lucifer → Executor** sekmesinde tek satır köprüyü çalıştır:
   ```lua
   local c = HttpClient.new(); c.url = "http://127.0.0.1:8829/bridge.lua"; local r = c:request(); load(r and r.body or c.content)()
   ```
3. Yapay zekandan şu 3 kontrolü yapmasını iste:
   - `luci_relay_info()` → Relay portu ve köprü bağlantısını doğrular
   - `luci_fleet_status()` → Canlı bot bağlantılarını doğrular
   - `luci_eval_sync("return getBot() and getBot():name() or 'NO_BOT'")` → Senkron Lua çalıştırmayı doğrular

Üçü de yeşil dönüyorsa kurulum tamamen uyumludur!
