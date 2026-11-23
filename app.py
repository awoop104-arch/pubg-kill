import json
import os
import secrets
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="PUBG Kill Match Scoreboard")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "tnals1004")
STATE_FILE = Path("kill_match_state.json")

RoomId = Literal["kill1", "kill2", "kill3", "mefun_ck"]
RoleType = Literal["user", "bj"]

ROOM_META = {
    "kill1": {"name": "킬내기 1번방", "desc": "메인 킬내기 매치 #1"},
    "kill2": {"name": "킬내기 2번방", "desc": "서브 킬내기 매치 #2"},
    "kill3": {"name": "킬내기 3번방", "desc": "서브 킬내기 매치 #3"},
    "mefun_ck": {"name": "메펀ck방", "desc": "메펀 CK 전용 전광판"},
}

admin_tokens: set[str] = set()


def default_room_data(room_id: str) -> dict:
    return {
        "id": room_id,
        "name": ROOM_META[room_id]["name"],
        "desc": ROOM_META[room_id]["desc"],
        "target_kills": 50,
        "chickens": 0,
        "active_bjs": [],  # 해당 방에서 수정 권한이 '활성화'된 BJ client_id 목록
        "rows": [
            {"id": 1, "name": "1팀 / 플레이어A", "kills": 0, "rank_pts": 0, "deduct": 0},
            {"id": 2, "name": "2팀 / 플레이어B", "kills": 0, "rank_pts": 0, "deduct": 0},
        ],
    }


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            # 누락된 방 보정
            data.setdefault("users", {})
            data.setdefault("rooms", {})
            for rid in ROOM_META:
                if rid not in data["rooms"]:
                    data["rooms"][rid] = default_room_data(rid)
            return data
        except Exception:
            pass
    return {
        "users": {},  # client_id -> {"nickname": str, "role": "user"|"bj"}
        "rooms": {rid: default_room_data(rid) for rid in ROOM_META},
    }


state = load_state()


def save_state() -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def verify_admin(authorization: str | None = Header(default=None)) -> None:
    token = (authorization or "").replace("Bearer ", "").strip()
    if token not in admin_tokens:
        raise HTTPException(status_code=403, detail="관리자 인증이 필요합니다.")


def check_room_edit_permission(room_id: str, client_id: str, authorization: str | None) -> str:
    token = (authorization or "").replace("Bearer ", "").strip()
    if token in admin_tokens:
        return "관리자"

    user = state["users"].get(client_id)
    room = state["rooms"].get(room_id)
    if not user or not room:
        raise HTTPException(status_code=403, detail="사용자 또는 방 정보를 찾을 수 없습니다.")
    if user["role"] != "bj" or client_id not in room["active_bjs"]:
        raise HTTPException(status_code=403, detail="이 방에 대한 수정 권한이 비활성화되어 있습니다.")
    return user["nickname"]


# -------------------------
# Pydantic Models
# -------------------------
class RegisterReq(BaseModel):
    client_id: str
    nickname: str


class AdminLoginReq(BaseModel):
    password: str


class SetRoleReq(BaseModel):
    client_id: str
    role: RoleType


class RoomBjToggleReq(BaseModel):
    room_id: RoomId
    client_id: str
    active: bool


class DisableAllReq(BaseModel):
    room_id: RoomId | None = None  # None이면 모든 방 전체 비활성화


class ScoreRow(BaseModel):
    id: int
    name: str
    kills: int
    rank_pts: int
    deduct: int


class UpdateRoomReq(BaseModel):
    client_id: str
    target_kills: int
    chickens: int
    rows: list[ScoreRow]


# -------------------------
# API Endpoints
# -------------------------
@app.post("/api/register")
def register_user(req: RegisterReq):
    nickname = req.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="닉네임을 입력하세요.")

    if req.client_id not in state["users"]:
        state["users"][req.client_id] = {
            "nickname": nickname,
            "role": "user",
        }
    else:
        state["users"][req.client_id]["nickname"] = nickname

    save_state()
    return {"ok": True, "user": state["users"][req.client_id]}


