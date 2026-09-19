#!/usr/bin/env bash
#
# Telegram Bot Universal Installer
# Compatible with: Debian/Ubuntu, Arch/Manjaro, Fedora/RHEL, Alpine, openSUSE, Void, Termux, macOS
#

set -e

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

info()    { echo -e "${CYAN}[*]${NC} $*"; }
ok()      { echo -e "${GREEN}[+]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
err()     { echo -e "${RED}[-]${NC} $*"; }
header()  { echo -e "\n${BOLD}${BLUE}=== $* ===${NC}\n"; }

ask() {
    local prompt="$1"
    local default="$2"
    local result
    if [ -n "$default" ]; then
        read -r -p "$(echo -e "${BOLD}${prompt}${NC} [${GREEN}${default}${NC}]: ")" result
        echo "${result:-$default}"
    else
        read -r -p "$(echo -e "${BOLD}${prompt}${NC}: ")" result
        echo "$result"
    fi
}

run_as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    elif command -v doas >/dev/null 2>&1; then
        doas "$@"
    else
        err "Perintah ini butuh akses root/sudo, tapi sudo/doas tidak ditemukan."
        exit 1
    fi
}

detect_platform() {
    if [ -n "$TERMUX_VERSION" ] || [ -d "/data/data/com.termux" ]; then
        echo "termux"
        return
    fi

    if [ "$(uname -s)" = "Darwin" ]; then
        echo "macos"
        return
    fi

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
            ubuntu|debian|linuxmint|pop|kali|elementary|raspbian)
                echo "debian"
                return
                ;;
            arch|manjaro|endeavouros|garuda|artix)
                echo "arch"
                return
                ;;
            fedora|rhel|centos|almalinux|rocky)
                echo "fedora"
                return
                ;;
            alpine)
                echo "alpine"
                return
                ;;
            opensuse*|sles)
                echo "suse"
                return
                ;;
            void)
                echo "void"
                return
                ;;
        esac

        case "${ID_LIKE:-}" in
            *debian*|*ubuntu*) echo "debian"; return ;;
            *arch*)            echo "arch"; return ;;
            *rhel*|*fedora*)   echo "fedora"; return ;;
            *suse*)            echo "suse"; return ;;
        esac
    fi

    echo "unknown"
}

# --- STEP 1: Platform Selection ---
header "Setup Lingkungan Sistem"

DETECTED_PLATFORM="$(detect_platform)"
info "Platform terdeteksi: ${BOLD}${DETECTED_PLATFORM}${NC}"

echo "Pilih jenis sistem operasi / distro target:"
echo "  1) Debian / Ubuntu / Linux Mint / Pop!_OS"
echo "  2) Arch Linux / Manjaro / EndeavourOS"
echo "  3) Fedora / RHEL / CentOS / Rocky / AlmaLinux"
echo "  4) Alpine Linux"
echo "  5) openSUSE"
echo "  6) Void Linux"
echo "  7) Android Termux"
echo "  8) macOS (Homebrew)"
echo "  9) Lewati instalasi paket sistem (Python/venv saja)"

case "$DETECTED_PLATFORM" in
    debian) DEFAULT_CHOICE=1 ;;
    arch)   DEFAULT_CHOICE=2 ;;
    fedora) DEFAULT_CHOICE=3 ;;
    alpine) DEFAULT_CHOICE=4 ;;
    suse)   DEFAULT_CHOICE=5 ;;
    void)   DEFAULT_CHOICE=6 ;;
    termux) DEFAULT_CHOICE=7 ;;
    macos)  DEFAULT_CHOICE=8 ;;
    *)      DEFAULT_CHOICE=1 ;;
esac

CHOICE=$(ask "Pilihan Anda" "$DEFAULT_CHOICE")

# --- STEP 2: Install System Packages ---
header "Instalasi Dependensi Sistem"

