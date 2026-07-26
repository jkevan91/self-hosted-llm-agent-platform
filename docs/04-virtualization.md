# Virtualization — one GPU, two workloads

The machine hosting the agent stack also has to be a gaming PC. Those are incompatible demands
on one GPU, and the resolution shaped the whole platform.

---

## The problem

A dual-boot arrangement means the assistant is offline whenever the machine is in Windows —
which is exactly when someone is at the desk and most likely to want it. Running both under a
hypervisor solves availability, but a consumer GPU cannot be meaningfully shared between two
VMs.

## The decision

Convert the machine to a **Proxmox hypervisor** with two guests:

- **VM A — gaming** (Windows): a fresh install
- **VM B — the agent stack** (Linux): physical-to-virtual conversion of the existing install,
  carrying the model server, agent runtime and MCP servers intact

The GPU is passed to **exactly one at a time, manually**. Never split, never automatic.

**Why manual is the right call.** Automatic handoff sounds better and is worse: the assistant
would disappear mid-conversation because something decided a game was starting. Manual means
the only thing that takes the assistant offline is a deliberate choice, and the mental model
stays trivial — `game-mode` or `work-mode`, nothing else.

---

## Passthrough setup

Both GPU functions (VGA and audio) bound to `vfio-pci` at boot, IOMMU in passthrough mode, and
the vendor's kernel driver blacklisted so it can't claim the card first.

Two things worth recording:

- **The current-generation Rust kernel driver for this vendor** binds early and hangs on this
  card. It must be blacklisted explicitly — the older driver name that most guides mention isn't
  enough on a modern kernel.
- **Releasing the boot framebuffer permanently blanks the local console** on a machine with no
  integrated graphics. That's the cost of clean passthrough, and it makes SSH reachability a
  hard prerequisite: confirm it *before* the reboot that applies it, or the host becomes
  unreachable with no way to see why.

The card landed alone in its own IOMMU group, so no ACS override was needed.

**It worked first try, with no vendor error code, no ROM file, and no reset quirk.** Modern
cards handle function-level reset cleanly; a lot of the folklore around GPU passthrough
describes hardware from several generations ago.

---

## The handoff, and a bug worth describing

The scripts are `game-mode` and `work-mode`, dry-run by default. Both shut down the VM that
currently holds the card and start the other.

**The first implementation was silently broken.** Both scripts only did "stop the other VM,
start this one" — but the Linux VM's config had **no passthrough device declared at all**.
`work-mode` would have started the agent VM with no GPU and reported success, because the VM
did start. It just started useless.

The fix was to manage the device **dynamically** rather than declaring it statically in both
configs:

```
work-mode:  qm set <linux-vm>  -hostpci0 <gpu>      # attach, then start
game-mode:  qm set <linux-vm>  -delete hostpci0     # detach, then start Windows
```

Static-in-both looks tidier and fails badly: the second VM to start hard-fails with the device
busy, and it also blocks the legitimate case of running the Linux VM GPU-less alongside Windows.

Two related details:

- **A passthrough device attaches only at VM start.** It can never be hot-added, so `work-mode`
  must shut the VM down first if it's already running.
- **The Linux VM deliberately does not get the primary-VGA flag.** That flag makes the card the
  guest's primary display, which costs a headless VM its virtual console — and with the physical
  console blanked, that console is the last resort when SSH breaks.

---

## Results

Verified on real hardware, round-tripped repeatedly:

| Measure | Result |
| --- | --- |
| Handoff time | ~45–75 s each way |
| Host reboots required | **none** |
| GPU in Linux guest | driver loads, model runs at 100% GPU with full context |
| GPU in Windows guest | device status OK, no error code |
| Driver reinstall after moving | **not needed** |

The card re-enumerates at the same PCI address in both guests, so neither guest's driver
notices it moved. The contingency plan for reinstalling drivers after each handoff went unused.

---

## Migration lessons

**The most expensive bug was not virtualization.** An installer hang — "waiting for /dev to be
fully populated" — cost hours and turned out to be an **empty front-panel card reader**
presenting an unreadable block device that made device enumeration never settle. Two plausible
suspects were investigated and cleared first. The actual fault had nothing to do with the
software being installed.

**Address disks by serial, never by letter.** Device letters shifted between boots as hardware
was unplugged during troubleshooting, to the point where a documented "never wipe this disk"
warning ended up pointing at the wrong device. Every disk reference is now a stable
`by-id`/serial path.

**Storage passed through raw was never interpreted by the hypervisor**, so a vendor-specific
storage pool reassembled intact in the guest. Verifying pool *health* is not the same as
verifying *files*, though — a claim of "all data intact" was later walked back to what had
actually been checked. That distinction matters more than it sounds: the check that was run
and the claim that was made had drifted apart.

**A guest agent added to a running VM doesn't work until a full stop/start.** The virtual serial
channel it needs is only attached at VM start, so the guest has no device to bind to. A reboot
*inside* the guest does not fix it, which produces a confusing "installed but dead" state that
resolves itself on the next cold boot.
