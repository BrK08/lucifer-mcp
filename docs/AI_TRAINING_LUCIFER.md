# 🧠 Lucifer Multibot AI Eğitim Dokümanı & API Ansiklopedisi (mr_berk edition)

> **DİKKAT (ChatGPT, Google Gemini, Claude, Antigravity ve Diğer Tüm Yapay Zekalar İçin):**
> Bu doküman, **Lucifer v2.88 p2** çalışma zamanından (runtime) `%100 dökülmüş (dumped)` gerçek API referansıdır.
> Lucifer için Lua scripti, MCP aracı veya otomasyon yazarken **BURADAKİ METOT VE ENUM DEĞERLERİ HARFİYEN ESAS ALINMALIDIR**.

---

## 1. TEMEL MİMARİ & KURALLAR

1. **Çoklu Bot (Multibot / Fleet):**
   - Lucifer tek bir oyuncuyu değil, onlarca hatta yüzlerce botu aynı anda bağımsız oturumlarla yönetir.
   - Script içinde `getBot()` o anki bot nesnesini döner; `getBots()` tüm botların listesini döner.
2. **GENTAHAX ile Karıştırma! (ZORUNLU KURAL):**
   - Lucifer'da `AddHook`, `makeRequest`, `requestTileChange`, `checkTile` gibi GentaHAX fonksiyonları **YOKTUR**.
   - Bunların yerine:
     - `makeRequest` YERİNE -> `HttpClient.new()` (`client.url`, `client.content`, `client:request()`)
     - `requestTileChange(x, y, item)` YERİNE -> `bot:place(x, y, item)` veya `bot:hit(x, y)`
     - `findPath(x, y)` YERİNE -> `bot:findPath(x, y)`
     - `sleep(ms)` yerleşik ve güvenlidir.
3. **Growtopia Oyun İçi ASCII Kuralı (TÜRKÇE KARAKTER YASAK):**
   - Growtopia oyun içi yazı tipi Türkçe karakterleri (`ğ, ü, ş, ı, ö, ç, İ, Ğ, Ü, Ş, Ö, Ç`) **DESTEKLEMEZ**.
   - Lua scriptlerinde (`print`, `bot:say`, `logToConsole`, paketler) **ASLA Türkçe karakter kullanma**; sadece ASCII (`g, u, s, i, o, c, I`) kullan!
4. **Threading & Gecikmeler (Delays):**
   - Sunucu banlarından ve `http_block` hatalarından kaçınmak için Growtopia eylemleri arasına mutlaka dinamik `sleep()` konmalıdır:
     - `warp`: minimum 3000ms - 5000ms
     - `punch / hit`: 160ms - 220ms
     - `place`: 130ms - 180ms
     - `collect`: 150ms - 200ms
     - `drop / trash`: 300ms - 500ms

---

## 2. GLSERVER (GOOGLE LOGIN SERVER) & GMAIL LOG ÇALIŞMA MANTIĞI

### Neden Her Bilgisayarda Farklıdır?
`glServer.exe`, her çalıştırıldığında rastgele ve benzersiz 64 karakterlik bir `accessKey` ve port (varsayılan `4580`) tahsis eder.
Örnek konsol çıktısı:
```
accessKey: 7240504ea8616251570bd27f1e987576284694014472fa5d9c53329ebfcde3ec
port: 4580
(cmd) server
local: localhost:4580:7240504ea8616251570bd27f1e987576284694014472fa5d9c53329ebfcde3ec
```

### Kurulum Adımları:
1. `glServer.exe` uygulamasını çalıştırın.
2. Konsola `server` yazın ve `local:` satırındaki metni (`localhost:4580:<access_key>`) kopyalayın.
3. Lucifer arayüzünde **Gmaillog Settings** sekmesine gidin.
4. Kopyaladığınız satırı yapıştırıp **Connect** tuşuna basın.
5. Botun durumunu `bot:google_status()` ile kontrol edin (kod `0` ise hazır, `1` ise işlemde).

---

## 3. RESMİ DÖKÜM: ENUMLAR (ENUMERATIONS)