case "$CHOICE" in
    1)
        info "Menginstall paket via APT..."
        run_as_root apt-get update -y
        run_as_root apt-get install -y \
            python3 python3-pip python3-venv python3-dev \
            ffmpeg aria2 git curl wget tmux build-essential \
            libffi-dev libssl-dev
        ok "Paket sistem berhasil dipasang."
        TARGET_OS="debian"
        ;;
    2)
        info "Menginstall paket via Pacman..."
        run_as_root pacman -Sy --noconfirm \
            python python-pip python-virtualenv \
            ffmpeg aria2 git curl wget tmux base-devel \
            libffi openssl
        ok "Paket sistem berhasil dipasang."
        TARGET_OS="arch"
        ;;
    3)
        info "Menginstall paket via DNF/YUM..."
        PKG_MGR="dnf"
        command -v dnf >/dev/null 2>&1 || PKG_MGR="yum"
        run_as_root "$PKG_MGR" install -y \
            python3 python3-pip python3-devel \
            ffmpeg aria2 git curl wget tmux gcc make \
            libffi-devel openssl-devel
        ok "Paket sistem berhasil dipasang."
        TARGET_OS="fedora"
        ;;
    4)
        info "Menginstall paket via APK (Alpine)..."
        run_as_root apk update
        run_as_root apk add \
            python3 py3-pip py3-virtualenv python3-dev \
            ffmpeg aria2 git curl wget tmux build-base \
            libffi-dev openssl-dev
        ok "Paket sistem berhasil dipasang."
        TARGET_OS="alpine"
        ;;
    5)
        info "Menginstall paket via Zypper..."
        run_as_root zypper refresh
        run_as_root zypper install -y \
            python3 python3-pip python3-devel \
            ffmpeg aria2 git curl wget tmux gcc make \
            libffi-devel libopenssl-devel
        ok "Paket sistem berhasil dipasang."
        TARGET_OS="suse"
        ;;
    6)
        info "Menginstall paket via XBPS (Void)..."
        run_as_root xbps-install -Sy \
            python3 python3-pip python3-devel \
            ffmpeg aria2 git curl wget tmux base-devel \
            libffi-devel openssl-devel
        ok "Paket sistem berhasil dipasang."
        TARGET_OS="void"
        ;;
    7)
        info "Menginstall paket di Android Termux..."
        pkg update -y
        pkg install -y \
            python ffmpeg aria2 git curl wget tmux \
            clang make libjpeg-turbo libcrypt libffi openssl
        ok "Paket Termux berhasil dipasang."
        TARGET_OS="termux"
        ;;
    8)
        info "Menginstall paket via Homebrew (macOS)..."
        if ! command -v brew >/dev/null 2>&1; then
            err "Homebrew belum terpasang. Pasang dari https://brew.sh terlebih dahulu."
            exit 1
        fi
        brew install python@3 ffmpeg aria2 tmux git curl wget
        ok "Paket macOS berhasil dipasang."
        TARGET_OS="macos"
        ;;
    9)
        info "Melewati tahap instalasi paket sistem."
        TARGET_OS="$DETECTED_PLATFORM"
        ;;
    *)
        warn "Pilihan tidak valid, melanjutkan dengan Python bawaan sistem."
        TARGET_OS="$DETECTED_PLATFORM"
        ;;
esac

# --- STEP 3: Python Environment & Dependencies ---
header "Setup Python & Virtualenv"

if [ "$TARGET_OS" = "termux" ]; then
    info "Menggunakan runtime Python native Termux..."
    PYTHON_EXEC="$(command -v python3 || command -v python)"
    PIP_EXEC="$(command -v pip3 || command -v pip)"
    "$PIP_EXEC" install --upgrade pip setuptools wheel
else
    USE_VENV=$(ask "Gunakan virtual environment terisolasi (venv)? (y/n)" "y")
    if [[ "$USE_VENV" =~ ^[Yy]$ ]]; then
        if [ ! -d "venv" ]; then
            info "Membuat virtual environment di ./venv ..."
            python3 -m venv venv || virtualenv venv
        fi
        PYTHON_EXEC="$ROOT_DIR/venv/bin/python3"
        PIP_EXEC="$ROOT_DIR/venv/bin/pip"
        ok "Virtualenv siap: $PYTHON_EXEC"
    else
        PYTHON_EXEC="$(command -v python3 || command -v python)"
        PIP_EXEC="$(command -v pip3 || command -v pip)"
    fi
    "$PIP_EXEC" install --upgrade pip setuptools wheel
fi

