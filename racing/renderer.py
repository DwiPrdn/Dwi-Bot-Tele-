import os
import time
import logging
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("RacingRenderer")

# Path to fonts
F1_WIDE = "racing/fonts/Formula1-Wide.woff2"
F1_BOLD = "racing/fonts/Formula1-Bold.woff2"
F1_REG = "racing/fonts/Formula1-Regular.woff2"
F1_BLACK = "racing/fonts/Formula1-Black.woff2"

MGP_DISPLAY = "racing/fonts/MotoGP-Display-Bold.ttf"
MGP_DISPLAY_WOFF2 = "racing/fonts/MotoGP-Display-Bold.woff2"

SYS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SYS_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SYS_COND_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"

# Team Colors
F1_TEAM_COLORS: Dict[str, str] = {
    "mercedes": "#00D2BE",
    "ferrari": "#EF1A2D",
    "red bull": "#3671C6",
    "mclaren": "#FF8000",
    "aston martin": "#229971",
    "alpine": "#0093CC",
    "williams": "#00A0DE",
    "racing bulls": "#6692FF",
    "rb": "#6692FF",
    "haas": "#B6BABD",
    "sauber": "#52E252",
    "audi": "#E21B23",
    "cadillac": "#C59B27",
}

MOTOGP_TEAM_COLORS: Dict[str, str] = {
    "ducati": "#CC0000",
    "lenovo": "#CC0000",
    "gresini": "#87CEEB",
    "vr46": "#FFE600",
    "pramac": "#5A2D81",
    "aprilia": "#D40000",
    "ktm": "#FA5800",
    "gasgas": "#E60000",
    "tech3": "#FA5800",
    "yamaha": "#0022AA",
    "honda": "#E60000",
    "lcr": "#008833",
    "trackhouse": "#0047AB",
}

NAT_TO_ISO: Dict[str, str] = {
    "british": "GBR", "italian": "ITA", "spanish": "ESP", "dutch": "NED",
    "monegasque": "MON", "french": "FRA", "german": "GER", "australian": "AUS",
    "japanese": "JPN", "mexican": "MEX", "canadian": "CAN", "new zealander": "NZL",
    "danish": "DEN", "finnish": "FIN", "thai": "THA", "chinese": "CHN",
    "american": "USA", "argentinian": "ARG", "brazilian": "BRA", "austrian": "AUT",
    "swiss": "SUI", "indonesian": "INA", "malaysian": "MAS", "portuguese": "POR",
    "south african": "RSA", "qatari": "QAT", "san marino": "SMR",
    "es": "ESP", "it": "ITA", "fr": "FRA", "de": "GER", "gb": "GBR",
    "au": "AUS", "jp": "JPN", "us": "USA", "nl": "NED", "mc": "MON",
    "th": "THA", "sm": "SMR", "za": "RSA", "pt": "POR", "my": "MAS",
    "id": "INA", "qa": "QAT", "at": "AUT", "br": "BRA", "ar": "ARG"
}

