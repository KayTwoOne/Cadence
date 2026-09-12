"""Drive every tab of the real app with demo pads. Output is disabled throughout."""
import sys, os, time, traceback, tempfile, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tkinter as tk
from cadence import app as A

errors = []
def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    if not cond:
        errors.append(name)

root = tk.Tk()
a = A.App(root, A.DemoReader(), demo=True, live_output=False)

def pump(seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        root.update()
        time.sleep(0.004)

try:
    pump(4.0)

    # ---------------------------------------------------------- tab 1: timing
    a.show_tab("timing"); pump(1.5)
    t = a.tabs["timing"]
    m = a.cur
    check("timing: presses captured", m and len(m.presses) > 5, f"{len(m.presses)}")
    check("timing: readout populated", a.tabs['timing'].big.cget("text") not in ("", "0 ms"),
          f"big={t.big.cget('text')!r} unit-suffix={t.plus.cget('text')!r}")
    check("timing: no duplicated unit in readout", "ms" not in t.big.cget("text"),
          f"big={t.big.cget('text')!r}")
    check("timing: log has rows", len(t.tree.get_children()) > 3)
    t.toggle_target(); t.target_var.set("60"); t.tol_var.set("25"); t.read_target()
    pump(1.5)
    check("timing: target hit rate reports", "landed within" in t.target_hits.cget("text"),
          t.target_hits.cget("text"))
    pump(2.5)
    tags = [t.tree.item(i, "tags")[0] for i in t.tree.get_children()]
    check("timing: rows tinted hit/miss", any(x in ("hit", "miss") for x in tags),
          str(tags[:8]))
    # a bracket only exists once the current sequence holds two presses
    for _ in range(60):
        pump(0.15)
        if len(a.cur.sequence) >= 3:
            break
    t.draw_timeline()
    check("timing: gap hover zones exist", len(t.gap_zones) > 0,
          f"{len(t.gap_zones)} zones, sequence of {len(a.cur.sequence)}")
    t.dismiss_hint(); t.draw_timeline()

    # ---------------------------------------------------------- tab 2: controllers
    a.show_tab("pads"); pump(2.5)
    p = a.tabs["pads"]
    check("pads: four cards built", len(p.cards) == 4)
    c0 = p.cards[0]
    check("pads: slot 1 shows connected", "not connected" not in c0.kind.cget("text"),
          c0.kind.cget("text"))
    check("pads: slot 3 shows empty", "not connected" in p.cards[2].kind.cget("text"))
    check("pads: report rate measured on demo pad",
          "ms" in c0.m_report.value.cget("text"), c0.m_report.value.cget("text"))
    c0.calibrate(); pump(1.0)
    check("pads: calibration shows a countdown", "Move the left stick" in c0.cal_note.cget("text"),
          c0.cal_note.cget("text")[:60])
    pump(4.0)
    check("pads: rate recovers after calibration",
          "ms" in c0.m_report.value.cget("text"), c0.m_report.value.cget("text"))

    # ---------------------------------------------------------- tab 3: macros
    a.show_tab("macros"); pump(0.6)
    mt = a.tabs["macros"]
    check("macros: one rule to start", len(a.engine.rules) == 1)
    check("macros: starts disarmed", not a.engine.armed_master)
    check("macros: logo dark while disarmed",
          a.logo.itemcget(a.logo_ring, "fill") != A.BRAND)

    mt.toggle_master(); pump(0.3)
    check("macros: arming lights the logo",
          a.logo.itemcget(a.logo_ring, "fill") == A.BRAND,
          a.logo.itemcget(a.logo_ring, "fill"))
    check("macros: armed state text", "live" in mt.state_line.cget("text"))

    # bind a trigger by "pressing" a button, the way the UI does it
    mt.capture_trigger()
    check("macros: capture mode shows prompt", "PRESS ANY" in mt.trigger_btn.cget("text"))
    consumed = mt.offer_button(0, "Y")
    check("macros: capture consumes the press", consumed)
    check("macros: trigger rebound to Y", mt.cur.trigger == "Y", mt.cur.trigger)

    # fire it
    rule = mt.cur
    rule.rate_value, rule.rate_unit = 20, "second"
    a.engine.handle(0, "Y", True)
    pump(0.8)
    a.engine.handle(0, "Y", False)
    pump(0.2)
    check("macros: firing incremented the counter", rule.fired > 5, f"{rule.fired} fires")
    check("macros: sent metric updates",
          mt.m_sent.value.cget("text") not in ("", "0"), mt.m_sent.value.cget("text"))
    check("macros: nothing reached the real mouse", not a.engine.synth.live)

    # advanced panel
    mt.toggle_advanced(); pump(0.3)
    check("macros: advanced panel shown", mt.adv.winfo_ismapped())
    mt.set_duty(60); mt.set_random(True); mt.read_rate()
    check("macros: duty note updates", "down" in mt.duty_note.cget("text"),
          mt.duty_note.cget("text"))
    mt.set_action("key"); mt.key_var.set("K"); mt.read_key(); root.update()
    check("macros: key row swaps in",
          mt.key_row.winfo_ismapped() and not mt.button_choice.winfo_ismapped())
    check("macros: key stored with case", mt.cur.key_text == "K")
    mt.set_action("mouse"); root.update()
    check("macros: button row swaps back",
          mt.button_choice.winfo_ismapped() and not mt.key_row.winfo_ismapped())

    mt.add_rule(); pump(0.2)
    check("macros: add creates a second rule", len(a.engine.rules) == 2)
    mt.remove_rule(); pump(0.2)
    check("macros: remove drops it", len(a.engine.rules) == 1)

    a.engine.panic("test")
    pump(0.3)
    check("macros: panic disarms", not a.engine.armed_master)
    check("macros: logo goes dark again",
          a.logo.itemcget(a.logo_ring, "fill") != A.BRAND)

    # ---------------------------------------------------------- shell
    a.show_tab("timing"); pump(0.4)
    a.show_help(); root.update()
    check("help window opens", a.help_win.winfo_exists())
    a.help_win.destroy()
    a.toggle_pause(); a.toggle_pause(); a.toggle_follow(); a.toggle_follow()
    a.select(1); pump(0.6); a.select(0)
    a.clear(); pump(0.3)

    d = tempfile.mkdtemp()
    a.select(1); pump(1.5)
    csvp, rptp = os.path.join(d, "t.csv"), os.path.join(d, "t.rpt")
    a.write_csv(csvp, a.cur); a.write_report(rptp, a.cur)
    check("export: csv written", os.path.getsize(csvp) > 200, f"{os.path.getsize(csvp)}B")
    check("export: report written", os.path.getsize(rptp) > 800, f"{os.path.getsize(rptp)}B")
    head = open(rptp, encoding="utf-8").read().splitlines()
    check("export: report names the app", head[0].startswith("CADENCE"), head[0])
    check("export: report states measurement basis",
          any("measured" in l or "assumed" in l for l in head[:16]))

except Exception:
    errors.append("exception")
    traceback.print_exc()

try:
    a.close()
except Exception:
    traceback.print_exc()
    errors.append("close")

print()
if errors:
    print(f"{len(errors)} FAILED: {errors}")
    sys.exit(1)
print("ALL UI TESTS PASSED")