if [ -f "requirements.txt" ]; then
    info "Menginstall pustaka dari requirements.txt ..."
    "$PIP_EXEC" install -r requirements.txt
    ok "Semua modul Python berhasil dipasang."
else
    warn "File requirements.txt tidak ditemukan, melewati instalasi pip."
fi

## Buat direktori data runtime jika belum ada
mkdir -p "$ROOT_DIR/dbbot/logs"
mkdir -p "$ROOT_DIR/dbbot/session"
mkdir -p "$ROOT_DIR/dbbot/db_chat"
mkdir -p "$ROOT_DIR/dbbot/db_user"
mkdir -p "$ROOT_DIR/dbbot/saved_media"
mkdir -p "$ROOT_DIR/scrapers/logs"
mkdir -p "$ROOT_DIR/downloads"

# Pastikan direktori data dapat ditulis oleh user saat ini
CURRENT_USER="$(id -un)"
CURRENT_GROUP="$(id -gn)"
if [ "$(id -u)" -eq 0 ] && [ -n "$SUDO_USER" ]; then
    CURRENT_USER="$SUDO_USER"
    CURRENT_GROUP="$(id -gn "$SUDO_USER" 2>/dev/null || id -gn)"
fi
run_as_root chown -R "$CURRENT_USER:$CURRENT_GROUP" "$ROOT_DIR/dbbot" 2>/dev/null || true

# --- STEP 4: Configuration (.env) ---
header "Konfigurasi Bot (.env)"

# Muat nilai lama dari .env jika sudah ada sebelumnya
OLD_API_ID=""
OLD_API_HASH=""
OLD_BOT_TOKEN=""
OLD_BOT_USERNAME="Plendes_bot"
OLD_OWNER_ID=""
OLD_BOT_ID=""
OLD_GEMINI_KEYS=""
OLD_MODEL_NAME="gemini-3.1-flash-lite"
OLD_GOFILE_TOKEN=""
OLD_BASE_PATH="$ROOT_DIR"

if [ -f ".env" ]; then
    info "Ditemukan file .env sebelumnya. Nilai lama akan dijadikan default."
    # Baca key .env tanpa merusak pemisah koma
    while IFS='=' read -r key val || [ -n "$key" ]; do
        [[ "$key" =~ ^#.*$ ]] && continue
        [ -z "$key" ] && continue
        val="$(echo "$val" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
        case "$key" in
            API_ID) OLD_API_ID="$val" ;;
            API_HASH) OLD_API_HASH="$val" ;;
            BOT_TOKEN) OLD_BOT_TOKEN="$val" ;;
            BOT_USERNAME) OLD_BOT_USERNAME="$val" ;;
            OWNER_ID) OLD_OWNER_ID="$val" ;;
            BOT_ID) OLD_BOT_ID="$val" ;;
            GEMINI_KEYS) OLD_GEMINI_KEYS="$val" ;;
            MODEL_NAME) OLD_MODEL_NAME="$val" ;;
            GOFILE_TOKEN) OLD_GOFILE_TOKEN="$val" ;;
            BASE_PATH) OLD_BASE_PATH="$val" ;;
        esac
    done < .env
fi

NEW_API_ID=$(ask "Telegram API_ID" "$OLD_API_ID")
NEW_API_HASH=$(ask "Telegram API_HASH" "$OLD_API_HASH")
NEW_BOT_TOKEN=$(ask "Telegram BOT_TOKEN (@BotFather)" "$OLD_BOT_TOKEN")

# Ekstrak default bot ID dari token jika ada
DERIVED_BOT_ID=""
if [[ "$NEW_BOT_TOKEN" == *":"* ]]; then
    DERIVED_BOT_ID="${NEW_BOT_TOKEN%%:*}"
fi
[ -z "$OLD_BOT_ID" ] && OLD_BOT_ID="$DERIVED_BOT_ID"

NEW_BOT_ID=$(ask "Telegram BOT_ID" "$OLD_BOT_ID")
NEW_BOT_USERNAME=$(ask "Telegram BOT_USERNAME" "$OLD_BOT_USERNAME")
NEW_OWNER_ID=$(ask "Telegram OWNER_ID" "$OLD_OWNER_ID")

