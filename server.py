import re, asyncio, aiohttp
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# Standard CORS to prevent ERR_FAILED on mobile
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=20)

YDL_OPTS = {
    'quiet': True,
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
}

def _extract_audio_sync(video_id: str):
    with YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            formats = [f for f in info.get('formats', []) if f.get('acodec') != 'none' and f.get('url')]
            formats.sort(key=lambda f: (f.get('ext') == 'm4a', f.get('abr') or 0), reverse=True)
            if not formats: return None
            best = formats[0]
            return {
                'url': best['url'], 
                'mime': 'audio/mp4' if best.get('ext') in ['m4a', 'mp4'] else 'audio/mpeg',
                'size': best.get('filesize') or best.get('filesize_approx') or 8000000
            }
        except: return None

@app.get("/health")
async def health():
    return {"status": "ok", "service": "wavelength-core"}

@app.get("/search")
async def search_api(q: str = Query(...)):
    def _search(query):
        with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
            res = ydl.extract_info(f"ytsearch10:{query}", download=False)
            return [{'id': e['id'], 'title': e['title'], 'author': e.get('uploader', 'Unknown'), 'thumb': f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg"} for e in res.get('entries', []) if e]
    return await asyncio.get_event_loop().run_in_executor(executor, _search, q)

@app.get("/stream")
async def stream(request: Request, videoId: str = Query(...)):
    info = await asyncio.get_event_loop().run_in_executor(executor, _extract_audio_sync, videoId)
    if not info: raise HTTPException(status_code=404)
    
    range_header = request.headers.get('range')
    file_size = info['size']
    
    headers = {
        'Accept-Ranges': 'bytes',
        'Content-Type': info['mime'],
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'no-cache, no-store',
    }

    status_code = 200
    start, end = 0, file_size - 1

    if range_header:
        status_code = 206
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            start = int(match.group(1))
            if match.group(2): end = int(match.group(2))
            headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
    
    headers['Content-Length'] = str((end - start) + 1)

    async def byte_generator():
        async with aiohttp.ClientSession() as session:
            h = {'User-Agent': YDL_OPTS['user_agent'], 'Range': f'bytes={start}-{end}'}
            async with session.get(info['url'], headers=h) as resp:
                # 256KB chunks to flood the mobile buffer and start playback instantly
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    yield chunk

    return StreamingResponse(byte_generator(), status_code=status_code, headers=headers)

@app.get("/")
async def index():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)