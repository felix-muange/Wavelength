# Wavelength 🎵

A premium, no-API-key YouTube music player.

---

## Run locally

```bash
node server.js
# Open http://localhost:3001
```

Zero dependencies. Node 18+ only.

---

## Deploy to Railway (free, public HTTPS URL, works on mobile)

Follow these steps exactly — it takes about 5 minutes.

---

### Step 1 — Create a GitHub account (if you don't have one)

Go to https://github.com and sign up. It's free.

---

### Step 2 — Create a new GitHub repository

1. Go to https://github.com/new
2. Name it `wavelength-player` (or anything you like)
3. Set it to **Public**
4. Leave everything else unchecked
5. Click **Create repository**

---

### Step 3 — Upload the project files to GitHub

On the repository page you just created, click **uploading an existing file**.

Drag and drop ALL files from this folder:
```
server.js
package.json
railway.json
.gitignore
index.html
```

Then scroll down, click **Commit changes**.

> If you're comfortable with Git, you can also do:
> ```bash
> git init
> git add .
> git commit -m "initial commit"
> git remote add origin https://github.com/YOUR_USERNAME/wavelength-player.git
> git push -u origin main
> ```

---

### Step 4 — Create a Railway account

1. Go to https://railway.app
2. Click **Login** → **Login with GitHub**
3. Authorize Railway to access your GitHub

Railway gives you **$5 free credit per month** — more than enough for this app
(a lightweight Node server uses roughly $0.50–1.00/month).

---

### Step 5 — Deploy to Railway

1. On the Railway dashboard, click **New Project**
2. Click **Deploy from GitHub repo**
3. Select your `wavelength-player` repository
4. Railway auto-detects Node.js and starts deploying

Wait about 60 seconds. You'll see build logs streaming in.

---

### Step 6 — Get your public URL

1. Click on your deployment (the card that appeared)
2. Click the **Settings** tab
3. Under **Networking**, click **Generate Domain**
4. Railway gives you a URL like: `https://wavelength-player-production.up.railway.app`

That's your permanent public URL — open it on your phone, share it, bookmark it.

---

### Step 7 — Open on mobile

Just visit your Railway URL in Safari or Chrome on your phone. No app install needed.

For the best experience on iOS:
1. Open the URL in Safari
2. Tap the **Share** button (box with arrow)
3. Tap **Add to Home Screen**
4. It works like a native app — full screen, no browser bar

---

## File structure

```
wavelength-player/
├── server.js      ← Node server (proxy + static file serving)
├── index.html     ← Full frontend app
├── package.json   ← npm config (no dependencies!)
├── railway.json   ← Railway deployment config
└── .gitignore
```

---

## How the proxy auto-detects environment

In `index.html`, the `PROXY` constant is set automatically:

```js
const PROXY = (location.hostname === 'localhost' || location.hostname === '127.0.0.1')
  ? `http://${location.hostname}:3001`  // local dev
  : '';                                  // Railway: same-origin, no prefix needed
```

This means the same `index.html` works both locally and on Railway
with no changes required.

---

## Updating the app after deployment

1. Edit files locally
2. Go to your GitHub repo → click a file → click the pencil icon to edit
3. Or push a new commit via Git
4. Railway **automatically redeploys** on every push to `main`

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Build fails | Check logs in Railway dashboard — usually a syntax error in server.js |
| App loads but search fails | Railway is running — check browser console for proxy errors |
| "Embed disabled" on videos | Normal — the app auto-skips to the next track |
| Free credit runs out | Railway charges ~$5/month after free tier — or redeploy on Render.com free tier |
