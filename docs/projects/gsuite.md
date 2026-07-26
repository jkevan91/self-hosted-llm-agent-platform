# gsuite — mail and calendar

> Search, read, and triage mail; read the calendar; track threads awaiting a reply — with **no send
> tool and no delete tool in existence.**

**Risk class:** reversible only · one gated outward-facing write (create event)

---

## In plain English

The assistant can look at mail and calendar. It can tell you what's in your inbox, sort mail into
labels, get things out of the way, write **draft** replies for you to review, and keep a list of
things you're waiting on so it can nudge you when nobody's gotten back to you.

It cannot send email. It cannot delete email. Not "we turned that off" — those abilities were never
built.

Picture an assistant given a key to your mail room but not to the outgoing mailbox. They can open
mail, read it, sort it into trays, staple a sticky note on the front, and leave a typed-up reply on
your desk for you to sign. They can't put anything in the post, and they can't throw anything away.

## How it's used

- **Look through mail** — *"what's in my inbox?"*, *"find everything from the insurance company this
  month,"* *"read me that thread with the contractor."*
- **Sort mail** — apply labels, archive out of the inbox (still findable), mark read/unread/starred,
  write a draft reply left in the mailbox for you to send yourself.
- **Track what you're waiting on** — *"I'm waiting on the landlord about the lease, give it three
  days."* It writes that to a list that survives restarts; a scheduled prompt checks twice a day
  whether a reply came in or the window lapsed, and tells you what's overdue. Answered threads tick
  themselves off automatically.
- **Calendar** — *"what's on today / this week?"*, *"find the dentist appointment."* It can create
  an event, but must show the details and get a yes first.

## Architecture

Access is **OAuth 2.0** with a refresh-token flow — the user approves access once in a browser, and
Google returns a scoped token that lives in the same mounted secrets file as every other server's
credentials, never in code. The watchlist is a small persisted store on a read-write volume that a
scheduled prompt polls; matching an incoming reply against a tracked thread is what lets an item
close itself.

## Safety model

Three layers:

1. **The dangerous capabilities don't exist.** No send, no delete, no move-to-spam — no code path to
   enable. The label tool additionally refuses `TRASH` and `SPAM` targets, so "archive this" can't
   become "destroy this" through a creative label.
2. **Everything it *can* do is reversible** — a label, an archive, a star are all two clicks to undo
   in the mail UI.
3. **Creating a calendar event needs a yes twice** — a plan call describes the event and returns a
   one-time token; nothing is created without it. Guests aren't emailed unless explicitly asked, and
   the tool ships disabled until drilled by hand.

**The honest limitation.** The OAuth scope granted (`gmail.modify`) *does* technically permit
sending — Google offers no scope that grants labels and drafts while withholding send. So the
no-send guarantee is **code-level, not scope-level**: an attacker who could replace the server
binary could send mail. The alternative (`gmail.readonly`) makes the restriction scope-enforced but
removes labeling, archiving, and drafts — most of the value. The tradeoff was made deliberately and
[written down](../03-security-model.md#principle-2--the-safest-capability-is-one-that-doesnt-exist)
rather than glossed.

## Engineering notes

Writing the plain-English summary of "no send tool exists" is what surfaced how much stronger *not
building* a capability is than disabling one. There's no flag to flip, no prompt that unlocks it, and
nothing an injected instruction in an email can reach — because reading an email is exactly the
moment a prompt-injection attack would fire, and this server reads email for a living. The residual
risk that remains — an injected agent could exfiltrate what it can *read* into a draft — is
documented, not hidden, in the [security model](../03-security-model.md#deliberate-residual-risks).
