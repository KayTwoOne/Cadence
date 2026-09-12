# Cadence — Controller Input Suite

A Windows tool for controllers: measure how fast you press things, check every pad
you have plugged in, and bind pad buttons to mouse and keyboard macros.

## Tabs

**Timing** — one controller, every press, and the gap between each pair. The headline
number is how long you left between your last two presses, shown to the precision the
hardware can actually support and in whole Rocket League physics ticks.

**Controllers** — all four XInput slots at once: what each device is, whether it is
wired, live button and stick state, and a per-pad timing calibration.

**Macros** — bind a pad button to a stream of clicks or keypresses. Hold or toggle,
fixed or random rate, duty cycle, click and time limits, double clicks, fixed-position
clicking, and rates per second, minute, hour or day.

## Honest limits

**Timing resolution is set by your controller, not by this app.** XInput returns the
last report the pad sent, and pads report every 4–8 ms. Reading faster than that
re-reads the same packet. Cadence measures your pad's real report rate and shows the
resulting margin rather than printing decimals it cannot support.

Some pads send nothing at all while they sit still, so that rate can only be measured
while a stick or trigger is moving. The Controllers tab has a button that does this
properly.

**Button names are a best guess.** XInput hides the brand, so the layout is recovered
from the USB vendor id through RawInput. A pad running through DS4Windows or Steam
Input reports as a virtual Microsoft pad, and with several pads attached Windows does
not say which slot is which. Whenever detection is not certain the app says so and
the layout can be set by hand.

## Stopping a macro

Three independent ways, because output lands in whatever window you are looking at:

1. The **ARMED** switch.
2. The **panic key** (F8 by default), which works even when Cadence is not focused.
   If another app already owns that key the app tells you instead of pretending.
3. Moving the **mouse into a screen corner**.

## Running

    python Cadence.py                 # normal
    python Cadence.py --demo          # two fake controllers, no hardware needed
    python Cadence.py --no-output     # macros count but send nothing

Windows 10/11 and Python 3.10+. No third-party packages.

## Building

    pip install pyinstaller
    python -m PyInstaller --onefile --noconsole --name Cadence --icon cadence.ico Cadence.py
