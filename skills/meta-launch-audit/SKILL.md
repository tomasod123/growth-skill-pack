---
name: meta-launch-audit
description: The standard audit for any Meta ads campaign, B2B / SaaS or a local clinic client. Pre-launch gate (account, targeting, budget, lead form, compliance), a visual check of every creative (premium, on-brand, never AI-looking), a hook/body/CTA review of every video, the CRM lead path end to end (GoHighLevel or similar), and for live campaigns the performance, kill/scale and payback maths. Produces one AUDIT.md with a verdict (DO NOT LAUNCH / LAUNCH + fix / READY) and a fix list your media buyer can run. Use when the user says "stress-test the campaign", "audit the ads", "pre-launch check", "can we launch", "is it ready to go live", "check the ad account", "check the creatives", "review the hooks", "what's the payback", "why is CPL up", or before ANY campaign is switched on.
---

> **Running this skill's scripts (applies to every command below).** Each Bash call is a fresh shell, so load the keys in the same call as the script: `set -a; source ~/.claude/skills/.env; set +a; <command>`. Use `~/.claude/skills/.venv/bin/python3` in place of `python3` when that venv exists (it holds the pip packages from SETUP.md). Run from the user's working folder; outputs go to `./meta-launch-audit-output/`.

# Meta launch audit

**Outcome:** after this runs, the person switching the ads on knows the one thing blocking launch (or that nothing is), and who fixes what in how many minutes.

Why it exists: it is common for every automated config check to come back green while the ads are still pointed miles away from the business, or the lead form drops leads on the floor. This audit forces the map, the creative and the lead path to be looked at, not just the settings.

Every Bash call that runs a script starts with `set -a; source ~/.claude/skills/.env; set +a; ` in the same command (each Bash call is a fresh shell) and uses the absolute path `~/.claude/skills/meta-launch-audit/scripts/...` (needs `META_ACCESS_TOKEN`, optionally `OPENAI_API_KEY`, `META_GRAPH_VERSION`). Output goes to `./meta-launch-audit-output/<date>/` unless the user gives another folder.

## When
| Moment | Run | Who | Time |
|---|---|---|---|
| Day before launch | Steps 1-6 | Claude runs, media buyer fixes | 20 min |
| Launch day, before switch-on | Steps 1 + 5 again | Media buyer | 5 min |
| Day 3, day 7, then weekly | Step 7 (live) | Claude runs, account owner decides | 10 min |
| Any new creative | Steps 3 + 4 | Claude, owner approves | 5 min/ad |

## Step 0: set your thresholds (once per account)
Copy `config/thresholds.example.json` to `config/thresholds.json` and set: target CPL, the multiple of target CPL at which a zero-lead ad is a kill candidate, the CTR and hook-rate floors, frequency ceiling, max local radius, ads per ad set, minimum daily budget per ad. Every value ships null; `_how_to_set` in the file says how to derive each one from your own last 90 days. Any check whose threshold is null is skipped and listed in AUDIT.md as "threshold not set, skipped", so tell the user which ones are off. Pass with `--config`.

## Step 1: the API sweep (2 min, read-only)
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/meta-launch-audit/scripts/meta_audit.py \
  --act "$META_AD_ACCOUNT_ID" --postcode "<UK postcode>" | --latlon "<lat,lon>" --town "<town>" \
  --market UK|IE|AU|US|CA --mode local|b2b --creatives \
  --config ~/.claude/skills/meta-launch-audit/config/thresholds.json \
  --out ./meta-launch-audit-output/<mon-dd>-launch
