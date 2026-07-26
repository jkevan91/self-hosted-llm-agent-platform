# The projects

Nine separate pieces make up this system. Each page below follows the same shape, so you can
read at whichever depth you want:

1. **In plain English** — what it is and why it exists, no jargon
2. **How it's used** — real requests, and what actually happens
3. **Architecture** — the sanitized technical design
4. **Safety model** — what it's allowed to do, and what stops it
5. **Engineering notes** — what went wrong and what that taught

---

## The agent's capabilities

Six MCP servers. Each is a separate codebase, container, credential set, and safety posture —
[why they're separate](../02-mcp-servers.md#why-separate-servers).

| Project | One line | Risk class |
| --- | --- | --- |
| [**netadmin**](netadmin.md) | Network discovery, scanning, DNS, device config management | State-changing — two-phase gate, git-backed rollback |
| [**mediactl**](mediactl.md) | AV device control — power, playback, app launch, volume | Ephemeral only |
| [**gsuite**](gsuite.md) | Mail search/read/triage, calendar, a "waiting on a reply" watchlist | Reversible only — **no send, no delete** |
| [**thermalctl**](thermalctl.md) | Fan speeds, RGB lighting, thermal telemetry across hosts | Ephemeral + gate for persistent curves |
| [**hoststat**](hoststat.md) | Read-only host inspection — memory, processes, disk, services | Read-only — no write path exists |
| [**kali-recon**](kali-recon.md) | Security scanning, network monitoring, gated exploitation | **Highest** — subnet-locked + out-of-band human approval |

## The surfaces and the platform

| Project | One line |
| --- | --- |
| [**security-dashboard**](security-dashboard.md) | Web dashboard: plain-language health, change alerts, and the human approval surface |
| [**proxmox-platform**](proxmox-platform.md) | The hypervisor migration — one GPU shared between a gaming VM and the agent VM |
| [**media-server**](media-server.md) | A second box running containerized media services, managed by the agent |

---

## Reading order, if you only read three

**For the security thinking:** [kali-recon](kali-recon.md) → the un-self-approvable approval
gate, and why the obvious design was broken.

**For the systems work:** [proxmox-platform](proxmox-platform.md) → GPU passthrough,
physical-to-virtual conversion, and a handoff bug that reported success while starting a useless VM.

**For the debugging:** [thermalctl](thermalctl.md) → the fan curve that ran for weeks and never
moved a fan.
