"""
GameOptimizerPro — reusable building blocks of the CustomTkinter UI.

Rule of thumb: CustomTkinter for the few big things (cards, buttons, inputs,
switches, progress bars, scroll areas), plain tk for the many small ones
(labels, list rows, the tweak checkboxes) — in the same colours. Measured on
the dev PC: 70 list rows with CTk checkboxes took 4.5 s to build and ~0.4 s per
window resize.
"""

from __future__ import annotations

import queue
import tkinter as tk
from datetime import datetime
from tkinter import ttk

import customtkinter as ctk

from ui.theme import (ACC, APP_BG, BORDER, BORDER2, CARD_BG, CARD_BG2, DIM, ERR, F_B, F_H,
                      F_MONO, F_MONOS, F_NUM, F_S, F_TITLE, F_XS, GREEN, HOVER, INPUT_BG,
                      MUTED, AMBER, RED, TEXT, TEXT2, WHITE, ctk_font, hover_of, mix, tint, tr)


# ── text ──────────────────────────────────────────────────────────────────────

class WrapLabel(tk.Label):
    """A label whose text wraps to the width it gets (pack/grid it with fill).
    The re-wrap waits until resizing pauses, so dragging the window stays smooth."""

    def __init__(self, master, pad: int = 6, **kw):
        kw.setdefault("justify", "left")
        kw.setdefault("anchor", "w")
        super().__init__(master, **kw)
        self._wrap_pad = pad
        self._wrap_width = 0
        self._wrap_job = None
        self.bind("<Configure>", self._on_configure, add="+")

    def _on_configure(self, e):
        width = max(60, e.width - self._wrap_pad)
        if abs(width - self._wrap_width) < 8:
            return
        if self._wrap_job is not None:
            try:
                self.after_cancel(self._wrap_job)
            except tk.TclError:
                pass
        self._wrap_job = self.after(70, self._apply_wrap, width)

    def _apply_wrap(self, width):
        self._wrap_job = None
        self._wrap_width = width
        try:
            self.configure(wraplength=width)
        except tk.TclError:
            pass


def section_title(parent, text: str, color: str = ACC, bg: str = APP_BG) -> tk.Frame:
    f = tk.Frame(parent, bg=bg)
    tk.Label(f, text=text.upper(), font=("Segoe UI Semibold", 8), fg=color, bg=bg).pack(side="left")
    tk.Frame(f, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(10, 0), pady=(2, 0))
    return f


def badge(parent, text: str, color: str, bg: str = CARD_BG) -> tk.Label:
    """Small tinted pill label (keeps its colour when a row is highlighted)."""
    lbl = tk.Label(parent, text=text, font=F_XS, fg=color, bg=tint(color, bg, 0.16), padx=7, pady=1)
    lbl._keep_bg = True
    return lbl


# ── buttons / inputs ─────────────────────────────────────────────────────────

def _is_light(c: str) -> bool:
    c = c.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


class _FillButton(ctk.CTkButton):
    """CTkButton whose coloured fill fades while it is disabled — CustomTkinter
    only greys the text, so a disabled red "Abbrechen" still looked active."""

    def __init__(self, *args, fill: str = "", **kw):
        self._gop_fill = fill
        if kw.get("state") == "disabled":
            kw["fg_color"] = self._dim(fill)
        super().__init__(*args, **kw)

    @staticmethod
    def _dim(fill: str) -> str:
        return mix(fill, CARD_BG2, 0.72)

    def configure(self, require_redraw=False, **kwargs):
        if "state" in kwargs and "fg_color" not in kwargs:
            on = kwargs["state"] != "disabled"
            kwargs["fg_color"] = self._gop_fill if on else self._dim(self._gop_fill)
        return super().configure(require_redraw, **kwargs)


def button(parent, text: str, command=None, kind: str = "secondary", color: str | None = None,
           width: int = 0, height: int = 34, **kw) -> ctk.CTkButton:
    """kind: primary (accent fill), secondary (neutral), ghost (transparent),
    danger (red). Coloured buttons fade while disabled."""
    if kind == "primary":
        fg = color or ACC
        txt = "#071018" if _is_light(fg) else WHITE
        hover = hover_of(fg)
    elif kind == "danger":
        fg, txt, hover = ERR, WHITE, hover_of(ERR)
    elif kind == "ghost":
        fg, txt, hover = "transparent", TEXT2, HOVER
    else:
        fg, txt, hover = CARD_BG2, TEXT, HOVER
    bold = kind in ("primary", "danger")
    common = dict(text=text, command=command, hover_color=hover, text_color=txt,
                  corner_radius=9, height=height, width=width, border_width=0,
                  font=ctk_font(13, "bold" if bold else "normal"))
    if bold:
        return _FillButton(parent, fill=fg, fg_color=fg, text_color_disabled=mix(fg, TEXT2, 0.35),
                           **common, **kw)
    return ctk.CTkButton(parent, fg_color=fg, text_color_disabled=MUTED, **common, **kw)


