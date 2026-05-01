import re, asyncio, aiohttp
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# Enable CORS for local development and mobile testing
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
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

# --- HEALTH ENDPOINT ---
@app.get("/health")
async def health():
    return {"status": "ok", "message": "Server is responsive", "port": 3001}

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
                'size': best.get('filesize') or best.get('filesize_approx') or 10000000
            }
        except: return None

@app.get("/search")
async def search_api(q: str = Query(...)):
    def _search(query):
        with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
            res = ydl.extract_info(f"ytsearch15:{query}", download=False)
            return [{'id': e['id'], 'title': e['title'], 'author': e.get('uploader', 'Unknown'), 'thumb': f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg"} for e in res.get('entries', []) if e]
    return await asyncio.get_event_loop().run_in_executor(executor, _search, q)

@app.get("/stream")
async def stream(request: Request, videoId: str = Query(...)):
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(executor, _extract_audio_sync, videoId)
    if not info: raise HTTPException(status_code=404)
    
    range_header = request.headers.get('range')
    file_size = info['size']
    headers = {'Accept-Ranges': 'bytes', 'Content-Type': info['mime'], 'Access-Control-Allow-Origin': '*'}
    
    status_code = 200
    if range_header:
        status_code = 206
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1
            headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            headers['Content-Length'] = str((end - start) + 1)

    async def byte_generator():
        async with aiohttp.ClientSession() as session:
            h = {'User-Agent': 'Mozilla/5.0'}
            if range_header: h['Range'] = range_header
            async with session.get(info['url'], headers=h) as resp:
                async for chunk in resp.content.iter_chunked(128 * 1024): yield chunk

    return StreamingResponse(byte_generator(), status_code=status_code, headers=headers)

@app.get("/")
async def index(): return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)