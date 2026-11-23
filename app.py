import asyncio
import hashlib
import hmac
import json
import os
import threading
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

DATA_FILE = os.environ.get("DATA_FILE", "pubg_kill_match_data.json")
EDIT_PIN = os.environ.get("EDIT_PIN", "tnals1004")
TOKEN_SECRET = os.environ.get("TOKEN_SECRET", f"pubg-kill-match-{EDIT_PIN}")

FILE_LOCK = threading.Lock()
STATE_VERSION = 1
PRESENCE_TTL_SECONDS = 25.0

# channel_id -> { client_id: last_seen_monotonic }
CHANNEL_PRESENCE: dict[str, dict[str, float]] = {}

CHANNELS = [
    ("kill1", "킬내기 1번방", "킬내기 매치 #1"),
    ("kill2", "킬내기 2번방", "킬내기 매치 #2"),
    ("kill3", "킬내기 3번방", "킬내기 매치 #3"),
    ("mefun_ck", "메펀ck방", "메펀 CK 전용"),
]
VALID_CHANNELS = {cid for cid, _, _ in CHANNELS}

MODES = [
    ("solo", "솔로", 1),
    ("duo", "듀오", 2),
    ("squad", "스쿼드", 4),
    ("tiers", "티어표", 0),
    ("scoreboard", "점수판", 0),
]

TEAM_MODES = [
    ("solo", "솔로", 1),
    ("duo", "듀오", 2),
    ("squad", "스쿼드", 4),
]

MAX_ROUNDS = 30

TIER_GROUPS = [
    ("0티어", ["0티어 최상", "0티어 상", "0티어 중", "0티어 하"]),
    ("1티어", ["1티어 최상", "1티어 상", "1티어 중", "1티어 하"]),
    ("2티어", ["2티어 최상", "2티어 상", "2티어 중", "2티어 하"]),
    ("3티어", ["3티어 최상", "3티어 상", "3티어 중", "3티어 하"]),
    ("4티어", ["4티어 최상", "4티어 상", "4티어 중", "4티어 하"]),
    ("씨앗", ["씨앗"]),
]

TIERS = [t for _, sub_list in TIER_GROUPS for t in sub_list]

INITIAL_PLAYER_TIER_MAP = {
    "킴코": "0티어 중",
    "워커": "0티어 하",
    "푸우": "0티어 하",
    "이썹": "1티어 최상",
    "몽지": "1티어 상",
    "대한": "1티어 상",
    "리호": "1티어 상",
    "대장": "1티어 중",
    "재석": "1티어 중",
    "실인": "1티어 하",
    "군단": "1티어 하",
    "재화": "1티어 하",
    "씬봉": "1티어 하",
    "오숍": "1티어 하",
    "주누": "1티어 하",
    "우진": "1티어 하",
    "임수민": "1티어 하",
    "정우욱": "1티어 하",
    "태민": "1티어 하",
    "뒷축": "2티어 최상",
    "까릉": "2티어 최상",
    "도연": "2티어 최상",
    "멍뭉": "2티어 최상",
    "릭스": "2티어 최상",
    "페이": "2티어 최상",
    "시팅": "2티어 최상",
    "모근": "2티어 최상",
    "스타": "2티어 최상",
    "뜬뜬": "2티어 최상",
    "토크": "2티어 상",
    "정현석": "2티어 상",
    "세계": "2티어 상",
    "우이": "2티어 상",
    "하품": "2티어 상",
    "히온": "2티어 상",
    "토이": "2티어 상",
    "그림": "2티어 상",
    "잉누": "2티어 상",
    "찬울": "2티어 상",
    "쪼하": "2티어 중",
    "도링": "2티어 중",
    "애투": "2티어 중",
    "윤창": "2티어 하",
    "피곤": "2티어 하",
    "뚜뚜": "2티어 하",
    "한솔": "2티어 하",
    "캘런": "2티어 하",
    "시우": "2티어 하",
    "밍정뿌": "2티어 하",
    "성현뚱": "2티어 하",
    "알랄": "2티어 하",
    "류연": "2티어 하",
    "욤갓": "2티어 하",
    "밍훈": "2티어 하",
    "시멈": "2티어 하",
    "아지": "2티어 하",
    "배경한": "2티어 하",
    "은찌": "2티어 하",
    "적묘": "2티어 하",
    "대희": "2티어 하",
    "가을": "3티어 최상",
    "경이": "3티어 최상",
    "천호": "3티어 최상",
    "응갑맨": "3티어 최상",
    "으나": "3티어 상",
    "예둥": "3티어 상",
    "나영": "3티어 상",
    "은주": "3티어 상",
    "도리": "3티어 상",
    "러브": "3티어 상",
    "아바": "3티어 상",
    "망고": "3티어 상",
    "혜빈": "3티어 상",
    "율지": "3티어 상",
    "씨원": "3티어 상",
    "아로": "3티어 중",
    "성인": "3티어 중",
    "무디": "3티어 중",
    "주녕": "3티어 중",
    "와니": "3티어 중",
    "랑구": "3티어 하",
    "도유": "3티어 하",
    "원주": "3티어 하",
    "희콩": "3티어 하",
    "현정": "3티어 하",
    "민콩": "3티어 하",
    "재진": "3티어 하",
    "강원": "3티어 하",
    "딸지": "4티어 최상",
    "다콤": "4티어 최상",
    "지원": "4티어 최상",
    "슈임": "4티어 상",
    "준영": "4티어 상",
    "마우": "4티어 상",
    "종수": "4티어 상",
    "리갱": "4티어 상",
    "해원": "4티어 중",
    "감튀": "4티어 중",
    "빈쁘": "4티어 중",
    "봄덕": "4티어 중",
    "쮸정": "4티어 중",
    "포뇨": "씨앗",
    "하녜": "씨앗",
    "가빈": "씨앗",
    "청진": "씨앗",
    "이로로": "씨앗",
    "앙": "씨앗",
}