@app.get("/api/bootstrap")
def bootstrap(client_id: str):
    user = state["users"].get(client_id)
    rooms_summary = []
    for rid, r in state["rooms"].items():
        total_kills = sum(max(0, int(row["kills"])) for row in r["rows"])
        rooms_summary.append({
            "id": rid,
            "name": r["name"],
            "desc": r["desc"],
            "total_kills": total_kills,
            "target_kills": r["target_kills"],
            "chickens": r["chickens"],
            "can_edit": bool(user and user["role"] == "bj" and client_id in r["active_bjs"]),
        })
    return {
        "ok": True,
        "user": user,
        "rooms": rooms_summary,
    }


@app.get("/api/rooms/{room_id}")
def get_room(room_id: RoomId, client_id: str):
    room = state["rooms"][room_id]
    user = state["users"].get(client_id)
    can_edit = bool(user and user["role"] == "bj" and client_id in room["active_bjs"])
    return {
        "ok": True,
        "room": room,
        "can_edit": can_edit,
    }


@app.put("/api/rooms/{room_id}")
def update_room(
    room_id: RoomId,
    req: UpdateRoomReq,
    authorization: str | None = Header(default=None),
):
    editor_name = check_room_edit_permission(room_id, req.client_id, authorization)
    room = state["rooms"][room_id]
    room["target_kills"] = max(1, int(req.target_kills))
    room["chickens"] = max(0, int(req.chickens))
    room["rows"] = [row.model_dump() for row in req.rows]
    save_state()
    return {"ok": True, "updated_by": editor_name, "room": room}


@app.post("/api/admin/login")
def admin_login(req: AdminLoginReq):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="관리자 비밀번호가 일치하지 않습니다.")
    token = secrets.token_hex(16)
    admin_tokens.add(token)
    return {"ok": True, "token": token}


@app.get("/api/admin/panel")
def admin_panel(authorization: str | None = Header(default=None)):
    verify_admin(authorization)
    users_list = [
        {"client_id": cid, **u}
        for cid, u in state["users"].items()
    ]
    room_active_map = {
        rid: r["active_bjs"]
        for rid, r in state["rooms"].items()
    }
    return {
        "ok": True,
        "users": users_list,
        "room_active_map": room_active_map,
    }