echo ""
info "Konfigurasi AI Services (Google Gemini):"
NEW_GEMINI_KEYS=$(ask "Gemini API Keys (pisahkan dengan koma jika multi-key)" "$OLD_GEMINI_KEYS")
NEW_MODEL_NAME=$(ask "Gemini Model" "$OLD_MODEL_NAME")

echo ""
info "Pengaturan Opsional:"
NEW_GOFILE_TOKEN=$(ask "Gofile Token (kosongkan jika tanpa akun)" "$OLD_GOFILE_TOKEN")
NEW_BASE_PATH=$(ask "Base Path Direktori Bot" "$OLD_BASE_PATH")

cat <<EOF > .env
# ==========================================
# Telegram API Credentials
# ==========================================
API_ID=${NEW_API_ID}
API_HASH=${NEW_API_HASH}

# ==========================================
# Telegram Bot Configuration
# ==========================================
BOT_TOKEN=${NEW_BOT_TOKEN}
BOT_USERNAME=${NEW_BOT_USERNAME}
BOT_ID=${NEW_BOT_ID}

# ==========================================
# Owner Configuration
# ==========================================
OWNER_ID=${NEW_OWNER_ID}

# ==========================================
# AI Service Keys
# ==========================================
GEMINI_KEYS=${NEW_GEMINI_KEYS}
MODEL_NAME=${NEW_MODEL_NAME}

<<<<<<< HEAD
=======

>>>>>>> 9a802dc09dff03bc9dadbc10c170665afa67fc1d
# ==========================================
# Storage & Mirror (Opsional)
# ==========================================
GOFILE_TOKEN=${NEW_GOFILE_TOKEN}
BASE_PATH=${NEW_BASE_PATH}
EOF

chmod 600 .env
ok "File .env berhasil disimpan dengan izin akses aman (600)."

# --- STEP 5: Service / Execution Manager ---
header "Manajemen Eksekusi Bot"

