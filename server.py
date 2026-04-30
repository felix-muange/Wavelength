import re
import aiohttp
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, Response
from yt_dlp import YoutubeDL

app = FastAPI()

ALLOWED_HOSTS = [
    'www.youtube.com',
    'noembed.com',
    'i.ytimg.com',
]

# ── yt-dlp options with iOS‑compatible format selection ──
YDL_OPTS = {
    # Prefer M4A (AAC), then MP3, then any other audio‑only format
    'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
}

def is_allowed(target_url: str) -> bool:
    from urllib.parse import urlparse
    hostname = urlparse(target_url).hostname
    return any(hostname == h or hostname.endswith('.' + h) for h in ALLOWED_HOSTS)

async def fetch_proxy_url(target_url: str) -> tuple[bytes, str]:
    if not is_allowed(target_url):
        raise HTTPException(status_code=403, detail="Domain not in allowlist")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'identity',
        'Cache-Control': 'no-cache',
    }

    timeout = aiohttp.ClientTimeout(total=15)
    current_url = target_url
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for _ in range(5):
            async with session.get(current_url, headers=headers, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get('Location')
                    if not location:
                        break
                    from urllib.parse import urljoin
                    new_url = urljoin(current_url, location)
                    if not is_allowed(new_url):
                        raise HTTPException(status_code=403, detail="Redirect domain not allowed")
                    current_url = new_url
                    continue
                content = await resp.read()
                return content, resp.content_type or 'text/plain'
        raise HTTPException(status_code=502, detail="Too many redirects")

@app.get("/health")
async def health():
    return {"status": "ok", "uptime": "N/A", "port": 3001}

@app.get("/")
async def serve_frontend():
    return FileResponse("index.html", media_type="text/html")

@app.get("/proxy")
async def proxy(url: str = Query(..., description="Target URL to proxy")):
    if not url:
        raise HTTPException(status_code=400, detail="Missing ?url= parameter")
    content, content_type = await fetch_proxy_url(url)
    return Response(content=content, media_type=content_type)

@app.get("/stream")
async def stream(videoId: str = Query(..., description="11-character YouTube video ID")):
    if not re.match(r'^[a-zA-Z0-9_-]{11}$', videoId):
        raise HTTPException(status_code=400, detail="Invalid videoId")

    # Extract info with iOS‑compatible format selector
    with YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={videoId}", download=False)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"yt-dlp error: {str(e)}")

    audio_url = info.get('url')
    if not audio_url:
        raise HTTPException(status_code=404, detail="No compatible audio stream found")

    # Determine content‑type from the selected format
    ext = info.get('ext', 'mp4')  # yt-dlp sets ext (m4a, mp3, etc.)
    content_type = f'audio/{ext}' if ext != 'mp4' else 'audio/mp4'

    async def audio_stream():
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        }
        timeout = aiohttp.ClientTimeout(total=None, sock_read=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(audio_url, headers=headers) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=resp.status, detail="Audio source unavailable")
                async for chunk in resp.content.iter_chunked(65536):
                    yield chunk

    return StreamingResponse(
        audio_stream(),
        media_type=content_type,
        headers={"Transfer-Encoding": "chunked", "Cache-Control": "no-cache"}
    )