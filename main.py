from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
import httpx
import os

app = FastAPI()

# 1. CORS 설정 (기존 설정 유지)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 인천 버스 API 설정 (절대 삭제 금지!) ---
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

# 2. 정적 파일 및 루트 경로 처리 (PWA 에러 방지용)
@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return HTMLResponse("<h1>Bus App Server</h1><p>index.html 파일을 찾을 수 없습니다.</p>")

@app.get("/index.html")
async def serve_index_html():
    """PWA의 start_url이 ./index.html 이므로 명시적으로 처리"""
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    raise HTTPException(status_code=404, detail="index.html not found")

@app.get("/{filename}")
async def serve_static(filename: str):
    allowed_extensions = [".css", ".js", ".json", ".png", ".jpg", ".ico", ".svg", ".html"]
    # API 요청과 겹치지 않도록 방어 로직 추가
    if filename.startswith("api"):
        raise HTTPException(status_code=404)
    
    if os.path.exists(filename) and any(filename.endswith(ext) for ext in allowed_extensions):
        return FileResponse(filename)
    raise HTTPException(status_code=404, detail="File Not Found")

# 3. 버스 검색 API (기존 로직 복구)
@app.get("/api/search-stop")
async def search_stop(q: str = Query(..., description="정류장 이름 또는 5자리 단축번호")):
    if not q.strip(): return []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post(SEARCH_URL, content=f"searchWord={q.strip()}", headers=COMMON_HEADERS)
            resp.raise_for_status()
            data = resp.json()
        
        stop_list = data.get("stopList", [])
        results = []
        for stop in stop_list[:10]:
            bstopid = stop.get("bstopid", "")
            bstopnm = stop.get("bstopnm", "알 수 없음")
            short_id = stop.get("short_bstopid", "") or q.strip()
            if bstopid:
                results.append({"id": bstopid, "name": bstopnm, "shortId": short_id})
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. 버스 도착 정보 API (기존 로직 복구)
@app.get("/api/bus-arrival")
async def get_bus_arrival(bstopid: str = Query(..., description="정류장 내부 ID (9자리)")):
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post(ARRIVAL_URL, content=f"bstopid={bstopid.strip()}", headers=COMMON_HEADERS)
            resp.raise_for_status()
            data = resp.json()
        
        result_list = data.get("resultList", [])
        buses = []
        for bus in result_list:
            route_no = bus.get("routeno", "")
            arr_plan_min = bus.get("arrplantm", "")
            rest_cnt = bus.get("rest_bstopcnt", "")
            cur_stop = bus.get("cur_bstopnm", "") or bus.get("bstopnm", "")
            
            if arr_plan_min and str(arr_plan_min).strip():
                minutes = int(str(arr_plan_min).strip())
                time_str = "잠시 후 도착" if minutes == 0 else f"{minutes}분 후"
                stop_info = f"{rest_cnt}정거장 전" if rest_cnt and str(rest_cnt) != "0" else (cur_stop or "위치 정보 없음")
                buses.append({"routeNo": route_no, "timeStr": time_str, "stopInfo": stop_info, "isArriving": minutes <= 3, "minutes": minutes})
        
        buses.sort(key=lambda x: x["minutes"])
        return buses
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)