MOTOGP_RIDERS_INFO: Dict[str, Dict[str, Any]] = {
    "acosta": {"number": 37, "bg": "#FA5800", "fg": "#000000", "mfg": "ktm", "color": "#FA5800", "nat": "ESP"},
    "bagnaia": {"number": 63, "bg": "#C62828", "fg": "#FFFFFF", "mfg": "ducati", "color": "#CC0000", "nat": "ITA"},
    "marc_marquez": {"number": 93, "bg": "#D32F2F", "fg": "#FFFFFF", "mfg": "ducati", "color": "#CC0000", "nat": "ESP"},
    "marcmarquez": {"number": 93, "bg": "#D32F2F", "fg": "#FFFFFF", "mfg": "ducati", "color": "#CC0000", "nat": "ESP"},
    "alex_marquez": {"number": 73, "bg": "#D32F2F", "fg": "#FFFFFF", "mfg": "ducati", "color": "#87CEEB", "nat": "ESP"},
    "alexmarquez": {"number": 73, "bg": "#D32F2F", "fg": "#FFFFFF", "mfg": "ducati", "color": "#87CEEB", "nat": "ESP"},
    "marquez": {"number": 93, "bg": "#D32F2F", "fg": "#FFFFFF", "mfg": "ducati", "color": "#CC0000", "nat": "ESP"},
    "martin": {"number": 89, "bg": "#6A1B9A", "fg": "#FFFFFF", "mfg": "aprilia", "color": "#D40000", "nat": "ESP"},
    "bezzecchi": {"number": 72, "bg": "#5E35B1", "fg": "#FFFF00", "mfg": "aprilia", "color": "#D40000", "nat": "ITA"},
    "bastianini": {"number": 23, "bg": "#E91E63", "fg": "#FFFFFF", "mfg": "ktm", "color": "#FA5800", "nat": "ITA"},
    "binder": {"number": 33, "bg": "#FF6F00", "fg": "#000000", "mfg": "ktm", "color": "#FA5800", "nat": "RSA"},
    "raul_fernandez": {"number": 25, "bg": "#00BCD4", "fg": "#FFFFFF", "mfg": "trackhouse", "color": "#0047AB", "nat": "ESP"},
    "raulfernandez": {"number": 25, "bg": "#00BCD4", "fg": "#FFFFFF", "mfg": "trackhouse", "color": "#0047AB", "nat": "ESP"},
    "augusto_fernandez": {"number": 47, "bg": "#E60000", "fg": "#FFFFFF", "mfg": "tech3", "color": "#FA5800", "nat": "ESP"},
    "augustofernandez": {"number": 47, "bg": "#E60000", "fg": "#FFFFFF", "mfg": "tech3", "color": "#FA5800", "nat": "ESP"},
    "fernandez": {"number": 25, "bg": "#00BCD4", "fg": "#FFFFFF", "mfg": "trackhouse", "color": "#0047AB", "nat": "ESP"},
    "ogura": {"number": 79, "bg": "#00ACC1", "fg": "#FFFFFF", "mfg": "trackhouse", "color": "#0047AB", "nat": "JPN"},
    "di giannantonio": {"number": 49, "bg": "#D4E157", "fg": "#000000", "mfg": "vr46", "color": "#FFE600", "nat": "ITA"},
    "digiannantonio": {"number": 49, "bg": "#D4E157", "fg": "#000000", "mfg": "vr46", "color": "#FFE600", "nat": "ITA"},
    "giannantonio": {"number": 49, "bg": "#D4E157", "fg": "#000000", "mfg": "vr46", "color": "#FFE600", "nat": "ITA"},
    "morbidelli": {"number": 21, "bg": "#76FF03", "fg": "#000000", "mfg": "vr46", "color": "#FFE600", "nat": "ITA"},
    "quartararo": {"number": 20, "bg": "#0D47A1", "fg": "#FFFFFF", "mfg": "yamaha", "color": "#0022AA", "nat": "FRA"},
    "rins": {"number": 42, "bg": "#1565C0", "fg": "#FFFFFF", "mfg": "yamaha", "color": "#0022AA", "nat": "ESP"},
    "miller": {"number": 43, "bg": "#1976D2", "fg": "#FFFFFF", "mfg": "yamaha", "color": "#5A2D81", "nat": "AUS"},
    "oliveira": {"number": 88, "bg": "#1976D2", "fg": "#FFFFFF", "mfg": "yamaha", "color": "#5A2D81", "nat": "POR"},
    "aldeguer": {"number": 54, "bg": "#0288D1", "fg": "#FFFFFF", "mfg": "ducati", "color": "#87CEEB", "nat": "ESP"},
    "marini": {"number": 10, "bg": "#E53935", "fg": "#FFFFFF", "mfg": "honda", "color": "#E60000", "nat": "ITA"},
    "mir": {"number": 36, "bg": "#FF8F00", "fg": "#FFFFFF", "mfg": "honda", "color": "#E60000", "nat": "ESP"},
    "zarco": {"number": 5, "bg": "#2E7D32", "fg": "#FFFFFF", "mfg": "honda", "color": "#008833", "nat": "FRA"},
    "chantra": {"number": 35, "bg": "#388E3C", "fg": "#FFFFFF", "mfg": "honda", "color": "#008833", "nat": "THA"},
    "viñales": {"number": 12, "bg": "#FF5722", "fg": "#FFFFFF", "mfg": "ktm", "color": "#FA5800", "nat": "ESP"},
    "vinales": {"number": 12, "bg": "#FF5722", "fg": "#FFFFFF", "mfg": "ktm", "color": "#FA5800", "nat": "ESP"},
    "espargaro": {"number": 41, "bg": "#D32F2F", "fg": "#FFFFFF", "mfg": "honda", "color": "#E60000", "nat": "ESP"},
}


def _get_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    if os.path.exists(SYS_BOLD):
        return ImageFont.truetype(SYS_BOLD, size)
    return ImageFont.load_default()


def _get_f1_team_color(team_name: str) -> str:
    name_lower = team_name.lower()
    for key, color in F1_TEAM_COLORS.items():
        if key in name_lower:
            return color
    return "#00D2BE"


def _get_motogp_team_color(team_name: str) -> str:
    name_lower = team_name.lower()
    for key, color in MOTOGP_TEAM_COLORS.items():
        if key in name_lower:
            return color
    return "#FF1801"


