# iOS Playback Fix — Patch Instructions

Two files to replace in your repo. That's it.

---

## 1. Replace `server.py`

Drop in the new `server.py` from this folder.

**What changed and why:**

- `/stream` endpoint now responds with `206 Partial Content` when iOS sends
  a `Range` header. **This is mandatory** — iOS Safari refuses to play any
  audio stream that doesn't support byte-range requests. Without it you get
  an immediate error (MEDIA_ERR_NETWORK) that looks like a permissions error.

- Audio format filter now **excludes webm/opus formats** when iOS-safe ones
  are available. `webm` containers do not play on iOS at all — yt-dlp was
  likely picking a webm stream as "best" which works on Chrome/desktop but
  silently fails on Safari.

- Added a small in-memory cache so repeated clicks on the same track don't
  re-invoke yt-dlp.

- Added a catch-all static file route for `manifest.json`, `sw.js`, `icon.svg`.

---

## 2. Replace the `<script>` block in `index.html`

In your `index.html`, find the large `<script>` block near the bottom (the one
with `loadAndPlay`, `initYT`, audio event listeners, etc.) and replace the
**entire block** with the contents of `ios-audio-fix.html`.

**What changed and why:**

### The core iOS bug

iOS Safari enforces a strict rule: `audio.play()` must be called
**synchronously within the same call stack as the user gesture** (the `click`
event). Any `await` or async gap between the tap and the `.play()` call
causes Safari to block it with `NotAllowedError`.

Your old code did:
```js
item.addEventListener('click', async () => {
  const url = await fetch('/stream?...');  // ← async gap here
  audio.src = url;
  audio.play();  // ← too late, gesture is gone
});
```

The fix calls `audio.play()` **first, synchronously**, then sets `src` async:
```js
item.addEventListener('click', () => {
  const playPromise = audio.play();  // ← synchronous, gesture still active
  audio.src = `/stream?videoId=${id}`;  // ← then set src
  audio.load();
  playPromise.then(() => { /* playing */ }).catch(err => { ... });
});
```

### Auto-advance on iOS

When a track ends and the next one starts automatically, there's no user
gesture. Instead of silently skipping everything, the fix shows a
"Tap to continue" overlay. One tap resumes with a real gesture.

### Audio session (background play)

The fix connects the `<audio>` element into a `Web Audio API` context and
plays a 1-frame silent buffer on the first user tap. This formally opens
an iOS audio session that survives screen lock and app switching.

### Media Session API

Lock-screen controls (play/pause/prev/next) are wired up via
`navigator.mediaSession` so you can control playback from the lock screen
and Control Center.

---

## Deploy

```bash
git add server.py index.html
git commit -m "fix: iOS audio playback — range requests + gesture fix"
git push
```

Railway redeploys automatically.

---

## Testing on iPhone

1. Open the app in Safari
2. Search for something
3. Tap a track → should play immediately
4. Lock the screen → audio should continue
5. Use Control Center to pause/skip → should work
6. Let a track finish → "Tap to continue" overlay appears (expected on iOS)
