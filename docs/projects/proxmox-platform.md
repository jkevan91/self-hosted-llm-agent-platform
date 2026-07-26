# proxmox-platform — one GPU, two workloads

> The machine hosting the agent stack also has to be a gaming PC. Those are incompatible demands on
> one GPU, and the resolution shaped the whole platform.

**Full write-up:** [docs/04-virtualization.md](../04-virtualization.md).

---

## In plain English

One physical computer has to be two things: the always-on brain for the house assistant, *and* a
gaming PC when someone's at the desk. A single high-end graphics card can't meaningfully do both at
once.

The naive answer — dual boot — means the assistant is offline the entire time the machine is in
Windows, which is exactly when a person is there and most likely to want it. So instead the machine
became a **hypervisor**: it runs two virtual computers, and the graphics card is handed to exactly
one of them at a time, manually. Game mode, work mode, nothing in between. The assistant only ever
goes offline because someone chose to game — never because software decided to.

## How it's used

Two commands: `game-mode` and `work-mode`. Each shuts down the VM currently holding the card and
starts the other. The handoff round-trips in about a minute each way, with **no reboot of the
physical host**.

## Architecture

- A single machine becomes a **Proxmox hypervisor** with two guests: a Windows gaming VM (fresh
  install) and a Linux agent VM (a physical-to-virtual conversion of the existing install, carrying
  the model server, agent runtime, and MCP servers over intact).
- **VFIO GPU passthrough:** both GPU functions bound to the passthrough driver at boot, IOMMU in
  passthrough mode, the vendor's kernel driver blacklisted so it can't claim the card first. The card
  landed alone in its own IOMMU group, so no ACS override was needed.
- **The GPU is managed dynamically, not declared statically in both VMs.** `work-mode` attaches the
  PCI device to the stopped Linux VM and starts it; `game-mode` detaches it and starts Windows. This
  is the fix for a real bug — see below.

## Safety model

This isn't a security boundary like the MCP servers, but it carries hard operational constraints that
are written as explicit "do not violate" rules, because the cost of rediscovering them is
unrecoverable:

- **Specific pass-through storage is never interpreted by the host** — a vendor storage pool passed
  through raw must reassemble in the guest untouched; the host must never try to mount or rebuild it.
- **Disks are addressed by stable serial / `by-id`, never by device letter** — letters shift between
  boots, and a "never wipe this disk" warning once ended up pointing at the wrong device.
- **A specific firmware recovery option is never accepted.**

These live in a "hard constraints" list precisely so neither a human nor a model re-derives them the
expensive way. See [engineering practices](../06-engineering-practices.md#safety-conventions-that-repeat).

## Engineering notes

Two findings from this build stand out:

- **The handoff was silently broken at first** — both mode scripts only did "stop the other VM, start
  this one," but the Linux VM's config had **no GPU device declared at all.** `work-mode` would start
  the agent VM with no GPU and report success, because the VM *did* start — it just started useless.
  The fix (manage the device dynamically) is the same class of bug as the rest of this project: a
  success return that didn't mean the thing worked. Full detail in
  [virtualization](../04-virtualization.md#the-handoff-and-a-bug-worth-describing).

- **The most expensive bug wasn't virtualization at all** — an installer hung on "waiting for /dev to
  be fully populated" for hours; the cause was an **empty front-panel card reader** presenting an
  unreadable block device that made device enumeration never settle. Two plausible software suspects
  were investigated and cleared first.

And one honesty correction lives here too: a migrated storage pool was claimed "all data intact," then
walked back to "pool health verified, files not checked" — because that's what had actually been done.
The corrected claim [stays in the record](../06-engineering-practices.md#honest-after-action-reports).
