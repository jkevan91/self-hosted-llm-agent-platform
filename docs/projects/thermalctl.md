# thermalctl — thermal and lighting control

> Fan speeds, RGB lighting, and thermal telemetry across hosts — the most complete example in the
> system, and the source of its signature bug.

**Risk class:** ephemeral (floor-clamped, TTL-bounded) + two-phase gate for persistent curves

**Code:** the sanitized server, agent, and revert helper are in
[`src/thermalctl`](../../src/thermalctl).

---

## In plain English

This lets the assistant control fans and lighting and read temperatures — "set the fans to 60% for
ten minutes", "turn the lights blue", "how hot is the case?" Temporary changes happen freely and
undo themselves; permanent ones (rewriting the fan curve that runs automatically) need a human to
confirm.

The catch that makes this the most instructive piece: the assistant runs *inside a virtual machine*,
and the fans and lights are on the physical host *underneath* it. Reaching down through that
boundary to touch hardware is exactly the kind of access that's dangerous if the assistant is
compromised — so it became the proving ground for the whole security model.

## How it's used

- *"Set the fans to 60% for ten minutes."* → clamped above a floor, auto-reverts on a timer.
- *"Turn the lights blue" / "lights off."* → ephemeral, TTL-bounded.
- *"How hot is the case / CPU / GPU?"* → thermal telemetry (GPU when the card is host-visible).
- *"Change the automatic fan curve."* → plan/apply gate, git-backed.

## Architecture

The assistant, in a guest VM, reaches the physical host through a single SSH key **pinned to a
forced command** — the host runs a fixed agent script instead of whatever was requested. That script
is the security boundary; it's [`thermalctl-agent`](../../src/thermalctl/thermalctl-agent), and it's
the file to read first.

Two fan backends are auto-detected per host:

| Backend | Mechanism | Notes |
| --- | --- | --- |
| **hwmon PWM** | Direct sysfs write via a Super-I/O driver | **Preferred** — no vendor driver in between to swallow the write |
| **vendor USB library** | The controller's serial | For USB fan controllers; on the reference hardware it rejects every write |

hwmon wins wherever both are present — for exactly the reason the debugging log documents.

## Safety model

- **Forced command, not sudoers.** `sshd` discards the requested command and runs the agent, which
  matches the request against six verbs, regex-validates every argument, and never touches a shell.
  A scoped sudoers file would still leave the account a shell and binaries rich enough to repurpose;
  a forced command removes the shell from the equation. Full reasoning and the live attack table are
  in the [security model](../03-security-model.md#principle-1--capability-not-access).
- **Floor clamp.** `fan set 0` is refused; anything below the floor is raised to it. No phrasing
  silences the cooling.
- **Mandatory TTL.** Every override arms a `systemd` transient timer that restores automatic
  control, capped at 12 hours — enforced by systemd rather than a backgrounded `sleep`, because the
  SSH session ends the instant the agent returns and would take a `sleep` with it.
- **Two-phase gate** for persistent curve changes; the change tools ship disabled.
- **Honest failure.** `fan_set` counts per-channel results and returns an **error** when zero
  channels accept the write, then restores automatic control — rather than reporting success on a
  change that never landed.

## Engineering notes

This server is where the project's most-repeated lesson was learned the hard way
([debugging log #1](../05-debugging-log.md#1-a-fan-curve-that-never-controlled-the-fans)):

> A fan-curve service ran for **weeks**, logging tidy temperature-to-duty transitions, and had never
> once moved a fan. The vendor library couldn't write to the controller and the script was
> discarding stderr, then logging a transition based on the value it had *computed*. Proven by
> commanding 100% then 30% and measuring **no RPM change** — a table of five identical fan speeds is
> the whole argument.

That finding forced the withdrawal of an earlier "fan curve validated under load" claim, which is
[kept in the record with its correction](../06-engineering-practices.md#honest-after-action-reports).
The rule that came out — *an API that doesn't raise is not an API that worked; where the effect can
be measured, measure it* — now governs every server in the system.
