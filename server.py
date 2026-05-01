import re
import asyncio
import aiohttp
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, Response
from yt_dlp import YoutubeDL

app = FastAPI()

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

# ── In‑memory cache for yt‑dlp results ──
_audio_cache: dict[str, dict] = {}


def _extract_audio_info(video_id: str) -> dict:
    """Blocking extract – used by /stream and /prefetch"""
    with YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"yt-dlp error: {str(e)}")

    formats = info.get('formats', [])

    # iOS‑safe formats first (m4a/mp3/mp4, https protocol, audio‑only)
    direct_audio = [
        f for f in formats
        if f.get('acodec') != 'none'
        and f.get('vcodec') == 'none'
        and f.get('protocol') == 'https'
        and f.get('url')
        and f.get('ext') in ('m4a', 'mp3', 'mp4')
    ]

    if not direct_audio:
        direct_audio = [
            f for f in formats
            if f.get('acodec') != 'none'
            and f.get('vcodec') == 'none'
            and f.get('protocol') == 'https'
            and f.get('url')
        ]

    if not direct_audio:
        raise HTTPException(status_code=404, detail="No compatible audio stream found")

    def format_priority(f):
        ext = f.get('ext', '')
        return {'m4a': 0, 'mp3': 1, 'mp4': 2}.get(ext, 9)

    direct_audio.sort(key=lambda f: (format_priority(f), -(f.get('abr') or 0)))
    best = direct_audio[0]

    return {
        'url': best['url'],
        'ext': best.get('ext', 'mp4'),
        'filesize': best.get('filesize') or best.get('filesize_approx'),
        'title': info.get('title', ''),
    }


def get_audio_info(video_id: str) -> dict:
    """Return cached info or extract + cache"""
    if video_id in _audio_cache:
        return _audio_cache[video_id]
    info = _extract_audio_info(video_id)
    _audio_cache[video_id] = info
    return info


# ─────────────────────────────────────────────────
#  Helper functions (unchanged)
# ─────────────────────────────────────────────────
def is_allowed(target_url: str) -> bool:
    from urllib.parse import urlparse
    hostname = urlparse(target_url).hostname
    return any(hostname == h or hostname.endswith('.' + h) for h in ALLOWED_HOSTS)

async def fetch_proxy_url(target_url: str) -> tuple[bytes, str]:
    if not is_allowed(target_url):
        raise HTTPException(status_code=403, detail="Domain not in allowlist")
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'identity',
        'Cache-Control': 'no-cache',
    }
    timeout = aiohttp.ClientTimeout(total=15)
    current_url = target_url
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for _ in range(5):
            async with session.get(
                current_url, headers=headers, allow_redirects=False
            ) as resp:
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


CONTENT_TYPE_MAP = {
    'm4a':  'audio/mp4',
    'mp3':  'audio/mpeg',
    'mp4':  'audio/mp4',
    'webm': 'audio/webm',
    'ogg':  'audio/ogg',
}


# ─────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/proxy")
async def proxy(url: str = Query(...)):
    content, content_type = await fetch_proxy_url(url)
    return Response(content=content, media_type=content_type)


@app.get("/prefetch")
async def prefetch(ids: str = Query(..., description="Comma‑separated video IDs")):
    """Prefetch audio info for a batch of video IDs so later plays are instant."""
    video_ids = [vid.strip() for vid in ids.split(',') if vid.strip()]
    if not video_ids:
        raise HTTPException(status_code=400, detail="No video IDs provided")
    if len(video_ids) > 50:
        video_ids = video_ids[:50]

    async def run_extract(vid):
        # Run blocking yt-dlp in a thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, get_audio_info, vid)
        except Exception:
            pass  # silently ignore errors for prefetch

    await asyncio.gather(*[run_extract(vid) for vid in video_ids])
    return {"cached": len(video_ids)}


@app.get("/stream")
async def stream(request: Request, videoId: str = Query(...)):
    if not re.match(r'^[a-zA-Z0-9_\-]{11}$', videoId):
        raise HTTPException(status_code=400, detail="Invalid videoId")

    info = get_audio_info(videoId)
    audio_url = info['url']
    ext = info['ext']
    filesize = info['filesize']
    content_type = CONTENT_TYPE_MAP.get(ext, 'audio/mp4')

    range_header = request.headers.get('range')
    start = 0
    end = None
    if range_header:
        m = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else None

    upstream_headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/125.0.0.0 Safari/537.36'
        ),
        'Referer': 'https://www.youtube.com/',
    }
    if range_header:
        upstream_headers['Range'] = range_header

    timeout = aiohttp.ClientTimeout(total=None, sock_read=30)

    async def audio_stream():
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(audio_url, headers=upstream_headers) as resp:
                if resp.status not in (200, 206):
                    return
                async for chunk in resp.content.iter_chunked(65536):
                    yield chunk

    response_headers = {
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*',
    }
    if filesize:
        end_byte = end if end is not None else filesize - 1
        response_headers['Content-Length'] = str(end_byte - start + 1)
        if range_header:
            response_headers['Content-Range'] = f'bytes {start}-{end_byte}/{filesize}'

    return StreamingResponse(
        audio_stream(),
        status_code=206 if range_header else 200,
        media_type=content_type,
        headers=response_headers,
    )


@app.get("/.well-known/{rest:path}")
async def well_known(rest: str):
    raise HTTPException(status_code=204)


@app.get("/")
@app.get("/index.html")
async def serve_frontend():
    return FileResponse("index.html", media_type="text/html")


@app.get("/{filename}")
async def static_files(filename: str):
    import os
    allowed = {'manifest.json', 'sw.js', 'icon.svg', 'favicon.ico'}
    if filename not in allowed:
        raise HTTPException(status_code=404)
    if not os.path.exists(filename):
        raise HTTPException(status_code=404)
    return FileResponse(filename)