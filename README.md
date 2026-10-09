# 👷 Victor's Company Farmer

Bot farmer otomatis untuk **Victor's Company** — Telegram Mini App dengan reward token **VIC**. Multi-akun, auto get pass, auto mining, auto task, auto withdraw, dengan dashboard Rich Live.

---

## ✨ Fitur

- 🔐 **Auto Login Telegram** — Login via Telethon, session disimpan di `sessions/acc_XXX.session`
- 📥 **Auto Fetch initData** — Ambil `tgWebAppData` dari WebView bot, cached 50 menit
- 🔑 **Auto Get humanPass** — Buka Chromium, intercept `X-Human-Pass` header dari network
- ⛏️ **Auto Mining** — Klaim VIC otomatis saat pending ≥ minimum
- ✅ **Auto Check-in** — Klaim check-in harian
- 🎯 **Auto Task** — Klaim task board dengan dwell 11-15 detik (random seperti manusia)
- 👥 **Auto Squad** — Klaim hiring bonus & komisi referral
- 💸 **Auto Withdraw** — Cek wallet terhubung dulu, buffer 200 di atas minimum
- 🔄 **Dynamic Loop** — Bangun saat task reset (dari `availableAt` API), bukan interval tetap
- 🖥️ **Dashboard Rich Live** — 6 slot per akun, akun dipisah garis, real-time
- 📝 **Logger** — Semua error & traceback ke `error.log`
- 🖥️ **Window Mode** — `normal` / `minimize` / `offscreen` (fleksibel)
- 🔁 **Auto Refresh humanPass** — Otomatis refresh saat sisa < 3 jam

---

## 📋 Requirement

- **Python** 3.10+ (rekomendasi 3.11+)
- **Windows / Linux / macOS**
- **Chrome / Chromium** (untuk Turnstile — Playwright/Patchright bundled)
- **Telegram API ID & Hash** — dari https://my.telegram.org
- **Akun Telegram** yang sudah join Victor's Company

---

## 🚀 Instalasi

### 1. Clone Repository

```bash
git clone https://github.com/erwindobp98/vic.git
cd vic
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Isi `requirements.txt`:**

```txt
httpx>=0.27.0
rich>=13.7.0
telethon>=1.36.0
patchright>=1.0.0
```

### 3. Install Chromium untuk Patchright

```bash
python -m patchright install chromium
```

**Kalau gagal**, pakai fallback playwright:

```bash
python -m playwright install chromium
```

### 4. Setup `config.json`

Jalankan script — `config.json` akan dibuat otomatis:

```bash
python vic.py
```

Setelah dibuat, edit `config.json` dan isi:

```json
{
  "telegram": {
    "api_id": 123456,
    "api_hash": "your_api_hash_here"
  }
}
```

**Cara dapat `api_id` & `api_hash`:**

1. Buka https://my.telegram.org
2. Login dengan nomor Telegram
3. Klik **API development tools**
4. Isi form (App title, Short name, dll)
5. Copy **App api_id** dan **App api_hash** ke `config.json`

---

## 📖 Cara Pakai

### ➕ Tambah Akun Baru

```bash
python vic.py --add
```

Akan prompt:

```
Nomor Telegram untuk acc_001: +62812xxxxxxx
Kode OTP: 12345
Password 2FA: (kalau ada)
```

Ulangi untuk akun berikutnya (`acc_002`, `acc_003`, ...).

### 🚀 Jalankan Farmer

```bash
python vic.py
```

Yang terjadi otomatis:
1. Cek semua akun di `sessions/`
2. Cek `.pass` (humanPass cache) tiap akun — skip kalau masih valid
3. Get pass untuk akun yang expired (Chromium terbuka, intercept)
4. Start dashboard
5. Mining + task + squad + withdraw paralel per akun
6. Loop dynamic — bangun saat task reset

### 🔑 Get Pass Manual (1 Akun)

```bash
python vic.py pass acc_001
```

### 🔑 Get Pass Manual (Semua Akun)

```bash
python vic.py pass-all
```

### ❓ Bantuan

```bash
python vic.py help
```

---

## 🖥️ Contoh Dashboard

```
╭──────────── 👷 Victor's Company Farmer ────────────╮
│ ACCOUNT  │ SLOT      │ DETAIL                      │
├──────────┼───────────┼─────────────────────────────┤
│ acc_001  │ ACCOUNT   │ READY · Lv=49 | Speed=1.95… │
│          │ AUTH      │ OK · Pass dari cache        │
│          │ MINING    │ SUCCESS · +1.0142 VIC       │
│          │ TASK      │ SUCCESS · 3 task | +15.00   │
│          │ SQUAD     │ SUCCESS · hiring bonus: +25 │
│          │ WITHDRAW  │ SKIP · Balance 854 < 1275   │
├──────────┼───────────┼─────────────────────────────┤
│ acc_002  │ ACCOUNT   │ READY · Lv=1 | Speed=0.20…  │
│          │ AUTH      │ OK · Pass dari cache        │
│          │ MINING    │ SUCCESS · +0.1822 VIC       │
│          │ TASK      │ WAIT · React on Latest…     │
│          │ SQUAD     │ WAIT · Menunggu...          │
│          │ WITHDRAW  │ WAIT · Menunggu...          │
╰──────────┴───────────┴─────────────────────────────╯
```

**Status warna:**
- 🟢 `SUCCESS` / `READY` / `OK` — hijau
- 🟡 `WAIT` / `RUNNING` / `CLAIM` — kuning
- 🔴 `FAILED` / `ERROR` — merah
- 🔵 `CACHE` / `FETCH` / `REFRESH` — cyan

---

## ⚙️ Konfigurasi (`config.json`)

### Ringkasan

| Section | Fungsi |
|---------|--------|
| `telegram` | `api_id`, `api_hash` dari my.telegram.org |
| `bot` | Username bot, URL app, URL API |
| `turnstile` | Pengaturan Chromium & Cloudflare |
| `human_pass` | Cache expiry margin, auto refresh threshold |
| `mining` | Minimum claimable (default 5 VIC) |
| `tasks` | Dwell time min/max (11-15 detik) |
| `withdrawal` | Minimum, fee, buffer, status pending |
| `cycle` | Interval fallback, timeout, retry, stagger |
| `miner_curve` | Rumus speed/daily/holding (dari API) |

### Window Mode

Pada `turnstile.window_mode`, pilih:

| Mode | Efek | Cocok untuk |
|------|------|-------------|
| `"normal"` | Chromium tampil di layar | Debug / paling stabil |
| `"minimize"` | Chromium tampil 1 detik lalu minimize | Produksi (default) |
| `"offscreen"` | Chromium di luar layar | ⚠️ Sering gagal Cloudflare |

**Rekomendasi:** gunakan `"minimize"` untuk produksi.

---

## 📁 Struktur Folder

```
victors-farmer/
├── vic.py                     # Script utama
├── config.json                # Konfigurasi (otomatis dibuat)
├── requirements.txt           # Dependencies
├── error.log                  # Log error (auto)
├── README.md
├── sessions/                  # Data session per akun
│   ├── acc_001.session        # Session Telethon
│   ├── acc_001.initdata       # Cache initData
│   ├── acc_001.pass           # Cache humanPass
│   └── ...
├── data/                      # State per akun
│   └── acc_001.json
└── chromium-profiles/         # Profil Chromium per akun
    ├── acc_001/
    ├── acc_001_farmer/
    └── ...