```
It checks: campaign objective and special ad categories; **business inside the geo circle** (a region "place" with a radius is centred on the REGION, not the business; this is the most common silent targeting bug); radius width; age 18+; optimisation vs destination; pixel if website conversions; end dates; ads per ad set; Meta issues and review feedback; IG account attached; one lead form per offer; URL parameters (utm) on every ad; budget per ad; copy compliance (step 2 rules); the town in the copy; a priced/free offer in the copy. With `--creatives` it downloads every image and video to `creatives/` and builds `contact-sheet.jpg`.

`--postcode` uses the free postcodes.io lookup (UK only). Outside the UK, pass `--latlon` (right-click the address in Google Maps to copy it). `--mode b2b` skips local geo and local-health copy rules and applies the B2B rules instead.

**Use a read-only token.** It cannot fix or switch anything on. Every fix is a person in Ads Manager. Never say "I'll fix it"; hand over the exact click path.

Not readable by the API (do by eye, step 5): account billing/quality, often lead form contents.

## Step 2: compliance (automatic + 2 min by eye)
The script flags by regex; a person still reads every primary text, headline and on-screen line once.

**Local health / aesthetics (UK/IE):** never name, imply, price or make bookable a prescription-only medicine: toxin brands (Botox, Dysport, Bocouture...), "botulinum", "anti-wrinkle", "wrinkle relaxing", "baby botox", fat dissolving (Aqualyx, Lemon Bottle), GLP-1 weight-loss drugs (Mounjaro, Wegovy, semaglutide: regulators actively enforce this, top severity). Fillers, skin boosters, microneedling, peels and lasers can generally be named. No guarantees, "permanent", "pain-free", "no downtime", "look 10 years younger". No "your wrinkles / are you overweight" (Meta Personal Attributes policy). No scarcity counters, no "worth £X". "Free" once at most. When the offer is priced, put an **18+ line** and **T&Cs apply** in the primary text; imaging or scan offers say "imaging, not a medical diagnosis". Use the words the client uses for their customers (some regulated providers must say "patients").
**AU:** add no before/after, no patient results and no testimonials about clinical outcomes (Ahpra cosmetic advertising guidelines).
**US:** check FDA/FTC rules on claims and any state medical board advertising rules; Meta restricts health and wellness advertisers from sharing some health-related events and building some custom audiences, so check what your pixel sends.
**B2B / SaaS:** no income or revenue figures promised to the viewer, no guarantees, no business-opportunity framing, no scarcity counters. For clinical / healthcare software: no unsubstantiated clinical outcome claims, no implied regulatory clearance you do not have, and "HIPAA compliant" or "SOC 2" only if you can back it with the actual attestation. If testimonials show results, add a "results vary" line.

If you have the `persona-qc` skill, run its compliance lens on any new copy.

## Step 3a: plan before you render (2 min per concept, saves rounds)
Write one line per concept BEFORE any pixels: the winner it copies (from your own account history or an ad library), the photo, where the faces sit in EACH ratio, where the text block goes, the hook, the benefit line. Rules:
- The photo is most of the ad and shows something happening (treatment, device, consult, product in use). A person sitting on a bench is not "what's going on".
- Square/feed source photos cannot fill a 9:16 frame without pushing faces under the Instagram header: use a sharp photo band over a blurred copy of itself, faces below y285.
- Text never over a face. Offer once in a badge or pill, never repeated twice on one ad. Badge labels must fit inside their shape.
- Benefit lines, not neutral ones: what they see, what they stop wasting, what they get, the money coming back.
- Every device, tech or AI claim checked against the manufacturer or product spec for THAT model before it goes on an ad (UK CAP code 3.1 substantiation; same idea everywhere).

## Step 3b: automatic creative QC (every render, before anyone sees it)
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/meta-launch-audit/scripts/creative_qc.py ./renders --out ./meta-launch-audit-output/qc
```
Needs `tesseract` and `pip install "opencv-python-headless<5" numpy pillow`. OCRs every text line, then checks WCAG contrast vs surroundings (FAIL < 3:1), text size (FAIL < 1.5% of width, legal lines < 1.3%), the 9:16 safe zone y285-y1380 + 65px sides, edge margins, and text over a detected face. Writes QC.md, qc.json and annotated copies (red fail, amber warn, blue faces). Known false positives: neon signs or packaging in the photo read as text; tiny logo wordmarks under the Reels card are WARN, not FAIL. It does NOT see a label overflowing a badge or a cluttered background: still do step 3c by eye.

## Step 3c: visual check of every creative (look at contact-sheet.jpg; 1 min per ad)
Score each ad PASS/FIX on these seven. Any FIX on 1-3 blocks that ad.
1. **Not AI-looking.** Real people, real location, real light. No plastic skin, warped hands or text, stock smiles, gradient-blob backgrounds. The client's own photos beat anything generated.
2. **Premium.** Sharp (video at least 1080x1920, stills 1080 wide; 576x1024 is a FIX), well lit, people composed and not mid-word. A webcam or video-call grab of the founder/practitioner is a FIX: swap for a shoot photo.
3. **On-brand.** The client's own kit only (fonts, colours, logo). Never the agency's colours on a client ad. Logo legible but small.
4. **Offer readable in 1 second at phone size.** The offer (price + what + town for local; outcome + who it is for in B2B) is the headline, not small print. "Who we are" is the subline. Soft brand lines with no offer rarely produce leads.
5. **Every ratio is a true re-typeset** (9:16, 4:5, 1:1, 1.91:1): no square on blurred bars, no dead half-frame, text never below ~28px at 1080 wide.
6. **Safe zone:** all readable text inside y285 to y1380 on 1080x1920, 65px from each side (the Reels CTA card starts around y1404).
7. **Nothing that breaks step 2 in the pixels:** product boxes, leaflets, screens showing before/afters, third-party handles, needles near faces, fake UI notifications.

