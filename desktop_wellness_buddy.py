"""Desktop Wellness Buddy: a local, office-safe wellbeing companion.

The buddy walks, pauses, shows short prompts, and offers small reset reminders.
It runs locally with no network calls, API keys, or company-data access.

 Pop ups (weekdays 8:00 to 17:30):
  fixed check-ins at 9:00, 12:30 and 15:30; water at 10:30 and 14:00; stretch breaks at 11:30 and 15:00.
Interact: click = pet, double click = joke, drag = move her, right click = menu and moods.
Starts when you sign in (Install_Skye.ps1), hides while the PC is locked, resets timers on unlock or wake.
No internet, no API key, no company data. Your photo stays on this computer.

Run by hand: python desktop_wellness_buddy.py   (flags: --pomodoro --solid --make-assets)
"""
import ctypes
import math
import os
import random
import socket
import sys
import time
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "desktop_wellness_buddy.log")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

sys.path.insert(0, HERE)
import buddy_art  # noqa: E402

if "--make-assets" in sys.argv:
    print("Icon saved:", buddy_art.save_icon())
    sys.exit(0)

import tkinter as tk  # noqa: E402
from PIL import Image, ImageOps, ImageTk  # noqa: E402

SOLID = "--solid" in sys.argv
POMODORO = "--pomodoro" in sys.argv
WATER_MIN = 60
BREAK_MIN = 90
BREAK_LEN = 5
WORK_START, WORK_END = 8.0, 17.5
# Fixed workday cadence: three check-ins, two water reminders, and two stretch breaks.
# Keeping these events on a wall-clock schedule prevents overlapping random timers.
SCHEDULE = (
    (9, 0, "checkin"),
    (10, 30, "water"),
    (11, 30, "break"),
    (12, 30, "checkin"),
    (14, 0, "water"),
    (15, 0, "break"),
    (15, 30, "checkin"),
)
W, H = 360, 290
KEY = "#fe00fe"
# The walk sheet holds one stride pose repeated (same leg forward) plus passing poses.
# Use the passing poses with a sway, so one leg is never always in front.
WALK_SEQ = [1, 3, 5, 3]
MOODS = ("happy", "hyper", "sassy", "sleepy", "zen", "proud")
MOOD_EYE = {"happy": "open", "hyper": "sparkle", "sassy": "sass", "sleepy": "sleepy", "zen": "zen", "proud": "happy"}
MOOD_FLAP = {"happy": 2, "hyper": 1, "sassy": 2, "sleepy": 4, "zen": 3, "proud": 2}  # ticks per frame
MOOD_BOB = {"happy": 5, "hyper": 9, "sassy": 4, "sleepy": 2, "zen": 3, "proud": 6}
MOOD_WANDER = {"happy": 110, "hyper": 190, "sassy": 70, "sleepy": 0, "zen": 40, "proud": 120}