def _check_images(root: tk.Misc, size: int, accent: str, bg: str, border: str):
    """Rounded checkbox images, drawn once per colour set and kept on the root
    (images belong to their Tk interpreter)."""
    cache = root.__dict__.setdefault("_gop_check_images", {})
    key = (size, accent, bg, border)
    if key not in cache:
        from PIL import Image, ImageDraw, ImageTk
        sc = 4
        s = size * sc
        imgs = []
        for checked in (False, True):
            im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            r = int(size * 0.28) * sc
            if checked:
                d.rounded_rectangle((0, 0, s - 1, s - 1), radius=r, fill=accent)
                ink = "#071018" if _is_light(accent) else "#ffffff"
                d.line([(s * 0.26, s * 0.53), (s * 0.44, s * 0.71), (s * 0.76, s * 0.32)],
                       fill=ink, width=int(2.3 * sc), joint="curve")
            else:
                d.rounded_rectangle((sc, sc, s - 1 - sc, s - 1 - sc), radius=r, outline=border,
                                    width=2 * sc)
            imgs.append(ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS), master=root))
        cache[key] = tuple(imgs)
    return cache[key]


class CheckBox(tk.Checkbutton):
    """Light rounded checkbox (plain tk + shared images) for long lists."""

    def __init__(self, parent, variable: tk.Variable, accent: str = RED, bg: str = CARD_BG,
                 size: int = 18, text: str = "", fg: str = TEXT, font=F_B, command=None, **kw):
        off, on = _check_images(parent._root(), size, accent, bg, MUTED)
        super().__init__(parent, variable=variable, image=off, selectimage=on, indicatoron=False,
                         compound="left", text=(" " + text) if text else "", fg=fg, font=font,
                         bd=0, bg=bg, activebackground=bg, activeforeground=fg, selectcolor=bg,
                         highlightthickness=0, relief="flat", offrelief="flat", overrelief="flat",
                         cursor="hand2", command=command, anchor="w", **kw)
        self._gop_imgs = (off, on)


class NumberField(tk.Frame):
    """[−][ value ][+] bound to an IntVar, clamped to lo..hi."""

    def __init__(self, parent, variable: tk.IntVar, lo: int, hi: int, step: int = 1,
                 width: int = 70, bg: str = CARD_BG, **kw):
        super().__init__(parent, bg=bg, **kw)
        self.var, self.lo, self.hi, self.step = variable, lo, hi, step
        small = dict(width=28, height=30, corner_radius=8, fg_color=CARD_BG2, hover_color=HOVER,
                     text_color=TEXT, font=ctk_font(14, "bold"))
        ctk.CTkButton(self, text="−", command=lambda: self.bump(-self.step), **small).pack(side="left")
        self.entry = ctk.CTkEntry(self, textvariable=variable, width=width, height=30, justify="center",
                                  fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
                                  corner_radius=8, font=ctk_font(13))
        self.entry.pack(side="left", padx=4)
        ctk.CTkButton(self, text="+", command=lambda: self.bump(self.step), **small).pack(side="left")
        self.entry.bind("<FocusOut>", lambda e: self.clamp(), add="+")
        self.entry.bind("<Return>", lambda e: self.clamp(), add="+")

    def value(self) -> int:
        try:
            return int(self.var.get())
        except (tk.TclError, ValueError):
            return self.lo

    def clamp(self):
        # only a value outside the range (or half-typed) is written: a write is a change for
        # whoever traces the variable (the GPU tab remembers changed fields as the user's)
        v = max(self.lo, min(self.hi, self.value()))
        try:
            if int(self.var.get()) == v:
                return
        except (tk.TclError, ValueError):
            pass
        self.var.set(v)

    def bump(self, delta: int):
        self.var.set(max(self.lo, min(self.hi, self.value() + delta)))