def draw_country_flag(draw: ImageDraw.ImageDraw, x: int, y: int, code: str, w: int = 28, h: int = 18):
    """Menggambar bendera negara miniatur dengan presisi geometris."""
    code = (code or "MGP").upper()
    draw.rectangle([(x, y), (x + w - 1, y + h - 1)], fill="#101010", outline="#252F3E", width=1)

    if code == "ITA":
        sw = w / 3.0
        draw.rectangle([(x, y), (x + sw, y + h - 1)], fill="#009246")
        draw.rectangle([(x + sw, y), (x + sw * 2, y + h - 1)], fill="#FFFFFF")
        draw.rectangle([(x + sw * 2, y), (x + w - 1, y + h - 1)], fill="#CE2B37")
    elif code == "FRA":
        sw = w / 3.0
        draw.rectangle([(x, y), (x + sw, y + h - 1)], fill="#002654")
        draw.rectangle([(x + sw, y), (x + sw * 2, y + h - 1)], fill="#FFFFFF")
        draw.rectangle([(x + sw * 2, y), (x + w - 1, y + h - 1)], fill="#ED2939")
    elif code == "NED":
        sh = h / 3.0
        draw.rectangle([(x, y), (x + w - 1, y + sh)], fill="#AE1C28")
        draw.rectangle([(x, y + sh), (x + w - 1, y + sh * 2)], fill="#FFFFFF")
        draw.rectangle([(x, y + sh * 2), (x + w - 1, y + h - 1)], fill="#21468B")
    elif code == "GER":
        sh = h / 3.0
        draw.rectangle([(x, y), (x + w - 1, y + sh)], fill="#000000")
        draw.rectangle([(x, y + sh), (x + w - 1, y + sh * 2)], fill="#DD0000")
        draw.rectangle([(x, y + sh * 2), (x + w - 1, y + h - 1)], fill="#FFCE00")
    elif code == "ESP":
        draw.rectangle([(x, y), (x + w - 1, y + h * 0.25)], fill="#AA151B")
        draw.rectangle([(x, y + h * 0.25), (x + w - 1, y + h * 0.75)], fill="#F1BF00")
        draw.rectangle([(x, y + h * 0.75), (x + w - 1, y + h - 1)], fill="#AA151B")
    elif code in ["MON", "INA"]:
        draw.rectangle([(x, y), (x + w - 1, y + h * 0.5)], fill="#CE1126")
        draw.rectangle([(x, y + h * 0.5), (x + w - 1, y + h - 1)], fill="#FFFFFF")
    elif code == "JPN":
        draw.rectangle([(x, y), (x + w - 1, y + h - 1)], fill="#FFFFFF")
        r = min(w, h) * 0.28
        draw.ellipse([(x + w/2 - r, y + h/2 - r), (x + w/2 + r, y + h/2 + r)], fill="#BC002D")
    elif code in ["GBR", "AUS", "NZL"]:
        draw.rectangle([(x, y), (x + w - 1, y + h - 1)], fill="#012169")
        draw.line([(x, y), (x + w - 1, y + h - 1)], fill="#FFFFFF", width=2)
        draw.line([(x, y + h - 1), (x + w - 1, y)], fill="#FFFFFF", width=2)
        draw.rectangle([(x + w * 0.40, y), (x + w * 0.60, y + h - 1)], fill="#FFFFFF")
        draw.rectangle([(x, y + h * 0.38), (x + w - 1, y + h * 0.62)], fill="#FFFFFF")
        draw.rectangle([(x + w * 0.44, y), (x + w * 0.56, y + h - 1)], fill="#C8102E")
        draw.rectangle([(x, y + h * 0.42), (x + w - 1, y + h * 0.58)], fill="#C8102E")
    elif code in ("RSA", "ZAF"):
        draw.rectangle([(x, y), (x + w - 1, y + h/2)], fill="#E03C31")
        draw.rectangle([(x, y + h/2), (x + w - 1, y + h - 1)], fill="#001489")
        draw.rectangle([(x, y + h*0.35), (x + w - 1, y + h*0.65)], fill="#FFFFFF")
        draw.rectangle([(x, y + h*0.40), (x + w - 1, y + h*0.60)], fill="#007749")
        draw.polygon([(x, y), (x + w*0.45, y + h/2), (x, y + h - 1)], fill="#FFB81C")
        draw.polygon([(x, y + 2), (x + w*0.40, y + h/2), (x, y + h - 3)], fill="#000000")
    elif code == "THA":
        s1 = h / 6.0
        draw.rectangle([(x, y), (x + w - 1, y + s1)], fill="#A51931")
        draw.rectangle([(x, y + s1), (x + w - 1, y + s1 * 2)], fill="#F4F5F8")
        draw.rectangle([(x, y + s1 * 2), (x + w - 1, y + s1 * 4)], fill="#2D2A4A")
        draw.rectangle([(x, y + s1 * 4), (x + w - 1, y + s1 * 5)], fill="#F4F5F8")
        draw.rectangle([(x, y + s1 * 5), (x + w - 1, y + h - 1)], fill="#A51931")
    elif code in ("SMR", "SM"):
        draw.rectangle([(x, y), (x + w - 1, y + h * 0.5)], fill="#FFFFFF")
        draw.rectangle([(x, y + h * 0.5), (x + w - 1, y + h - 1)], fill="#5EB6E4")
    elif code == "POR":
        draw.rectangle([(x, y), (x + w * 0.4, y + h - 1)], fill="#046A38")
        draw.rectangle([(x + w * 0.4, y), (x + w - 1, y + h - 1)], fill="#DA291C")
        draw.ellipse([(x + w * 0.3, y + h * 0.3), (x + w * 0.5, y + h * 0.7)], fill="#FFD700")
    elif code == "BRA":
        draw.rectangle([(x, y), (x + w - 1, y + h - 1)], fill="#009739")
        draw.polygon([(x + w * 0.5, y + 2), (x + w - 2, y + h * 0.5), (x + w * 0.5, y + h - 2), (x + 2, y + h * 0.5)], fill="#FEDD00")
        draw.ellipse([(x + w * 0.38, y + h * 0.32), (x + w * 0.62, y + h * 0.68)], fill="#002776")
    elif code == "ARG":
        sh = h / 3.0
        draw.rectangle([(x, y), (x + w - 1, y + sh)], fill="#74ACDF")
        draw.rectangle([(x, y + sh), (x + w - 1, y + sh * 2)], fill="#FFFFFF")
        draw.rectangle([(x, y + sh * 2), (x + w - 1, y + h - 1)], fill="#74ACDF")
        draw.ellipse([(x + w * 0.40, y + h * 0.38), (x + w * 0.60, y + h * 0.62)], fill="#F6B40E")
    else:
        # Fallback pill
        draw.rectangle([(x, y), (x + w - 1, y + h - 1)], fill="#1E2634")
        draw.text((x + 3, y + 3), code[:3], fill="#CBD5E1", font=_get_font(F1_BOLD, 9))