@app.post("/api/admin/role")
def set_user_role(req: SetRoleReq, authorization: str | None = Header(default=None)):
    verify_admin(authorization)
    user = state["users"].get(req.client_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    user["role"] = req.role
    if req.role == "user":
        # 일반유저로 내리면 모든 방의 활성 권한 즉시 회수
        for r in state["rooms"].values():
            if req.client_id in r["active_bjs"]:
                r["active_bjs"].remove(req.client_id)

    save_state()
    return {"ok": True}


@app.post("/api/admin/room-bj")
def toggle_room_bj(req: RoomBjToggleReq, authorization: str | None = Header(default=None)):
    verify_admin(authorization)
    user = state["users"].get(req.client_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if user["role"] != "bj":
        raise HTTPException(status_code=400, detail="비제이 역할 사용자만 활성화할 수 있습니다.")

    active_list: list[str] = state["rooms"][req.room_id]["active_bjs"]
    if req.active and req.client_id not in active_list:
        active_list.append(req.client_id)
    elif not req.active and req.client_id in active_list:
        active_list.remove(req.client_id)

    save_state()
    return {"ok": True}


@app.post("/api/admin/disable-all")
def disable_all_bjs(req: DisableAllReq, authorization: str | None = Header(default=None)):
    verify_admin(authorization)
    if req.room_id:
        state["rooms"][req.room_id]["active_bjs"] = []
    else:
        for r in state["rooms"].values():
            r["active_bjs"] = []
    save_state()
    return {"ok": True}


# -------------------------
# Single-File Web UI
# -------------------------
HTML_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>PUBG 킬내기 & CK 전광판</title>
<style>
  :root {
    --bg: #0f172a;
    --panel: #1e293b;
    --panel-2: #0b1220;
    --border: #334155;
    --text: #f8fafc;
    --muted: #94a3b8;
    --accent: #f59e0b;
    --green: #10b981;
    --red: #ef4444;
    --blue: #3b82f6;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: 'Malgun Gothic', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text);
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 24px;
    background: var(--panel-2);
    border-bottom: 1px solid var(--border);
  }
  .brand { font-size: 18px; font-weight: 800; color: var(--accent); letter-spacing: -0.3px; }
  .badge {
    display: inline-block;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    background: #334155;
    color: #e2e8f0;
  }
  .badge.bj { background: rgba(59,130,246,0.2); color: #60a5fa; border: 1px solid #3b82f6; }
  .badge.active { background: rgba(16,185,129,0.2); color: #34d399; border: 1px solid #10b981; }
  .badge.admin { background: rgba(245,158,11,0.2); color: #fbbf24; border: 1px solid #f59e0b; }
  button {
    cursor: pointer;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
    padding: 7px 13px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
  }
  button:hover:not(:disabled) { filter: brightness(1.15); }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.primary { background: var(--accent); color: #111827; border-color: var(--accent); }
  button.success { background: var(--green); color: #052e16; border-color: var(--green); }
  button.danger { background: var(--red); color: #fff; border-color: var(--red); }
  input, select {
    background: #0f172a;
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
  }
  .container { max-width: 1080px; margin: 28px auto; padding: 0 20px; }

  /* Lobby Grid */
  .room-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 16px;
    margin-top: 18px;
  }
  .room-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
    transition: transform 0.15s, border-color 0.15s;
    cursor: pointer;
  }
  .room-card:hover { transform: translateY(-3px); border-color: var(--accent); }
  .room-title { font-size: 19px; font-weight: 800; margin-bottom: 6px; }
  .room-desc { font-size: 13px; color: var(--muted); margin-bottom: 14px; }

  /* Scoreboard */
  .board-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 22px;
    box-shadow: 0 12px 30px rgba(0,0,0,0.35);
  }
  .board-top {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }
  table { width: 100%; border-collapse: collapse; margin-top: 16px; }
  th, td {
    padding: 11px 10px;
    border-bottom: 1px solid var(--border);
    text-align: center;
    font-size: 14px;
  }
  th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
  td.name-col { text-align: left; }
  td input[type="number"] { width: 76px; text-align: center; }
  td input[type="text"] { width: 100%; max-width: 240px; }

  /* Scoreboard Bottom Right Chicken + Target Kill % */
  .board-footer {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }
  .chicken-target-box {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 16px;
    background: var(--panel-2);
    border: 1px solid var(--border);
    padding: 12px 18px;
    border-radius: 12px;
  }
  .chicken-stat {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: 800;
    color: #fbbf24;
  }
  .divider-v { width: 1px; height: 32px; background: var(--border); }
  .target-stat { min-width: 210px; }
  .target-stat-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 13px;
    margin-bottom: 6px;
  }
  .pct-highlight { font-size: 18px; font-weight: 900; color: var(--green); }
  .progress-track {
    width: 100%;
    height: 8px;
    background: #1e293b;
    border-radius: 999px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #f59e0b, #10b981);
    transition: width 0.25s ease;
  }

  /* Modals */
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 23, 0.78);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 16px;
  }
  .modal-backdrop.open { display: flex; }
  .modal {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 14px;
    width: 100%;
    max-width: 580px;
    max-height: 88vh;
    overflow-y: auto;
    padding: 22px;
  }
  .user-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }
</style>
</head>
<body>

<header>
  <div style="display:flex; align-items:center; gap:12px;">
    <span class="brand">PUBG KILL MATCH</span>
    <span id="userBadge" class="badge">미접속</span>
    <button id="backLobbyBtn" onclick="showLobby()" style="display:none;">채널 선택으로</button>
  </div>
  <div style="display:flex; align-items:center; gap:8px;">
    <button onclick="openNicknameModal(true)">닉네임 변경</button>
    <button id="adminLoginBtn" onclick="openAdminLogin()">관리자 로그인</button>
    <button id="permissionBtn" class="primary" onclick="openPermissionModal()" style="display:none;">권한 설정</button>
  </div>
</header>

<div class="container">
  <!-- 4개 채널 로비 -->
  <section id="lobbySection">
    <h2 style="margin:0 0 6px 0;">입장할 채널을 선택하세요</h2>
    <p style="margin:0; color:var(--muted); font-size:14px;">일반유저는 조회만 가능하며, 관리자가 지정한 방의 활성화된 비제이만 점수를 수정할 수 있습니다.</p>
    <div id="roomGrid" class="room-grid"></div>
  </section>

  <!-- 방 전광판 화면 -->
  <section id="roomSection" style="display:none;">
    <div class="board-card">
      <div class="board-top">
        <div>
          <div style="display:flex; align-items:center; gap:10px;">
            <h2 id="roomTitle" style="margin:0;">방 제목</h2>
            <span id="roomEditBadge" class="badge">읽기 전용</span>
          </div>
          <div id="roomDesc" style="color:var(--muted); font-size:13px; margin-top:4px;"></div>
        </div>

        <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
          <label style="font-size:13px; color:var(--muted);">
            목표킬:
            <input id="targetKillsInput" type="number" min="1" value="50" style="width:82px;" oninput="recalcFooter()" />
          </label>
          <label style="font-size:13px; color:var(--muted);">
            치킨:
            <input id="chickensInput" type="number" min="0" value="0" style="width:68px;" oninput="recalcFooter()" />
          </label>
          <button id="addRowBtn" onclick="addScoreRow()">+ 팀/인원 추가</button>
          <button id="saveRoomBtn" class="primary" onclick="saveRoomData()">전광판 저장</button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th style="width:60px;">#</th>
            <th style="text-align:left;">팀 / 닉네임</th>
            <th style="width:110px;">킬 수</th>
            <th style="width:110px;">순위 점수</th>
            <th style="width:110px;">감점</th>
            <th style="width:110px;">총점</th>
            <th style="width:70px;">삭제</th>
          </tr>
        </thead>
        <tbody id="scoreBody"></tbody>
      </table>

      <!-- 전광판 하단: 우측 하단 치킨 옆 목표킬 대비 달성률(%) -->
      <div class="board-footer">
        <div style="font-size:13px; color:var(--muted);">
          * 수정 권한이 있는 비제이 또는 관리자만 값을 변경하고 저장할 수 있습니다.
        </div>

        <div class="chicken-target-box">
          <div class="chicken-stat">
            <span>🍗 치킨</span>
            <span id="footerChickenCount">0</span>마리
          </div>
          <div class="divider-v"></div>
          <div class="target-stat">
            <div class="target-stat-header">
              <span>목표킬 달성률 (<strong id="footerCurrentKills">0</strong> / <span id="footerTargetKills">50</span>킬)</span>
              <span id="footerKillPct" class="pct-highlight">0.0%</span>
            </div>
            <div class="progress-track">
              <div id="footerProgressFill" class="progress-fill" style="width:0%;"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</div>

<!-- 초기 닉네임 설정 모달 -->
<div id="nicknameModal" class="modal-backdrop">
  <div class="modal" style="max-width:400px;">
    <h3 style="margin-top:0;">닉네임 설정</h3>
    <p style="font-size:13px; color:var(--muted);">접속 시 사용할 닉네임을 입력하세요. 초기 역할은 일반유저로 등록됩니다.</p>
    <input id="nicknameInput" type="text" placeholder="닉네임 입력" style="width:100%; margin-bottom:14px;" onkeydown="if(event.key==='Enter') submitNickname()" />
    <div style="display:flex; justify-content:flex-end; gap:8px;">
      <button id="cancelNickBtn" onclick="closeNicknameModal()" style="display:none;">취소</button>
      <button class="primary" onclick="submitNickname()">입장하기</button>
    </div>
  </div>
</div>

<!-- 관리자 권한 설정 모달 -->
<div id="permissionModal" class="modal-backdrop">
  <div class="modal">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="margin:0;">관리자 권한 설정</h3>
      <button onclick="closePermissionModal()">닫기</button>
    </div>

    <!-- 방 선택 및 동시 비활성화 컨트롤 -->
    <div style="background:var(--panel-2); border:1px solid var(--border); border-radius:10px; padding:12px; margin-bottom:16px;">
      <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px;">
        <div>
          <label style="font-size:13px; font-weight:700;">대상 방 선택: </label>
          <select id="adminRoomSelect" onchange="renderAdminPanel()">
            <option value="kill1">킬내기 1번방</option>
            <option value="kill2">킬내기 2번방</option>
            <option value="kill3">킬내기 3번방</option>
            <option value="mefun_ck">메펀ck방</option>
          </select>
        </div>
        <div style="display:flex; gap:6px;">
          <button class="danger" onclick="disableAllBjs(true)">이 방 비제이 전체 비활성화</button>
          <button class="danger" onclick="disableAllBjs(false)">모든 방 전체 비활성화</button>
        </div>
      </div>
      <div style="font-size:12px; color:var(--muted); margin-top:8px;">
        * 역할을 <strong>비제이</strong>로 지정한 사용자만 선택한 방에서 개별 활성화/비활성화할 수 있습니다.
      </div>
    </div>

    <div id="adminUserList"></div>
  </div>
</div>

<script>
const ROOM_NAMES = {
  kill1: "킬내기 1번방",
  kill2: "킬내기 2번방",
  kill3: "킬내기 3번방",
  mefun_ck: "메펀ck방",
};

const clientId = localStorage.getItem("pubg_client_id") || (() => {
  const id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
  localStorage.setItem("pubg_client_id", id);
  return id;
})();

let adminToken = sessionStorage.getItem("pubg_admin_token") || "";
let currentUser = null;
let currentRoomId = null;
let currentRoomData = null;
let canEditCurrentRoom = false;
let adminCache = { users: [], room_active_map: {} };
let pollTimer = null;

function isAdmin() {
  return Boolean(adminToken);
}

function syncHeader() {
  const badge = document.getElementById("userBadge");
  if (!currentUser) {
    badge.textContent = "미접속";
    badge.className = "badge";
  } else if (isAdmin()) {
    badge.textContent = `${currentUser.nickname} (관리자)`;
    badge.className = "badge admin";
  } else if (currentUser.role === "bj") {
    badge.textContent = `${currentUser.nickname} (비제이)`;
    badge.className = "badge bj";
  } else {
    badge.textContent = `${currentUser.nickname} (일반유저)`;
    badge.className = "badge";
  }

  document.getElementById("adminLoginBtn").style.display = isAdmin() ? "none" : "inline-block";
  document.getElementById("permissionBtn").style.display = isAdmin() ? "inline-block" : "none";
  document.getElementById("backLobbyBtn").style.display = currentRoomId ? "inline-block" : "none";
}

async function init() {
  const res = await fetch(`/api/bootstrap?client_id=${encodeURIComponent(clientId)}`);
  const data = await res.json();
  currentUser = data.user;
  syncHeader();

  if (!currentUser) {
    openNicknameModal(false);
  } else {
    renderLobby(data.rooms);
  }

  // 3초마다 상태/권한 자동 동기화
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(refreshCurrentView, 3000);
}

async function refreshCurrentView() {
  if (!currentUser) return;
  if (!currentRoomId) {
    const res = await fetch(`/api/bootstrap?client_id=${encodeURIComponent(clientId)}`);
    const data = await res.json();
    currentUser = data.user;
    syncHeader();
    renderLobby(data.rooms);
  } else {
    // 수정 중인 입력 포커스가 없을 때만 자동 갱신
    const activeTag = document.activeElement?.tagName;
    if (activeTag === "INPUT") return;
    await loadRoom(currentRoomId, true);
  }
}

function openNicknameModal(allowCancel) {
  document.getElementById("cancelNickBtn").style.display = allowCancel ? "inline-block" : "none";
  document.getElementById("nicknameInput").value = currentUser ? currentUser.nickname : "";
  document.getElementById("nicknameModal").classList.add("open");
  setTimeout(() => document.getElementById("nicknameInput").focus(), 50);
}

function closeNicknameModal() {
  document.getElementById("nicknameModal").classList.remove("open");
}

async function submitNickname() {
  const nickname = document.getElementById("nicknameInput").value.trim();
  if (!nickname) return alert("닉네임을 입력하세요.");

  const res = await fetch("/api/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: clientId, nickname }),
  });
  const data = await res.json();
  if (!res.ok) return alert(data.detail || "등록 실패");

  currentUser = data.user;
  closeNicknameModal();
  await init();
}

