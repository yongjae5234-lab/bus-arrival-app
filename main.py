from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import httpx
import os

app = FastAPI()

# 1. CORS 설정 (기존과 동일)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 인천 버스 API 설정 부분 (기존과 동일하므로 중략) ---
BUS_INCHEON_BASE = "https://bus.incheon.go.kr"
SEARCH_URL = f"{BUS_INCHEON_BASE}/inq/selectStopSearchList.do"
ARRIVAL_URL = f"{BUS_INCHEON_BASE}/inq/selectArrivalInfoList.do"
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://bus.incheon.go.kr/bis/search1.view",
    "Origin": "https://bus.incheon.go.kr",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# 2. 루트 경로('/') 처리 개선
@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    # 파일이 없을 경우 에러 메시지 출력
    return HTMLResponse("<h1>Bus App Server</h1><p>index.html 파일을 찾을 수 없습니다. 경로를 확인해주세요.</p>")

# 3. 정적 파일 처리 (기존 serve_static 함수를 대체)
# PWA에 필요한 모든 파일(css, js, manifest, icons 등)을 안전하게 서빙합니다.
@app.get("/{filename}")
async def serve_static(filename: str):
    # 허용할 확장자들을 정의합니다.
    allowed_extensions = [".css", ".js", ".json", ".png", ".jpg", ".ico", ".svg", ".js", ".html"]
    
    # 보안을 위해 현재 폴더에 실제 존재하는 파일이고, 허용된 확장자인지 확인합니다.
    if os.path.exists(filename) and any(filename.endswith(ext) for ext in allowed_extensions):
        # 중요: 소스 코드(main.py) 등은 절대 서빙되지 않도록 방어
        if filename == "main.py":
            raise HTTPException(status_code=403, detail="Forbidden")
        return FileResponse(filename)
    
    raise HTTPException(status_code=404, detail=f"'{filename}' 파일을 찾을 수 없거나 허용되지 않았습니다.")

# --- API 엔드포인트 부분 (기존과 동일하므로 중략) ---
# @app.get("/api/search-stop") ...
# @app.get("/api/bus-arrival") ...

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)