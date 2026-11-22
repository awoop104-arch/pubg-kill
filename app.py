import asyncio
import json
import os
import threading
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

DATA_FILE = os.environ.get("DATA_FILE", "pubg_kill_match_data.json")
FILE_LOCK = threading.Lock()
STATE_VERSION = 1

MODES = [
    ("solo", "솔로", 1),
    ("duo", "듀오", 2),
    ("squad", "스쿼드", 4),
    ("tiers", "티어표", 0),
]

TIERS = [
    "0티어 최상", "0티어 상", "0티어 중", "0티어 하",
    "1티어 최상", "1티어 상", "1티어 중", "1티어 하",
    "2티어 최상", "2티어 상", "2티어 중", "2티어 하",
    "3티어 최상", "3티어 상", "3티어 중", "3티어 하",
    "4티어 최상", "4티어 상", "4티어 중", "4티어 하",
    "씨앗",
]

INITIAL_PLAYER_TIER_MAP = {
    # 0티어
    "킴코": "0티어 중",
    "위커": "0티어 하",
    "푸우": "0티어 하",
    # 1티어
    "이섭": "1티어 최상",
    "용지": "1티어 상",
    "대한": "1티어 상",
    "리호": "1티어 상",
    "실인": "1티어 상",
    "군단": "1티어 상",
    "재화": "1티어 상",
    "찐봉": "1티어 상",
    "오줌": "1티어 상",
    "주누": "1티어 상",
    "우진": "1티어 상",
    "대장": "1티어 중",
    "재석": "1티어 중",
    "임수민": "1티어 하",
    "정옥": "1티어 하",
    "태민": "1티어 하",
    # 2티어
    "뒷축": "2티어 최상",
    "까릉": "2티어 최상",
    "도연": "2티어 최상",
    "멍뭉": "2티어 최상",
    "릭스": "2티어 최상",
    "페이": "2티어 최상",
    "시팅": "2티어 최상",
    "모근": "2티어 최상",
    "스타": "2티어 최상",
    "쫀쫀": "2티어 최상",
    "토크": "2티어 상",
    "정현석": "2티어 상",
    "세계": "2티어 상",
    "무이": "2티어 상",
    "하품": "2티어 상",
    "하온": "2티어 상",
    "토이": "2티어 상",
    "그림": "2티어 상",
    "잉누": "2티어 상",
    "찬율": "2티어 상",
    "죠하": "2티어 중",
    "도링": "2티어 중",
    "애두": "2티어 중",
    "윤창": "2티어 중",
    "피곤": "2티어 중",
    "투두": "2티어 중",
    "한솔": "2티어 중",
    "캘린": "2티어 중",
    "시우": "2티어 중",
    "밍정투": "2티어 중",
    "성연뚱": "2티어 중",
    "알랄": "2티어 중",
    "류연": "2티어 중",
    "용갓": "2티어 중",
    "밍훈": "2티어 중",
    "시멈": "2티어 중",
    "아지": "2티어 중",
    "배경한": "2티어 중",
    "은지": "2티어 하",
    "적모": "2티어 하",
    "대휘": "2티어 하",
    # 3티어
    "가을": "3티어 최상",
    "경이": "3티어 최상",
    "천호": "3티어 최상",
    "응갈맨": "3티어 최상",
    "으나": "3티어 최상",
    "예동": "3티어 최상",
    "나영": "3티어 최상",
    "은주": "3티어 최상",
    "도유": "3티어 최상",
    "도리": "3티어 최상",
    "러브": "3티어 최상",
    "아바": "3티어 최상",
    "망고": "3티어 상",
    "혜빈": "3티어 상",
    "율지": "3티어 상",
    "씨원": "3티어 상",
    "아로": "3티어 상",
    "원주": "3티어 상",
    "랑구": "3티어 상",
    "성인": "3티어 중",
    "무디": "3티어 중",
    "주녕": "3티어 중",
    "와니": "3티어 중",
    "희롱": "3티어 하",
    "현정": "3티어 하",
    "민클": "3티어 하",
    "재진": "3티어 하",
    "강원": "3티어 하",
    # 4티어
    "딸지": "4티어 최상",
    "다름": "4티어 최상",
    "지원": "4티어 최상",
    "슈임": "4티어 최상",
    "준영": "4티어 최상",
    "마우": "4티어 상",
    "종수": "4티어 상",
    "리갱": "4티어 상",
    "해련": "4티어 상",
    "감튀": "4티어 상",
    "빈쁜": "4티어 중",
    "봄덕": "4티어 중",
    "쮸정": "4티어 중",
    "포노": "4티어 중",
    "하네": "4티어 중",
    # 씨앗
    "가빈": "씨앗",
    "청진": "씨앗",
    "이로로": "씨앗",
    "앙": "씨앗",
}

