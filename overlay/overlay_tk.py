"""Full-screen meeting alert for Windows (and any tkinter platform).

Reads one JSON object (UTF-8) from stdin. Exit codes: 0 dismiss, 10 join, 20 snooze.
Keys: Enter = join, Space = snooze, Esc = dismiss. Stdlib only.
"""
import json
import os
import sys
import tkinter as tk
import webbrowser

WIN = sys.platform == "win32"
BG, BTN_BG, BTN_HOVER = "#CC1419", "#E04046", "#EC6065"
DARK_RED, PRIMARY_HOVER = "#B71217", "#EBEBEB"
HEADER_FG, SUB_FG, HINT_FG = "#EBA1A3", "#F7D0D1", "#E6A0A2"  # white at 80/92/65% over BG
DEFAULTS = {
    "header": "MEETING", "title": "Meeting", "subtitle": "", "link": "",
    "join_label": "Join  (Enter)", "snooze_label": "Snooze 2 min  (Space)",
    "dismiss_label": "Dismiss  (Esc)", "hint": "This screen stays until you press a key.",
    "auto_close": 0, "sound": True,
}


def load_payload():
    data = dict(DEFAULTS)
    try:
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        loaded = json.loads(raw) if raw.strip() else {}
        if isinstance(loaded, dict):
            data.update({k: v for k, v in loaded.items() if v is not None})
    except (ValueError, OSError):
        pass
    return data


def monitors(root):
    """Return [(x, y, w, h)] with the primary monitor first."""
    if WIN:
        try:
            return win_monitors()
        except Exception:
            pass
    return [(0, 0, root.winfo_screenwidth(), root.winfo_screenheight())]


def win_monitors():
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    found = []
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                   ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def callback(hmon, _dc, _rect, _lp):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            found.append((info.dwFlags & 1 == 0, (r.left, r.top, r.right - r.left, r.bottom - r.top)))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, proc_type(callback), 0)
    found.sort(key=lambda m: m[0])
    return [m[1] for m in found]


def fit_title(text, width, size):
    """Shorten to roughly two wrapped lines at the given font size."""
    cap = max(10, int(2 * width / (size * 0.58)) - 2)
    return text if len(text) <= cap else text[: cap - 1].rstrip() + "…"


class Overlay:
    def __init__(self, cfg):
        self.cfg = cfg
        self.root = tk.Tk()
        self.windows = []
        self.buttons = [(cfg["join_label"], True, self.join),
                        (cfg["snooze_label"], False, self.snooze),
                        (cfg["dismiss_label"], False, self.dismiss)]
        for i, (x, y, w, h) in enumerate(monitors(self.root)):
            win = self.root if i == 0 else tk.Toplevel(self.root)
            self.build(win, x, y, w, h)
            self.windows.append(win)
        self.root.after(50, self.startup)
        if cfg["auto_close"]:
            self.root.after(int(float(cfg["auto_close"]) * 1000), self.dismiss)

    def build(self, win, x, y, w, h):
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.configure(bg=BG)
        for key in ("<Return>", "<KP_Enter>"):
            win.bind(key, lambda e: self.join())
        win.bind("<space>", lambda e: self.snooze())
        win.bind("<Escape>", lambda e: self.dismiss())
        s = max(0.45, min(1.0, w / 1700, h / 900))
        fam, c = "Segoe UI", self.cfg
        box = tk.Frame(win, bg=BG)
        box.place(relx=0.5, rely=0.5, anchor="center")
        wrap = int(w - 160 * s)
        tsize = int(76 * s)
        tk.Label(box, text=c["header"], font=(fam, int(34 * s), "bold"), fg=HEADER_FG, bg=BG).pack(pady=(0, int(14 * s)))
        tk.Label(box, text=fit_title(str(c["title"]), wrap, tsize), font=(fam, tsize, "bold"), fg="white",
                 bg=BG, wraplength=wrap, justify="center").pack(pady=(0, int(18 * s)))
        tk.Label(box, text=c["subtitle"], font=(fam, int(30 * s)), fg=SUB_FG, bg=BG,
                 wraplength=wrap, justify="center").pack(pady=(0, int(40 * s)))
        row = tk.Frame(box, bg=BG)
        row.pack()
        for label, primary, cmd in self.buttons:
            self.make_button(row, label, primary, cmd, s, fam).pack(side="left", padx=int(12 * s))
        tk.Label(box, text=c["hint"], font=(fam, max(10, int(17 * s))), fg=HINT_FG, bg=BG).pack(pady=(int(36 * s), 0))

    def make_button(self, parent, label, primary, cmd, s, fam):
        fill, hover = (("white", PRIMARY_HOVER) if primary else (BTN_BG, BTN_HOVER))
        fg = DARK_RED if primary else "white"
        b = tk.Button(parent, text=label, command=cmd, relief="flat", bd=0, highlightthickness=0,
                      font=(fam, max(11, int(25 * s)), "bold"), bg=fill, fg=fg, activebackground=hover,
                      activeforeground=fg, cursor="hand2", width=20, padx=int(10 * s), pady=int(16 * s))
        b.bind("<Enter>", lambda e: b.configure(bg=hover))
        b.bind("<Leave>", lambda e: b.configure(bg=fill))
        return b

    def startup(self):
        self.lift_all()
        if WIN:
            self.foreground_trick()
        self.tick()

    def foreground_trick(self):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.keybd_event(0x12, 0, 0, 0)
            user32.keybd_event(0x12, 0, 2, 0)
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def lift_all(self):
        for win in self.windows:
            win.lift()
            win.attributes("-topmost", True)
        self.root.focus_force()

    def beep(self):
        if not self.cfg["sound"]:
            return
        try:
            if WIN:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONHAND)
            else:
                self.root.bell()
        except Exception:
            pass

    def tick(self):
        """Beep and re-lift now, then every 4 seconds."""
        self.lift_all()
        self.beep()
        self.root.after(4000, self.tick)

    def finish(self, code):
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)

    def join(self):
        link = str(self.cfg["link"] or "")
        if link:
            try:
                webbrowser.open(link)
            except Exception:
                pass
        self.finish(10)

    def snooze(self):
        self.finish(20)

    def dismiss(self):
        self.finish(0)


def main():
    cfg = load_payload()
    if WIN:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    Overlay(cfg).root.mainloop()


if __name__ == "__main__":
    main()