create_tmux_scripts() {
    info "Membuat script runner tmux (start.sh, stop.sh, restart.sh, status.sh, attach.sh)..."

    cat <<EOF > start.sh
#!/usr/bin/env bash
set -e

DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
cd "\$DIR"

SESSION="bot"

if tmux has-session -t "\$SESSION" 2>/dev/null; then
    echo -e "\033[1;33m[!] Sesi tmux '\$SESSION' sudah berjalan.\033[0m"
    echo -e "Gunakan \033[1;36m./attach.sh\033[0m untuk melihat konsol atau \033[1;31m./stop.sh\033[0m untuk mematikan."
    exit 0
fi

# Cari interpreter Python yang valid
if [ -f "\$DIR/venv/bin/python3" ]; then
    PY="\$DIR/venv/bin/python3"
elif [ -n "${PYTHON_EXEC}" ] && [ -x "${PYTHON_EXEC}" ]; then
    PY="${PYTHON_EXEC}"
elif command -v python3 >/dev/null 2>&1; then
    PY="\$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PY="\$(command -v python)"
else
    echo -e "\033[1;31m[-] Interpreter Python tidak ditemukan!\033[0m"
    exit 1
fi

mkdir -p "\$DIR/dbbot/logs" "\$DIR/scrapers/logs"

# Jalankan bot di dalam sesi tmux dengan penahan error agar traceback tidak hilang
tmux new-session -d -s "\$SESSION" -c "\$DIR" "bash -c '\$PY main.py; EXIT_CODE=\\\$?; if [ \\\$EXIT_CODE -ne 0 ]; then echo -e \"\n\033[1;31m[!] Bot berhenti dengan error (exit code: \\\$EXIT_CODE).\033[0m\"; echo \"Tekan Enter untuk menutup sesi...\"; read -r; fi'"

sleep 1.5

if tmux has-session -t "\$SESSION" 2>/dev/null; then
    # Cek apakah proses main.py benar-benar aktif berjalan
    if pgrep -f "main.py" >/dev/null 2>&1; then
        echo -e "\033[1;32m[+] Bot berhasil dijalankan di background (tmux session: '\$SESSION')\033[0m"
        echo -e "Perintah kontrol:"
        echo -e "  \033[1;36m./attach.sh\033[0m  - Buka konsol interaktif bot"
        echo -e "  \033[1;36m./status.sh\033[0m  - Cek status & log terbaru"
        echo -e "  \033[1;36m./restart.sh\033[0m - Restart bot"
        echo -e "  \033[1;36m./stop.sh\033[0m    - Hentikan bot"
    else
        echo -e "\033[1;31m[-] Bot mengalami error saat startup!\033[0m"
        echo -e "\033[1;33m--- Output Terminal / Error Traceback: ---\033[0m"
        tmux capture-pane -p -t "\$SESSION" 2>/dev/null | grep -v '^[[:space:]]*$' | tail -n 25 || true
        echo -e "\033[1;33m------------------------------------------\033[0m"
        echo -e "Jalankan \033[1;36m./attach.sh\033[0m untuk melihat konsol, atau coba manual: \033[1;36m\$PY main.py\033[0m"
        exit 1
    fi
else
    echo -e "\033[1;31m[-] Gagal membuat sesi tmux '\$SESSION'. Pastikan paket tmux terpasang.\033[0m"
    exit 1
fi
EOF

    cat <<'EOF' > stop.sh
#!/usr/bin/env bash
SESSION="bot"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux kill-session -t "$SESSION"
    echo -e "\033[1;32m[+] Sesi bot '$SESSION' telah dihentikan.\033[0m"
else
    echo -e "\033[1;33m[!] Sesi '$SESSION' tidak sedang berjalan.\033[0m"
fi

# Hentikan sisa proses python main.py jika ada
pkill -f "$DIR/main.py" 2>/dev/null || true
EOF

    cat <<'EOF' > restart.sh
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$DIR/stop.sh"
sleep 1
"$DIR/start.sh"
EOF

    cat <<'EOF' > attach.sh
#!/usr/bin/env bash
SESSION="bot"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux attach-session -t "$SESSION"
else
    echo -e "\033[1;33m[!] Sesi '$SESSION' belum berjalan. Jalankan dengan ./start.sh\033[0m"
fi
EOF

    cat <<'EOF' > status.sh
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION="bot"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    PID="$(pgrep -f "main.py" | head -n 1 || true)"
    if [ -n "$PID" ]; then
        echo -e "\033[1;32m● Status: AKTIF (tmux session '$SESSION')\033[0m"
        echo "  PID: $PID"
        if command -v ps >/dev/null 2>&1; then
            ps -p "$PID" -o %cpu,%mem,etime,cmd --headers 2>/dev/null || true
        fi
    else
        echo -e "\033[1;33m● Status: Sesi tmux aktif, tetapi proses bot terhenti.\033[0m"
        echo "  Gunakan ./attach.sh untuk memeriksa error di konsol."
    fi
else
    echo -e "\033[1;31m○ Status: NONAKTIF\033[0m"
fi

echo ""
LOG_FILE="$DIR/dbbot/logs/bot.log"
if [ -f "$LOG_FILE" ]; then
    echo -e "\033[1;36m--- Log Terbaru (15 baris terakhir) ---\033[0m"
    tail -n 15 "$LOG_FILE"
fi
EOF

    chmod +x start.sh stop.sh restart.sh attach.sh status.sh
    ok "Script tmux runner siap digunakan."
}

create_systemd_service() {
    local service_file="/etc/systemd/system/telegram-bot.service"
    local run_user
    run_user="$(id -un)"

    info "Menyiapkan file systemd service di $service_file ..."

    cat <<EOF | run_as_root tee "$service_file" >/dev/null
[Unit]
Description=Telegram Multifunction Bot
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${run_user}
WorkingDirectory=${ROOT_DIR}
ExecStart=${PYTHON_EXEC} ${ROOT_DIR}/main.py
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStopSec=10
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

    run_as_root systemctl daemon-reload
    ok "Systemd service 'telegram-bot.service' berhasil dibuat."

    START_NOW=$(ask "Aktifkan dan jalankan service sekarang? (y/n)" "y")
    if [[ "$START_NOW" =~ ^[Yy]$ ]]; then
        run_as_root systemctl enable --now telegram-bot
        ok "Service telegram-bot telah berjalan via systemd."
        echo "Perintah kontrol:"
        echo "  sudo systemctl status telegram-bot"
        echo "  sudo journalctl -u telegram-bot -f"
        echo "  sudo systemctl restart telegram-bot"
        echo "  sudo systemctl stop telegram-bot"
    fi
}