PENALTIES = [0] + [-n for n in range(1, 11)]
HANDICAPS = list(range(0, 11))


def default_tier_board():
    board = {tier: [] for tier in TIERS}
    for player_name, tier in INITIAL_PLAYER_TIER_MAP.items():
        if tier in board and player_name not in board[tier]:
            board[tier].append(player_name)
    return board


def normalize_tier_board(raw_board):
    board = {tier: [] for tier in TIERS}
    if not isinstance(raw_board, dict):
        return default_tier_board()

    has_any = False
    for tier in TIERS:
        items = raw_board.get(tier, [])
        if isinstance(items, list) and len(items) > 0:
            has_any = True
        if isinstance(items, list):
            for name in items:
                clean = str(name or "").strip()
                if clean and clean not in board[tier]:
                    board[tier].append(clean)

    return board if has_any else default_tier_board()


def default_mode_data():
    return {
        "team_count": 2,
        "teams": [],
    }


def default_db():
    return {
        "modes": {
            mode_key: default_mode_data()
            for mode_key, _, _ in MODES
            if mode_key != "tiers"
        },
        "tier_board": default_tier_board(),
    }


def load_db():
    base = default_db()
    if not os.path.exists(DATA_FILE):
        return base

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return base

    if "modes" not in raw and ("teams" in raw or "team_count" in raw):
        base["modes"]["squad"] = {
            "team_count": max(2, min(10, int(raw.get("team_count", 2)))),
            "teams": raw.get("teams", []),
        }
        return base

    raw_modes = raw.get("modes", {})
    for mode_key, _, _ in MODES:
        if mode_key == "tiers":
            continue
        m = raw_modes.get(mode_key, {})
        if not isinstance(m, dict):
            m = {}
        count = max(2, min(10, int(m.get("team_count", 2))))
        teams = m.get("teams", [])
        if not isinstance(teams, list):
            teams = []
        base["modes"][mode_key] = {
            "team_count": count,
            "teams": teams,
        }

    base["tier_board"] = normalize_tier_board(raw.get("tier_board"))
    return base


def save_db(data):
    global STATE_VERSION
    parent_dir = os.path.dirname(os.path.abspath(DATA_FILE))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    tmp_file = f"{DATA_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, DATA_FILE)
    STATE_VERSION += 1


class ModeStatePayload(BaseModel):
    team_count: int
    teams: list
    client_id: str = ""


class TierBoardPayload(BaseModel):
    tier_board: dict
    client_id: str = ""


app = FastAPI(title="PUBG 킬내기 관리 웹 (실시간)")


@app.get("/api/state")
def get_state():
    with FILE_LOCK:
        data = load_db()
        version = STATE_VERSION
    return {
        "version": version,
        "modes_meta": [
            {"key": k, "label": label, "max_members": max_m}
            for k, label, max_m in MODES
        ],
        "tiers": TIERS,
        "tier_board": data["tier_board"],
        "penalties": PENALTIES,
        "handicaps": HANDICAPS,
        "data": data,
    }


@app.put("/api/modes/{mode_key}")
def update_mode(mode_key: str, payload: ModeStatePayload):
    valid_keys = {k for k, _, _ in MODES if k != "tiers"}
    if mode_key not in valid_keys:
        raise HTTPException(status_code=400, detail="지원하지 않는 모드입니다.")

    count = max(2, min(10, int(payload.team_count)))
    with FILE_LOCK:
        data = load_db()
        data["modes"][mode_key] = {
            "team_count": count,
            "teams": payload.teams,
        }
        save_db(data)
        version = STATE_VERSION
    return {"ok": True, "version": version, "mode": mode_key, "data": data}


