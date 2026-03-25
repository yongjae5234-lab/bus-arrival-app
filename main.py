from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
import httpx
import os
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 인천 버스 API (기존 - 스크래핑 방식, API 키 불필요)
# ============================================================
BUS_INCHEON_BASE = "https://bus.incheon.go.kr"
INCHEON_SEARCH_URL = f"{BUS_INCHEON_BASE}/inq/selectStopSearchList.do"
INCHEON_ARRIVAL_URL = f"{BUS_INCHEON_BASE}/inq/selectArrivalInfoList.do"

INCHEON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://bus.incheon.go.kr/bis/search1.view",
    "Origin": "https://bus.incheon.go.kr",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# ============================================================
# 서울 버스 API (스크래핑 방식, API 키 불필요)
# ============================================================
SEOUL_SEARCH_URL = "https://bus.go.kr/sbus/bus/selectVApiTotalstr.do"
SEOUL_ARRIVAL_URL = "https://bus.go.kr/sbus/bus/selectBusArrive.do"

SEOUL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://bus.go.kr/app/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# ============================================================
# 경기도 버스 API (공공데이터포털 REST API, API 키 필요)
# ============================================================
GG_API_KEY = os.getenv("BUS_API_KEY", "")
GG_SEARCH_URL = "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationListv2"
GG_ARRIVAL_URL = "https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2"

# ============================================================
# 정적 파일 서빙
# ============================================================
@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return HTMLResponse("<h1>Bus App Server</h1>")

@app.get("/index.html")
async def serve_index_html():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    raise HTTPException(status_code=404, detail="index.html not found")

@app.get("/{filename}")
async def serve_static(filename: str):
    allowed_extensions = [".css", ".js", ".json", ".png", ".jpg", ".ico", ".svg", ".html"]
    if filename.startswith("api"):
        raise HTTPException(status_code=404)
    if os.path.exists(filename) and any(filename.endswith(ext) for ext in allowed_extensions):
        return FileResponse(filename)
    raise HTTPException(status_code=404, detail="File Not Found")


# ============================================================
# 공통 유틸
# ============================================================
def _parse_incheon_search(data: dict) -> list:
    results = []
    for stop in data.get("stopList", [])[:10]:
        bstopid = stop.get("bstopid", "")
        bstopnm = stop.get("bstopnm", "알 수 없음")
        short_id = stop.get("short_bstopid", "")
        if bstopid:
            results.append({"id": bstopid, "name": bstopnm, "shortId": short_id, "region": "incheon"})
    return results

def _parse_incheon_arrival(data: dict) -> list:
    buses = []
    for bus in data.get("resultList", []):
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

def _parse_seoul_search(data: dict) -> list:
    try:
        result_list = data["ResponseVO"]["data"]["resultList"]
    except (KeyError, TypeError):
        return []
    results = []
    for s in result_list[:10]:
        stop_id = str(s.get("strid", ""))
        stop_name = s.get("strnm", "알 수 없음")
        short_id = s.get("strno", "")
        if stop_id:
            results.append({"id": stop_id, "name": stop_name, "shortId": short_id, "region": "seoul"})
    return results

def _parse_seoul_arrival(data: dict) -> list:
    try:
        result_list = data["ResponseVO"]["data"]["resultList"]
    except (KeyError, TypeError):
        return []
    buses = []
    for bus in result_list:
        route_no = bus.get("rtnm", bus.get("strnm", ""))
        # 도착 시간: actnm(초 단위) 또는 예정시간 필드
        arr_sec1 = bus.get("arrmsg1", "")  # "3분 후" 형태 문자열
        arr_sec2 = bus.get("arrmsg2", "")
        # acrsec 필드: 도착 예정 초
        sec1 = bus.get("acrsec", 0) or bus.get("acrsecNd", 0)
        
        # arrmsg1 가 있으면 활용, 없으면 acrsec 변환
        if arr_sec1 and arr_sec1 not in ["운행종료", "출발대기", "곧 도착"]:
            time_str = arr_sec1
            # 분 파싱 시도
            import re
            m = re.search(r'(\d+)\s*분', arr_sec1)
            minutes = int(m.group(1)) if m else 99
        elif arr_sec1 == "곧 도착":
            time_str = "잠시 후 도착"
            minutes = 0
        elif sec1:
            minutes = int(sec1) // 60
            time_str = "잠시 후 도착" if minutes == 0 else f"{minutes}분 후"
        else:
            continue

        stop_info = bus.get("stbstopnm", bus.get("stNm", "위치 정보 없음"))
        if not stop_info or stop_info == "null":
            stop_info = "위치 정보 없음"
        
        if route_no:
            buses.append({"routeNo": route_no, "timeStr": time_str, "stopInfo": stop_info, "isArriving": minutes <= 3, "minutes": minutes})
    
    buses.sort(key=lambda x: x["minutes"])
    return buses[:10]