### [Enum: BotStatus] — 44 Durum Kodu
| ID | Enum Adı | Açıklama |
|---|---|---|
| 0 | `offline` | Bot çevrimdışı |
| 1 | `online` | Bot oyunda ve çevrimiçi |
| 2 | `wrong_password` | Hatalı şifre |
| 3 | `account_banned` | Hesap banlandı |
| 4 | `account_suspended` | Hesap askıya alındı |
| 5 | `location_banned` | Konum/IP banlandı |
| 6 | `version_update` | Growtopia sürüm güncellemesi |
| 7 | `advanced_account_protection` | AAP doğrulaması gerekli |
| 8 | `server_overload` | Sunucu aşırı yüklü |
| 9 | `too_many_login` | Çok fazla giriş denemesi |
| 10 | `maintenance` | Oyun sunucusu bakımda |
| 11 | `server_busy` | Sunucu meşgul |
| 12 | `guest_limit` | Misafir hesabı limiti |
| 13 | `http_block` | **IP Growtopia CDN tarafından engellendi (server_data.php)** |
| 14 | `bad_name_length` | Geçersiz isim uzunluğu |
| 15 | `invalid_account` | Geçersiz hesap |
| 16 | `ubi_disabled` | Ubisoft girişi devre dışı |
| 17 | `account_restricted` | Hesap kısıtlandı |
| 18 | `network_restricted` | Ağ kısıtlandı |
| 19 | `error_connecting` | Bağlantı hatası |
| 20 | `logon_fail` | Giriş başarısız |
| 21 | `captcha_requested` | Captcha çözümü istendi |
| 22 | `mod_entered` | **Dünyaya Moderator girdi!** |
| 23 | `player_entered` | Dünyaya başka oyuncu girdi |
| 24 | `high_load` | Yüksek sunucu yükü |
| 25 | `high_ping` | Yüksek gecikme süresi |
| 26 | `changing_subserver` | Alt sunucuya geçiliyor |
| 27 | `stopped` | Bot durduruldu |
| 28 | `getting_server_data` | Sunucu verisi alınıyor |
| 29 | `bypassing_server_data` | Sunucu verisi atlatılıyor |
| 30 | `could_not_warp` | Dünyaya ışınlanamadı |
| 31 | `bad_inventory` | Envanter verisi bozuk |
| 32 | `bad_gateway` | Ağ geçidi hatası |
| 33 | `server_issue` | Sunucu sorunu |
| 34 | `retrieving_token` | Token alınıyor |
| 35 | `two_factor` | 2FA onay kodu gerekli |
| 36 | `google_logon_fail` | Google girişi başarısız |
| 38 | `steam_logon_fail` | Steam girişi başarısız |
| 39 | `linking_steam` | Steam hesabı bağlanıyor |
| 40 | `steam_not_linked` | Steam hesabı bağlı değil |
| 41 | `solving_captcha` | Captcha çözülüyor |
| 42 | `failed_captcha` | Captcha çözülemedi |
| 43 | `banwave_detected` | **Ban dalgası tespit edildi!** |
| 44 | `sms_error` | SMS onay hatası |

---

