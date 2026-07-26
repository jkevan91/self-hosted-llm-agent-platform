# MCP server design

Six servers, one shared foundation. Each is its own container, its own repository, its own
credentials, and its own safety posture. This page covers the design common to all of them; a
per-server tour with plain-English framing is in [docs/projects](projects/).

---

## Why separate servers

A single "do everything" server would be simpler to build and much worse to reason about. Split
by domain:

- **Credential isolation.** The mail server holds an OAuth refresh token. The hardware server
  holds an SSH key. Neither can see the other's secrets, because only declared environment keys
  are forwarded into each container.
- **Independent blast radius.** A bug in AV device control cannot touch the hypervisor.
- **Independent safety models.** Network config changes need a two-phase gate and git-backed
  rollback. Pressing pause on a media player does not. Forcing one model on both would either
  over-constrain the trivial case or under-constrain the dangerous one.
- **Independent lifecycle.** Rebuild and restart one without disturbing the rest.

---

## The shared foundation

Every server follows the same rules — see [src/foundation](../src/foundation).

### Protocol-compatibility rules

These are not style preferences. Violating them makes the server fail to load:

- Single-line docstrings only
- No rich type hints — no `Optional`, `Union`, `List[str]`
- Every parameter is a string defaulting to `""`, never `None`
- Every tool returns a formatted string, never a raw object
- Logging goes to **stderr** — stdout is the protocol transport
- No exception may escape a tool; catch and return a readable error

**Why every parameter is a string.** Schema validation is strict: a tool declaring an integer
and receiving `"7"` fails, and one declaring a string and receiving `7` also fails. Small local
models are inconsistent about which they emit. Declaring everything as a string and coercing
internally makes the tool robust to both. (Measured on the model actually in use: it emits
strings consistently — but the coercion costs nothing and removes a class of failure.)

### Safety rules for anything touching the outside world

- Treat every argument as untrusted; validate hostnames, addresses and paths
- Build subprocess argument lists directly — never through a shell
- Bound every external command with a timeout, and cap output size
- Never hardcode credentials, addresses or subnets — environment or mounted config only
- Redact secrets from logs and responses
- Run non-root; opt into capabilities only where genuinely required

---

## Designing an API for a language model

The most useful lesson from building these: **the caller is not a programmer, and it is not a
human either.** It's a model that will pass whatever the person said.

### Resolve names to identifiers inside the tool

A user says "put Netflix on the living room TV." The model passes `"Netflix"` and
`"living room"`. The underlying API wants a reverse-DNS bundle identifier and a device UUID.

