Wavelength 🎵
A premium, no‑API‑key YouTube music player with background playback and PWA support – works offline after first visit, and can be installed to your phone’s home screen like a native app.

🚀 Run locally
Prerequisites: Python 3.9+ and pip.

bash
# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn server:app --host 0.0.0.0 --port 3001
Then open http://localhost:3001 in your browser.
That’s it – no API keys, no accounts required.

📱 Progressive Web App (PWA)
After visiting the site once, you can install it as a standalone app:

iOS Safari: tap the Share button → “Add to Home Screen”

Android Chrome: tap the menu → “Install app”

The app will open in full‑screen mode with a premium icon, and even works offline thanks to the included service worker.

☁️ Deploy to Railway (free, public HTTPS URL)
Railway gives you a free $5 monthly credit – more than enough for this lightweight Python service.

1 – Create a GitHub repo
Go to GitHub and create a public repository (name it wavelength-player or anything).

Push all project files to the repo:

text
server.py
requirements.txt
railway.json
.gitignore
index.html
manifest.json
sw.js
icon.svg
(If you’re using git: git init, git add ., git commit, then push.)

2 – Deploy on Railway
Sign up at Railway using your GitHub account.

Click New Project → Deploy from GitHub repo.

Select your wavelength-player repository.

Railway will detect the Python project, install dependencies from requirements.txt, and start the server using the command in railway.json.

3 – Get your public URL
In your Railway project, go to the Settings tab.

Under Networking, click Generate Domain.

You’ll receive a URL like https://wavelength-player-production.up.railway.app.

Open that URL on any device – the music player is live with background playback, just like the local version.

⚙️ How it works
Frontend: Pure HTML/CSS/JS (index.html) – responsive, dark UI with gold accents.

Backend: Python FastAPI server (server.py) that:

Serves the frontend and static files.

Proxies YouTube search results and metadata (noembed).

Uses yt-dlp to extract the best audio‑only stream URL for any YouTube video.

Audio streaming: The <audio> element plays directly from a /stream?videoId=... endpoint, which pipes the raw audio data back to the client.

Background playback: The native audio element plus Media Session API keep music playing when you lock the screen or switch apps.

PWA: manifest.json and sw.js enable install‑to‑home‑screen and offline caching.

📁 File structure
text
wavelength-player/
├── server.py          # FastAPI backend (proxying, streaming)
├── requirements.txt   # Python dependencies
├── railway.json       # Railway deployment config
├── index.html         # Complete frontend (responsive, PWA‑enabled)
├── manifest.json      # PWA manifest (icon, colors, display mode)
├── sw.js              # Service worker (offline cache)
├── icon.svg           # Premium app icon (vector)
└── .gitignore         # Python ignores (venv, __pycache__)
🔁 Updating after deployment
Just push new commits to your GitHub repository. Railway automatically redeploys on every push to the main branch – no manual steps needed.

🛠️ Troubleshooting
Problem	Fix
Build fails	Check Railway logs – often a missing dependency or syntax error
Search works but playback doesn’t	Verify that yt-dlp is installed and up‑to‑date (pip install --upgrade yt-dlp)
“No audio-only format found”	Some very new videos may not have audio‑only formats yet; try another track
Domain not in allowlist	The proxy only allows YouTube, noembed, and i.ytimg.com – no other hosts are accessible
💡 Tech stack
Python 3 with FastAPI & Uvicorn

yt‑dlp for audio extraction

aiohttp for async proxying

Vanilla JS frontend (no frameworks)

Service Worker API for offline support

Media Session API for lock‑screen controls

Enjoy your premium, background‑ready music player 🎧