@app.post("/api/modes/{mode_key}/reset")
def reset_mode(mode_key: str):
    valid_keys = {k for k, _, _ in MODES if k != "tiers"}
    if mode_key not in valid_keys:
        raise HTTPException(status_code=400, detail="지원하지 않는 모드입니다.")

    with FILE_LOCK:
        data = load_db()
        data["modes"][mode_key] = default_mode_data()
        save_db(data)
        version = STATE_VERSION
    return {"ok": True, "version": version, "mode": mode_key, "data": data}


@app.put("/api/tier-board")
def update_tier_board(payload: TierBoardPayload):
    with FILE_LOCK:
        data = load_db()
        data["tier_board"] = normalize_tier_board(payload.tier_board)
        save_db(data)
        version = STATE_VERSION
    return {"ok": True, "version": version, "data": data}


@app.post("/api/tier-board/reset")
def reset_tier_board():
    with FILE_LOCK:
        data = load_db()
        data["tier_board"] = default_tier_board()
        save_db(data)
        version = STATE_VERSION
    return {"ok": True, "version": version, "data": data}


@app.get("/api/stream")
async def stream_state(request: Request):
    async def event_generator():
        last_sent_version = -1
        last_ping = time.monotonic()
        while True:
            if await request.is_disconnected():
                break

            with FILE_LOCK:
                current_version = STATE_VERSION
                current_data = load_db() if current_version != last_sent_version else None

            if current_data is not None:
                last_sent_version = current_version
                payload = json.dumps(
                    {"version": current_version, "data": current_data},
                    ensure_ascii=False,
                )
                yield f"data: {payload}\n\n"
                last_ping = time.monotonic()
            elif time.monotonic() - last_ping >= 15:
                yield ": keepalive\n\n"
                last_ping = time.monotonic()

            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


