# Dwi-Bot-Tele-

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Telethon](https://img.shields.io/badge/Telethon-MTProto-blueviolet?logo=telegram&logoColor=white)](https://github.com/LonamiWebs/Telethon)
[![AI](https://img.shields.io/badge/AI-Google%20Gemini-4285F4?logo=google&logoColor=white)](https://aistudio.google.com/)
[![OS](https://img.shields.io/badge/OS-Linux%20%7C%20macOS%20%7C%20Termux-success?logo=linux&logoColor=white)](https://github.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A multifunction Telegram bot built with **Telethon (MTProto API)**. It handles media downloading across 13+ platforms, multi-turn AI chat and vision analysis, live Formula 1 and MotoGP standings, group management with AI verification challenges, music downloading, Gofile mirroring, prayer times alerts, and includes an interactive terminal CLI to control the bot directly from your server console.

---

## Table of Contents

- [What is this bot for?](#what-is-this-bot-for)
- [Features](#features)
- [Module Architecture](#module-architecture)
- [Command Reference](#command-reference)
- [Terminal CLI Usage](#terminal-cli-usage)
- [Installation & Setup](#installation--setup)
  - [Option 1: Quick Setup (`install.sh`)](#option-1-quick-setup-installsh)
  - [Option 2: Manual Setup](#option-2-manual-setup)
- [Environment Configuration (`.env`)](#environment-configuration-env)
- [Running the Bot](#running-the-bot)
- [License](#license)

---

## What is this bot for?

This bot serves as a flexible all-in-one assistant for both personal chats and Telegram groups:
- **Media & Music Downloads**: Automatically downloads videos, audio, and photos from links (TikTok, IG, YouTube, X, Spotify, etc.).
- **AI Assistant**: Answers questions, writes code, and analyzes images using Google Gemini with multi-key rotation.
- **Group Moderation & Security**: Protects groups from spam bots via an AI-generated verification challenge in private chat, plus auto-replies (filters), notes with media album support, and moderation tools (ban, mute, kick).
- **Motorsports Hub**: Tracks Formula 1 and MotoGP schedules, standings, and race results rendered as clean visual telemetry cards.
- **Server Administration**: Lets the bot host manage chats, read messages, and reply or upload files directly from the server terminal without opening Telegram.

---

## Features

### 1. Artificial Intelligence & Vision
- **Google Gemini (Flash-Lite)**: Multi-turn chat with automatic API key rotation to prevent rate limits.
- **Multimodal Vision (`/aigv`)**: Reply to any photo, sticker, or image for visual explanation.
- **AI Image Generation (`/draw`)**: Creates images from text prompts.
- **Custom AI Persona (`/setstyle`)**: Switch conversational tone (casual, sarcastic, formal, etc.).
- **AI Health Check (`/statusai`)**: Check API key status, latency, and active model.

### 2. Universal Media Downloader
Send any link to the chat or use `/snatch` on replied media:
- **TikTok**: No-watermark video, original audio, and photo slide sets.
- **Instagram**: Reels, carousels/albums, posts, and Stories.
- **YouTube**: Videos, Shorts, and MP3 audio extraction.
- **Twitter / X**: Highest quality video and HD images.
- **Threads & Facebook**: Public videos, reels, and photo posts.
- **Pinterest**: Videos, GIFs, and images.
- **Other Platforms**: Reddit (muxed audio), Bluesky, CapCut templates, Pixiv artwork.
- **Smart Fallback**: Integrated `aria2` multi-connection downloader with download resume.

### 3. Music & Audio Suite
- **Search Music (`/msc <title>`)**: Search across YouTube, Spotify, or SoundCloud with an interactive platform switcher.
- **Direct Download (`/msc <link>`)**: Downloads audio with full ID3 tags (artist, title, cover artwork).
- **Shazam Recognition**: Reply to any audio or video with `/msc` to identify the song.

### 4. Racing Hub (Formula 1 & MotoGP)
- **Interactive Dashboard (`/racing`)**: Quick access to F1 and MotoGP menus.
- **Formula 1 (`/f1`)**: Driver & constructor standings, upcoming schedules, countdowns, and race results.
- **MotoGP (`/motogp`)**: Rider standings, sprint race, qualifying, and race results.
- **Broadcast Cards**: Standings and timing data are rendered into visual graphics using Pillow.

### 5. Group Management & AI Verification Gate
- **AI Verification Gate (`/verify on|off`)**:
  - Automatically mutes newly joined members.
  - Sends a deep-link to the bot's private chat.
  - Gemini AI generates dynamic logic/human questions in English, Indonesian, or the user's preferred language.
  - Answers are evaluated by AI for natural human understanding (not strict string matching).
  - Unmutes upon success; auto-kicks after 3 failed attempts or timeout (default 5 minutes).
- **Filters (`/filter`, `/stop`, `/filters`)**: Keyword auto-replies.
- **Notes (`/save`, `/get`, `#notename`, `/notes`, `/clear`)**:
  - Saves text or media triggered by hashtag or command.
  - Full support for media albums (`grouped_id`) saved locally to disk.
- **Custom Welcome (`/welcome`, `/setwelcome`)**: Formatted welcome messages with tags like `{first}`, `{username}`, `{chatname}`.
- **Moderation Tools**: `/ban`, `/unban`, `/mute`, `/unmute`, `/kick`, and `/info`.

### 6. Cloud Mirroring (Gofile)
- **Mirroring (`/mirror <link>` or reply to file)**:
  - Uploads files or resolves direct URLs (Google Drive, Mediafire, Mega) straight to Gofile.io.
  - Shows real-time ASCII progress bar with speed and ETA.
  - Optional `GOFILE_TOKEN` to store uploads in your personal account.

### 7. Prayer Time Alerts
- **Daily Prayer Times (`/praytime [city]`)**: Accurate prayer times and countdown to the next prayer.
- **Auto Adzan Scheduler**: Background loop that sends visual prayer cards and adzan audio to configured groups.

### 8. Sticker Snatcher
- **Command `/snatch` or `/kang`**: Reply to a sticker, photo, or document to add it to your bot sticker pack, or snatch entire sticker sets with `snatch_all`.

### 9. Interactive Terminal CLI
A built-in interactive console powered by `prompt-toolkit`:
- System telemetry header (CPU, RAM, OS, Python, latency).
- Real-time colorful tree logs for incoming messages.
- Read messages, chat, reply, and upload local files directly from the server.
- Silent mode toggle (`/mute` and `/unmute`) to suppress terminal logs.
- In-place bot restart (`/restart`).

### 10. Owner Chat Proxy
- **`/chatowner` & `/stopchat`**: Lets users securely send messages to the bot owner with interactive Accept / Reject / End buttons.

---

## Module Architecture

```text
├── main.py                     # Main bot entry point, event handlers, and terminal CLI
├── install.sh                  # Universal system installer script
├── requirements.txt            # Python dependencies
├── .env.example                # Configuration template
├── .env                        # Private credentials (chmod 600)
│
├── admins/                     # Group administration
│   ├── moderation.py           # Filters, notes (with album support), welcome, ban/mute/kick
│   └── verify.py               # AI join gate captcha challenge via DM
│
├── scrapers/                   # Media downloaders
│   ├── ig.py                   # Instagram scraper
│   ├── tiktok.py               # TikTok scraper
│   ├── youtube.py              # YouTube scraper
│   ├── twitter.py              # Twitter / X scraper
│   ├── threads.py              # Threads scraper
│   ├── facebook.py             # Facebook scraper
│   ├── pinterest.py            # Pinterest scraper
│   ├── spotify.py              # Spotify resolver & downloader
│   ├── soundcloud.py           # SoundCloud scraper
│   ├── reddit.py               # Reddit scraper
│   ├── bluesky.py              # Bluesky scraper
│   ├── capcut.py               # CapCut scraper
│   ├── pixiv.py                # Pixiv scraper
│   ├── aria2_dl.py             # Smart multi-connection aria2 downloader
│   └── logs/                   # Debug log directory
│
├── racing/                     # Motorsport hub
│   ├── racing_service.py       # F1 & MotoGP schedule and standings API
│   ├── renderer.py             # Graphic card renderer (Pillow)
│   ├── assets/                 # Team badges, flags, and circuit layouts
│   └── fonts/                  # Card typography fonts
│
├── mirror/                     # Cloud upload & link resolvers
│   ├── gofile_upload.py        # Gofile uploader with progress tracking
│   ├── gofile_api.py           # Gofile API client
│   ├── link_resolvers.py       # Direct download resolvers
│   └── mega_dl.py              # Mega downloader
│
├── stickers/                   # Sticker tools
│   └── snatcher.py             # Sticker pack scraper and converter
│
├── uploader/                   # Telethon upload optimizations
│   └── fast_telethon.py        # Parallel multi-part uploader for large files
│
└── dbbot/                      # Local data storage
    ├── db_chat/                # Group settings
    ├── db_user/                # User data
    ├── db_prayers/             # Prayer assets & schedules
    ├── saved_media/            # Group notes media storage
    ├── session/                # Telethon session file
    └── logs/                   # Runtime log files
```

---

## Command Reference

### General
| Command | Description |
| :--- | :--- |
| `/start` | Start the bot and view the main menu |
| `/help` | Detailed command manual |
| `/ping` | Latency and connection check |
| `/stats` | System stats (CPU, RAM, database info) |
| `/info` | Display user Telegram info |
| `/changelog` | Bot update history |

### AI & Vision
| Command | Description | Example |
| :--- | :--- | :--- |
| `/aigm <prompt>` | Ask Google Gemini (multi-turn chat) | `/aigm Explain how async event loops work` |
| `/aigv [prompt]` | Multimodal vision (reply to photo or sticker) | *Reply photo* `/aigv what is this?` |
| `/draw <prompt>` | Generate an image with AI | `/draw a futuristic cyberpunk city in rain` |
| `/setstyle <style>` | Change AI conversation tone | `/setstyle casual and witty` |
| `/statusai` | Check AI model status and API key pool | `/statusai` |

### Media & Music
| Command / Action | Description | Example |
| :--- | :--- | :--- |
| *Paste Link* | Auto-downloads media from 13+ social platforms | Send a TikTok / IG / YT link |
| `/msc <title>` | Search music on YouTube, Spotify, or SoundCloud | `/msc Bohemian Rhapsody` |
| `/msc <link>` | Download high-quality audio from a track link | `/msc https://open.spotify.com/track/...` |
| `/msc` (*reply*) | Identify song from audio/video via Shazam | *Reply video* `/msc` |
| `/snatch` or `/kang` | Extract media or add replied sticker to pack | *Reply sticker* `/snatch` |
| `/vidset` | Video download format settings | `/vidset` |
| `/asupan` | Send a random video clip from the pool | `/asupan` |
| `/asupopt` | Category settings for video pool | `/asupopt` |

### Formula 1 & MotoGP
| Command | Description | Options |
| :--- | :--- | :--- |
| `/racing` | Open main racing dashboard | Interactive buttons |
| `/f1` | F1 standings, schedule, and race results | `drivers`, `constructors`, `race`, `sprint`, `quali`, `practice` |
| `/motogp` | MotoGP standings, schedule, and results | `riders`, `race`, `sprint`, `quali`, `practice` |

### Cloud Mirroring
| Command | Description | Example |
| :--- | :--- | :--- |
| `/mirror <url>` | Download from URL and upload to Gofile | `/mirror https://example.com/file.zip` |
| `/mirror` (*reply*) | Upload replied Telegram file/media to Gofile | *Reply document* `/mirror` |

### Prayer Times
| Command | Description | Example |
| :--- | :--- | :--- |
| `/praytime [city]` | Show 5 daily prayer times & next prayer countdown | `/praytime Jakarta` |

### Group Moderation (Admins)
| Command | Description | Example |
| :--- | :--- | :--- |
| `/verify on\|off` | Toggle AI captcha gate for new members | `/verify on` |
| `/filter <trigger> <text>` | Add keyword auto-reply | `/filter rules Check pinned message!` |
| `/stop <trigger>` | Remove keyword auto-reply | `/stop rules` |
| `/stopall` | Remove all filters in group | `/stopall` |
| `/filters` | List all active filters | `/filters` |
| `/save <name> <text>` | Save note (supports text, media, and albums) | `/save info Server IP: 1.2.3.4` |
| `/get <name>` or `#name` | Retrieve a note | `/get info` or `#info` |
| `/notes` | List all notes in the group | `/notes` |
| `/clear <name>` | Delete a note | `/clear info` |
| `/notereply on\|off` | Toggle reply tag on note responses | `/notereply on` |
| `/welcome on\|off` | Enable/disable welcome message | `/welcome on` |
| `/setwelcome <text>` | Set welcome message format | `/setwelcome Welcome {mention}!` |
| `/resetwelcome` | Reset welcome message to default | `/resetwelcome` |
| `/ban`, `/unban` | Ban or unban group member | *Reply user* `/ban` |
| `/mute`, `/unmute` | Mute or unmute group member | *Reply user* `/mute` |
| `/kick` | Kick member from group | *Reply user* `/kick` |

### Owner Contact
| Command | Description |
| :--- | :--- |
| `/chatowner` | Request a chat session with the bot owner (private chat only) |
| `/stopchat` | End active chat session with the owner |

---

## Terminal CLI Usage

When running the bot directly in your server terminal or via tmux, you can manage conversations interactively:

```text
 █▀▀█ 
 █▄▄▀ 
 █  █   OS: Linux 6.6 (x86_64) · CPU: 12% · RAM: 2.4 GB / 8.0 GB
 ▀  ▀   Python: 3.12 · Telethon: 1.36.0 · Bot: @Plendes_bot · Ping: 42ms
────────────────────────────────────────────────────────────────────────────────
> 
```

### CLI Commands
| Command | Action |
| :--- | :--- |
| `/list` | Show all stored chats and groups |
| `/openg <index/name/id>` | Open an active chat session |
| `/read [count]` | Read the last N messages in the active chat (default: 10) |
| `/r #[id] <message>` | Reply to a specific message ID in the active chat |
| `/close` | Close the currently active chat session |
| `/mute` or `/notif off` | Silence real-time message logs in the terminal |
| `/unmute` or `/notif on` | Restore real-time message logs in the terminal |
| `/restart` | Restart the bot in-place |
| `/exit` or `/stop` | Gracefully shut down the bot |

### Sending Messages & Local Files
- **Text Message**: Open a chat with `/openg`, type your message, and hit **Enter**.
- **Send Local File**: Enter the absolute or relative file path, with an optional caption:
  ```bash
  > /home/user/document.pdf Here is the report
  > "/path with spaces/photo.jpg" Photo caption
  ```
  Files larger than 20 MB are automatically uploaded via `fast_telethon`.

---

## Installation & Setup

### Prerequisites
- **OS**: Linux (Debian, Ubuntu, Arch, Fedora, Alpine, openSUSE, Void), Android Termux, or macOS.
- **Python**: Version `3.10` or higher.
- **System Packages**: `ffmpeg`, `aria2`, `tmux`, `git`, `curl`, `build-essential`.

---

### Option 1: Quick Setup (`install.sh`)

An interactive universal setup script is included:

```bash
git clone https://github.com/DwiPrdn/Dwi-Bot-Tele-.git
cd Dwi-Bot-Tele-
chmod +x install.sh
./install.sh
```

The script will:
1. Detect your operating system and package manager.
2. Install required system packages (`ffmpeg`, `aria2`, `tmux`, `python3-venv`, etc.).
3. Create a Python virtual environment (`venv`) and install `requirements.txt`.
4. Walk you through configuring your `.env` file.
5. Create tmux launcher scripts or register a `systemd` service.

---

### Option 2: Manual Setup

#### 1. Install System Dependencies

- **Debian / Ubuntu**:
  ```bash
  sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv ffmpeg aria2 tmux git
  ```
- **Arch Linux**:
  ```bash
  sudo pacman -Sy python python-pip ffmpeg aria2 tmux git base-devel
  ```
- **Fedora**:
  ```bash
  sudo dnf install -y python3 python3-pip ffmpeg aria2 tmux git
  ```
- **Termux**:
  ```bash
  pkg update && pkg install -y python ffmpeg aria2 tmux git clang make
  ```

#### 2. Create Virtual Environment & Install Modules

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### 3. Create Runtime Folders

```bash
mkdir -p dbbot/logs dbbot/session dbbot/db_chat dbbot/db_user dbbot/saved_media downloads
```

#### 4. Configure Environment

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

---

## Environment Configuration (`.env`)

Edit `.env` with your credentials:

```ini
# ==========================================
# Telegram API Credentials
# Get these from: https://my.telegram.org/apps
# ==========================================
API_ID=12345678
API_HASH=abcdef0123456789abcdef0123456789

# ==========================================
# Telegram Bot Configuration
# Get this from @BotFather
# ==========================================
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
BOT_USERNAME=Plendes_bot
BOT_ID=123456789

# ==========================================
# Owner Configuration (Numeric User ID)
# Get your ID from @userinfobot
# ==========================================
OWNER_ID=987654321

# ==========================================
# AI Service Keys
# ==========================================
# Google Gemini API Keys (comma-separated for key rotation)
# Get keys from: https://aistudio.google.com/app/apikey
GEMINI_KEYS=AIzaSyA...,AIzaSyB...
MODEL_NAME=gemini-3.1-flash-lite

# ==========================================
# Storage & Mirror (Optional)
# ==========================================
GOFILE_TOKEN=
BASE_PATH=
```

---

## Running the Bot

### Using Tmux (Recommended)
Tmux lets the bot run continuously in the background while still allowing you to attach to the interactive CLI:

```bash
./start.sh     # Starts bot in a background tmux session named 'bot'
./attach.sh    # Attaches to the interactive console
./status.sh    # Checks status, PID, memory, and recent logs
./restart.sh   # Restarts the session
./stop.sh      # Stops the bot
```

> **Detach tip**: While inside tmux (`./attach.sh`), press `Ctrl + B` then `D` to detach without stopping the bot.

### Using Systemd (Production Server)
If you set up the systemd service:

```bash
sudo systemctl status telegram-bot   # Check service status
sudo journalctl -u telegram-bot -f   # Follow live logs
sudo systemctl restart telegram-bot  # Restart bot
sudo systemctl stop telegram-bot     # Stop bot
```

---

## License

This project is licensed under the [MIT License](LICENSE).