class HoverTip:
    """An explanation window for any widget: pointing at it (or a click) opens a
    little window with the text, leaving it closes it again. `text` may be a
    function — the window then says what holds right now (status dots)."""

    WRAP_PX = 330

    def __init__(self, widget, text, click: bool = True):
        self.widget = widget
        self.text = text
        self._tip: tk.Toplevel | None = None
        self._job = None
        widget.bind("<Enter>", lambda e: self._schedule(), add="+")
        widget.bind("<Leave>", lambda e: self.hide(), add="+")
        if click:
            widget.bind("<Button-1>", lambda e: self.show(), add="+")

    def _text(self) -> str:
        try:
            return str(self.text() if callable(self.text) else self.text)
        except Exception:
            return ""

    def _schedule(self):
        self._cancel()
        try:
            self._job = self.widget.after(300, self.show)
        except tk.TclError:
            self._job = None

    def _cancel(self):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def show(self):
        self._cancel()
        text = self._text()
        if self._tip is not None or not text:
            return
        w = self.widget
        try:
            tip = tk.Toplevel(w)
            tip.wm_overrideredirect(True)
            tip.attributes("-topmost", True)
            box = tk.Frame(tip, bg=BORDER2, padx=1, pady=1)
            box.pack()
            tk.Label(box, text=text, font=F_S, fg=TEXT, bg=CARD_BG2, justify="left", anchor="w",
                     wraplength=self.WRAP_PX, padx=10, pady=8).pack()
            tip.update_idletasks()
            x = w.winfo_rootx() + w.winfo_width() + 6
            y = w.winfo_rooty() - 4
            sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
            if x + tip.winfo_reqwidth() > sw - 8:            # no room on the right: left of it
                x = max(8, w.winfo_rootx() - tip.winfo_reqwidth() - 6)
            if y + tip.winfo_reqheight() > sh - 8:           # bottom of the screen: above it
                y = max(8, w.winfo_rooty() - tip.winfo_reqheight() - 6)
            tip.geometry(f"+{x}+{y}")
            self._tip = tip
        except tk.TclError:
            self._tip = None

    def hide(self):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


class HelpTip(tk.Label):
    """A small "?" next to a setting with its explanation (HoverTip)."""

    def __init__(self, parent, text: str, bg: str = CARD_BG):
        super().__init__(parent, text="?", font=("Segoe UI Semibold", 8), fg=TEXT,
                         bg=mix(bg, "#ffffff", 0.14), padx=4, pady=0, cursor="question_arrow")
        self._hover = HoverTip(self, text)

    @property
    def text(self) -> str:
        return self._hover.text

    @text.setter
    def text(self, value: str):
        self._hover.text = value

    @property
    def _tip(self):
        return self._hover._tip

    def show(self):
        self._hover.show()

    def hide(self):
        self._hover.hide()

    def destroy(self):
        self.hide()
        super().destroy()


def param_cell(parent, label: str, var, lo: int, hi: int, step: int, help_text: str,
               bg: str = CARD_BG, width: int = 64) -> tk.Frame:
    """Setting in a parameter grid: label (wraps) + "?" with the explanation,
    the number field below."""
    cell = tk.Frame(parent, bg=bg)
    head = tk.Frame(cell, bg=bg)
    head.pack(fill="x")
    HelpTip(head, help_text, bg=bg).pack(side="right", anchor="n", padx=(4, 0))
    WrapLabel(head, text=label, font=F_XS, fg=DIM, bg=bg, pad=2).pack(side="left", fill="x", expand=True)
    NumberField(cell, var, lo, hi, step, width=width, bg=bg).pack(anchor="w", pady=(2, 0))
    return cell


def run_async(widget: tk.Misc, work, done=None, poll_ms: int = 80):
    """Run work() in a thread; done(result) runs later on the Tk main thread.
    The hand-over is polled from the main thread (after() called from a worker
    raises on Python 3.14 when the main loop is not running yet)."""
    box = {}

    def worker():
        try:
            box["result"] = work()
        except Exception as e:                 # noqa: BLE001 — reported to done()
            box["result"] = e

    def poll():
        if "result" in box:
            if done is not None:
                try:
                    done(box["result"])
                except tk.TclError:
                    pass
            return
        try:
            widget.after(poll_ms, poll)
        except (tk.TclError, RuntimeError):
            pass

    import threading
    threading.Thread(target=worker, daemon=True).start()
    widget.after(poll_ms, poll)


# ── containers ───────────────────────────────────────────────────────────────