function renderLobby(rooms) {
  document.getElementById("lobbySection").style.display = "block";
  document.getElementById("roomSection").style.display = "none";
  currentRoomId = null;
  syncHeader();

  const grid = document.getElementById("roomGrid");
  grid.innerHTML = rooms.map(r => {
    const pct = r.target_kills > 0 ? ((r.total_kills / r.target_kills) * 100).toFixed(1) : "0.0";
    const permTag = (isAdmin() || r.can_edit)
      ? `<span class="badge active">수정 가능</span>`
      : `<span class="badge">조회 전용</span>`;

    return `
      <div class="room-card" onclick="enterRoom('${r.id}')">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <span class="room-title">${r.name}</span>
          ${permTag}
        </div>
        <div class="room-desc">${r.desc}</div>
        <div style="font-size:13px; color:#cbd5e1; display:flex; justify-content:space-between;">
          <span>킬: <strong>${r.total_kills}</strong> / ${r.target_kills} (${pct}%)</span>
          <span>🍗 ${r.chickens}</span>
        </div>
      </div>
    `;
  }).join("");
}

function showLobby() {
  currentRoomId = null;
  init();
}

async function enterRoom(roomId) {
  currentRoomId = roomId;
  document.getElementById("lobbySection").style.display = "none";
  document.getElementById("roomSection").style.display = "block";
  syncHeader();
  await loadRoom(roomId, false);
}

