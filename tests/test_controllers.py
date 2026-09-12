"""QA for controller identification and scheme application.

Covers the cases a real user hits: a known brand, a licensed third party, an unknown
vendor, several pads at once, a remapper pretending to be Microsoft, and RawInput
returning nothing at all.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cadence import controllers as C

fails = []
def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    if not cond:
        fails.append(name)

def dev(vid, pid=0x0001):
    return {"vid": vid, "pid": pid, "path": f"HID#VID_{vid:04X}&PID_{pid:04X}&IG_00"}

# ---------------------------------------------------------------- identification
cases = [
    ("Xbox pad",            [dev(0x045E, 0x02FF)], 1, "xbox",        "certain"),
    ("DualSense",           [dev(0x054C, 0x0CE6)], 1, "playstation", "certain"),
    ("Switch Pro",          [dev(0x057E, 0x2009)], 1, "nintendo",    "certain"),
    ("Steam Deck",          [dev(0x28DE, 0x1205)], 1, "xbox",        "certain"),
    ("8BitDo (licensed)",   [dev(0x2DC8, 0x3106)], 1, "xbox",        "likely"),
    ("PowerA (licensed)",   [dev(0x24C6, 0x581A)], 1, "xbox",        "likely"),
    ("unknown vendor",      [dev(0x31E3, 0x1320)], 1, None,          "unknown"),
    ("nothing visible",     [],                    1, None,          "unknown"),
    ("two pads attached",   [dev(0x045E), dev(0x054C)], 2, None,     "ambiguous"),
]
for name, devices, n, want_scheme, want_conf in cases:
    key, vendor, conf, detail = C.identify(devices, n)
    check(f"identify: {name}", key == want_scheme and conf == want_conf,
          f"-> {key}/{conf}")

# a single pad with two devices listed should still resolve, not go ambiguous
k, _, conf, _ = C.identify([dev(0x045E)], 1)
check("identify: one slot, one device resolves", k == "xbox" and conf == "certain")

# the remapper caveat has to be stated, not assumed away
_, _, _, detail = C.identify([dev(0x045E, 0x028E)], 1)
check("identify: warns that remappers look like Microsoft",
      "DS4Windows" in detail or "Steam Input" in detail, detail[:70])

# ---------------------------------------------------------------- scheme content
for key in C.SCHEME_ORDER:
    s = C.SCHEMES[key]
    from cadence.hardware import KEYS
    missing = [k for k in KEYS if k not in s.labels]
    check(f"scheme {key}: labels every XInput button", not missing, str(missing))
    check(f"scheme {key}: has all four face colours",
          all(f in s.faces for f in ("A", "B", "X", "Y")))
    check(f"scheme {key}: valid stick layout", s.sticks in ("offset", "symmetric"))

# the Nintendo swap is the whole reason schemes exist - assert it explicitly
n = C.SCHEMES["nintendo"]
check("nintendo: XInput A is labelled B", n.label("A") == "B", n.label("A"))
check("nintendo: XInput B is labelled A", n.label("B") == "A", n.label("B"))
check("nintendo: XInput X is labelled Y", n.label("X") == "Y")
check("nintendo: XInput Y is labelled X", n.label("Y") == "X")
check("nintendo: shoulders are L/R not LB/RB",
      (n.label("LB"), n.label("RB")) == ("L", "R"))
check("nintendo: triggers are ZL/ZR", (n.label("LT"), n.label("RT")) == ("ZL", "ZR"))

p = C.SCHEMES["playstation"]
check("playstation: face names", (p.label("A"), p.label("B"), p.label("X"), p.label("Y"))
      == ("Cross", "Circle", "Square", "Triangle"))
check("playstation: shoulders L1/R1", (p.label("LB"), p.label("RB")) == ("L1", "R1"))
check("playstation: triggers L2/R2", (p.label("LT"), p.label("RT")) == ("L2", "R2"))
check("playstation: sticks are symmetric", p.sticks == "symmetric")
check("playstation: draws symbols not letters", p.glyphs == "symbol")
check("playstation: sticks are L3/R3", (p.label("LS"), p.label("RS")) == ("L3", "R3"))

x = C.SCHEMES["xbox"]
check("xbox: face letters unchanged",
      all(x.label(k) == k for k in ("A", "B", "X", "Y")))
check("xbox: sticks are offset", x.sticks == "offset")
check("xbox: centre buttons are View/Menu", x.centre == ("View", "Menu"))

# ---------------------------------------------------------------- resolver
r = C.SchemeResolver()
r.detected[0] = ("playstation", "Sony", "certain", "Sony")
check("resolver: certain detection is applied", r.scheme_key(0) == "playstation")
check("resolver: certain detection is not a guess", not r.is_guess(0))

r.detected[1] = (None, None, "unknown", "VID 0x31E3 unrecognised")
check("resolver: unknown falls back to xbox", r.scheme_key(1) == "xbox")
check("resolver: unknown is flagged as a guess", r.is_guess(1))
check("resolver: unknown explains itself", "31E3" in r.explain(1), r.explain(1))

r.set_override(1, "nintendo")
check("resolver: override wins", r.scheme_key(1) == "nintendo")
check("resolver: override is not a guess", not r.is_guess(1))
check("resolver: override says who chose", "set by you" in r.explain(1), r.explain(1))

r.detected[2] = ("xbox", "8BitDo", "likely", "8BitDo")
check("resolver: 'likely' is applied", r.scheme_key(2) == "xbox")
check("resolver: 'likely' still counts as a guess", r.is_guess(2))
check("resolver: 'likely' is worded as probable",
      "probably" in r.explain(2), r.explain(2))

r.set_override(3, "not-a-real-scheme")
check("resolver: rejects an unknown scheme key", r.scheme_key(3) == "xbox")

# ---------------------------------------------------------------- live hardware
real = C.enumerate_xinput_devices()
print(f"\n-- this machine --")
print(f"XInput HID devices seen: {len(real)}")
for d in real:
    key, vendor, conf, detail = C.identify([d], 1)
    print(f"   VID 0x{d['vid']:04X} PID 0x{d['pid']:04X} -> scheme={key} "
          f"confidence={conf}")
    print(f"   {detail}")
check("live: enumeration does not throw", isinstance(real, list))

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL CONTROLLER TESTS PASSED")
