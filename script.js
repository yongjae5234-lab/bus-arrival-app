/**
 * 우리 동네 버스 앱 - JavaScript
 * 
 * 구조:
 * - 3개 슬롯 (슬롯 0 = 독정역 고정, 슬롯 1~2 사용자 지정)
 * - 메인 화면 <-> 도착 정보 화면 전환
 * - 30초 자동 새로고침
 */

// ==========================================
//  상수 & 설정
// ==========================================

/** 1번 슬롯 (독정역) 고정 값 */
const SLOT_0_FIXED = {
    id: "168000378",      // 인천 버스 내부 ID
    name: "독정역",
    shortId: "42378",
};

/** 기본 슬롯 초기값 */
const DEFAULT_SLOTS = [
    SLOT_0_FIXED,
    { id: "", name: "정류장 2", shortId: "" },
    { id: "", name: "정류장 3", shortId: "" },
];

/** 자동 새로고침 간격 (ms) */
const REFRESH_INTERVAL_MS = 30_000;

// ==========================================
//  앱 상태
// ==========================================

let slots = [...DEFAULT_SLOTS.map(s => ({ ...s }))];
let currentSlotIndex = -1;   // 현재 보고 있는 슬롯 인덱스
let refreshTimer = null;      // setInterval 타이머
let countdownTimer = null;    // 카운트다운 타이머
let countdownSec = 30;        // 카운트다운 초
let currentEditingSlot = -1; // 설정 모달에서 편집 중인 슬롯
let isLoadingArrival = false; // 도착 정보 로딩 중 여부

// ==========================================
//  localStorage
// ==========================================

function loadSlots() {
    try {
        const raw = localStorage.getItem("busSlots_v2");
        if (raw) {
            const parsed = JSON.parse(raw);
            // 슬롯 0는 항상 고정값 사용
            slots[0] = { ...SLOT_0_FIXED };
            if (parsed[1] && parsed[1].id) slots[1] = parsed[1];
            if (parsed[2] && parsed[2].id) slots[2] = parsed[2];
        }
    } catch (e) {
        console.warn("슬롯 로드 실패:", e);
    }
}

function saveSlots() {
    localStorage.setItem("busSlots_v2", JSON.stringify(slots));
}

// ==========================================
//  화면 전환
// ==========================================

function showScreen(id) {
    document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
    document.getElementById(id).classList.add("active");
}

function showMain() {
    stopRefreshTimers();
    showScreen("main-screen");
    currentSlotIndex = -1;
}

function showArrivalScreen(slotIndex) {
    const slot = slots[slotIndex];
    currentSlotIndex = slotIndex;

    document.getElementById("arrival-stop-name").textContent = slot.name;
    document.getElementById("arrival-stop-id").textContent =
        slot.shortId ? `정류장 번호: ${slot.shortId}` : `ID: ${slot.id}`;

    showScreen("arrival-screen");
    loadArrivalData(slot.id);
    startRefreshTimers(slot.id);
}

// ==========================================
//  메인 화면 렌더링
// ==========================================

function renderSlots() {
    const container = document.getElementById("slots-section");
    container.innerHTML = "";

    slots.forEach((slot, i) => {
        const isEmpty = !slot.id;
        const card = document.createElement("div");
        card.className = `slot-card ${isEmpty ? "empty" : "filled"}`;

        // 아이콘
        const icons = ["🏠", "📍", "📌"];
        const icon = icons[i] || "🚏";

        if (isEmpty) {
            // 빈 슬롯 - 클릭하면 설정 모달
            card.innerHTML = `
                <button class="slot-main-btn" onclick="openSetupModal(${i})">
                    <span class="slot-icon">➕</span>
                    <div class="slot-text">
                        <div class="slot-name">정류장 ${i + 1} 추가</div>
                        <div class="slot-short-id">터치하여 정류장 설정</div>
                    </div>
                    <span class="slot-arrow">›</span>
                </button>
            `;
        } else {
            // 설정된 슬롯
            const settingsHtml = i > 0 ? `
                <div class="slot-footer">
                    <button class="slot-setup-btn" onclick="openSetupModal(${i}); event.stopPropagation();">
                        ⚙️ 정류장 변경
                    </button>
                </div>
            ` : `
                <div class="slot-footer">
                    <button class="slot-setup-btn" style="opacity:0.4; cursor:default;">
                        📌 고정 정류장 (변경 불가)
                    </button>
                </div>
            `;

            card.innerHTML = `
                <button class="slot-main-btn" onclick="showArrivalScreen(${i})">
                    <span class="slot-icon">${icon}</span>
                    <div class="slot-text">
                        <div class="slot-name">${escapeHtml(slot.name)}</div>
                        ${slot.shortId
                            ? `<span class="slot-short-id">정류장 번호: ${escapeHtml(slot.shortId)}</span>`
                            : `<span class="slot-short-id">ID: ${escapeHtml(slot.id)}</span>`
                        }
                    </div>
                    <span class="slot-arrow">›</span>
                </button>
                ${settingsHtml}
            `;
        }

        container.appendChild(card);
    });
}