def _parse_gg_search(data: dict) -> list:
    try:
        items = data["response"]["msgBody"]["busStationList"]
        if isinstance(items, dict):
            items = [items]
    except (KeyError, TypeError):
        return []
    results = []
    for s in (items or [])[:10]:
        stop_id = str(s.get("stationId", ""))
        stop_name = s.get("stationName", "알 수 없음")
        short_id = str(s.get("mobileNo", ""))
        if stop_id:
            results.append({"id": stop_id, "name": stop_name, "shortId": short_id, "region": "gyeonggi"})
    return results

def _parse_gg_arrival(data: dict) -> list:
    try:
        items = data["response"]["msgBody"]["busArrivalList"]
        if isinstance(items, dict):
            items = [items]
    except (KeyError, TypeError):
        return []
    buses = []
    for bus in (items or []):
        route_no = bus.get("routeName", "")
        predict_time1 = bus.get("predictTime1", "")
        remain_seat = bus.get("remainSeatCnt1", "")
        if predict_time1 and str(predict_time1).strip():
            try:
                minutes = int(str(predict_time1).strip())
            except:
                continue
            time_str = "잠시 후 도착" if minutes == 0 else f"{minutes}분 후"
            stop_info = f"남은 좌석: {remain_seat}" if remain_seat and str(remain_seat) != "-1" else "위치 정보 없음"
            buses.append({"routeNo": route_no, "timeStr": time_str, "stopInfo": stop_info, "isArriving": minutes <= 3, "minutes": minutes})
    buses.sort(key=lambda x: x["minutes"])
    return buses


# ============================================================
# API 엔드포인트
# ============================================================

@app.get("/api/search-stop")
async def search_stop(
    q: str = Query(..., description="정류장 이름 또는 번호"),
    region: str = Query("incheon", description="지역: incheon | gyeonggi | seoul")
):
    if not q.strip():
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=False) as client:
            if region == "incheon":
                resp = await client.post(INCHEON_SEARCH_URL, content=f"searchWord={q.strip()}", headers=INCHEON_HEADERS)
                resp.raise_for_status()
                return _parse_incheon_search(resp.json())

            elif region == "seoul":
                resp = await client.get(SEOUL_SEARCH_URL, params={"strkey": q.strip(), "strdiv": "2", "pageIndex": "1", "recordCountPerPage": "10"}, headers=SEOUL_HEADERS)
                resp.raise_for_status()
                return _parse_seoul_search(resp.json())

            elif region == "gyeonggi":
                if not GG_API_KEY:
                    raise HTTPException(status_code=500, detail="경기도 API 키가 설정되지 않았습니다.")
                resp = await client.get(GG_SEARCH_URL, params={"serviceKey": GG_API_KEY, "keyword": q.strip(), "format": "json"})
                resp.raise_for_status()
                return _parse_gg_search(resp.json())

            else:
                raise HTTPException(status_code=400, detail=f"알 수 없는 지역: {region}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bus-arrival")
async def get_bus_arrival(
    bstopid: str = Query(..., description="정류장 ID"),
    region: str = Query("incheon", description="지역: incheon | gyeonggi | seoul")
):
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=False) as client:
            if region == "incheon":
                resp = await client.post(INCHEON_ARRIVAL_URL, content=f"bstopid={bstopid.strip()}", headers=INCHEON_HEADERS)
                resp.raise_for_status()
                return _parse_incheon_arrival(resp.json())

            elif region == "seoul":
                resp = await client.get(SEOUL_ARRIVAL_URL, params={"stopId": bstopid.strip()}, headers=SEOUL_HEADERS)
                resp.raise_for_status()
                return _parse_seoul_arrival(resp.json())

            elif region == "gyeonggi":
                if not GG_API_KEY:
                    raise HTTPException(status_code=500, detail="경기도 API 키가 설정되지 않았습니다.")
                resp = await client.get(GG_ARRIVAL_URL, params={"serviceKey": GG_API_KEY, "stationId": bstopid.strip(), "format": "json"})
                resp.raise_for_status()
                return _parse_gg_arrival(resp.json())

            else:
                raise HTTPException(status_code=400, detail=f"알 수 없는 지역: {region}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)