def clean_walk_frame(raw):
    """Keep the largest connected avatar shape and discard neighboring pose fragments."""
    alpha = raw.getchannel("A")
    sw, sh = max(80, raw.width // 4), max(120, raw.height // 4)
    small = alpha.resize((sw, sh), Image.Resampling.BILINEAR)
    px = small.load()
    seen = set()
    components = []
    for sy in range(sh):
        for sx in range(sw):
            if (sx, sy) in seen or px[sx, sy] < 50:
                continue
            stack, seen_count = [(sx, sy)], 0
            left = right = sx
            top = bottom = sy
            seen.add((sx, sy))
            while stack:
                x, y = stack.pop()
                seen_count += 1
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < sw and 0 <= ny < sh and (nx, ny) not in seen and px[nx, ny] >= 50:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            components.append((seen_count, left, top, right, bottom))
    if not components:
        return raw
    _, left, top, right, bottom = max(components)
    scale_x, scale_y = raw.width / sw, raw.height / sh
    left = max(0, int(left * scale_x) - 12)
    top = max(0, int(top * scale_y) - 12)
    right = min(raw.width, int((right + 1) * scale_x) + 12)
    bottom = min(raw.height, int((bottom + 1) * scale_y) + 12)
    return raw.crop((left, top, right, bottom))

def align_poses(poses, cw=190, ch=170, target_h=164):
    """Put every pose on one fixed canvas: same height, feet on the same line, and the head/torso
    on the same vertical axis, so frames do not jitter or slide when they change."""
    out = []
    for im in poses:
        a = im.getchannel("A").point(lambda v: 255 if v > 128 else 0)
        bb = a.getbbox()
        if not bb:
            out.append(im)
            continue
        fig = im.crop(bb)
        s = target_h / fig.height
        fig = fig.resize((max(1, round(fig.width * s)), target_h), Image.Resampling.LANCZOS)
        fa = fig.getchannel("A").point(lambda v: 255 if v > 128 else 0)
        top_h = int(fig.height * 0.35)  # head and shoulders
        px = fa.load()
        xs = [x for y in range(0, top_h, 2) for x in range(fig.width) if px[x, y]]
        cx = sum(xs) / len(xs) if xs else fig.width / 2
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        canvas.paste(fig, (int(round(cw / 2 - cx)), ch - 1 - target_h), fig)
        out.append(canvas)
    return out


def _load_name():
    """Name used in messages. Edit the local config.json; defaults to Buddy."""
    try:
        import json
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
            return str(json.load(f).get("name", "Buddy"))[:30]
    except Exception:
        return "Buddy"


USER_NAME = _load_name()

WATER = [f"Water time, {USER_NAME}. Sip now, spreadsheet later.",
         "Hydration check. Even servers need cooling.",
         "Glug glug. That is a data refresh for your body.",
         "Your brain is mostly water. Top it up."]
BREAK = ["Stretch break! Stand up, roll your shoulders, look far away for 20 seconds.",
         "Chair hug is over. Walk for 5 minutes, I will wait."]
BACK = ["Break over. Pick one small step and start there.", "Welcome back. One thing, 15 minutes."]
CHECKIN = ["Quick check in: how are you holding up?", "Pause. How is your energy right now?",
           "Beep boop. Mood check. How are we doing?"]
JOKES = [
    "Why did the analyst bring a ladder? To reach the next level of insight.",
    "I told my dashboard a joke. It did not refresh.",
    "SQL walks into a bar, sees two tables and asks: can I join you?",
    "My forecast is 100% accurate, as long as nothing happens.",
    "Correlation is not causation, but it does get invited to every meeting.",
    "Why did the churn rate go to therapy? Separation issues.",
    "I would tell you a UDP joke, but you might not get it.",
    "Why did the dashboard take a break? It needed a refresh.",
    "My meeting could have been an email. My email could have been a calendar invite. Hello.",
    "A good analyst is like a tea bag. You find out their strength in hot water.",
    "There are 10 kinds of people: those who read binary and those who do not.",
    "Why was the spreadsheet calm? It had everything in its cells under control.",
    "I tried to organize a data party. Nobody could agree on the schema.",
    "Why did the average go to the party alone? It was mean.",
    "Why did the analyst bring a pencil to the meeting? For a sharp point.",
    "I asked the backlog to relax. It said it had too many open issues.",
    "Why was the KPI so calm? It had already found its baseline.",
    "My data set walked into a cafe. It wanted a little more context.",
    "Why did the query take a nap? It was waiting on a join.",
    "I tried to make a pie chart laugh. It was already in a good slice of mind.",
    "The dashboard said it needed space. I gave it a new tab.",
    "Why did the metric bring an umbrella? It expected a forecast.",
]
PEP = [
    "Small steps still count as moving forward.",
    "You do not need all the answers today. You need the next step.",
    "Done and shared beats perfect and hidden.",
    "Hard day? Breathe. You have handled harder ones.",
    "One focused 15 minutes beats an hour of worry.",
    "You lead a team and learn on the side. That is a lot. Be kind to yourself.",
    "Curiosity is your superpower. Keep asking the good question.",
    "Eloquent word of the day: tenacious. That is you.",
    "You can be serious about the work without being harsh with yourself.",
    "A pause is part of the process, not evidence that you are behind.",
    "Reduce the scope until starting feels easy, then let momentum help.",
    "You are allowed to ask for clarity before accepting more work.",
    "Protect the quality of your attention; it is one of your best tools.",
    "Progress can look like deleting one unnecessary step.",
    "The next version only needs to be clearer than the last one.",
]
ARRIVAL_THOUGHTS = [
    "New position, same mission: make the next useful decision.",
    "What is the one thing you want future-you to be glad you finished today?",
    "Before you add another task, decide what can leave the list.",
    "A strong analysis starts with a precise question, not a giant spreadsheet.",
    "What pattern is hiding in plain sight because everyone is used to it?",
    "If the recommendation is not actionable, it is not finished yet.",
    "Name the audience before you polish the message.",
    "What would change your mind? Write that down before reviewing more data.",
    "Turn the messy problem into three smaller questions.",
    "The best next step is usually smaller than the one your anxiety invented.",
    "Look for the repeatable process behind today’s one-time win.",
    "What is the business consequence, not just the metric movement?",
    "Separate signal, noise, and the decision they support.",
    "One clear chart beats five charts that require a tour guide.",
    "Ask who owns the next action before the meeting ends.",
    "What can you test this week instead of debating for another week?",
    "A forecast is a decision aid, not a promise carved in stone.",
    "Make the risk visible while it is still cheap to address.",
    "What did you learn today that the team should not have to relearn?",
    "Protect your focus like a scarce business resource.",
    "Breathe in for 4, hold for 4, out for 6. Repeat twice.",
    "Try boxed breathing: in 4, hold 4, out 4, hold 4.",
    "Drop your shoulders. Unclench your jaw. Take one slow breath.",
    "Before the next task: inhale gently, exhale longer, then choose one step.",
    "Your nervous system is part of the workflow. Give it 30 seconds to reset.",
    "Pause before reacting: breathe in, breathe out, then write the answer.",
    "Name five things you can see, then return to the next useful action.",
    "A two-minute reset is not lost time if it restores good judgment.",
    "Try physiological sighs: two small inhales, one long slow exhale. Repeat twice.",
    "Unclench your hands, lower your shoulders, and let your eyes soften for ten seconds.",
    "If the task feels huge, write only the first verb: open, compare, draft, or send.",
    "Use a 5-4-3-2-1 reset: five things you see, four you feel, three you hear, two you smell, one you taste.",
    "Give the worry a parking lot: write it down, schedule a review, return to the task.",
    "Try a ninety-second reset before the next decision: breathe, name the facts, choose one action.",
    "You do not need to solve the whole system to improve one handoff today.",
    "Stand up, look across the room, and let your body remember that the screen is not the whole world.",
]
CONTEXT_LINES = {
    "water": [
        "Water first, then decide whether this task still deserves your attention.",
        "Take three sips and ask: what is the smallest useful next step?",
        "Hydrate, lower your shoulders, and return to one clearly named outcome.",
    ],
    "break": [
        "Step away for five minutes. Breathe in 4, hold 4, out 6.",
        "Try boxed breathing: in 4, hold 4, out 4, hold 4, then stretch.",
        "A real break protects the quality of the decision you make next.",
        "Look away from the screen, unclench your jaw, and let your eyes rest.",
        "Try two physiological sighs: a small inhale, a second top-up inhale, then a long exhale.",
        "Walk to the next room and back without taking your phone. Let the reset be boring.",
        "Stretch your hands and forearms; your keyboard does not get to keep the whole afternoon.",
    ],
    "checkin": [
        "Quick check: what is your energy level, and what task matches it?",
        "Name the pressure clearly: urgent, important, or safe to drop?",
        "Separate facts, assumptions, and the decision you need to make.",
        "If you feel stuck, choose one action that takes less than 15 minutes.",
        "Check your body before your inbox: jaw, shoulders, breath, and energy.",
        "Do you need information, permission, time, or a smaller task? Name the real need.",
    ],
    "joke": [
        "A tiny reset is allowed. After the laugh, close one open loop.",
        "Your next best move may be simpler than the spreadsheet suggests.",
        "Use the lighter moment to choose one priority, not five new tabs.",
    ],
    "pep": [
        "Write the conclusion first, then gather only the evidence that earns its place.",
        "Make the problem smaller before trying to make the answer bigger.",
        "Future-you needs a clear next step more than a perfect plan.",
        "Make the next action so obvious that tired-you can start it without rereading this.",
        "A useful draft creates something to react to; an empty page creates pressure.",
    ],
    "back": [
        "Welcome back. Re-enter gently: choose one task and one visible finish line.",
        "Before reopening everything, decide what can stay closed today.",
        "Take one breath, review the next action, and protect your attention.",
        "Restart with a low-friction task: open the file, write the heading, or name the decision.",
        "Do not repay the break with panic. Re-enter at a human pace.",
    ],
}
LINES = {  # Short, useful prompts in the buddy's voice
    "happy": [
        "What is the one outcome that would make today feel successful?",
        "Capture the next smallest step before opening another tab.",
        "You do not need a perfect plan. Choose the next test.",
        "What can you finish, not merely continue, in the next 20 minutes?",
        "Write the headline first. The details can earn their place underneath it.",
        "What would make this easier for the next person who touches it?",
        "Turn one observation into a measurable question.",
        "Before adding work, ask what can be simplified or removed.",
        "What is the evidence—not the feeling—that this is the right priority?",
    ],
    "hyper": [
        "Good energy. Aim it at one 15-minute win.",
        "Write the decision first, then research only what supports it.",
        "Which single move would create the most leverage right now?",
        "Put the idea in a one-sentence testable form.",
        "You have enough tabs. Choose one source and extract the decision.",
        "Separate interesting from important before you spend more time.",
        "What is the fastest safe experiment you can run today?",
        "If everything feels urgent, identify the consequence of delay.",
        "Use the energy to close a loop, not open five more.",
    ],
    "sassy": [
        "Is this urgent, important, or safe to drop? Be honest.",
        "What would happen if you did less—but finished the right thing?",
        "Name the assumption before you defend the recommendation.",
        "Is this a real blocker, or an uncomfortable decision?",
        "What would an executive ask before approving this?",
        "Which detail is distracting from the actual business outcome?",
        "Are you solving the root cause or decorating the symptom?",
        "What is the strongest argument against your current view?",
        "If the answer is no, what would you do next?",
    ],
    "sleepy": [
        "Close one loop, write tomorrow's first step, then stop.",
        "Protect tomorrow: choose your shutdown time now.",
        "If this can wait, park it visibly instead of carrying it mentally.",
        "Do the smallest useful version and leave a clear handoff note.",
        "Your brain is not a task manager. Put the task somewhere trusted.",
        "What can you deliberately not solve tonight?",
        "Review the calendar, choose tomorrow's first action, then log off.",
        "A clean stopping point is progress too.",
        "Do not trade tomorrow's focus for tonight's anxiety.",
    ],
    "zen": [
        "One thing at a time. What deserves your full attention for 15 minutes?",
        "Separate the facts, the assumptions, and the decision.",
        "Breathe once, then make the smallest reversible decision.",
        "What do you know, what do you suspect, and what must you verify?",
        "Make the problem smaller before trying to make the answer bigger.",
        "Which constraint is real, and which one are you assuming?",
        "What would change your mind? Write it down before reviewing more data.",
        "Find the pattern, then check whether one exception breaks it.",
        "Clarity first. Speed comes after the question is precise.",
        "Breathe in for 4, hold for 4, out for 6. Then choose one next step.",
        "Try one boxed breath: in 4, hold 4, out 4, hold 4.",
        "Drop your shoulders and let the exhale take longer than the inhale.",
    ],
    "proud": [
        "Record what worked. That is how a win becomes a repeatable playbook.",
        "Turn today's lesson into one sentence you can reuse next week.",
        "You made progress. What evidence will prove it to your future self?",
        "What did you learn that the team should not have to relearn?",
        "Capture the decision, owner, and next checkpoint while it is fresh.",
        "Which part of today's work created value beyond today?",
        "Name one behavior worth repeating and one worth retiring.",
        "What did you make clearer for someone else?",
        "A good result is useful. A documented good process is scalable.",
    ],
}
PET_LINES = {
    "happy": ["Good. Now make the next step visible.", "That is a useful win."],
    "hyper": ["Pick one lane, then go.", "Energy deployed. Nicely done."],
    "sassy": ["I will accept that answer—for now.", "Exactly. Less noise, more signal."],
    "sleepy": ["Good stopping point.", "Future-you says thank you."],
    "zen": ["Clear enough to continue.", "That is the right pace."],
    "proud": ["Save that as a pattern.", "Evidence captured. Excellent."],
}
GREAT = ["Love that for you! Bank that energy.", "Yes! Protect that feeling with a snack."]
MEH = ["Meh is allowed. Here is a joke to fix it.", "Meh happens. Water, stretch, joke. In that order."]
STRESSED = ["Breathe: in for 4, hold 4, out for 6. Do it twice. Then pick ONE small thing.",
            "Stress is just energy with no plan. Pick one tiny step and I will cheer."]


def locked():
    """True when the Windows lock screen is showing."""
    try:
        u = ctypes.windll.user32
        h = u.OpenInputDesktop(0, False, 0x0100)
        if not h:
            return True
        ok = u.SwitchDesktop(h)
        u.CloseDesktop(h)
        return not ok
    except Exception:
        return False


def single_instance():
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 47653))  # local only: just an "already running" flag
    except OSError:
        return None
    return s


