import asyncio, aiohttp, os
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from concurrent.futures import ThreadPoolExecutor

COOKIE_FILE = "cookies.txt"
env_cookies = os.getenv("YOUTUBE_COOKIES")
if env_cookies:
    with open(COOKIE_FILE, "w") as f: f.write(env_cookies)
HAS_COOKIES = os.path.exists(COOKIE_FILE)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
executor = ThreadPoolExecutor(max_workers=50)

def get_ydl_opts():
    # Use 'mweb' (Mobile Web) client. It's the fastest and least restricted right now.
    opts = {
        'quiet': True,
        'format': 'bestaudio/best',
        'noplaylist': True,
        'nocheckcertificate': True,
        'cookiefile': COOKIE_FILE if HAS_COOKIES else None,
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb'], # mweb is the key to bypassing signature issues
            }
        },
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
    }
    return opts

def get_stream_url(video_id: str):
    with YoutubeDL(get_ydl_opts()) as ydl:
        try:
            # We use 'download=False' and only fetch the specific video
            info = ydl.extract_info(f"XLFwIo56n4g" if not video_id else video_id, download=False)
            if 'url' in info:
                return info['url'], info.get('ext') == 'm4a'
            return None, False
        except Exception as e:
            print(f"Extraction Failed: {str(e)}")
            return None, False

@app.get("/stream")
async def stream(request: Request, videoId: str = Query(...)):
    loop = asyncio.get_event_loop()
    url, is_m4a = await loop.run_in_executor(executor, get_stream_url, videoId)
    if not url: raise HTTPException(status_code=403)

    async def stream_generator():
        async with aiohttp.ClientSession() as session:
            h = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X)'}
            if request.headers.get('range'): h['Range'] = request.headers.get('range')
            async with session.get(url, headers=h) as resp:
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    yield chunk

    return StreamingResponse(stream_generator(), headers={
        'Accept-Ranges': 'bytes',
        'Content-Type': 'audio/mp4' if is_m4a else 'audio/mpeg',
    })

@app.get("/search")
async def search_api(q: str = Query(...)):
    def _search(query):
        with YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
            res = ydl.extract_info(f"ytsearch12:{query}", download=False)
            return [{'id': e['id'], 'title': e['title'], 'author': e.get('uploader', 'Unknown'), 'thumb': f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg"} for e in res.get('entries', []) if e]
    return await asyncio.get_event_loop().run_in_executor(executor, _search, q)

@app.get("/health")
async def health(): return {"status": "ok", "cookies": HAS_COOKIES}

@app.get("/")
async def index(): return FileResponse("index.html")

if __name__ == "__main__":
    uvicorn_port = int(os.getenv("PORT", 3001))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=uvicorn_port)