PENALTIES = [0] + [-n for n in range(1, 11)]
HANDICAPS = list(range(0, 11))


def touch_presence(channel_id: str, client_id: str | None, remove: bool = False):
    cid = (client_id or "").strip()
    if not cid or channel_id not in VALID_CHANNELS:
        return
    now = time.monotonic()
    room_map = CHANNEL_PRESENCE.setdefault(channel_id, {})
    expired = [k for k, ts in room_map.items() if now - ts > PRESENCE_TTL_SECONDS]
    for k in expired:
        room_map.pop(k, None)
    if remove:
        room_map.pop(cid, None)
    else:
        room_map[cid] = now


def get_channel_viewer_count(channel_id: str) -> int:
    now = time.monotonic()
    room_map = CHANNEL_PRESENCE.get(channel_id, {})
    expired = [k for k, ts in room_map.items() if now - ts > PRESENCE_TTL_SECONDS]
    for k in expired:
        room_map.pop(k, None)
    return len(room_map)


def issue_edit_token() -> str:
    msg = f"editor:{EDIT_PIN}".encode("utf-8")
    return hmac.new(TOKEN_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_edit_token(token: str | None) -> bool:
    if not token:
        return False
    expected = issue_edit_token()
    return hmac.compare_digest(token.strip(), expected)


def normalize_nickname(nickname: str) -> str:
    return " ".join((nickname or "").strip().split()).lower()


def is_nickname_taken(db_obj: dict, nickname: str, exclude_client_id: str | None = None) -> bool:
    target = normalize_nickname(nickname)
    if not target:
        return False
    users = db_obj.get("users", {})
    if not isinstance(users, dict):
        return False
    for cid, u in users.items():
        if exclude_client_id and cid == exclude_client_id:
            continue
        if normalize_nickname(u.get("nickname", "")) == target:
            return True
    return False


def is_admin_actor(db_obj: dict, client_id: str | None, token: str | None) -> bool:
    if verify_edit_token(token):
        return True
    if client_id:
        u = db_obj.get("users", {}).get(client_id)
        if isinstance(u, dict) and u.get("role") == "admin":
            return True
    return False


def can_edit_channel(db_obj: dict, channel_id: str, client_id: str | None, token: str | None) -> bool:
    if is_admin_actor(db_obj, client_id, token):
        return True
    if not client_id:
        return False
    u = db_obj.get("users", {}).get(client_id)
    if not isinstance(u, dict) or u.get("role") != "bj":
        return False
    ch_obj = db_obj.get("channels", {}).get(channel_id, {})
    active_bjs = ch_obj.get("active_bjs", [])
    return isinstance(active_bjs, list) and client_id in active_bjs


def require_admin(request: Request, db_obj: dict, client_id: str | None = None):
    token = request.headers.get("X-Edit-Token", "")
    cid = (client_id or request.headers.get("X-Client-Id") or "").strip()
    if not is_admin_actor(db_obj, cid, token):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")


def require_channel_editor(request: Request, db_obj: dict, channel_id: str, client_id: str | None = None):
    token = request.headers.get("X-Edit-Token", "")
    cid = (client_id or request.headers.get("X-Client-Id") or "").strip()
    if not can_edit_channel(db_obj, channel_id, cid, token):
        raise HTTPException(status_code=403, detail="이 채널에 대한 수정 권한이 없습니다.")


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


def default_scoreboard_data():
    return {
        "active_team_mode": "solo",
        "view_style": "table",
        "target_score": 300,
        "big_map_points": 8,
        "small_map_points": 5,
        "rounds_by_mode": {
            mode_key: {}
            for mode_key, _, _ in TEAM_MODES
        },
    }


def normalize_scoreboard_data(raw_sb):
    base = default_scoreboard_data()
    if not isinstance(raw_sb, dict):
        return base

    valid_team_modes = {k for k, _, _ in TEAM_MODES}
    active = str(raw_sb.get("active_team_mode", "solo"))
    if active in valid_team_modes:
        base["active_team_mode"] = active

    view_style = str(raw_sb.get("view_style", "table"))
    if view_style in {"table", "board"}:
        base["view_style"] = view_style

    try:
        target = int(raw_sb.get("target_score", 300))
        base["target_score"] = max(1, min(999999, target))
    except Exception:
        base["target_score"] = 300

    try:
        big_pts = int(raw_sb.get("big_map_points", 8))
        base["big_map_points"] = max(0, min(999, big_pts))
    except Exception:
        base["big_map_points"] = 8

    try:
        small_pts = int(raw_sb.get("small_map_points", 5))
        base["small_map_points"] = max(0, min(999, small_pts))
    except Exception:
        base["small_map_points"] = 5

    raw_rounds = raw_sb.get("rounds_by_mode", {})
    if isinstance(raw_rounds, dict):
        for mode_key in valid_team_modes:
            mode_rounds = raw_rounds.get(mode_key, {})
            if isinstance(mode_rounds, dict):
                base["rounds_by_mode"][mode_key] = mode_rounds
    return base


def default_channel_payload(raw_source: dict | None = None):
    src = raw_source if isinstance(raw_source, dict) else {}
    modes_out = {}
    raw_modes = src.get("modes", {}) if isinstance(src.get("modes"), dict) else {}
    for mode_key, _, _ in TEAM_MODES:
        m = raw_modes.get(mode_key, {})
        if not isinstance(m, dict):
            m = {}
        count = max(2, min(10, int(m.get("team_count", 2))))
        teams = m.get("teams", [])
        if not isinstance(teams, list):
            teams = []
        modes_out[mode_key] = {
            "team_count": count,
            "teams": teams,
        }

    active_bjs = src.get("active_bjs", [])
    if not isinstance(active_bjs, list):
        active_bjs = []

    return {
        "active_bjs": active_bjs,
        "modes": modes_out,
        "tier_board": normalize_tier_board(src.get("tier_board")),
        "scoreboard": normalize_scoreboard_data(src.get("scoreboard")),
    }


def default_db():
    return {
        "users": {},
        "channels": {
            cid: default_channel_payload()
            for cid, _, _ in CHANNELS
        },
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

    if not isinstance(raw, dict):
        return base

    raw_users = raw.get("users", {})
    if isinstance(raw_users, dict):
        for cid, u in raw_users.items():
            if isinstance(u, dict) and str(u.get("nickname", "")).strip():
                role = u.get("role", "user")
                if role not in {"user", "bj", "admin"}:
                    role = "user"
                base["users"][str(cid)] = {
                    "nickname": str(u["nickname"]).strip(),
                    "role": role,
                }

    if "channels" not in raw and ("modes" in raw or "teams" in raw or "team_count" in raw):
        legacy = {}
        if "modes" not in raw and ("teams" in raw or "team_count" in raw):
            legacy["modes"] = {
                "squad": {
                    "team_count": max(2, min(10, int(raw.get("team_count", 2)))),
                    "teams": raw.get("teams", []),
                }
            }
        else:
            legacy["modes"] = raw.get("modes", {})
        legacy["tier_board"] = raw.get("tier_board")
        legacy["scoreboard"] = raw.get("scoreboard")
        base["channels"]["kill1"] = default_channel_payload(legacy)
        return base

    raw_channels = raw.get("channels", {})
    if isinstance(raw_channels, dict):
        for cid, _, _ in CHANNELS:
            base["channels"][cid] = default_channel_payload(raw_channels.get(cid))

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


class RegisterNicknamePayload(BaseModel):
    client_id: str
    nickname: str


class PresenceHeartbeatPayload(BaseModel):
    client_id: str
    channel_id: str
    active: bool = True


class AuthUnlockPayload(BaseModel):
    pin: str
    client_id: str = ""


class AdminRolePayload(BaseModel):
    client_id: str
    role: str
    actor_client_id: str = ""


class AdminRoomBjPayload(BaseModel):
    channel_id: str
    client_id: str
    active: bool
    actor_client_id: str = ""


class AdminDisableAllPayload(BaseModel):
    channel_id: str | None = None
    actor_client_id: str = ""


class ModeStatePayload(BaseModel):
    team_count: int
    teams: list
    client_id: str = ""


class TierBoardPayload(BaseModel):
    tier_board: dict
    client_id: str = ""


class ScoreboardPayload(BaseModel):
    active_team_mode: str = "solo"
    view_style: str = "table"
    target_score: int = 300
    big_map_points: int = 8
    small_map_points: int = 5
    rounds_by_mode: dict = {}
    client_id: str = ""


app = FastAPI(title="PUBG 킬내기 관리 웹")


@app.post("/api/presence")
def presence_heartbeat(payload: PresenceHeartbeatPayload):
    if payload.channel_id not in VALID_CHANNELS:
        raise HTTPException(status_code=400, detail="올바르지 않은 채널입니다.")
    with FILE_LOCK:
        touch_presence(payload.channel_id, payload.client_id, remove=not payload.active)
        counts = {cid: get_channel_viewer_count(cid) for cid, _, _ in CHANNELS}
    return {"ok": True, "viewer_counts": counts}


@app.post("/api/user/register")
def register_nickname(payload: RegisterNicknamePayload):
    cid = (payload.client_id or "").strip()
    clean_nick = " ".join((payload.nickname or "").strip().split())
    if not cid:
        raise HTTPException(status_code=400, detail="클라이언트 ID가 없습니다.")
    if not clean_nick:
        raise HTTPException(status_code=400, detail="닉네임을 입력해 주세요.")

    with FILE_LOCK:
        db_obj = load_db()
        if is_nickname_taken(db_obj, clean_nick, exclude_client_id=cid):
            raise HTTPException(status_code=409, detail="이미 사용 중인 닉네임입니다. 다른 닉네임을 입력해 주세요.")

        existing = db_obj["users"].get(cid)
        role = existing.get("role", "user") if isinstance(existing, dict) else "user"
        if role not in {"user", "bj", "admin"}:
            role = "user"

        db_obj["users"][cid] = {
            "nickname": clean_nick,
            "role": role,
        }
        save_db(db_obj)
        version = STATE_VERSION
        user_obj = db_obj["users"][cid]

    return {"ok": True, "version": version, "user": user_obj}


@app.post("/api/auth/unlock")
def unlock_editor(payload: AuthUnlockPayload):
    if not hmac.compare_digest((payload.pin or "").strip(), EDIT_PIN.strip()):
        raise HTTPException(status_code=401, detail="비밀번호(PIN)가 올바르지 않습니다.")

    cid = (payload.client_id or "").strip()
    with FILE_LOCK:
        db_obj = load_db()
        if cid and cid in db_obj["users"]:
            db_obj["users"][cid]["role"] = "admin"
            for ch in db_obj["channels"].values():
                if cid in ch.get("active_bjs", []):
                    ch["active_bjs"].remove(cid)
            save_db(db_obj)

    return {"ok": True, "edit_token": issue_edit_token()}


@app.get("/api/auth/verify")
def verify_editor(request: Request, client_id: str = ""):
    token = request.headers.get("X-Edit-Token", "")
    cid = (client_id or request.headers.get("X-Client-Id") or "").strip()
    with FILE_LOCK:
        db_obj = load_db()
        admin_ok = is_admin_actor(db_obj, cid, token)
    return {"ok": admin_ok, "is_admin": admin_ok}


@app.get("/api/admin/users")
def admin_get_users(request: Request, client_id: str = ""):
    with FILE_LOCK:
        db_obj = load_db()
        require_admin(request, db_obj, client_id)
        users_list = [
            {"client_id": uid, "nickname": u.get("nickname", ""), "role": u.get("role", "user")}
            for uid, u in db_obj.get("users", {}).items()
        ]
        room_active_map = {
            cid: list(ch.get("active_bjs", []))
            for cid, ch in db_obj.get("channels", {}).items()
        }
    return {"ok": True, "users": users_list, "room_active_map": room_active_map}


@app.post("/api/admin/role")
def admin_set_role(payload: AdminRolePayload, request: Request):
    if payload.role not in {"user", "bj", "admin"}:
        raise HTTPException(status_code=400, detail="올바르지 않은 역할입니다.")
    target_cid = (payload.client_id or "").strip()
    with FILE_LOCK:
        db_obj = load_db()
        require_admin(request, db_obj, payload.actor_client_id)
        if target_cid not in db_obj.get("users", {}):
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

        db_obj["users"][target_cid]["role"] = payload.role
        if payload.role != "bj":
            for ch in db_obj["channels"].values():
                if target_cid in ch.get("active_bjs", []):
                    ch["active_bjs"].remove(target_cid)

        save_db(db_obj)
        version = STATE_VERSION
    return {"ok": True, "version": version}


@app.post("/api/admin/room-bj")
def admin_toggle_room_bj(payload: AdminRoomBjPayload, request: Request):
    if payload.channel_id not in VALID_CHANNELS:
        raise HTTPException(status_code=400, detail="올바르지 않은 채널입니다.")
    target_cid = (payload.client_id or "").strip()
    with FILE_LOCK:
        db_obj = load_db()
        require_admin(request, db_obj, payload.actor_client_id)
        user = db_obj.get("users", {}).get(target_cid)
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        if user.get("role") != "bj":
            raise HTTPException(status_code=400, detail="비제이 역할 사용자만 활성화할 수 있습니다.")

        active_list = db_obj["channels"][payload.channel_id].setdefault("active_bjs", [])
        if payload.active and target_cid not in active_list:
            active_list.append(target_cid)
        elif not payload.active and target_cid in active_list:
            active_list.remove(target_cid)

        save_db(db_obj)
        version = STATE_VERSION
    return {"ok": True, "version": version}


@app.post("/api/admin/disable-all")
def admin_disable_all(payload: AdminDisableAllPayload, request: Request):
    with FILE_LOCK:
        db_obj = load_db()
        require_admin(request, db_obj, payload.actor_client_id)
        if payload.channel_id:
            if payload.channel_id not in VALID_CHANNELS:
                raise HTTPException(status_code=400, detail="올바르지 않은 채널입니다.")
            db_obj["channels"][payload.channel_id]["active_bjs"] = []
        else:
            for ch in db_obj["channels"].values():
                ch["active_bjs"] = []
        save_db(db_obj)
        version = STATE_VERSION
    return {"ok": True, "version": version}


@app.get("/api/state")
def get_state(request: Request, channel: str = "kill1", client_id: str = "", in_lobby: int = 0):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    cid = (client_id or request.headers.get("X-Client-Id") or "").strip()
    token = request.headers.get("X-Edit-Token", "")

    with FILE_LOCK:
        if cid:
            if int(in_lobby or 0) == 1:
                for c_id, _, _ in CHANNELS:
                    touch_presence(c_id, cid, remove=True)
            else:
                touch_presence(ch_id, cid, remove=False)

        db_obj = load_db()
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
        user_obj = db_obj["users"].get(cid)
        admin_flag = is_admin_actor(db_obj, cid, token)
        editable_flag = can_edit_channel(db_obj, ch_id, cid, token)

        channels_meta = []
        for c_id, c_label, c_desc in CHANNELS:
            c_obj = db_obj["channels"][c_id]
            channels_meta.append({
                "id": c_id,
                "label": c_label,
                "desc": c_desc,
                "can_edit": can_edit_channel(db_obj, c_id, cid, token),
                "viewer_count": get_channel_viewer_count(c_id),
                "active_bj_count": len(c_obj.get("active_bjs", [])),
            })

    return {
        "version": version,
        "channel": ch_id,
        "channels_meta": channels_meta,
        "user": user_obj,
        "is_admin": admin_flag,
        "can_edit": editable_flag,
        "modes_meta": [
            {"key": k, "label": label, "max_members": max_m}
            for k, label, max_m in MODES
        ],
        "team_modes_meta": [
            {"key": k, "label": label, "max_members": max_m}
            for k, label, max_m in TEAM_MODES
        ],
        "max_rounds": MAX_ROUNDS,
        "tier_groups": [
            {"group": g, "tiers": sub}
            for g, sub in TIER_GROUPS
        ],
        "tiers": TIERS,
        "tier_board": ch_data["tier_board"],
        "penalties": PENALTIES,
        "handicaps": HANDICAPS,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": ch_data["tier_board"],
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.put("/api/modes/{mode_key}")
def update_mode(mode_key: str, payload: ModeStatePayload, request: Request, channel: str = "kill1"):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    valid_keys = {k for k, _, _ in TEAM_MODES}
    if mode_key not in valid_keys:
        raise HTTPException(status_code=400, detail="지원하지 않는 모드입니다.")

    count = max(2, min(10, int(payload.team_count)))
    with FILE_LOCK:
        db_obj = load_db()
        require_channel_editor(request, db_obj, ch_id, payload.client_id)
        ch_data = db_obj["channels"][ch_id]
        ch_data["modes"][mode_key] = {
            "team_count": count,
            "teams": payload.teams,
        }
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
    return {
        "ok": True,
        "version": version,
        "mode": mode_key,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": ch_data["tier_board"],
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.post("/api/modes/{mode_key}/reset")
def reset_mode(mode_key: str, request: Request, channel: str = "kill1", client_id: str = ""):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    valid_keys = {k for k, _, _ in TEAM_MODES}
    if mode_key not in valid_keys:
        raise HTTPException(status_code=400, detail="지원하지 않는 모드입니다.")

    with FILE_LOCK:
        db_obj = load_db()
        require_channel_editor(request, db_obj, ch_id, client_id)
        ch_data = db_obj["channels"][ch_id]
        ch_data["modes"][mode_key] = default_mode_data()
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
    return {
        "ok": True,
        "version": version,
        "mode": mode_key,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": ch_data["tier_board"],
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.put("/api/tier-board")
def update_tier_board(payload: TierBoardPayload, request: Request, channel: str = "kill1"):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    with FILE_LOCK:
        db_obj = load_db()
        require_channel_editor(request, db_obj, ch_id, payload.client_id)
        ch_data = db_obj["channels"][ch_id]
        ch_data["tier_board"] = normalize_tier_board(payload.tier_board)
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
    return {
        "ok": True,
        "version": version,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": ch_data["tier_board"],
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.post("/api/tier-board/reset")
def reset_tier_board(request: Request, channel: str = "kill1", client_id: str = ""):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    with FILE_LOCK:
        db_obj = load_db()
        require_channel_editor(request, db_obj, ch_id, client_id)
        ch_data = db_obj["channels"][ch_id]
        ch_data["tier_board"] = default_tier_board()
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
    return {
        "ok": True,
        "version": version,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": ch_data["tier_board"],
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.put("/api/scoreboard")
def update_scoreboard(payload: ScoreboardPayload, request: Request, channel: str = "kill1"):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    with FILE_LOCK:
        db_obj = load_db()
        require_channel_editor(request, db_obj, ch_id, payload.client_id)
        ch_data = db_obj["channels"][ch_id]
        ch_data["scoreboard"] = normalize_scoreboard_data({
            "active_team_mode": payload.active_team_mode,
            "view_style": payload.view_style,
            "target_score": payload.target_score,
            "big_map_points": payload.big_map_points,
            "small_map_points": payload.small_map_points,
            "rounds_by_mode": payload.rounds_by_mode,
        })
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
    return {
        "ok": True,
        "version": version,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": ch_data["tier_board"],
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.post("/api/scoreboard/reset")
def reset_scoreboard(request: Request, channel: str = "kill1", client_id: str = ""):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    with FILE_LOCK:
        db_obj = load_db()
        require_channel_editor(request, db_obj, ch_id, client_id)
        ch_data = db_obj["channels"][ch_id]
        sb = normalize_scoreboard_data(ch_data.get("scoreboard"))
        active = sb.get("active_team_mode", "solo")
        sb["rounds_by_mode"][active] = {}
        ch_data["scoreboard"] = sb
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
    return {
        "ok": True,
        "version": version,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": ch_data["tier_board"],
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.get("/api/stream")
async def stream_state(request: Request, channel: str = "kill1", client_id: str = "", in_lobby: int = 0):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    cid = (client_id or request.query_params.get("client_id") or "").strip()
    token = request.headers.get("X-Edit-Token") or request.query_params.get("edit_token") or ""
    lobby_flag = int(in_lobby or 0) == 1

    async def event_generator():
        last_sent_version = -1
        last_ping = time.monotonic()
        while True:
            if await request.is_disconnected():
                if cid:
                    with FILE_LOCK:
                        for c_id, _, _ in CHANNELS:
                            touch_presence(c_id, cid, remove=True)
                break

            with FILE_LOCK:
                if cid:
                    if lobby_flag:
                        for c_id, _, _ in CHANNELS:
                            touch_presence(c_id, cid, remove=True)
                    else:
                        touch_presence(ch_id, cid, remove=False)

                current_version = STATE_VERSION
                if current_version != last_sent_version:
                    db_obj = load_db()
                    ch_data = db_obj["channels"][ch_id]
                    current_payload = {
                        "version": current_version,
                        "channel": ch_id,
                        "user": db_obj["users"].get(cid),
                        "is_admin": is_admin_actor(db_obj, cid, token),
                        "can_edit": can_edit_channel(db_obj, ch_id, cid, token),
                        "data": {
                            "modes": ch_data["modes"],
                            "tier_board": ch_data["tier_board"],
                            "scoreboard": ch_data["scoreboard"],
                        },
                    }
                else:
                    current_payload = None

            if current_payload is not None:
                last_sent_version = current_version
                yield f"data: {json.dumps(current_payload, ensure_ascii=False)}\n\n"
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


HTML_PAGE = r"""<!DOCTYPE html>
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
      max-width: 1420px;
      margin: 0 auto;
      padding: 18px 16px 48px;
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
      gap: 14px;
      flex-wrap: wrap;
    }
    h1 {
      margin: 0;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.3px;
    }
    .channel-pill {
      padding: 4px 10px;
      border-radius: 999px;
      background: #e2e8f0;
      color: #0f172a;
      font-size: 12px;
      font-weight: 800;
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
    .submode-pills {
      display: inline-flex;
      gap: 5px;
      flex-wrap: wrap;
    }
    .pill-btn {
      padding: 5px 11px;
      border: 1px solid #cbd5e1;
      background: #fff;
      color: #334155;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
    }
    .pill-btn.active {
      background: #0f766e;
      color: #fff;
      border-color: #0f766e;
    }
    .target-inline {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 13px;
      font-weight: 700;
      color: #0f172a;
    }
    .target-input {
      width: 68px !important;
      padding: 5px 6px !important;
      font-size: 13px !important;
      font-weight: 700;
      text-align: center;
    }
    .pts-input {
      width: 52px !important;
      padding: 5px 5px !important;
      font-size: 13px !important;
      font-weight: 700;
      text-align: center;
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
    .auth-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    .auth-left {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .auth-right {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .user-nick-tag {
      font-size: 13px;
      font-weight: 800;
      color: #0f172a;
      background: #f1f5f9;
      border: 1px solid #cbd5e1;
      padding: 4px 10px;
      border-radius: 999px;
    }
    .lock-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 999px;
    }
    .lock-badge.locked {
      color: #991b1b;
      background: #fef2f2;
      border: 1px solid #fecaca;
    }
    .lock-badge.unlocked {
      color: #1d4ed8;
      background: #eff6ff;
      border: 1px solid #bfdbfe;
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
    input[type="text"], input[type="password"], input[type="number"], select {
      padding: 6px 8px;
      border: 1px solid #cbd5e1;
      border-radius: 7px;
      font-size: 14px;
      background: #fff;
      color: #0f172a;
    }
    input[type="password"] {
      width: 130px;
    }
    input[type="number"] {
      width: 68px;
    }
    input:disabled, select:disabled, button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
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
    button:hover:not(:disabled) {
      background: #eef2f6;
    }
    button.primary {
      background: #1e293b;
      color: #fff;
      border-color: #1e293b;
    }
    button.success {
      background: #0f766e;
      color: #fff;
      border-color: #0f766e;
    }
    button.danger {
      background: #fff;
      border-color: #fca5a5;
      color: #b91c1c;
    }
    button.danger-solid {
      background: #dc2626;
      border-color: #dc2626;
      color: #fff;
    }

    /* 채널 로비 */
    .lobby-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
      margin-top: 12px;
    }
    .lobby-card {
      background: #fff;
      border: 1px solid #cbd5e1;
      border-radius: 12px;
      padding: 18px;
      cursor: pointer;
      transition: transform 0.12s ease, border-color 0.12s ease;
    }
    .lobby-card:hover {
      transform: translateY(-2px);
      border-color: #1e293b;
    }
    .lobby-card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .lobby-card-title {
      font-size: 18px;
      font-weight: 800;
      color: #0f172a;
    }
    .lobby-card-desc {
      font-size: 13px;
      color: #475569;
      margin-bottom: 12px;
    }

    /* 모달 */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.55);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 200;
      padding: 16px;
    }
    .modal-backdrop.open {
      display: flex;
    }
    .modal-box {
      background: #fff;
      border: 1px solid #cbd5e1;
      border-radius: 12px;
      width: 100%;
      max-width: 640px;
      max-height: 86vh;
      overflow-y: auto;
      padding: 18px 20px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.22);
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid #e2e8f0;
    }
    .modal-title {
      margin: 0;
      font-size: 17px;
      font-weight: 800;
    }
    .admin-toolbar {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      padding: 10px 12px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      margin-bottom: 10px;
    }
    .admin-filter-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }
    .admin-user-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      padding: 9px 4px;
      border-bottom: 1px solid #f1f5f9;
    }
    .error-msg {
      color: #b91c1c;
      font-size: 12px;
      font-weight: 700;
      min-height: 16px;
      margin-top: 6px;
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
    .tier-groups-wrap {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    @media (max-width: 980px) {
      .tier-groups-wrap {
        grid-template-columns: 1fr;
      }
    }
    .tier-group-card {
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .tier-group-banner {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px;
      background: #1e293b;
      color: #fff;
      font-weight: 800;
      font-size: 15px;
    }
    .tier-group-count {
      font-size: 12px;
      font-weight: 700;
      color: #cbd5e1;
    }
    .subtier-cols {
      display: grid;
      gap: 1px;
      background: #e2e8f0;
    }
    .subtier-cols.cols-4 {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    .subtier-cols.cols-1 {
      grid-template-columns: minmax(0, 1fr);
    }
    .subtier-col {
      background: #fff;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-width: 0;
    }
    .subtier-col-header {
      padding: 7px 8px;
      text-align: center;
      font-size: 13px;
      font-weight: 800;
      color: #0f172a;
      background: #f8fafc;
      border-bottom: 1px solid #e2e8f0;
    }
    .subtier-vertical-list {
      padding: 8px;
      display: flex;
      flex-direction: column;
      gap: 5px;
      flex: 1;
      min-height: 92px;
    }
    .vertical-member-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 4px;
      padding: 4px 7px;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      background: #fcfcfd;
      font-size: 12px;
      font-weight: 600;
      color: #1e293b;
    }
    .vertical-member-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .chip-del {
      border: none;
      background: transparent;
      color: #94a3b8;
      padding: 0 2px;
      font-size: 13px;
      line-height: 1;
      cursor: pointer;
    }
    .subtier-add-box {
      padding: 7px;
      border-top: 1px solid #f1f5f9;
      background: #f8fafc;
      display: flex;
      gap: 4px;
    }
    .subtier-add-input {
      flex: 1;
      min-width: 0;
      padding: 4px 6px;
      font-size: 12px;
    }
    .subtier-add-btn {
      padding: 4px 8px;
      font-size: 12px;
    }
    .sb-summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .sb-mini-card {
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 10px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .sb-mini-name {
      font-size: 14px;
      font-weight: 800;
      color: #0f172a;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .sb-mini-score {
      font-size: 14px;
      font-weight: 800;
      color: #0f766e;
      white-space: nowrap;
    }
    .sb-team-card {
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      margin-bottom: 14px;
      overflow: hidden;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .sb-team-top {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 14px;
      background: #f8fafc;
      border-bottom: 1px solid #e2e8f0;
    }
    .sb-team-title {
      font-size: 15px;
      font-weight: 800;
      color: #0f172a;
    }
    .sb-team-totals {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      font-size: 13px;
      font-weight: 700;
      color: #0f766e;
    }
    .sb-table-wrap {
      overflow-x: auto;
      max-height: 540px;
    }
    table.sb-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    table.sb-table th, table.sb-table td {
      border: 1px solid #e2e8f0;
      padding: 5px 6px;
      text-align: center;
      white-space: nowrap;
    }
    table.sb-table thead th {
      position: sticky;
      top: 0;
      background: #1e293b;
      color: #fff;
      z-index: 2;
      font-weight: 700;
    }
    table.sb-table th.round-col, table.sb-table td.round-col {
      position: sticky;
      left: 0;
      background: #f8fafc;
      font-weight: 800;
      color: #334155;
      z-index: 1;
      width: 54px;
    }
    table.sb-table thead th.round-col {
      background: #0f172a;
      color: #fff;
      z-index: 3;
    }
    .kill-input {
      width: 62px;
      padding: 4px 6px;
      font-size: 12px;
      text-align: right;
    }
    .map-chk-group {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }
    .map-chk-label {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      font-size: 11px;
      font-weight: 700;
      color: #0f172a;
      cursor: pointer;
    }
    .map-chk {
      width: 14px;
      height: 14px;
      cursor: pointer;
      margin: 0;
    }
    .death-cell-wrap {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
    }
    .death-chk {
      width: 15px;
      height: 15px;
      cursor: pointer;
    }
    .pen-tag {
      font-size: 11px;
      color: #b91c1c;
      font-weight: 700;
    }
    .round-sum-cell {
      font-weight: 800;
      color: #0f172a;
      background: #f8fafc;
      min-width: 66px;
    }

    .board-grid {
      display: flex;
      justify-content: center;
      align-items: flex-start;
      width: 100%;
    }
    .match-board-card {
      width: 100%;
      max-width: 710px;
      background: #ffffff;
      border: 1.5px solid #222222;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
      overflow: hidden;
    }
    .match-board-header {
      padding: 4px 6px;
      border-bottom: 1.5px solid #222222;
      text-align: center;
      font-size: 11px;
      font-weight: 800;
      color: #111111;
      letter-spacing: -0.2px;
      line-height: 1.25;
      word-break: keep-all;
    }
    .match-board-header.tone-pink { background: #f8cedc; }
    .match-board-header.tone-yellow { background: #f8e4a6; }
    .match-board-header.tone-blue { background: #b8d3f0; }

    .match-board-columns {
      display: grid;
      border-bottom: 1px solid #222222;
    }
    .match-board-col {
      padding: 4px 4px;
      text-align: center;
      min-width: 0;
    }
    .match-board-col + .match-board-col {
      border-left: 1px dashed #444444;
    }
    .match-board-player {
      padding: 1px 2px;
      font-size: 10.5px;
      font-weight: 800;
      color: #111111;
      line-height: 1.3;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .match-board-chicken-row {
      display: grid;
      border-bottom: 1px solid #222222;
    }
    .match-board-chicken-cell {
      padding: 3px 3px;
      text-align: center;
      font-size: 10.5px;
      font-weight: 800;
      color: #111111;
      min-width: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .match-board-chicken-cell + .match-board-chicken-cell {
      border-left: 1px dashed #444444;
    }
    .match-board-chicken-cell.tone-pink { background: #fce7ee; }
    .match-board-chicken-cell.tone-yellow { background: #fdf3d2; }
    .match-board-chicken-cell.tone-blue { background: #e3effb; }

    .match-board-footer {
      height: 11px;
    }
    .match-board-footer.tone-pink { background: #fce7ee; }
    .match-board-footer.tone-yellow { background: #fdf3d2; }
    .match-board-footer.tone-blue { background: #e3effb; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="title-area">
        <h1>PUBG KILL MATCH</h1>
        <span class="channel-pill" id="activeChannelBadge">채널 선택</span>
        <button type="button" id="backLobbyBtn" onclick="openLobbyView()" style="display:none;">채널 선택</button>
        <div class="tabs" id="modeTabs" style="display:none;"></div>
      </div>
      <div class="info-text" id="modeInfo"></div>
    </header>

    <div class="card">
      <div class="auth-row">
        <div class="auth-left" id="authControls"></div>
        <div class="auth-right" id="userAndAdminControls"></div>
      </div>
    </div>

    <div class="card" id="settingsCard" style="display:none;">
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

  <!-- 닉네임 설정/변경 모달 -->
  <div class="modal-backdrop" id="nicknameModal">
    <div class="modal-box" style="max-width:400px;">
      <div class="modal-header">
        <h3 class="modal-title">닉네임 설정</h3>
        <button type="button" id="closeNickModalBtn" onclick="closeNicknameModal()" style="display:none;">닫기</button>
      </div>
      <div class="info-text" style="margin-bottom:10px;">
        중복되지 않는 닉네임을 입력해 주세요. 초기 역할은 일반유저로 등록됩니다.
      </div>
      <input type="text" id="nicknameInput" placeholder="닉네임 입력" style="width:100%;" />
      <div class="error-msg" id="nickErrorMsg"></div>
      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:10px;">
        <button type="button" class="primary" onclick="submitNickname()">확인</button>
      </div>
    </div>
  </div>

  <!-- 관리자 권한 설정 모달 -->
  <div class="modal-backdrop" id="permissionModal">
    <div class="modal-box">
      <div class="modal-header">
        <h3 class="modal-title">권한 설정</h3>
        <button type="button" onclick="closePermissionModal()">닫기</button>
      </div>

      <div class="admin-toolbar">
        <div>
          <label for="adminChannelSelect" style="font-size:13px; font-weight:700;">대상 채널:</label>
          <select id="adminChannelSelect" onchange="renderAdminUserList()">
            <option value="kill1">킬내기 1번방</option>
            <option value="kill2">킬내기 2번방</option>
            <option value="kill3">킬내기 3번방</option>
            <option value="mefun_ck">메펀ck방</option>
          </select>
        </div>
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
          <button type="button" class="danger-solid" onclick="disableAllRoomBjs(true)">이 방 비제이 전체 비활성화</button>
          <button type="button" class="danger-solid" onclick="disableAllRoomBjs(false)">모든 방 전체 비활성화</button>
        </div>
      </div>

      <div class="admin-filter-bar">
        <input type="text" id="adminSearchInput" placeholder="닉네임 검색..." style="flex:1; min-width:160px;" oninput="renderAdminUserList()" />
        <select id="adminRoleFilter" onchange="renderAdminUserList()">
          <option value="all">전체 보기</option>
          <option value="admin">관리자만</option>
          <option value="bj">비제이만</option>
          <option value="user">일반유저만</option>
          <option value="active_in_room">선택방 활성만</option>
        </select>
        <button type="button" onclick="resetAdminFilters()">초기화</button>
      </div>

      <div id="adminUserList"></div>
    </div>
  </div>

  <script>
    const CLIENT_STORAGE_KEY = "pubg_kill_match_client_id";
    const TOKEN_STORAGE_KEY = "pubg_kill_match_edit_token";
    const HEADER_TONES = ["tone-pink", "tone-yellow", "tone-blue"];
    const CHANNEL_LABELS = {
      kill1: "킬내기 1번방",
      kill2: "킬내기 2번방",
      kill3: "킬내기 3번방",
      mefun_ck: "메펀ck방"
    };

    const clientId = localStorage.getItem(CLIENT_STORAGE_KEY) || (() => {
      const id = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36));
      localStorage.setItem(CLIENT_STORAGE_KEY, id);
      return id;
    })();

    let state = null;
    let currentChannel = "kill1";
    let inLobby = true;
    let currentMode = "solo";
    let localVersion = 0;
    let saveTimer = null;
    let isSaving = false;
    let pendingSave = false;
    let eventSource = null;
    let canEdit = false;
    let isAdminUser = false;
    let currentUser = null;
    let editToken = localStorage.getItem(TOKEN_STORAGE_KEY) || "";
    let adminCache = { users: [], room_active_map: {} };
    let presenceTimer = null;

    function authHeaders(extra = {}) {
      const headers = {
        "X-Client-Id": clientId,
        ...extra
      };
      if (editToken) {
        headers["X-Edit-Token"] = editToken;
      }
      return headers;
    }

    function hasAdminAccess() {
      return Boolean(isAdminUser || (currentUser && currentUser.role === "admin") || editToken);
    }

    function sendPresenceHeartbeat(active = true) {
      if (!clientId) return;
      const targetActive = Boolean(active && !inLobby);
      fetch("/api/presence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: clientId,
          channel_id: currentChannel,
          active: targetActive
        }),
        keepalive: true
      }).then(async (res) => {
        if (!res.ok) return;
        const data = await res.json();
        if (data && data.viewer_counts && state && Array.isArray(state.channels_meta)) {
          state.channels_meta.forEach(ch => {
            if (Object.prototype.hasOwnProperty.call(data.viewer_counts, ch.id)) {
              ch.viewer_count = data.viewer_counts[ch.id];
            }
          });
          if (inLobby) {
            renderLobby();
          }
        }
      }).catch(() => {});
    }

    function startPresenceLoop() {
      if (presenceTimer) clearInterval(presenceTimer);
      presenceTimer = setInterval(() => {
        sendPresenceHeartbeat(!inLobby);
      }, 10000);
    }

    function renderAuthBar() {
      const container = document.getElementById("authControls");
      const rightContainer = document.getElementById("userAndAdminControls");

      if (canEdit) {
        container.innerHTML = `
          <span class="lock-badge unlocked">수정 권한 활성 (편집 가능)</span>
          ${editToken ? `<button type="button" onclick="lockEditor()">수정 잠금</button>` : ""}
        `;
      } else {
        container.innerHTML = `
          <span class="lock-badge locked">보기 전용 (수정 잠금)</span>
          <input type="password" id="pinInput" placeholder="관리자 PIN" />
          <button type="button" class="primary" onclick="unlockEditor()">잠금 해제</button>
        `;
        const pinEl = document.getElementById("pinInput");
        if (pinEl) {
          pinEl.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              unlockEditor();
            }
          });
        }
      }

      const roleText = !currentUser
        ? "미등록"
        : (currentUser.role === "admin" ? "관리자" : (currentUser.role === "bj" ? "비제이" : "일반유저"));
      const nickText = currentUser ? `${currentUser.nickname} (${roleText})` : "닉네임 미설정";

      rightContainer.innerHTML = `
        <span class="user-nick-tag">${escapeHtml(nickText)}</span>
        <button type="button" onclick="openNicknameModal(Boolean(currentUser))">닉네임 변경</button>
        ${hasAdminAccess() ? `<button type="button" class="success" onclick="openPermissionModal()">권한 설정</button>` : ""}
      `;
    }

    function openNicknameModal(allowClose) {
      const modal = document.getElementById("nicknameModal");
      const closeBtn = document.getElementById("closeNickModalBtn");
      const input = document.getElementById("nicknameInput");
      const errEl = document.getElementById("nickErrorMsg");
      closeBtn.style.display = allowClose ? "inline-block" : "none";
      errEl.textContent = "";
      input.value = currentUser ? currentUser.nickname : "";
      modal.classList.add("open");
      setTimeout(() => input.focus(), 40);
    }

    function closeNicknameModal() {
      if (!currentUser) return;
      document.getElementById("nicknameModal").classList.remove("open");
    }

    async function submitNickname() {
      const input = document.getElementById("nicknameInput");
      const errEl = document.getElementById("nickErrorMsg");
      const rawNick = (input.value || "").trim();
      if (!rawNick) {
        errEl.textContent = "닉네임을 입력해 주세요.";
        return;
      }
      try {
        const res = await fetch("/api/user/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ client_id: clientId, nickname: rawNick })
        });
        const data = await res.json();
        if (!res.ok) {
          errEl.textContent = data.detail || "이미 사용 중인 닉네임입니다.";
          return;
        }
        currentUser = data.user;
        document.getElementById("nicknameModal").classList.remove("open");
        await reloadChannelState(currentChannel, false);
      } catch (e) {
        errEl.textContent = "닉네임 등록 중 오류가 발생했습니다.";
      }
    }

    async function unlockEditor() {
      const pinEl = document.getElementById("pinInput");
      const pin = pinEl ? pinEl.value : "";
      if (!pin.trim()) {
        alert("비밀번호(PIN)를 입력해 주세요.");
        return;
      }
      try {
        const res = await fetch("/api/auth/unlock", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pin, client_id: clientId })
        });
        if (!res.ok) {
          alert("비밀번호(PIN)가 올바르지 않습니다.");
          return;
        }
        const data = await res.json();
        editToken = data.edit_token || "";
        localStorage.setItem(TOKEN_STORAGE_KEY, editToken);
        await reloadChannelState(currentChannel, false);
      } catch (e) {
        alert("잠금 해제 요청 중 오류가 발생했습니다.");
      }
    }

    async function lockEditor() {
      editToken = "";
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      await reloadChannelState(currentChannel, false);
    }

    async function openPermissionModal() {
      if (!hasAdminAccess()) return;
      const sel = document.getElementById("adminChannelSelect");