class Card(ctk.CTkFrame):
    """Rounded card: optional title row (with `actions` on the right) and a
    `body` frame for the content."""

    def __init__(self, parent, title: str | None = None, subtitle: str | None = None,
                 accent: str | None = None, padx: int = 16, pady: int = 14,
                 bg: str = CARD_BG, **kw):
        super().__init__(parent, fg_color=bg, corner_radius=12, border_width=1,
                         border_color=BORDER, **kw)
        self.bg = bg
        inner = tk.Frame(self, bg=bg)
        inner.pack(fill="both", expand=True, padx=padx, pady=pady)
        self.actions = None
        if title:
            head = tk.Frame(inner, bg=bg)
            head.pack(fill="x", pady=(0, 8))
            if accent:
                tk.Frame(head, bg=accent, width=3, height=16).pack(side="left", padx=(0, 9))
            tk.Label(head, text=title, font=F_H, fg=TEXT, bg=bg).pack(side="left")
            self.actions = tk.Frame(head, bg=bg)
            self.actions.pack(side="right")
            if subtitle:
                WrapLabel(inner, text=subtitle, font=F_S, fg=DIM, bg=bg).pack(fill="x", pady=(0, 10))
        self.body = tk.Frame(inner, bg=bg)
        self.body.pack(fill="both", expand=True)