async function loadRoom(roomId, isSilent) {
  const res = await fetch(`/api/rooms/${roomId}?client_id=${encodeURIComponent(clientId)}`);
  const data = await res.json();
  if (!res.ok) return;

  currentRoomData = data.room;
  canEditCurrentRoom = isAdmin() || data.can_edit;
  renderRoomBoard();
}

function renderRoomBoard() {
  const r = currentRoomData;
  document.getElementById("roomTitle").textContent = r.name;
  document.getElementById("roomDesc").textContent = r.desc;

  const badge = document.getElementById("roomEditBadge");
  if (canEditCurrentRoom) {
    badge.textContent = isAdmin() ? "관리자 수정 가능" : "수정 권한 활성";
    badge.className = "badge active";
  } else {
    badge.textContent = "읽기 전용 (수정 불가)";
    badge.className = "badge";
  }

  const targetInput = document.getElementById("targetKillsInput");
  const chickenInput = document.getElementById("chickensInput");
  targetInput.value = r.target_kills;
  chickenInput.value = r.chickens;
  targetInput.disabled = !canEditCurrentRoom;
  chickenInput.disabled = !canEditCurrentRoom;
  document.getElementById("addRowBtn").style.display = canEditCurrentRoom ? "inline-block" : "none";
  document.getElementById("saveRoomBtn").style.display = canEditCurrentRoom ? "inline-block" : "none";

  const tbody = document.getElementById("scoreBody");
  tbody.innerHTML = r.rows.map((row, idx) => {
    const total = (Number(row.kills) || 0) + (Number(row.rank_pts) || 0) - (Number(row.deduct) || 0);
    if (!canEditCurrentRoom) {
      return `
        <tr>
          <td>${idx + 1}</td>
          <td class="name-col"><strong>${escapeHtml(row.name)}</strong></td>
          <td>${row.kills}</td>
          <td>${row.rank_pts}</td>
          <td>${row.deduct}</td>
          <td><strong>${total}</strong></td>
          <td>-</td>
        </tr>
      `;
    }
    return `
      <tr>
        <td>${idx + 1}</td>
        <td class="name-col"><input type="text" value="${escapeHtml(row.name)}" onchange="updateLocalRow(${idx}, 'name', this.value)" /></td>
        <td><input type="number" min="0" value="${row.kills}" oninput="updateLocalRow(${idx}, 'kills', this.value)" /></td>
        <td><input type="number" value="${row.rank_pts}" oninput="updateLocalRow(${idx}, 'rank_pts', this.value)" /></td>
        <td><input type="number" min="0" value="${row.deduct}" oninput="updateLocalRow(${idx}, 'deduct', this.value)" /></td>
        <td><strong id="rowTotal_${idx}">${total}</strong></td>
        <td><button class="danger" style="padding:4px 8px;" onclick="removeScoreRow(${idx})">X</button></td>
      </tr>
    `;
  }).join("");

  recalcFooter();
}

