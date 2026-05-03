import asyncio
import aiohttp
import re
import os
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

# Railway Cookie Handler
COOKIE_FILE = "cookies.txt"
env_cookies = os.getenv("YOUTUBE_COOKIES")
if env_cookies:
    with open(COOKIE_FILE, "w") as f:
        f.write(env_cookies)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
executor = ThreadPoolExecutor(max_workers=50) # Increased workers for faster handling

# Streaming Options (Needs Cookies)
YDL_STREAM_OPTS = {
    'quiet': True,
    'format': 'wa[ext=m4a]/ba[ext=m4a]/bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'cookiefile': COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
    'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
}

# Search Options (NO Cookies for Speed)
YDL_SEARCH_OPTS = {
    'quiet': True,
    'extract_flat': True, # Crucial: Don't resolve video info during search
    'force_generic_extractor': False,
}

def get_stream_url(video_id: str):
    with YoutubeDL(YDL_STREAM_OPTS) as ydl:
        try:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return info.get('url'), info.get('ext') == 'm4a'
        except Exception:
            return None, False

@app.get("/search")
async def search_api(q: str = Query(...)):
    def _search(query):
        # We DO NOT use cookies here. YouTube search is usually 
        # not IP-blocked as aggressively as the stream itself.
        with YoutubeDL(YDL_SEARCH_OPTS) as ydl:
            res = ydl.extract_info(f"ytsearch10:{query}", download=False)
            return [{
                'id': e['id'], 
                'title': e['title'], 
                'author': e.get('uploader', 'Unknown'), 
                'thumb': f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg"
            } for e in res.get('entries', []) if e]
            
    return await asyncio.get_event_loop().run_in_executor(executor, _search, q)

@app.get("/stream")
async def stream(request: Request, videoId: str = Query(...)):
    loop = asyncio.get_event_loop()
    url, is_m4a = await loop.run_in_executor(executor, get_stream_url, videoId)
    
    if not url: 
        raise HTTPException(status_code=404)

    headers = {
        'Accept-Ranges': 'bytes',
        'Content-Type': 'audio/mp4' if is_m4a else 'audio/mpeg',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive', # Keep connection open for mobile
    }

    async def stream_generator():
        # Using a persistent session for faster relay
        async with aiohttp.ClientSession() as session:
            h = {'User-Agent': YDL_STREAM_OPTS['user_agent']}
            if request.headers.get('range'):
                h['Range'] = request.headers.get('range')

            async with session.get(url, headers=h) as resp:
                # 128KB chunks for smoother mobile ramp-up
                async for chunk in resp.content.iter_chunked(128 * 1024):
                    yield chunk

    return StreamingResponse(stream_generator(), headers=headers)

@app.get("/")
async def index(): return FileResponse("index.html")

@app.get("/health")
async def health(): return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3001))
    uvicorn.run(app, host="0.0.0.0", port=port)