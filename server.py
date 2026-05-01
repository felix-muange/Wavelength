import asyncio, aiohttp
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
executor = ThreadPoolExecutor(max_workers=20)

# Optimized for fast-start streaming
YDL_OPTS = {
    'quiet': True,
    'format': 'wa[ext=m4a]/ba[ext=m4a]/bestaudio/best', # Force m4a for native iOS compatibility
    'noplaylist': True,
    'nocheckcertificate': True,
    'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
}

def get_stream_url(video_id: str):
    with YoutubeDL(YDL_OPTS) as ydl:
        try:
            # We only extract the URL, skipping all heavy metadata processing
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return info.get('url'), info.get('ext') == 'm4a'
        except: return None, False

@app.get("/health")
async def health(): return {"status": "ready"}

@app.get("/stream")
async def stream(request: Request, videoId: str = Query(...)):
    loop = asyncio.get_event_loop()
    url, is_m4a = await loop.run_in_executor(executor, get_stream_url, videoId)
    
    if not url: raise HTTPException(status_code=404)

    # We omit Content-Length to force "Chunked" mode. 
    # This is the secret to instant loading on long videos.
    headers = {
        'Accept-Ranges': 'bytes',
        'Content-Type': 'audio/mp4' if is_m4a else 'audio/mpeg',
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*',
    }

    async def stream_generator():
        async with aiohttp.ClientSession() as session:
            # Pass the Range header from the browser directly to YouTube
            proxy_headers = {'User-Agent': YDL_OPTS['user_agent']}
            if request.headers.get('range'):
                proxy_headers['Range'] = request.headers.get('range')

            async with session.get(url, headers=proxy_headers) as resp:
                # Use a very large chunk size for the initial burst
                async for chunk in resp.content.iter_chunked(512 * 1024):
                    yield chunk

    return StreamingResponse(stream_generator(), headers=headers)

@app.get("/search")
async def search_api(q: str = Query(...)):
    def _search(query):
        with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
            res = ydl.extract_info(f"ytsearch10:{query}", download=False)
            return [{'id': e['id'], 'title': e['title'], 'author': e.get('uploader', 'Unknown'), 'thumb': f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg"} for e in res.get('entries', []) if e]
    return await asyncio.get_event_loop().run_in_executor(executor, _search, q)

@app.get("/")
async def index(): return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001, timeout_keep_alive=60)