function updateLocalRow(idx, field, val) {
  if (!currentRoomData) return;
  if (field === "name") {
    currentRoomData.rows[idx].name = val;
  } else {
    currentRoomData.rows[idx][field] = Number(val) || 0;
    const row = currentRoomData.rows[idx];
    const totalEl = document.getElementById(`rowTotal_${idx}`);
    if (totalEl) totalEl.textContent = row.kills + row.rank_pts - row.deduct;
  }
  recalcFooter();
}

function addScoreRow() {
  if (!canEditCurrentRoom) return;
  const nextId = currentRoomData.rows.length + 1;
  currentRoomData.rows.push({
    id: Date.now(),
    name: `${nextId}팀 / 신규`,
    kills: 0,
    rank_pts: 0,
    deduct: 0,
  });
  renderRoomBoard();
}

function removeScoreRow(idx) {
  if (!canEditCurrentRoom) return;
  currentRoomData.rows.splice(idx, 1);
  renderRoomBoard();
}

function recalcFooter() {
  if (!currentRoomData) return;
  const targetKills = Math.max(1, Number(document.getElementById("targetKillsInput").value) || 1);
  const chickens = Math.max(0, Number(document.getElementById("chickensInput").value) || 0);
  const currentKills = currentRoomData.rows.reduce((acc, r) => acc + Math.max(0, Number(r.kills) || 0), 0);
  const pct = (currentKills / targetKills) * 100;

  document.getElementById("footerChickenCount").textContent = chickens;
  document.getElementById("footerCurrentKills").textContent = currentKills;
  document.getElementById("footerTargetKills").textContent = targetKills;
  document.getElementById("footerKillPct").textContent = `${pct.toFixed(1)}%`;
  document.getElementById("footerProgressFill").style.width = `${Math.min(100, pct)}%`;
}

