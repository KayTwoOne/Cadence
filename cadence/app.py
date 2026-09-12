"""Cadence - Controller Input Suite. The shell: top bar, tabs, and the event pump."""

import gc
import sys
import csv
import threading
import time
import queue
import ctypes
import statistics
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from .theme import (BG, PANEL, PANEL_2, RAISED, RAISED_HI, EDGE, LINE, TEXT, MUTED, DIM,
                    BRAND, BRAND_HI, TINT, ACCENT, MISS, Type)
from .widgets import UIKit
from .hardware import XInputReader, DemoReader, Poller, BUTTONS, LABEL
from . import timing as T
from .timing import TimingModel, fmt_ticks, stick_arrow
from .macros import MacroEngine, GlobalHotkey
from .synth import PANIC_KEYS, Synth
from .tab_timing import TimingTab
from .tab_pads import PadsTab
from .tab_macros import MacroTab
from .controllers import SchemeResolver, SCHEMES
from .version import __version__, APP_NAME, APP_TAGLINE
from . import chrome, updater

GC_INTERVAL = 12.0


def dark_title_bar(root):
    """Ask Windows for a dark title bar so the frame matches the app inside it."""
    if sys.platform != "win32":
        return
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        flag = ctypes.c_int(1)
        for attribute in (20, 19):      # 20 on current builds, 19 on 1809-1903
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd), ctypes.c_int(attribute),
                    ctypes.byref(flag), ctypes.sizeof(flag)) == 0:
                break
    except Exception:
        pass


