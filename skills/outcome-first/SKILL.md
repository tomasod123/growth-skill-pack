---
name: outcome-first
description: Stops word salad in anything written for a person (client emails, texts, Slack, one-pagers, briefs, handovers, SOPs, chat replies). Before drafting, write the one real-world outcome (who does what, by when); write only what gets that done; then delete every sentence that doesn't help the reader do it, and swap jargon for their words. Applies to every draft by default. Also use when the user says "too long", "word salad", "waffle", "cut this down", "make it clearer", "what do they actually need to do", "TLDR it" or "outcome first".
---

# Outcome first

People write to change what someone else does. Write that down first, send only that, and cut the rest.

## Step 1. Write the outcome line (before any draft)

`After reading this, <person> will <do what> by <when>.`

- "Do what" is something physical: pay the invoice, click Accept on the Google invite, reply "yes", record a 30-second video, leave feedback on the page.
- If the outcome is "understand X" or "be updated", ask what they'll do differently because of it. If nothing, send one line or nothing.
- If you can't write the line, you don't know what to send yet. Ask first.
- Several things needed? Number them in the order they'll do them, and say which one blocks the rest.
- A reply also answers every question they asked. Those answers stay.

## Step 2. Write only these four things

1. **What we want them to do.** In the first two lines, never under background. In a reply, straight after the answers to their questions.
2. **How, exactly.** The link, the button name, the one step.
3. **What they get.** The result for them, in their words.
4. **Why it's worth it.** One line, and only if they might not do it without it.

Greeting, sign-off and tone come from the person's own past messages. Everything else goes to a link, a collapsed "Background" block, a team task, or nowhere.

## Step 3. Cut test (on the finished draft)

Ask of every sentence: **does this help them do the outcome?**

- Yes: keep it.
- No: delete it. Don't reword it.
- Needed, but not by this reader (how we'll build it, an internal note): move it to the team task.

Delete on sight:
- What we did to get here: "I've gone through...", "I took a look at...", "After reviewing...".
- A recap of what they just told us.
- Context before the ask. The ask goes first; context after it, and only if needed.
- The same point said twice, or a closing summary of the top.
- Lists of what a linked page "also covers". They can open it.
- Hedges: "we would aim to", "it may be worth considering".
- Lead-ins: "Here's the thing:", "The short version:", "Why this matters:".

## Step 4. Jargon swap

Any word the reader wouldn't say out loud becomes their words, or "it's kind of like" plus something from their world.

- "CPL" → "what each enquiry costs you"
- "Retargeting" → "showing the ad again to people who've already been on your site"
- "DNS records" → "two lines your web person pastes into the domain settings, kind of like changing the address on your post"

## Footer (in the handover or chat, never inside the copyable text)

```
OUTCOME: <person> will <action> by <when>
CUT: <n> sentences (<before> → <after> words)
SWAPPED: <jargon> → <plain words>, or "none"
```

## Example: follow-up after a demo call

Outcome: the prospect sends the name of the person who will run the pilot.

Before, about 250 words. The one ask sat in paragraph four, after a thank-you, a recap of the call, two links and a list of features. A "next steps" list and a paragraph about the company came after it.

After, about 70 words:

> Hi Sam,
>
> Thanks for your time on the call.
>
> The one thing we need from you is **the name of the person who will run the pilot** on your side. A reply to this email is fine.
>
> Once we have it, we will send them a short setup form and book a 30-minute setup call at a time that suits them.
>
> The summary of what we discussed is here: [page]
>
> Best regards,
> Alex

## When not to cut

- Terms an ad or offer must legally carry.
- The scope beside a fee on a proposal. The client needs it to say yes.
- Numbers the reader will check against their own tools.
- Reference files (FACTS.md, a SPEC) aren't messages, but their first line is still the next action.

## Pairs with

`persona-qc` (run this skill's cut test on every message persona-qc approves). If you keep a global `~/.claude/CLAUDE.md`, add one line there: "Run outcome-first on every draft written for a person."

Source: Alex Hormozi, "The One Sentence That Shrinks Any Message by 5X" (public YouTube video): "Write down what you want to have happen in the real world as a result of what you are saying. Then tell people that part and skip the thing you were going to say originally."
