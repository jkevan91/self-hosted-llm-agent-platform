# security-dashboard — the human surface

> One web page: live server and VM health in plain language, the change-over-time alerts, and the
> human **Approve / Deny** surface for the scanner's intrusive actions.

**Risk class:** read-only for stats · the one write it performs is approving a scan — so the whole
page is password-gated

---

## In plain English

A single web page that shows, at a glance, how the home servers are doing — in words a human can
read, not raw numbers — and lets you approve or deny the security scanner's riskier jobs with a
button.

- **Are my machines healthy?** Big tiles for the hypervisor and each VM — processor, memory, disk,
  temperature — each green/amber/red and stating what it *means*: "plenty of memory free" vs "almost
  out of memory, a program may get killed," so you don't have to interpret percentages.
- **What changed on my network?** A feed of "a new device appeared," "a new port opened," and
  anything the scanner refused to do (e.g. someone tried to point it off-network).
- **Anything waiting on me?** The scanner's dangerous jobs never run on their own; when one is
  queued it shows here with **Approve** and **Deny**. You're the switch.

## How it's used

Open it on the LAN, log in, glance at the tiles. When a scan needs sign-off, review it and click.
There's also a **Diagnose** button per machine: memory looks high, you click, and the assistant
investigates and explains *what's* eating it and your options — without changing anything.

## Architecture

```
browser (LAN, password) ──► security-dashboard (web app, container, non-root)
     ├── hypervisor API (read-only audit token)     → node/VM/storage stats
     ├── thermalctl forced-command key (read-only)   → case/CPU temps, GPU when host-visible
     └── scanner's shared data volume                → approvals (write), audit + monitor (read)
```

- **Health stats** come from a dedicated **read-only audit token** on the hypervisor — it can see
  everything and change nothing.
- **Temperatures** come through the same read-only thermal forced-command key the rest of the system
  uses. When the GPU is passed through to a VM the host can't see it, so it's reported honestly as
  "assigned to a VM right now" rather than faked to zero.
- **The scanner feed** is read from a shared volume: pending approvals, the audit log, and the
  monitoring snapshots.

## Safety model

- **Read-only for everything except approvals.** The only state it changes is approving or denying a
  scanner request — which is the entire point of it existing.
- **That one write is why the whole app is password-gated**, with a signed, expiring session cookie.
  When it approves, it writes the *identical* HMAC-signed marker the host-side approval command
  writes — so the dashboard is simply a **second trusted human approval surface**, and nothing else
  about it can start a scan.
- **The model has no path to either surface.** Approval lives entirely outside the model's tool list,
  by design (see [kali-recon](kali-recon.md#safety-model--why-the-model-cant-cheat)).
- **LAN-bound, non-root.** Not exposed beyond the local network.

## Engineering notes

The dashboard is where the system's two audiences meet: it's an operator tool, but its whole design
premise is that a number should never appear without a plain-language reading of what it means —
which is the same discipline as the project's [three-documents rule](../06-engineering-practices.md).
Writing "almost out of memory — a program may get killed" next to a percentage is trivial to build
and is the difference between a dashboard someone reads and one they ignore.

It's also the second, independent implementation of the un-forgeable approval marker — proving the
gate wasn't a one-off trick tied to the CLI, but a boundary any trusted human surface can write to
and the model still can't.
