# Debugging log — when software lies about succeeding

The hardest bugs in this project were not crashes. They were things that **reported success and
did nothing**. Each one is written up here with how it was proven, because the proof is the
interesting part.

The common lesson: **an API that doesn't raise is not an API that worked.** Where an effect can
be measured, measure it.

---

## 1. A fan curve that never controlled the fans

**Symptom.** None. That was the problem. A service had been running for weeks, reading a
temperature sensor, computing duty percentages, and logging clean transitions:

```
fan-curve[…]: case=51C -> fans 43%
fan-curve[…]: case=52C -> fans 45%
```

Everything looked healthy. It was discovered only while building a tool that needed to set fan
speeds through the same library and got errors the service never showed.

**Root cause, two parts.**

The vendor library cannot write to this fan controller. It tags the device `(broken)` in its
own device listing, and every write form fails:

```
$ liquidctl --serial <redacted> set fan1 speed 100
ERROR: <controller> (broken): unspecified liquidctl error
```

`set fans speed` (all channels), an `--unsafe` opt-in flag, and running `initialize` first all
fail identically. Reads — RPM, temperatures — work perfectly, which is what makes it so
convincing from the outside.

And the service was hiding it:

```bash
liquidctl --serial "$SERIAL" set fan"$f" speed "$pct" >/dev/null 2>&1
#                                                     ^^^^^^^^^^^^^^^
```

Errors went to `/dev/null`. The loop then logged a transition based on the value it had
*computed*, never checking whether the hardware accepted it.

**How it was proven.** Not by reading the error text — by measurement. All five channels
commanded to 100%, 30 seconds to settle, then 30%, 30 seconds to settle:

| Commanded | Fan 1 | Fan 2 | Fan 3 | Fan 4 | Fan 5 |
| --- | --- | --- | --- | --- | --- |
| **100%** | 624 | 614 | 635 | 598 | 616 |
| **30%** | 628 | 617 | 636 | 603 | 611 |

Identical within noise. That table is the whole argument, and it's why the earlier
"validated under load" claim — fans reading 727→756 rpm as the curve moved 43%→45% — had to be
withdrawn. A 29 rpm drift is thermal noise, not a 2% duty change. The original reading assumed
the correlation it was trying to demonstrate.

**Fixes.**

- The service now captures stderr, counts per-channel results, and emits a loud rate-limited
  error when every channel fails.
- It no longer logs a curve transition it didn't achieve.
- The new MCP tool refuses to report success, and restores automatic control rather than
  leaving the curve stopped after a change that never landed.
- The documentation claiming working fan control was corrected, including the after-action
  report.

**Not an emergency, and saying so matters.** The fans free-run at a safe speed and the machine
is heavily over-cooled — under sustained full-GPU load the case sensor moved 0.4 °C and the GPU
held 45 °C on its own fans. Cooling was always adequate. It simply was never being *controlled*.
Reporting a scary-sounding finding without that context would have been its own kind of
inaccuracy.

---

## 2. Same class of bug, different vendor: the lighting CLI

**Symptom.** `<tool> --noautoconnect -d 0 -m off` exits **0**, prints a complete and correct
device detection, and changes nothing. Repeatedly. The active mode never changes.

**Root cause.** That CLI path doesn't write. Only the SDK-server path (`--server`, then a
`--client` connection to it) actually applies changes. Both are documented; only one works.

**Fix.** Run the daemon and drive it as a client. And bind it to loopback while you're there —
its default is all-interfaces with no auth.

**Also found here:** a second library was tried first for the same job and was worse — its
"set colour off" call returns success and applies nothing, and its other colour method is
literally `raise NotSupportedByDriver`. Clean division in the end: **one library owns fan
speeds, the other owns lighting, and they are never crossed.**

