#!/usr/bin/env node
/* QC a rendered swipe page in headless Chrome, SILENTLY.
 *
 * HARD RULE: headless Chrome on a desktop plays page audio through the real speakers, and a
 * swipe page is a wall of competitor videos. One unguarded render can start every video at once
 * with no window to close. So every Chrome this skill
 * launches, for screenshots, measurement or QC, MUST carry:
 *     --mute-audio  --autoplay-policy=user-gesture-required
 * and MUST be killed by PID the moment the check finishes. Never
 * --autoplay-policy=no-user-gesture-required. Where a check needs to know whether a video plays
 * or pauses, read the element's `paused` and `currentTime` over CDP; if play() is genuinely
 * needed, set `muted = true` on the element first. This script does all of that for you: it
 * spawns its own Chrome with the safe flags, uses a fresh tab, and kills the process it started
 * in a finally block. Use it instead of hand-rolling a Chrome command.
 *
 *   node qc_page.mjs http://127.0.0.1:8791/index.html               # 1440x789 then 390x844
 *   node qc_page.mjs <url> --width 1440 --height 789
 *   node qc_page.mjs <url> --shot /abs/path/card.png                # + a screenshot, still muted
 *
 * Serve the site over http first (video files misbehave on file://):
 *   cd <site> && python3 -m http.server 8791
 *
 * Checks: two-column layout the right way round (script left, example right and larger),
 * example stacks above the script on a phone, no horizontal overflow, and the click-to-enlarge
 * overlay (opens, meta + insight lines present, focus trapped, closes on X / Escape / outside
 * click, video paused after each close, focus returned).
 */
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Chrome / Chromium: --chrome <path>, then $CHROME_PATH or $CHROME_BIN, else the usual install locations on macOS and Linux.
const _ci = process.argv.indexOf("--chrome");
const _cflag = _ci > -1 ? process.argv[_ci + 1] : "";
if (_ci > -1) process.argv.splice(_ci, 2);
const CHROME = _cflag || process.env.CHROME_PATH || process.env.CHROME_BIN || [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
].find(p => existsSync(p));
if (!CHROME) { console.error("Chrome not found: set CHROME_PATH=/path/to/chrome (or CHROME_BIN, or pass --chrome /path/to/chrome)"); process.exit(2); }
const args = process.argv.slice(2);
const url = args.find(a => !a.startsWith("--"));
const flag = (n, d) => { const i = args.indexOf("--" + n); return i === -1 ? d : args[i + 1]; };
if (!url) { console.error("usage: node qc_page.mjs <url> [--width N --height N] [--shot out.png]"); process.exit(2); }
const shot = flag("shot", null);
const sizes = args.includes("--width")
  ? [[parseInt(flag("width", "1440"), 10), parseInt(flag("height", "789"), 10)]]
  : [[1440, 789], [390, 844]];

const port = 9200 + Math.floor(Math.random() * 700);
const profile = mkdtempSync(join(tmpdir(), "swipe-qc-"));
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  "--mute-audio",                            // HARD RULE: never remove
  "--autoplay-policy=user-gesture-required", // HARD RULE: never flip to no-user-gesture-required
  "--no-first-run", "--no-default-browser-check", "--disable-gpu",
  // Linux servers and containers: Chrome aborts with "No usable sandbox" without this
  ...(process.platform === "linux" ? ["--no-sandbox"] : []),
  "about:blank",
], { stdio: "ignore", detached: false });

const sleep = ms => new Promise(r => setTimeout(r, ms));
const results = {};
try {
  for (let i = 0; i < 40; i++) {
    try { await fetch(`http://127.0.0.1:${port}/json/version`); break; } catch { await sleep(250); }
  }
  for (const [W, H] of sizes) results[`${W}x${H}`] = await run(W, H);
  console.log(JSON.stringify(results, null, 1));
  const fails = [];
  for (const [k, r] of Object.entries(results)) {
    for (const [n, v] of Object.entries({ ...r.layout, ...r.overlay })) if (v === false) fails.push(`${k}.${n}`);
  }
  // refStacksAbove is expected false on desktop and true on a phone; scriptIsLeft the reverse
  const expected = new Set(sizes.flatMap(([W]) => W < 760
    ? [`${W}x${sizes.find(s => s[0] === W)[1]}.scriptIsLeft`]
    : [`${W}x${sizes.find(s => s[0] === W)[1]}.refStacksAbove`]));
  const real = fails.filter(f => !expected.has(f));
  console.log(real.length ? "FAIL: " + real.join(", ") : "PASS: layout + enlarge overlay OK, nothing played out loud");
  process.exitCode = real.length ? 1 : 0;
} finally {
  try { process.kill(chrome.pid); } catch {}      // kill by PID, always
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}