### [Enum: GoogleStatus] — 21 Durum Kodu (`bot:google_status()`)
| ID | Enum Adı | Anlamı ve Çözümü |
|---|---|---|
| 0 | `idle` | Boşta, istek bekleniyor veya işlem başarıyla bitti |
| 1 | `processing` | Google OAuth token'ı alınıyor |
| 2 | `bad_server` | glServer yanıtı geçersiz |
| 3 | `bad_connection` | glServer ile iletişim kurulamadı |
| 4 | `invalid_key` | **AccessKey hatalı! glServer.exe konsolundaki anahtarı girin** |
| 5 | `missing_server` | **glServer.exe çalışmıyor veya port yanlış** |
| 6 | `missing_local_server` | glServer localhost soketi bulunamadı |
| 7 | `timeout` | Google yanıt vermedi, zaman aşımı |
| 8 | `driver_closed` | Headless Chrome/Selenium sürücüsü kapandı |
| 9 | `init_error` | glServer başlatma hatası |
| 10 | `invalid_credentials` | Gmail veya şifre hatalı |
| 11 | `invalid_secret` | Secret key geçersiz |
| 12 | `account_disabled` | Google hesabı kapatılmış/devre dışı |
| 13 | `captcha_required` | Google girişi robot doğrulaması (Captcha) istedi |
| 14 | `phone_required` | Google SMS / telefon doğrulaması istedi |
| 15 | `recovery_required` | Google kurtarma e-postası onayı istedi |
| 16 | `otp_required` | Google Authenticator (2FA) kodu istedi |
| 17 | `invalid_challenge` | Challenge yanıtı reddedildi |
| 18 | `couldnt_verify` | Kimlik doğrulanamadı |
| 19 | `unknown_url` | Beklenmeyen Google yönlendirmesi |
| 21 | `redirect` | OAuth başarılı, Growtopia'ya yönlendirildi |

---

### [Diğer Enumlar]
- **`Action`:** `move=0`, `collect=1`, `hit=2`, `place=3`, `harvest=4`, `plant=5`, `warp=6`, `drop=7`, `trash=8`
- **`Bubble`:** `none=0`, `talk=1`, `brb=2`
- **`Event`:** `variantlist=0`, `update_packet=1`, `track_packet=2`, `generic_text=3`, `game_message=4`, `got_punched=5`, `mod_enter=6`, `render=7`
- **`GeigerArea`:** `null=0`, `red=1`, `yellow=2`, `green=3`, `rapid=4`, `prize=5`
- **`Method`:** `get=0`, `post=1`, `patch=2`, `put=3`, `delete=4`, `head=5`
- **`Platform`:** `windows=0`, `ios=1`, `macos=2`, `android=4`, `ubiconnect=13`, `steam=15`, `apple=69`
- **`Proxy`:** `none=0`, `http=1`, `https=2`, `socks5=3`
- **`Role`:** `farm=0`, `build=1`, `surg=2`, `fish=3`, `cook=4`, `startopia=5`
- **`StorageType`:** `pack=0`, `seed=1`

---

## 4. BOT METOTLARI LİSTESİ (100% GERÇEK RUNTIME)

```lua
-- Temel Kontrol & Durum
bot:name()                            -- Bot adini doner
bot:status()                          -- BotStatus int kodunu doner
bot:google_status()                   -- GoogleStatus int kodunu doner
bot:connect()                         -- Oyuna baglanir
bot:disconnect()                      -- Oyundan cikar
bot:warp(world, door_id)              -- Dunyaya isinlanir
bot:leaveWorld()                      -- Dunyadan ayrilir
bot:respawn()                         -- Yeniden dogar
bot:say(text)                         -- Chat'e mesaj yazar
bot:gem_count()                       -- Gem miktari
bot:pearl_count()                     -- Inci sayisi
bot:obtained_gem_count()              -- Oturumda kazanilan gem miktari
bot:obtained_pack_count()             -- Oturumda alinan pack miktari
bot:level()                           -- Bot seviyesi
bot:getPing()                         -- Gecikme suresi (ms)
bot:getCaptcha()                      -- Captcha cozum URL'si
bot:getInventory()                    -- Envanter nesnesi
bot:getWorld()                        -- Dunya nesnesi

-- Hareket & Blok Islemleri
bot:findPath(x, y)                    -- Koordinata yol bulur ve yurur
bot:moveTo(dx, dy)                    -- Adim atar
bot:place(x, y, item_id)              -- Blok/seed koyar
bot:hit(x, y)                         -- Yumruk atar
bot:wrench(x, y)                      -- Wrench acar
bot:wrenchPlayer(netid)               -- Oyuncuya wrench atar
bot:collect(range, interval)          -- Yerdeki objeleri toplar
bot:collectByID(id)                   -- Sadece belirli esyayi toplar
bot:collectObject(uid)                -- Belirli objeyi toplar
bot:drop(id, count)                   -- Esya yere atar
bot:fastDrop(id, count)               -- Hizli esya atar
bot:trash(id, count)                  -- Esya siler
bot:fastTrash(id, count)              -- Hizli esya siler
bot:wear(id)                          -- Esya giyer
bot:unwear(id)                        -- Esya cikarir
bot:use(id)                           -- Tuketime uygun esyayi kullanir
bot:buy(item_id, count, max_price)    -- Vend'den esya alir

-- Guvenlik & Yapilandirma
bot:legit_mode(bool)                  -- Insansi hareket modu
bot:anti_fire(bool)                   -- Yangin korumasi
bot:anti_toxic(bool)                  -- Zehir korumasi
bot:ignore_gems(bool)                 -- Gemleri toplamaz
bot:ignore_essences(bool)             -- Ozleri toplamaz
bot:hide_gems(bool)                   -- Gem gosterimini gizler
bot:leave_world_before_warp(bool)     -- Isinlanmadan once cikis yapar
bot:setPlatform(Platform.windows)     -- Cihaz platformunu ayarlar
bot:setCountry("tr")                  -- Ulke kodunu ayarlar
bot:bypass_logon(bool)                -- Logon bypass modu
bot:auto_reconnect(bool)              -- Otomatik yeniden baglanma
bot:auto_leave_on_mod(bool)           -- Mod gelince aninda kacma
bot:auto_leave_on_admin(bool)         -- Admin gelince aninda kacma
```

