# zen-battery-life: glossary

Making Zen (a Firefox-based browser) use about as little power on an M4 MacBook Pro as Safari does, for the user's real daily tasks.

## Language

**Power cost**:
The average power draw, in watts, of a browser while running one Workload, measured over a fixed window.
_Avoid_: battery drain, energy impact, battery usage

**Workload**:
A fixed, scripted browser task that is measured for Power cost (e.g. "YouTube 1080p windowed").
_Avoid_: scenario, test case, benchmark

**Reference browser**:
Safari. It sets the Power cost each Workload is judged against.
_Avoid_: baseline, control

**Parity target**:
Zen's Power cost on a Workload is at most 1.2× the Reference browser's.
_Avoid_: goal, threshold

**Stretch target**:
Zen's Power cost on a Workload is below the Reference browser's.
_Avoid_: beating Safari, bonus goal

**Safari-parity rule**:
Any behavior the Reference browser has by default is an acceptable tradeoff to copy into Zen, unless it loses user state (reloaded tabs, lost input) or delays notifications the user relies on.
_Avoid_: acceptable degradation

**Extension cost**:
The difference in Power cost on a Workload with and without one extension installed.
_Avoid_: extension overhead, extension drain

**Clean profile**:
A new browser profile used only for measuring, with no user data and only the extensions a measurement calls for.
_Avoid_: test profile, fresh profile

**Real profile**:
The user's everyday Zen profile. It is read-only for this project.
_Avoid_: main profile, default profile

**Fix ladder**:
The order in which fixes are tried: settings first, then changes to Zen/Gecko source code only for what settings can't reach.
_Avoid_: escalation, tiers
