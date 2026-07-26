# thermalctl — worked example

The most complete of the four servers, included because it exercises every pattern in this
system: a hard security boundary, two auto-detected hardware backends, ephemeral control with
safety bounds, and a two-phase gate for persistent change.

## Files

| File | Runs where | Role |
| --- | --- | --- |
| `thermalctl_server.py` | Container beside the agent | The MCP server — 10 tools, host resolution, plan/apply tokens |
| `thermalctl-agent` | Each target host, as root | **The security boundary.** The only thing the inbound key may execute |
| `thermalctl-revert` | Each target host, as root | Restores automatic control when an override expires |
| `Dockerfile` | — | Non-root image, read-only secrets mount |

## The security boundary

`thermalctl-agent` is the file to read first. It's pinned in `authorized_keys` as a forced
command:

```
command="/usr/local/sbin/thermalctl-agent",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-user-rc ssh-ed25519 AAAA...EXAMPLE
```

`sshd` ignores whatever the client asked to run and executes the agent, passing the request in
`$SSH_ORIGINAL_COMMAND`. The agent:

1. Rejects any string containing shell metacharacters (`;`, `|`, `&`, `$`, backtick, redirects,
   newline) outright
2. Splits the remainder and matches the first token against six verbs
3. Validates every argument by regex before use
4. Never passes anything to a shell — no `eval`, no `bash -c`, no constructed redirects

Steps 1 and 3 are deliberately redundant. The metacharacter check is a coarse early gate; the
per-argument regexes are the real control.

## Safety bounds

**Floor clamp.** `fan set 0` is refused. Anything below the configured floor is raised to it.
There is no phrasing that silences the cooling.

**Mandatory TTL.** Every override arms a `systemd-run --on-active` transient timer that
restores automatic control, capped at 12 hours.

Using systemd rather than a backgrounded `sleep` is load-bearing: the SSH session ends the
instant the agent returns, taking any child process with it. The revert has to outlive the
connection that requested it.

**Honest failure.** `fan_set` counts per-channel results and returns an **error** when zero
channels accept the write — then restores automatic control rather than leaving the curve
stopped after a change that never landed. See the debugging log for why that matters here.

## Two backends

Auto-detected per host, reported through `caps`:

| Cap | Mechanism |
| --- | --- |
| `fan_hwmon` | Direct sysfs PWM writes via a Super-I/O driver — **preferred** |
| `fan_liquidctl` | A vendor USB library, for controllers with no kernel driver |

hwmon wins where both exist: it's a plain sysfs write with no vendor driver in between to
swallow it. On the reference hardware the vendor library rejects every write while reads keep
working — the exact failure that motivated the "measure the effect" rule.

Two hwmon traps encoded in the agent:

- The chip is resolved by **name**, never by `hwmonN` — indices are assigned in probe order and
  move between boots.
- `pwmN_enable` is chip-specific: `1` = manual, `5` = BIOS curve, and **`0` = full speed
  ignoring duty**. A channel reading mode `0` is not under control even though writes appear to
  land.

## Environment assumptions

A forced-command session and a systemd timer both start with an almost-empty environment — no
login shell, no profile. Both the agent and the revert helper therefore source their config
file explicitly rather than expecting the environment to carry it.

That config file must **quote** space-separated values. An unquoted `CHANNELS=1 2 3 4 5` makes
the sourcing shell try to execute `2`.

> Addresses, hostnames, serials and keys in this directory are placeholders.