// ==========================================
//  도착 정보 로드
// ==========================================

async function loadArrivalData(bstopid) {
    if (isLoadingArrival) return;
    isLoadingArrival = true;

    const busList = document.getElementById("bus-list");
    const loading = document.getElementById("loading-indicator");
    const noBus = document.getElementById("no-bus");
    const errorInfo = document.getElementById("error-info");

    busList.innerHTML = "";
    noBus.classList.add("hidden");
    errorInfo.classList.add("hidden");
    loading.classList.remove("hidden");

    try {
        const resp = await fetch(`/api/bus-arrival?bstopid=${encodeURIComponent(bstopid)}`);
        if (!resp.ok) {
            const err = await resp.text();
            throw new Error(`서버 오류 (${resp.status})`);
        }
        const buses = await resp.json();

        loading.classList.add("hidden");

        if (!buses || buses.length === 0) {
            noBus.classList.remove("hidden");
        } else {
            renderBusList(buses);
        }
    } catch (e) {
        loading.classList.add("hidden");
        errorInfo.classList.remove("hidden");
        document.getElementById("error-detail").textContent = e.message || "알 수 없는 오류";
    } finally {
        isLoadingArrival = false;
    }
}

function renderBusList(buses) {
    const container = document.getElementById("bus-list");
    container.innerHTML = "";

    buses.forEach((bus, idx) => {
        const card = document.createElement("div");
        let cls = "bus-card";
        let badge = "";

        if (bus.isArriving) {
            cls += " arriving";
            badge = `<span class="arriving-badge">🔴 곧 도착</span>`;
        } else if (bus.minutes <= 5) {
            cls += " soon";
            badge = `<span class="soon-badge">🟡 곧 도착</span>`;
        }

        card.className = cls;
        card.style.animationDelay = `${idx * 0.06}s`;

        // 시간 표시: "잠시 후 도착"은 큰 박스, 분 단위는 숫자+단위 분리
        let timeHtml = "";
        if (bus.timeStr.includes("잠시")) {
            timeHtml = `<span class="bus-arrival-time" style="font-size:2rem;">잠시 후</span>`;
        } else {
            // "X분 후" → 숫자와 단위 분리
            const match = bus.timeStr.match(/^(\d+)(분 후)$/);
            if (match) {
                timeHtml = `<span class="bus-arrival-time">${match[1]}</span><span class="bus-arrival-unit">분 후</span>`;
            } else {
                timeHtml = `<span class="bus-arrival-time">${bus.timeStr}</span>`;
            }
        }

        card.innerHTML = `
            <div class="bus-number-badge">${escapeHtml(bus.routeNo)}번</div>
            <div class="bus-info">
                <div class="bus-time-row">
                    ${timeHtml}
                </div>
                <div class="bus-location">${escapeHtml(bus.stopInfo)}</div>
            </div>
            ${badge}
        `;

        container.appendChild(card);
    });
}

function retryArrival() {
    if (currentSlotIndex >= 0) {
        loadArrivalData(slots[currentSlotIndex].id);
    }
}

// ==========================================
//  자동 새로고침 타이머
// ==========================================

function startRefreshTimers(bstopid) {
    stopRefreshTimers();
    countdownSec = REFRESH_INTERVAL_MS / 1000;
    updateCountdownDisplay();

    refreshTimer = setInterval(() => {
        loadArrivalData(bstopid);
        countdownSec = REFRESH_INTERVAL_MS / 1000;
    }, REFRESH_INTERVAL_MS);

    countdownTimer = setInterval(() => {
        countdownSec = Math.max(0, countdownSec - 1);
        updateCountdownDisplay();
    }, 1000);
}