---

## 5. OTOMASYON MOTORLARI

Lucifer, dahili C++ otomasyon motorlarına sahiptir:
- `bot.auto_farm`: `auto_break`, `auto_place`, `id`, `mag_x`, `mag_y`, `seed_storage`, `block_storage`, `enabled`
- `bot.auto_geiger`: `addWorld`, `removeWorld`, `use_chocolate`, `addStorage`, `spread`, `enabled`
- `bot.auto_spam`: `messages`, `interval`, `random_interval`, `use_color`, `randomizer`, `enabled`
- `bot.auto_fish`: `world`, `getRod`, `setRod`, `getBait`, `setBait`, `auto_trawler`, `auto_drill`, `enabled`
- `bot.auto_cook`: `world`, `x`, `y`, `setFood`, `setTemperature`, `interval`, `enabled`
- `bot.auto_parkour`: `setWebhook`, `setTicket`, `setReward`, `limit`, `block`, `enabled`
- `bot.auto_message`: `message`, `interval`, `victim_uid`, `uid_count`, `ignore_admin`, `loop_mode`, `enabled`
- `bot.auto_carnival`: `reward_storage`, `ticket_storage`, `selected_game`, `auto_buy`, `enabled`
- `bot.auto_crime`: `world`, `tool_storage`, `reward_storage`, `auto_bbq`, `auto_wave`, `enabled`
- `bot.rotation`: `primary`, `secondary`, `pnb_world`, `pnb_in_home`, `harvest_until_level`, `tiles`, `enabled`

---

## 6. HTTP İSTEMCİSİ (HTTPCLIENT) DOĞRU KULLANIMI

```lua
-- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp
local client = HttpClient.new()
client.url = "http://127.0.0.1:8829/api/heartbeat"
client.method = Method.post
client.content = '{"name":"Bot1","status":"online"}'
client.body = client.content

local res = client:request()
if res and res.body then
    print("Sunucu Yaniti: " .. tostring(res.body))
end
```

---

## 7. GOOGLE LOGIN CAPTCHA ÇÖZÜM REHBERİ (glServer vs Lucifer İçi Ayarlar)

### Temel Kavram: İki Farklı Captcha Türü Vardır!
1. **Growtopia Oyun İçi Captcha'ları:**
   - Bot oyundayken Growtopia'nın çıkardığı görsel/puzzle doğrulamalarıdır (`bot:getCaptcha()`).
   - Bu doğrulama Lucifer'ın **Captcha Settings** sekmesindeki API anahtarı ile otomatik çözülür.