## Step 4: video review (hook / body / CTA)
Transcribe with OpenAI `whisper-1` (`OPENAI_API_KEY`) and read on-screen text with ffmpeg frame grabs + tesseract. The Graph `source` field sometimes downloads the video; if not, use the original master. Never trust Whisper for names or towns: check against the brief. Passing a names prompt to Whisper on short clips can make it hallucinate; re-check with an empty prompt.
- **Hook (0-3 s):** average watch time on cold traffic is a few seconds, so the offer or the problem must land by second 2. A person-to-camera opener with one clear offer card is a reliable shape. "Hi, I'm X" with no offer until second 10 is a FIX.
- **Body:** one concrete promise the viewer can picture (what the scan shows, what happens at the visit, what the dashboard does on day one); captions on; person + captions usually beats music-only.
- **CTA:** price or offer, what they get, where (local), what to tap, 18+/T&Cs if needed, held at least 2 s, inside the safe zone.
- Diversity: count distinct ideas (a different reason to buy, problem, audience, format or person), not files. Reworded hooks on one body count as ONE concept; Meta's public Andromeda guidance asks for creatively diverse ads. If you have the `ad-library` skill, read what has worked before suggesting new hooks.

## Step 5: the lead path, end to end (media buyer, 10 min)
1. If you have the `ghl-account-audit` skill, run it on the client location (P0s block launch): lead workflows published, alerts go to the person who calls (not the owner's mobile), custom values filled, T&C link works, opt-out workflow published. Otherwise check the same by hand in your CRM.
2. Lead form by eye: privacy URL loads, fields = full name + phone + email (+ one qualifier), thank-you screen says who calls and when, "Higher intent" on.
3. **One test lead** through Meta's Lead Ads Testing Tool (developers.facebook.com/tools/lead-ads-testing), named "Test <date>". Tell the client's caller first, because the alert really fires; get the account owner's OK before any test into a client account. Pass = the contact appears in the CRM with the right tags AND the alert arrives AND the first text/email sends. Delete the test contact after.
4. Billing: card valid, account not in grace period (Business Settings > Billing).

## Step 6: verdict + handover
Verdict = any P0 means **DO NOT LAUNCH**. Write the top line into the client handover note or launch task: verdict, the P0s with click paths, who, minutes. The media buyer fixes, re-runs step 1, ticks.

## Step 7: live campaigns (day 3, day 7, weekly)
```bash
set -a; source ~/.claude/skills/.env; set +a; python3 ~/.claude/skills/meta-launch-audit/scripts/meta_audit.py --act "$META_AD_ACCOUNT_ID" --latlon "<lat,lon>" --days 7 \
  --customer-value <first purchase value> --lead-to-customer <rate, e.g. 0.2> [--ltv <12-mo gross profit>] \
  --config ~/.claude/skills/meta-launch-audit/config/thresholds.json --out ./meta-launch-audit-output/<mon-dd>-live
```
Leads count `action_type == 'lead'` ONLY (substring matching double counts grouped lead actions). Working rules (numbers come from your config; unset ones are skipped):
- Do not change anything until each ad has spent a meaningful multiple of target CPL over several days, unless leading indicators are dire (very low CTR with zero leads).
- Kill an ad that has spent your kill multiple of target CPL with 0 leads. Low hook rate = new first 3 s, same body. High frequency on a local audience = new concepts.
- Scale a winner in place in modest steps every few days; duplicating a proven ad into a new ad set resets learning and often performs far worse.
- **Payback:** CAC = spend / new customers; front-end cash ROAS = first-purchase cash / spend; LTV:CAC from `--ltv`. Front-end ROAS under 1 is fine only if LTV:CAC is healthy and the business can float the cash; otherwise lift the offer price or the lead-to-customer rate (speed to lead, a call within minutes) before touching the ads. Pull real customers from the CRM (GHL opportunities/appointments), not guesses, once there are 2+ weeks of data.
- If the client's numbers are going on a client-facing page: under-promise, no CPL/lead forecasts.
- For the deeper weekly read, use `meta-ads-analyst`.

## Gotchas learnt the hard way
- Region "place" + radius centres on the region, so a business on the edge of a city can sit outside its own circle. Always set the business address or a pin as a custom location.
- Automated config checks can be nearly all green while the geo is wrong: config checks are not a substitute for looking at the map.
- A lead form the system user cannot read is normal; check it by eye, don't report it "missing".
- Video `source` downloads sometimes come back at upload resolution: if it reads 576 wide, the uploaded file is low-res, get the master.
- No URL parameters on any ad means instant-form leads can't be tied to a creative, so CPL per ad is guesswork. Paste the utm string on every ad before launch.
- A text-only compliance read is not enough: drawn buttons, old labels, doubled CTAs in outpainted bands and fake notifications only show in the pixels. Open every ratio.

## Files
- `scripts/meta_audit.py`: the sweep (GET only). Output AUDIT.md, raw.json, creatives/, contact-sheet.jpg.
- `scripts/creative_qc.py`: contrast / size / safe-zone / face-overlap checker for statics (step 3b).
- `config/thresholds.example.json`: your kill/scale/structure thresholds.
- Related pack skills: `ghl-account-audit` (step 5), `meta-ads-analyst` (deeper live diagnosis), `persona-qc` (compliance lens on new copy), `ad-library` (what has worked), `static-ad-factory` (making the statics).