async function saveRoomData() {
  if (!canEditCurrentRoom || !currentRoomId) return;
  const payload = {
    client_id: clientId,
    target_kills: Math.max(1, Number(document.getElementById("targetKillsInput").value) || 1),
    chickens: Math.max(0, Number(document.getElementById("chickensInput").value) || 0),
    rows: currentRoomData.rows,
  };

  const headers = { "Content-Type": "application/json" };
  if (isAdmin()) headers["Authorization"] = `Bearer ${adminToken}`;

  const res = await fetch(`/api/rooms/${currentRoomId}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) return alert(data.detail || "저장 실패");

  currentRoomData = data.room;
  renderRoomBoard();
  alert("전광판이 저장되었습니다.");
}

// -------------------------
// 관리자 로그인 & 권한 설정
// -------------------------
async function openAdminLogin() {
  const pw = prompt("관리자 비밀번호를 입력하세요.");
  if (!pw) return;

  const res = await fetch("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: pw }),
  });
  const data = await res.json();
  if (!res.ok) return alert(data.detail || "비밀번호 오류");

  adminToken = data.token;
  sessionStorage.setItem("pubg_admin_token", adminToken);
  syncHeader();
  if (currentRoomId) await loadRoom(currentRoomId, false);
  await openPermissionModal();
}

async function openPermissionModal() {
  if (!isAdmin()) return;
  if (currentRoomId) {
    document.getElementById("adminRoomSelect").value = currentRoomId;
  }
  document.getElementById("permissionModal").classList.add("open");
  await fetchAdminPanel();
}

function closePermissionModal() {
  document.getElementById("permissionModal").classList.remove("open");
}

async function fetchAdminPanel() {
  const res = await fetch("/api/admin/panel", {
    headers: { "Authorization": `Bearer ${adminToken}` },
  });
  if (res.status === 403) {
    adminToken = "";
    sessionStorage.removeItem("pubg_admin_token");
    closePermissionModal();
    syncHeader();
    return alert("관리자 세션이 만료되었습니다. 다시 로그인하세요.");
  }
  adminCache = await res.json();
  renderAdminPanel();
}

function renderAdminPanel() {
  const selectedRoom = document.getElementById("adminRoomSelect").value;
  const activeSet = new Set(adminCache.room_active_map[selectedRoom] || []);
  const listEl = document.getElementById("adminUserList");

  if (!adminCache.users.length) {
    listEl.innerHTML = `<div style="color:var(--muted); text-align:center; padding:20px;">접속한 유저가 없습니다.</div>`;
    return;
  }

  listEl.innerHTML = adminCache.users.map(u => {
    const isBj = u.role === "bj";
    const isActiveInRoom = isBj && activeSet.has(u.client_id);

    // 어느 방들에 활성화되어 있는지 요약 표시
    const activeRoomsText = isBj
      ? Object.entries(ROOM_NAMES)
          .filter(([rid]) => (adminCache.room_active_map[rid] || []).includes(u.client_id))
          .map(([, rname]) => rname)
          .join(", ") || "활성 방 없음"
      : "일반유저 (권한 신청 불가)";

    const toggleControl = isBj
      ? (isActiveInRoom
          ? `<button class="danger" onclick="toggleBjRoom('${u.client_id}', false)">비활성화</button>`
          : `<button class="success" onclick="toggleBjRoom('${u.client_id}', true)">활성화</button>`)
      : `<span style="color:var(--muted); font-size:12px; min-width:74px; text-align:center;">-</span>`;

    return `
      <div class="user-row">
        <div>
          <div style="font-weight:700;">
            ${escapeHtml(u.nickname)}
            ${u.client_id === clientId ? '<span class="badge" style="margin-left:4px;">나</span>' : ''}
          </div>
          <div style="font-size:12px; color:var(--muted); margin-top:2px;">${activeRoomsText}</div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <select onchange="changeUserRole('${u.client_id}', this.value)">
            <option value="user" ${u.role === "user" ? "selected" : ""}>일반유저</option>
            <option value="bj" ${u.role === "bj" ? "selected" : ""}>비제이</option>
          </select>
          ${toggleControl}
        </div>
      </div>
    `;
  }).join("");
}

async function changeUserRole(targetClientId, role) {
  await fetch("/api/admin/role", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${adminToken}`,
    },
    body: JSON.stringify({ client_id: targetClientId, role }),
  });
  await fetchAdminPanel();
  await refreshCurrentView();
}

async function toggleBjRoom(targetClientId, active) {
  const roomId = document.getElementById("adminRoomSelect").value;
  await fetch("/api/admin/room-bj", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${adminToken}`,
    },
    body: JSON.stringify({ room_id: roomId, client_id: targetClientId, active }),
  });
  await fetchAdminPanel();
  await refreshCurrentView();
}

async function disableAllBjs(onlySelectedRoom) {
  const roomId = onlySelectedRoom ? document.getElementById("adminRoomSelect").value : null;
  await fetch("/api/admin/disable-all", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${adminToken}`,
    },
    body: JSON.stringify({ room_id: roomId }),
  });
  await fetchAdminPanel();
  await refreshCurrentView();
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

init();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PAGE


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
