import asyncio
import aiohttp
import re
import os
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

# --- RAILWAY COOKIE HANDLER ---
# This looks for the YOUTUBE_COOKIES env var and writes it to a local file
COOKIE_FILE = "cookies.txt"
env_cookies = os.getenv("YOUTUBE_COOKIES")

if env_cookies:
    with open(COOKIE_FILE, "w") as f:
        f.write(env_cookies)
    print("SUCCESS: Cookies loaded from Environment Variable.")
else:
    print("WARNING: No YOUTUBE_COOKIES found. Railway might return 429 errors.")
# ------------------------------

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
executor = ThreadPoolExecutor(max_workers=20)

YDL_OPTS = {
    'quiet': True,
    'format': 'wa[ext=m4a]/ba[ext=m4a]/bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'cookiefile': COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
    'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
}

def get_stream_url(video_id: str):
    with YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return info.get('url'), info.get('ext') == 'm4a'
        except Exception as e:
            print(f"Extraction Error: {e}")
            return None, False

@app.get("/health")
async def health(): 
    return {"status": "ready", "using_cookies": os.path.exists(COOKIE_FILE)}

@app.get("/stream")
async def stream(request: Request, videoId: str = Query(...)):
    loop = asyncio.get_event_loop()
    url, is_m4a = await loop.run_in_executor(executor, get_stream_url, videoId)
    
    if not url: 
        raise HTTPException(status_code=404, detail="Could not extract stream URL")

    headers = {
        'Accept-Ranges': 'bytes',
        'Content-Type': 'audio/mp4' if is_m4a else 'audio/mpeg',
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*',
    }

    async def stream_generator():
        async with aiohttp.ClientSession() as session:
            h = {'User-Agent': YDL_OPTS['user_agent']}
            if request.headers.get('range'):
                h['Range'] = request.headers.get('range')

            async with session.get(url, headers=h) as resp:
                async for chunk in resp.content.iter_chunked(512 * 1024):
                    yield chunk

    return StreamingResponse(stream_generator(), headers=headers)

@app.get("/search")
async def search_api(q: str = Query(...)):
    def _search(query):
        # We use cookies here too so search results aren't blocked
        with YoutubeDL(YDL_OPTS) as ydl:
            res = ydl.extract_info(f"ytsearch10:{query}", download=False)
            return [{
                'id': e['id'], 
                'title': e['title'], 
                'author': e.get('uploader', 'Unknown'), 
                'thumb': f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg"
            } for e in res.get('entries', []) if e]
            
    return await asyncio.get_event_loop().run_in_executor(executor, _search, q)

@app.get("/")
async def index(): 
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    # Railway usually provides a PORT env var, but 3001 is our default
    port = int(os.getenv("PORT", 3001))
    uvicorn.run(app, host="0.0.0.0", port=port)