The wrong design accepts identifiers and documents that requirement. The model will guess and
guess wrong — and if the API no-ops on bad input, the tool reports success while nothing
happens. (That exact bug: [debugging log #3](05-debugging-log.md#3-a-device-api-that-acks-invalid-identifiers).)

The right design resolves inside the tool: fetch the real list, match exact-ID → exact-name →
substring, act on the resolved value, and return a **disambiguation error listing the real
options** when the match is empty or ambiguous. An error that names the valid choices lets the
model self-correct in one turn.

The same pattern applies to host arguments — `thermalctl` accepts an alias, a hostname, or an
address, case-insensitively, and lists known hosts when it can't resolve one.

### Make output scannable

Tools return formatted text with consistent markers — ✅ success, ❌ error, ⚠️ warning,
📝 planned change. Both the model and the human reading the transcript parse it faster, and
consistent prefixes let the model reliably distinguish a refusal from a failure.

### Say what actually happened

Where an effect can be checked, check it, and word the result honestly. `set_fan_speed` returns
`applied=1 failed=0`, not a bare ✅ — and returns an **error** when zero channels accepted the
write, rather than a success with a footnote.

---

## The two-phase gate

For any tool that mutates persistent state:

```
plan_*   read-only. Computes the target, a diff, the caller's stated reason,
         and a one-time confirm token. Touches nothing.
apply_*  refuses without a matching, recent token. Commits before-state,
         applies, commits after-state.
```

Backed by a git repository on a mounted volume plus timestamped backups, with
`list_*_history` and `rollback_*` alongside. Change tools ship **disabled** in the agent
configuration until drilled by hand.

The gate exists so a human always sees *what* and *why* before anything runs. It's deliberately
**not** applied to ephemeral actions — ceremony on a "press pause" tool is friction that trains
people to click through prompts.

---

## Per-server notes

### netadmin — network diagnostics and device management

Discovery, port and service scans, DNS, connectivity diagnostics, remote device management.
Needs LAN reach, so it's the one server that runs with host networking and raw-socket
capability. Config changes go through the full two-phase gate with git-backed rollback.

### mediactl — AV device control

Discovery and control of AV devices: power, transport, app launch, volume. Read and ephemeral
control only — no gate. Pairing is an interactive one-time human step (a PIN shown on screen),
which is called out as a manual setup gate rather than automated around.

### gsuite — mail and calendar

Search, read, and triage mail; read calendar; track threads awaiting a reply via a persisted
watchlist that a scheduled prompt polls. **No send tool and no delete tool exist.** Calendar
event creation is the one outward-facing write and is gated.

### thermalctl — thermal and lighting control

The most complete example, included in [src/thermalctl](../src/thermalctl). Two auto-detected
fan backends:

| Backend | Requires | Notes |
| --- | --- | --- |
| **hwmon PWM** | A Super-I/O driver exposing `pwmN` | Preferred — a direct sysfs write with no vendor driver to swallow it |
| **vendor USB library** | The controller's serial | Needed for USB fan controllers; on the reference hardware it does not work at all |

hwmon wins where both are present, for exactly the reason the debugging log documents.

### hoststat — read-only host inspection

Added so the assistant could **explain** a problem, not just report the gauge reading. The
dashboard already showed "memory is high on the agent host"; what it couldn't do was say *why*.
`hoststat` gives the agent a read-only look at the host it runs on: memory breakdown, top
processes by memory or CPU, disk usage, listening sockets, and one service's status or recent
logs.

It reaches the host the same way `thermalctl` reaches the hypervisor — an SSH key **pinned to a
forced command** — but the dispatcher on the far end knows only read-only verbs
(`summary | mem | proc | disk | sockets | svc-status | svc-logs`), parses its argument into an
array with no shell involved, validates unit names by charset, and clamps counts. It logs in as an
**unprivileged** account, which is enough for "what's eating memory" and deliberately not enough to
inspect another user's process internals.

Because there is no verb that changes anything, the server has **no two-phase gate** — there is
nothing to gate. That's the design goal stated in reverse: the safest write path is the one that
was never built.

### kali-recon — subnet-locked scanning with a human-gated exploit path

The highest-risk server, and the one whose safety design is the most interesting — so it has its
own page: [projects/kali-recon.md](projects/kali-recon.md). Two boundaries that don't appear
anywhere else in the system:

- **Scope is a source-code constant**, not config — the permitted networks can't be widened at
  runtime by a prompt-injected model or a mistaken operator; every target is resolved (URLs and
  hostnames included) and checked before any tool runs.
- **Intrusive actions require an out-of-band human approval the model cannot give itself** — there
  is no MCP tool that approves, and the approval secret is never in the model's context. This is the
  corrected version of a plan→apply gate whose token was returned *to the model* (and so wasn't a
  human gate at all). The principle: **if a check can be satisfied by the thing being checked, it
  isn't a check.**

Read-only recon and monitoring run freely, in-scope; only attacking/brute-forcing is gated.

---

## Transport: from stdio subprocesses to loopback services

The servers originally ran the textbook MCP way — the agent launched each as a child process and
spoke JSON-RPC over stdio. That is simple and it works, but it has a hidden cost: **the agent
account needs container-daemon access to launch them.** When the host was hardened so the agent
account holds no container privilege at all (see
[security model, Principle 5](03-security-model.md#principle-5--the-sandbox-must-not-be-the-host)),
that launch model had to go.

Now each server runs as an **independent, root-managed system service** and speaks MCP over
**streamable-HTTP bound to host loopback**; the agent attaches by URL instead of by spawning a
process. The server code needed one small, backward-compatible change — honour a transport
environment variable, defaulting to stdio — so the same image runs either way. Loopback-only
binding keeps the endpoints off the network; verified with an external probe that the ports refuse
connections from anywhere but the host itself.

The lesson worth keeping: **a transport choice can be a security boundary.** Moving from "the
agent spawns the tool" to "the agent calls the tool" removed a whole category of privilege from the
most exposed account.