class ResponsiveGrid(tk.Frame):
    """Lays its children out in equal columns — as many as fit (min_width each),
    balanced over the rows: 6 tiles become 3 + 3 rather than 5 + 1."""

    def __init__(self, parent, min_width: int = 260, max_cols: int = 4, gap: int = 12,
                 bg: str = APP_BG, **kw):
        super().__init__(parent, bg=bg, **kw)
        self._min, self._max, self._gap = min_width, max_cols, gap
        self._items: list[tk.Widget] = []
        self._cols = 0
        self._fit = 0                      # columns the current width allows
        self.bind("<Configure>", self._on_configure, add="+")

    def add(self, widget: tk.Widget) -> tk.Widget:
        self._items.append(widget)
        self._layout(self._balanced(self._fit or self._max))
        return widget

    def _balanced(self, fit: int) -> int:
        n = max(1, len(self._items))
        rows = -(-n // max(1, fit))        # ceil
        return max(1, -(-n // rows))

    def _on_configure(self, e):
        self._fit = max(1, min(self._max, (e.width + self._gap) // (self._min + self._gap)))
        cols = self._balanced(self._fit)
        if cols != self._cols:
            self._layout(cols)

    def _layout(self, cols: int):
        self._cols = cols
        for c in range(self._max):
            self.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="rg" if c < cols else "")
        for i, w in enumerate(self._items):
            r, c = divmod(i, cols)
            w.grid(row=r, column=c, sticky="nsew",
                   padx=(0 if c == 0 else self._gap // 2, 0 if c == cols - 1 else self._gap // 2),
                   pady=(0, self._gap))


class ThinScrollbar(tk.Canvas):
    """Slim rounded scrollbar drawn on a canvas (API like tk.Scrollbar: set() and
    command=yview). No update_idletasks() — see ScrollArea."""

    def __init__(self, parent, command=None, bg: str = APP_BG, width: int = 10):
        # height=20: a canvas asks for 7 cm (265 px) by default — that stretched
        # every log box next to it; fill="y" gives it its real height
        super().__init__(parent, width=width, height=20, bg=bg, highlightthickness=0, bd=0)
        self._cmd = command
        self._first, self._last = 0.0, 1.0
        self._hot = self._drag = False
        self._grab = 0.0
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hot(True))
        self.bind("<Leave>", lambda e: self._set_hot(False))
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)

    def configure(self, cnf=None, **kw):
        if "command" in kw:
            self._cmd = kw.pop("command")
        if cnf or kw:
            return super().configure(cnf, **kw)

    config = configure

    def set(self, first, last):
        self._first, self._last = float(first), float(last)
        self._draw()

    def get(self):
        return self._first, self._last

    def _set_hot(self, hot):
        self._hot = hot
        self._draw()

    def _geometry(self):
        h = self.winfo_height()
        pad, span = 2, max(1, self.winfo_height() - 4)
        y0 = pad + self._first * span
        y1 = pad + self._last * span
        if y1 - y0 < 28:                       # keep the thumb grabbable
            mid = (y0 + y1) / 2
            y0, y1 = max(pad, mid - 14), min(h - pad, mid + 14)
        return y0, y1, span

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if h < 8 or self._last - self._first >= 0.999:
            return                              # nothing to scroll: no thumb
        y0, y1, _span = self._geometry()
        tw = 6 if (self._hot or self._drag) else 4
        x0 = (w - tw) / 2
        col = MUTED if (self._hot or self._drag) else BORDER2
        r = tw / 2
        self.create_oval(x0, y0, x0 + tw, y0 + tw, fill=col, outline="")
        self.create_oval(x0, y1 - tw, x0 + tw, y1, fill=col, outline="")
        self.create_rectangle(x0, y0 + r, x0 + tw, y1 - r, fill=col, outline="")

    def _press(self, e):
        if self._cmd is None or self._last - self._first >= 0.999:
            return
        y0, y1, span = self._geometry()
        if y0 <= e.y <= y1:
            self._drag, self._grab = True, (e.y - y0) / span
            self._draw()
        else:
            self._cmd("scroll", -1 if e.y < y0 else 1, "pages")

    def _motion(self, e):
        if self._drag and self._cmd is not None:
            _y0, _y1, span = self._geometry()
            self._cmd("moveto", max(0.0, (e.y - 2) / span - self._grab))

    def _release(self, _e):
        self._drag = False
        self._draw()


class ScrollArea(tk.Frame):
    """Vertically scrolling area. The object IS the content frame — create the
    children with it as parent; pack/grid/place it like a frame (that moves the
    outer container). The mouse wheel works anywhere over the content (~60 px
    per notch); scrollable children (log, tables) scroll themselves first."""

    def __init__(self, parent, bg: str = APP_BG, width: int = 200, height: int = 200):
        self._outer = tk.Frame(parent, bg=bg)
        self._parent_canvas = tk.Canvas(self._outer, bg=bg, highlightthickness=0, bd=0,
                                        width=width, height=height, yscrollincrement=3)
        self._sb = ThinScrollbar(self._outer, command=self._parent_canvas.yview, bg=bg)
        self._sb.pack(side="right", fill="y", padx=(4, 0), pady=2)
        self._parent_canvas.pack(side="left", fill="both", expand=True)
        super().__init__(self._parent_canvas, bg=bg)
        self._win = self._parent_canvas.create_window(0, 0, window=self, anchor="nw")
        self._parent_canvas.configure(yscrollcommand=self._sb.set)
        self.bind("<Configure>", self._fit_region, add="+")
        self._parent_canvas.bind("<Configure>", self._fit_width, add="+")
        root = self._root()
        if not getattr(root, "_gop_wheel", False):          # one dispatcher per Tk root
            root._gop_wheel = True
            root.bind_all("<MouseWheel>", _wheel_dispatch, add="+")

    def _fit_region(self, _e=None):
        self._parent_canvas.configure(scrollregion=(0, 0, self.winfo_reqwidth(),
                                                    max(self.winfo_reqheight(), 1)))

    def _fit_width(self, e):
        self._parent_canvas.itemconfigure(self._win, width=e.width)

    def scrollable(self) -> bool:
        return self._parent_canvas.yview() != (0.0, 1.0)

    def _mouse_wheel_all(self, e):
        """Scroll when the wheel event happened over this area's content."""
        w = e.widget
        while w is not None:
            if w is self:
                if self.scrollable():
                    self._parent_canvas.yview_scroll(-20 if e.delta > 0 else 20, "units")
                return True
            w = getattr(w, "master", None)
        return False

    # geometry managers act on the outer container
    def pack(self, **kw):
        self._outer.pack(**kw)

    def grid(self, **kw):
        self._outer.grid(**kw)

    def place(self, **kw):
        self._outer.place(**kw)

    def pack_forget(self):
        self._outer.pack_forget()

    def grid_forget(self):
        self._outer.grid_forget()

    def winfo_manager(self):
        return self._outer.winfo_manager()

    def destroy(self):
        super().destroy()
        try:
            self._outer.destroy()
        except tk.TclError:
            pass


def _wheel_dispatch(e):
    """The innermost ScrollArea under the pointer gets the wheel event."""
    w = e.widget
    if isinstance(w, str):
        try:
            w = e.widget.nametowidget(w)        # pragma: no cover — string widgets are rare
        except Exception:
            return
    while w is not None:
        if isinstance(w, ScrollArea):
            if w.scrollable():
                w._parent_canvas.yview_scroll(-20 if e.delta > 0 else 20, "units")
            return
        w = getattr(w, "master", None)


def scroll_area(parent, bg: str = APP_BG, **kw) -> ScrollArea:
    """A ScrollArea (kept as a function for the call sites)."""
    return ScrollArea(parent, bg=bg, **kw)


def own_wheel(widget):
    """A scrollable child (text, table) inside a scrolling page scrolls itself
    while it can — and only then; at its end the page scrolls on."""
    def on_wheel(e):
        first, last = widget.yview()
        if (first, last) == (0.0, 1.0):
            return None                         # nothing to scroll: let the page move
        step = -1 if e.delta > 0 else 1
        if (step < 0 and first <= 0.0) or (step > 0 and last >= 1.0):
            return "break"
        widget.yview_scroll(step * 3, "units")
        return "break"
    widget.bind("<MouseWheel>", on_wheel)


class Page(tk.Frame):
    """A page: title row (accent bar, title, subtitle, `actions` on the right)
    and a `body` — scrolling (CTkScrollableFrame) or fixed."""

    def __init__(self, parent, title: str, subtitle: str = "", color: str = ACC,
                 scroll: bool = True, **kw):
        super().__init__(parent, bg=APP_BG, **kw)
        head = tk.Frame(self, bg=APP_BG)
        head.pack(fill="x", padx=24, pady=(18, 12))
        self.actions = tk.Frame(head, bg=APP_BG)      # packed first: never squeezed out
        self.actions.pack(side="right", padx=(12, 0))
        tk.Frame(head, bg=color, width=4).pack(side="left", fill="y", padx=(0, 12))
        tbox = tk.Frame(head, bg=APP_BG)
        tbox.pack(side="left", fill="x", expand=True)
        tk.Label(tbox, text=title, font=F_TITLE, fg=TEXT, bg=APP_BG, anchor="w").pack(fill="x")
        self.lbl_subtitle = WrapLabel(tbox, text=subtitle, font=F_S, fg=DIM, bg=APP_BG)
        if subtitle:
            self.lbl_subtitle.pack(fill="x")
        self.head = head
        if scroll:
            self.body = scroll_area(self)
            self.body.pack(fill="both", expand=True, padx=(14, 4), pady=(0, 8))
        else:
            self.body = tk.Frame(self, bg=APP_BG)
            self.body.pack(fill="both", expand=True, padx=24, pady=(0, 14))


# ── data display ─────────────────────────────────────────────────────────────

def tile(parent, title: str, value: str = "--", color: str = ACC, unit: str = "",
         bg: str = CARD_BG2):
    """Stat tile -> (frame, value_label). The value label is plain tk, so
    `.config(text=..., fg=...)` works as before."""
    f = ctk.CTkFrame(parent, fg_color=bg, corner_radius=10)
    inner = tk.Frame(f, bg=bg)
    inner.pack(fill="both", expand=True, padx=10, pady=8)
    tk.Label(inner, text=title, font=F_XS, fg=DIM, bg=bg).pack()
    vl = tk.Label(inner, text=value, font=F_NUM, fg=color, bg=bg)
    vl.pack()
    if unit:
        tk.Label(inner, text=unit, font=F_MONOS, fg=DIM, bg=bg).pack()
    return f, vl


class ProgressLine(tk.Canvas):
    """Thin rounded progress bar on a plain canvas (a CTkProgressBar costs ~1 ms
    to build and redraws through CustomTkinter's engine; lists of cards add up)."""

    def __init__(self, parent, color: str = ACC, height: int = 5, bg: str = CARD_BG):
        super().__init__(parent, height=height, width=40, bg=bg, highlightthickness=0, bd=0)
        self.color, self._frac = color, 0.0
        self._track = mix(bg, "#ffffff", 0.07)
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, frac: float):
        self._frac = max(0.0, min(1.0, float(frac)))
        self._draw()

    def get(self) -> float:
        return self._frac

    def _pill(self, x0, x1, h, color):
        self.create_oval(x0, 0, x0 + h, h, fill=color, outline="")
        self.create_oval(x1 - h, 0, x1, h, fill=color, outline="")
        if x1 - x0 > h:
            self.create_rectangle(x0 + h / 2, 0, x1 - h / 2, h, fill=color, outline="")

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self._pill(0, w, h - 1, self._track)
        fw = w * self._frac
        if fw >= h:
            self._pill(0, fw, h - 1, self.color)


class GaugeBar(tk.Frame):
    """Label | rounded bar | value — `.set(value, max_value, fmt=None)`."""

    def __init__(self, parent, label: str, unit: str = "", color: str = ACC, bg: str = CARD_BG,
                 **kw):
        super().__init__(parent, bg=bg, **kw)
        self.unit, self.color, self._pct = unit, color, 0.0
        self._track = mix(bg, "#ffffff", 0.06)
        tk.Label(self, text=label, font=F_S, fg=TEXT2, bg=bg, width=14, anchor="w").pack(side="left")
        self.lbl = tk.Label(self, text="--", font=F_MONO, fg=color, bg=bg, width=10, anchor="e")
        self.lbl.pack(side="right")
        self.cv = tk.Canvas(self, height=10, width=40, bg=bg, highlightthickness=0, bd=0)
        self.cv.pack(side="left", fill="x", expand=True, padx=(4, 10), pady=6)
        self.cv.bind("<Configure>", self._draw)

    def set(self, val, max_val, fmt=None):
        self._pct = min(1.0, max(0.0, val / max_val)) if max_val else 0.0
        self.lbl.config(text=fmt or f"{val:.0f}{self.unit}")
        self._draw()

    def _pill(self, x0, x1, h, color):
        r = h / 2
        self.cv.create_oval(x0, 0, x0 + h, h, fill=color, outline="")
        self.cv.create_oval(x1 - h, 0, x1, h, fill=color, outline="")
        if x1 - x0 > h:
            self.cv.create_rectangle(x0 + r, 0, x1 - r, h, fill=color, outline="")

    def _draw(self, *_):
        w, h = self.cv.winfo_width(), self.cv.winfo_height()
        if w < 4 or h < 4:
            return
        self.cv.delete("all")
        self._pill(0, w, h - 1, self._track)
        fw = int(w * self._pct)
        if fw >= h:
            self._pill(0, fw, h - 1, self.color)


class LogView(tk.Frame):
    """Log text box. append()/clear() are safe from ANY thread: they only put
    into a queue that a main-thread poller drains (Tk must never be touched
    from worker threads — Python 3.14 raises "main thread is not in main loop")."""

    COLORS = {"info": TEXT2, "warning": AMBER, "error": ERR, "success": GREEN,
              "header": ACC, "dim": DIM}

    def __init__(self, parent, height: int = 8, bg: str = INPUT_BG, **kw):
        super().__init__(parent, bg=bg, **kw)
        sb = ThinScrollbar(self, bg=bg)
        sb.pack(side="right", fill="y", padx=(0, 2), pady=2)
        self.txt = tk.Text(self, height=height, font=F_MONO, bg=bg, fg=TEXT2, relief="flat", bd=0,
                           highlightthickness=0, wrap="word", state="disabled", padx=10, pady=8,
                           insertbackground=ACC, selectbackground=mix(bg, ACC, 0.35),
                           yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.configure(command=self.txt.yview)
        own_wheel(self.txt)
        for tag, col in self.COLORS.items():
            self.txt.tag_config(tag, foreground=col)
        self.txt.tag_config("ts", foreground=MUTED)
        self._q: queue.Queue = queue.Queue()
        self._alive = True
        self._after_id = self.after(120, self._drain)

    def destroy(self):
        self._alive = False
        try:
            if self._after_id:
                self.after_cancel(self._after_id)
        except Exception:
            pass
        self._after_id = None
        super().destroy()

    def append(self, msg: str, tag: str = "info"):
        self._q.put(("append", datetime.now().strftime("%H:%M:%S"), msg, tag))

    def clear(self):
        self._q.put(("clear",))

    def _drain(self):
        try:
            self.txt.config(state="normal")
            wrote = False
            while True:
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                if item[0] == "append":
                    _, ts, msg, tag = item
                    self.txt.insert("end", f"[{ts}] ", "ts")
                    self.txt.insert("end", f"{msg}\n", tag)
                    wrote = True
                elif item[0] == "clear":
                    self.txt.delete("1.0", "end")
            if wrote:
                self.txt.see("end")
            self.txt.config(state="disabled")
        except tk.TclError:
            self._alive = False
            return
        if self._alive:
            try:
                self._after_id = self.after(120, self._drain)
            except (tk.TclError, RuntimeError):
                self._alive = False


class ChoiceDialog(ctk.CTkToplevel):
    """Modal pick-one dialog. options: [(value, label)]; notes: [(text, colour)]
    shown under the list. show() returns the chosen value or None."""

    def __init__(self, parent, title: str, heading: str, options, current=None, notes=(),
                 ok_text: str = "OK", accent: str = GREEN):
        super().__init__(parent)
        self.title(title)
        # no resizable(): CustomTkinter re-colours the title bar 10 ms later, and a
        # transient dialog closed before that crashes Tk (access violation)
        self.result = None
        try:
            from ui.theme import app_icon_path
            icon = app_icon_path()
            if icon:
                self.iconbitmap(icon)
        except tk.TclError:
            pass
        body = tk.Frame(self, bg=APP_BG)
        body.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(body, text=heading, font=("Segoe UI Semibold", 12), fg=TEXT, bg=APP_BG,
                 justify="left", wraplength=440).pack(anchor="w", pady=(0, 10))
        self._var = tk.StringVar(value=current if current is not None else "")
        box = scroll_area(body, height=min(320, 34 * len(options) + 8), width=440, bg=CARD_BG)
        box.pack(fill="x")
        for value, label in options:
            ctk.CTkRadioButton(box, text=label, value=value, variable=self._var, fg_color=accent,
                               hover_color=hover_of(accent), font=ctk_font(13)
                               ).pack(anchor="w", padx=12, pady=5)
        for text, color in notes:
            tk.Label(body, text=text, font=F_XS, fg=color, bg=APP_BG, justify="left",
                     wraplength=440).pack(anchor="w", pady=(8, 0))
        btns = tk.Frame(body, bg=APP_BG)
        btns.pack(fill="x", pady=(16, 0))
        button(btns, tr("Abbrechen", "Cancel"), self.destroy).pack(side="right", padx=(8, 0))
        button(btns, ok_text, self._ok, kind="primary", color=accent).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        try:
            self.transient(parent.winfo_toplevel())
        except tk.TclError:
            pass
        self.after(60, self._focus)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except tk.TclError:
            pass

    def _ok(self):
        self.result = self._var.get() or None
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


class TextDialog(ChoiceDialog):
    """Modal one-line text input, pre-filled and selected (CTkInputDialog can't
    pre-fill — renaming starts from the old name). show() -> text or None.
    `check(text)` -> error message or "" keeps the dialog open on bad input."""

    def __init__(self, parent, title: str, heading: str, initial: str = "", ok_text: str = "OK",
                 check=None, accent: str = GREEN):
        ctk.CTkToplevel.__init__(self, parent)
        self.title(title)
        self.result = None
        self._check = check
        try:
            from ui.theme import app_icon_path
            icon = app_icon_path()
            if icon:
                self.iconbitmap(icon)
        except tk.TclError:
            pass
        body = tk.Frame(self, bg=APP_BG)
        body.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(body, text=heading, font=("Segoe UI Semibold", 12), fg=TEXT, bg=APP_BG,
                 justify="left", wraplength=420).pack(anchor="w", pady=(0, 10))
        self._var = tk.StringVar(value=initial)
        self.entry = ctk.CTkEntry(body, textvariable=self._var, width=420, height=32, font=ctk_font(13))
        self.entry.pack(fill="x")
        self.lbl_err = tk.Label(body, text="", font=F_XS, fg=ERR, bg=APP_BG, anchor="w")
        self.lbl_err.pack(fill="x", pady=(6, 0))
        btns = tk.Frame(body, bg=APP_BG)
        btns.pack(fill="x", pady=(10, 0))
        button(btns, tr("Abbrechen", "Cancel"), self.destroy).pack(side="right", padx=(8, 0))
        button(btns, ok_text, self._ok, kind="primary", color=accent).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        try:
            self.transient(parent.winfo_toplevel())
        except tk.TclError:
            pass
        self.after(60, self._focus)

    def _focus(self):
        super()._focus()
        try:
            self.entry.focus_set()
            self.entry.select_range(0, "end")
            self.entry.icursor("end")
        except tk.TclError:
            pass

    def _ok(self):
        text = self._var.get().strip()
        err = self._check(text) if (self._check and text) else ("" if text else "…")
        if err:
            self.lbl_err.config(text=err if err != "…" else tr("Bitte einen Namen eingeben.",
                                                               "Please enter a name."))
            return
        self.result = text
        self.destroy()


class Table(tk.Frame):
    """Dark ttk.Treeview with a CTk scrollbar. columns: [(key, heading, width, anchor)]."""

    def __init__(self, parent, columns, height: int = 10, bg: str = CARD_BG,
                 selectmode: str = "extended", **kw):
        super().__init__(parent, bg=bg, **kw)
        from ui.theme import ensure_styles
        ensure_styles(self)
        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings",
                                 style="GOP.Treeview", height=height, selectmode=selectmode)
        for key, head, width, anchor in columns:
            self.tree.heading(key, text=head)
            self.tree.column(key, width=width, anchor=anchor, minwidth=40, stretch=True)
        sb = ThinScrollbar(self, command=self.tree.yview, bg=bg)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        own_wheel(self.tree)