HTML_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>PUBG 킬내기 관리</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "맑은 고딕", Malgun Gothic, -apple-system, BlinkMacSystemFont, sans-serif;
      background: #f3f5f8;
      color: #1e242b;
    }
    .wrap {
      max-width: 1320px;
      margin: 0 auto;
      padding: 18px 16px 40px;
    }
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }
    .title-area {
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }
    h1 {
      margin: 0;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.3px;
    }
    .tabs {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .tab-btn {
      padding: 8px 16px;
      border: 1px solid #cbd5e1;
      background: #fff;
      color: #334155;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }
    .tab-btn.active {
      background: #1e293b;
      color: #fff;
      border-color: #1e293b;
    }
    .info-text {
      font-size: 13px;
      color: #475569;
    }
    .card {
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 14px 16px;
      margin-bottom: 14px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .settings-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .settings-left {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
    }
    .settings-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    input[type="text"], input[type="number"], select {
      padding: 6px 8px;
      border: 1px solid #cbd5e1;
      border-radius: 7px;
      font-size: 14px;
      background: #fff;
      color: #0f172a;
    }
    input[type="number"] {
      width: 68px;
    }
    button {
      padding: 7px 13px;
      border-radius: 8px;
      border: 1px solid #cbd5e1;
      background: #f8fafc;
      color: #0f172a;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }
    button:hover {
      background: #eef2f6;
    }
    button.danger {
      background: #fff;
      border-color: #fca5a5;
      color: #b91c1c;
    }
    button.danger:hover {
      background: #fef2f2;
    }
    .team-header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
      padding-bottom: 8px;
      border-bottom: 1px solid #f1f5f9;
    }
    .team-title-group {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .team-badge {
      font-weight: 800;
      font-size: 15px;
      color: #0f172a;
      margin-right: 4px;
    }
    .team-right {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .summary-text {
      font-size: 13px;
      font-weight: 700;
      color: #0f766e;
    }
    .member-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      padding: 5px 0;
    }
    .slot-label {
      width: 42px;
      font-size: 13px;
      font-weight: 700;
      color: #475569;
    }
    .member-name {
      width: 190px;
    }
    .field-label {
      font-size: 13px;
      color: #475569;
      margin-left: 4px;
    }
    .live-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 600;
      color: #0f766e;
      background: #f0fdfa;
      border: 1px solid #99f6e4;
      padding: 4px 10px;
      border-radius: 999px;
    }
    .live-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #14b8a6;
    }

    /* 티어표 그리드 스타일 */
    .tier-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
      gap: 12px;
    }
    .tier-box {
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 10px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .tier-box-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid #f1f5f9;
      padding-bottom: 6px;
    }
    .tier-name-badge {
      font-size: 14px;
      font-weight: 800;
      color: #0f172a;
    }
    .tier-count {
      font-size: 12px;
      font-weight: 700;
      color: #64748b;
    }
    .tier-members {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      min-height: 36px;
      align-content: flex-start;
    }
    .member-chip {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: #f8fafc;
      border: 1px solid #cbd5e1;
      border-radius: 999px;
      padding: 3px 9px;
      font-size: 12px;
      font-weight: 600;
      color: #1e293b;
    }
    .chip-del {
      border: none;
      background: transparent;
      color: #94a3b8;
      padding: 0 2px;
      font-size: 12px;
      line-height: 1;
      cursor: pointer;
    }
    .chip-del:hover {
      color: #dc2626;
      background: transparent;
    }
    .tier-add-row {
      display: flex;
      gap: 6px;
    }
    .tier-add-input {
      flex: 1;
      min-width: 0;
      padding: 5px 8px;
      font-size: 13px;
    }
    .tier-add-btn {
      padding: 5px 10px;
      font-size: 12px;
      white-space: nowrap;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="title-area">
        <h1>PUBG KILL MATCH</h1>
        <div class="tabs" id="modeTabs"></div>
      </div>
      <div class="info-text" id="modeInfo"></div>
    </header>

    <div class="card">
      <div class="settings-row">
        <div class="settings-left" id="modeSettingsLeft"></div>
        <div class="settings-actions">
          <span class="live-badge" id="syncBadge">
            <span class="live-dot"></span>
            <span id="saveStatus">실시간 동기화 중</span>
          </span>
          <button class="danger" id="resetBtn" onclick="resetCurrentView()">초기화</button>
        </div>
      </div>
    </div>

    <div id="mainContent"></div>
  </div>

  <script>
    const clientId = Math.random().toString(36).slice(2);
    let state = null;
    let currentMode = "solo";
    let localVersion = 0;
    let saveTimer = null;
    let isSaving = false;
    let pendingSave = false;
    let eventSource = null;

    function getModeMeta(modeKey = currentMode) {
      return state.modes_meta.find(m => m.key === modeKey) || { key: modeKey, label: modeKey, max_members: 4 };
    }

    function getModeData(modeKey = currentMode) {
      if (!state.data.modes[modeKey]) {
        state.data.modes[modeKey] = { team_count: 2, teams: [] };
      }
      return state.data.modes[modeKey];
    }

    function getTierBoard() {
      if (!state.data.tier_board) {
        state.data.tier_board = {};
      }
      state.tiers.forEach(t => {
        if (!Array.isArray(state.data.tier_board[t])) {
          state.data.tier_board[t] = [];
        }
      });
      return state.data.tier_board;
    }

    function buildDynamicPlayerTierMap() {
      const map = {};
      const board = getTierBoard();
      state.tiers.forEach(tier => {
        const list = board[tier] || [];
        list.forEach(rawName => {
          const clean = (rawName || "").trim();
          if (clean) {
            map[clean] = tier;
            map[clean.replace(/\s+/g, "")] = tier;
          }
        });
      });
      return map;
    }

    function lookupAutoTier(rawName) {
      const cleaned = (rawName || "").trim();
      if (!cleaned) return "";
      const map = buildDynamicPlayerTierMap();
      if (Object.prototype.hasOwnProperty.call(map, cleaned)) {
        return map[cleaned];
      }
      const noSpace = cleaned.replace(/\s+/g, "");
      if (Object.prototype.hasOwnProperty.call(map, noSpace)) {
        return map[noSpace];
      }
      return "";
    }

    function collectCurrentTeamUI() {
      const meta = getModeMeta(currentMode);
      const countInput = document.getElementById("teamCountInput");
      const countVal = countInput ? parseInt(countInput.value, 10) : 2;
      const teamCount = Math.max(2, Math.min(10, Number.isNaN(countVal) ? 2 : countVal));
      const cards = document.querySelectorAll(".team-card");
      const teams = [];

      cards.forEach((card, idx) => {
        const nameEl = card.querySelector(".team-name-input");
        const summaryEl = card.querySelector(".summary-text");
        const memberRows = card.querySelectorAll(".member-row");
        const members = [];

        memberRows.forEach((row, sIdx) => {
          if (sIdx >= meta.max_members) return;
          const mName = row.querySelector(".member-name").value.trim();
          const mTier = row.querySelector(".member-tier").value;
          const mPenalty = parseInt(row.querySelector(".member-penalty").value, 10) || 0;
          const mHandicap = parseInt(row.querySelector(".member-handicap").value, 10) || 0;
          members.push({
            slot: sIdx + 1,
            name: mName,
            tier: mTier,
            penalty: mPenalty,
            handicap: mHandicap
          });
        });

        teams.push({
          name: (nameEl.value || "").trim() || `TEAM ${idx + 1}`,
          summary: summaryEl.textContent || "",
          members
        });
      });

      return { team_count: teamCount, teams, client_id: clientId };
    }

    function scheduleAutoSave(delay = 250) {
      document.getElementById("saveStatus").textContent = "자동 저장 중...";
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        saveTimer = null;
        flushAutoSave();
      }, delay);
    }

    async function flushAutoSave() {
      if (isSaving) {
        pendingSave = true;
        return;
      }
      isSaving = true;

      try {
        if (currentMode === "tiers") {
          const payload = {
            tier_board: getTierBoard(),
            client_id: clientId
          };
          const res = await fetch("/api/tier-board", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          if (!res.ok) {
            document.getElementById("saveStatus").textContent = "저장 오류 (재시도 대기)";
            return;
          }
          const result = await res.json();
          localVersion = Math.max(localVersion, result.version || 0);
          state.data = result.data;
          document.getElementById("saveStatus").textContent = "실시간 저장 완료";
        } else {
          const modeToSave = currentMode;
          const payload = collectCurrentTeamUI();
          state.data.modes[modeToSave] = {
            team_count: payload.team_count,
            teams: payload.teams
          };
          const res = await fetch(`/api/modes/${modeToSave}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          if (!res.ok) {
            document.getElementById("saveStatus").textContent = "저장 오류 (재시도 대기)";
            return;
          }
          const result = await res.json();
          localVersion = Math.max(localVersion, result.version || 0);
          state.data = result.data;
          document.getElementById("saveStatus").textContent = "실시간 저장 완료";
        }
      } catch (err) {
        document.getElementById("saveStatus").textContent = "연결 불안정";
      } finally {
        isSaving = false;
        if (pendingSave) {
          pendingSave = false;
          flushAutoSave();
        }
      }
    }

    function renderTabs() {
      const container = document.getElementById("modeTabs");
      container.innerHTML = "";
      state.modes_meta.forEach(m => {
        const btn = document.createElement("button");
        btn.className = "tab-btn" + (m.key === currentMode ? " active" : "");
        btn.textContent = m.label;
        btn.onclick = () => switchMode(m.key);
        container.appendChild(btn);
      });
    }

    function getFocusSnapshot() {
      const active = document.activeElement;
      if (!active || !active.dataset || !active.dataset.fieldKey) return null;
      return {
        fieldKey: active.dataset.fieldKey,
        value: active.value,
        selectionStart: active.selectionStart,
        selectionEnd: active.selectionEnd
      };
    }

    function restoreFocusSnapshot(snap) {
      if (!snap) return;
      const target = document.querySelector(`[data-field-key="${snap.fieldKey}"]`);
      if (!target) return;
      target.focus();
      if (typeof snap.selectionStart === "number" && typeof target.setSelectionRange === "function") {
        try {
          target.setSelectionRange(snap.selectionStart, snap.selectionEnd);
        } catch (e) {}
      }
    }

    function renderSettingsBar() {
      const leftEl = document.getElementById("modeSettingsLeft");
      const resetBtn = document.getElementById("resetBtn");

      if (currentMode === "tiers") {
        const board = getTierBoard();
        const totalCount = state.tiers.reduce((acc, t) => acc + (board[t] ? board[t].length : 0), 0);
        document.getElementById("modeInfo").textContent =
          `[티어표] 전체 티어 한눈에 보기 · 티어별 인원 추가/삭제 시 실시간 반영`;
        leftEl.innerHTML = `
          <strong>전체 등록 인원</strong>
          <span class="info-text">${totalCount}명 (${state.tiers.length}개 세부 티어)</span>
        `;
        resetBtn.textContent = "기본 티어표 복원";
      } else {
        const meta = getModeMeta(currentMode);
        const modeData = getModeData(currentMode);
        const teamCount = Math.max(2, Math.min(10, parseInt(modeData.team_count || 2, 10)));

        document.getElementById("modeInfo").textContent =
          `[${meta.label}] AI 밸런스 조절 제외 · 최대 10팀 / 팀당 최대 ${meta.max_members}명`;
        leftEl.innerHTML = `
          <label for="teamCountInput"><strong>참가 팀 수</strong></label>
          <input type="number" id="teamCountInput" min="2" max="10" value="${teamCount}" />
          <span class="info-text">${meta.label} 기준 · 팀당 최대 ${meta.max_members}명</span>
        `;
        resetBtn.textContent = "초기화";

        document.getElementById("teamCountInput").addEventListener("change", () => {
          const current = collectCurrentTeamUI();
          state.data.modes[currentMode] = {
            team_count: current.team_count,
            teams: current.teams
          };
          renderMainContent(false);
          scheduleAutoSave(50);
        });
      }
    }

    function addPlayerToTier(tier, inputEl) {
      const rawName = (inputEl.value || "").trim();
      if (!rawName) return;

      const board = getTierBoard();
      // 기존 다른 티어에 동일 이름이 있으면 중복 제거 후 새 티어로 이동
      state.tiers.forEach(t => {
        board[t] = (board[t] || []).filter(n => n !== rawName);
      });
      board[tier].push(rawName);
      inputEl.value = "";

      renderSettingsBar();
      renderTierBoard(false);
      scheduleAutoSave(50);
    }

    function removePlayerFromTier(tier, playerName) {
      const board = getTierBoard();
      board[tier] = (board[tier] || []).filter(n => n !== playerName);
      renderSettingsBar();
      renderTierBoard(false);
      scheduleAutoSave(50);
    }

    function renderTierBoard(preserveFocus = false) {
      const focusSnap = preserveFocus ? getFocusSnapshot() : null;
      const board = getTierBoard();
      const container = document.getElementById("mainContent");
      container.innerHTML = "";

      const grid = document.createElement("div");
      grid.className = "tier-grid";

      state.tiers.forEach((tier, tIdx) => {
        const players = board[tier] || [];
        const box = document.createElement("div");
        box.className = "tier-box";

        const header = document.createElement("div");
        header.className = "tier-box-header";
        header.innerHTML = `
          <span class="tier-name-badge">${escapeHtml(tier)}</span>
          <span class="tier-count">${players.length}명</span>
        `;
        box.appendChild(header);

        const membersWrap = document.createElement("div");
        membersWrap.className = "tier-members";
        if (players.length === 0) {
          membersWrap.innerHTML = `<span class="info-text">등록된 인원 없음</span>`;
        } else {
          players.forEach(name => {
            const chip = document.createElement("span");
            chip.className = "member-chip";
            chip.innerHTML = `
              <span>${escapeHtml(name)}</span>
              <button type="button" class="chip-del" title="삭제">×</button>
            `;
            chip.querySelector(".chip-del").onclick = () => removePlayerFromTier(tier, name);
            membersWrap.appendChild(chip);
          });
        }
        box.appendChild(membersWrap);

        const inputKey = `tier-add-${tIdx}`;
        const addRow = document.createElement("div");
        addRow.className = "tier-add-row";
        const inputVal = (focusSnap && focusSnap.fieldKey === inputKey) ? focusSnap.value : "";
        addRow.innerHTML = `
          <input type="text" class="tier-add-input" data-field-key="${inputKey}" placeholder="이름 입력 후 추가" value="${escapeHtml(inputVal)}" />
          <button type="button" class="tier-add-btn">추가</button>
        `;

        const addInput = addRow.querySelector(".tier-add-input");
        const addBtn = addRow.querySelector(".tier-add-btn");
        addBtn.onclick = () => addPlayerToTier(tier, addInput);
        addInput.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            addPlayerToTier(tier, addInput);
          }
        });

        box.appendChild(addRow);
        grid.appendChild(box);
      });

      container.appendChild(grid);

      if (preserveFocus) {
        restoreFocusSnapshot(focusSnap);
      }
    }

    function renderTeams(preserveFocus = false) {
      const focusSnap = preserveFocus ? getFocusSnapshot() : null;
      const meta = getModeMeta(currentMode);
      const modeData = getModeData(currentMode);
      const teamCount = Math.max(2, Math.min(10, parseInt(modeData.team_count || 2, 10)));

      const listEl = document.getElementById("mainContent");
      listEl.innerHTML = "";
      const savedTeams = modeData.teams || [];

      for (let tIdx = 0; tIdx < teamCount; tIdx++) {
        const saved = savedTeams[tIdx] || {};
        const teamNameKey = `${currentMode}-t${tIdx}-name`;
        const teamName = (focusSnap && focusSnap.fieldKey === teamNameKey)
          ? focusSnap.value
          : (saved.name || `TEAM ${tIdx + 1}`);
        const summary = saved.summary || "";
        const savedMembers = saved.members || [];

        const card = document.createElement("div");
        card.className = "card team-card";

        const header = document.createElement("div");
        header.className = "team-header";

        const left = document.createElement("div");
        left.className = "team-title-group";
        left.innerHTML = `
          <span class="team-badge">TEAM ${tIdx + 1}</span>
          <label><span class="field-label">팀 이름</span></label>
          <input type="text" class="team-name-input" data-field-key="${teamNameKey}" value="${escapeHtml(teamName)}" style="width:160px;" />
        `;
        left.querySelector(".team-name-input").addEventListener("input", () => scheduleAutoSave());

        const right = document.createElement("div");
        right.className = "team-right";

        const summarySpan = document.createElement("span");
        summarySpan.className = "summary-text";
        summarySpan.textContent = summary;

        const doneBtn = document.createElement("button");
        doneBtn.textContent = "완료";
        doneBtn.onclick = () => completeTeam(card);

        right.appendChild(summarySpan);
        right.appendChild(doneBtn);

        header.appendChild(left);
        header.appendChild(right);
        card.appendChild(header);

        for (let slot = 1; slot <= meta.max_members; slot++) {
          const mSaved = savedMembers[slot - 1] || {};
          const row = document.createElement("div");
          row.className = "member-row";

          const mNameKey = `${currentMode}-t${tIdx}-s${slot}-name`;
          const mNameVal = (focusSnap && focusSnap.fieldKey === mNameKey)
            ? focusSnap.value
            : (mSaved.name || "");

          const matchedTier = lookupAutoTier(mNameVal);
          const effectiveTier = matchedTier || (mSaved.tier || "");

          const tierOptions = [`<option value="">선택</option>`]
            .concat(state.tiers.map(t => `<option value="${t}" ${effectiveTier === t ? "selected" : ""}>${t}</option>`))
            .join("");

          const penaltyVal = mSaved.penalty !== undefined ? mSaved.penalty : 0;
          const penaltyOptions = state.penalties
            .map(p => `<option value="${p}" ${Number(penaltyVal) === p ? "selected" : ""}>${p}</option>`)
            .join("");

          const handicapVal = mSaved.handicap !== undefined ? mSaved.handicap : 0;
          const handicapOptions = state.handicaps
            .map(h => `<option value="${h}" ${Number(handicapVal) === h ? "selected" : ""}>${h}</option>`)
            .join("");

          row.innerHTML = `
            <span class="slot-label">${slot}번</span>
            <input type="text" class="member-name" data-field-key="${mNameKey}" placeholder="멤버 이름" value="${escapeHtml(mNameVal)}" />
            <span class="field-label">티어</span>
            <select class="member-tier">${tierOptions}</select>
            <span class="field-label">감점</span>
            <select class="member-penalty">${penaltyOptions}</select>
            <span class="field-label">킬핸디</span>
            <select class="member-handicap">${handicapOptions}</select>
          `;

          const nameInput = row.querySelector(".member-name");
          const tierSelect = row.querySelector(".member-tier");

          const applyAutoTier = () => {
            const autoTier = lookupAutoTier(nameInput.value);
            if (autoTier && state.tiers.includes(autoTier)) {
              tierSelect.value = autoTier;
            }
          };

          nameInput.addEventListener("input", () => {
            applyAutoTier();
            scheduleAutoSave();
          });
          nameInput.addEventListener("change", () => {
            applyAutoTier();
            scheduleAutoSave(50);
          });
          tierSelect.addEventListener("change", () => scheduleAutoSave(50));
          row.querySelector(".member-penalty").addEventListener("change", () => scheduleAutoSave(50));
          row.querySelector(".member-handicap").addEventListener("change", () => scheduleAutoSave(50));

          card.appendChild(row);
        }

        listEl.appendChild(card);
      }

      if (preserveFocus) {
        restoreFocusSnapshot(focusSnap);
      }
    }

    function renderMainContent(preserveFocus = false) {
      if (currentMode === "tiers") {
        renderTierBoard(preserveFocus);
      } else {
        renderTeams(preserveFocus);
      }
    }

    function escapeHtml(str) {
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    async function completeTeam(card) {
      let penaltySum = 0;
      let handicapSum = 0;
      card.querySelectorAll(".member-row").forEach(row => {
        penaltySum += parseInt(row.querySelector(".member-penalty").value, 10) || 0;
        handicapSum += parseInt(row.querySelector(".member-handicap").value, 10) || 0;
      });
      card.querySelector(".summary-text").textContent =
        `완료 · 감점 합계: ${penaltySum} | 킬핸디 합계: ${handicapSum}`;
      if (saveTimer) {
        clearTimeout(saveTimer);
        saveTimer = null;
      }
      await flushAutoSave();
    }

    async function switchMode(nextMode) {
      if (nextMode === currentMode) return;
      if (saveTimer) {
        clearTimeout(saveTimer);
        saveTimer = null;
        await flushAutoSave();
      }
      currentMode = nextMode;
      renderTabs();
      renderSettingsBar();
      renderMainContent(false);
    }

    async function resetCurrentView() {
      if (saveTimer) {
        clearTimeout(saveTimer);
        saveTimer = null;
      }

      if (currentMode === "tiers") {
        if (!confirm("티어표를 기본 명단으로 되돌릴까요?")) return;
        const res = await fetch("/api/tier-board/reset", { method: "POST" });
        if (!res.ok) {
          alert("초기화 중 오류가 발생했습니다.");
          return;
        }
        const result = await res.json();
        localVersion = Math.max(localVersion, result.version || 0);
        state.data = result.data;
        renderSettingsBar();
        renderMainContent(false);
        document.getElementById("saveStatus").textContent = "기본 티어표 복원 완료";
        return;
      }

      const meta = getModeMeta(currentMode);
      if (!confirm(`[${meta.label}] 모드 데이터를 초기화할까요?`)) return;

      const res = await fetch(`/api/modes/${currentMode}/reset`, { method: "POST" });
      if (!res.ok) {
        alert("초기화 중 오류가 발생했습니다.");
        return;
      }
      const result = await res.json();
      localVersion = Math.max(localVersion, result.version || 0);
      state.data = result.data;
      renderSettingsBar();
      renderMainContent(false);
      document.getElementById("saveStatus").textContent = `${meta.label} 초기화 완료`;
    }

    function connectRealtimeStream() {
      if (eventSource) {
        eventSource.close();
      }
      eventSource = new EventSource("/api/stream");
      eventSource.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (!msg || typeof msg.version !== "number") return;
          if (msg.version <= localVersion) return;
          if (saveTimer || isSaving) return;

          localVersion = msg.version;
          state.data = msg.data;
          renderSettingsBar();
          renderMainContent(true);
          document.getElementById("saveStatus").textContent = "실시간 동기화됨";
        } catch (e) {}
      };
      eventSource.onerror = () => {
        document.getElementById("saveStatus").textContent = "재연결 중...";
      };
    }

    async function initApp() {
      const res = await fetch("/api/state");
      state = await res.json();
      localVersion = state.version || 1;
      renderTabs();
      renderSettingsBar();
      renderMainContent(false);
      connectRealtimeStream();
    }

    initApp();
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PAGE


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
