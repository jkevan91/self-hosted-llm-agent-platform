# What this is, in plain English

*No jargon. If you're not an engineer, start here — this page explains the whole system and
why it was hard. Every other document in this repository assumes you're technical.*

---

## The one-sentence version

I built a private AI assistant that lives on a computer in my house, and I gave it the ability
to actually operate the house's technology — check the network, control the TV, triage my mail,
manage the fans and lights, scan for security weaknesses — while making sure that even if the
AI is tricked or goes wrong, it can't do real damage.

## Why that's harder than it sounds

Most AI assistants can only talk. This one can *act*, and that changes the problem completely.

An assistant that can only answer questions has one failure mode: it says something wrong. An
assistant that can restart servers, change network settings, and read your email has a much
worse failure mode — it does something wrong, to real equipment, permanently.

And there's a specific reason to worry. AI language models can be **talked into things**. Not
just by the person using them, but by any text they read. If the assistant reads an email, and
that email contains instructions, the model may follow them. This is a real, well-documented
weakness with no complete fix.

So the central question of this whole project isn't *"will the AI behave?"* It's:

> **When the AI misbehaves — and it will — what is it actually able to reach?**

Everything I built follows from taking that question seriously.

---

## How it fits together

Five pieces, in plain terms:

**1. The brain runs in my house.** The AI model runs on a graphics card in my own computer, not
in anybody's cloud. Nothing I say to it, no email it reads, and no detail about my network is
ever sent to an outside company. This was the first decision and it shaped everything else.

**2. I text it like a person.** I message it from my phone through a chat app. Only my account
is allowed to talk to it — everyone else is refused by default, not by a filter that has to
recognise them as bad.

**3. Its abilities are separate, single-purpose tools.** The assistant can't "do things" in
general. It has a fixed set of specific tools, each one built separately: one for network
diagnostics, one for AV devices, one for mail, one for fans and lighting, one for checking on
the computer's own health, one for security scanning. Each lives in its own sealed box with only
the keys it personally needs. The mail tool cannot touch the fans. The fan tool cannot read
mail.

**4. The dangerous abilities were never built.** This is the idea I'd most want to explain. The
mail tool can search, read, label, archive, and write drafts. It **cannot send email and cannot
delete email** — not because I switched those off, but because I never wrote them. There's no
setting to flip and no way to talk the AI into it, because the ability does not exist. You
cannot misuse a button that isn't there.

**5. Anything permanent needs me.** Temporary actions happen freely — turn the lights blue, set
the fans higher for ten minutes, pause the TV. Those expire on their own; a temporary change
can't be forgotten about because it undoes itself. But permanent changes, and anything
genuinely risky, stop and wait for a human. I get shown exactly what's about to happen and I
have to say yes.

---

## The bit I'm proudest of

For the security scanner, "a human has to say yes" turned out to be harder than it sounds.

The obvious design: the AI asks for permission, gets back a permission slip, then hands the slip
back to start the job. Except — the AI is holding the slip. It can just hand it straight back to
itself. That's not a human approval, it's a formality with extra steps. I'd built exactly that
pattern elsewhere before noticing the flaw.

The fix was to make approval something the AI has **no ability to do at all**. Permission is a
file that only a human can create, by running a command on the machine or clicking a button on a
dashboard. The AI's entire world is its list of tools, and there is no tool for approving. It can
ask. It cannot answer.

The lesson generalises well beyond AI: **if a check can be satisfied by the thing being checked,
it isn't a check.**

---

## The other thing I learned: software lies about succeeding

The hardest problems in this project weren't crashes. Crashes are easy — they tell you where
they are. The hard ones were programs that **reported success and did nothing at all.**

The clearest example: I had a program controlling my computer's fans based on temperature. It
ran for weeks. Its logs looked perfect — nice tidy entries, "52 degrees, setting fans to 45%."

It had never once moved a fan.

The fan hardware was rejecting every single command, and the program was throwing the error
messages away without reading them, then writing a log entry based on what it had *decided* to
do rather than what happened. Every outward sign said healthy.

I found it by ignoring the software entirely and just measuring: command the fans to 100%, wait,
write down the speed. Command 30%, wait, write down the speed. The two numbers were identical.
That's the whole proof, and no amount of reading logs would have produced it.

I found **three separate programs** from three different manufacturers doing this same thing —
claiming success while doing nothing. It became the rule I now apply everywhere:

> **Something not complaining is not the same as something working.** If you can measure whether
> it actually worked, measure it.

There's a full write-up of each of these in [the debugging log](05-debugging-log.md) — it's
readable without being an engineer, and it's the most honest part of this repository.

## And: I keep the mistakes in writing

Two things I documented confidently turned out to be wrong — I'd claimed the fan control was
"working, verified under load," and that a migrated set of files was "all intact." Both were
later disproved by better measurement.

Rather than quietly fix those sentences, I left them in with corrections next to them. A record
that only ever gets more confident isn't trustworthy. Knowing **which claims were actually
tested and which were assumed** is the entire difference between documentation and advertising.

---

## Where to go next

| If you want… | Read |
| --- | --- |
| A tour of each piece, plain-English first | [the project pages](projects/) |
| Why the security design looks like it does | [the security model](03-security-model.md) |
| The bugs, and how each was proven | [the debugging log](05-debugging-log.md) |
| How one computer is both a gaming PC and a server | [virtualization](04-virtualization.md) |

> **A note on this repository.** The system described here is real and running. But this is a
> public copy, so every address, machine name, serial number, and password has been replaced
> with a fake placeholder, and anything that could help someone find or get into the actual
> network has been left out entirely. The engineering, the reasoning, and the findings are
> exactly as they happened.