2. **Google Login (Gmail OAuth) Captcha'ları:**
   - Bot oyuna girmeden önce `glServer.exe` tarayarak Google OAuth token'ı alırken Google'ın sorduğu reCAPTCHA / bot doğrulamasıdır.
   - **Lucifer'ın Captcha Settings sekmesi bu aşamada DEVREYE GİRMEZ!**
   - Bu doğrulamayı **`glServer.exe`** çözer veya yönetir.

### `"Couldn't Solve Captcha."` Hatasının Nedeni
Konsolda şu yanıtı gördüğünüzde:
```json
{"statusCode":13,"status":"captcharequired","id":"berk.webops@gmail.com","data":"Couldn't Solve Captcha."}
```
Bunun tek sebebi, `glServer.exe` varsayılan ayarlarında şunların olmasıdır:
- `selectedSolver: 0 (none)`  -> Hiçbir çözücü seçili değildir.
- `userInteraction: False`   -> Kullanıcının elle çözmesine izin verilmez, hemen hata verir.

### Kesin Çözüm Yolları

#### Yöntem 1: Ücretsiz Manuel Etkileşim & Profil Kaydetme (Tavsiye Edilen)
Hiçbir API anahtarına veya bakiye ödemeye gerek yoktur:
> 💡 **Altın Kural:** glServer.exe açıkken konsoluna `set useHeadless False`, `set userInteraction True`, `set saveProfile True` yazıp bir kere botu bağladığında bu dertten tamamen kurtulmuş olacaksın!

1. `glServer.exe` konsoluna girin ve şu 3 komutu çalıştırın:
   ```cmd
   set useHeadless False
   set userInteraction True
   set saveProfile True
   ```
2. Lucifer'da botu **Connect** yapın.
3. Ekranda otomatik olarak Google Chrome/Edge penceresi açılacaktır. Google Captcha sorduğunda elle kutucuğa tıklayıp doğrulayın.
4. Başarılı olduktan sonra oturum `chrome/` klasörüne kaydedilir (`saveProfile True`).
5. **Sonuç:** Google bu cihazı/tarayıcıyı güvenli tanır ve sonraki girişlerde **ASLA BİR DAHA CAPTCHA SORMAZ!**


#### Yöntem 2: CapSolver ile Otomatik Çözüm
1. `glServer.exe` konsoluna yazın:
   ```cmd
   set selectedSolver 1
   ```
2. İndirilen `gl_server_1.6/capsolver/assets/config.json` dosyasını açın.
3. `"apiKey": "CAP-..."` alanına CapSolver anahtarınızı yapıştırın.

#### Yöntem 3: CapMonster ile Otomatik Çözüm
1. `glServer.exe` konsoluna yazın:
   ```cmd
   set selectedSolver 2
   ```
2. `gl_server_1.6/capmonster/assets/config.json` içine ClientKey yapıştırın.

#### Yöntem 4: MiniRPA (Yerel Çözücü)
1. `glServer.exe` konsoluna yazın:
   ```cmd
   set selectedSolver 3
   ```

---

## 8. CANLI DÜNYA & OYUN İÇİ NESNELER (%100 RUNTIME DUMP v3.0)

Bot oyundayken doğrudan erişilebilen C++ nesneleri, özellikleri ve metotları:

### 1. `World` Nesnesi (`getBot():getWorld()` veya `getWorld()`)
- `world.name` : string — Dünyanın adı (örn. `"ASDASDASDASVASD"`).
- `world.x` : number — Dünya genişliği (Growtopia standart: `100` karo).
- `world.y` : number — Dünya yüksekliği (Growtopia standart: `60` karo).
- `world.weather` : number — Hava durumu ID'si.
- `world:hasAccess()` : boolean — **Botun bu dünyada kilit/inşaat yetkisi var mı?**
- `world:getTile(x, y)` : Tile — Belirtilen koordinattaki karo nesnesi.
- `world:getTiles()` / `world:getTilesSafe()` : table — Dünyadaki tüm 6000 karonun listesi.
- `world:getPlayers()` : table — Dünyadaki tüm oyuncuların (NetAvatar) listesi.
- `world:getObjects()` : table — Yerdeki yüzen eşyaların (NetObject) listesi.

