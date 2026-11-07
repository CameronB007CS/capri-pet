"""
capri.py - a little desktop companion that just lives on your screen.
No AI, no API keys. Sprites are from the lachydotmcg/capri-desktop repo.

Setup (Windows):
    pip install pillow
    Put this file in your CAPRI folder (the one that has assets/sprites inside it)
    python capri.py

You can also point it at a sprites folder:
    python capri.py "C:\\path\\to\\sprites"

What she does:
    - floats around the bottom of your screen, blinks, wanders, dances
    - sometimes sits on the taskbar or lies down on it
    - falls asleep if you haven't moved the mouse for a while, wakes up when you do
    - drag her around (she dangles), click her to poke her, double click to dance
    - right click for the menu (including Quit)
"""

import os
import sys
import time
import random
import ctypes
import tkinter as tk

from PIL import Image, ImageOps, ImageTk

# ---------------------------------------------------------------- settings --
SCALE = 0.5            # sprite size. 0.5 = half size (a 384px tall frame becomes 192px)
HOVER = 30             # how many px she floats above the taskbar when idle
WALK_SPEED = 70        # px per second
SLEEP_AFTER = 120      # seconds of no mouse movement before she falls asleep
FPS_TICK = 33          # ms between updates (~30 updates a second)
KEY = "#010203"        # colour that becomes see-through. Pick something not in the art.
ALPHA_CUTOFF = 100     # pixels with alpha under this are treated as see-through

# name -> (frame width in px, animation fps)
# frame widths were worked out from the sheets: most are 240 wide,
# perch sheets are 196 wide, laydown sheets are 372 wide.
SHEETS = {
    "idle": (240, 12), "blink": (240, 14), "walk": (240, 12),
    "sleep": (240, 10), "wake": (240, 14), "dance": (240, 14),
    "grin": (240, 12), "dangle": (240, 14), "arrive": (240, 16),
    "leave": (240, 16), "glitch": (240, 16),
    "perch": (196, 12), "perch_blink": (196, 14),
    "laydown": (372, 12), "laydown_blink": (372, 14), "laydown_sleep": (372, 12),
}

# sheets that come with a pre-made "_flipped" version for the other direction
HAS_FLIPPED = {"perch", "perch_blink", "laydown", "laydown_blink", "laydown_sleep"}

# which blink sheet goes with which base animation
BLINKS = {"idle": "blink", "perch": "perch_blink", "laydown": "laydown_blink"}

BIGGEST_W = 372
BIGGEST_H = 384


