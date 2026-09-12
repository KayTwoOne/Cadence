"""Engine tests with output disabled: counters tick, nothing touches the real mouse."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cadence import macros, synth

fails = []

def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    if not cond:
        fails.append(name)

def engine():
    e = macros.MacroEngine(sender=synth.Synth(live=False))
    e.start()
    return e

# ---------------------------------------------------------------- rate accuracy
e = engine()
r = e.add(macros.Rule("RB"))
r.rate_value, r.rate_unit, r.duty = 10, "second", 0.25
e.set_master(True)
e.handle(0, "RB", True)
time.sleep(2.0)
e.handle(0, "RB", False)
time.sleep(0.05)
check("10/sec fires ~20 times in 2s", 18 <= r.fired <= 22, f"got {r.fired}")
check("nothing left held down", not r.down)
check("disarmed on release", not r.armed)

# down/up pairing in the log
kinds = [d for k, d in e.synth.log if k == "mouse"]
downs = sum(1 for d in kinds if "down" in d)
ups = sum(1 for d in kinds if "up" in d)
check("every press has a release", downs == ups, f"{downs} down / {ups} up")

# ---------------------------------------------------------------- duty cycle
# Sample the button state densely and compare the share of time it was down against
# the configured duty. Checking a single instant only tells you where that instant fell.
for duty in (0.25, 0.5, 0.8):
    ed = engine()
    rd = ed.add(macros.Rule("A"))
    rd.rate_value, rd.rate_unit, rd.duty = 20, "second", duty
    ed.set_master(True)
    ed.handle(0, "A", True)
    time.sleep(0.1)
    samples = []
    t_end = time.perf_counter() + 1.0
    while time.perf_counter() < t_end:
        samples.append(rd.down)
        time.sleep(0.001)
    ed.handle(0, "A", False)
    measured = sum(samples) / len(samples)
    check(f"duty {duty:g} holds the button that share of the time",
          abs(measured - duty) < 0.09, f"measured {measured:.2f} over {len(samples)} samples")
    ed.stop()

# ---------------------------------------------------------------- toggle mode
e3 = engine()
r3 = e3.add(macros.Rule("X"))
r3.mode, r3.rate_value = "toggle", 20
e3.set_master(True)
e3.handle(0, "X", True); e3.handle(0, "X", False)     # press and release once
time.sleep(0.3)
on_after_release = r3.armed
e3.handle(0, "X", True); e3.handle(0, "X", False)     # press again
time.sleep(0.05)
check("toggle stays on after release", on_after_release)
check("toggle turns off on second press", not r3.armed)

# ---------------------------------------------------------------- limits
e4 = engine()
r4 = e4.add(macros.Rule("Y"))
r4.rate_value, r4.limit_clicks = 50, 7
e4.set_master(True)
e4.handle(0, "Y", True)
time.sleep(0.8)
check("click limit stops the rule", not r4.armed and r4.session_fired == 7,
      f"fired {r4.session_fired}, reason '{r4.stopped_reason}'")

e5 = engine()
r5 = e5.add(macros.Rule("LB"))
r5.rate_value, r5.limit_seconds = 100, 0.3
e5.set_master(True)
e5.handle(0, "LB", True)
time.sleep(0.6)
check("time limit stops the rule", not r5.armed, f"reason '{r5.stopped_reason}'")

# ---------------------------------------------------------------- rate units
for unit, expect in (("second", 1.0), ("minute", 60.0), ("hour", 3600.0), ("day", 86400.0)):
    rr = macros.Rule()
    rr.rate_value, rr.rate_unit = 1, unit
    check(f"1 per {unit} -> {expect:g}s interval", abs(rr.base_interval() - expect) < 1e-6,
          f"got {rr.base_interval():g}")

# ---------------------------------------------------------------- random rate
rr = macros.Rule(); rr.random_rate, rr.rate_min, rr.rate_max = True, 10, 20
iv = [rr.base_interval() for _ in range(400)]
check("random CPS stays inside its range",
      all(1/20 - 1e-9 <= v <= 1/10 + 1e-9 for v in iv),
      f"{min(iv):.4f}..{max(iv):.4f}s = {1/max(iv):.1f}..{1/min(iv):.1f} cps")
check("random CPS actually varies", len(set(round(v, 5) for v in iv)) > 50)

# ---------------------------------------------------------------- double click
e6 = macros.MacroEngine(sender=synth.Synth(live=False)); e6.start()
r6 = e6.add(macros.Rule("RT"))
r6.action, r6.rate_value, r6.duty = "double", 5, 0.2
e6.set_master(True)
e6.handle(0, "RT", True)
time.sleep(0.45)
e6.handle(0, "RT", False)
time.sleep(0.05)
d = sum(1 for k, v in e6.synth.log if k == "mouse" and "down" in v)
check("double click sends two presses per fire", d == r6.fired * 2,
      f"{r6.fired} fires -> {d} downs")

# ---------------------------------------------------------------- keyboard + case
e7 = macros.MacroEngine(sender=synth.Synth(live=False)); e7.start()
r7 = e7.add(macros.Rule("B"))
r7.action, r7.key_text, r7.rate_value = "key", "Q", 20
e7.set_master(True)
e7.handle(0, "B", True); time.sleep(0.25); e7.handle(0, "B", False); time.sleep(0.05)
keys = [v for k, v in e7.synth.log if k == "key"]
check("keyboard output fires", len(keys) >= 2, f"{len(keys)} key events")
check("case is preserved", all(v.startswith("Q") for v in keys), str(keys[:3]))

# ---------------------------------------------------------------- edge stop
e8 = macros.MacroEngine(sender=synth.Synth(live=False)); e8.start()
r8 = e8.add(macros.Rule("LS"))
r8.rate_value, r8.edge_stop = 50, True
real_near_edge = macros.synth.near_edge
macros.synth.near_edge = lambda m, c: True        # pretend the mouse is in a corner
e8.set_master(True)
e8.handle(0, "LS", True)
time.sleep(0.2)
check("edge stop disarms the rule", not r8.armed, f"reason '{r8.stopped_reason}'")
macros.synth.near_edge = real_near_edge

# ---------------------------------------------------------------- master off releases
e9 = macros.MacroEngine(sender=synth.Synth(live=False)); e9.start()
r9 = e9.add(macros.Rule("RB"))
r9.rate_value, r9.duty = 2, 0.9        # long hold, so it is mid-press when we cut it
e9.set_master(True)
e9.handle(0, "RB", True)
time.sleep(0.1)
was_down = r9.down
e9.set_master(False)
check("master off catches a mid-press", was_down)
check("master off releases the button", not r9.down)
lg = [v for k, v in e9.synth.log if k == "mouse"]
check("no button left stuck after master off",
      sum('down' in v for v in lg) == sum('up' in v for v in lg), str(lg))

# ---------------------------------------------------------------- slot filtering
e10 = macros.MacroEngine(sender=synth.Synth(live=False)); e10.start()
r10 = e10.add(macros.Rule("A", slot=1))
e10.set_master(True)
e10.handle(0, "A", True); time.sleep(0.05)
wrong_pad = r10.armed
e10.handle(1, "A", True); time.sleep(0.05)
check("rule bound to pad 2 ignores pad 1", not wrong_pad)
check("rule bound to pad 2 fires on pad 2", r10.armed)

# ---------------------------------------------------------------- master gate
e11 = macros.MacroEngine(sender=synth.Synth(live=False)); e11.start()
r11 = e11.add(macros.Rule("A"))
e11.handle(0, "A", True); time.sleep(0.1)
check("nothing fires while master is off", not r11.armed and r11.fired == 0)

for eng in (e, e3, e4, e5, e6, e7, e8, e9, e10, e11):
    eng.stop()

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL MACRO ENGINE TESTS PASSED")