### 2. `Tile` Nesnesi (`getTile(x, y)`)
- `tile.x` : number — Karo X koordinatı (`0 - 99`).
- `tile.y` : number — Karo Y koordinatı (`0 - 59`).
- `tile.fg` : number — Ön plandaki blok/ağaç eşya ID'si (`0` ise boş).
- `tile.bg` : number — Arka plandaki duvar/background eşya ID'si (`0` ise boş).
- `tile.flags` : number — Karo bayrakları (çarpışma, su, alev vb.).
- `tile:canHarvest()` : boolean — **AĞAÇ TAM BÜYÜDÜ MÜ?** Hasata hazır ise `true` döner.
- `tile:hasExtra()` : boolean — Karo üzerinde ek veri (kilit, tabela, kapı, tohum) var mı?
- `tile:getExtra()` : TileExtra — Karodaki ek veriyi (`TileExtra` nesnesi) döner.

### 3. `TileExtra` Nesnesi (`tile:getExtra()`)
- `tile_extra.id` : number — Karodaki ekstra eşyanın ID'si (ör. kilit ID veya tohum ID).
- `tile_extra.count` : number — Depolanan eşya veya ağaçtaki meyve sayısı.
- `tile_extra.growth` : number — **Ağacın ekilmesinden itibaren geçen saniye!**
- `tile_extra.flags` : number — Ekstra bayraklar.

### 4. `Player` Nesnesi (`getPlayers()` veya `getLocal()`)
- `player.name` : string — Oyuncunun GrowID'si (`"Berkimmm"`).
- `player.netid` : number — Oyuncunun o dünyadaki ağ ID'si.
- `player.userid` : number — Oyuncunun kalıcı sayısal User ID'si.
- `player.country` : string — Oyuncunun ülke kodu (`"us"`, `"tr"`).
- `player.clothes` : Clothes — Oyuncunun giydiği eşyalar.

### 5. `InventoryItem` Nesnesi (`getInventory():getItems()`)
- `item.id` : number — Eşya ID'si.
- `item.count` : number — Çantadaki miktar (`1 - 200`).
- `item.isActive` : boolean — **Eşya şu an elde/üzerinde takılı mı?**

### 6. `ItemDescription` Nesnesi (`getInfo(id)`)
- `info.id` : number — Eşya ID'si.
- `info.name` : string — Eşya adı (örn. `"Dirt"`, `"Sugar Cane"`).
- `info.rarity` : number — Nadirlik puanı.
- `info.growth` : number — **Tohumun tam büyüme süresi (saniye cinsinden)!**
- `info.flags` : number — Eşya bayrakları.

---

## 9. 🛡️ BAN KORUMA & MANTIK HATASI ÖNLEME ZORUNLU KURALLARI

Growtopia'da banlanmaların %95'i hız sınırlarını aşmaktan (CPS/Speed check), moderatör tespit edememekten ve mantık hatalarından kaynaklanır. Yazılan **HER LUA SCRIPTİNDE** aşağıdaki kurallar harfiyen uygulanmalıdır:

### 1. İnsan Benzeri Dinamik Gecikmeler (Humanized Jitter Delays)
- **ASLA sabit gecikme kullanma!** `sleep(150)` gibi robotik ve sabit tekrarlar sunucu tarafında imza tespiti (heuristic detection) ile yakalanır.
- **Her zaman dinamik varyasyon ekle:**
  ```lua
  -- Dogru ve Guvenli Gecikmeler (Pure ASCII):
  sleep(170 + math.random(15, 45))  -- Blok kirma / Vurma (Punch / Hit)
  sleep(145 + math.random(15, 35))  -- Blok koyma (Place)
  sleep(160 + math.random(20, 50))  -- Esya toplama (Collect)
  sleep(3500 + math.random(200, 600)) -- Dunya isinlanma (Warp)
  sleep(350 + math.random(50, 100)) -- Esya atma / Cop (Drop / Trash)
  ```