def draw_manufacturer_mark(draw: ImageDraw.ImageDraw, img: Image.Image, cx: int, cy: int, mfg: str):
    """Menggambar logo pabrikan MotoGP menggunakan aset PNG resmi siaran."""
    mfg = (mfg or "").lower().strip()
    if mfg in ["gresini", "lenovo"]:
        mfg = "ducati"
    elif mfg in ["pramac", "monster"]:
        mfg = "yamaha"
    elif mfg in ["tech3", "gasgas"]:
        mfg = "ktm"
    elif mfg in ["lcr", "repsol"]:
        mfg = "honda"

    logo_path = f"racing/assets/manufacturers/{mfg}.png"
    if os.path.exists(logo_path):
        try:
            m_img = Image.open(logo_path).convert("RGBA")
            max_w, max_h = 32, 22
            scale = min(max_w / m_img.width, max_h / m_img.height, 1.0)
            target_w = max(1, int(m_img.width * scale))
            target_h = max(1, int(m_img.height * scale))
            scaled = m_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            px = cx - target_w // 2
            py = cy - target_h // 2
            img.paste(scaled, (px, py), mask=scaled)
            return
        except Exception:
            pass

    font = _get_font(SYS_BOLD, 10)
    draw.text((cx - 14, cy - 6), mfg[:6].upper(), fill="#FFFFFF", font=font)


def _get_f1_driver_cutout(last_name: str) -> Optional[Image.Image]:
    """Mengambil foto cutout pembalap F1 yang sudah di-cache."""
    clean = last_name.lower().strip()
    # Direct match or alias
    candidates = [
        clean,
        clean.replace(" ", ""),
        clean.split()[-1] if clean.split() else clean
    ]
    for c in candidates:
        p = f"racing/assets/drivers/f1/{c}.webp"
        if os.path.exists(p):
            try:
                return Image.open(p).convert("RGBA")
            except Exception:
                pass
    return None


def _get_motogp_rider_cutout(last_name: str, first_name: str = "") -> Optional[Image.Image]:
    """Mengambil foto cutout pembalap MotoGP yang sudah di-cache dengan dukungan first_name."""
    clean_last = (last_name or "").lower().strip().replace("ñ", "n")
    clean_first = (first_name or "").lower().strip().replace("ñ", "n")

    candidates = []
    if clean_first:
        candidates.append(f"{clean_first}_{clean_last}")
        candidates.append(f"{clean_first}{clean_last}")
        candidates.append(f"{clean_first}_{clean_last.split()[-1]}")
    candidates.extend([
        clean_last,
        clean_last.replace(" ", ""),
        clean_last.split()[-1] if clean_last.split() else clean_last
    ])

    for c in candidates:
        p = f"racing/assets/drivers/motogp/{c}.png"
        if os.path.exists(p):
            try:
                return Image.open(p).convert("RGBA")
            except Exception:
                pass
    return None


# =====================================================================
# 1. FORMULA 1 BROADCAST RENDERER (Official Broadcast Timing Tower Replica)
# =====================================================================

