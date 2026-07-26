# kali-recon — subnet-locked scanning with a human-gated exploitation path

> The full security-tester's toolchain, wrapped so it can only ever be pointed at the home network,
> and so nothing intrusive runs without an out-of-band human yes the model has no way to give itself.

**Risk class:** highest in the system · scope hard-coded in source · out-of-band un-self-approvable
approval

---

## In plain English

This gives the assistant a professional penetration-tester's toolbox — the tools used to find weak
spots on a network — behind two welded-on rails: it can only ever be pointed at *your own* network,
and it can never break into anything without you personally saying yes first.

Think of giving a very capable security guard a full set of lock-picks and diagnostic gear, with two
rules bolted on:

1. **The guard is physically fenced onto your property.** The list of addresses it may inspect is
   built into the machine — not a setting, not a preference. Even if someone tricked it with a forged
   note ("go check the neighbour's house"), the fence won't let it off your land.
2. **The guard can look all day, but can't force a lock without your key.** Looking around — which
   doors are open, which locks are old — happens freely. Actually *trying to pick a lock*
   (password-guessing, running an exploit) stops and waits. You get a request; you turn your key
   before anything happens. **The guard has no way to turn that key itself.**

## How it's used

- **Look around** — find live devices, their services and versions.
- **Flag weaknesses** — vulnerability checks, web-server scans, TLS/SSL and SSH configuration audits,
  and (with a login) deep hardening audits of your own machines.
- **Keep watch over time** — periodic snapshots, then a diff: a new device appeared, a new port
  opened, a service version moved. That's the early warning.
- **Test defences, on a leash** — password-strength testing and exploit validation against your own
  kit, only after you approve each one by hand.
- Every single action is written to a permanent audit log.

## Architecture

Read-only recon runs freely; intrusive actions route through a plan → approve → apply gate.

```
model ──► kali-recon (real LAN adjacency, non-root, no added caps)
   │
   ├── read-only recon (nmap, web/TLS/SSH scans, module search) ─┐
   ├── monitoring (snapshot + diff over time)                    ├─ every target passes check_scope()
   ├── credentialed audit (SSH to an owned inventory host)       ─┘
   │
   └── plan_intrusive_action ──► [human] approve ──► apply_intrusive_action
                                  (out-of-band; no MCP tool can approve)
```

### The two hard boundaries

**1. Scope is hard-coded and cannot be widened at runtime.** The permitted networks are a Python
constant in the source — deliberately **not** an environment variable or config value. A
prompt-injected model or a mistaken operator cannot change it; widening scope means editing the
file, rebuilding, and re-reviewing, which shows up in git. Every target (IP, CIDR, hostname, or URL)
is resolved and checked before any tool runs:

- a **CIDR** must be a *subset* of a scope net, so `0.0.0.0/0` or a broad `/16` fail even though they
  overlap;
- a **bare IP** must be a member;
- a **hostname** is resolved and **every** address it returns must be in scope — a name that points
  anywhere outside is refused, which closes the DNS-rebinding / off-net-name gap.

A refusal is logged with status `REFUSED-SCOPE`.

**2. Intrusive actions need an out-of-band human approval the model can't forge.**

| Step | Actor | What happens |
| --- | --- | --- |
| `plan_intrusive_action` | model | scope-checked; writes a request with the concrete command line and a canonical string to sign; **runs nothing** |
| approve | **human** — a host command or a dashboard button | reviews it and writes `HMAC(secret, canon)` as an approval marker |
| `apply_intrusive_action` | model | refuses unless the marker exists, is fresh, and its HMAC matches |

## Safety model — why the model can't cheat

This is the piece I'd point an interviewer to first, because the *obvious* design is broken and I
built the broken version elsewhere before seeing it.

The obvious gate: the tool returns a confirm token to the model, and the model passes it back to
apply. But **the model is holding the token** — it can hand it straight back to itself. That's not a
human approval; it's a formality. (That exact weakness was a finding against an earlier plan→apply
gate in this same stack.)

The fix makes approval something the model has **no ability to perform**:

- There is **no MCP tool that writes an approval marker.** The model's entire interface is its tool
  list, and approval is not in it. It can ask; it cannot answer.
- The approval secret is **never in the model's context**, so it can't compute the HMAC.
- The command line is rebuilt server-side from a per-kind allowlist, and the HMAC covers
  `id | kind | target | argv` — so an approved request can't be swapped for a different command.

The generalizable principle: **if a check can be satisfied by the thing being checked, it isn't a
check.** The trust boundary has to be a thing the untrusted component structurally cannot reach.

## Engineering notes

- **The container is non-root and needs no added capabilities** — all scans are TCP connect scans,
  so nothing here requires raw sockets or extra privilege.
- **Read vs. run is the line.** Searching an exploit database is read-only and ungated; *running* a
  module is intrusive and gated. The gate is on effect, not on tool family.
- **Layered, not either/or.** Scope-locking and the approval gate are independent: scope stops it
  pointing anywhere it shouldn't; approval stops it *attacking* even in-scope without a human. Either
  alone would leave a hole the other covers.