### 2. Moderatör ve Ban Dalgası Otomatik Kaçış (Mod Evasion)
- Döngü her döndüğünde veya periyodik olarak dünyaya yetkili girip girmediği kontrol edilmelidir:
  ```lua
  -- Mod girisi kontrolu (BotStatus 22 = mod_entered)
  -- DIKKAT: bot.status bir sayidir (property). bot:getBotStatus() DIYE BIR METOT YOKTUR!
  if bot.status == 22 then
      bot:say("BRB")
      sleep(500)
      bot:warp("EXIT")
      sleep(4000)
      return
  end

  -- Banwave algilandiysa (BotStatus 43 = banwave_detected)
  if bot.status == 43 then
      sleep(60000) -- Tum islemleri dondur
      return
  end
  ```

### 3. Sıfır Mantık Hatası (Zero Logic Bugs)
1. **Dünya ve Karo Nil Kontrolü (Crash Önleme):**
   ```lua
   local world = bot:getWorld()
   if not world then
       sleep(1000)
       return
   end
   local tile = world:getTile(target_x, target_y)
   if not tile then return end
   ```
2. **Envanterde Olmayan Eşyayı Koymaya Çalışmama:**
   - Eşya adedi `0` iken `bot:place()` çağırmak sunucuya geçersiz paket yollar ve ban riskini artırır.
   ```lua
   local has_item = false
   for _, it in pairs(bot:getInventory()) do
       if it.id == target_item_id and it.count > 0 then
           has_item = true
           break
       end
   end
   if not has_item then return end -- Esya yoksa koyma
   ```
3. **Büyümemiş Ağacı Kırmaya Çalışmama:**
   - Ağaç henüz meyve vermemiş veya büyümemişse hasat etmeye çalışma:
   ```lua
   if tile:canHarvest() then
       bot:hit(tile.x, tile.y)
   end
   ```
4. **Çanta Doluluk (200 Adet) Kontrolü:**
   - Envanter 200 adet doluyken toplamaya çalışmak gem ve tohum kaybına yol açar. Toplamadan veya kırmadan önce çanta kontrol edilip gerekirse boşaltılmalıdır.
5. **Sonsuz Döngü Kilitlenmesi (Client Freezing):**
   - İçinde `sleep(ms)` bulunmayan hiçbir `while true do` döngüsü yazılamaz; aksi takdirde Lua thread'i işletim sistemini kilitler ve Lucifer çöker.
6. **Koordinat Sınırları ve Bölme Yasağı:**
   - `bot.x` ve `bot.y` zaten blok koordinatıdır. Asla 32'ye bölme!
   - Hedef koordinat daima `0 <= x < 100` ve `0 <= y < 60` aralığında olmalıdır. Solid duvarların içine ışınlanmaya çalışmak noclip banı sebebidir (`bot:findPath` kullanılmalıdır).

### 4. Kesinlikle Yasaklı Uydurma Metotlar (Hallucination Traps)
1. **`bot:getBotStatus()` YASAK:**
   - Lucifer C++ motorunda botun durumu `bot.status` sayısal özelliği (property) ile okunur (`0` ile `44` arası).
   - `bot:getBotStatus()` şeklinde çağırmak `attempt to call a nil value (method 'getBotStatus')` hatası verir.
2. **`world:getDoors()` YASAK:**
   - Lucifer'da `world` nesnesi üzerinde `getDoors()` metodu **yoktur**.
   - Bir dünyaya ışınlanmak için doğrudan `bot:warp("DUNYA_ADI")` veya `bot:warp("DUNYA_ADI", "KAPI_ID")` kullanılır.
   - Dünyadaki kapıları tespit etmek için `world:getTiles()` listesi taranarak `tile.fg == 6` (normal kapı) veya `tile.fg == 12` (ana giriş kapısı) aranır.
3. **`world:name()` YASAK:**
   - `world.name` bir metin özelliğidir (`string`), metot değildir. Parantezli çağrı (`world:name()`) `attempt to call a string value` hatası verir.
4. **Koordinat Bölme Yasağı:**
   - `bot.x` ve `bot.y` zaten karo koordinatıdır; asla 32'ye bölünmez.