class App:
    def __init__(self, root, reader, demo=False, live_output=True):
        self.root = root
        self.demo = demo
        self.q = queue.Queue()
        self.poller = Poller(reader, self.q)
        self.t_start = time.perf_counter()
        self.paused = False
        self.follow = False
        self.ignored = {"START", "BACK"}
        self.gap_ref = [600]
        self.models = {}
        self.names = {i: f"Controller {i + 1}" for i in range(4)}
        self.connected = set()
        self.activity = {i: 0.0 for i in range(4)}
        self.selected = None
        self.res = 0.0
        self.last_status = 0.0
        self.last_gc = time.perf_counter()
        self.tick_job = None
        self.help_win = None
        self.panic_key = "F8"
        self.hotkey = None
        self.schemes = SchemeResolver()
        self.pending_update = None
        self.maximised = False
        self.restore_geom = None
        self.frameless = False

        self.type = Type(root)
        self.ui = UIKit(root, self.type)
        self.engine = MacroEngine(sender=Synth(live=live_output),
                                  on_change=self.on_engine_change)

        root.title(f"{APP_NAME}{' (demo)' if demo else ''}")
        root.configure(bg=BG)
        # Our own caption replaces the native one. Done before any geometry work so
        # the window is only ever sized once.
        if sys.platform == "win32":
            try:
                root.overrideredirect(True)
                self.frameless = True
            except Exception:
                self.frameless = False
        want_w, want_h = self.ui.px(1300), self.ui.px(950)
        w = min(want_w, root.winfo_screenwidth() - self.ui.px(40))
        h = min(want_h, root.winfo_screenheight() - self.ui.px(80))
        root.geometry(f"{w}x{h}")
        root.minsize(min(self.ui.px(1100), w), min(self.ui.px(720), h))

        self.anim = chrome.WindowAnimator(root)
        self._style()
        self._build()
        if self.frameless:
            chrome.keep_on_taskbar(root)
            self.grips = chrome.ResizeGrips(root, self, self.ui.px(1000),
                                            self.ui.px(680))
            root.after(120, lambda: chrome.round_corners(root))
        else:
            dark_title_bar(root)
        self.poller.start()
        self.engine.start()
        self.install_hotkey()
        # One quiet check a few seconds after launch, off the UI thread. If GitHub is
        # slow, blocked or down, nothing happens and nobody is told.
        self.root.after(4000, self.check_for_update)

        for key, fn in (("c", self.clear), ("p", self.toggle_pause),
                        ("s", self.export), ("h", self.show_help)):
            root.bind(f"<Key-{key}>", lambda e, f=fn: f())
            root.bind(f"<Key-{key.upper()}>", lambda e, f=fn: f())
        for i in range(4):
            root.bind(f"<Key-{i + 1}>", lambda e, n=i: self.select(n))
        root.bind("<Escape>", lambda e: self.engine.panic("Escape"))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.tick()

    # ---------------------------------------------------------------- chrome
    def _style(self):
        ui = self.ui
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("Log.Treeview", background=PANEL, fieldbackground=PANEL,
                     foreground=TEXT, rowheight=ui.px(25), borderwidth=0, font=ui.d(9))
        st.configure("Log.Treeview.Heading", background=PANEL_2, foreground=MUTED,
                     relief="flat", borderwidth=0, font=ui.f(9, "tight"), padding=(6, 6))
        st.map("Log.Treeview", background=[("selected", BRAND)])
        st.map("Log.Treeview.Heading", background=[("active", PANEL_2)])
        st.layout("Log.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        st.configure("Log.Vertical.TScrollbar", background=RAISED, troughcolor=PANEL,
                     bordercolor=PANEL, arrowcolor=MUTED, lightcolor=RAISED,
                     darkcolor=RAISED, gripcount=0)
        st.map("Log.Vertical.TScrollbar",
               background=[("active", LINE), ("!active", RAISED)])

    def _build(self):
        ui = self.ui
        # One hairline around everything, because a frameless window has no edge of
        # its own and would otherwise bleed into whatever sits behind it.
        outer = tk.Frame(self.root, bg=EDGE)
        outer.pack(fill="both", expand=True)
        r = tk.Frame(outer, bg=BG)
        r.pack(fill="both", expand=True, padx=1, pady=(1, 1))
        self.shell = r
        r.grid_columnconfigure(0, weight=1)
        r.grid_rowconfigure(4, weight=1)

        if self.frameless:
            self.titlebar = chrome.TitleBar(r, self, self.close, self.minimise,
                                            self.toggle_maximise)
            self.titlebar.frame.grid(row=0, column=0, sticky="ew")
            self.titlebar.rule.grid(row=1, column=0, sticky="ew")
        else:
            self.titlebar = None

        head = tk.Frame(r, bg=BG)
        head.grid(row=2, column=0, sticky="ew", padx=18, pady=(14, 8))
        # The mark is the running indicator: dark while idle, lit while macros are armed.
        self.logo = tk.Canvas(head, width=ui.px(30), height=ui.px(30), bg=BG,
                              highlightthickness=0)
        self.logo_ring = self.logo.create_oval(*ui.s(1, 1, 29, 29), fill=RAISED, outline="")
        self.logo_bars = [
            self.logo.create_line(*ui.s(9, 20, 9, 10), fill=DIM, width=2.6 * ui.S,
                                  capstyle="round"),
            self.logo.create_line(*ui.s(15, 23, 15, 7), fill=DIM, width=2.6 * ui.S,
                                  capstyle="round"),
            self.logo.create_line(*ui.s(21, 19, 21, 11), fill=DIM, width=2.6 * ui.S,
                                  capstyle="round")]
        self.logo.pack(side="left", padx=(0, 11))
        ui.tooltip(self.logo, "Lights up while macros are armed")
        word = tk.Frame(head, bg=BG)
        word.pack(side="left")
        tk.Label(word, text=APP_NAME.upper(), bg=BG, fg=TEXT, font=ui.f(17, "semi"),
                 anchor="w").pack(fill="x")
        tk.Label(word, text=APP_TAGLINE, bg=BG, fg=MUTED, font=ui.f(9, "tight"),
                 anchor="w").pack(fill="x")
        helpb = tk.Label(head, text="?", bg=RAISED, fg=TEXT, font=ui.f(11, "semi"),
                         width=2, pady=2, cursor="hand2")
        helpb.pack(side="left", padx=(16, 0))
        helpb.bind("<Button-1>", lambda e: self.show_help())
        ui.hover(helpb, RAISED, RAISED_HI)
        ui.tooltip(helpb, "What every number on screen means  (H)")

        self.m_loop = ui.metric(head, "read loop")
        self.m_loop.pack(side="right", padx=(18, 0))
        ui.tooltip(self.m_loop, "How fast the reader thread spins, and the slowest single "
                                "trip it took. Only matters if the worst figure grows.")
        self.m_res = ui.metric(head, "resolution")
        self.m_res.pack(side="right", padx=(18, 0))
        ui.tooltip(self.m_res, "How often the selected pad sends its state, and the "
                               "margin that puts on every gap. Measure a pad on the "
                               "Controllers tab to replace the assumption.")
        self.m_pads = ui.metric(head, "controllers")
        self.m_pads.pack(side="right", padx=(18, 0))

        # ---- tab strip and per-tab actions on one line
        bar = tk.Frame(r, bg=BG)
        bar.grid(row=3, column=0, sticky="ew", padx=18, pady=(2, 10))
        self.tab_row = tk.Frame(bar, bg=BG)
        self.tab_row.pack(side="left")

        self.timing_actions = tk.Frame(bar, bg=BG)
        ui.action(self.timing_actions, "SAVE CSV", "S", self.export,
                  kind="brand").pack(side="right")
        ui.action(self.timing_actions, "CLEAR", "C", self.clear).pack(side="right",
                                                                     padx=8)
        self.pause_btn = ui.action(self.timing_actions, "PAUSE", "P", self.toggle_pause)
        self.pause_btn.pack(side="right")
        self.follow_btn = ui.button(self.timing_actions, "", self.toggle_follow)
        self.follow_btn.pack(side="right", padx=8)
        self._paint_follow()

        self.pad_sep = tk.Frame(bar, bg=LINE, width=1)
        self.pad_pills = tk.Frame(bar, bg=BG)
        self.pills = {}
        for i in range(4):
            p = tk.Frame(self.pad_pills, bg=PANEL, cursor="hand2", padx=10, pady=5)
            p.pack(side="left", padx=(0, 6))
            dot = tk.Canvas(p, width=ui.px(9), height=ui.px(9), bg=PANEL,
                            highlightthickness=0)
            dot_id = dot.create_oval(*ui.s(0, 0, 9, 9), fill=DIM, outline="")
            dot.pack(side="left", padx=(0, 7))
            name = tk.Label(p, text=self.names[i], bg=PANEL, fg=MUTED, font=ui.f(9, "semi"))
            name.pack(side="left")
            for w in (p, dot, name):
                w.bind("<Button-1>", lambda e, s=i: self.select(s))
                w.bind("<Double-Button-1>", lambda e, s=i: self.rename(s))
            self.pills[i] = (p, dot, dot_id, name)

        # ---- tab bodies
        host = tk.Frame(r, bg=BG)
        host.grid(row=4, column=0, sticky="nsew", padx=18, pady=(0, 16))
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)
        self.host = host

        self.tabs = {}
        self.tab_order = [("timing", "TIMING", TimingTab),
                          ("pads", "CONTROLLERS", PadsTab),
                          ("macros", "MACROS", MacroTab)]
        self.tab_buttons = {}
        for key, label, cls in self.tab_order:
            tab = cls(host, self)
            tab.frame.grid(row=0, column=0, sticky="nsew")
            self.tabs[key] = tab
            holder = tk.Frame(self.tab_row, bg=BG)
            holder.pack(side="left", padx=(0, 4))
            b = tk.Label(holder, text=label, font=ui.f(11, "semi"), padx=18, pady=8,
                         cursor="hand2")
            b.pack(fill="x")
            rule = tk.Frame(holder, bg=BG, height=ui.px(3))
            rule.pack(fill="x")
            for wdg in (b, holder):
                wdg.bind("<Button-1>", lambda e, k=key: self.show_tab(k))
            self.tab_buttons[key] = (b, rule)
        self.current_tab = None
        self.show_tab("timing")
        self.root.after(60, self.fit_to_content)

    # ---------------------------------------------------------------- window
    def minimise(self):
        chrome.minimise(self.root)

    def toggle_maximise(self):
        """Maximise fills the work area, not the screen, so the taskbar stays visible."""
        if self.maximised:
            x, y, w, h = self.restore_geom or (100, 100, self.ui.px(1300),
                                               self.ui.px(950))
            self.maximised = False
            self.anim.to(x, y, w, h, on_done=self._after_resize)
        else:
            self.restore_geom = (self.root.winfo_x(), self.root.winfo_y(),
                                 self.root.winfo_width(), self.root.winfo_height())
            wx, wy, ww, wh = chrome.work_area()
            self.maximised = True
            self.anim.to(wx, wy, ww, wh, on_done=self._after_resize)
        if self.titlebar:
            self.titlebar.set_maximised(self.maximised)

    def _after_resize(self):
        if self.frameless:
            chrome.round_corners(self.root)
            if hasattr(self, "grips"):
                self.grips._place()

    def fit_to_content(self):
        """Size the window once, to whichever tab needs the most room.

        Resizing on every tab switch looked reasonable and behaved badly: Tk relays out
        every widget in the window on each animation frame, and at four hundred-odd
        widgets that is about a seventh of a second each. Thirty frames of that is the
        window visibly coming apart and reassembling. Picking one size up front costs
        a little spare space on the smaller tabs and nothing else."""
        if self.maximised or not self.frameless:
            return
        self.root.update_idletasks()
        chrome_h = self.titlebar.frame.winfo_height() if self.titlebar else 0
        need_h = need_w = 0
        for tab in self.tabs.values():
            need_h = max(need_h, tab.frame.winfo_reqheight())
            need_w = max(need_w, tab.frame.winfo_reqwidth())
        wx, wy, ww, wh = chrome.work_area()
        h = max(self.ui.px(720), min(need_h + chrome_h + self.ui.px(150), wh))
        w = max(self.ui.px(1100), min(need_w + self.ui.px(44), ww))
        x = max(wx, min(self.root.winfo_x(), wx + ww - w))
        y = max(wy, min(self.root.winfo_y(), wy + wh - h))
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self._after_resize()

    def show_tab(self, key):
        if key == self.current_tab:
            return
        self.current_tab = key
        for k, (b, rule) in self.tab_buttons.items():
            on = k == key
            self.ui.restyle(b, PANEL if on else BG, PANEL if on else RAISED,
                            TEXT if on else MUTED)
            rule.configure(bg=BRAND_HI if on else BG)
        self.tabs[key].frame.tkraise()
        # Actions belong to the tab that uses them, so the bar changes with the tab
        # rather than showing controls that do nothing where you are standing.
        self.timing_actions.pack_forget()
        self.pad_pills.pack_forget()
        self.pad_sep.pack_forget()
        if key == "timing":
            self.timing_actions.pack(side="right")
            self.pad_pills.pack(side="right", padx=(0, 16))
            self.pad_sep.pack(side="right", fill="y", pady=4, padx=(0, 16))
        self.tabs[key].refresh_all()

    # ---------------------------------------------------------------- model
    def scheme(self, slot=None):
        slot = self.selected if slot is None else slot
        return self.schemes.scheme(0 if slot is None else slot)

    def label(self, key, slot=None):
        """What this button is called on the pad it came from.

        XInput reports one fixed set of names; the scheme translates them into what is
        printed on the plastic the user is actually holding."""
        return self.scheme(slot).label(key)

    def rescan_schemes(self):
        self.schemes.scan(self.connected)
        for tab in self.tabs.values():
            if hasattr(tab, "on_scheme_change"):
                tab.on_scheme_change()

    def model(self, slot):
        if slot not in self.models:
            self.models[slot] = TimingModel(self.ignored, self.gap_ref)
        return self.models[slot]

    @property
    def cur(self):
        return self.model(self.selected) if self.selected is not None else None

    def select(self, slot):
        if slot not in self.connected and slot not in self.models:
            return
        if slot == self.selected:
            return
        self.selected = slot
        self.tabs["timing"].refresh_all()
        self.paint_pills()

    def rename(self, slot):
        name = simpledialog.askstring("Rename controller", "Name for this controller:",
                                      initialvalue=self.names[slot], parent=self.root)
        if name and name.strip():
            self.names[slot] = name.strip()[:22]
            self.paint_pills()

    # ---------------------------------------------------------------- events
    def handle(self, ev):
        kind, slot, key, t, payload = ev
        if kind == "connected":
            self.connected.add(slot)
            self.model(slot)
            self.root.after(60, self.rescan_schemes)
            if self.selected is None or self.selected not in self.connected:
                self.selected = slot
                self.tabs["timing"].refresh_all()
            return False
        if kind == "disconnected":
            self.connected.discard(slot)
            return False

        if kind == "down":
            # Macros and the binding capture see every press, on every pad, on every
            # tab. Only the timing log is filtered down to the selected controller.
            if self.tabs["macros"].offer_button(slot, key):
                return False
            self.engine.handle(slot, key, True)
        elif kind == "up":
            self.engine.handle(slot, key, False)

        m = self.model(slot)
        if kind == "down":
            self.activity[slot] = t
            if self.paused:
                return False
            if self.follow and slot != self.selected:
                self.selected = slot
                self.tabs["timing"].refresh_all()
            rec = m.press(key, t, payload)
            if rec and slot == self.selected:
                self.tabs["timing"].on_press(rec)
                return True
        elif kind == "up":
            rec = m.release(key, t)
            if rec and slot == self.selected:
                self.tabs["timing"].on_release(rec)
                return True
        return False

    def on_engine_change(self):
        """The engine runs on its own thread, so bounce back to the UI thread."""
        try:
            self.root.after(0, self._engine_changed)
        except RuntimeError:
            pass

    def _engine_changed(self):
        self.tabs["macros"].paint_master()
        self.paint_logo()

    # ---------------------------------------------------------------- updates
    def check_for_update(self, announce=False):
        def done(latest):
            self.root.after(0, lambda: self.update_found(latest, announce))
        updater.UpdateCheck(done).start()

    def update_found(self, latest, announce):
        if not latest:
            if announce:
                messagebox.showinfo("Cadence",
                                    f"You are on {__version__}, which is the newest.")
            return
        self.pending_update = latest
        if self.titlebar:
            self.titlebar.show_update(latest["version"])

    def run_update(self):
        latest = self.pending_update
        if not latest:
            return
        notes = latest["notes"]
        if len(notes) > 700:
            notes = notes[:700].rsplit("\n", 1)[0] + "\n..."
        kind = updater.install_kind()
        if kind == "source":
            messagebox.showinfo(
                "Cadence",
                f"Version {latest['version']} is out.\n\n"
                f"This copy runs from source, so git pull is the update.")
            return
        if not messagebox.askyesno(
                f"Cadence {latest['version']}",
                f"You have {__version__}. Version {latest['version']} is "
                f"available.\n\n{notes}\n\nDownload and install it now?"):
            return
        asset = updater.pick_asset(latest["assets"], kind)
        if not asset:
            messagebox.showinfo(
                "Cadence",
                f"That release has no Windows download.\n"
                f"Open {latest['page']} to get it manually.")
            return

        def work():
            try:
                path = updater.download(asset)
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror(
                    "Download failed",
                    f"{exc}\n\nTry {latest['page']} instead."))
                return
            self.root.after(0, lambda: self.finish_update(path))
        threading.Thread(target=work, daemon=True).start()
        if self.titlebar:
            self.titlebar.set_update_text("downloading...")


    def finish_update(self, path):
        if updater.apply_update(path):
            self.close()

    # ---------------------------------------------------------------- hotkey
    def install_hotkey(self):
        if self.hotkey:
            self.hotkey.stop()
            self.hotkey = None
        vk = PANIC_KEYS.get(self.panic_key)
        if vk:
            self.hotkey = GlobalHotkey(vk, lambda: self.engine.panic(
                f"{self.panic_key} panic key"))
            self.hotkey.start()

    def hotkey_ok(self):
        """Whether the panic key is actually registered.

        RegisterHotKey fails silently when another application already owns the key,
        and a panic key that does nothing is worse than no panic key at all, because
        you would be relying on it."""
        if not self.hotkey:
            return False
        if self.hotkey.is_alive() or self.hotkey.ok:
            return self.hotkey.ok
        return False

    def set_panic_key(self, key):
        self.panic_key = key
        self.install_hotkey()
        self.tabs["macros"].paint_master()

    # ---------------------------------------------------------------- painting
    def paint_logo(self):
        on = self.engine.armed_master
        self.logo.itemconfigure(self.logo_ring, fill=BRAND if on else RAISED)
        for bar in self.logo_bars:
            self.logo.itemconfigure(bar, fill=TEXT if on else DIM)

    def paint_pills(self):
        now = time.perf_counter()
        for i, (p, dot, dot_id, name) in self.pills.items():
            conn = i in self.connected
            sel = i == self.selected
            bg = BRAND if sel else PANEL
            for w in (p, dot, name):
                w.configure(bg=bg)
            active = conn and now - self.activity[i] < 0.12
            dot.itemconfigure(dot_id,
                              fill=("#ffffff" if active
                                    else (TINT if conn else DIM)))
            name.configure(text=self.names[i],
                           fg=TEXT if (conn or sel) else DIM)

    def paint_metrics(self):
        n = len(self.connected)
        if not n:
            self.m_pads.value.configure(text="none", fg=DIM)
            self.m_pads.caption.configure(text="CONTROLLERS")
            self.m_res.value.configure(text="—", fg=DIM)
            self.m_res.caption.configure(text="RESOLUTION")
            self.m_loop.value.configure(text="—", fg=DIM)
            self.m_loop.caption.configure(text="READ LOOP")
            return
        self.m_pads.value.configure(text="paused" if self.paused else f"{n} live",
                                    fg=ACCENT if self.paused else BRAND_HI)
        self.m_pads.caption.configure(text="CONTROLLERS")
        rep = self.poller.report_ms(self.selected) if self.selected is not None else 0.0
        self.m_res.value.configure(text=f"±{self.res:.1f} ms", fg=TEXT if rep else MUTED)
        self.m_res.caption.configure(
            text=f"RESOLUTION · PAD {rep:.1f} MS" if rep else "RESOLUTION · ASSUMED")
        worst = self.poller.worst_poll_ms
        self.m_loop.value.configure(text=f"{self.poller.sample_hz:,.0f} Hz",
                                    fg=MUTED if worst < 4 else ACCENT)
        self.m_loop.caption.configure(text=f"READ LOOP · WORST {worst:.0f} MS")

    def _paint_follow(self):
        self.follow_btn.configure(text="AUTO-SWITCH ON" if self.follow
                                  else "AUTO-SWITCH OFF")
        self.ui.restyle(self.follow_btn, BRAND if self.follow else RAISED,
                        BRAND_HI if self.follow else RAISED_HI)

    # ---------------------------------------------------------------- controls
    def toggle_follow(self):
        self.follow = not self.follow
        self._paint_follow()

    def toggle_pause(self):
        self.paused = not self.paused
        self.ui.restyle(self.pause_btn, ACCENT if self.paused else RAISED,
                        "#ffc866" if self.paused else RAISED_HI,
                        "#231800" if self.paused else TEXT)
        self.pause_btn.configure(text="RESUME" if self.paused else "PAUSE")

    def clear(self):
        if self.cur:
            self.cur.reset()
        self.tabs["timing"].refresh_all()

    # ---------------------------------------------------------------- export
    def export(self):
        m = self.cur
        if not m or not m.presses:
            messagebox.showinfo("Nothing to save", "Press some buttons first, then save.")
            return
        safe = "".join(ch if ch.isalnum() else "_"
                       for ch in self.names[self.selected]).strip("_")
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=f"cadence_{safe}.csv",
            filetypes=[("Spreadsheet data (.csv)", "*.csv"),
                       ("Readable report (.rpt)", "*.rpt"), ("All files", "*.*")])
        if not path:
            return
        try:
            if path.lower().endswith(".rpt"):
                self.write_report(path, m)
            else:
                self.write_csv(path, m)
        except OSError as e:
            messagebox.showerror("Could not save", str(e))
            return
        messagebox.showinfo("Saved", f"Saved {len(m.presses)} presses to\n{path}")

    def write_csv(self, path, m):
        """Full precision goes in the file even though the screen rounds it. The
        resolution column says how much of each figure is real."""
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["press", "time_s", "button", "gap_ms", "engine_ticks", "held_ms",
                        "stick_x", "stick_y", "sequence", "resolution_ms",
                        "observation_window_ms", "trigger_value"])
            for r in m.presses:
                w.writerow([r["n"], f"{r['t'] - self.t_start:.4f}", LABEL[r["key"]],
                            "" if r["gap"] is None else f"{r['gap']:.2f}",
                            fmt_ticks(r["gap"]),
                            "" if r["held"] is None else f"{r['held']:.2f}",
                            f"{r['stick'][0]:.2f}", f"{r['stick'][1]:.2f}", r["seq"],
                            f"{self.res:.2f}", f"{r.get('win', 0.0):.2f}",
                            "" if r.get("trig") is None else r["trig"]])

    def write_report(self, path, m):
        out = []
        add = out.append
        tab = self.tabs["timing"]
        held = [r["held"] for r in m.presses if r["held"] is not None]
        counts = {}
        for r in m.presses:
            counts[r["key"]] = counts.get(r["key"], 0) + 1
        ignored = [LABEL[k] for _, k, _ in BUTTONS if k in self.ignored]

        add(f"{APP_NAME.upper()}  session report")
        add("=" * 72)
        add(f"Saved            {time.strftime('%d %B %Y, %H:%M')}")
        add(f"Controller       {self.names[self.selected]}")
        info = self.poller.info.get(self.selected, {})
        if info:
            add(f"Device           {info.get('subtype', '?')}, "
                f"{'wireless' if info.get('wireless') else 'wired'}")
        add(f"Presses          {len(m.presses)} across {m.presses[-1]['seq']} sequences")
        add("Buttons used     " + ", ".join(f"{LABEL[k]} x{n}" for k, n in
                                            sorted(counts.items(), key=lambda kv: -kv[1])))
        if held:
            add(f"Hold time        {statistics.fmean(held):.1f} ms average, "
                f"{min(held):.1f} ms shortest")
        add("Not counted      " + (", ".join(ignored) if ignored else "nothing"))
        add(f"New sequence after {int(self.gap_ref[0])} ms of no presses")
        rep = self.poller.report_ms(self.selected)
        add("Pad report rate  " + (f"every {rep:.2f} ms ({1000 / rep:,.0f} Hz), measured"
                                   if rep else "not measured - assumed"))
        add(f"Resolution       +/- {self.res:.2f} ms  (nothing finer than this is real)")
        add(f"Read loop        {self.poller.sample_hz:,.0f} Hz, "
            f"worst single gap {self.poller.worst_poll_ms:.1f} ms")
        add(f"Engine tick      {T.TICK_MS:.2f} ms ({T.TICK_HZ:.0f} per second)")
        if tab.target_on:
            hits, total = m.target_hits(tab.target, tab.tol)
            add(f"Practice target  {tab.target:.0f} ms +/- {tab.tol:.0f} ms, "
                f"hit {hits} of the last {total}")
        add("")
        add("BY BUTTON PAIR   (typical is the median: the middle attempt, not the average)")
        add("-" * 72)
        add(f"{'Pair':<22}{'Typical':>12}{'Spread':>10}{'Fastest':>10}"
            f"{'Slowest':>10}{'Count':>8}")
        for (a, b), d in reversed(m.pairs.items()):
            vals = list(d)
            groups = m._split(vals)
            for note, part in ((("quick", groups[0]), ("delayed", groups[1]))
                               if groups else ((("", vals)),)):
                name = f"{LABEL[a]} -> {LABEL[b]}" + (f"  {note}" if note else "")
                sd = statistics.stdev(part) if len(part) > 1 else 0.0
                add(f"{name:<22}{statistics.median(part):>9.1f} ms{sd:>9.1f}"
                    f"{min(part):>9.1f}{max(part):>9.1f}{len(part):>8}")
        add("")
        add("EVERY PRESS")
        add("-" * 72)
        add(f"{'#':>6}  {'Time':>9}  {'Button':<7}{'Gap':>11}{'Ticks':>8}"
            f"{'Held':>11}  Left stick")
        seq = None
        for r in m.presses:
            if r["seq"] != seq:
                seq = r["seq"]
                add("")
                members = [x for x in m.presses if x["seq"] == seq]
                total = (members[-1]["t"] - members[0]["t"]) * 1000
                add(f"  Sequence {seq}  -  {len(members)} press"
                    f"{'' if len(members) == 1 else 'es'} in {total:.0f} ms")
            gap = "start" if r["gap"] is None else f"{r['gap']:.1f} ms"
            hold = "holding" if r["held"] is None else f"{r['held']:.1f} ms"
            add(f"{r['n']:>6}  {r['t'] - self.t_start:>8.3f}s  {LABEL[r['key']]:<7}"
                f"{gap:>11}{fmt_ticks(r['gap']):>8}{hold:>11}  {stick_arrow(*r['stick'])}")
        add("")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out))

    # ---------------------------------------------------------------- help
    def show_help(self):
        if self.help_win is not None and self.help_win.winfo_exists():
            self.help_win.lift()
            return
        ui = self.ui
        w = tk.Toplevel(self.root)
        self.help_win = w
        w.title("What the numbers mean")
        w.configure(bg=BG)
        hh = min(ui.px(900), self.root.winfo_screenheight() - ui.px(90))
        w.geometry(f"{ui.px(660)}x{hh}")
        dark_title_bar(w)
        tk.Label(w, text="What the numbers mean", bg=BG, fg=TEXT, font=ui.f(16, "semi"),
                 anchor="w").pack(fill="x", padx=22, pady=(18, 2))
        ui.button(w, "CLOSE", w.destroy).pack(side="bottom", pady=(8, 16))
        keys = tk.Frame(w, bg=BG)
        keys.pack(side="bottom", fill="x", padx=22, pady=(0, 4))
        tk.Label(keys, text="KEYS", bg=BG, fg=DIM, font=ui.f(8, "tight"),
                 anchor="w").pack(fill="x")
        tk.Label(keys, text=f"P pause   ·   C clear   ·   S save   ·   H this panel   ·   "
                            f"1-4 switch controller   ·   Esc or {self.panic_key} stop "
                            f"all macros",
                 bg=BG, fg=MUTED, font=ui.f(9), anchor="w").pack(fill="x")
        body = tk.Frame(w, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=(6, 8))
        res = self.res or 0.0
        entries = [
            ("Gap from last",
             "Time between the start of one press and the start of the next. This is the "
             "number the big readout shows, and the one that matters for flip timing."),
            ("Held for",
             "How long you kept that button down. Plenty of games treat a long press "
             "differently from a short one, up to some cap of their own."),
            ("Ticks",
             f"Games sample input once per engine tick. At the {T.TICK_HZ:.0f} Hz set "
             f"on the Timing tab that is once every {T.TICK_MS:.2f} ms, so gaps are "
             f"shown in whole ticks because that is all the engine sees. Two presses "
             f"{T.TICK_MS * 3:.0f} ms apart and {T.TICK_MS * 3 + 4:.0f} ms apart can "
             f"land on the same tick and play out identically. Set the rate to match "
             f"whatever you are playing."),
            ("Timing resolution",
             "Your controller sends its state on a fixed schedule, usually every 4 to "
             "8 ms, and nothing can be measured finer than that"
             + (f" - currently about ±{res:.1f} ms." if res else ".")
             + " Some pads send nothing at all while they sit still, so the rate can "
               "only be read while a stick or trigger is moving. The Controllers tab "
               "has a button that measures it properly."),
            ("Typical and Spread",
             "Typical is the middle value of your recent attempts, which ignores the odd "
             "fumble. Spread is how far your attempts wander from it. Getting spread "
             "down is what practice actually does."),
            ("quick and delayed",
             "The same two buttons often get used for two different things. A then A is "
             "both a quick repeat and a slow one. When your times fall into two "
             "clearly separate clusters they get listed as separate rows instead of "
             "blended into one meaningless average."),
            ("Target",
             "Pick a gap you are training, set how close counts, and the app tracks how "
             "many of your last 25 attempts landed inside that window. Amber means a "
             "hit, red a miss, and the row in the log is tinted to match."),
            ("Macros",
             "Bind a pad button to a stream of clicks or keypresses. Three independent "
             f"ways to stop one: the ARMED switch, the {self.panic_key} panic key which "
             "works even when Cadence is not the focused window, and shoving the mouse "
             "into a screen corner."),
        ]
        for i, (title, text) in enumerate(entries):
            tk.Label(body, text=title, bg=BG, fg=BRAND_HI, font=ui.f(11, "semi"),
                     anchor="w").pack(fill="x", pady=(10 if i else 0, 0))
            tk.Label(body, text=text, bg=BG, fg=MUTED, font=ui.f(9), anchor="w",
                     justify="left", wraplength=ui.px(600)).pack(fill="x")

    # ---------------------------------------------------------------- loop
    def tick(self):
        dirty = False
        try:
            while True:
                dirty |= self.handle(self.q.get_nowait())
        except queue.Empty:
            pass
        sel = self.selected
        latest = self.poller.latest.get(sel)
        connected = sel in self.connected
        tab = self.tabs.get(self.current_tab)
        if tab:
            tab.tick(latest, connected, dirty)
        now = time.perf_counter()
        if now - self.last_status > 0.06:
            self.last_status = now
            self.res = self.poller.resolution_ms(sel) if sel is not None else 0.0
            self.paint_metrics()
            self.paint_pills()
        # The reader thread must not be stalled by a collection it did not ask for, so
        # cyclic gc is off and run deliberately from here, where a pause costs a frame.
        if not gc.isenabled() and now - self.last_gc > GC_INTERVAL:
            self.last_gc = now
            gc.collect()
        self.tick_job = self.root.after(8, self.tick)

    def close(self):
        if self.tick_job is not None:
            try:
                self.root.after_cancel(self.tick_job)
            except Exception:
                pass
            self.tick_job = None
        self.anim.stop()
        self.poller.running = False
        self.engine.stop()
        if self.hotkey:
            self.hotkey.stop()
        self.ui.hide_tip()
        if sys.platform == "win32":
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
        self.root.destroy()


def open_reader():
    """Whichever controller backend this machine actually has."""
    if sys.platform == "win32":
        return XInputReader()
    from . import linux_input
    if not linux_input.available():
        raise RuntimeError("No controller found at /dev/input/js*. Plug one in, or "
                           "check your user is in the 'input' group.")
    return linux_input.LinuxJoystickReader()



def main():
    demo = "--demo" in sys.argv
    safe = "--no-output" in sys.argv       # run the UI without sending real input
    sys.setswitchinterval(0.0005)
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass
    root = tk.Tk()
    try:
        reader = DemoReader() if demo else open_reader()
    except RuntimeError as e:
        root.withdraw()
        messagebox.showerror(APP_NAME, f"{e}" + chr(10) * 2 +
                             "Run with --demo to look around without one.")
        return
    app = App(root, reader, demo, live_output=not safe)
    gc.collect()
    gc.freeze()
    gc.disable()
    try:
        root.mainloop()
    finally:
        gc.enable()
        del app