**A third trap, in the same tool.** Its client opens two connections and concatenates both
controller lists, so every device is reported **twice** — 12 entries for 6 devices. Deduping by
name would be wrong, because two of the devices are genuinely distinct units with identical
model names. The correct fix detects the exact doubling (first half's names equal second
half's) and keeps one half.

---

## 3. A device API that acks invalid identifiers

**Symptom.** An "launch app on device" tool reported ✅ while the device sat idle.

**Root cause.** The remote protocol accepts *any* string as an app identifier, acknowledges it
with no error, and does nothing when it doesn't match. Meanwhile the model was passing the app's
**human name** ("Netflix") because that's what a human said, while the device wanted an exact
reverse-DNS bundle identifier.

**Fix, and the generalizable lesson.** Resolve names to IDs **inside the tool**: fetch the
device's own installed-app list, match exact-ID → exact-name → substring (case-insensitive),
launch the resolved ID, and return a disambiguation error listing real options when the match
is empty or ambiguous.

**The caller is a language model, and it will pass human-friendly strings.** Any tool wrapping
an API that needs stable identifiers should do that resolution itself rather than pushing the
burden onto the caller, which will guess and guess wrong. This is now a rule in the shared
foundation.

---

## 4. ACPI silently holding a hardware interface

**Symptom.** A motherboard sensor chip that clearly exists, exposing nothing. No fan readings,
no PWM control files.

**Diagnosis.** The kernel module finds the chip and then gives up:

```
nct6775: Found NCT6791D or compatible chip at 0x2e:0x290
ACPI: OSL: Resource conflict; ACPI support missing from driver?
```

ACPI had claimed the chip's I/O range, so the driver refused to register rather than risk two
things driving the same hardware. A vendor-specific alternative driver also loads cleanly on
this board and registers nothing at all — a dead end that looks like progress.

**Fix.** `acpi_enforce_resources=lax` on the kernel command line, plus a reboot. The chip then
appeared with six PWM channels, and control turned out to be genuinely proportional:

| Commanded | Chassis fan RPM |
| --- | --- |
| baseline (BIOS curve) | 733 |
| 40% | 488 |
| 80% | 831 |
| 100% | 944 |
| restored | 734 |

Same measurement discipline as finding #1 — and this time it earned a ✅ that means something,
because the numbers move.

**Two traps worth knowing.** `pwmN_enable` values are chip-specific: on this family `1` is
manual and `5` is the BIOS curve, but **`0` means full-speed-ignoring-duty** — a channel reading
mode 0 is *not* under your control even though writes appear to land. And `hwmonN` indices are
assigned in probe order and **move between boots**, so anything durable must resolve the chip by
name.

---

## 5. Two failures that were really one environment assumption

Both from the same root: **a process started by `sshd` as a forced command, or by a systemd
timer, begins with an almost-empty environment.** No login shell, no profile.

- **Config never loaded.** The agent read its settings from environment variables that a login
  shell would have set. Under a forced command they were empty, so every hardware verb refused
  with a confusing "not configured" error. Fix: the agent sources its own config file explicitly.
- **A config line that executed.** That file contained `CHANNELS=1 2 3 4 5` — unquoted. Sourcing
  it made the shell try to run `2` as a command, printing `line 5: 2: command not found` before
  every single response. Fix: quote it, and quote it in the generator that writes it.

---

## 6. Stale state after a timer fired correctly

**Symptom.** Status reported an active manual override hours after it had expired.

**Root cause.** The expiry timer restarted the automatic service — correctly — but nothing
removed the marker file recording that an override existed. The automation was fine; the
*reporting* was wrong, which is arguably worse, because it's the part a human reads.

**Fix.** A small revert helper that clears the marker *and* restarts the service, so "control
returned" and "we say control returned" cannot diverge. The timer calls the helper, never
`systemctl` directly.

---

## 7. Debugging tools that lie to you

Two environment quirks that produced confidently wrong conclusions before being spotted:

- **`dmesg` returning empty to a non-root user** (`kernel.dmesg_restrict=1`). Greps against it
  silently matched nothing, which read as "the feature is absent" rather than "you can't see."
  This put a wrong hardware conclusion into documentation for days. Prefer `sysfs` for hardware
  facts.
- **A near-identically-named sensor.** Two temperature sources with similar labels; grepping the
  wrong one showed a static value and made a working control loop look frozen.

**Rule adopted:** when a diagnostic returns nothing, first prove the diagnostic works.

---

## 8. A tool that was registered, healthy, and invisible

**Symptom.** After adding a new server, the agent insisted one of its tools "isn't available" —
while every direct check said it was. The service was up, the transport handshake returned the
full tool list, and the runtime's own registry showed the tool attached and enabled. Yet asked to
use it, the model claimed it didn't exist, and asked to *find* it first, still gave up.

**The false trails.** Everything pointed at the tool itself or the new server — so both got
re-verified: the container was healthy, a direct protocol call to the tool returned real data, and
the registry listing was clean. All green. When every component tests good but the whole fails, the
fault is in the composition, not a part.

**Root cause.** The runtime has an automatic **tool-deferral** feature: once the combined tool
definitions exceed a share of the model's context budget, it stops listing every tool inline and
instead hides them behind a *search → describe → call* bridge, to save tokens. Adding the new
server pushed the total tool count over that threshold. So the tools didn't disappear — they moved
behind a lookup the small local model couldn't reliably drive. A larger model would have used the
bridge; the local one fumbled the indirection and concluded the tool was gone.

The tell was in the timeline, not the components: it had worked with fewer tools and broke on
crossing a count, which is the signature of a budget threshold, not a broken registration.

**How it was proven.** The threshold is configurable. Turning deferral off — putting every tool
back inline — made the same model call the same tool correctly on the first try, with no other
change. Flipping it back reproduced the failure. One toggle, two outcomes: the deferral was the
cause.

**Fix.** Disable deferral for this deployment. The feature optimizes for a scarce context window
and a capable model; here the model is the weak link and the context is local and effectively free,
so the tradeoff inverts — spend the tokens, keep every tool in plain sight. (If the tool count ever
grows enough to matter, the honest lever is to raise the threshold, not to expect the small model to
learn the indirection.)

**The lesson.** A capability the model can't *find* is as good as absent, and "the tool works" and
"the model can use the tool" are different claims that need testing separately. The bug was not in
any component — it was in an optimization that assumed a stronger caller than this system has.

---

## 9. A documented config flag that was accepted and never wired

**Symptom.** The agent runtime documents a setting that turns on export of conversation
trajectories — the full record of what a model was asked, what it reasoned, which tools it
called, in a standard training-data format. The plan for the next phase of work depended on
having that data. The documentation gives the exact YAML. Setting it produced no files.

**The false trail.** Every obvious cause looked plausible and was wrong. Was the service reading
the config at all? Yes — other keys in the same block were demonstrably in effect. Was the
output going somewhere unexpected? The docs say files land in the working directory, so the
first assumption was a working-directory mismatch between the interactive command and the
long-running service. A query was run from a freshly created empty directory to remove that
variable. Still nothing, anywhere on the box.

**What it actually was.** The flag is real and it works — for two callers. Reading the source
rather than the documentation showed that the batch runner and the runtime's own
direct-invocation entry point both pass it through. The interactive command and the
long-running service build their agent by a **third** path that never passes the parameter at
all. The key is parsed, accepted, silently ignored, and reported nowhere. No warning, no
"unknown option", no error. Documentation described a capability that exists in the codebase
but is unreachable from the way this system actually runs.

**The part that changed the conclusion.** Having established the export didn't work, the next
question was what it would have cost. The answer was: nothing, because the data was already
being captured. The runtime maintains a local database of sessions and messages that is always
on and needs no configuration — and it stores strictly more than the export would have
produced, including per-message reasoning and the raw tool-call payloads. The project's own
notes had recorded "trajectory logging has never been on," and that was **wrong in a way that
mattered**: capture had been running the whole time. What was missing was a converter.

So the fix was thirty lines of read-only SQL against a database that already had months of
history, on a scheduled timer, instead of a blocked dependency. A planned future task that had
been deferred for want of a dataset turned out to be much less blocked than the plan assumed.

**Rules adopted.**

> A configuration key that is accepted is not a configuration key that is honored. If a setting
> is supposed to produce an artifact, verify the artifact — not the absence of an error.

> Before building a data pipeline, check what the system already stores. The most common reason
> a capability is missing is that nobody looked for it under a different name.

An inert config line is worse than no line, because the next person to read the file will
believe it. It was removed rather than left in place looking load-bearing.
