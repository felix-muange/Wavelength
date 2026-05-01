import re
import asyncio
import aiohttp
import os
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, Response
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urljoin

app = FastAPI()

# Thread pool prevents blocking the main event loop during yt-dlp extraction
executor = ThreadPoolExecutor(max_workers=10)

ALLOWED_HOSTS = [
    'www.youtube.com',
    'noembed.com',
    'i.ytimg.com',
]

YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'user_agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0.0.0 Safari/537.36'
    ),
}

# In‑memory cache
_audio_cache: dict[str, dict] = {}

def _extract_audio_sync(video_id: str) -> dict:
    """Blocking extraction via yt-dlp, run in thread pool."""
    with YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False
            )
        except Exception as e:
            print(f"yt-dlp error: {e}")
            return None

    formats = info.get('formats', [])

    # Filter for direct streamable audio
    # iOS prefers m4a/mp4 containers for background playback stability
    audio_formats = [
        f for f in formats
        if f.get('acodec') != 'none'
        and f.get('url')
        and f.get('protocol') in ('https', 'http')
    ]

    if not audio_formats:
        return None

    # Priority: m4a > mp3 > others, then by bitrate
    def get_priority(f):
        ext = f.get('ext', '')
        if ext == 'm4a': return 0
        if ext == 'mp3': return 1
        return 2

    audio_formats.sort(key=lambda f: (get_priority(f), -(f.get('abr') or 0)))
    best = audio_formats[0]

    return {
        'url': best['url'],
        'mime_type': best.get('mime_type', 'audio/mp4'),
        'filesize': best.get('filesize') or best.get('filesize_approx'),
        'title': info.get('title', ''),
    }

async def get_audio_info(video_id: str) -> dict:
    """Async wrapper to offload blocking work."""
    if video_id in _audio_cache:
        return _audio_cache[video_id]
    
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(executor, _extract_audio_sync, video_id)
    
    if not info:
        raise HTTPException(status_code=404, detail="Stream not found")
        
    _audio_cache[video_id] = info
    return info

# ── Proxy helpers ──
def is_allowed(target_url: str) -> bool:
    hostname = urlparse(target_url).hostname
    if not hostname: return False
    return any(hostname == h or hostname.endswith('.' + h) for h in ALLOWED_HOSTS)

async def fetch_proxy_url(target_url: str) -> tuple[bytes, str]:
    if not is_allowed(target_url):
        raise HTTPException(status_code=403, detail="Domain not in allowlist")
    
    headers = {'User-Agent': YDL_OPTS['user_agent']}
    timeout = aiohttp.ClientTimeout(total=15)
    current_url = target_url
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for _ in range(5):
            async with session.get(current_url, headers=headers, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get('Location')
                    if not location: break
                    current_url = urljoin(current_url, location)
                    if not is_allowed(current_url):
                        raise HTTPException(status_code=403, detail="Redirect not allowed")
                    continue
                content = await resp.read()
                return content, resp.content_type or 'text/plain'
    raise HTTPException(status_code=502, detail="Too many redirects")

# ── Routes ──
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/proxy")
async def proxy(url: str = Query(...)):
    content, content_type = await fetch_proxy_url(url)
    return Response(content=content, media_type=content_type)

@app.get("/stream")
async def stream(request: Request, videoId: str = Query(...)):
    if not re.match(r'^[a-zA-Z0-9_\-]{11}$', videoId):
        raise HTTPException(status_code=400, detail="Invalid videoId")

    info = await get_audio_info(videoId)
    audio_url = info['url']
    filesize = info['filesize']
    
    # Handle Byte-Range requests
    range_header = request.headers.get('range')
    upstream_headers = {
        'User-Agent': YDL_OPTS['user_agent'],
        'Referer': 'https://www.youtube.com/',
    }
    
    if range_header:
        upstream_headers['Range'] = range_header

    async def audio_stream():
        # Using no total timeout for streaming, but set a socket read timeout
        timeout = aiohttp.ClientTimeout(total=None, sock_read=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(audio_url, headers=upstream_headers) as resp:
                if resp.status not in (200, 206):
                    return
                # Chunk size 128KB for smoother streaming of large files
                async for chunk in resp.content.iter_chunked(131072):
                    yield chunk

    response_headers = {
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Access-Control-Allow-Origin': '*',
    }

    status_code = 200
    if range_header and filesize:
        m = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else filesize - 1
            response_headers['Content-Range'] = f'bytes {start}-{end}/{filesize}'
            response_headers['Content-Length'] = str(end - start + 1)
            status_code = 206

    return StreamingResponse(
        audio_stream(),
        status_code=status_code,
        media_type=info['mime_type'],
        headers=response_headers,
    )

@app.get("/")
@app.get("/index.html")
async def serve_frontend():
    return FileResponse("index.html", media_type="text/html")

@app.get("/{filename}")
async def static_files(filename: str):
    allowed = {'manifest.json', 'sw.js', 'icon.svg', 'favicon.ico'}
    if filename not in allowed or not os.path.exists(filename):
        raise HTTPException(status_code=404)
    return FileResponse(filename)