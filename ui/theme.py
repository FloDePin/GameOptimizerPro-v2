"""
GameOptimizerPro — design tokens for the CustomTkinter UI.

CustomTkinter draws the big surfaces (window, sidebar, cards, buttons,
switches, progress bars). Long lists use plain tk widgets in the same colours
(measured: 70 rows of CTk checkboxes took 4.5 s to build and ~0.4 s per window
resize — see ui/components.CheckBox).
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

# ── surfaces ──────────────────────────────────────────────────────────────────
APP_BG     = "#0b0e13"
SIDEBAR_BG = "#0e1218"
HEADER_BG  = "#0e1218"
CARD_BG    = "#151a22"
CARD_BG2   = "#1b212b"      # nested surfaces, table headers
INPUT_BG   = "#10141b"
BORDER     = "#242b36"
BORDER2    = "#313b4a"
HOVER      = "#1d2430"

# ── text ──────────────────────────────────────────────────────────────────────
TEXT  = "#e6edf3"
TEXT2 = "#b3bdcb"
DIM   = "#7d8896"
MUTED = "#4f5a69"
WHITE = "#ffffff"

# ── accents ───────────────────────────────────────────────────────────────────
RED    = "#e53935"
CYAN   = "#00b4d8"
ACC    = "#00d9ff"
AMBER  = "#f59e0b"
GREEN  = "#22c55e"
BLUE   = "#3b82f6"
PURPLE = "#7c3aed"
VIOLET = "#a78bfa"
ERR    = "#ef4444"
SLATE  = "#9ca3af"
OK, WRN = GREEN, AMBER

PAGE_COLORS = {
    "dashboard": RED, "optimizer": RED, "gpu": CYAN, "stress": AMBER,
    "compare": VIOLET, "bios": AMBER, "games": GREEN, "diagnose": ACC,
    "settings": SLATE,
}

# ── fonts (points; tk widgets) ───────────────────────────────────────────────
F_TITLE = ("Segoe UI Semibold", 17)
F_H     = ("Segoe UI Semibold", 11)
F_B     = ("Segoe UI", 10)
F_BB    = ("Segoe UI Semibold", 10)
F_S     = ("Segoe UI", 9)
F_SB    = ("Segoe UI Semibold", 9)
F_XS    = ("Segoe UI", 8)
F_MONO  = ("Consolas", 9)
F_MONOS = ("Consolas", 8)
F_NUM   = ("Consolas", 20, "bold")
F_NUMS  = ("Consolas", 14, "bold")

# ── icons (Segoe Fluent Icons on Windows 11, MDL2 Assets on Windows 10) ──────
_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
if os.path.exists(os.path.join(_FONTS, "SegoeIcons.ttf")):
    ICON_FONT, ICON_FILE = "Segoe Fluent Icons", os.path.join(_FONTS, "SegoeIcons.ttf")
elif os.path.exists(os.path.join(_FONTS, "segmdl2.ttf")):
    ICON_FONT, ICON_FILE = "Segoe MDL2 Assets", os.path.join(_FONTS, "segmdl2.ttf")
else:
    ICON_FONT, ICON_FILE = "", ""

ICONS = {
    "dashboard": "\uEC4A", "optimizer": "\uE9F5", "gpu": "\uE964", "stress": "\uECAD",
    "compare": "\uE9D2", "bios": "\uE950", "games": "\uE7FC", "diagnose": "\uE9D9",
    "settings": "\uE713", "startup": "\uE7E8", "services": "\uE90F", "folder": "\uE838",
    "refresh": "\uE72C", "check": "\uE73E", "play": "\uE768", "stop": "\uE71A",
    "save": "\uE74E", "warning": "\uE7BA", "info": "\uE946", "globe": "\uE774",
    "history": "\uE81C", "bolt": "\uE945", "thermo": "\uE9CA", "search": "\uE721",
    "add": "\uE710", "delete": "\uE74D", "star": "\uE734", "monitor": "\uE7F4",
    "network": "\uE839", "audio": "\uE767", "windows": "\uE7F4", "link": "\uE71B",
    "download": "\uE896", "upload": "\uE898", "flame": "\uECAD", "chip": "\uEEA1",
    "copy": "\uE8C8", "back": "\uE72B", "undo": "\uE7A7", "shield": "\uEA18",
}


def tr(de: str, en: str) -> str:
    """Pick the text for the current UI language."""
    try:
        from core.i18n import current_lang
        return de if current_lang() == "de" else en
    except Exception:
        return en


EMOJI_FILE = os.path.join(_FONTS, "seguiemj.ttf")


def emoji_image(widget: tk.Misc, text: str, size: int = 22):
    """A colour emoji as PhotoImage (cached per Tk root), None if not possible."""
    root = widget._root()
    cache = root.__dict__.setdefault("_gop_emoji", {})
    key = (text, size)
    if key not in cache:
        img = None
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            sc = 4
            font = ImageFont.truetype(EMOJI_FILE, size * sc)
            px = size * sc
            im = Image.new("RGBA", (px + 2 * sc, px + 2 * sc), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            box = d.textbbox((0, 0), text, font=font, embedded_color=True)
            x = (im.width - (box[2] - box[0])) / 2 - box[0]
            y = (im.height - (box[3] - box[1])) / 2 - box[1]
            d.text((x, y), text, font=font, embedded_color=True)
            img = ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS), master=root)
        except Exception:
            img = None
        cache[key] = img
    return cache[key]


def named_font(widget: tk.Misc, family: str, size: int, weight: str = "normal"):
    """A font object created once per Tk root and shared. Tk loads a font given as
    a tuple again for every widget — 17 ms per label for 'Segoe UI Emoji'."""
    from tkinter import font as tkfont
    root = widget._root()
    cache = root.__dict__.setdefault("_gop_fonts", {})
    key = (family, size, weight)
    if key not in cache:
        cache[key] = tkfont.Font(root=root, family=family, size=size, weight=weight)
    return cache[key]


def ctk_font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    """CustomTkinter font (pixel sizes, scaled with the window)."""
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


# ── colour helpers ────────────────────────────────────────────────────────────
def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """Colour between a (t=0) and b (t=1)."""
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return "#{:02x}{:02x}{:02x}".format(round(ra + (rb - ra) * t), round(ga + (gb - ga) * t),
                                        round(ba + (bb - ba) * t))


def tint(color: str, bg: str = CARD_BG, amount: float = 0.18) -> str:
    """A subtle background tinted with an accent (active nav item, badges)."""
    return mix(bg, color, amount)


def hover_of(color: str) -> str:
    return mix(color, "#000000", 0.18)


def is_light(color: str) -> bool:
    r, g, b = _rgb(color)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


def on_color(color: str) -> str:
    """Readable text colour on a filled accent."""
    return "#071018" if is_light(color) else WHITE


_ICON_CACHE: dict = {}


def icon_image(name: str, color: str, size: int = 18):
    """An icon glyph as CTkImage (for CTk buttons); None when no icon font."""
    glyph = ICONS.get(name, "")
    if not (glyph and ICON_FILE):
        return None
    key = (name, color, size)
    if key not in _ICON_CACHE:
        try:
            from PIL import Image, ImageDraw, ImageFont
            sc = 4
            px = size * sc
            font = ImageFont.truetype(ICON_FILE, int(px * 0.86))
            im = Image.new("RGBA", (px, px), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            box = d.textbbox((0, 0), glyph, font=font)
            x = (px - (box[2] - box[0])) / 2 - box[0]
            y = (px - (box[3] - box[1])) / 2 - box[1]
            d.text((x, y), glyph, font=font, fill=color)
            im = im.resize((size * 2, size * 2), Image.LANCZOS)    # 2x: crisp at 200 % too
            _ICON_CACHE[key] = ctk.CTkImage(light_image=im, dark_image=im, size=(size, size))
        except Exception:
            _ICON_CACHE[key] = None
    return _ICON_CACHE[key]


def icon_label(parent, name: str, color: str = DIM, size: int = 12, bg: str = CARD_BG, **kw):
    """A tk.Label showing an icon glyph (falls back to nothing without the font)."""
    glyph = ICONS.get(name, "") if ICON_FONT else ""
    return tk.Label(parent, text=glyph, font=(ICON_FONT or "Segoe UI", size), fg=color, bg=bg, **kw)


# ── CustomTkinter defaults ───────────────────────────────────────────────────
def _patch_ctk_theme():
    ctk.set_appearance_mode("dark")
    T = ctk.ThemeManager.theme

    def c(v):
        return [v, v]

    T["CTk"]["fg_color"] = c(APP_BG)
    T["CTkToplevel"]["fg_color"] = c(APP_BG)
    T["CTkFrame"].update(fg_color=c(CARD_BG), top_fg_color=c(CARD_BG2), border_color=c(BORDER))
    T["CTkButton"].update(fg_color=c(CARD_BG2), hover_color=c(HOVER), border_color=c(BORDER2),
                          text_color=c(TEXT), text_color_disabled=c(MUTED), corner_radius=9)
    T["CTkLabel"].update(text_color=c(TEXT))
    T["CTkEntry"].update(fg_color=c(INPUT_BG), border_color=c(BORDER), text_color=c(TEXT),
                         placeholder_text_color=c(MUTED), corner_radius=8)
    T["CTkCheckBox"].update(fg_color=c(ACC), border_color=c(MUTED), hover_color=c(hover_of(ACC)),
                            checkmark_color=c("#071018"), text_color=c(TEXT),
                            text_color_disabled=c(MUTED), corner_radius=5)
    T["CTkSwitch"].update(fg_color=c(BORDER2), progress_color=c(ACC), button_color=c(TEXT),
                          button_hover_color=c(WHITE), text_color=c(TEXT), text_color_disabled=c(MUTED))
    T["CTkRadioButton"].update(fg_color=c(ACC), border_color=c(MUTED), hover_color=c(hover_of(ACC)),
                               text_color=c(TEXT), text_color_disabled=c(MUTED))
    T["CTkProgressBar"].update(fg_color=c(mix(CARD_BG, "#ffffff", 0.07)), progress_color=c(ACC),
                               border_color=c(BORDER))
    T["CTkSlider"].update(fg_color=c(BORDER2), progress_color=c(ACC), button_color=c(ACC),
                          button_hover_color=c(WHITE))
    T["CTkOptionMenu"].update(fg_color=c(CARD_BG2), button_color=c(BORDER2),
                              button_hover_color=c(HOVER), text_color=c(TEXT),
                              text_color_disabled=c(MUTED), corner_radius=8)
    T["CTkComboBox"].update(fg_color=c(INPUT_BG), border_color=c(BORDER), button_color=c(BORDER2),
                            button_hover_color=c(HOVER), text_color=c(TEXT),
                            text_color_disabled=c(MUTED), corner_radius=8)
    T["CTkScrollbar"].update(fg_color="transparent", button_color=c(BORDER2),
                             button_hover_color=c(MUTED))
    T["CTkSegmentedButton"].update(fg_color=c(CARD_BG2), selected_color=c(ACC),
                                   selected_hover_color=c(hover_of(ACC)),
                                   unselected_color=c(CARD_BG2), unselected_hover_color=c(HOVER),
                                   text_color=c(TEXT), text_color_disabled=c(MUTED), corner_radius=9)
    T["CTkTextbox"].update(fg_color=c(INPUT_BG), border_color=c(BORDER), text_color=c(TEXT2),
                           scrollbar_button_color=c(BORDER2), scrollbar_button_hover_color=c(MUTED))
    T["CTkScrollableFrame"].update(label_fg_color=c(CARD_BG2))
    T["DropdownMenu"].update(fg_color=c(CARD_BG2), hover_color=c(HOVER), text_color=c(TEXT))
    T["CTkFont"]["Windows"] = {"family": "Segoe UI", "size": 13, "weight": "normal"}


_patch_ctk_theme()


# ── per-root setup (ttk styles) ──────────────────────────────────────────────
def ensure_styles(widget: tk.Misc):
    """setup() once per Tk root — pages may be built inside a plain tk.Tk (tests)."""
    root = widget._root()
    if not getattr(root, "_gop_styled", False):
        setup(root)


def setup(root: tk.Misc):
    root._gop_styled = True
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("GOP.Treeview", background=CARD_BG, foreground=TEXT, fieldbackground=CARD_BG,
                    rowheight=28, font=F_S, borderwidth=0, relief="flat")
    style.configure("GOP.Treeview.Heading", background=CARD_BG2, foreground=TEXT2,
                    font=F_SB, relief="flat", borderwidth=0, padding=(8, 6))
    style.map("GOP.Treeview.Heading", background=[("active", HOVER)])
    style.map("GOP.Treeview", background=[("selected", mix(CARD_BG, PURPLE, 0.55))],
              foreground=[("selected", WHITE)])
    style.layout("GOP.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("TCombobox", fieldbackground=INPUT_BG, background=CARD_BG2, foreground=TEXT,
                    arrowcolor=TEXT2, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.map("TCombobox", fieldbackground=[("readonly", INPUT_BG)],
              foreground=[("readonly", TEXT)], background=[("readonly", CARD_BG2)])
    try:
        root.option_add("*TCombobox*Listbox.background", CARD_BG2)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", PURPLE)
        root.option_add("*TCombobox*Listbox.selectForeground", WHITE)
    except tk.TclError:
        pass


def app_icon_path() -> str:
    """The window icon as .ico (drawn once into logs/, which is not in git)."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "logs", "gop_icon.ico")
    if os.path.exists(path):
        return path
    try:
        from PIL import Image, ImageDraw
        s = 256
        im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((8, 8, s - 8, s - 8), radius=58, fill=(14, 18, 24, 255),
                            outline=(229, 57, 53, 255), width=10)
        bolt = [(146, 34), (70, 142), (122, 142), (104, 222), (186, 108), (132, 108), (150, 34)]
        d.polygon(bolt, fill=(0, 217, 255, 255))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        im.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return path
    except Exception:
        return ""