# ------------------------------------------------------------------ sheets --
class Sheet:
    """One horizontal strip of frames, loaded lazily, cached as tk images."""

    def __init__(self, folder, name, facing):
        fw, self.fps = SHEETS[name]
        flipped_file = name in HAS_FLIPPED and facing == -1
        filename = name + ("_flipped" if flipped_file else "") + ".png"
        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            raise FileNotFoundError("missing sprite: " + path)

        img = Image.open(path).convert("RGBA")
        w, h = img.size
        self.n = max(1, w // fw)
        mirror = facing == -1 and name not in HAS_FLIPPED

        self.frames = []
        bottom = 0
        for i in range(self.n):
            f = img.crop((i * fw, 0, (i + 1) * fw, h))
            if mirror:
                f = ImageOps.mirror(f)
            alpha = f.split()[3].point(lambda a: 255 if a >= ALPHA_CUTOFF else 0)
            box = alpha.getbbox()
            if box:
                bottom = max(bottom, box[3])
            # flatten onto the key colour so the transparent colour trick works
            bg = Image.new("RGB", f.size, KEY)
            bg.paste(f.convert("RGB"), (0, 0), alpha)
            new_size = (max(1, int(fw * SCALE)), max(1, int(h * SCALE)))
            self.frames.append(bg.resize(new_size, Image.NEAREST if SCALE >= 1 else Image.LANCZOS))

        # how many px of empty space sit under her feet, so we can line her up
        self.pad = int((h - (bottom or h)) * SCALE)
        self.tk_frames = [None] * self.n

    def frame(self, i):
        i = max(0, min(self.n - 1, int(i)))
        if self.tk_frames[i] is None:
            self.tk_frames[i] = ImageTk.PhotoImage(self.frames[i])
        return self.tk_frames[i]


# --------------------------------------------------------------- the pet -----
class Capri:
    def __init__(self, folder):
        self.folder = folder
        self.root = tk.Tk()
        self.root.title("Capri")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", KEY)
        except tk.TclError:
            print("note: transparent window colour isn't supported on this OS, "
                  "you'll see a solid background (this is only meant for Windows)")
        self.root.config(bg=KEY)

        self.W = int(BIGGEST_W * SCALE)
        self.H = int(BIGGEST_H * SCALE)
        self.canvas = tk.Canvas(self.root, width=self.W, height=self.H, bg=KEY,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.img_id = self.canvas.create_image(self.W // 2, self.H, anchor="s")

        self.sheets = {}
        self.facing = random.choice([-1, 1])

        # every monitor's usable area (excludes taskbars)
        self.monitors = self.get_monitors()
        self.set_monitor(self.monitor_at(0, 0))      # start on the main monitor

        # position (cx = horizontal centre, by = where her feet/bottom are)
        self.cx = random.randint(int(self.left + self.W), int(self.right - self.W))
        self.by = float(self.float_by)

        self.state = "arrive"
        self.anim = "arrive"
        self.loop = False
        self.done = None
        self.t = 0.0
        self.state_end = 0.0
        self.next_blink = time.time() + random.uniform(3, 7)
        self.walk_target = self.cx
        self.vy = 0.0

        self.held = False
        self.grab = (0, 0)
        self.press_pos = (0, 0)
        self.moved = False

        self.last_pointer = self.root.winfo_pointerxy()
        self.last_move = time.time()

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Dance", command=lambda: self.go("dance"))
        self.menu.add_command(label="Grin", command=lambda: self.go("grin"))
        self.menu.add_command(label="Sit on the taskbar", command=lambda: self.go("perch"))
        self.menu.add_command(label="Lie down", command=lambda: self.go("laydown"))
        self.menu.add_command(label="Go to sleep", command=lambda: self.go("sleep"))
        self.menu.add_command(label="Glitch", command=lambda: self.go("glitch"))
        self.menu.add_command(label="Turn around", command=self.turn_around)
        self.menu.add_command(label="Next monitor", command=self.next_monitor)
        self.menu.add_separator()
        self.menu.add_command(label="Quit", command=self.quit)

        c = self.canvas
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Double-Button-1>", lambda e: self.go("dance"))
        c.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))

        self.play("arrive", loop=False, done=lambda: self.go("idle"))
        self.last = time.perf_counter()
        self.place()
        self.root.after(FPS_TICK, self.tick)

    # ------------------------------------------------------------ helpers --
    def get_monitors(self):
        """Work areas (screen minus taskbar) of every monitor, left to right."""
        if sys.platform == "win32":
            try:
                import ctypes.wintypes as wt

                class MONITORINFO(ctypes.Structure):
                    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                                ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

                Proc = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HMONITOR, wt.HDC,
                                          ctypes.POINTER(wt.RECT), wt.LPARAM)
                user32 = ctypes.windll.user32
                user32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), Proc, wt.LPARAM]
                user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFO)]
                found = []

                def cb(hmon, hdc, rect, lparam):
                    mi = MONITORINFO()
                    mi.cbSize = ctypes.sizeof(MONITORINFO)
                    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
                    w = mi.rcWork
                    found.append((w.left, w.top, w.right, w.bottom))
                    return 1

                user32.EnumDisplayMonitors(None, None, Proc(cb), 0)
                if found:
                    return sorted(found)
            except Exception:
                pass
        return [(0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 40)]

    def monitor_at(self, x, y):
        """Index of the monitor closest to a point."""
        best, best_d = 0, None
        for i, (l, t, r, b) in enumerate(self.monitors):
            dx = max(l - x, 0, x - r)
            dy = max(t - y, 0, y - b)
            d = dx * dx + dy * dy
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def set_monitor(self, i):
        """Make monitor i the one she lives on (walk limits, taskbar height)."""
        self.mon = i
        self.left, self.top, self.right, self.bottom = self.monitors[i]
        self.ground = self.bottom                    # taskbar top edge
        self.float_by = self.ground - HOVER

    def next_monitor(self):
        i = (self.mon + 1) % len(self.monitors)
        self.set_monitor(i)
        self.cx = (self.left + self.right) / 2
        self.by = float(self.float_by)
        if self.state in ("walk",):
            self.go("idle")

    def sheet(self, name):
        key = (name, self.facing)
        if key not in self.sheets:
            self.sheets[key] = Sheet(self.folder, name, self.facing)
        return self.sheets[key]

    def play(self, name, loop=True, done=None):
        self.anim = name
        self.loop = loop
        self.done = done
        self.t = 0.0

    def place(self):
        sh = self.sheet(self.anim)
        # push the picture down so her lowest pixel sits on 'by'
        self.canvas.coords(self.img_id, self.W // 2, self.H + sh.pad)
        self.canvas.itemconfig(self.img_id, image=sh.frame(self.t))
        x = int(self.cx - self.W / 2)
        y = int(self.by - self.H)
        self.root.geometry("%dx%d+%d+%d" % (self.W, self.H, x, y))

    def clamp_x(self):
        self.cx = max(self.left + self.W / 2, min(self.right - self.W / 2, self.cx))

    def turn_around(self):
        self.facing = -self.facing

    # -------------------------------------------------------------- states --
    def go(self, state):
        """Switch to a new state and set up its animation."""
        if self.state == "leave":
            return
        now = time.time()
        prev = self.state
        self.state = state
        if state == "idle":
            self.play("idle")
            self.state_end = now + random.uniform(4, 9)
        elif state == "walk":
            lo, hi = int(self.left + self.W / 2), int(self.right - self.W / 2)
            self.walk_target = random.randint(lo, hi)
            if abs(self.walk_target - self.cx) < 80:
                return self.go("idle")
            self.facing = 1 if self.walk_target > self.cx else -1
            self.play("walk")
        elif state == "dance":
            self.play("dance")
            self.state_end = now + random.uniform(6, 10)
        elif state == "grin":
            self.play("grin")
            self.state_end = now + random.uniform(2.5, 4)
        elif state == "perch":
            self.play("perch")
            self.state_end = now + random.uniform(15, 40)
        elif state == "laydown":
            self.play("laydown")
            self.state_end = now + random.uniform(15, 40)
        elif state == "sleep":
            self.play("laydown_sleep" if prev == "laydown" else "sleep")
            self.sleep_started = now
        elif state == "wake":
            self.play("wake", loop=False, done=lambda: self.go("idle"))
        elif state == "glitch":
            self.play("glitch", loop=False, done=lambda: self.go("idle"))
        elif state == "held":
            self.play("dangle")
        elif state == "fall":
            self.vy = 0.0
            self.play("idle")

    def pick_next(self):
        options = [("walk", 45), ("dance", 10), ("grin", 10),
                   ("perch", 15), ("laydown", 10), ("idle", 10)]
        names = [o[0] for o in options]
        weights = [o[1] for o in options]
        self.go(random.choices(names, weights)[0])

    def quit(self):
        self.state = "leave"
        self.play("leave", loop=False, done=self.root.destroy)

    # --------------------------------------------------------------- mouse --
    def on_press(self, e):
        if self.state == "leave":
            return
        self.held = True
        self.moved = False
        self.press_pos = (e.x_root, e.y_root)
        self.grab = (e.x_root - self.cx, e.y_root - self.by)
        self.was_sleeping = self.state == "sleep"

    def on_drag(self, e):
        if not self.held:
            return
        if not self.moved:
            if abs(e.x_root - self.press_pos[0]) + abs(e.y_root - self.press_pos[1]) < 6:
                return
            self.moved = True
            self.go("held")
        m = self.monitor_at(e.x_root, e.y_root)
        if m != self.mon:
            self.set_monitor(m)
        self.cx = e.x_root - self.grab[0]
        self.by = e.y_root - self.grab[1]
        self.clamp_x()
        self.by = min(self.by, self.ground)

    def on_release(self, e):
        if not self.held:
            return
        self.held = False
        if self.moved:
            self.go("fall")
        elif self.state == "sleep":
            self.go("wake")
        else:
            self.go("grin")      # just a poke

    # ---------------------------------------------------------------- loop --
    def tick(self):
        try:
            self.step()
        except FileNotFoundError as err:
            print(err)
            self.root.destroy()
            return
        self.root.after(FPS_TICK, self.tick)

    def step(self):
        now_p = time.perf_counter()
        dt = min(now_p - self.last, 0.1)
        self.last = now_p
        now = time.time()

        # keep track of mouse movement for the sleep timer
        ptr = self.root.winfo_pointerxy()
        if ptr != self.last_pointer:
            self.last_pointer = ptr
            self.last_move = now

        self.logic(dt, now)
        self.advance(dt)
        self.place()

        # windows sometimes drops topmost, poke it every so often
        if int(now) % 5 == 0:
            self.root.attributes("-topmost", True)

    def logic(self, dt, now):
        s = self.state

        # things that put her to sleep / wake her up
        if s in ("idle", "walk", "perch", "laydown", "grin", "dance"):
            if now - self.last_move > SLEEP_AFTER:
                self.go("sleep")
                return
        if s == "sleep":
            if now - self.last_move < 1.0 and now - self.sleep_started > 2:
                if self.anim == "laydown_sleep":
                    self.go("laydown")
                else:
                    self.go("wake")
                return

        # floating states drift to their hover height, sitting ones to the taskbar
        on_ground = s in ("perch", "laydown") or self.anim == "laydown_sleep"
        target = self.ground if on_ground else self.float_by
        if s in ("idle", "walk", "dance", "grin", "perch", "laydown", "sleep", "wake"):
            if abs(self.by - target) > 1:
                step = 260 * dt
                self.by += max(-step, min(step, target - self.by))
            else:
                self.by = target

        if s == "walk":
            d = self.walk_target - self.cx
            if abs(d) <= WALK_SPEED * dt:
                self.cx = self.walk_target
                self.go("idle")
            else:
                self.cx += WALK_SPEED * dt * (1 if d > 0 else -1)
        elif s == "fall":
            self.vy += 2200 * dt
            self.by += self.vy * dt
            if self.by >= self.float_by:
                self.by = self.float_by
                self.go("idle")
        elif s in ("idle", "dance", "grin", "perch", "laydown") and now >= self.state_end:
            if s == "idle":
                self.pick_next()
            else:
                self.go("idle")

        # random blinking
        base = self.anim
        if base in BLINKS and self.loop and now >= self.next_blink:
            self.next_blink = now + random.uniform(3, 8)
            self.play(BLINKS[base], loop=False, done=lambda b=base: self.back_to(b))

    def back_to(self, name):
        if self.state in ("idle", "perch", "laydown"):
            self.play(name)

    def advance(self, dt):
        sh = self.sheet(self.anim)
        self.t += dt * sh.fps
        if self.t >= sh.n:
            if self.loop:
                self.t %= sh.n
            else:
                self.t = sh.n - 1
                cb, self.done = self.done, None
                if cb:
                    cb()

    def run(self):
        self.root.mainloop()


# ------------------------------------------------------------------ main -----
def find_sprites():
    if len(sys.argv) > 1:
        return sys.argv[1]
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "assets", "sprites"), os.path.join(here, "sprites"), here):
        if os.path.exists(os.path.join(p, "idle.png")):
            return p
    return os.path.join(here, "assets", "sprites")


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # real pixel coords on hi-dpi screens
        except Exception:
            pass
    folder = find_sprites()
    if not os.path.exists(os.path.join(folder, "idle.png")):
        print("couldn't find the sprites folder (looked for idle.png in %s)" % folder)
        print("put capri.py next to the assets folder, or run: python capri.py <path to sprites>")
        sys.exit(1)
    Capri(folder).run()
