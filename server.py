import re
import asyncio
import aiohttp
import os
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# Enable CORS for mobile & PWA access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=10)

YDL_OPTS = {
    'quiet': True,
    'extract_flat': False,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
}

def _extract_sync(v_id):
    with YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
            formats = [f for f in info.get('formats', []) if f.get('acodec') != 'none' and f.get('url')]
            # Prioritize m4a for iOS background play stability
            formats.sort(key=lambda f: (f.get('ext') != 'm4a', -(f.get('abr') or 0)))
            best = formats[0]
            return {
                'url': best['url'], 
                'mime': best.get('mime_type', 'audio/mp4'), 
                'size': best.get('filesize') or best.get('filesize_approx')
            }
        except: return None

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/proxy")
async def proxy(url: str = Query(...)):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return Response(content=await resp.read(), media_type=resp.content_type)

@app.get("/stream")
async def stream(request: Request, videoId: str = Query(...)):
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(executor, _extract_sync, videoId)
    if not info: raise HTTPException(status_code=404)
    
    range_h = request.headers.get('range')
    headers = {'User-Agent': YDL_OPTS['user_agent'], 'Range': range_h} if range_h else {}

    async def gen():
        async with aiohttp.ClientSession() as session:
            async with session.get(info['url'], headers=headers) as r:
                async for chunk in r.content.iter_chunked(128*1024): yield chunk

    h = {'Accept-Ranges': 'bytes', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache'}
    if range_h and info['size']:
        m = re.match(r'bytes=(\d+)-(\d*)', range_h)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else info['size'] - 1
            h.update({'Content-Range': f'bytes {start}-{end}/{info["size"]}', 'Content-Length': str(end-start+1)})
            return StreamingResponse(gen(), status_code=206, media_type=info['mime'], headers=h)
    return StreamingResponse(gen(), headers=h, media_type=info['mime'])

@app.get("/")
async def index(): return FileResponse("index.html")

# Serves sw.js, manifest.json, icon.svg automatically
app.mount("/", StaticFiles(directory="."), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)