create_openrc_service() {
    local init_file="/etc/init.d/telegram-bot"
    local run_user
    run_user="$(id -un)"

    info "Menyiapkan OpenRC service di $init_file ..."

    cat <<EOF | run_as_root tee "$init_file" >/dev/null
#!/sbin/openrc-run

name="telegram-bot"
description="Telegram Multifunction Bot"
directory="${ROOT_DIR}"
command="${PYTHON_EXEC}"
command_args="${ROOT_DIR}/main.py"
command_user="${run_user}"
command_background="yes"
pidfile="/run/\${RC_SVCNAME}.pid"

depend() {
    need net
    after firewall
}
EOF

    run_as_root chmod +x "$init_file"
    ok "OpenRC service 'telegram-bot' berhasil dibuat."

    START_NOW=$(ask "Tambahkan ke runlevel default dan jalankan sekarang? (y/n)" "y")
    if [[ "$START_NOW" =~ ^[Yy]$ ]]; then
        run_as_root rc-update add telegram-bot default
        run_as_root rc-service telegram-bot start
        ok "Service telegram-bot telah berjalan via OpenRC."
    fi
}

# Pemilihan mode eksekusi
if [ "$TARGET_OS" = "termux" ]; then
    info "Platform Termux terdeteksi: Otomatis menggunakan runner tmux."
    create_tmux_scripts
    EXEC_MODE="tmux"
else
    echo "Pilih metode menjalankan bot:"
    echo "  1) tmux session runner (Disarankan - konsol interaktif & mudah di-attach)"
    echo "  2) systemd service (Otomatis start saat boot server)"
    echo "  3) OpenRC service (Khusus Alpine / non-systemd init)"
    echo "  4) Manual (Saya akan jalankan sendiri)"

    # Rekomendasikan systemd jika ada systemd, selain itu tmux
    DEFAULT_MGR=1
    if [ -d /run/systemd/system ] || command -v systemctl >/dev/null 2>&1; then
        DEFAULT_MGR=1
    elif [ -f /sbin/openrc-run ] || command -v rc-service >/dev/null 2>&1; then
        DEFAULT_MGR=3
    fi

    MGR_CHOICE=$(ask "Pilihan Anda" "$DEFAULT_MGR")

    case "$MGR_CHOICE" in
        1)
            create_tmux_scripts
            EXEC_MODE="tmux"
            ;;
        2)
            create_systemd_service
            EXEC_MODE="systemd"
            ;;
        3)
            create_openrc_service
            EXEC_MODE="openrc"
            ;;
        *)
            create_tmux_scripts
            EXEC_MODE="manual"
            ;;
    esac
fi

# Tanyakan start bot jika menggunakan mode tmux
if [ "$EXEC_MODE" = "tmux" ]; then
    START_TMUX=$(ask "Jalankan bot sekarang via ./start.sh? (y/n)" "y")
    if [[ "$START_TMUX" =~ ^[Yy]$ ]]; then
        ./start.sh
    fi
fi

header "Instalasi Selesai!"
ok "Semua komponen telah berhasil dipasang dan dikonfigurasi."
echo -e "Direktori Bot : ${BOLD}${ROOT_DIR}${NC}"
echo -e "File Config   : ${BOLD}${ROOT_DIR}/.env${NC}"
echo -e "Python Binary : ${BOLD}${PYTHON_EXEC}${NC}"
echo ""
echo "Untuk mengelola bot di masa mendatang:"
if [ "$EXEC_MODE" = "systemd" ]; then
    echo "  • Status : sudo systemctl status telegram-bot"
    echo "  • Log    : sudo journalctl -u telegram-bot -f"
    echo "  • Restart: sudo systemctl restart telegram-bot"
    echo "  • Stop   : sudo systemctl stop telegram-bot"
else
    echo "  • Start  : ./start.sh"
    echo "  • Attach : ./attach.sh"
    echo "  • Status : ./status.sh"
    echo "  • Restart: ./restart.sh"
    echo "  • Stop   : ./stop.sh"
fi
echo ""
