# ⚡ Dwi-Bot-Tele- (Alya & Gavin Superbot)

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Telethon](https://img.shields.io/badge/Library-Telethon%20MTProto-blueviolet?logo=telegram&logoColor=white)](https://github.com/LonamiWebs/Telethon)
[![AI Engine](https://img.shields.io/badge/AI-Google%20Gemini%20%7C%20Groq-4285F4?logo=google&logoColor=white)](https://aistudio.google.com/)
[![OS Support](https://img.shields.io/badge/OS-Linux%20%7C%20macOS%20%7C%20Termux-success?logo=linux&logoColor=white)](https://github.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Dwi-Bot-Tele-** (dikenal juga dengan persona **Alya & Gavin**) adalah superbot Telegram berbasis **Telethon (MTProto API)** berkinerja tinggi. Dilengkapi dengan arsitektur multi-tasking asinkron, bot ini menggabungkan AI Generatif cerdas, scraper media sosial lintas platform, hub balapan resmi (Formula 1 & MotoGP) dengan kartu visual dinamis, pemutar musik Hi-Fi, gerbang verifikasi captcha AI untuk grup, integrasi cloud mirror, pengingat sholat otomatis, serta konsol terminal interaktif (CLI) dua arah.

---

## 📑 Daftar Isi

- [Apa Saja Fungsinya? (Overview)](#-apa-saja-fungsinya-overview)
- [Fitur Utama](#-fitur-utama)
  - [1. Artificial Intelligence & Vision](#1-artificial-intelligence--vision)
  - [2. Universal Media Downloader](#2-universal-media-downloader)
  - [3. Musik & Audio Suite (Shazam Engine)](#3-musik--audio-suite-shazam-engine)
  - [4. Racing Hub (Formula 1 & MotoGP)](#4-racing-hub-formula-1--motogp)
  - [5. Manajemen Grup & AI Verification Gate](#5-manajemen-grup--ai-verification-gate)
  - [6. Cloud Storage & Mirroring (Gofile)](#6-cloud-storage--mirroring-gofile)
  - [7. Jadwal & Alarm Waktu Sholat Otomatis](#7-jadwal--alarm-waktu-sholat-otomatis)
  - [8. Sticker Snatcher / Kang Pack](#8-sticker-snatcher--kang-pack)
  - [9. Konsol Terminal Interaktif (Dual-Interface CLI)](#9-konsol-terminal-interaktif-dual-interface-cli)
  - [10. Proxy Chat ke Owner](#10-proxy-chat-ke-owner)
- [Struktur & Arsitektur Modul](#-struktur--arsitektur-modul)
- [Daftar Perintah (Commands Reference)](#-daftar-perintah-commands-reference)
- [Panduan Terminal CLI](#-panduan-terminal-cli)
- [Panduan Instalasi & Menjalankan Bot](#-panduan-instalasi--menjalankan-bot)
  - [Metode 1: Installer Otomatis (`install.sh`)](#metode-1-installer-otomatis-installsh)
  - [Metode 2: Setup Manual](#metode-2-setup-manual)
- [Konfigurasi Environment (`.env`)](#-konfigurasi-environment-env)
- [Manajemen Proses (tmux & systemd)](#-manajemen-proses-tmux--systemd)
- [Keamanan & Tips Pemeliharaan](#-keamanan--tips-pemeliharaan)

---

## 🎯 Apa Saja Fungsinya? (Overview)

Bot ini dirancang sebagai **asisten all-in-one serba mandiri** untuk obrolan personal maupun komunitas grup besar:
1. **Untuk Grup**: Mengamankan grup dari serangan bot/spammer menggunakan Captcha AI berbasis DM, menyediakan fitur auto-reply filter, catatan informasi (*notes*) multi-media, pesan sambutan (*welcome*), dan moderasi lengkap (*ban, mute, kick*).
2. **Untuk Penikmat Media & Musik**: Mengunduh video, musik, dan foto resolusi penuh tanpa watermark dari 13+ platform cukup dengan menempelkan tautan (*auto-detect link*).
3. **Untuk Fans Balapan**: Menyajikan jadwal balap, klasemen pembalap/konstruktor, serta hasil kualifikasi & balapan Formula 1 dan MotoGP dalam bentuk kartu grafis (*telemetry broadcast card*) berkualitas tinggi.
4. **Untuk Produktivitas & Asisten AI**: Menjawab pertanyaan kompleks, coding, penalaran multimodal dari gambar/stiker, serta generator gambar AI dengan gaya persona yang dapat diubah sesuai preferensi.
5. **Untuk Admin/Pemilik Server**: Mengontrol bot langsung dari layar terminal server menggunakan konsol CLI interaktif, membaca dan membalas pesan secara anonim tanpa perlu membuka aplikasi Telegram.

---

## 🚀 Fitur Utama

### 1. Artificial Intelligence & Vision
- **Multi-Key Google Gemini Rotation**: Rotasi otomatis API key Gemini (`gemini-3.1-flash-lite` atau model kustom) untuk menghindari kuota limit (429 Too Many Requests).
- **Groq Fallback**: Cadangan otomatis menggunakan model cepat LLM Groq (`qwen/qwen3-32b`).
- **Multimodal Vision (`/aigv`)**: Analisis dan penalaran gambar, stiker, atau foto secara mendalam.
- **Kustomisasi Gaya (`/setstyle`)**: Ubah kepribadian AI (contoh: santai, wibu, tsundere, sarkas, formal, dsb.).
- **Text-to-Image Generator (`/draw`)**: Hasilkan ilustrasi gambar baru langsung dari instruksi teks.
- **AI Monitor (`/statusai`)**: Pemantau status API key, latensi, dan model aktif.

### 2. Universal Media Downloader
Deteksi link otomatis (*auto-scrape*) atau via perintah `/snatch` / `/kang`:
- **TikTok**: Video HD tanpa watermark, audio asli, dan galeri slide foto.
- **Instagram**: Reels, postingan multi-slide (carousel), foto, dan Stories.
- **YouTube**: Video reguler, YouTube Shorts, dan audio MP3 (didukung `yt-dlp` & engine internal).
- **Twitter / X**: Video kualitas tertinggi dan gambar resolusi asli.
- **Threads**: Postingan teks, gambar, dan video.
- **Facebook**: Video publik, Facebook Reels, dan foto album.
- **Pinterest**: Video, GIF berulang, dan foto pin resolusi penuh.
- **Reddit**: Video dengan audio terintegrasi (*muxed*) dan gambar galeri.
- **Platform Lain**: CapCut template video, Bluesky, dan Pixiv artwork.
- **Mesin Cadangan Cerdas**: Didukung `aria2` multi-connection downloader dengan fitur resume unduhan yang terputus.

### 3. Musik & Audio Suite (Shazam Engine)
- **Cari Lagu Multi-Platform (`/msc <judul>`)**: Menu tombol inline interaktif untuk memilih lagu dari YouTube, Spotify, atau SoundCloud.
- **Download Langsung (`/msc <link>`)**: Konversi otomatis ke MP3/FLAC dengan penyisipan metadata ID3 lengkap (judul, artis, album, dan cover art).
- **Deteksi Musik Otomatis (Shazam)**: Balas pesan audio, rekaman suara (*voice note*), atau klip video apa saja dengan `/msc` untuk mendeteksi judul lagu dan penyanyinya dalam hitungan detik.

### 4. Racing Hub (Formula 1 & MotoGP)
- **Menu Siaran Balap (`/racing`)**: Dashboard terpadu navigasi F1 dan MotoGP.
- **Formula 1 (`/f1`)**:
  - Klasemen pembalap & konstruktor (*Driver & Constructor Standings*).
  - Jadwal balapan mendatang dan hitung mundur sesi latihan, kualifikasi, sprint, & race.
  - Hasil balapan terakhir (*last race result*).
- **MotoGP (`/motogp`)**:
  - Klasemen kejuaraan dunia pembalap (*Rider Standings*).
  - Hasil sesi latihan bebas, kualifikasi, sprint race, dan balapan utama.
- **Pillow Broadcast Card Renderer**: Hasil balapan dan klasemen digenerate menjadi kartu grafis beresolusi tinggi dengan foto pembalap, bendera negara, warna tim resmi, layout sirkuit, dan *timing tower*.

### 5. Manajemen Grup & AI Verification Gate
- **AI Join Gate Captcha (`/verify on|off`)**:
  - Member baru yang masuk otomatis di-mute total secara instan.
  - Bot mengirim tombol deep-link ke DM bot untuk memulai verifikasi.
  - Gemini AI membuat pertanyaan logika/human test acak dalam Bahasa Indonesia, Inggris, atau bahasa pilihan user.
  - Jawaban dinilai menggunakan pemahaman semantik AI (bukan string-matching kaku).
  - Jika lulus, status mute di grup otomatis dicabut. Jika gagal 3x atau melewati batas waktu (default 5 menit), member akan di-kick otomatis.
- **Filters ala @MissRose_bot (`/filter`, `/stop`, `/filters`)**: Balasan otomatis berdasarkan kata kunci tertentu.
- **Notes System (`/save`, `/get`, `#namanote`, `/notes`, `/clear`)**:
  - Menyimpan teks atau berkas media yang bisa dipanggil kembali kapan saja.
  - **Mendukung Album Media (`grouped_id`)**: Jika membalas album foto/video, seluruh berkas dalam album akan diunduh dan disimpan ke disk lokal bot secara permanen.
- **Pesan Sambutan Dinamis (`/welcome`, `/setwelcome`)**: Pesan selamat datang kustom dengan tag variabel otomatis (`{first}`, `{fullname}`, `{username}`, `{chatname}`, dll.).
- **Tindakan Moderasi**: `/ban`, `/unban`, `/mute`, `/unmute`, `/kick`, dan `/info`.

### 6. Cloud Storage & Mirroring (Gofile)
- **Perintah `/mirror`**:
  - Balas file apa saja di Telegram atau ketik `/mirror <link>` untuk mengunggah berkas ke **Gofile.io**.
  - Mendukung ekstraksi link langsung dari berbagai cloud hosting (Google Drive, Mediafire, Mega, dll.).
  - Progress bar dinamis bergaya ASCII dengan perhitungan kecepatan (*speed MB/s*) dan perkiraan waktu (*ETA*).
  - Terintegrasi dengan akun pribadi Gofile via `GOFILE_TOKEN`.

### 7. Jadwal & Alarm Waktu Sholat Otomatis
- **Perhitungan Waktu Sholat (`/praytime [kota]`)**: Jadwal waktu sholat harian untuk wilayah Indonesia dan global.
- **Adzan Reminder Background Loop**:
  - Mengirim notifikasi otomatis saat masuk waktu Subuh, Dzuhur, Ashar, Maghrib, dan Isya.
  - Disertai dengan file audio adzan berkualitas dan kartu visual waktu sholat.
  - Pengaturan zona waktu dan bahasa melalui tombol inline.

### 8. Sticker Snatcher / Kang Pack
- **Perintah `/snatch` atau `/kang`**:
  - Mengambil stiker, gambar, atau foto profil dan menambahkannya ke paket stiker Telegram milik bot/owner.
  - Mendukung konversi otomatis format gambar ke standar webp stiker Telegram.
  - Opsi `snatch_all` untuk mengkloning seluruh isi pack stiker milik orang lain secara batch.

### 9. Konsol Terminal Interaktif (Dual-Interface CLI)
Bot ini tidak hanya berjalan di latar belakang, tetapi juga menyediakan **Interactive Shell** langsung di terminal server menggunakan `prompt-toolkit`:
- **ASCII R Header & Live Telemetry**: Menampilkan banner ASCII "R", statistik CPU, RAM, OS, Python, dan ping saat startup.
- **Real-Time Log Tree**: Notifikasi pesan masuk dari PM maupun grup ditampilkan dalam format pohon warna-warni yang rapi (`🟢 [Message] Chat · Sender: Isi Pesan`).
- **Navigasi Chat (`/list`, `/openg`, `/read`)**: Buka ruang obrolan mana pun dan baca riwayat obrolan dari terminal.
- **Kirim & Balas Pesan Langsung**: Ketik teks biasa untuk mengirim pesan ke chat aktif, atau `/r #[id] <pesan>` untuk membalas pesan tertentu.
- **Kirim File dari Komputer**: Cukup ketik path file lokal di terminal (misal: `/home/user/foto.jpg Keren nih`) untuk mengirim media langsung ke Telegram.
- **Mode Hening (`/mute` & `/unmute`)**: Matikan sementara pencetakan pesan masuk di terminal tanpa mematikan proses bot.
- **In-Place Restart (`/restart`)**: Mulai ulang kode bot secara langsung tanpa memutus sesi tmux.

### 10. Proxy Chat ke Owner
- **`/chatowner` & `/stopchat`**: Pengguna dapat menghubungi owner bot secara aman.
- Permintaan obrolan masuk ke owner disertai tombol interaktif `[Terima]`, `[Tolak]`, dan `[Akhiri Chat]`.
- Pesan teks dan media diteruskan bolak-balik antara user dan owner secara transparan.

---

## 📂 Struktur & Arsitektur Modul

```text
├── main.py                     # Entrypoint bot, event loop, CLI terminal, & command dispatcher
├── install.sh                  # Installer universal (apt, pacman, dnf, apk, brew, pkg)
├── requirements.txt            # Dependensi pustaka Python
├── .env.example                # Template konfigurasi variabel lingkungan
├── .env                        # File konfigurasi rahasia (chmod 600)
│
├── admins/                     # Modul Administrasi Grup
│   ├── moderation.py           # Filters, notes, album media saver, welcome, ban/mute/kick
│   └── verify.py               # AI Join Gate captcha challenge (Gemini-powered DM verification)
│
├── scrapers/                   # Mesin Pengunduh Media Sosial
│   ├── ig.py                   # Scraper Instagram (Reels, Posts, Carousel, Stories)
│   ├── tiktok.py               # Scraper TikTok (No watermark, slides, music)
│   ├── youtube.py              # Scraper YouTube & Shorts
│   ├── twitter.py              # Scraper Twitter / X
│   ├── threads.py              # Scraper Threads
│   ├── facebook.py             # Scraper Facebook Video & Reels
│   ├── pinterest.py            # Scraper Pinterest (Video, GIF, Gambar)
│   ├── spotify.py              # Scraper & resolver Spotify audio
│   ├── soundcloud.py           # Scraper SoundCloud
│   ├── reddit.py               # Scraper Reddit
│   ├── bluesky.py              # Scraper Bluesky media
│   ├── capcut.py               # Scraper CapCut template
│   ├── pixiv.py                # Scraper Pixiv artwork
│   ├── aria2_dl.py             # Downloader pintar aria2 dengan fallback multi-koneksi
│   └── logs/                   # Log output debugging scraper
│
├── racing/                     # Mesin Motorsport Telemetry
│   ├── racing_service.py       # API client & parser jadwal/hasil F1 & MotoGP
│   ├── renderer.py             # Mesin pembuat kartu gambar siaran dengan Pillow (PIL)
│   ├── assets/                 # Logo tim, bendera, sirkuit, dan siluet pembalap
│   └── fonts/                  # Font tipografi untuk rendering kartu siaran
│
├── mirror/                     # Cloud Storage & Link Resolvers
│   ├── gofile_upload.py        # Uploader Gofile.io dengan ASCII progress bar
│   ├── gofile_api.py           # API wrapper Gofile
│   ├── link_resolvers.py       # Resolver URL langsung (Drive, Mediafire, dll.)
│   └── mega_dl.py              # Downloader berkas Mega.nz
│
├── stickers/                   # Manajemen Stiker
│   └── snatcher.py             # Sticker pack snatcher & image-to-sticker converter
│
├── uploader/                   # Optimasi Pengiriman File Telethon
│   └── fast_telethon.py        # Pengunggahan multi-chunk paralel cepat untuk file besar (>20MB)
│
└── dbbot/                      # Basis Data Lokal & File Runtime
    ├── db_chat/                # JSON konfigurasi per chat / grup
    ├── db_user/                # JSON profil pengguna
    ├── db_prayers/             # Basis data jadwal sholat & aset audio/gambar adzan
    ├── saved_media/            # Penyimpanan berkas media notes grup permanen
    ├── session/                # Telethon MTProto session file
    └── logs/                   # Berkas log bot (bot.log)
```

---

## 📜 Daftar Perintah (Commands Reference)

### Perintah Umum & Informasi
| Perintah | Deskripsi | Hak Akses |
| :--- | :--- | :--- |
| `/start` | Memulai bot dan membuka menu utama interaktif | Semua User |
| `/help` | Menampilkan panduan komprehensif seluruh fitur bot | Semua User |
| `/ping` | Mengukur kecepatan respon dan latensi bot | Semua User |
| `/stats` | Menampilkan statistik penggunaan RAM, CPU, disk, dan basis data | Semua User |
| `/info` | Menampilkan informasi identitas pengguna Telegram | Semua User |
| `/changelog` | Menampilkan riwayat pembaruan bot | Semua User |

### Artificial Intelligence & Gambar
| Perintah | Deskripsi | Contoh |
| :--- | :--- | :--- |
| `/aigm <prompt>` | Tanya AI (Google Gemini 3.1 Flash-Lite) multi-turn | `/aigm jelaskan cara kerja turbocahrger` |
| `/aigv [prompt]` | Analisis AI Visual (balas ke foto, gambar, atau stiker) | *Reply foto* `/aigv benda apa ini?` |
| `/draw <prompt>` | Hasilkan ilustrasi gambar baru menggunakan AI | `/draw a futuristic cyberpunk city in rain` |
| `/setstyle <style>` | Ubah gaya bahasa respons AI | `/setstyle santai dan humoris` |
| `/statusai` | Cek status kuota, API key, dan model AI yang aktif | `/statusai` |

### Media Downloader & Musik
| Perintah / Aksi | Deskripsi | Contoh |
| :--- | :--- | :--- |
| *Paste Link* | Otomatis mengunduh video/foto dari 13+ platform sosial | Kirim link TikTok / IG / YT ke chat |
| `/msc <judul>` | Cari lagu di YouTube, Spotify, atau SoundCloud | `/msc Bohemian Rhapsody` |
| `/msc <link>` | Unduh file audio kualitas tinggi dari tautan musik | `/msc https://open.spotify.com/track/...` |
| `/msc` (*reply*) | Identifikasi musik dari klip audio/video (Shazam) | *Reply video* `/msc` |
| `/snatch` / `/kang` | Ekstrak media dari balasan atau tautan | *Reply stiker/foto* `/snatch` |
| `/vidset` | Pengaturan preferensi format unduhan video | `/vidset` |
| `/asupan` | Mengirim video acak dari media pool | `/asupan` |
| `/asupopt` | Menu pengaturan opsi kategori video asupan | `/asupopt` |

### Formula 1 & MotoGP
| Perintah | Deskripsi | Argumen / Sub-menu |
| :--- | :--- | :--- |
| `/racing` | Buka menu siaran balapan terpadu | Tombol interaktif |
| `/f1` | Hub Formula 1 lengkap dengan kartu grafik visual | `drivers`, `constructors`, `race`, `sprint`, `quali`, `practice` |
| `/motogp` | Hub MotoGP resmi dengan timing tower visual | `riders`, `race`, `sprint`, `quali`, `practice` |

### Cloud Storage & File Mirroring
| Perintah | Deskripsi | Contoh |
| :--- | :--- | :--- |
| `/mirror <url>` | Unduh dari tautan eksternal lalu upload ke Gofile.io | `/mirror https://example.com/file.zip` |
| `/mirror` (*reply*) | Upload berkas/dokumen Telegram yang dibalas ke Gofile | *Reply dokumen Telegram* `/mirror` |

### Pengingat Waktu Sholat & Religi
| Perintah | Deskripsi | Contoh |
| :--- | :--- | :--- |
| `/praytime [kota]` | Cek jadwal 5 waktu sholat dan hitung mundur | `/praytime Jakarta` atau `/praytime Surabaya` |
| *(Otomatis)* | Siaran adzan audio dan kartu waktu sholat harian | Berjalan otomatis via background loop |

### Moderasi & Keamanan Grup (Khusus Admin)
| Perintah | Deskripsi | Contoh |
| :--- | :--- | :--- |
| `/verify on\|off` | Mengaktifkan/menonaktifkan gerbang Captcha AI untuk member baru | `/verify on` |
| `/filter <trigger> <teks>` | Membuat auto-reply untuk kata kunci tertentu | `/filter halo Halo juga kawan!` |
| `/stop <trigger>` | Menghapus filter kata kunci | `/stop halo` |
| `/stopall` | Menghapus semua filter kata kunci di grup | `/stopall` |
| `/filters` | Melihat daftar filter yang aktif di grup | `/filters` |
| `/save <nama> <konten>` | Menyimpan catatan (mendukung reply teks & album media) | `/save aturan Baca rules di pinned!` |
| `/get <nama>` atau `#nama` | Menampilkan isi catatan yang sudah disimpan | `/get aturan` atau `#aturan` |
| `/notes` | Menampilkan seluruh daftar catatan grup | `/notes` |
| `/clear <nama>` | Menghapus catatan tertentu | `/clear aturan` |
| `/notereply on\|off` | Mengatur apakah balasan notes me-reply pesan pemanggil | `/notereply on` |
| `/welcome on\|off` | Menyalakan/mematikan pesan sambutan member baru | `/welcome on` |
| `/setwelcome <teks>` | Mengatur format pesan sambutan (mendukung tag `{first}`, dll.) | `/setwelcome Selamat datang {mention}!` |
| `/resetwelcome` | Mengembalikan pesan sambutan ke format bawaan | `/resetwelcome` |
| `/ban`, `/unban` | Blokir atau buka blokir anggota grup | *Reply user* `/ban` |
| `/mute`, `/unmute` | Bungkam atau buka bungkam anggota grup | *Reply user* `/mute` |
| `/kick` | Keluarkan anggota dari grup | *Reply user* `/kick` |

### Komunikasi Owner
| Perintah | Deskripsi |
| :--- | :--- |
| `/chatowner` | Mulai sesi obrolan dua arah dengan Pemilik Bot (hanya di DM) |
| `/stopchat` | Akhiri sesi obrolan dengan Pemilik Bot |

---

## 💻 Panduan Terminal CLI

Saat bot dijalankan langsung atau di-attach dari terminal server, Anda disajikan antarmuka baris perintah berkemampuan penuh:

```text
 █▀▀█ 
 █▄▄▀ 
 █  █   OS: Linux 6.6 (x86_64) · CPU: 12% · RAM: 2.4 GB / 8.0 GB
 ▀  ▀   Python: 3.12 · Telethon: 1.36.0 · Bot: @Plendes_bot · Ping: 42ms
────────────────────────────────────────────────────────────────────────────────
> 
```

### Perintah Shell Konsol
| Perintah CLI | Fungsi |
| :--- | :--- |
| `/list` | Tampilkan daftar semua ruang obrolan (PM dan grup) yang pernah berinteraksi dengan bot |
| `/openg <no/nama/id>` | Buka ruang obrolan aktif berdasarkan indeks nomor, nama, atau ID Telegram |
| `/read [jumlah]` | Baca pesan terakhir pada obrolan aktif (default: 10 pesan, maks: 50) |
| `/r #[id] <pesan>` | Balas pesan spesifik pada obrolan yang sedang aktif |
| `/close` | Keluar dari ruang obrolan yang sedang dibuka |
| `/mute` atau `/notif off` | Mengaktifkan **Mode Hening** (pesan masuk tidak mencetak log di terminal) |
| `/unmute` atau `/notif on` | Mengaktifkan kembali pencetakan pesan masuk secara realtime di terminal |
| `/restart` | Restart proses bot secara langsung (*in-place execution*) |
| `/exit` atau `/stop` | Hentikan bot dan keluar dari terminal secara aman |

### Mengirim Pesan & Berkas via Terminal
- **Kirim Pesan Teks**: Setelah membuka chat dengan `/openg <target>`, cukup ketik teks Anda lalu tekan **Enter**.
- **Kirim File / Media Langsung**: Ketik path lengkap berkas di disk Anda beserta caption opsional:
  ```bash
  > /home/user/document.pdf Laporan terbaru
  > "/path/dengan spasi/foto.jpg" Foto dokumentasi
  ```
  *(Berkas berukuran di atas 20 MB akan otomatis dikirim menggunakan engine `fast_telethon` multi-part upload).*

---

## 🛠️ Panduan Instalasi & Menjalankan Bot

### Prasyarat Sistem
- **Sistem Operasi**: Linux (Ubuntu/Debian, Arch, Fedora, Alpine, openSUSE, Void), Android Termux, atau macOS.
- **Python**: Versi `3.10` atau lebih baru.
- **Dependensi Sistem**: `ffmpeg`, `aria2`, `tmux`, `git`, `curl`, `build-essential`.

---

### Metode 1: Installer Otomatis (`install.sh`)

Gunakan skrip instalasi interaktif universal yang telah disediakan:

```bash
git clone https://github.com/DwiPrdn/Dwi-Bot-Tele-.git
cd Dwi-Bot-Tele-
chmod +x install.sh
./install.sh
```

**Skrip `install.sh` akan secara otomatis:**
1. Mendeteksi distro Linux / sistem operasi Anda.
2. Menginstall dependensi paket sistem (`ffmpeg`, `aria2`, `python3-venv`, `tmux`, dll.).
3. Menyiapkan Python Virtual Environment (`./venv`) dan menginstall seluruh `requirements.txt`.
4. Membimbing Anda mengisi konfigurasi file `.env` secara interaktif.
5. Membuat runner skrip tmux (`start.sh`, `stop.sh`, `attach.sh`, dll.) atau memasang `systemd service`.

---

### Metode 2: Setup Manual

#### 1. Pasang Dependensi Sistem

- **Debian / Ubuntu / Linux Mint**:
  ```bash
  sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv ffmpeg aria2 tmux git
  ```
- **Arch Linux / Manjaro**:
  ```bash
  sudo pacman -Sy python python-pip ffmpeg aria2 tmux git base-devel
  ```
- **Fedora / RHEL**:
  ```bash
  sudo dnf install -y python3 python3-pip ffmpeg aria2 tmux git
  ```
- **Android Termux**:
  ```bash
  pkg update && pkg install -y python ffmpeg aria2 tmux git clang make
  ```

#### 2. Siapkan Virtual Environment & Modul Python

```bash
cd Dwi-Bot-Tele-
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### 3. Buat Folder Data Runtime

```bash
mkdir -p dbbot/logs dbbot/session dbbot/db_chat dbbot/db_user dbbot/saved_media downloads
```

#### 4. Konfigurasi File `.env`

Salin contoh template dan sesuaikan dengan kredensial Anda:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

---

## ⚙️ Konfigurasi Environment (`.env`)

Isi file `.env` Anda dengan kredensial yang valid:

```ini
# ==========================================
# Telegram API Credentials
# Dapatkan dari: https://my.telegram.org/apps
# ==========================================
API_ID=12345678
API_HASH=abcdef0123456789abcdef0123456789

# ==========================================
# Telegram Bot Configuration
# Dapatkan dari @BotFather di Telegram
# ==========================================
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
BOT_USERNAME=Plendes_bot
BOT_ID=123456789

# ==========================================
# Owner Configuration (ID Angka Telegram)
# Dapatkan dari bot @userinfobot
# ==========================================
OWNER_ID=987654321

# ==========================================
# AI Service Keys
# ==========================================
# Google Gemini API Keys (bisa多-key dipisahkan tanda koma untuk auto-failover)
# Dapatkan dari: https://aistudio.google.com/app/apikey
GEMINI_KEYS=AIzaSyA...,AIzaSyB...,AIzaSyC...
MODEL_NAME=gemini-3.1-flash-lite

# Groq API Key (Opsional / Fallback)
# Dapatkan dari: https://console.groq.com/keys
GROQ_KEY=gsk_...
GROQ_MODEL=qwen/qwen3-32b

# ==========================================
# Storage & Mirror (Opsional)
# ==========================================
# Token akun Gofile untuk upload ke akun pribadi (kosongkan jika tanpa akun)
GOFILE_TOKEN=
BASE_PATH=
```

---

## 🔄 Manajemen Proses (tmux & systemd)

### Menjalankan dengan Tmux (Sangat Direkomendasikan)
Menjalankan bot di background menggunakan sesi tmux terisolasi:

```bash
./start.sh     # Menjalankan bot di background (sesi: 'bot')
./attach.sh    # Membuka antarmuka konsol interaktif bot
./status.sh    # Memeriksa penggunaan resource dan tail log terbaru
./restart.sh   # Merestart sesi bot
./stop.sh      # Menghentikan bot
```

> **Catatan:** Saat berada di dalam sesi tmux (`./attach.sh`), tekan tombol `Ctrl + B` lalu tekan `D` untuk melepaskan (*detach*) terminal tanpa menghentikan proses bot.

### Menjalankan dengan Systemd Service (Server Production)
Jika Anda memilih opsi systemd saat menjalankan `install.sh`:

```bash
sudo systemctl status telegram-bot   # Cek status service
sudo journalctl -u telegram-bot -f   # Pantau realtime logs
sudo systemctl restart telegram-bot  # Restart bot
sudo systemctl stop telegram-bot     # Hentikan bot
```

---

## 🔒 Keamanan & Tips Pemeliharaan

1. **Amankan Kredensial `.env`**: Selalu pastikan izin akses file `.env` diset ke `600` agar tidak dapat dibaca oleh user lain di server:
   ```bash
   chmod 600 .env
   ```
2. **Multi-Key Gemini**: Gunakan 2–3 API key gratis dari Google AI Studio dan pisahkan dengan koma di `GEMINI_KEYS`. Bot akan otomatis beralih ke key berikutnya jika salah satu terkena pembatasan kuota (*rate limit*).
3. **Penyimpanan Media Notes**: Media notes grup disimpan di direktori `dbbot/saved_media/`. Bersihkan berkas lama secara berkala jika kapasitas server Anda terbatas.
4. **Git Safety**: File `.env`, folder `dbbot/`, dan cache Python sudah diatur di `.gitignore` untuk mencegah kebocoran data sensitif ke publik repository.

---

## 📄 Lisensi

Proyek ini dirilis di bawah lisensi [MIT License](LICENSE). Bebas digunakan, dimodifikasi, dan dikembangkan kembali dengan tetap mencantumkan atribusi pengembang asli.