function stopRefreshTimers() {
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
}

function updateCountdownDisplay() {
    const el = document.getElementById("refresh-timer");
    if (el) el.textContent = `자동 새로고침: ${countdownSec}초 후`;
}

// ==========================================
//  설정 모달
// ==========================================

function openSetupModal(slotIndex) {
    if (slotIndex === 0) return; // 슬롯 0은 고정

    currentEditingSlot = slotIndex;
    document.getElementById("stop-id-input").value = "";
    document.getElementById("modal-result").innerHTML = "";
    document.getElementById("modal-result").classList.add("hidden");
    document.getElementById("modal-searching").classList.add("hidden");
    document.getElementById("setup-modal").classList.remove("hidden");

    setTimeout(() => {
        document.getElementById("stop-id-input").focus();
    }, 300);
}

function closeSetupModal() {
    document.getElementById("setup-modal").classList.add("hidden");
    currentEditingSlot = -1;
}

function handleModalEnter(e) {
    if (e.key === "Enter") searchAndSaveStop();
}

async function searchAndSaveStop() {
    const input = document.getElementById("stop-id-input").value.trim();
    if (!input) {
        alert("정류장 번호를 입력해주세요.");
        return;
    }

    const searching = document.getElementById("modal-searching");
    const resultContainer = document.getElementById("modal-result");

    searching.classList.remove("hidden");
    resultContainer.classList.add("hidden");
    resultContainer.innerHTML = "";

    try {
        const resp = await fetch(`/api/search-stop?q=${encodeURIComponent(input)}`);
        if (!resp.ok) throw new Error("검색 실패");
        const results = await resp.json();

        searching.classList.add("hidden");

        if (!results || results.length === 0) {
            resultContainer.innerHTML = `
                <div class="modal-result-item" style="cursor:default; color: var(--text-sub);">
                    검색 결과가 없습니다.<br>5자리 정류장 번호를 정확히 입력해주세요.
                </div>
            `;
            resultContainer.classList.remove("hidden");
            return;
        }

        // 결과 목록 표시
        resultContainer.innerHTML = results.map(stop => `
            <div class="modal-result-item" 
                 onclick="selectStop('${escapeAttr(stop.id)}', '${escapeAttr(stop.name)}', '${escapeAttr(stop.shortId)}')">
                <div class="modal-result-name">${escapeHtml(stop.name)}</div>
                <div class="modal-result-id">
                    정류장 번호: ${escapeHtml(stop.shortId || stop.id)}
                </div>
            </div>
        `).join("");
        resultContainer.classList.remove("hidden");

    } catch (e) {
        searching.classList.add("hidden");
        resultContainer.innerHTML = `
            <div class="modal-result-item" style="cursor:default; color: var(--danger);">
                오류: ${e.message}
            </div>
        `;
        resultContainer.classList.remove("hidden");
    }
}

function selectStop(id, name, shortId) {
    if (currentEditingSlot < 1) return;
    slots[currentEditingSlot] = { id, name, shortId };
    saveSlots();
    renderSlots();
    closeSetupModal();
    // 선택 즉시 도착 정보 보여주기
    showArrivalScreen(currentEditingSlot);
}

// ==========================================
//  유틸리티
// ==========================================

function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
    if (!str) return "";
    return str.replace(/'/g, "\\'").replace(/"/g, "&quot;");
}

// ==========================================
//  이벤트 바인딩
// ==========================================

document.addEventListener("DOMContentLoaded", () => {
    // 슬롯 로드 및 렌더링
    loadSlots();
    renderSlots();

    // 뒤로 버튼
    document.getElementById("back-btn").addEventListener("click", () => {
        showMain();
        renderSlots(); // 슬롯 새로고침
    });

    // 수동 새로고침 버튼
    document.getElementById("refresh-btn").addEventListener("click", () => {
        if (currentSlotIndex >= 0) {
            const slot = slots[currentSlotIndex];
            loadArrivalData(slot.id);
            // 카운트다운 리셋
            countdownSec = REFRESH_INTERVAL_MS / 1000;
        }
    });
});