async function run(W, H) {
  const tab = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json();
  const ws = new WebSocket(tab.webSocketDebuggerUrl);
  let id = 0; const waiters = new Map();
  ws.addEventListener("message", e => {
    const m = JSON.parse(e.data);
    if (m.id && waiters.has(m.id)) { waiters.get(m.id)(m); waiters.delete(m.id); }
  });
  await new Promise(r => ws.addEventListener("open", r));
  const send = (method, params = {}) => {
    const mid = ++id;
    return new Promise(res => { waiters.set(mid, res); ws.send(JSON.stringify({ id: mid, method, params })); });
  };
  const ev = async expr => {
    const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
    return r.result?.result?.value;
  };
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: W < 500 });
  await send("Page.navigate", { url });
  await sleep(1600);
  // belt and braces: mute every media element in the page as well as the browser
  await ev(`[...document.querySelectorAll('video,audio')].forEach(v=>{v.muted=true;v.pause();}); true`);

  const layout = await ev(`(() => {
    const cols = document.querySelector('.ad-cols');
    const s = cols.querySelector('.ad-script').getBoundingClientRect();
    const r = cols.querySelector('.ad-ref').getBoundingClientRect();
    return {
      viewport: [innerWidth, innerHeight],
      gridTemplate: getComputedStyle(cols).gridTemplateColumns,
      scriptIsLeft: s.left < r.left,
      refIsLarger: r.width >= Math.min(340, innerWidth - 80),
      refStacksAbove: r.top < s.top,
      noHorizontalOverflow: document.documentElement.scrollWidth <= innerWidth + 1,
      zoomButtons: document.querySelectorAll('[data-zoom]').length,
      nothingPlaying: [...document.querySelectorAll('video')].every(v => v.paused)
    };
  })()`);

  const overlay = await ev(`(async () => {
    const r = {}, wait = ms => new Promise(s => setTimeout(s, ms));
    const z = document.getElementById('zoom'), btn = document.querySelector('.ad-ref [data-zoom]');
    const disp = () => getComputedStyle(z).display;
    r.startHidden = z.hidden === true && disp() === 'none';
    btn.click(); await wait(150);
    r.opens = z.hidden === false && disp() !== 'none';
    r.metaPairs = document.getElementById('zoomMeta').querySelectorAll('dt').length >= 3;
    r.hasInsights = document.getElementById('zoomWhy').querySelectorAll('li').length >= 2;
    r.focusOnClose = document.activeElement === document.getElementById('zoomClose');
    r.bodyLocked = document.body.classList.contains('zoom-open');
    const v = document.getElementById('zoomVideo');
    v.muted = true;                       // HARD RULE: muted before any play()
    const f = [...document.getElementById('zoomCard').querySelectorAll('a[href],button:not([disabled]),video[controls],[tabindex]:not([tabindex="-1"])')]
                .filter(el => !el.hidden && el.offsetParent !== null);
    f[f.length - 1].focus();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true })); await wait(60);
    r.trapWrapsForward = document.activeElement === f[0];
    f[0].focus();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true })); await wait(60);
    r.trapWrapsBackward = document.activeElement === f[f.length - 1];
    const playMuted = async () => { v.muted = true; try { await v.play(); } catch (e) {} await wait(220); };
    await playMuted(); r.playsWhileOpen = !v.paused && v.muted;
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await wait(120);
    r.closesOnEscape = z.hidden === true && disp() === 'none';
    r.pausedAfterEscape = v.paused;
    r.focusReturned = document.activeElement === btn;
    r.bodyUnlocked = !document.body.classList.contains('zoom-open');
    btn.click(); await wait(120); await playMuted();
    z.querySelector('.zoom-back').click(); await wait(120);
    r.closesOnOutsideClick = z.hidden === true; r.pausedAfterOutsideClick = v.paused;
    btn.click(); await wait(120); await playMuted();
    document.getElementById('zoomClose').click(); await wait(120);
    r.closesOnX = z.hidden === true; r.pausedAfterX = v.paused;
    btn.click(); await wait(120);
    document.getElementById('zoomTitle').click(); await wait(100);
    r.staysOpenOnInsideClick = z.hidden === false;
    document.getElementById('zoomClose').click(); await wait(100);
    const w = document.querySelector('.adcard [data-zoom]');
    r.winnersEnlargeToo = !!w;
    if (w) { w.click(); await wait(120); r.winnerOpens = z.hidden === false; document.getElementById('zoomClose').click(); }
    await wait(100);
    r.everythingSilentAtEnd = [...document.querySelectorAll('video')].every(x => x.paused);
    return r;
  })()`);

  if (shot) {
    const s = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(shot.replace(/\.png$/, "") + `-${W}x${H}.png`, Buffer.from(s.result.data, "base64"));
  }
  await fetch(`http://127.0.0.1:${port}/json/close/${tab.id}`);
  ws.close();
  return { layout, overlay };
}