def render_f1_broadcast(data: Dict[str, Any], output_path: str) -> str:
    """
    Renders an authentic Formula 1 broadcast TV leaderboard card.
    Dimensions: 1240 x 700 px.
    """
    W, H = 1240, 700
    img = Image.new("RGB", (W, H), "#0c0f16")
    draw = ImageDraw.Draw(img)

    # 1. Subtle diagonal speed lines
    for x in range(-700, W + 700, 36):
        draw.line([(x, 0), (x + 360, H)], fill="#121724", width=2)

    # Fonts
    font_wide_title = _get_font(F1_WIDE, 24)
    font_bold_top = _get_font(F1_BOLD, 15)
    font_th = _get_font(F1_BOLD, 11)
    font_row_bold = _get_font(F1_BOLD, 15)
    font_row_reg = _get_font(F1_REG, 14)
    font_spot_num = _get_font(F1_BLACK, 210)
    font_spot_name_first = _get_font(F1_REG, 18)
    font_spot_name_last = _get_font(F1_BLACK, 36)
    font_spot_team = _get_font(F1_BOLD, 18)

    accent_red = "#E10600"

    # 2. Header Section
    draw.rectangle([(40, 20), (46, 75)], fill=accent_red)

    title_text = data.get("title", "FORMULA 1 WORLD CHAMPIONSHIP 2026")
    subtitle_text = data.get("subtitle", "DRIVER STANDINGS")
    session_type = (data.get("session_type") or "").upper()
    category = (data.get("category") or "").upper()
    is_standings = "STANDINGS" in session_type or "STANDINGS" in subtitle_text or "STANDINGS" in category
    is_constructor = "CONSTRUCTOR" in category or "CONSTRUCTOR" in subtitle_text

    # Top small title
    draw.text((60, 20), title_text.upper(), fill="#CFD6E0", font=font_bold_top)

    # Top right badge (FASTEST / LEADER / STANDINGS)
    if "PRACTICE" in subtitle_text or "QUALIFYING" in subtitle_text:
        top_right_tag = "FASTEST"
    elif "RACE" in subtitle_text or "SPRINT" in subtitle_text:
        top_right_tag = "RACE WINNER"
    elif is_constructor:
        top_right_tag = "CONSTRUCTORS"
    else:
        top_right_tag = "CHAMPIONSHIP"

    tag_font = _get_font(F1_BOLD, 15)
    tag_w = draw.textlength(top_right_tag, font=tag_font)
    draw.text((1200 - tag_w, 20), top_right_tag, fill="#9CA8B6", font=tag_font)

    # Session title in F1-Wide (scaled so it never collides with right side)
    title_font_size = 22 if len(subtitle_text) > 28 else 25
    draw.text((60, 44), subtitle_text.upper(), fill="#FFFFFF", font=_get_font(F1_WIDE, title_font_size))

    # Red horizontal separator line
    draw.line([(40, 80), (1200, 80)], fill=accent_red, width=3)

    # 3. Table Column Header
    tbl_x1 = 40
    tbl_x2 = 800
    hdr_y1 = 92
    hdr_y2 = 120
    draw.rectangle([(tbl_x1, hdr_y1), (tbl_x2, hdr_y2)], fill="#FFFFFF")
    draw.rectangle([(tbl_x1, hdr_y1), (tbl_x2, hdr_y1 + 2)], fill=accent_red)

    name_col_header = "CONSTRUCTOR" if is_constructor else "DRIVER"
    metric_header = "POINTS" if is_standings else data.get("metric_header", "TIME")

    draw.text((50, hdr_y1 + 5), "POSITION", fill="#111111", font=font_th)
    draw.text((150, hdr_y1 + 5), name_col_header, fill="#111111", font=font_th)
    if not is_constructor:
        draw.text((380, hdr_y1 + 5), "TEAM", fill="#111111", font=font_th)
    draw.text((680, hdr_y1 + 5), metric_header, fill="#111111", font=font_th)

    # 4. Rows (Top 10)
    items = data.get("items", [])
    row_height = 47
    start_y = 126

    leader_item = items[0] if items else None
    leader_team_color = "#00D2BE"

    for idx, item in enumerate(items[:10]):
        ry1 = start_y + (idx * row_height)
        ry2 = ry1 + row_height - 5
        pos = item.get("position", idx + 1)
        first_name = item.get("first_name", "")
        last_name = item.get("last_name", "")
        team = item.get("team", "Unknown")
        team_color = _get_f1_team_color(team)
        if idx == 0:
            leader_team_color = team_color

        metric_val = item.get("time") or item.get("points", "0")
        if "POINTS" in metric_header and not str(metric_val).endswith("PTS"):
            metric_str = f"{metric_val} PTS"
        else:
            metric_str = str(metric_val)

        nat_raw = (item.get("nationality") or "").lower().strip()
        country_code = NAT_TO_ISO.get(nat_raw, (item.get("code") or "F1")[:3].upper())

        if idx == 0:
            # Row 1: Solid White Highlight row
            draw.rectangle([(tbl_x1, ry1), (tbl_x2, ry2)], fill="#FFFFFF")
            draw.text((55, ry1 + 12), str(pos), fill="#000000", font=font_row_bold)
            draw_country_flag(draw, 88, ry1 + 11, country_code)

            # Official F1 Team Color Vertical Stripe
            draw.rounded_rectangle([(122, ry1 + 8), (126, ry2 - 8)], radius=2, fill=team_color)

            if is_constructor:
                draw.text((136, ry1 + 12), last_name.upper(), fill="#000000", font=font_row_bold)
            else:
                fn_w = draw.textlength(first_name + " ", font=font_row_reg)
                draw.text((136, ry1 + 12), first_name + " ", fill="#333333", font=font_row_reg)
                draw.text((136 + fn_w, ry1 + 12), last_name.upper(), fill="#000000", font=font_row_bold)
                team_disp = (team[:22] + "..") if len(team) > 24 else team
                draw.text((380, ry1 + 12), team_disp.upper(), fill="#000000", font=font_row_bold)

            # Metric
            draw.text((680, ry1 + 12), metric_str, fill="#000000", font=font_row_bold)

            # Red broadcast tyre badge only in live session timing
            if not is_standings:
                draw.text((775, ry1 + 12), "S", fill=accent_red, font=font_row_bold)
        else:
            # Rows 2-10: Dark sleek rows
            row_bg = "#11151F" if idx % 2 == 1 else "#141A26"
            draw.rectangle([(tbl_x1, ry1), (tbl_x2, ry2)], fill=row_bg)

            pos_color = "#E5B832" if pos == 2 else ("#B0B8C2" if pos == 3 else "#FFFFFF")
            draw.text((55, ry1 + 12), str(pos), fill=pos_color, font=font_row_bold)
            draw_country_flag(draw, 88, ry1 + 11, country_code)

            # Official F1 Team Color Vertical Stripe
            draw.rounded_rectangle([(122, ry1 + 8), (126, ry2 - 8)], radius=2, fill=team_color)

            if is_constructor:
                draw.text((136, ry1 + 12), last_name.upper(), fill="#FFFFFF", font=font_row_bold)
            else:
                fn_w = draw.textlength(first_name + " ", font=font_row_reg)
                draw.text((136, ry1 + 12), first_name + " ", fill="#CBD5E1", font=font_row_reg)
                draw.text((136 + fn_w, ry1 + 12), last_name.upper(), fill="#FFFFFF", font=font_row_bold)
                team_disp = (team[:22] + "..") if len(team) > 24 else team
                draw.text((380, ry1 + 12), team_disp.upper(), fill="#B4C0CE", font=font_row_bold)

            # Metric
            draw.text((680, ry1 + 12), metric_str, fill="#FFFFFF", font=font_row_bold)

            # Red broadcast tyre badge only in live session timing
            if not is_standings:
                draw.text((775, ry1 + 12), "S", fill=accent_red, font=font_row_bold)

    # 5. Right Side Leader Spotlight
    if leader_item:
        leader_num = str(leader_item.get("number", "1"))
        leader_first = leader_item.get("first_name", "")
        leader_last = leader_item.get("last_name", "")
        leader_team = leader_item.get("team", "")

        # Watermark in Background
        draw.text((790, 110), leader_num, fill="#12242B", font=font_spot_num)
        draw.text((790, 110), leader_num, fill="#16383E", font=font_spot_num)

        if not is_constructor:
            # Composite Driver Photo Cutout
            cutout = _get_f1_driver_cutout(leader_last)
            if cutout:
                crop_h = int(cutout.height * 0.72)
                cropped = cutout.crop((0, 0, cutout.width, crop_h))
                aspect = cropped.width / cropped.height
                target_h = 550
                target_w = int(target_h * aspect)
                scaled_driver = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
                paste_x = 860
                paste_y = 125
                img.paste(scaled_driver, (paste_x, paste_y), mask=scaled_driver)

            draw.text((810, 545), leader_first, fill="#FFFFFF", font=font_spot_name_first)
            draw.text((810, 570), leader_last.upper(), fill=leader_team_color, font=font_spot_name_last)
            draw.text((810, 620), leader_team.upper(), fill="#FFFFFF", font=font_spot_team)
        else:
            # Constructor Spotlight
            draw.text((810, 260), "1ST PLACE", fill="#9CA8B6", font=font_spot_name_first)
            draw.text((810, 290), leader_last.upper(), fill=leader_team_color, font=font_spot_name_last)
            pts_c = str(leader_item.get("points", "0")) + " POINTS"
            draw.text((810, 350), pts_c, fill="#FFFFFF", font=font_spot_team)

    # 6. Bottom Brand Bar
    draw.rectangle([(40, 665), (48, 680)], fill=accent_red)
    draw.text((56, 665), "FORMULA 1 LIVE TIMING", fill=accent_red, font=_get_font(F1_BOLD, 12))
    draw.text((260, 665), "• Official Broadcast Leaderboard Powered by @Plendes_bot", fill="#6A778B", font=_get_font(F1_REG, 11))

    img.save(output_path, "PNG", quality=95)
    return output_path


