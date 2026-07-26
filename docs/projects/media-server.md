# media-server — a second box, containerized and agent-managed

> An older machine turned into a headless, containerized media server with GPU hardware
> transcoding — a separate node the assistant can inspect and manage.

**Risk class:** not agent-controlled for changes · read-only from the assistant's side

---

## In plain English

An older PC — previous-generation CPU, an older but capable graphics card, a fresh drive — was turned
into a quiet, headless media server. It runs its services in containers (isolated, easy to update or
restart individually), uses the graphics card to do the heavy lifting of re-encoding video on the
fly, and is reachable from the rest of the house. The assistant can see its health through the
read-only [hoststat](hoststat.md) pattern, but doesn't reconfigure it.

## How it's used

- The media services run as containers, managed through a small web UI (start, stop, restart, edit).
- The graphics card does hardware transcoding, so streaming to a device that needs a different format
  doesn't peg the CPU.
- The assistant reaches it read-only to report on health — "is the media service up?" — via the same
  forced-command, look-only mechanism used for the agent's own host.

## Architecture

- **Stock server OS + a single one-shot setup script**, rather than a custom install image — more
  reliable and far easier to debug. The script updates the OS, installs the container runtime,
  installs the GPU driver and container toolkit, lays out the media folders, and brings the stack up.
- **Containerized services** behind a lightweight management UI, with a clean split between config and
  data on disk so drives can be added or repointed later without moving the apps.
- **GPU hardware transcoding**, verified to actually offload to the card rather than assumed from a
  checkbox — same "measure the effect" discipline as the rest of the system.
- The setup deliberately keeps **in-container paths stable** so every service sees the same layout,
  which removes a whole class of path-juggling bugs when wiring the services together.

## Safety model

This node predates the agent stack and isn't wired for agent-driven *changes* — the assistant's
relationship to it is **read-only reporting**. That's a deliberate scoping choice: the media box is
managed by hand and through its own web UI, and the assistant's job is to *notice* when something's
wrong (a service down, a disk filling), not to reconfigure it. If agent-driven management is ever
added, it would come through the same plan → approve → apply gate as everything else, as its own
separate decision.

## Engineering notes

The valuable pattern here is **stock-OS-plus-idempotent-script over a bespoke image**. A custom
install image is tidy in theory and miserable to debug when one step fails; a plain OS plus a
re-runnable setup script means every step is visible, individually testable, and safe to run again.
The one reboot the process needs (after the GPU driver installs) is called out explicitly rather than
left as a silent prerequisite — the same "state the sharp edge" habit as the
[gotchas tables](../06-engineering-practices.md#gotchas-tables) in every other repo.
