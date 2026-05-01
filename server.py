import re, asyncio, aiohttp, os
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=10)

# Critical: Use 'ios' player client to bypass "Sign in to confirm you're not a bot"
YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'format': 'bestaudio/best',
    'extractor_args': {'youtube': {'player_client': ['ios']}},
}

def _extract_sync(v_id):
    with YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
            formats = [f for f in info.get('formats', []) if f.get('acodec') != 'none' and f.get('url')]
            formats.sort(key=lambda f: (f.get('ext') == 'm4a', f.get('abr') or 0), reverse=True)
            best = formats[0]
            return {
                'url': best['url'], 
                'mime': 'audio/mp4',
                'size': best.get('filesize') or best.get('filesize_approx')
            }
        except Exception as e:
            print(f"Extraction Error: {e}")
            return None

@app.get("/health")
async def health(): return {"status": "ok"}

@app.get("/proxy")
async def proxy(url: str = Query(...)):
    async with aiohttp.ClientSession() as session:
        headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'}
        async with session.get(url, headers=headers) as resp:
            return Response(content=await resp.read(), media_type=resp.content_type)

@app.get("/stream")
async def stream(request: Request, videoId: str = Query(...)):
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(executor, _extract_sync, videoId)
    if not info: raise HTTPException(status_code=403, detail="Blocked by YouTube")
    
    range_h = request.headers.get('range')
    headers = {'User-Agent': 'com.google.ios.youtube/19.29.1', 'Range': range_h} if range_h else {}

    async def gen():
        async with aiohttp.ClientSession() as session:
            async with session.get(info['url'], headers=headers) as r:
                async for chunk in r.content.iter_chunked(256*1024): yield chunk

    h = {'Accept-Ranges': 'bytes', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache'}
    if range_h and info['size']:
        m = re.match(r'bytes=(\d+)-(\d*)', range_h)
        if m:
            start, end = int(m.group(1)), (int(m.group(2)) if m.group(2) else info['size'] - 1)
            h.update({'Content-Range': f'bytes {start}-{end}/{info["size"]}', 'Content-Length': str(end-start+1)})
            return StreamingResponse(gen(), status_code=206, media_type=info['mime'], headers=h)
    return StreamingResponse(gen(), headers=h, media_type=info['mime'])

@app.get("/")
async def index(): return FileResponse("index.html")

app.mount("/", StaticFiles(directory="."), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))