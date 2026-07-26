# Self-hosted LLM agent platform

A home lab where a **locally-hosted language model** operates real infrastructure through
purpose-built [MCP](https://modelcontextprotocol.io) servers — network diagnostics, media
devices, mail and calendar, and hardware thermal/lighting control — reached from a phone over
a chat client.

No cloud inference. No vendor agent framework. The model runs on a GPU in the house, and every
capability it has was designed, threat-modelled, and built as a separate service with its own
safety posture.

> **About this repository.** This is a sanitized public write-up of a private production
> system. Hostnames, addresses, serials, keys and account identifiers are placeholders. The
> architecture, the code patterns, and every engineering finding are real.

---

## What this demonstrates

| Area | Evidence |
| --- | --- |
| **Security engineering** | An agent that controls a hypervisor without ever holding a shell on it — SSH forced commands, verb allowlists, capability-scoped keys |
| **Systems / virtualization** | Bare-metal → Proxmox migration, VFIO GPU passthrough, physical-to-virtual conversion, a single GPU handed between two VMs with no host reboot |
| **API & protocol work** | Four MCP servers over stdio JSON-RPC, OAuth 2.0 refresh-token flows, hardware control via sysfs/HID |
| **Debugging rigor** | Three separate "reports success, does nothing" bugs found and proven by measurement — see [the debugging log](docs/05-debugging-log.md) |
| **Operational discipline** | Dry-run-by-default tooling, two-phase change gates, documented rollback paths, honest after-action reports |

---

## Architecture

```
         phone
           │  chat message
           ▼
    ┌─────────────┐
    │ chat gateway│  allowlisted users only
    └──────┬──────┘
           ▼
    ┌──────────────────────┐        ┌────────────────────┐
    │   agent runtime      │───────▶│  local LLM server  │  GPU inference
    │  (tool orchestration)│        │  (OpenAI-compatible)│  64k context
    └──────┬───────────────┘        └────────────────────┘
           │  MCP over stdio (one container per server)
           ├──────────────┬───────────────┬──────────────┐
           ▼              ▼               ▼              ▼
      ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐
      │ netadmin│   │ mediactl │   │  gsuite  │   │ thermalctl │
      │ network │   │ AV device│   │ mail/cal │   │ fans + RGB │
      │  diag   │   │  control │   │          │   │            │
      └────┬────┘   └────┬─────┘   └────┬─────┘   └─────┬──────┘
           │             │              │               │
           ▼             ▼              ▼               ▼
       LAN hosts     AV devices     Google APIs    hypervisor +
                                                   media server
                                                  (forced-command SSH)
```

Everything below the agent runtime lives in its own container, running non-root, holding only
the credentials it needs.

---

## The physical layer

A single machine hosts the whole stack as a **Proxmox hypervisor**:

- **VM A — gaming** (Windows): gets the GPU when the operator wants to game
- **VM B — the agent stack** (Linux): local model + agent runtime + MCP servers

One GPU, handed between them **manually and exclusively** — never split, never automatic, so
the assistant only goes offline when that's a deliberate choice. The handoff round-trips in
about a minute each way with **no host reboot**, by attaching and detaching the PCI device on
the stopped VM rather than declaring it statically in both configs.

A second box runs media services and is managed by the same agent.

See [docs/04-virtualization.md](docs/04-virtualization.md).

---

## The MCP servers

| Server | Purpose | State-changing? |
| --- | --- | --- |
| **netadmin** | Host discovery, port/service scans, DNS, connectivity diagnostics, device config management | Yes — two-phase gate, git-backed rollback |
| **mediactl** | AV device discovery and control (power, transport, app launch, volume) | Ephemeral only |
| **gsuite** | Mail search/read/triage, calendar read, a "waiting on a reply" watchlist | Reversible only — **no send, no delete tools exist** |
| **thermalctl** | Fan speeds, RGB lighting, thermal telemetry across hosts | Ephemeral + a two-phase gate for persistent curves |

They share a common foundation — see [docs/02-mcp-servers.md](docs/02-mcp-servers.md) and
[src/foundation](src/foundation).

---

## The security question this project is really about

> If a language model can run commands on your infrastructure, and language models can be
> talked into things, what stops a malicious email from rebooting your server?

Three answers, applied in layers:

**1. The agent never holds general-purpose access.** `thermalctl` needs to control fans on the
hypervisor from inside a guest. The lazy version is a root SSH key. Instead its key is pinned
to a forced command that accepts six verbs and rejects everything else — including a valid
verb with a shell injection appended. Verified against a live host:

| Sent | Result |
| --- | --- |
| `ping` | ✅ allowed |
| `id` | ❌ `unknown verb` |
| `cat /etc/shadow` | ❌ `unknown verb` |
| `fan set 50; rm -rf /tmp/x` | ❌ `illegal characters` |
| `` status `id` `` | ❌ `illegal characters` |
| *(bare shell request)* | ❌ `no command` |

**2. Dangerous capabilities don't exist rather than being disabled.** The mail server has no
send tool and no delete tool — not toggled off, not implemented. The most reliable way to stop
an agent doing something is to give it no code path that does it.

**3. Anything persistent needs a second human-visible step.** Momentary actions (set a fan to
60% for ten minutes) are bounded by a floor clamp and a mandatory expiry. Permanent changes
(rewrite the fan curve, change a device config) require a `plan_*` call that shows a diff and
returns a one-time token, then an `apply_*` call that refuses without it.

Full reasoning in [docs/03-security-model.md](docs/03-security-model.md).

---

## The findings I'm most proud of

Not features — bugs. Three cases where software reported success and did nothing:

1. **A fan curve that never controlled the fans.** Running for weeks, logging tidy transitions,
   changing nothing. The vendor library rejected every write; the script discarded stderr.
   Proven by commanding 100% then 30% and measuring **no RPM change**.
2. **A lighting CLI that exits 0 and no-ops.** Prints a full successful device detection,
   changes nothing. Only a different code path in the same tool actually writes.
3. **A device API that acks invalid identifiers.** Accepts any app ID, returns no error, does
   nothing — so the tool reported ✅ while the device sat idle. Fixed by resolving
   human-friendly names to real IDs *inside* the tool.

The through-line: **an API that doesn't raise is not an API that worked.** Where the effect can
be measured, measure it. Full write-ups in [docs/05-debugging-log.md](docs/05-debugging-log.md).

---

## Repository map

```
docs/
  01-architecture.md        the stack, layer by layer
  02-mcp-servers.md         server design, the shared foundation, LLM-facing API design
  03-security-model.md      threat model and the controls that answer it
  04-virtualization.md      Proxmox, VFIO passthrough, P2V, the GPU handoff
  05-debugging-log.md       silent-failure bugs, how each was proven
  06-engineering-practices.md  dry-run tooling, docs policy, after-action reports
src/
  foundation/               the rules every MCP server in this system follows
  thermalctl/               the forced-command agent + MCP server (most complete example)
```

## License

MIT — see [LICENSE](LICENSE).