# =====================================================================
# 2. MOTOGP BROADCAST RENDERER (100% Replica of Official Standings)
# =====================================================================

def render_motogp_broadcast(data: Dict[str, Any], output_path: str) -> str:
    """
    Renders an authentic MotoGP broadcast leaderboard card (100% replica of official standings).
    Dimensions: 720 x 960 px.
    Uses official MotoGP Display typography, driver cutout, leader banner, and rider pills.
    """
    W, H = 720, 960
    img = Image.new("RGB", (W, H), "#151618")
    draw = ImageDraw.Draw(img)

    # 1. Subtle diagonal broad bands (MotoGP speed texture)
    stripe_w = 90
    gap = 180
    for x in range(-H, W + H, gap):
        poly = [(x, 0), (x + stripe_w, 0), (x + stripe_w + int(H * 0.7), H), (x + int(H * 0.7), H)]
        draw.polygon(poly, fill="#191a1e")

    # 2. Top Header
    title_l1 = data.get("title_l1")
    title_l2 = data.get("title_l2")
    session_type = (data.get("session_type") or "STANDINGS").upper()

    if not title_l1 or not title_l2:
        if session_type in ["RAC", "RACE"]:
            title_l1 = "GRAND PRIX"
            title_l2 = "RACE RESULTS"
        elif session_type in ["SPR", "SPRINT"]:
            title_l1 = "SPRINT RACE"
            title_l2 = "RESULTS"
        elif session_type in ["Q", "QUALI", "QUALIFYING"]:
            title_l1 = "QUALIFYING"
            title_l2 = "RESULTS"
        elif session_type in ["FP", "PR", "PRACTICE"]:
            title_l1 = "FREE PRACTICE"
            title_l2 = "RESULTS"
        else:
            title_l1 = "RIDERS'"
            title_l2 = "CHAMPIONSHIP"

    event_str = data.get("event") or data.get("race_name") or "PT GRAND PRIX OF THAILAND"
    event_flag = data.get("event_country") or "THA"

    font_title = _get_font(MGP_DISPLAY, 46)
    font_sub = _get_font(SYS_BOLD, 15)

    # Title Line 1 (centered)
    w1 = draw.textlength(title_l1, font=font_title)
    draw.text(((W - w1) / 2, 70), title_l1, fill="#FFFFFF", font=font_title)

    # Title Line 2 (centered)
    w2 = draw.textlength(title_l2, font=font_title)
    draw.text(((W - w2) / 2, 122), title_l2, fill="#FFFFFF", font=font_title)

    # Event subtitle (centered)
    we = draw.textlength(event_str.upper(), font=font_sub)
    draw.text(((W - we) / 2, 185), event_str.upper(), fill="#FFFFFF", font=font_sub)

    # Event flag (centered)
    flag_w, flag_h = 36, 23
    draw_country_flag(draw, int((W - flag_w) / 2), 215, event_flag, flag_w, flag_h)

    # Table dimensions
    tbl_x1 = 60
    tbl_x2 = 660
    tbl_w = tbl_x2 - tbl_x1

    items = data.get("items", [])
    leader_item = items[0] if items else {}
    leader_first_raw = (leader_item.get("first_name") or "").lower().strip()
    leader_last_raw = (leader_item.get("last_name") or "acosta").lower().strip()
    leader_first_clean = leader_first_raw.replace(" ", "").replace("ñ", "n")
    leader_last_clean = leader_last_raw.replace(" ", "").replace("ñ", "n")
    leader_full_key = f"{leader_first_clean}_{leader_last_clean}" if leader_first_clean else leader_last_clean
    leader_meta = MOTOGP_RIDERS_INFO.get(
        leader_full_key,
        MOTOGP_RIDERS_INFO.get(leader_last_clean, MOTOGP_RIDERS_INFO.get(leader_last_raw.split()[-1] if leader_last_raw.split() else "", {}))
    )

    leader_color = leader_item.get("team_color") or leader_meta.get("color") or _get_motogp_team_color(leader_item.get("team", ""))

    # 3. Leader Banner (Card)
    card_y1 = 280
    card_y2 = 355
    # Rounded top corners
    draw.rounded_rectangle([(tbl_x1, card_y1), (tbl_x2, card_y2)], radius=8, corners=(True, True, False, False), fill=leader_color)

    # Outlined LEADER / WINNER / POLE Text in hollow style
    if "leader_status" in data:
        leader_text = data["leader_status"].upper()
    elif session_type in ["RAC", "SPR", "RACE", "SPRINT"]:
        leader_text = "WINNER"
    elif session_type in ["Q", "QUALIFYING"]:
        leader_text = "POLE"
    elif session_type in ["FP", "PR", "PRACTICE"]:
        leader_text = "FASTEST"
    else:
        leader_text = "LEADER"

    font_leader = _get_font(MGP_DISPLAY, 58)
    tx = tbl_x2 - draw.textlength(leader_text, font=font_leader) - 25
    ty = card_y1 + 12
    draw.text((tx, ty), leader_text, font=font_leader, fill=leader_color, stroke_width=2, stroke_fill="#000000")

    # Leader Cutout Photo (Head and shoulders extending ABOVE top of card)
    cutout = _get_motogp_rider_cutout(leader_last_clean, leader_first_clean)
    if cutout:
        try:
            cw, ch = cutout.size
            crop = cutout.crop((int(cw * 0.10), 0, int(cw * 0.90), int(ch * 0.48)))
            aspect = crop.width / crop.height
            target_h = 160
            target_w = int(target_h * aspect)
            scaled = crop.resize((target_w, target_h), Image.Resampling.LANCZOS)
            paste_x = tbl_x1 + 30
            paste_y = card_y2 - target_h
            img.paste(scaled, (paste_x, paste_y), mask=scaled)
        except Exception as e:
            logger.warning(f"Error rendering leader cutout: {e}")

    # 4. Leader Row (Row 1)
    row1_y1 = 355
    row1_y2 = 405
    # Gradient overlay on leader color
    row1_img = Image.new("RGBA", (tbl_w, row1_y2 - row1_y1), leader_color)
    grad = Image.new("RGBA", (tbl_w, row1_y2 - row1_y1))
    gdraw = ImageDraw.Draw(grad)
    for y in range(row1_y2 - row1_y1):
        alpha = int(120 * (y / (row1_y2 - row1_y1)))
        gdraw.line([(0, y), (tbl_w, y)], fill=(0, 0, 0, alpha))
    row1_img = Image.alpha_composite(row1_img, grad)
    img.paste(row1_img, (tbl_x1, row1_y1))

    # Elements in Row 1:
    font_pos = _get_font(MGP_DISPLAY, 24)
    draw.text((tbl_x1 + 20, row1_y1 + 12), "1", fill="#FFFFFF", font=font_pos)

    # Flag
    nat_raw = (leader_item.get("nationality") or leader_meta.get("nat") or "ESP").lower().strip()
    nat_code = NAT_TO_ISO.get(nat_raw, nat_raw[:3].upper())
    draw_country_flag(draw, tbl_x1 + 55, row1_y1 + 16, nat_code, 26, 17)

    # Number box pill
    num_bg = leader_item.get("number_bg") or leader_meta.get("bg", leader_color)
    num_fg = leader_item.get("number_fg") or leader_meta.get("fg", "#000000")
    num_val = leader_item.get("number") or leader_meta.get("number", 1)
    num_str = str(num_val)
    num_box_x = tbl_x1 + 95
    num_box_y = row1_y1 + 13
    draw.rounded_rectangle([(num_box_x, num_box_y), (num_box_x + 44, num_box_y + 24)], radius=4, fill=num_bg, outline="#000000", width=1)
    font_num = _get_font(SYS_BOLD, 15)
    nw = draw.textlength(num_str, font=font_num)
    draw.text((num_box_x + (44 - nw) / 2, num_box_y + 3), num_str, fill=num_fg, font=font_num)

    # Rider Name
    first_name = leader_item.get("first_name", "")
    last_name = leader_item.get("last_name", "")
    font_fname = _get_font(SYS_REG, 13)
    font_lname = _get_font(SYS_BOLD, 16)
    draw.text((tbl_x1 + 155, row1_y1 + 8), first_name, fill="#FFFFFF", font=font_fname)
    draw.text((tbl_x1 + 155, row1_y1 + 25), last_name.upper(), fill="#FFFFFF", font=font_lname)

    # Manufacturer Icon (Official PNG logo)
    mfg_code = leader_item.get("manufacturer") or leader_meta.get("mfg", "")
    if not mfg_code:
        t_low = (leader_item.get("team") or "").lower()
        for k in ["ktm", "ducati", "aprilia", "trackhouse", "vr46", "yamaha", "honda"]:
            if k in t_low:
                mfg_code = k
                break
    draw_manufacturer_mark(draw, img, tbl_x1 + 420, row1_y1 + 25, mfg_code or "ktm")

    # Far Right Solid White Box for Points / Metric
    pts_box_w = 75
    pts_box_x = tbl_x2 - pts_box_w
    draw.rounded_rectangle([(pts_box_x, row1_y1), (tbl_x2, row1_y2)], radius=6, corners=(False, True, False, False), fill="#FFFFFF")
    font_pts_bold = _get_font(MGP_DISPLAY, 30)
    pts_str = str(leader_item.get("points") or leader_item.get("time", "0"))
    pw = draw.textlength(pts_str, font=font_pts_bold)
    draw.text((pts_box_x + (pts_box_w - pw) / 2, row1_y1 + 10), pts_str, fill="#000000", font=font_pts_bold)

    # 5. Rows 2 to 10
    row_h = 45
    start_y = row1_y2
    font_row_pos = _get_font(MGP_DISPLAY, 20)
    font_gap = _get_font(SYS_REG, 14)
    font_pts = _get_font(MGP_DISPLAY, 24)

    is_standings_mgp = "STANDINGS" in session_type or "CHAMPIONSHIP" in title_l2

    for idx, item in enumerate(items[1:10], start=2):
        ry1 = start_y + (idx - 2) * row_h
        ry2 = ry1 + row_h
        is_last = (idx == 10)

        # Row Background
        if is_last:
            draw.rounded_rectangle([(tbl_x1, ry1), (tbl_x2, ry2)], radius=8, corners=(False, False, True, True), fill="#0E0F12")
        else:
            draw.rectangle([(tbl_x1, ry1), (tbl_x2, ry2)], fill="#0E0F12")

        # Separator line
        draw.line([(tbl_x1, ry1), (tbl_x2, ry1)], fill="#1E2026", width=1)

        # Metadata
        fname_raw = (item.get("first_name") or "").lower().strip()
        lname_raw = (item.get("last_name") or "").lower().strip()
        fname_clean = fname_raw.replace(" ", "").replace("ñ", "n")
        lname_clean = lname_raw.replace(" ", "").replace("ñ", "n")
        full_key = f"{fname_clean}_{lname_clean}" if fname_clean else lname_clean
        meta = MOTOGP_RIDERS_INFO.get(
            full_key,
            MOTOGP_RIDERS_INFO.get(lname_clean, MOTOGP_RIDERS_INFO.get(lname_raw.split()[-1] if lname_raw.split() else "", {}))
        )

        # POS
        pos_str = str(item.get("position", idx))
        pos_w = draw.textlength(pos_str, font=font_row_pos)
        draw.text((tbl_x1 + 20 + (16 - pos_w) / 2, ry1 + 11), pos_str, fill="#FFFFFF", font=font_row_pos)

        # Flag
        nat_r = (item.get("nationality") or meta.get("nat") or "ITA").lower().strip()
        nat_code = NAT_TO_ISO.get(nat_r, nat_r[:3].upper())
        draw_country_flag(draw, tbl_x1 + 55, ry1 + 13, nat_code, 26, 17)

        # Rider Number Box
        num_bg = item.get("number_bg") or meta.get("bg", "#333333")
        num_fg = item.get("number_fg") or meta.get("fg", "#FFFFFF")
        num_val = item.get("number") or meta.get("number", idx)
        num_str = str(num_val)
        n_box_x = tbl_x1 + 95
        n_box_y = ry1 + 10
        draw.rounded_rectangle([(n_box_x, n_box_y), (n_box_x + 44, n_box_y + 24)], radius=4, fill=num_bg)
        nw = draw.textlength(num_str, font=font_num)
        draw.text((n_box_x + (44 - nw) / 2, n_box_y + 3), num_str, fill=num_fg, font=font_num)

        # Rider Name
        fname = item.get("first_name", "")
        lname = item.get("last_name", "")
        draw.text((tbl_x1 + 155, ry1 + 6), fname, fill="#FFFFFF", font=font_fname)
        draw.text((tbl_x1 + 155, ry1 + 22), lname.upper(), fill="#FFFFFF", font=font_lname)

        # Manufacturer Icon (Official PNG logo)
        mfg = item.get("manufacturer") or meta.get("mfg", "")
        if not mfg:
            t_low = (item.get("team") or "").lower()
            for k in ["ktm", "ducati", "aprilia", "trackhouse", "vr46", "yamaha", "honda"]:
                if k in t_low:
                    mfg = k
                    break
        draw_manufacturer_mark(draw, img, tbl_x1 + 420, ry1 + 22, mfg)

        # Vertical column separators
        draw.line([(tbl_x1 + 460, ry1 + 8), (tbl_x1 + 460, ry2 - 8)], fill="#1E2026", width=1)
        draw.line([(tbl_x1 + 525, ry1 + 8), (tbl_x1 + 525, ry2 - 8)], fill="#1E2026", width=1)

        # Gap column
        gap_str = str(item.get("gap", ""))
        if not gap_str and is_standings_mgp and leader_item:
            try:
                p_lead = float(leader_item.get("points") or 0)
                p_curr = float(item.get("points") or 0)
                diff = int(p_lead - p_curr)
                if diff > 0:
                    gap_str = f"-{diff}"
                elif diff == 0:
                    gap_str = "0"
            except Exception:
                pass

        if gap_str:
            gw = draw.textlength(gap_str, font=font_gap)
            draw.text((tbl_x1 + 492 - gw / 2, ry1 + 13), gap_str, fill="#A0A8B4", font=font_gap)

        # Points / Time column
        p_str = str(item.get("points") or item.get("time", "0"))
        pw = draw.textlength(p_str, font=font_pts)
        draw.text((tbl_x2 - 35 - pw / 2, ry1 + 10), p_str, fill="#FFFFFF", font=font_pts)

    # 6. Bottom MotoGP Logo
    logo_path = "racing/assets/motogp_logo_clean.png"
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_h = 24
            logo_w = int(logo_img.width * (logo_h / logo_img.height))
            scaled_logo = logo_img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            img.paste(scaled_logo, (int((W - logo_w) / 2), 885), mask=scaled_logo)
        except Exception:
            pass

    img.save(output_path, "PNG", quality=95)
    return output_path


# =====================================================================
# MAIN DISPATCHER
# =====================================================================

def render_racing_card(data: Dict[str, Any], output_path: Optional[str] = None) -> str:
    """
    Renders racing leaderboard matching the specific series:
    - Formula 1 uses authentic F1 broadcast style & F1 fonts (exact replica of example.jpg).
    - MotoGP uses authentic MotoGP broadcast style & styling.
    """
    if not output_path:
        os.makedirs("downloads/racing", exist_ok=True)
        output_path = f"downloads/racing/racing_{int(time.time() * 1000)}.png"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    series = (data.get("series") or "F1").upper()
    if "MOTO" in series:
        return render_motogp_broadcast(data, output_path)
    else:
        return render_f1_broadcast(data, output_path)