def ease_out_back(p):
    c1, c3 = 1.2, 2.2
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


class DesktopWellnessBuddy:
    def __init__(self):
        self.root = tk.Tk()
        r = self.root
        r.title("Desktop Wellness Buddy")
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        bg = "#eef7ff" if SOLID else KEY
        r.config(bg=bg)
        if not SOLID:
            try:
                r.attributes("-transparentcolor", KEY)
            except tk.TclError:
                pass
        self.cv = tk.Canvas(r, width=W, height=H, bg=bg, highlightthickness=0)
        self.cv.pack()
        try:
            r.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.avatar =ImageTk.PhotoImage(buddy_art.make_avatar(72).resize((64, 64)))
        self.avatar_sprite = buddy_art.make_avatar(112)
        walk_path = os.path.join(HERE, "avatar_walk.png")
        self.avatar_frames = []
        if os.path.exists(walk_path):
            sheet = Image.open(walk_path).convert("RGBA")
            frame_w = sheet.width // 6
            for i in range(6):
                left = max(0, i * frame_w - 80)
                right = min(sheet.width, (i + 1) * frame_w + 80)
                raw = sheet.crop((left, 0, right, sheet.height))
                raw = clean_walk_frame(raw)
                bbox = raw.getchannel("A").getbbox()
                if not bbox:
                    continue
                left, top, right, bottom = bbox
                pad = 24
                clipped = Image.new("RGBA", (right - left + 2 * pad, bottom - top + 2 * pad), (0, 0, 0, 0))
                clipped.alpha_composite(raw.crop((left, top, right, bottom)), (pad, pad))
                self.avatar_frames.append(clipped)
        self.front_pose = None  # front facing standing pose, used whenever she stops walking
        front_path = os.path.join(HERE, "avatar.png")
        if os.path.exists(front_path):
            try:
                fp = Image.open(front_path).convert("RGBA")
                fp.putalpha(fp.getchannel("A").point(lambda v: 255 if v > 200 else 0))  # drop the soft glow
                bb = fp.getchannel("A").getbbox()
                if bb:
                    self.front_pose = align_poses([fp.crop(bb)])[0]
            except Exception as ex:
                log(f"front pose unavailable: {ex}")
        if self.avatar_frames:
            self.avatar_frames = align_poses(self.avatar_frames)
        self.avatar_tk = None
        self.avatar_x = W / 2
        self.avatar_dir = 1
        self.walk_phase = 0.0
        self.walk_in_elapsed = 0
        self.entrance_alpha = 0.0
        self.avatar_action = "stroll"
        self.avatar_action_until = 0
        self.action_start = 0
        self.perform_mood = "happy"
        self.perform_start = 0
        self.mood_poses = {}  # optional own pictures: pose_zen.png, pose_hyper.png ... in this folder
        for mname in MOODS:
            pp = os.path.join(HERE, f"pose_{mname}.png")
            if os.path.exists(pp):
                try:
                    pim = Image.open(pp).convert("RGBA")
                    pim.putalpha(pim.getchannel("A").point(lambda v: 255 if v > 200 else 0))
                    pbb = pim.getchannel("A").getbbox()
                    if pbb:
                        self.mood_poses[mname] = align_poses([pim.crop(pbb)])[0]
                except Exception as ex:
                    log(f"pose {mname} unavailable: {ex}")
        self.next_action = 200
        self.arrival_pending = True
        self.quit_confirm_until = 0.0
        self.cur_img = None
        self.sw, self.sh = r.winfo_screenwidth(), r.winfo_screenheight()
        self.home_x = float((self.sw // 3) - W // 2)
        self.home_y = float(self.sh - H - 60)
        self.mid_x = float(self.sw // 2 - W // 2)
        self.mid_y = float(self.sh * 0.28)
        self.x, self.y = -float(W), float(self.sh - H - 60)
        self.t = 0
        self.d = 1
        self.state = "walk_in"
        self.p = 0.0
        self.kind = None
        self.text, self.buttons = "", []
        self.talk_start = 0.0
        self.chirp_until = 0.0
        self.away_ticks = 0
        self.st, self.stv = 0.0, 0.0  # stretch and its spring velocity
        self.tilt = 0.0
        self.hop_t = -1
        self.next_hop = 150
        self.blink_t = 0
        self.next_blink = 80
        self.next_mutter = 120
        self.last_line = None
        self.pets = []
        self.happy_until = 0.0
        self.override = None
        self.override_until = 0.0
        self.mood_effect = None
        self.mood_effect_until = 0
        self.last_drink = time.time()
        self.fx = []
        self.press = None
        self.dragging = False
        self.hover_close = False
        self.alive = True
        self.cmds = []
        self.last_tick = time.time()
        self.was_locked = False
        self.quiet_after = None
        self.hidden_until_due = False
        self.schedule_day = datetime.now().date().isoformat()
        self.fired_schedule = set()
        self.reset_timers()
        self.tray = None
        self.menu = tk.Menu(r, tearoff=0)
        for label, cmd in (("Cheer me up", "joke"), ("Water now", "water"), ("Break now", "break"),
                           ("Check in with me", "checkin")):
            self.menu.add_command(label=label, command=lambda c=cmd: self.cmds.append(c))
        mm = tk.Menu(self.menu, tearoff=0)
        for m in MOODS + ("auto",):
            mm.add_command(label=m.capitalize(), command=lambda c="mood:" + m: self.cmds.append(c))
        self.menu.add_cascade(label="Avatar mood", menu=mm)
        self.menu.add_command(label="Quiet for 60 minutes", command=lambda: self.cmds.append("quiet"))
        self.menu.add_command(label="Quit", command=lambda: self.cmds.append("quit"))
        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_motion)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<Motion>", self.on_hover)
        self.cv.bind("<Leave>", lambda e: setattr(self, "hover_close", False))
        self.cv.bind("<Double-Button-1>", self.on_double)
        self.cv.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        r.geometry(f"{W}x{H}+{int(self.x)}+{int(self.y)}")
        r.update_idletasks()
        r.after(250, self.start_tray_later)
        log(f"ready screen={self.sw}x{self.sh} state={self.state} tray=pending")
        self.tick()

    # ---------- tray ----------
    def start_tray_later(self):
        if self.alive and self.tray is None:
            self.tray = self.start_tray()
            log(f"tray={'ready' if self.tray else 'unavailable'}")

    def start_tray(self):
        try:
            import pystray
            from pystray import MenuItem as Item
            add = self.cmds.append
            menu = pystray.Menu(
                Item("Cheer me up", lambda: add("joke"), default=True),
                Item("Water now", lambda: add("water")),
                Item("Break now", lambda: add("break")),
                Item("Check in with me", lambda: add("checkin")),
                Item("Quiet for 60 minutes", lambda: add("quiet")),
                Item("Quit", lambda: add("quit")))
            icon = pystray.Icon("Desktop Wellness Buddy", buddy_art.make_avatar(64), "Desktop Wellness Buddy", menu)
            icon.run_detached()
            return icon
        except Exception as e:
            log(f"tray unavailable: {e}")
            return None

    # ---------- mood ----------
    def mood(self):
        n = time.time()
        if self.override and n < self.override_until:
            return self.override
        self.pets = [p for p in self.pets if n - p < 300]
        h = datetime.now().hour
        if len(self.pets) >= 5:
            return "hyper"
        if h >= 17 or h < 8:
            return "sleepy"
        if self.in_hours() and n - self.last_drink > 50 * 60:
            return "sassy"
        if n - self.last_drink < 20 * 60:
            return "proud"
        return "happy"

    def eye(self):
        if time.time() < self.happy_until:
            return "happy"
        if self.blink_t > 0 and self.mood() in ("happy", "sassy", "proud", "hyper"):
            return "blink"
        return MOOD_EYE[self.mood()]

    # ---------- timers ----------
    def reset_timers(self):
        n = time.time()
        self.back_at = None

    def in_hours(self):
        n = datetime.now()
        return n.weekday() < 5 and WORK_START <= n.hour + n.minute / 60 < WORK_END

    def due(self):
        if not self.in_hours():
            return None
        now = datetime.now()
        day = now.date().isoformat()
        if self.schedule_day != day:
            self.schedule_day = day
            self.fired_schedule = set()
        minute = now.hour * 60 + now.minute
        for hour, scheduled_minute, kind in SCHEDULE:
            key = (day, hour, scheduled_minute, kind)
            if minute == hour * 60 + scheduled_minute and key not in self.fired_schedule:
                self.fired_schedule.add(key)
                return kind
        return None

    # ---------- popups ----------
    def start_flight(self, kind):
        self.kind = kind
        pool = {"water": WATER, "break": BREAK, "back": BACK, "checkin": CHECKIN,
                "joke": JOKES, "pep": PEP}[kind]
        # Use a reminder appropriate to the event first. Keep the original
        # pools as a fallback for any future event type not yet categorized.
        self.text = random.choice(CONTEXT_LINES.get(kind, pool))
        self.set_buttons(kind)
        # Avatar interactions stay anchored at the taskbar; only the thought bubble changes.
        self.state, self.p = "talk", 1.0
        self.x, self.y = self.home_x, self.home_y
        self.talk_start = time.time()

    def set_buttons(self, kind):
        self.buttons = {
            "water": [("Drank it", "drank"), ("In 5 min", "snooze5")],
            "break": [("Starting break", "break_go"), ("Later", "snooze10")],
            "back": [("Ready", "dismiss")],
            "checkin": [("Great", "great"), ("Meh", "meh"), ("Stressed", "stressed")],
            "joke": [("Haha", "dismiss"), ("Another", "another")],
            "pep": [("Thanks", "dismiss")],
        }.get(kind, [("OK", "dismiss")])

    def act(self, a):
        n = time.time()
        if a == "drank":
            self.last_drink = n
            self.next_water = n + WATER_MIN * 60
            self.react("Gold star. Hydration logged.", happy=True)
        elif a == "snooze5":
            self.next_water = n + 5 * 60
            self.leave("Fine. Five minutes. I am counting.")
        elif a == "break_go":
            self.next_break = n + BREAK_MIN * 60
            self.next_water = max(self.next_water, n + 10 * 60)
            self.back_at = n + BREAK_LEN * 60
            self.leave("Go! I will fetch you in 5 minutes.")
        elif a == "snooze10":
            self.next_break = n + 10 * 60
            self.leave("Ten minutes. Then I get loud.")
        elif a == "great":
            self.override, self.override_until = "hyper", n + 600
            self.react(random.choice(GREAT), happy=True)
        elif a == "meh":
            self.kind = "joke"
            self.set_buttons("joke")
            self.react(random.choice(MEH) + " " + random.choice(JOKES), happy=False, stay=True)
        elif a == "stressed":
            self.override, self.override_until = "zen", n + 900
            self.react(random.choice(STRESSED), happy=False)
        elif a == "another":
            self.text = random.choice(JOKES)
            self.talk_start = n
            self.stv += 0.2
        else:  # dismiss
            self.leave(None)

    def react(self, text, happy, stay=False):
        self.text = text
        self.talk_start = time.time() + 20  # give her time to read
        self.buttons = [("OK", "dismiss")] if not stay else self.buttons
        if happy:
            self.happy_until = time.time() + 3
        self.stv += 0.35

    def leave(self, parting):
        n = time.time()
        self.kind, self.buttons = None, []
        if parting:
            self.text = parting
            self.chirp_until = n + 2.5
        self.x, self.y = self.home_x, self.home_y
        self.state, self.p = "home", 1.0

    # ---------- commands ----------
    def run_cmd(self, c):
        if c == "quit":
            return self.quit()
        if c == "quiet":
            self.state = "quiet"
            self.root.withdraw()
            self.root.after(3600000, self.unquiet)
        elif c.startswith("mood:"):
            m = c.split(":")[1]
            if m == "auto":
                self.override = None
                chosen = self.mood()
            else:
                self.override, self.override_until = m, time.time() + 1800
                chosen = m
            self.text = self.new_thought(chosen)  # one bubble, stays 15 seconds
            self.chirp_until = time.time() + 15
            self.mood_effect = chosen if chosen != "auto" else None
            self.mood_effect_until = self.t + 180
            self.action_start = self.t
            self.perform_mood, self.perform_start = chosen, self.t  # a 20 second mood show
            self.avatar_action, self.avatar_action_until = "perform", self.t + 500
            self.stv += 0.3
        elif c == "trick":
            if self.state == "home" and self.avatar_action not in ("hop", "spin"):
                self.action_start = self.t
                if random.random() < 0.5:
                    self.avatar_action, self.avatar_action_until = "hop", self.t + 24
                else:
                    self.avatar_action, self.avatar_action_until = "spin", self.t + 26
        elif self.state == "quiet":
            self.unquiet()
        elif c in ("joke", "water", "break", "checkin"):
            # Manual tray commands must be able to wake the pet after X hides it.
            # The scheduled path intentionally remains separate and still waits
            # for the next fixed wall-clock event.
            if self.state == "hidden":
                self.hidden_until_due = False
                self.root.deiconify()
                self.x, self.y = self.home_x, self.home_y
                self.state, self.p = "home", 1.0
            if self.state == "home":
                self.start_flight(c)

    def unquiet(self):
        if self.state == "quiet":
            self.reset_timers()
            self.root.deiconify()
            self.x, self.y = -float(W), float(self.sh - H - 60)
            self.state, self.p = "walk_in", 0.0
            self.walk_in_elapsed = 0
            self.entrance_alpha = 0.0

    # ---------- mood performances ----------
    def perform_transform(self):
        """Body motion for the mood show: returns angle, scale_x, scale_y, vertical offset."""
        k = self.t - self.perform_start
        m = self.perform_mood
        s = math.sin
        if m == "zen":  # levitating meditation: floats, breathes slowly
            breath = s(k / 26.0)
            return 0, 1.0 + 0.025 * breath, 1.0 + 0.03 * breath, -16 + 4 * s(k / 13.0)
        if m == "hyper":  # hops non stop and spins every second hop
            hop = abs(s(math.pi * k / 14.0))
            ang = int(((k % 56) / 28.0) * 360) % 360 if (k % 56) < 28 else 0
            return ang, 1.0 - 0.05 * math.cos(2 * math.pi * k / 14.0), 1.0 + 0.07 * math.cos(2 * math.pi * k / 14.0), -hop * 26
        if m == "happy":  # bouncy happy dance
            hop = abs(s(math.pi * k / 20.0))
            return int(7 * s(k / 10.0)), 1.0 - 0.04 * math.cos(2 * math.pi * k / 20.0), 1.0 + 0.06 * math.cos(2 * math.pi * k / 20.0), -hop * 24
        if m == "proud":  # standing tall
            grow = (1 + s(k / 18.0)) / 2
            return 0, 1.0 + 0.03 * grow, 1.0 + 0.05 * grow, -3 * grow
        if m == "sassy":  # head tilt and a foot tap
            return int(8 * s(k / 16.0)), 1.0, 1.0, -2 * abs(s(k / 6.0))
        # sleepy: slow sink and sway
        return int(4 * s(k / 30.0)), 1.0 + 0.02 * s(k / 40.0), 0.94 + 0.02 * s(k / 40.0), 5

    def draw_star(self, c, x, y, r, fill):
        pts = []
        for i in range(8):
            rr = r if i % 2 == 0 else r * 0.4
            ang = math.pi / 4 * i - math.pi / 2
            pts += [x + rr * math.cos(ang), y + rr * math.sin(ang)]
        c.create_polygon(*pts, fill=fill, outline="")

    def draw_label(self, c, text, right_x, y):
        """Readable text: dark bold letters on a white pill with a magenta edge, right aligned at right_x."""
        try:
            import tkinter.font as tkfont
            w = tkfont.Font(family="Segoe UI", size=10, weight="bold").measure(text) + 18
        except Exception:
            w = len(text) * 8 + 18
        x2, x1 = right_x, right_x - w
        c.create_rectangle(x1, y - 12, x2, y + 12, fill="white", outline="#E20074", width=2)
        c.create_text((x1 + x2) / 2, y, text=text, fill="#2b1a3a", font=("Segoe UI", 10, "bold"))

    def draw_performance(self, c, bob):
        """Props around her for the chosen mood. Office safe and drawn, not emoji."""
        k = self.t - self.perform_start
        m = self.perform_mood
        ax, ay = self.avatar_x, H - 98 + bob
        gy = H - 14  # ground
        lx = ax - 44  # labels sit to her left, the x button sits to her right
        if m == "zen":
            for i in range(5):  # pink petal shapes under her
                dx = (i - 2) * 11
                c.create_oval(ax + dx - 7, gy - 16 + abs(i - 2) * 3, ax + dx + 7, gy + 2,
                              fill="#ffd1e8" if i % 2 else "#ffb3d9", outline="#e20074")
            self.draw_label(c, "breathe in" if math.sin(k / 26.0) > 0 else "breathe out", lx, ay - 30)
        elif m == "hyper":
            for i in range(8):
                ang = k / 6.0 + i * math.pi / 4
                self.draw_star(c, ax + 62 * math.cos(ang), ay - 10 + 70 * math.sin(ang), 6 + (i % 2) * 3,
                               "#f5a300" if i % 2 else "#2bd6b3")
            for j in range(3):
                c.create_line(ax - 60 - j * 6, ay - 30 + j * 22, ax - 90 - j * 10, ay - 30 + j * 22,
                              fill="#7b4bb7", width=2)
        elif m == "happy":
            cols = ("#e20074", "#2bd6b3", "#f5a300", "#7b4bb7")
            for i in range(14):
                x = ax + 75 * math.sin(i * 2.3)
                y = 100 + ((k * 3 + i * 37) % 170)
                c.create_rectangle(x, y, x + 5, y + 8, fill=cols[i % 4], outline="")
        elif m == "proud":
            self.draw_star(c, ax + 46, ay - 78 - 3 * math.sin(k / 8.0), 13, "#f5a300")
            self.draw_star(c, ax - 48, ay - 50, 7, "#2bd6b3")
            self.draw_label(c, "well done", lx, ay - 30)
        elif m == "sassy":
            self.draw_label(c, "hmph.", lx, ay - 30)
        else:  # sleepy
            for i in range(3):
                rise = (k + i * 28) % 84
                zx, zy, zr = ax - 58 - i * 6, ay - 40 - rise * 0.7, 9 + i * 2
                c.create_oval(zx - zr, zy - zr, zx + zr, zy + zr, fill="white", outline="#7b4bb7", width=2)
                c.create_text(zx, zy, text="Z", fill="#2b1a3a", font=("Segoe UI", 8 + i * 2, "bold"))
            c.create_arc(ax - 74, ay - 70, ax - 38, ay - 34, start=60, extent=220, style="arc",
                         outline="#7b4bb7", width=5)  # little moon

    # ---------- idle life: stroll, turn at the edges, hop, spin ----------
    def idle_motion(self, mood):
        a = self.avatar_action
        if a == "perform":
            self.avatar_x += max(-3.0, min(3.0, W / 2 - self.avatar_x))  # glide to the middle so labels have room
            if self.t >= self.avatar_action_until:  # show over: back to normal
                self.avatar_action = "idle"
                self.next_action = self.t + 60
            return
        if a == "wave":
            return  # let the wave finish first
        if a in ("hop", "spin"):
            if self.t >= self.avatar_action_until:
                self.avatar_action = "idle"
                self.next_action = self.t + random.randint(60, 160)
            return
        if a == "stroll" and self.pointer_near():
            self.avatar_action = "idle"  # stop walking so the x and her are easy to click
            self.next_action = self.t + 60
            return
        if a == "idle" and self.pointer_near():
            self.next_action = max(self.next_action, self.t + 30)
        if a == "stroll":
            speed =0.5 if mood == "sleepy" else (1.3 if mood == "hyper" else 0.9)
            self.walk_phase += 0.075 * speed / 0.9
            self.avatar_x += speed * self.avatar_dir
            lo, hi = 70, W - 70
            if self.avatar_x >= hi:
                self.avatar_x, self.avatar_dir = hi, -1  # turn around at the edge
            elif self.avatar_x <= lo:
                self.avatar_x, self.avatar_dir = lo, 1
            if self.t >= self.avatar_action_until:
                self.avatar_action = "idle"
                self.next_action = self.t + random.randint(40, 120)
            return
        if self.t >= self.next_action:  # idle: pick something to do
            roll = random.random()
            stroll_share = 0.2 if mood == "hyper" else 0.4
            if mood == "sleepy" or roll < stroll_share:
                self.avatar_action = "stroll"
                self.avatar_dir = random.choice((-1, 1))
                self.avatar_action_until = self.t + random.randint(100, 220)
            elif roll < 0.75 or mood == "hyper":
                self.avatar_action, self.action_start = "hop", self.t
                self.avatar_action_until = self.t + 24
            else:
                self.avatar_action, self.action_start = "spin", self.t
                self.avatar_action_until = self.t + 26

    # ---------- mouse ----------
    def close_box(self):
        """Return the close-button rectangle attached to the avatar."""
        # Right beside her head, following her. She stands still while your mouse is near her.
        x1 = min(W - 34, int(self.avatar_x) + 42)
        y1 = H - 172
        return x1, y1, x1 + 28, y1 + 28

    def pointer_near(self):
        try:
            px = self.root.winfo_pointerx() - self.root.winfo_rootx()
            py = self.root.winfo_pointery() - self.root.winfo_rooty()
            return -30 <= px <= W + 30 and -10 <= py <= H + 30
        except Exception:
            return False

    def in_close_box(self, x, y):
        x1, y1, x2, y2 = self.close_box()
        return x1 - 6 <= x <= x2 + 6 and y1 - 6 <= y <= y2 + 6  # a little extra room to click

    def on_hover(self, e):
        """Show a discoverable close control whenever the pet is hovered."""
        if not self.hover_close:
            self.hover_close = True
            self.draw()

    def on_press(self, e):
        if self.in_close_box(e.x, e.y):
            self.hide_until_due()  # × hides her; the next scheduled reminder brings her back
            return
        self.press =(e.x, e.y, e.x_root, e.y_root)
        self.dragging = False

    def on_motion(self, e):
        if not self.press or self.state not in ("home",):
            return
        if not self.dragging and abs(e.x_root - self.press[2]) + abs(e.y_root - self.press[3]) > 6:
            self.dragging = True
        if self.dragging:
            self.x = e.x_root - self.press[0]
            self.y = e.y_root - self.press[1]
            self.stv += 0.0
            self.tilt = max(-10, min(10, (e.x_root - self.press[2]) * 0.05))

    def on_release(self, e):
        if self.in_close_box(e.x, e.y):
            return
        if self.dragging:
            self.home_x = max(0.0, min(self.sw - W, self.x))
            self.home_y = max(0.0, min(self.sh - H, self.y + 0))
            self.dragging = False
            self.stv -= 0.3  # plop
            return
        for (label, a, x1, y1, x2, y2) in self.btn_boxes():
            if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                return self.act(a)
        if self.state == "home":
            n = time.time()
            self.pets.append(n)
            m = self.mood()
            self.text = self.new_thought(m)  # a fresh thought on every click
            self.chirp_until = n + 15
            self.happy_until = n + 2
            self.stv += 0.35

    def new_thought(self, mood):
        choices = [line for line in LINES[mood] if line != self.last_line] or LINES[mood]
        self.last_line = random.choice(choices)
        return self.last_line

    def on_double(self, e):
        if self.state == "home" and not self.dragging:
            self.text = random.choice(JOKES + PEP)
            self.chirp_until = time.time() + 7
            self.happy_until = time.time() + 3
            self.stv += 0.4

    def quit(self):
        self.alive = False
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.root.destroy()

    def hide_until_due(self):
        """Hide the pet without stopping the process or its reminder timers."""
        self.hidden_until_due = True
        self.state = "hidden"
        self.kind, self.buttons = None, []
        self.text = ""
        self.root.withdraw()
        log("hidden until next scheduled reminder")

    # ---------- drawing ----------
    def btn_boxes(self):
        if self.state != "talk" or not self.buttons:
            return []
        out, n = [], len(self.buttons)
        bw = (W - 24 - 8 * (n - 1)) // n
        for i, (label, a) in enumerate(self.buttons):
            x1 = 12 + i * (bw + 8)
            out.append((label, a, x1, 84, x1 + bw, 110))
        return out

    def render_avatar(self):
        """Render the avatar with a restrained step cycle, not a floating motion."""
        action = self.avatar_action
        stride = 0.0  # walking is flat: no tilt, no bounce, no stretch (those made it look like hopping)
        scale_x = 1.0
        scale_y = 1.0
        action_bob = 0
        angle = 0
        if action == "perform":
            angle, scale_x, scale_y, action_bob = self.perform_transform()
        elif action == "hop":
            k = (self.t - self.action_start) / 24.0
            action_bob = -abs(math.sin(math.pi * k)) * 30
            scale_y += 0.06 * math.cos(2 * math.pi * k)  # stretch going up, squash landing
            scale_x -= 0.04 * math.cos(2 * math.pi * k)
        elif action == "spin":
            angle = int(((self.t - self.action_start) / 26.0) * 360) % 360
        else:
            angle = 0

        front = self.front_pose is not None and action in ("wave", "idle", "hop", "spin", "perform")
        if front or (self.avatar_frames and action in ("stroll", "run", "wave", "idle", "hop", "spin", "perform")):
            seq = WALK_SEQ if len(self.avatar_frames) >= 6 else list(range(len(self.avatar_frames)))
            frame_index = 1 if action in ("wave", "idle", "hop", "spin") else seq[int(self.walk_phase / 0.75) % len(seq)]
            if front:
                pose = self.front_pose.copy()  # standing still: face the front
                if action == "perform" and self.perform_mood in self.mood_poses:
                    pose = self.mood_poses[self.perform_mood].copy()  # your own pose picture, if you added one
                if action in ("wave", "idle"):
                    angle, scale_x, scale_y, action_bob = 0, 1.0, 1.0, 0
            else:
                pose = self.avatar_frames[frame_index].copy()
            im = pose  # already aligned on a fixed 190x170 canvas
            im = im.resize((max(40, int(im.width * scale_x)), max(40, int(im.height * scale_y))), Image.Resampling.LANCZOS)
        else:
            w = max(40, int(112 * scale_x))
            h = max(40, int(112 * scale_y))
            im = self.avatar_sprite.resize((w, h), Image.Resampling.LANCZOS)
        if self.avatar_dir < 0 and not front:
            im = ImageOps.mirror(im)
        if angle:
            im = im.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        im.putalpha(im.getchannel("A").point(lambda v: 255 if v > 128 else 0))  # no pink fringe on the see-through window
        self.avatar_tk = ImageTk.PhotoImage(im)
        return self.avatar_tk, action_bob

    def draw(self):
        c = self.cv
        c.delete("all")
        avatar, action_bob = self.render_avatar()
        # A simple ground contact makes the feet read as walking on the taskbar.
        c.create_line(self.avatar_x - 30, H - 14, self.avatar_x + 30, H - 14,
                      fill="#a7a7a7", width=2)
        c.create_image(self.avatar_x, H - 98 + action_bob, image=avatar, anchor="center")
        if self.avatar_action == "wave":
            self.draw_label(c, "Hi!", self.avatar_x - 46, H - 150)
        if self.avatar_action == "perform":
            self.draw_performance(c, action_bob)
        n = time.time()
        talking = self.state == "talk"
        chirp = n < self.chirp_until and self.state in ("home", "walk_in", "exit")
        if talking or chirp:
            bh = 118 if (talking and self.buttons) else 84
            c.create_rectangle(2, 2, W - 2, bh, fill="white", outline="#E20074", width=3)
            c.create_image(10, 10, image=self.avatar, anchor="nw")
            c.create_text(84, 12, text=self.text, width=W - 98, anchor="nw", font=("Segoe UI", 9))
            for (label, a, x1, y1, x2, y2) in self.btn_boxes():
                c.create_rectangle(x1, y1 + 4, x2, y2 + 4, fill="#E20074", outline="")
                c.create_text((x1 + x2) / 2, (y1 + y2) / 2 + 4, text=label, fill="white",
                              font=("Segoe UI", 9, "bold"))
        if True:  # always visible: transparent areas ignore the mouse, so a hover-only button cannot be reached
            x1, y1, x2, y2 = self.close_box()
            c.create_oval(x1, y1, x2, y2, fill="#E20074", outline="white", width=1)
            c.create_text((x1 + x2) / 2, (y1 + y2) / 2 - 1, text="×", fill="white",
                          font=("Segoe UI", 14, "bold"))
    def draw_mood_effect(self, c):
        """Show an office-safe animated data/science reaction instead of mood text or hearts."""
        mode = self.mood_effect
        x1, y1 = max(4, int(self.avatar_x - 92)), H - 154
        if mode == "hyper":
            x2, y2 = x1 + 68, y1 + 36
            c.create_rectangle(x1, y1, x2, y2, fill="#eef7ff", outline="#5b2a86", width=2)
            c.create_text(x1 + 7, y1 + 5, text="LIVE DATA", anchor="nw", fill="#5b2a86",
                          font=("Segoe UI", 7, "bold"))
            heights = [8 + int(5 * abs(math.sin(self.t / 5 + i))) for i in range(4)]
            for i, height in enumerate(heights):
                bx = x1 + 8 + i * 11
                c.create_rectangle(bx, y2 - 6 - height, bx + 6, y2 - 6,
                                   fill="#2bd6b3" if i % 2 else "#7b4bb7", outline="")
            c.create_line(x1 + 7, y2 - 8, x1 + 20, y2 - 15, x1 + 34, y2 - 11,
                          x1 + 48, y2 - 22, x1 + 60, y2 - 17, fill="#e20074", width=2)
        elif mode == "proud":
            c.create_rectangle(x1 + 9, y1 + 8, x1 + 59, y1 + 28,
                               fill="#fff5d6", outline="#f5a300", width=2)
            c.create_text(x1 + 34, y1 + 18, text="✓", fill="#2b9b77", font=("Segoe UI", 16, "bold"))
        elif mode == "happy":
            radius = 7 + int(3 * abs(math.sin(self.t / 6)))
            c.create_oval(x1 + 34 - radius, y1 + 18 - radius, x1 + 34 + radius, y1 + 18 + radius,
                          outline="#2bd6b3", width=2)
            c.create_oval(x1 + 30, y1 + 14, x1 + 34, y1 + 18, fill="#e20074", outline="")
        elif mode == "sassy":
            c.create_polygon(x1 + 34, y1 + 5, x1 + 50, y1 + 29, x1 + 18, y1 + 29,
                             fill="#fff5d6", outline="#e20074", width=2)
            c.create_text(x1 + 34, y1 + 20, text="!", fill="#e20074", font=("Segoe UI", 10, "bold"))
        elif mode == "zen":
            radius = 8 + int(3 * abs(math.sin(self.t / 8)))
            c.create_oval(x1 + 34 - radius, y1 + 18 - radius, x1 + 34 + radius, y1 + 18 + radius,
                          outline="#2bd6b3", width=2)
        elif mode == "sleepy":
            c.create_arc(x1 + 18, y1 + 8, x1 + 46, y1 + 28, start=0, extent=180,
                         style="arc", outline="#7b4bb7", width=3)
            c.create_line(x1 + 32, y1 + 18, x1 + 51, y1 + 18, fill="#7b4bb7", width=2)

    # ---------- main loop ----------
    def tick(self):
        if not self.alive:
            return
        try:
            self.step()
        except Exception:
            log(traceback.format_exc())
        if self.alive:
            self.root.after(40, self.tick)

    def step(self):
        now = time.time()
        if now - self.last_tick > 30:  # PC slept: start fresh
            self.reset_timers()
        self.last_tick = now
        self.t += 1
        if self.t % 50 == 0:  # every 2 seconds
            lk = locked()
            if lk and not self.was_locked:
                self.root.withdraw()
            elif self.was_locked and not lk and self.state != "quiet":
                self.reset_timers()
                # Do not pop up immediately after unlock. Wait for the next fixed event.
                self.hidden_until_due = True
                self.state = "hidden"
                self.kind, self.buttons = None, []
                self.text = ""
                self.root.withdraw()
            self.was_locked = lk
        if self.was_locked:
            return
        while self.cmds:
            self.run_cmd(self.cmds.pop(0))
        if not self.alive:
            return
        if self.hidden_until_due:
            kind = self.due()
            if not kind:
                return
            self.hidden_until_due = False
            self.root.deiconify()
            self.x, self.y = self.home_x, self.home_y
            self.start_flight(kind)
        # spring for squash and stretch
        self.stv += (0 - self.st) * 0.22
        self.stv *= 0.72
        self.st += self.stv
        self.tilt *= 0.85
        # blinking
        if self.blink_t > 0:
            self.blink_t -= 1
        elif self.t >= self.next_blink:
            self.blink_t = 4
            self.next_blink = self.t + random.randint(60, 140)
        m = self.mood()
        st = self.state
        bob = math.sin(self.t / (5 if m == "hyper" else 8)) * MOOD_BOB[m]
        if st == "home":
            if not self.dragging:
                # Keep the desktop pet window anchored. The avatar moves inside it.
                self.x = self.home_x
                self.y = self.home_y
                self.d = 1
                self.tilt = 0
            # Stop at the destination, wave once, then show the first thought.
            if self.avatar_action == "wave" and self.t >= self.avatar_action_until:
                self.avatar_action = "idle"
                self.next_action = self.t + 40
                if self.arrival_pending:  # one welcome thought after walking in, never after a mood pick
                    self.arrival_pending = False
                    choices = [line for line in ARRIVAL_THOUGHTS if line != self.last_line] or ARRIVAL_THOUGHTS
                    self.last_line = random.choice(choices)
                    self.text = self.last_line
                    self.chirp_until = now + 12
            if not self.dragging:
                self.idle_motion(m)
            # No automatic thought changes: a new thought appears only when you click her.
            if self.t % 20 == 0 and not self.dragging:
                k = self.due()
                if k:
                    self.start_flight(k)
        elif st == "walk_in":
            # Fade in at a fixed scale, then use a slow eased walk across one-third
            # of the screen. The walk starts immediately; there is no pop-in pause.
            self.y = self.home_y
            self.avatar_dir = 1
            self.walk_in_elapsed += 1
            self.avatar_action = "stroll"
            self.entrance_alpha = min(1.0, self.walk_in_elapsed / 15.0)
            try:
                self.root.attributes("-alpha", self.entrance_alpha)
            except tk.TclError:
                pass
            walk_ticks = 220.0  # about 9 seconds, a relaxed pace
            progress = min(1.0, (self.walk_in_elapsed - 1) / walk_ticks)
            eased = 0.85 * progress + 0.15 * progress * progress * (3.0 - 2.0 * progress)  # mostly even steps
            start_x = -(W / 2 + 70)  # just far enough left that she is off screen
            self.x = start_x + (self.home_x - start_x) * eased
            self.walk_phase += 0.11
            if self.x >= self.home_x:
                self.x = self.home_x
                self.state = "home"
                self.arrival_pending = True
                self.avatar_action = "wave"
                self.avatar_action_until = self.t + 70
                self.next_mutter = self.t + 82
                self.entrance_alpha = 1.0
                try:
                    self.root.attributes("-alpha", 1.0)
                except tk.TclError:
                    pass
            self.root.geometry(f"+{int(self.x)}+{int(self.y)}")
            self.draw()
            return
        elif st in ("enter", "return"):
            self.d = 1
            self.p = min(1.0, self.p + 1 / 55.0)
            tx = self.mid_x if st == "enter" else self.home_x
            ty = self.mid_y if st == "enter" else self.home_y
            sx0 = -float(W)
            self.x = sx0 + (tx - sx0) * ease_out_back(self.p)
            self.y = self.y + (ty - self.y) * 0.05 - math.sin(self.p * math.pi) * 3
            self.tilt = -8 * (1 - self.p)
            if self.p >= 1.0:
                self.stv -= 0.5  # landing squash
                self.state = "talk" if st == "enter" else "home"
                self.talk_start = now
        elif st == "talk":
            self.d = 1
            self.x = self.home_x
            self.y = self.home_y
            if now - self.talk_start > 90:  # not answered: leave, ask again later
                if self.kind == "water":
                    self.next_water = now + 5 * 60
                elif self.kind == "break":
                    self.next_break = now + 10 * 60
                self.leave(None)
        elif st == "exit":
            self.d = 1
            self.p = min(1.0, self.p + 1 / 40.0)
            if self.p < 0.15:
                self.stv += 0.1  # wind up stretch
            self.x += 3 + 22 * self.p * self.p
            self.y -= 1.5
            self.tilt = 10 * self.p
            if self.x > self.sw:
                self.state, self.away_ticks = "away", 0
        elif st == "away":
            self.away_ticks += 1
            self.x = float(self.sw + 50)
            if self.away_ticks > 60:
                self.x, self.y = -float(W), float(self.sh - H - 60)
                self.state, self.p = "walk_in", 0.0
                self.walk_in_elapsed = 0
                self.entrance_alpha = 0.0
        if st != "quiet":
            self.root.geometry(f"+{int(self.x)}+{int(self.y)}")
            self.draw()


if __name__ == "__main__":
    lock = single_instance()
    if lock is None:
        log("already running, exiting")
        sys.exit(0)
    try:
        DesktopWellnessBuddy().root.mainloop()
    except Exception:
        log(traceback.format_exc())
        raise
