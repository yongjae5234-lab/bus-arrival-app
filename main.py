from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import httpx
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 인천 버스 공식 사이트 API (bus.incheon.go.kr)
BUS_INCHEON_BASE = "https://bus.incheon.go.kr"
SEARCH_URL = f"{BUS_INCHEON_BASE}/inq/selectStopSearchList.do"
ARRIVAL_URL = f"{BUS_INCHEON_BASE}/inq/selectArrivalInfoList.do"

# 공통 헤더 (브라우저를 흉내내야 403/세션 오류 방지)
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://bus.incheon.go.kr/bis/search1.view",
    "Origin": "https://bus.incheon.go.kr",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# 정적 파일 서빙
@app.get("/")
async def serve_index():
    return FileResponse("index.html")

@app.get("/{filename}")
async def serve_static(filename: str):
    allowed = ["styles.css", "script.js", "manifest.json", "icon-192.png", "icon-512.png", "sw.js"]
    if filename in allowed and os.path.exists(filename):
        return FileResponse(filename)
    raise HTTPException(status_code=404, detail="Not Found")


@app.get("/api/search-stop")
async def search_stop(q: str = Query(..., description="정류장 이름 또는 5자리 단축번호")):
    """
    정류장 검색 - 인천 버스 공식 사이트의 selectStopSearchList.do 사용
    """
    if not q.strip():
        return []
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post(
                SEARCH_URL,
                content=f"searchWord={q.strip()}",
                headers=COMMON_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
        
        stop_list = data.get("stopList", [])
        results = []
        for stop in stop_list[:10]:  # 최대 10개
            bstopid = stop.get("bstopid", "")
            bstopnm = stop.get("bstopnm", "알 수 없음")
            short_id = stop.get("short_bstopid", "") or q.strip()
            if bstopid:
                results.append({
                    "id": bstopid,           # 내부 9자리 ID (API 호출용)
                    "name": bstopnm,
                    "shortId": short_id,     # 5자리 단축번호 (사용자 표시용)
                })
        return results
    
    except Exception as e:
        print(f"[search-stop 오류] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bus-arrival")
async def get_bus_arrival(bstopid: str = Query(..., description="정류장 내부 ID (9자리)")):
    """
    버스 도착 정보 조회 - 인천 버스 공식 사이트의 selectArrivalInfoList.do 사용
    응답: resultList 배열 (routeno, arrtime(초), rest_bstopcnt, cur_bstopnm)
    """
    if not bstopid.strip():
        raise HTTPException(status_code=400, detail="bstopid 필요")
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post(
                ARRIVAL_URL,
                content=f"bstopid={bstopid.strip()}",
                headers=COMMON_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
        
        result_list = data.get("resultList", [])
        buses = []
        
        for bus in result_list:
            route_no = bus.get("routeno", "")
            if not route_no:
                continue
            
            # arrplantm: 도착 예정 시간(분) - 실제 사용되는 필드
            # arrtime: 초 단위 필드인데 현재 API에서 비어있음
            arr_plan_min = bus.get("arrplantm", "")   # 분 단위
            arr_time_raw = bus.get("arrtime", "")      # 초 단위 (비어있을 수 있음)
            rest_cnt = bus.get("rest_bstopcnt", "")
            cur_stop = bus.get("cur_bstopnm", "") or bus.get("bstopnm", "")
            
            minutes = None

            # 1순위: arrplantm (분 단위)
            if arr_plan_min and str(arr_plan_min).strip():
                try:
                    minutes = int(str(arr_plan_min).strip())
                except ValueError:
                    pass

            # 2순위: arrtime (초 단위)
            if minutes is None and arr_time_raw and str(arr_time_raw).strip():
                try:
                    arr_seconds = int(str(arr_time_raw).strip())
                    minutes = arr_seconds // 60
                except ValueError:
                    pass

            # 도착 시간 정보가 전혀 없으면 건너뜀
            if minutes is None:
                continue

            if minutes == 0:
                time_str = "잠시 후 도착"
            else:
                time_str = f"{minutes}분 후"
            is_arriving = minutes <= 3
            
            stop_info = ""
            if rest_cnt and str(rest_cnt).strip() and str(rest_cnt).strip() != "0":
                stop_info = f"{rest_cnt}정거장 전"
            elif cur_stop and cur_stop.strip():
                stop_info = cur_stop
            else:
                stop_info = "위치 정보 없음"
            
            buses.append({
                "routeNo": route_no,       # 버스 번호 (예: "66", "70")
                "timeStr": time_str,        # "3분 후" 또는 "잠시 후 도착"
                "stopInfo": stop_info,      # "5정거장 전" 또는 현재 위치
                "isArriving": is_arriving,  # True면 긴급(빨강), False면 일반
                "minutes": minutes,
            })
        
        # 도착 시간 순으로 정렬
        buses.sort(key=lambda x: x["minutes"])
        return buses
    
    except Exception as e:
        print(f"[bus-arrival 오류] {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
