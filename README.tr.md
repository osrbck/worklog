# worklog

**AI kodlama oturumlarını iş raporuna dönüştürür.** `/worklog`, bilgisayarında Claude Code, Codex,
Kiro ve OpenCode/OpenChamber ile yaptığın oturumları okur; belirttiğin sürede yapılan işleri proje
bazında, süre tahmini, commit'ler ve issue anahtarlarıyla madde madde yazar.

> 🇬🇧 English: [README.md](README.md)

```
/worklog dün
```

```
## Worklog · 5 Kasım Perşembe · ≈5s 40dk · 3 proje

### shop-api · ≈3s 10dk · feat/SHOP-42-cart · SHOP-42, SHOP-45
- ✅ SHOP-42 Sepet toplamındaki yuvarlama hatası düzeltildi, kupon desteği eklendi (≈1s 50dk, 3 commit)
- 🔄 SHOP-45 Ödeme sayfasına başlandı; form ve doğrulama hazır, ödeme adımı kaldı (≈1s 05dk)
- 🔍 Kararsız webhook testi incelendi, saate bağlı bir fixture'dan kaynaklandığı bulundu (≈15dk)
...
Toplam ≈5s 40dk · 6 commit · Claude Code, Codex, Kiro
```

## Nasıl çalışır

```
/worklog <aralık>
   │
   ├─ 1. toplayıcı (Python, sadece standart kütüphane, salt-okur)
   │     adapter'lar ── claude · codex · kiro · opencode
   │     → ortak model: proje, branch, senin istekler, düzenlenen dosyalar, önemli komutlar,
   │       ajanın son cevabı, aktivite zaman damgaları
   │     → gizli bilgiler maskelenir, enjekte edilen bağlam temizlenir, alt ajan ve
   │       workflow oturumları ana oturuma bağlanır
   │
   ├─ 2. git: bulunan her repoda aynı aralıktaki kendi commit'lerin (tüm branch'ler)
   │
   └─ 3. ajan raporu bu kısa JSON özetinden yazar
```

- **Yapıldı mı, konuşuldu mu?** Durumu commit'ler ve değişen dosyalar belirler: ✅ tamamlandı,
  🔄 devam ediyor, 🔍 araştırma/analiz.
- **Gerçekçi süre.** 30 dakikadan uzun boşluklar boşta sayılır; aynı projedeki paralel oturumlar
  iki kez sayılmaz.
- **İş başına tek madde.** Aynı özelliğe önce Claude'da sonra Codex'te çalıştıysan tek madde olur.
- **Issue anahtarları** (`ABC-123`) branch'lerden, commit mesajlarından ve isteklerinden yakalanır.

## Desteklenen araçlar

| Araç | Okunan veri | Durum |
|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` (alt ajanlar dahil) | ✅ test edildi |
| Codex (CLI ve IDE) | `~/.codex/sessions/**/rollout-*.jsonl` + `session_index.jsonl` | ✅ test edildi |
| Kiro (IDE ve CLI) | `~/.kiro/sessions/*/sess_*/` (workflow çalıştırmaları dahil) | ✅ test edildi |
| OpenCode / OpenChamber | `~/.local/share/opencode` (JSON veya SQLite) | 🧪 deneysel |

Kurulu olmayan araçlar atlanır. Konumlar ayarlardan değiştirilebilir; `CLAUDE_CONFIG_DIR`,
`CODEX_HOME`, `KIRO_HOME` ve `XDG_DATA_HOME` dikkate alınır.

## Kurulum

Gereksinimler: Python 3.8+, git ve Claude Code veya Codex. macOS, Linux ve WSL.

```bash
git clone https://github.com/osrbck/worklog.git ~/worklog
~/worklog/install.sh          # Claude Code
~/worklog/install.sh --codex  # Codex
~/worklog/install.sh --all    # ikisi birden
```

Kurulum betiği hangi oturum kaynaklarını bulduğunu listeler. Güncelleme:
`cd ~/worklog && git pull && ./install.sh`, kaldırma: `./install.sh --uninstall`.

## Kullanım

```
/worklog                       bugün
/worklog dün
/worklog bu hafta              (veya: geçen hafta, bu ay, son 3 gün, 2026-11-01..2026-11-05)
/worklog pazartesi 09:00'dan beri
/worklog geçen hafta shop-api
/worklog dün standup           Yapılanlar / Devam edenler / Engeller
/worklog bu hafta tablo        Tarih | Proje | Issue | İş | Süre | Durum
```

## Gizlilik

- Toplayıcı dosyaları sadece **okur** ve salt-okur `git log` çalıştırır. Ağa hiçbir istek atmaz.
- Ham sohbet dökümleri modele gitmez. Ajan kısa bir özet görür: istekler (280 karakterle sınırlı),
  dosya yolları, önemli komutlar ve ajanın son cevabı. Bilinen gizli bilgi formatları (API anahtarı,
  token, JWT, özel anahtar, `PASSWORD=` tarzı atamalar, URL içindeki kimlik bilgileri) maskelenir.
- Bu özet ajanla yaptığın sohbetin parçasıdır. Hassas projeleri `exclude_projects` ile dışarıda bırak.

## Ayarlar

İsteğe bağlı: `~/.config/worklog/config.json` (bütün alanlar opsiyonel). Örnek ve alanların
açıklaması için [README.md](README.md#configuration).

## Lisans

[MIT](LICENSE). worklog bir topluluk projesidir; Anthropic, OpenAI, AWS veya OpenCode projesiyle
bağlantılı değildir.