```

---

## 🔧 Troubleshooting

### ❌ `Executable doesn't exist at ... chromium`

Chromium bundled belum diinstall:

```bash
python -m patchright install chromium
```

### ❌ `Session expired. Please reopen the app from Telegram`

`initData` sudah expired. Script akan fetch ulang otomatis (cache 50 menit). Kalau masih error:

```bash
rm sessions/*.initdata
python vic.py
```

### ❌ `HUMAN_REQUIRED` terus-menerus

`humanPass` invalid atau expired. Hapus cache dan jalankan ulang:

```bash
rm sessions/*.pass
python vic.py
```

### ❌ Chromium crash di Linux

Butuh dependencies tambahan:

```bash
sudo apt update
sudo apt install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
  libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
  libcairo2 libasound2
```

### ❌ Turnstile muncul terus di Chromium

Ubah `config.json` → `turnstile.window_mode` jadi `"normal"`. Jalankan sekali dengan Chromium tampil di layar untuk "memanaskan" profil, lalu kembali ke `"minimize"`.

### ❌ Multi akun berat / RAM habis

Ubah `config.json` → `turnstile.max_concurrent` menjadi `1` (satu Chromium buka dalam satu waktu). Sudah default `1`.

---

## 📝 Log

Semua log tersimpan di **`error.log`** dengan format:

```
2026-10-04 22:36:40 [INFO] [acc_001] initData OK (619 chars)
2026-10-04 22:36:41 [WARNING] [acc_001] HTTP 403 POST /auth/login
2026-10-04 22:36:42 [ERROR] [acc_001] Cycle error: RuntimeError: ...
```

Cek log terakhir:

```bash
tail -50 error.log
```

Atau di Windows:

```bash
type error.log
```

---

## 🔐 Keamanan

- **Session Telethon** disimpan sebagai SQLite di `sessions/acc_XXX.session` — **JANGAN commit ke GitHub**
- **`initData`** dan **`humanPass`** disimpan di folder `sessions/` — **JANGAN commit ke GitHub**
- **`config.json`** berisi `api_hash` — **JANGAN commit ke GitHub**

**Buat `.gitignore`:**

```gitignore
# Secrets
sessions/
data/
chromium-profiles/
chrome-profiles/
config.json
error.log

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
venv/
env/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

---

## ⚠️ Disclaimer

**Gunakan dengan risiko sendiri.**

- Bot ini adalah **otomatisasi pihak ketiga** — tidak resmi dari Victor's Company
- Bisa **melanggar Terms of Service** Victor's Company dan menyebabkan **akun di-ban**
- Script **tidak menyimpan** wallet phrase atau private key (karena tidak butuh)
- API endpoint bisa **berubah sewaktu-waktu** dan mematahkan script
- Turnstile Cloudflare bisa **mendeteksi browser otomatis** kapan saja

**Penulis tidak bertanggung jawab atas kerugian apapun** yang timbul dari penggunaan script ini.

---

**Selamat farming! 🚀**
