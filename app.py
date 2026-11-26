import asyncio
import hashlib
import hmac
import json
import os
import sys
import threading
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel


def resolve_default_data_file() -> str:
    env_path = (os.environ.get("DATA_FILE") or "").strip()
    if env_path:
        return os.path.abspath(env_path)
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "pubg_kill_match_data.json")


DATA_FILE = resolve_default_data_file()
EDIT_PIN = os.environ.get("EDIT_PIN", "tnals1004")
TOKEN_SECRET = os.environ.get("TOKEN_SECRET", f"pubg-kill-match-{EDIT_PIN}")

FILE_LOCK = threading.Lock()
STATE_VERSION = int(time.time() * 1000)
PRESENCE_TTL_SECONDS = 25.0


def bump_state_version() -> int:
    global STATE_VERSION
    now_ms = int(time.time() * 1000)
    STATE_VERSION = max(STATE_VERSION + 1, now_ms)
    return STATE_VERSION


# channel_id -> { client_id: last_seen_monotonic }
CHANNEL_PRESENCE: dict[str, dict[str, float]] = {}

CHANNELS = [
    ("kill1", "킬내기 1번방", "킬내기 매치 #1"),
    ("kill2", "킬내기 2번방", "킬내기 매치 #2"),
    ("kill3", "킬내기 3번방", "킬내기 매치 #3"),
    ("mefun_ck", "메펀CK방", "메펀 CK 전용"),
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
    "씬봉": "1티어 하",
    "오숍": "1티어 하",
    "주누": "1티어 하",
    "우진": "1티어 하",
    "수민": "1티어 하",
    "정욱": "1티어 하",
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
    "준형": "3티어 중",
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


def is_logged_in(request: Request) -> bool:
    token = request.headers.get("X-Edit-Token", "")
    return verify_edit_token(token)


def require_full_edit(request: Request):
    if not is_logged_in(request):
        raise HTTPException(status_code=403, detail="로그인이 필요한 기능입니다.")


def default_tier_board():
    board = {tier: [] for tier in TIERS}
    for player_name, tier in INITIAL_PLAYER_TIER_MAP.items():
        if tier in board and player_name not in board[tier]:
            board[tier].append(player_name)
    return board


def normalize_tier_board(raw_board, is_initialized: bool = False):
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

    if has_any or is_initialized:
        return board
    return default_tier_board()


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

    return {
        "modes": modes_out,
        "scoreboard": normalize_scoreboard_data(src.get("scoreboard")),
    }


def default_db():
    return {
        "tier_board_initialized": False,
        "tier_board": default_tier_board(),
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

    tb_init = bool(raw.get("tier_board_initialized", False))
    if isinstance(raw.get("tier_board"), dict):
        base["tier_board"] = normalize_tier_board(raw.get("tier_board"), is_initialized=tb_init)
        base["tier_board_initialized"] = tb_init or any(len(v) > 0 for v in base["tier_board"].values())
    else:
        migrated_board = None
        if isinstance(raw.get("channels"), dict):
            for cid, _, _ in CHANNELS:
                ch_raw = raw["channels"].get(cid)
                if isinstance(ch_raw, dict) and isinstance(ch_raw.get("tier_board"), dict):
                    candidate = normalize_tier_board(ch_raw.get("tier_board"), is_initialized=True)
                    if any(len(v) > 0 for v in candidate.values()):
                        migrated_board = candidate
                        break
        if migrated_board is not None:
            base["tier_board"] = migrated_board
            base["tier_board_initialized"] = True
        else:
            base["tier_board"] = default_tier_board()
            base["tier_board_initialized"] = False

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
        legacy["scoreboard"] = raw.get("scoreboard")
        base["channels"]["kill1"] = default_channel_payload(legacy)
        return base

    raw_channels = raw.get("channels", {})
    if isinstance(raw_channels, dict):
        for cid, _, _ in CHANNELS:
            base["channels"][cid] = default_channel_payload(raw_channels.get(cid))

    return base


def save_db(data):
    parent_dir = os.path.dirname(os.path.abspath(DATA_FILE))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    tmp_file = f"{DATA_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, DATA_FILE)
    bump_state_version()


class PresenceHeartbeatPayload(BaseModel):
    client_id: str
    channel_id: str
    active: bool = True


class AuthUnlockPayload(BaseModel):
    pin: str


class ModeStatePayload(BaseModel):
    team_count: int
    teams: list


class TierBoardPayload(BaseModel):
    tier_board: dict


class ScoreboardPayload(BaseModel):
    active_team_mode: str = "solo"
    view_style: str = "table"
    target_score: int = 300
    big_map_points: int = 8
    small_map_points: int = 5
    rounds_by_mode: dict = {}


app = FastAPI(title="PUBG 킬내기 관리 웹")


@app.post("/api/presence")
def presence_heartbeat(payload: PresenceHeartbeatPayload):
    if payload.channel_id not in VALID_CHANNELS:
        raise HTTPException(status_code=400, detail="올바르지 않은 채널입니다.")
    with FILE_LOCK:
        touch_presence(payload.channel_id, payload.client_id, remove=not payload.active)
        counts = {cid: get_channel_viewer_count(cid) for cid, _, _ in CHANNELS}
    return {"ok": True, "viewer_counts": counts}


@app.post("/api/auth/unlock")
def unlock_editor(payload: AuthUnlockPayload):
    if not hmac.compare_digest((payload.pin or "").strip(), EDIT_PIN.strip()):
        raise HTTPException(status_code=401, detail="비밀번호(PIN)가 올바르지 않습니다.")
    return {"ok": True, "edit_token": issue_edit_token()}


@app.get("/api/auth/verify")
def verify_editor(request: Request):
    logged_in = is_logged_in(request)
    return {"ok": logged_in, "logged_in": logged_in}


@app.get("/api/state")
def get_state(request: Request, channel: str = "kill1", client_id: str = "", in_lobby: int = 0):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    cid = (client_id or request.headers.get("X-Client-Id") or "").strip()
    logged_in = is_logged_in(request)

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
        shared_tier_board = db_obj["tier_board"]

        channels_meta = []
        for c_id, c_label, c_desc in CHANNELS:
            channels_meta.append({
                "id": c_id,
                "label": c_label,
                "desc": c_desc,
                "full_edit": logged_in,
                "scoreboard_edit": True,
                "viewer_count": get_channel_viewer_count(c_id),
            })

    return {
        "version": version,
        "channel": ch_id,
        "channels_meta": channels_meta,
        "logged_in": logged_in,
        "full_edit": logged_in,
        "scoreboard_edit": True,
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
        "tier_board": shared_tier_board,
        "penalties": PENALTIES,
        "handicaps": HANDICAPS,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": shared_tier_board,
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.put("/api/modes/{mode_key}")
def update_mode(mode_key: str, payload: ModeStatePayload, request: Request, channel: str = "kill1"):
    require_full_edit(request)
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    valid_keys = {k for k, _, _ in TEAM_MODES}
    if mode_key not in valid_keys:
        raise HTTPException(status_code=400, detail="지원하지 않는 모드입니다.")

    count = max(2, min(10, int(payload.team_count)))
    with FILE_LOCK:
        db_obj = load_db()
        ch_data = db_obj["channels"][ch_id]
        ch_data["modes"][mode_key] = {
            "team_count": count,
            "teams": payload.teams,
        }
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
        shared_tier_board = db_obj["tier_board"]
    return {
        "ok": True,
        "version": version,
        "mode": mode_key,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": shared_tier_board,
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.post("/api/modes/{mode_key}/reset")
def reset_mode(mode_key: str, request: Request, channel: str = "kill1"):
    require_full_edit(request)
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    valid_keys = {k for k, _, _ in TEAM_MODES}
    if mode_key not in valid_keys:
        raise HTTPException(status_code=400, detail="지원하지 않는 모드입니다.")

    with FILE_LOCK:
        db_obj = load_db()
        ch_data = db_obj["channels"][ch_id]
        ch_data["modes"][mode_key] = default_mode_data()
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
        shared_tier_board = db_obj["tier_board"]
    return {
        "ok": True,
        "version": version,
        "mode": mode_key,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": shared_tier_board,
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.put("/api/tier-board")
def update_tier_board(payload: TierBoardPayload, request: Request, channel: str = "kill1"):
    require_full_edit(request)
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    with FILE_LOCK:
        db_obj = load_db()
        db_obj["tier_board_initialized"] = True
        db_obj["tier_board"] = normalize_tier_board(payload.tier_board, is_initialized=True)
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
        shared_tier_board = db_obj["tier_board"]
    return {
        "ok": True,
        "version": version,
        "tier_board": shared_tier_board,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": shared_tier_board,
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.post("/api/tier-board/reset")
def reset_tier_board(request: Request, channel: str = "kill1"):
    require_full_edit(request)
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    with FILE_LOCK:
        db_obj = load_db()
        db_obj["tier_board_initialized"] = True
        db_obj["tier_board"] = default_tier_board()
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
        shared_tier_board = db_obj["tier_board"]
    return {
        "ok": True,
        "version": version,
        "tier_board": shared_tier_board,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": shared_tier_board,
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.put("/api/scoreboard")
def update_scoreboard(payload: ScoreboardPayload, request: Request, channel: str = "kill1"):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    with FILE_LOCK:
        db_obj = load_db()
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
        shared_tier_board = db_obj["tier_board"]
    return {
        "ok": True,
        "version": version,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": shared_tier_board,
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.post("/api/scoreboard/reset")
def reset_scoreboard(request: Request, channel: str = "kill1"):
    require_full_edit(request)
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    with FILE_LOCK:
        db_obj = load_db()
        ch_data = db_obj["channels"][ch_id]
        sb = normalize_scoreboard_data(ch_data.get("scoreboard"))
        active = sb.get("active_team_mode", "solo")
        sb["rounds_by_mode"][active] = {}
        ch_data["scoreboard"] = sb
        save_db(db_obj)
        version = STATE_VERSION
        ch_data = db_obj["channels"][ch_id]
        shared_tier_board = db_obj["tier_board"]
    return {
        "ok": True,
        "version": version,
        "data": {
            "modes": ch_data["modes"],
            "tier_board": shared_tier_board,
            "scoreboard": ch_data["scoreboard"],
        },
    }


@app.get("/api/stream")
async def stream_state(request: Request, channel: str = "kill1", client_id: str = "", in_lobby: int = 0):
    ch_id = channel if channel in VALID_CHANNELS else "kill1"
    cid = (client_id or request.query_params.get("client_id") or "").strip()
    token = request.headers.get("X-Edit-Token") or request.query_params.get("edit_token") or ""
    logged_in = verify_edit_token(token)
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
                    shared_tier_board = db_obj["tier_board"]
                    current_payload = {
                        "version": current_version,
                        "channel": ch_id,
                        "logged_in": logged_in,
                        "full_edit": logged_in,
                        "scoreboard_edit": True,
                        "tier_board": shared_tier_board,
                        "data": {
                            "modes": ch_data["modes"],
                            "tier_board": shared_tier_board,
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

            await asyncio.sleep(0.3)

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
    button.danger {
      background: #fff;
      border-color: #fca5a5;
      color: #b91c1c;
    }

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

    /* 전광판 보기: 2팀이든 3팀 이상이든 컴팩트한 동일 규격 크기로 축소 */
    .board-grid {
      display: flex;
      justify-content: center;
      align-items: flex-start;
      width: 100%;
    }
    .match-board-card {
      width: 100%;
      max-width: 390px;
      background: #ffffff;
      border: 1.5px solid #222222;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
      overflow: hidden;
    }
    .match-board-card.many-teams {
      max-width: 480px;
    }
    .match-board-header {
      padding: 5px 6px;
      border-bottom: 1.5px solid #222222;
      text-align: center;
      font-size: 13.5px;
      font-weight: 800;
      color: #111111;
      letter-spacing: -0.25px;
      line-height: 1.28;
      word-break: keep-all;
    }
    .match-board-card.many-teams .match-board-header {
      font-size: 12px;
      padding: 4px 5px;
    }
    .match-board-header.tone-blue { background: #b8d3f0; }
    .match-board-header.tone-pink { background: #f8cedc; }
    .match-board-header.tone-purple { background: #cbc0ea; }
    .match-board-header.tone-orange { background: #f8d3a6; }
    .match-board-header.tone-yellow { background: #f8e4a6; }

    .match-board-columns {
      display: grid;
      border-bottom: 1px solid #222222;
    }
    .match-board-col {
      padding: 4px 3px;
      text-align: center;
      min-width: 0;
    }
    .match-board-col + .match-board-col {
      border-left: 1px dashed #444444;
    }
    .match-board-player {
      padding: 1px 1px;
      font-size: 13px;
      font-weight: 800;
      color: #111111;
      line-height: 1.32;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .match-board-card.many-teams .match-board-player {
      font-size: 11px;
      line-height: 1.28;
    }
    .match-board-chicken-row {
      display: grid;
      border-bottom: 1px solid #222222;
    }
    .match-board-chicken-cell {
      padding: 3px 3px;
      text-align: center;
      font-size: 12.5px;
      font-weight: 800;
      color: #111111;
      min-width: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .match-board-card.many-teams .match-board-chicken-cell {
      font-size: 11px;
      padding: 3px 2px;
    }
    .match-board-chicken-cell + .match-board-chicken-cell {
      border-left: 1px dashed #444444;
    }
    .match-board-chicken-cell.tone-blue { background: #e3effb; }
    .match-board-chicken-cell.tone-pink { background: #fce7ee; }
    .match-board-chicken-cell.tone-purple { background: #ebe5f9; }
    .match-board-chicken-cell.tone-orange { background: #fdf0df; }
    .match-board-chicken-cell.tone-yellow { background: #fdf3d2; }

    .match-board-footer {
      height: 8px;
    }
    .match-board-footer.tone-blue { background: #e3effb; }
    .match-board-footer.tone-pink { background: #fce7ee; }
    .match-board-footer.tone-purple { background: #ebe5f9; }
    .match-board-footer.tone-orange { background: #fdf0df; }
    .match-board-footer.tone-yellow { background: #fdf3d2; }

    /* 메펀CK방 전광판: 2팀이든 3팀 이상이든 컴팩트한 동일 크기로 통일 */
    .mefun-board-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      max-width: 500px;
      margin: 0 auto;
    }
    @media (max-width: 540px) {
      .mefun-board-grid {
        grid-template-columns: 1fr;
        max-width: 320px;
      }
    }
    .mefun-team-card {
      background: #ffffff;
      border: 1.5px solid #222222;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
      overflow: hidden;
    }
    .mefun-team-header {
      padding: 5px 6px;
      border-bottom: 1.5px solid #222222;
      text-align: center;
      font-size: 15px;
      font-weight: 800;
      color: #111111;
      letter-spacing: -0.3px;
    }
    .mefun-team-header.tone-blue { background: #b4d1f0; }
    .mefun-team-header.tone-pink { background: #f7cad8; }
    .mefun-team-header.tone-purple { background: #c5b8e8; }
    .mefun-team-header.tone-orange { background: #f7cfa0; }

    .mefun-members-box {
      padding: 5px 6px;
      background: #ffffff;
      border-bottom: 1.5px solid #222222;
    }
    .mefun-member-line {
      font-size: 14px;
      font-weight: 800;
      color: #111111;
      line-height: 1.42;
      text-align: center;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .mefun-bottom-bar {
      display: grid;
      grid-template-columns: 1fr 1fr;
    }
    .mefun-bottom-cell {
      padding: 4px 5px;
      text-align: center;
      font-size: 13.5px;
      font-weight: 800;
      color: #111111;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .mefun-bottom-cell + .mefun-bottom-cell {
      border-left: 1.5px solid #222222;
    }
    .mefun-bottom-cell.tone-blue { background: #e3effb; }
    .mefun-bottom-cell.tone-pink { background: #fce7ee; }
    .mefun-bottom-cell.tone-purple { background: #ebe5f9; }
    .mefun-bottom-cell.tone-orange { background: #fdf0df; }
    .mefun-bottom-pct {
      background: #d8dce2 !important;
    }
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
        <div class="info-text">비로그인 상태: 모든 채널 솔로·듀오·스쿼드 점수판 편집 가능 / 로그인 상태: 전체 편집 가능</div>
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

  <script>
    const CLIENT_STORAGE_KEY = "pubg_kill_match_client_id";
    const TOKEN_STORAGE_KEY = "pubg_kill_match_edit_token";
    const VIEW_STYLE_STORAGE_KEY = "pubg_kill_match_sb_view_style";
    const HEADER_TONES = ["tone-blue", "tone-pink", "tone-purple", "tone-orange"];
    const CHANNEL_LABELS = {
      kill1: "킬내기 1번방",
      kill2: "킬내기 2번방",
      kill3: "킬내기 3번방",
      mefun_ck: "메펀CK방"
    };

    function getOrCreateClientId() {
      try {
        const existing = localStorage.getItem(CLIENT_STORAGE_KEY);
        if (existing && existing.trim()) return existing.trim();
        const id = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36));
        localStorage.setItem(CLIENT_STORAGE_KEY, id);
        return id;
      } catch (e) {
        return "temp_" + Date.now().toString(36);
      }
    }

    function getSavedViewStyle() {
      try {
        const v = (localStorage.getItem(VIEW_STYLE_STORAGE_KEY) || "").trim();
        return (v === "board" || v === "table") ? v : "";
      } catch (e) {
        return "";
      }
    }

    function setSavedViewStyle(v) {
      try {
        if (v === "board" || v === "table") {
          localStorage.setItem(VIEW_STYLE_STORAGE_KEY, v);
        }
      } catch (e) {}
    }

    const clientId = getOrCreateClientId();

    let state = null;
    let currentChannel = "kill1";
    let inLobby = true;
    let currentMode = "solo";
    let localVersion = 0;
    let saveTimer = null;
    let isSaving = false;
    let pendingSave = false;
    let eventSource = null;
    let fullEdit = false;
    let localViewStyle = getSavedViewStyle();
    let editToken = (() => {
      try { return localStorage.getItem(TOKEN_STORAGE_KEY) || ""; } catch (e) { return ""; }
    })();
    let presenceTimer = null;
    let syncPollTimer = null;

    function canEditCurrentView() {
      if (fullEdit) return true;
      return currentMode === "scoreboard";
    }

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

    function flushPendingOnUnload() {
      if (!state || inLobby) return;
      if (!canEditCurrentView()) return;
      const chParam = `channel=${encodeURIComponent(currentChannel)}`;
      let url = "";
      let bodyObj = null;

      if (currentMode === "tiers" && fullEdit) {
        url = `/api/tier-board?${chParam}`;
        bodyObj = { tier_board: getTierBoard() };
      } else if (currentMode === "scoreboard") {
        const sb = getScoreboardData();
        url = `/api/scoreboard?${chParam}`;
        bodyObj = {
          active_team_mode: sb.active_team_mode,
          view_style: sb.view_style,
          target_score: sb.target_score,
          big_map_points: sb.big_map_points,
          small_map_points: sb.small_map_points,
          rounds_by_mode: sb.rounds_by_mode
        };
      } else if (["solo", "duo", "squad"].includes(currentMode) && fullEdit) {
        url = `/api/modes/${currentMode}?${chParam}`;
        bodyObj = collectCurrentTeamUI();
      }

      if (url && bodyObj) {
        try {
          fetch(url, {
            method: "PUT",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify(bodyObj),
            keepalive: true
          }).catch(() => {});
        } catch (e) {}
      }
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

    function startSyncBackupLoop() {
      if (syncPollTimer) clearInterval(syncPollTimer);
      syncPollTimer = setInterval(async () => {
        if (!state || saveTimer || isSaving || pendingSave) return;
        try {
          const lobbyParam = inLobby ? 1 : 0;
          const q = `/api/state?channel=${encodeURIComponent(currentChannel)}&client_id=${encodeURIComponent(clientId)}&in_lobby=${lobbyParam}`;
          const res = await fetch(q, { headers: authHeaders() });
          if (!res.ok) return;
          const latest = await res.json();
          if (typeof latest.version === "number" && latest.version > localVersion) {
            applyRemoteState(latest, true);
          }
        } catch (e) {}
      }, 2000);
    }

    function applyRemoteState(msg, preserveFocus = true) {
      if (!msg || typeof msg.version !== "number") return;
      if (msg.version <= localVersion) return;
      if (saveTimer || isSaving || pendingSave) return;

      localVersion = msg.version;
      if (Object.prototype.hasOwnProperty.call(msg, "full_edit")) {
        fullEdit = Boolean(msg.full_edit);
      } else if (Object.prototype.hasOwnProperty.call(msg, "logged_in")) {
        fullEdit = Boolean(msg.logged_in);
      }
      if (Array.isArray(msg.channels_meta) && state) {
        state.channels_meta = msg.channels_meta;
      }

      const sharedBoard = msg.tier_board || (msg.data && msg.data.tier_board) || null;
      if (state) {
        if (!state.data) state.data = {};
        if (msg.data) {
          if (msg.data.modes) state.data.modes = msg.data.modes;
          if (msg.data.scoreboard) {
            const incomingSb = msg.data.scoreboard;
            const preferredStyle = localViewStyle || (state.data.scoreboard && state.data.scoreboard.view_style) || incomingSb.view_style || "table";
            state.data.scoreboard = {
              ...incomingSb,
              view_style: preferredStyle
            };
          }
        }
        if (sharedBoard) {
          state.tier_board = sharedBoard;
          state.data.tier_board = sharedBoard;
        }
      }

      renderAuthBar();
      if (!inLobby) {
        renderSettingsBar();
      }
      renderMainContent(preserveFocus);
      const statusEl = document.getElementById("saveStatus");
      if (statusEl) statusEl.textContent = "실시간 동기화됨";
    }

    function renderAuthBar() {
      const container = document.getElementById("authControls");
      if (fullEdit) {
        container.innerHTML = `
          <span class="lock-badge unlocked">로그인됨 (전체 수정 가능)</span>
          <button type="button" onclick="lockEditor()">로그아웃</button>
        `;
      } else {
        container.innerHTML = `
          <span class="lock-badge locked">미로그인 (점수판만 수정 가능)</span>
          <input type="password" id="pinInput" placeholder="비밀번호(PIN)" />
          <button type="button" class="primary" onclick="unlockEditor()">로그인</button>
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
          body: JSON.stringify({ pin })
        });
        if (!res.ok) {
          alert("비밀번호(PIN)가 올바르지 않습니다.");
          return;
        }
        const data = await res.json();
        editToken = data.edit_token || "";
        try { localStorage.setItem(TOKEN_STORAGE_KEY, editToken); } catch (e) {}
        await reloadChannelState(currentChannel, false);
        connectRealtimeStream();
      } catch (e) {
        alert("로그인 요청 중 오류가 발생했습니다.");
      }
    }

    async function lockEditor() {
      editToken = "";
      try { localStorage.removeItem(TOKEN_STORAGE_KEY); } catch (e) {}
      await reloadChannelState(currentChannel, false);
      connectRealtimeStream();
    }

    async function openLobbyView() {
      if (canEditCurrentView() && saveTimer) {
        clearTimeout(saveTimer);
        saveTimer = null;
        await flushAutoSave();
      }
      inLobby = true;
      syncShellVisibility();
      sendPresenceHeartbeat(false);
      await reloadChannelState(currentChannel, false);
      connectRealtimeStream();
    }

    async function selectChannel(chId) {
      inLobby = false;
      currentChannel = chId;
      syncShellVisibility();
      sendPresenceHeartbeat(true);
      await reloadChannelState(chId, false);
      connectRealtimeStream();
    }

    function syncShellVisibility() {
      const badge = document.getElementById("activeChannelBadge");
      const backBtn = document.getElementById("backLobbyBtn");
      const tabsEl = document.getElementById("modeTabs");
      const settingsCard = document.getElementById("settingsCard");

      if (inLobby) {
        badge.textContent = "채널 선택";
        backBtn.style.display = "none";
        tabsEl.style.display = "none";
        settingsCard.style.display = "none";
        document.getElementById("modeInfo").textContent = "입장할 채널을 선택해 주세요.";
      } else {
        badge.textContent = CHANNEL_LABELS[currentChannel] || currentChannel;
        backBtn.style.display = "inline-block";
        tabsEl.style.display = "flex";
        settingsCard.style.display = "block";
      }
    }

    function renderLobby() {
      const container = document.getElementById("mainContent");
      const chList = (state && Array.isArray(state.channels_meta) && state.channels_meta.length)
        ? state.channels_meta
        : Object.entries(CHANNEL_LABELS).map(([id, label]) => ({
            id,
            label,
            desc: "",
            full_edit: fullEdit,
            viewer_count: 0
          }));

      container.innerHTML = `
        <div class="card">
          <h2 style="margin:0 0 4px 0; font-size:18px;">채널 선택</h2>
          <div class="info-text">원하는 방을 선택하면 이동합니다. (모든 채널 솔로·듀오·스쿼드 점수판 편집 가능)</div>
          <div class="lobby-grid">
            ${chList.map(ch => `
              <div class="lobby-card" onclick="selectChannel('${ch.id}')">
                <div class="lobby-card-top">
                  <span class="lobby-card-title">${escapeHtml(ch.label)}</span>
                  <span class="lock-badge ${fullEdit ? "unlocked" : "locked"}">${fullEdit ? "전체 수정" : "점수판 수정"}</span>
                </div>
                <div class="lobby-card-desc">${escapeHtml(ch.desc || "")}</div>
                <div class="info-text">입장 인원: ${ch.viewer_count || 0}명</div>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }

    function getModeMeta(modeKey = currentMode) {
      return state.modes_meta.find(m => m.key === modeKey) || { key: modeKey, label: modeKey, max_members: 4 };
    }

    function getTeamModeMeta(modeKey) {
      return (state.team_modes_meta || []).find(m => m.key === modeKey) || { key: modeKey, label: modeKey, max_members: 4 };
    }

    function getModeData(modeKey = currentMode) {
      if (!state.data.modes[modeKey]) {
        state.data.modes[modeKey] = { team_count: 2, teams: [] };
      }
      return state.data.modes[modeKey];
    }

    function getScoreboardData() {
      if (!state.data.scoreboard || typeof state.data.scoreboard !== "object") {
        state.data.scoreboard = {
          active_team_mode: "solo",
          view_style: localViewStyle || "table",
          target_score: 300,
          big_map_points: 8,
          small_map_points: 5,
          rounds_by_mode: { solo: {}, duo: {}, squad: {} }
        };
      }
      if (!state.data.scoreboard.rounds_by_mode || typeof state.data.scoreboard.rounds_by_mode !== "object") {
        state.data.scoreboard.rounds_by_mode = { solo: {}, duo: {}, squad: {} };
      }
      ["solo", "duo", "squad"].forEach(k => {
        if (!state.data.scoreboard.rounds_by_mode[k] || typeof state.data.scoreboard.rounds_by_mode[k] !== "object") {
          state.data.scoreboard.rounds_by_mode[k] = {};
        }
      });
      if (!["solo", "duo", "squad"].includes(state.data.scoreboard.active_team_mode)) {
        state.data.scoreboard.active_team_mode = "solo";
      }
      if (localViewStyle === "board" || localViewStyle === "table") {
        state.data.scoreboard.view_style = localViewStyle;
      } else if (!["table", "board"].includes(state.data.scoreboard.view_style)) {
        state.data.scoreboard.view_style = "table";
      }
      const parsedTarget = parseInt(state.data.scoreboard.target_score, 10);
      state.data.scoreboard.target_score = Number.isNaN(parsedTarget)
        ? 300
        : Math.max(1, Math.min(999999, parsedTarget));

      const parsedBig = parseInt(state.data.scoreboard.big_map_points, 10);
      state.data.scoreboard.big_map_points = Number.isNaN(parsedBig)
        ? 8
        : Math.max(0, Math.min(999, parsedBig));

      const parsedSmall = parseInt(state.data.scoreboard.small_map_points, 10);
      state.data.scoreboard.small_map_points = Number.isNaN(parsedSmall)
        ? 5
        : Math.max(0, Math.min(999, parsedSmall));

      return state.data.scoreboard;
    }

    function getTierBoard() {
      if (!state.tier_board && state.data && state.data.tier_board) {
        state.tier_board = state.data.tier_board;
      }
      if (!state.tier_board || typeof state.tier_board !== "object") {
        state.tier_board = {};
      }
      state.tiers.forEach(t => {
        if (!Array.isArray(state.tier_board[t])) {
          state.tier_board[t] = [];
        }
      });
      if (state.data) {
        state.data.tier_board = state.tier_board;
      }
      return state.tier_board;
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

      return { team_count: teamCount, teams };
    }

    function scheduleAutoSave(delay = 180) {
      if (!canEditCurrentView()) return;
      document.getElementById("saveStatus").textContent = "자동 저장 중...";
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        saveTimer = null;
        flushAutoSave();
      }, delay);
    }

    async function flushAutoSave() {
      if (!canEditCurrentView()) return;
      if (isSaving) {
        pendingSave = true;
        return;
      }
      isSaving = true;

      try {
        const chParam = `channel=${encodeURIComponent(currentChannel)}`;
        if (currentMode === "tiers") {
          if (!fullEdit) return;
          const payload = { tier_board: getTierBoard() };
          const res = await fetch(`/api/tier-board?${chParam}`, {
            method: "PUT",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify(payload)
          });
          if (res.status === 403) {
            await reloadChannelState(currentChannel, true);
            return;
          }
          if (!res.ok) {
            document.getElementById("saveStatus").textContent = "저장 오류 (재시도 대기)";
            return;
          }
          const result = await res.json();
          localVersion = Math.max(localVersion, result.version || 0);
          const updatedBoard = result.tier_board || (result.data && result.data.tier_board);
          if (updatedBoard) {
            state.tier_board = updatedBoard;
            if (state.data) state.data.tier_board = updatedBoard;
          }
          document.getElementById("saveStatus").textContent = "실시간 저장 완료";
        } else if (currentMode === "scoreboard") {
          const sb = getScoreboardData();
          const payload = {
            active_team_mode: sb.active_team_mode,
            view_style: sb.view_style,
            target_score: sb.target_score,
            big_map_points: sb.big_map_points,
            small_map_points: sb.small_map_points,
            rounds_by_mode: sb.rounds_by_mode
          };
          const res = await fetch(`/api/scoreboard?${chParam}`, {
            method: "PUT",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify(payload)
          });
          if (!res.ok) {
            document.getElementById("saveStatus").textContent = "저장 오류 (재시도 대기)";
            return;
          }
          const result = await res.json();
          localVersion = Math.max(localVersion, result.version || 0);
          if (!saveTimer && !pendingSave) {
            state.data.scoreboard.target_score = result.data.scoreboard.target_score;
            state.data.scoreboard.big_map_points = result.data.scoreboard.big_map_points;
            state.data.scoreboard.small_map_points = result.data.scoreboard.small_map_points;
            state.data.scoreboard.active_team_mode = result.data.scoreboard.active_team_mode;
            if (!localViewStyle) {
              state.data.scoreboard.view_style = result.data.scoreboard.view_style;
            }
          }
          document.getElementById("saveStatus").textContent = "실시간 저장 완료";
        } else {
          if (!fullEdit) return;
          const modeToSave = currentMode;
          const payload = collectCurrentTeamUI();
          state.data.modes[modeToSave] = {
            team_count: payload.team_count,
            teams: payload.teams
          };
          const res = await fetch(`/api/modes/${modeToSave}?${chParam}`, {
            method: "PUT",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify(payload)
          });
          if (res.status === 403) {
            await reloadChannelState(currentChannel, true);
            return;
          }
          if (!res.ok) {
            document.getElementById("saveStatus").textContent = "저장 오류 (재시도 대기)";
            return;
          }
          const result = await res.json();
          localVersion = Math.max(localVersion, result.version || 0);
          if (!saveTimer && !pendingSave) {
            state.data.modes[modeToSave] = result.data.modes[modeToSave];
          }
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
      if (!target || target.disabled) return;
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
      resetBtn.disabled = !fullEdit;
      const chLabel = CHANNEL_LABELS[currentChannel] || currentChannel;

      if (currentMode === "tiers") {
        const board = getTierBoard();
        const totalCount = state.tiers.reduce((acc, t) => acc + (board[t] ? board[t].length : 0), 0);
        document.getElementById("modeInfo").textContent =
          `[ 공용 · 티어표] ${fullEdit ? "수정 가능" : "로그인 필요"}`;
        leftEl.innerHTML = `
          <strong> 공용 · 등록 인원</strong>
          <span class="info-text">${totalCount}명</span>
        `;
        resetBtn.textContent = "기본 티어표 복원";
      } else if (currentMode === "scoreboard") {
        const sb = getScoreboardData();
        const activeMode = sb.active_team_mode;
        const viewStyle = sb.view_style;
        const targetScore = sb.target_score;
        const bigPts = sb.big_map_points;
        const smallPts = sb.small_map_points;
        const tMeta = getTeamModeMeta(activeMode);
        const mData = getModeData(activeMode);
        const tCount = Math.max(2, Math.min(10, parseInt(mData.team_count || 2, 10)));
        const sbEditable = canEditCurrentView();

        document.getElementById("modeInfo").textContent =
          `[${chLabel} · 점수판 · ${tMeta.label}] 목표 ${targetScore}점 · 큰맵 +${bigPts} / 작은맵 +${smallPts}`;
        leftEl.innerHTML = `
          <strong>모드</strong>
          <div class="submode-pills" id="sbModePills"></div>
          <strong>보기 전환</strong>
          <div class="submode-pills" id="sbViewPills"></div>
          <label class="target-inline" for="targetScoreInput">
            <span>목표</span>
            <input
              type="number"
              id="targetScoreInput"
              class="target-input"
              data-field-key="sb-target-score"
              min="1"
              max="999999"
              value="${escapeHtml(targetScore)}"
              ${sbEditable ? "" : "disabled"}
            />
          </label>
          <label class="target-inline" for="bigMapPtsInput">
            <span>큰맵점수</span>
            <input
              type="number"
              id="bigMapPtsInput"
              class="pts-input"
              data-field-key="sb-big-pts"
              min="0"
              max="999"
              value="${escapeHtml(bigPts)}"
              ${sbEditable ? "" : "disabled"}
            />
          </label>
          <label class="target-inline" for="smallMapPtsInput">
            <span>작은맵점수</span>
            <input
              type="number"
              id="smallMapPtsInput"
              class="pts-input"
              data-field-key="sb-small-pts"
              min="0"
              max="999"
              value="${escapeHtml(smallPts)}"
              ${sbEditable ? "" : "disabled"}
            />
          </label>
          <span class="info-text">${tCount}팀 · 최대 30라운드</span>
        `;
        resetBtn.textContent = "점수판 초기화";

        const pillsWrap = document.getElementById("sbModePills");
        (state.team_modes_meta || []).forEach(tm => {
          const pBtn = document.createElement("button");
          pBtn.type = "button";
          pBtn.className = "pill-btn" + (tm.key === activeMode ? " active" : "");
          pBtn.textContent = tm.label;
          pBtn.onclick = () => switchScoreboardTeamMode(tm.key);
          pillsWrap.appendChild(pBtn);
        });

        const viewWrap = document.getElementById("sbViewPills");
        [
          { key: "table", label: "점수표" },
          { key: "board", label: "전광판 보기" }
        ].forEach(v => {
          const vBtn = document.createElement("button");
          vBtn.type = "button";
          vBtn.className = "pill-btn" + (v.key === viewStyle ? " active" : "");
          vBtn.textContent = v.label;
          vBtn.onclick = () => switchScoreboardViewStyle(v.key);
          viewWrap.appendChild(vBtn);
        });

        const targetInput = document.getElementById("targetScoreInput");
        if (targetInput && sbEditable) {
          targetInput.addEventListener("input", () => {
            const currentSb = getScoreboardData();
            const val = parseInt(targetInput.value, 10);
            currentSb.target_score = Number.isNaN(val) ? 300 : Math.max(1, Math.min(999999, val));
            if (currentSb.view_style === "board") {
              renderScoreboard(true);
            }
            scheduleAutoSave();
          });
          targetInput.addEventListener("change", () => {
            const currentSb = getScoreboardData();
            const val = parseInt(targetInput.value, 10);
            const cleanVal = Number.isNaN(val) ? 300 : Math.max(1, Math.min(999999, val));
            currentSb.target_score = cleanVal;
            targetInput.value = String(cleanVal);
            if (currentSb.view_style === "board") {
              renderScoreboard(true);
            }
            scheduleAutoSave(50);
          });
        }

        const bigInput = document.getElementById("bigMapPtsInput");
        if (bigInput && sbEditable) {
          bigInput.addEventListener("input", () => {
            const currentSb = getScoreboardData();
            const val = parseInt(bigInput.value, 10);
            currentSb.big_map_points = Number.isNaN(val) ? 8 : Math.max(0, Math.min(999, val));
            recomputeAllScoreboardTeamsLive();
            scheduleAutoSave();
          });
          bigInput.addEventListener("change", () => {
            const currentSb = getScoreboardData();
            const val = parseInt(bigInput.value, 10);
            const cleanVal = Number.isNaN(val) ? 8 : Math.max(0, Math.min(999, val));
            currentSb.big_map_points = cleanVal;
            bigInput.value = String(cleanVal);
            recomputeAllScoreboardTeamsLive();
            scheduleAutoSave(50);
          });
        }

        const smallInput = document.getElementById("smallMapPtsInput");
        if (smallInput && sbEditable) {
          smallInput.addEventListener("input", () => {
            const currentSb = getScoreboardData();
            const val = parseInt(smallInput.value, 10);
            currentSb.small_map_points = Number.isNaN(val) ? 5 : Math.max(0, Math.min(999, val));
            recomputeAllScoreboardTeamsLive();
            scheduleAutoSave();
          });
          smallInput.addEventListener("change", () => {
            const currentSb = getScoreboardData();
            const val = parseInt(smallInput.value, 10);
            const cleanVal = Number.isNaN(val) ? 5 : Math.max(0, Math.min(999, val));
            currentSb.small_map_points = cleanVal;
            smallInput.value = String(cleanVal);
            recomputeAllScoreboardTeamsLive();
            scheduleAutoSave(50);
          });
        }
      } else {
        const meta = getModeMeta(currentMode);
        const modeData = getModeData(currentMode);
        const teamCount = Math.max(2, Math.min(10, parseInt(modeData.team_count || 2, 10)));

        document.getElementById("modeInfo").textContent =
          `[${chLabel} · ${meta.label}] 최대 10팀 / 팀당 최대 ${meta.max_members}명 (${fullEdit ? "수정 가능" : "로그인 필요"})`;
        leftEl.innerHTML = `
          <label for="teamCountInput"><strong>참가 팀 수</strong></label>
          <input type="number" id="teamCountInput" min="2" max="10" value="${teamCount}" ${fullEdit ? "" : "disabled"} />
          <span class="info-text">${meta.label} 기준 · 팀당 최대 ${meta.max_members}명</span>
        `;
        resetBtn.textContent = "초기화";

        const countInput = document.getElementById("teamCountInput");
        if (countInput && fullEdit) {
          countInput.addEventListener("change", () => {
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
    }

    async function switchScoreboardTeamMode(nextTeamMode) {
      const sb = getScoreboardData();
      if (sb.active_team_mode === nextTeamMode) return;
      if (canEditCurrentView() && saveTimer) {
        clearTimeout(saveTimer);
        saveTimer = null;
        await flushAutoSave();
      }
      getScoreboardData().active_team_mode = nextTeamMode;
      renderSettingsBar();
      renderScoreboard(false);
      if (canEditCurrentView()) {
        scheduleAutoSave(50);
      }
    }

    async function switchScoreboardViewStyle(nextStyle) {
      const sb = getScoreboardData();
      if (sb.view_style === nextStyle && localViewStyle === nextStyle) return;
      localViewStyle = nextStyle;
      setSavedViewStyle(nextStyle);
      getScoreboardData().view_style = nextStyle;
      renderSettingsBar();
      renderScoreboard(false);
    }

    function penaltyDeductionAmount(rawPenalty) {
      const n = parseInt(rawPenalty, 10);
      if (Number.isNaN(n)) return 0;
      return Math.abs(n);
    }

    function getRoundEntry(modeRoundsObj, tIdx, roundNum, maxMembers) {
      const tKey = `t${tIdx}`;
      if (!modeRoundsObj[tKey] || typeof modeRoundsObj[tKey] !== "object") {
        modeRoundsObj[tKey] = {};
      }
      const rKey = `r${roundNum}`;
      if (!modeRoundsObj[tKey][rKey] || typeof modeRoundsObj[tKey][rKey] !== "object") {
        modeRoundsObj[tKey][rKey] = {
          kills: [],
          deaths: [],
          big_map: false,
          small_map: false
        };
      }
      const entry = modeRoundsObj[tKey][rKey];
      if (!Array.isArray(entry.kills)) entry.kills = [];
      if (!Array.isArray(entry.deaths)) entry.deaths = [];
      if (typeof entry.big_map !== "boolean") entry.big_map = Boolean(entry.big_map);
      if (typeof entry.small_map !== "boolean") entry.small_map = Boolean(entry.small_map);
      for (let i = 0; i < maxMembers; i++) {
        if (entry.kills[i] === undefined) entry.kills[i] = "";
        if (entry.deaths[i] === undefined) entry.deaths[i] = false;
      }
      return entry;
    }

    function computeTeamScoreboardTotals(teamObj, tIdx, modeRoundsObj, maxRounds, maxMembers, sb = null) {
      const scoreCfg = sb || getScoreboardData();
      const bigPts = parseInt(scoreCfg.big_map_points, 10);
      const smallPts = parseInt(scoreCfg.small_map_points, 10);
      const bigVal = Number.isNaN(bigPts) ? 8 : bigPts;
      const smallVal = Number.isNaN(smallPts) ? 5 : smallPts;

      const members = teamObj.members || [];
      let totalHandicap = 0;
      const memberHandicaps = [];

      for (let s = 0; s < maxMembers; s++) {
        const m = members[s] || {};
        const hVal = parseFloat(m.handicap);
        const hNum = Number.isNaN(hVal) ? 0 : hVal;
        memberHandicaps.push(hNum);
        totalHandicap += hNum;
      }

      let totalKills = 0;
      let totalDeductions = 0;
      let totalChickenPoints = 0;
      let totalChickens = 0;
      let bigMapCount = 0;
      let smallMapCount = 0;
      let roundsNetSum = 0;

      const memberStats = [];
      for (let s = 0; s < maxMembers; s++) {
        memberStats.push({
          kills: 0,
          deaths: 0,
          deductionTotal: 0,
          handicap: memberHandicaps[s],
          net: memberHandicaps[s]
        });
      }
      const roundTotals = [];

      for (let r = 1; r <= maxRounds; r++) {
        const entry = getRoundEntry(modeRoundsObj, tIdx, r, maxMembers);
        let rKills = 0;
        let rDed = 0;

        for (let s = 0; s < maxMembers; s++) {
          const m = members[s] || {};
          const kVal = parseFloat(entry.kills[s]);
          const killsNum = Number.isNaN(kVal) ? 0 : kVal;
          const isDead = Boolean(entry.deaths[s]);
          const dedAmt = isDead ? penaltyDeductionAmount(m.penalty) : 0;

          rKills += killsNum;
          rDed += dedAmt;

          memberStats[s].kills += killsNum;
          if (isDead) {
            memberStats[s].deaths += 1;
            memberStats[s].deductionTotal += dedAmt;
          }
          memberStats[s].net += (killsNum - dedAmt);
        }

        const isBig = Boolean(entry.big_map);
        const isSmall = Boolean(entry.small_map);
        const rChickenPts = (isBig ? bigVal : 0) + (isSmall ? smallVal : 0);
        const rChickenCnt = (isBig ? 1 : 0) + (isSmall ? 1 : 0);

        if (isBig) bigMapCount += 1;
        if (isSmall) smallMapCount += 1;

        const rNet = rKills - rDed + rChickenPts;
        totalKills += rKills;
        totalDeductions += rDed;
        totalChickenPoints += rChickenPts;
        totalChickens += rChickenCnt;
        roundsNetSum += rNet;

        roundTotals.push({
          round: r,
          kills: rKills,
          deduction: rDed,
          chickenPoints: rChickenPts,
          net: rNet
        });
      }

      const totalNet = roundsNetSum + totalHandicap;
      const sumAllDeaths = memberStats.reduce((acc, ms) => acc + ms.deaths, 0);

      return {
        totalKills,
        totalDeaths: sumAllDeaths,
        totalDeductions,
        totalHandicap,
        totalChickenPoints,
        totalChickens,
        bigMapCount,
        smallMapCount,
        totalNet,
        memberStats,
        roundTotals
      };
    }

    function formatNumberDisplay(val) {
      if (Number.isInteger(val)) return String(val);
      return String(Math.round(val * 100) / 100);
    }

    function formatAchievementPct(score, target) {
      const safeTarget = target > 0 ? target : 300;
      const pct = (score / safeTarget) * 100;
      const rounded = Math.round(pct * 100) / 100;
      return `${rounded.toFixed(2)}%`;
    }

    function renderScoreboard(preserveFocus = false) {
      const sb = getScoreboardData();
      if (sb.view_style === "board") {
        if (currentChannel === "mefun_ck") {
          renderMefunCkBoardView(preserveFocus);
        } else {
          renderScoreboardBoardView(preserveFocus);
        }
      } else {
        renderScoreboardTableView(preserveFocus);
      }
    }

    function renderMefunCkBoardView(preserveFocus = false) {
      const focusSnap = preserveFocus ? getFocusSnapshot() : null;
      const sb = getScoreboardData();
      const activeMode = sb.active_team_mode;
      const targetScore = sb.target_score || 300;
      const tMeta = getTeamModeMeta(activeMode);
      const mData = getModeData(activeMode);
      const savedTeams = Array.isArray(mData.teams) ? mData.teams : [];
      const configuredCount = Math.max(2, Math.min(10, parseInt(mData.team_count || 2, 10)));
      const teamCount = Math.max(configuredCount, savedTeams.length);
      const maxRounds = state.max_rounds || 30;
      const maxMembers = tMeta.max_members || 4;
      const modeRoundsObj = sb.rounds_by_mode[activeMode];

      const container = document.getElementById("mainContent");
      container.innerHTML = "";

      const grid = document.createElement("div");
      grid.className = "mefun-board-grid";

      for (let tIdx = 0; tIdx < teamCount; tIdx++) {
        const tSaved = savedTeams[tIdx] || {};
        const teamName = (tSaved.name || "").trim() || `TEAM ${tIdx + 1}`;
        const members = Array.isArray(tSaved.members) ? tSaved.members : [];
        const totals = computeTeamScoreboardTotals(tSaved, tIdx, modeRoundsObj, maxRounds, maxMembers, sb);
        const toneClass = HEADER_TONES[tIdx % HEADER_TONES.length];
        const pctText = formatAchievementPct(totals.totalNet, targetScore);

        const memberLines = [];
        for (let s = 0; s < maxMembers; s++) {
          const m = members[s] || {};
          const mName = (m.name || "").trim();
          const ms = totals.memberStats[s] || { kills: 0, deaths: 0, deductionTotal: 0, handicap: 0, net: 0 };
          const hasAnyActivity = mName || ms.kills !== 0 || ms.deductionTotal !== 0 || ms.handicap !== 0 || ms.net !== 0;
          if (!hasAnyActivity && s > 0 && activeMode !== "solo") continue;

          const displayName = mName || `${s + 1}번`;
          const killsWithHandicap = ms.kills + ms.handicap;
          const lineText = `${displayName} ${formatNumberDisplay(ms.net)} [${formatNumberDisplay(killsWithHandicap)} -${formatNumberDisplay(ms.deductionTotal)}]`;
          memberLines.push(`<div class="mefun-member-line" title="${escapeHtml(lineText)}">${escapeHtml(lineText)}</div>`);
        }

        const card = document.createElement("div");
        card.className = "mefun-team-card";
        card.innerHTML = `
          <div class="mefun-team-header ${toneClass}">${escapeHtml(teamName)} ${formatNumberDisplay(totals.totalNet)} 점</div>
          <div class="mefun-members-box">
            ${memberLines.join("") || `<div class="mefun-member-line">-</div>`}
          </div>
          <div class="mefun-bottom-bar">
            <div class="mefun-bottom-cell ${toneClass}">🍗 : ${formatNumberDisplay(totals.totalChickenPoints)}</div>
            <div class="mefun-bottom-cell mefun-bottom-pct">${escapeHtml(pctText)}</div>
          </div>
        `;
        grid.appendChild(card);
      }

      container.appendChild(grid);

      if (preserveFocus && canEditCurrentView()) {
        restoreFocusSnapshot(focusSnap);
      }
    }

    function renderScoreboardBoardView(preserveFocus = false) {
      const focusSnap = preserveFocus ? getFocusSnapshot() : null;
      const sb = getScoreboardData();
      const activeMode = sb.active_team_mode;
      const targetScore = sb.target_score || 300;
      const tMeta = getTeamModeMeta(activeMode);
      const mData = getModeData(activeMode);
      const savedTeams = Array.isArray(mData.teams) ? mData.teams : [];
      const configuredCount = Math.max(2, Math.min(10, parseInt(mData.team_count || 2, 10)));
      const teamCount = Math.max(configuredCount, savedTeams.length);
      const maxRounds = state.max_rounds || 30;
      const maxMembers = tMeta.max_members || 4;
      const modeRoundsObj = sb.rounds_by_mode[activeMode];

      const container = document.getElementById("mainContent");
      container.innerHTML = "";

      const teamSummaries = [];
      for (let tIdx = 0; tIdx < teamCount; tIdx++) {
        const tSaved = savedTeams[tIdx] || {};
        const teamName = (tSaved.name || "").trim() || `TEAM ${tIdx + 1}`;
        const members = Array.isArray(tSaved.members) ? tSaved.members : [];
        const totals = computeTeamScoreboardTotals(tSaved, tIdx, modeRoundsObj, maxRounds, maxMembers, sb);

        const colPlayers = [];
        for (let s = 0; s < maxMembers; s++) {
          const m = members[s] || {};
          const mName = (m.name || "").trim() || `${s + 1}번`;
          const ms = totals.memberStats[s] || { kills: 0, deaths: 0, deductionTotal: 0, handicap: 0, net: 0 };
          const killsWithHandicap = ms.kills + ms.handicap;
          colPlayers.push({
            label: `${mName} ${formatNumberDisplay(ms.net)} (${formatNumberDisplay(killsWithHandicap)}-${formatNumberDisplay(ms.deductionTotal)})`,
          });
        }

        teamSummaries.push({
          idx: tIdx,
          name: teamName,
          netScore: totals.totalNet,
          totalKills: totals.totalKills + totals.totalHandicap,
          chickenPoints: totals.totalChickenPoints,
          achievementPct: formatAchievementPct(totals.totalNet, targetScore),
          colPlayers
        });
      }

      const grid = document.createElement("div");
      grid.className = "board-grid";

      const toneClass = HEADER_TONES[0];
      const headerParts = teamSummaries.map(
        t => `${escapeHtml(t.name)} ${formatNumberDisplay(t.netScore)}`
      );
      const headerText = `[ ${targetScore} ] ${headerParts.join(" : ")}`;

      const boardCard = document.createElement("div");
      boardCard.className = "match-board-card" + (teamSummaries.length >= 3 ? " many-teams" : "");

      const headerDiv = document.createElement("div");
      headerDiv.className = `match-board-header ${toneClass}`;
      headerDiv.textContent = headerText;
      boardCard.appendChild(headerDiv);

      const colsDiv = document.createElement("div");
      colsDiv.className = "match-board-columns";
      colsDiv.style.gridTemplateColumns = `repeat(${teamSummaries.length}, minmax(0, 1fr))`;

      teamSummaries.forEach(t => {
        const colDiv = document.createElement("div");
        colDiv.className = "match-board-col";
        colDiv.innerHTML = t.colPlayers
          .map(p => `<div class="match-board-player" title="${escapeHtml(p.label)}">${escapeHtml(p.label)}</div>`)
          .join("");
        colsDiv.appendChild(colDiv);
      });
      boardCard.appendChild(colsDiv);

      const chickenRow = document.createElement("div");
      chickenRow.className = "match-board-chicken-row";
      chickenRow.style.gridTemplateColumns = `repeat(${teamSummaries.length}, minmax(0, 1fr))`;

      teamSummaries.forEach(t => {
        const cCell = document.createElement("div");
        cCell.className = `match-board-chicken-cell ${toneClass}`;
        const cellLabel = `🍗 : [ ${formatNumberDisplay(t.chickenPoints)} ] (${t.achievementPct})`;
        cCell.title = cellLabel;
        cCell.textContent = cellLabel;
        chickenRow.appendChild(cCell);
      });
      boardCard.appendChild(chickenRow);

      const footerDiv = document.createElement("div");
      footerDiv.className = `match-board-footer ${toneClass}`;
      boardCard.appendChild(footerDiv);

      grid.appendChild(boardCard);
      container.appendChild(grid);

      if (preserveFocus && canEditCurrentView()) {
        restoreFocusSnapshot(focusSnap);
      }
    }

    function renderScoreboardTableView(preserveFocus = false) {
      const focusSnap = preserveFocus ? getFocusSnapshot() : null;
      const sb = getScoreboardData();
      const activeMode = sb.active_team_mode;
      const tMeta = getTeamModeMeta(activeMode);
      const mData = getModeData(activeMode);
      const savedTeams = Array.isArray(mData.teams) ? mData.teams : [];
      const configuredCount = Math.max(2, Math.min(10, parseInt(mData.team_count || 2, 10)));
      const teamCount = Math.max(configuredCount, savedTeams.length);
      const maxRounds = state.max_rounds || 30;
      const maxMembers = tMeta.max_members || 4;
      const modeRoundsObj = sb.rounds_by_mode[activeMode];
      const sbEditable = canEditCurrentView();
      const disAttr = sbEditable ? "" : "disabled";

      const container = document.getElementById("mainContent");
      container.innerHTML = "";

      const summaryGrid = document.createElement("div");
      summaryGrid.className = "sb-summary-grid";
      summaryGrid.id = "sbSummaryGrid";

      for (let tIdx = 0; tIdx < teamCount; tIdx++) {
        const tSaved = savedTeams[tIdx] || {};
        const teamName = (tSaved.name || "").trim() || `TEAM ${tIdx + 1}`;
        const totals = computeTeamScoreboardTotals(tSaved, tIdx, modeRoundsObj, maxRounds, maxMembers, sb);

        const mini = document.createElement("div");
        mini.className = "sb-mini-card";
        mini.dataset.summaryTeamIdx = String(tIdx);
        mini.innerHTML = `
          <span class="sb-mini-name">${escapeHtml(teamName)}</span>
          <span class="sb-mini-score" id="sbMiniScore-${tIdx}">${formatNumberDisplay(totals.totalNet)}점 · 🍗+${formatNumberDisplay(totals.totalChickenPoints)}</span>
        `;
        summaryGrid.appendChild(mini);
      }
      container.appendChild(summaryGrid);

      for (let tIdx = 0; tIdx < teamCount; tIdx++) {
        const tSaved = savedTeams[tIdx] || {};
        const teamName = (tSaved.name || "").trim() || `TEAM ${tIdx + 1}`;
        const members = Array.isArray(tSaved.members) ? tSaved.members : [];
        const totals = computeTeamScoreboardTotals(tSaved, tIdx, modeRoundsObj, maxRounds, maxMembers, sb);

        const card = document.createElement("div");
        card.className = "sb-team-card";

        const topBar = document.createElement("div");
        topBar.className = "sb-team-top";
        topBar.innerHTML = `
          <span class="sb-team-title">TEAM ${tIdx + 1} · ${escapeHtml(teamName)}</span>
          <div class="sb-team-totals" id="sbTeamTotals-${tIdx}">
            <span>총점: ${formatNumberDisplay(totals.totalNet)}</span>
            <span>킬핸디: +${formatNumberDisplay(totals.totalHandicap)}</span>
            <span>킬 합계: ${formatNumberDisplay(totals.totalKills)}</span>
            <span>감점 차감: -${formatNumberDisplay(totals.totalDeductions)}</span>
            <span>🍗 치킨점수: +${formatNumberDisplay(totals.totalChickenPoints)} (큰${totals.bigMapCount}/작${totals.smallMapCount})</span>
          </div>
        `;
        card.appendChild(topBar);

        const tableWrap = document.createElement("div");
        tableWrap.className = "sb-table-wrap";

        let headerHtml = `<thead><tr><th class="round-col">R</th>`;
        for (let s = 0; s < maxMembers; s++) {
          const m = members[s] || {};
          const mLabel = (m.name || "").trim() || `${s + 1}번`;
          const dedAmt = penaltyDeductionAmount(m.penalty);
          const hAmt = parseFloat(m.handicap) || 0;
          headerHtml += `
            <th>${escapeHtml(mLabel)} 킬<br><span style="font-size:10px; font-weight:500; color:#99f6e4;">(핸디 +${formatNumberDisplay(hAmt)})</span></th>
            <th>${escapeHtml(mLabel)} 데스<br><span style="font-size:10px; font-weight:500; color:#fca5a5;">(-${dedAmt})</span></th>
          `;
        }
        headerHtml += `<th>팀 치킨(큰맵/작은맵)</th><th>라운드 합</th></tr></thead>`;

        let bodyHtml = `<tbody>`;
        for (let r = 1; r <= maxRounds; r++) {
          const entry = getRoundEntry(modeRoundsObj, tIdx, r, maxMembers);
          const rInfo = totals.roundTotals[r - 1];
          bodyHtml += `<tr><td class="round-col">${r}R</td>`;

          for (let s = 0; s < maxMembers; s++) {
            const m = members[s] || {};
            const dedAmt = penaltyDeductionAmount(m.penalty);
            const kFieldKey = `sb-${currentChannel}-${activeMode}-t${tIdx}-r${r}-s${s}-kill`;
            const dFieldKey = `sb-${currentChannel}-${activeMode}-t${tIdx}-r${r}-s${s}-death`;

            const rawKill = (focusSnap && focusSnap.fieldKey === kFieldKey)
              ? focusSnap.value
              : (entry.kills[s] !== undefined && entry.kills[s] !== "" ? entry.kills[s] : "");
            const isDead = Boolean(entry.deaths[s]);

            bodyHtml += `
              <td>
                <input
                  type="number"
                  step="any"
                  class="kill-input"
                  data-field-key="${kFieldKey}"
                  data-sb-t="${tIdx}"
                  data-sb-r="${r}"
                  data-sb-s="${s}"
                  value="${escapeHtml(rawKill)}"
                  placeholder="0"
                  ${disAttr}
                />
              </td>
              <td>
                <div class="death-cell-wrap">
                  <input
                    type="checkbox"
                    class="death-chk"
                    data-field-key="${dFieldKey}"
                    data-sb-t="${tIdx}"
                    data-sb-r="${r}"
                    data-sb-s="${s}"
                    ${isDead ? "checked" : ""}
                    ${disAttr}
                  />
                  <span class="pen-tag">${isDead ? `-${dedAmt}` : ""}</span>
                </div>
              </td>
            `;
          }

          const bigFieldKey = `sb-${currentChannel}-${activeMode}-t${tIdx}-r${r}-bigmap`;
          const smallFieldKey = `sb-${currentChannel}-${activeMode}-t${tIdx}-r${r}-smallmap`;
          const isBigChecked = Boolean(entry.big_map);
          const isSmallChecked = Boolean(entry.small_map);

          bodyHtml += `
            <td>
              <div class="map-chk-group">
                <label class="map-chk-label">
                  <input
                    type="checkbox"
                    class="map-chk big-map-chk"
                    data-field-key="${bigFieldKey}"
                    data-sb-t="${tIdx}"
                    data-sb-r="${r}"
                    ${isBigChecked ? "checked" : ""}
                    ${disAttr}
                  />
                  <span>큰맵</span>
                </label>
                <label class="map-chk-label">
                  <input
                    type="checkbox"
                    class="map-chk small-map-chk"
                    data-field-key="${smallFieldKey}"
                    data-sb-t="${tIdx}"
                    data-sb-r="${r}"
                    ${isSmallChecked ? "checked" : ""}
                    ${disAttr}
                  />
                  <span>작은맵</span>
                </label>
              </div>
            </td>
            <td class="round-sum-cell" id="sbRoundSum-${tIdx}-r${r}">${formatNumberDisplay(rInfo.net)}</td>
          </tr>`;
        }
        bodyHtml += `</tbody>`;

        tableWrap.innerHTML = `<table class="sb-table">${headerHtml}${bodyHtml}</table>`;
        card.appendChild(tableWrap);
        container.appendChild(card);

        if (sbEditable) {
          tableWrap.querySelectorAll(".kill-input").forEach(inp => {
            inp.addEventListener("input", () => {
              const latestSb = getScoreboardData();
              const latestRounds = latestSb.rounds_by_mode[activeMode];
              const latestTeam = (getModeData(activeMode).teams || [])[parseInt(inp.dataset.sbT, 10)] || tSaved;
              const ti = parseInt(inp.dataset.sbT, 10);
              const rn = parseInt(inp.dataset.sbR, 10);
              const si = parseInt(inp.dataset.sbS, 10);
              const ent = getRoundEntry(latestRounds, ti, rn, maxMembers);
              ent.kills[si] = inp.value;
              refreshScoreboardTeamTotals(ti, latestTeam, latestRounds, maxRounds, maxMembers, latestSb);
              scheduleAutoSave();
            });
          });

          tableWrap.querySelectorAll(".death-chk").forEach(chk => {
            chk.addEventListener("change", () => {
              const latestSb = getScoreboardData();
              const latestRounds = latestSb.rounds_by_mode[activeMode];
              const latestTeam = (getModeData(activeMode).teams || [])[parseInt(chk.dataset.sbT, 10)] || tSaved;
              const ti = parseInt(chk.dataset.sbT, 10);
              const rn = parseInt(chk.dataset.sbR, 10);
              const si = parseInt(chk.dataset.sbS, 10);
              const ent = getRoundEntry(latestRounds, ti, rn, maxMembers);
              ent.deaths[si] = chk.checked;

              const m = (latestTeam.members || [])[si] || {};
              const dedAmt = penaltyDeductionAmount(m.penalty);
              const tagEl = chk.parentElement ? chk.parentElement.querySelector(".pen-tag") : null;
              if (tagEl) {
                tagEl.textContent = chk.checked ? `-${dedAmt}` : "";
              }
              refreshScoreboardTeamTotals(ti, latestTeam, latestRounds, maxRounds, maxMembers, latestSb);
              scheduleAutoSave(50);
            });
          });

          tableWrap.querySelectorAll(".big-map-chk").forEach(bchk => {
            bchk.addEventListener("change", () => {
              const latestSb = getScoreboardData();
              const latestRounds = latestSb.rounds_by_mode[activeMode];
              const latestTeam = (getModeData(activeMode).teams || [])[parseInt(bchk.dataset.sbT, 10)] || tSaved;
              const ti = parseInt(bchk.dataset.sbT, 10);
              const rn = parseInt(bchk.dataset.sbR, 10);
              const ent = getRoundEntry(latestRounds, ti, rn, maxMembers);
              ent.big_map = bchk.checked;
              refreshScoreboardTeamTotals(ti, latestTeam, latestRounds, maxRounds, maxMembers, latestSb);
              scheduleAutoSave(50);
            });
          });

          tableWrap.querySelectorAll(".small-map-chk").forEach(schk => {
            schk.addEventListener("change", () => {
              const latestSb = getScoreboardData();
              const latestRounds = latestSb.rounds_by_mode[activeMode];
              const latestTeam = (getModeData(activeMode).teams || [])[parseInt(schk.dataset.sbT, 10)] || tSaved;
              const ti = parseInt(schk.dataset.sbT, 10);
              const rn = parseInt(schk.dataset.sbR, 10);
              const ent = getRoundEntry(latestRounds, ti, rn, maxMembers);
              ent.small_map = schk.checked;
              refreshScoreboardTeamTotals(ti, latestTeam, latestRounds, maxRounds, maxMembers, latestSb);
              scheduleAutoSave(50);
            });
          });
        }
      }

      if (preserveFocus && canEditCurrentView()) {
        restoreFocusSnapshot(focusSnap);
      }
    }

    function recomputeAllScoreboardTeamsLive() {
      const sb = getScoreboardData();
      const activeMode = sb.active_team_mode;
      const tMeta = getTeamModeMeta(activeMode);
      const mData = getModeData(activeMode);
      const savedTeams = Array.isArray(mData.teams) ? mData.teams : [];
      const configuredCount = Math.max(2, Math.min(10, parseInt(mData.team_count || 2, 10)));
      const teamCount = Math.max(configuredCount, savedTeams.length);
      const maxRounds = state.max_rounds || 30;
      const maxMembers = tMeta.max_members || 4;
      const modeRoundsObj = sb.rounds_by_mode[activeMode];

      for (let tIdx = 0; tIdx < teamCount; tIdx++) {
        const tSaved = savedTeams[tIdx] || {};
        refreshScoreboardTeamTotals(tIdx, tSaved, modeRoundsObj, maxRounds, maxMembers, sb);
      }
    }

    function refreshScoreboardTeamTotals(tIdx, teamObj, modeRoundsObj, maxRounds, maxMembers, sb = null) {
      const totals = computeTeamScoreboardTotals(teamObj, tIdx, modeRoundsObj, maxRounds, maxMembers, sb);
      const miniEl = document.getElementById(`sbMiniScore-${tIdx}`);
      if (miniEl) {
        miniEl.textContent = `${formatNumberDisplay(totals.totalNet)}점 · 🍗+${formatNumberDisplay(totals.totalChickenPoints)}`;
      }
      const topTotalsEl = document.getElementById(`sbTeamTotals-${tIdx}`);
      if (topTotalsEl) {
        topTotalsEl.innerHTML = `
          <span>총점: ${formatNumberDisplay(totals.totalNet)}</span>
          <span>킬핸디: +${formatNumberDisplay(totals.totalHandicap)}</span>
          <span>킬 합계: ${formatNumberDisplay(totals.totalKills)}</span>
          <span>감점 차감: -${formatNumberDisplay(totals.totalDeductions)}</span>
          <span>🍗 치킨점수: +${formatNumberDisplay(totals.totalChickenPoints)} (큰${totals.bigMapCount}/작${totals.smallMapCount})</span>
        `;
      }
      totals.roundTotals.forEach(rt => {
        const cellEl = document.getElementById(`sbRoundSum-${tIdx}-r${rt.round}`);
        if (cellEl) {
          cellEl.textContent = formatNumberDisplay(rt.net);
        }
      });
    }

    async function addPlayerToTier(tier, inputEl) {
      if (!fullEdit) return;
      const rawName = (inputEl.value || "").trim();
      if (!rawName) return;

      const board = getTierBoard();
      state.tiers.forEach(t => {
        board[t] = (board[t] || []).filter(n => n !== rawName);
      });
      board[tier].push(rawName);
      inputEl.value = "";

      renderSettingsBar();
      renderTierBoard(false);
      await flushAutoSave();
    }

    async function removePlayerFromTier(tier, playerName) {
      if (!fullEdit) return;
      const board = getTierBoard();
      board[tier] = (board[tier] || []).filter(n => n !== playerName);
      renderSettingsBar();
      renderTierBoard(false);
      await flushAutoSave();
    }

    function renderTierBoard(preserveFocus = false) {
      const focusSnap = preserveFocus ? getFocusSnapshot() : null;
      const board = getTierBoard();
      const container = document.getElementById("mainContent");
      container.innerHTML = "";

      const wrap = document.createElement("div");
      wrap.className = "tier-groups-wrap";

      const groups = state.tier_groups || [];
      groups.forEach((grp, gIdx) => {
        const subTiers = grp.tiers || [];
        const groupTotal = subTiers.reduce((sum, t) => sum + ((board[t] && board[t].length) || 0), 0);

        const groupCard = document.createElement("div");
        groupCard.className = "tier-group-card";

        const banner = document.createElement("div");
        banner.className = "tier-group-banner";
        banner.innerHTML = `
          <span>${escapeHtml(grp.group)}</span>
          <span class="tier-group-count">총 ${groupTotal}명</span>
        `;
        groupCard.appendChild(banner);

        const colsWrap = document.createElement("div");
        colsWrap.className = "subtier-cols " + (subTiers.length >= 4 ? "cols-4" : "cols-1");

        subTiers.forEach((tier, sIdx) => {
          const players = board[tier] || [];
          const shortLabel = tier.startsWith(grp.group) && tier !== grp.group
            ? tier.slice(grp.group.length).trim()
            : tier;

          const col = document.createElement("div");
          col.className = "subtier-col";

          const colHeader = document.createElement("div");
          colHeader.className = "subtier-col-header";
          colHeader.textContent = `${shortLabel} (${players.length})`;
          col.appendChild(colHeader);

          const vList = document.createElement("div");
          vList.className = "subtier-vertical-list";

          if (players.length === 0) {
            vList.innerHTML = `<span class="info-text" style="text-align:center; padding-top:8px;">-</span>`;
          } else {
            players.forEach(name => {
              const item = document.createElement("div");
              item.className = "vertical-member-item";
              item.innerHTML = `
                <span class="vertical-member-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
                <button type="button" class="chip-del" title="삭제" ${fullEdit ? "" : "disabled"}>×</button>
              `;
              const delBtn = item.querySelector(".chip-del");
              if (fullEdit) {
                delBtn.onclick = () => removePlayerFromTier(tier, name);
              }
              vList.appendChild(item);
            });
          }
          col.appendChild(vList);

          const inputKey = `tier-add-shared-${gIdx}-${sIdx}`;
          const addBox = document.createElement("div");
          addBox.className = "subtier-add-box";
          const inputVal = (focusSnap && focusSnap.fieldKey === inputKey) ? focusSnap.value : "";
          addBox.innerHTML = `
            <input type="text" class="subtier-add-input" data-field-key="${inputKey}" placeholder="이름" value="${escapeHtml(inputVal)}" ${fullEdit ? "" : "disabled"} />
            <button type="button" class="subtier-add-btn" ${fullEdit ? "" : "disabled"}>+</button>
          `;

          const addInput = addBox.querySelector(".subtier-add-input");
          const addBtn = addBox.querySelector(".subtier-add-btn");
          if (fullEdit) {
            addBtn.onclick = () => addPlayerToTier(tier, addInput);
            addInput.addEventListener("keydown", (e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addPlayerToTier(tier, addInput);
              }
            });
          }

          col.appendChild(addBox);
          colsWrap.appendChild(col);
        });

        groupCard.appendChild(colsWrap);
        wrap.appendChild(groupCard);
      });

      container.appendChild(wrap);

      if (preserveFocus && fullEdit) {
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
      const disAttr = fullEdit ? "" : "disabled";

      for (let tIdx = 0; tIdx < teamCount; tIdx++) {
        const saved = savedTeams[tIdx] || {};
        const teamNameKey = `${currentChannel}-${currentMode}-t${tIdx}-name`;
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
          <input type="text" class="team-name-input" data-field-key="${teamNameKey}" value="${escapeHtml(teamName)}" style="width:160px;" ${disAttr} />
        `;
        const teamNameInput = left.querySelector(".team-name-input");
        if (fullEdit) {
          teamNameInput.addEventListener("input", () => scheduleAutoSave());
        }

        const right = document.createElement("div");
        right.className = "team-right";

        const summarySpan = document.createElement("span");
        summarySpan.className = "summary-text";
        summarySpan.textContent = summary;

        const doneBtn = document.createElement("button");
        doneBtn.textContent = "완료";
        doneBtn.disabled = !fullEdit;
        if (fullEdit) {
          doneBtn.onclick = () => completeTeam(card);
        }

        right.appendChild(summarySpan);
        right.appendChild(doneBtn);

        header.appendChild(left);
        header.appendChild(right);
        card.appendChild(header);

        for (let slot = 1; slot <= meta.max_members; slot++) {
          const mSaved = savedMembers[slot - 1] || {};
          const row = document.createElement("div");
          row.className = "member-row";

          const mNameKey = `${currentChannel}-${currentMode}-t${tIdx}-s${slot}-name`;
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
            <input type="text" class="member-name" data-field-key="${mNameKey}" placeholder="멤버 이름" value="${escapeHtml(mNameVal)}" ${disAttr} />
            <span class="field-label">티어</span>
            <select class="member-tier" ${disAttr}>${tierOptions}</select>
            <span class="field-label">감점</span>
            <select class="member-penalty" ${disAttr}>${penaltyOptions}</select>
            <span class="field-label">킬핸디</span>
            <select class="member-handicap" ${disAttr}>${handicapOptions}</select>
          `;

          if (fullEdit) {
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
          }

          card.appendChild(row);
        }

        listEl.appendChild(card);
      }

      if (preserveFocus && fullEdit) {
        restoreFocusSnapshot(focusSnap);
      }
    }

    function renderMainContent(preserveFocus = false) {
      if (inLobby) {
        renderLobby();
        return;
      }
      if (currentMode === "tiers") {
        renderTierBoard(preserveFocus);
      } else if (currentMode === "scoreboard") {
        renderScoreboard(preserveFocus);
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
      if (!fullEdit) return;
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
      if (canEditCurrentView() && saveTimer) {
        clearTimeout(saveTimer);
        saveTimer = null;
        await flushAutoSave();
      } else if (fullEdit && ["solo", "duo", "squad"].includes(currentMode)) {
        const current = collectCurrentTeamUI();
        state.data.modes[currentMode] = {
          team_count: current.team_count,
          teams: current.teams
        };
      }
      currentMode = nextMode;
      renderTabs();
      renderSettingsBar();
      renderMainContent(false);
    }

    async function resetCurrentView() {
      if (!fullEdit) return;
      if (saveTimer) {
        clearTimeout(saveTimer);
        saveTimer = null;
      }

      const chParam = `channel=${encodeURIComponent(currentChannel)}`;

      if (currentMode === "tiers") {
        if (!confirm("전체 방 공용 티어표를 기본 명단으로 되돌릴까요?")) return;
        const res = await fetch(`/api/tier-board/reset?${chParam}`, {
          method: "POST",
          headers: authHeaders()
        });
        if (res.status === 403) {
          await reloadChannelState(currentChannel, true);
          return;
        }
        if (!res.ok) {
          alert("초기화 중 오류가 발생했습니다.");
          return;
        }
        const result = await res.json();
        localVersion = Math.max(localVersion, result.version || 0);
        const updatedBoard = result.tier_board || (result.data && result.data.tier_board);
        if (updatedBoard) {
          state.tier_board = updatedBoard;
          if (state.data) state.data.tier_board = updatedBoard;
        }
        renderSettingsBar();
        renderMainContent(false);
        document.getElementById("saveStatus").textContent = "기본 티어표 복원 완료";
        return;
      }

      if (currentMode === "scoreboard") {
        const sb = getScoreboardData();
        const tMeta = getTeamModeMeta(sb.active_team_mode);
        if (!confirm(`[점수판 · ${tMeta.label}] 1~30라운드 기록을 초기화할까요?`)) return;
        const res = await fetch(`/api/scoreboard/reset?${chParam}`, {
          method: "POST",
          headers: authHeaders()
        });
        if (res.status === 403) {
          await reloadChannelState(currentChannel, true);
          return;
        }
        if (!res.ok) {
          alert("초기화 중 오류가 발생했습니다.");
          return;
        }
        const result = await res.json();
        localVersion = Math.max(localVersion, result.version || 0);
        const keepStyle = localViewStyle || (state.data && state.data.scoreboard && state.data.scoreboard.view_style);
        state.data = result.data;
        if (keepStyle && state.data && state.data.scoreboard) {
          state.data.scoreboard.view_style = keepStyle;
        }
        renderSettingsBar();
        renderMainContent(false);
        document.getElementById("saveStatus").textContent = "점수판 초기화 완료";
        return;
      }

      const meta = getModeMeta(currentMode);
      if (!confirm(`[${meta.label}] 모드 데이터를 초기화할까요?`)) return;

      const res = await fetch(`/api/modes/${currentMode}/reset?${chParam}`, {
        method: "POST",
        headers: authHeaders()
      });
      if (res.status === 403) {
        await reloadChannelState(currentChannel, true);
        return;
      }
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

    async function reloadChannelState(chId, preserveFocus = true) {
      const lobbyParam = inLobby ? 1 : 0;
      const q = `/api/state?channel=${encodeURIComponent(chId)}&client_id=${encodeURIComponent(clientId)}&in_lobby=${lobbyParam}`;
      const res = await fetch(q, { headers: authHeaders() });
      const nextState = await res.json();
      if (localViewStyle && nextState && nextState.data && nextState.data.scoreboard) {
        nextState.data.scoreboard.view_style = localViewStyle;
      }
      state = nextState;
      localVersion = Math.max(localVersion, nextState.version || 1);
      fullEdit = Boolean(nextState.full_edit ?? nextState.logged_in);

      renderAuthBar();
      renderTabs();
      syncShellVisibility();
      if (!inLobby) {
        renderSettingsBar();
      }
      renderMainContent(preserveFocus);
    }

    function connectRealtimeStream() {
      if (eventSource) {
        eventSource.close();
      }
      const lobbyParam = inLobby ? 1 : 0;
      const q = `/api/stream?channel=${encodeURIComponent(currentChannel)}&client_id=${encodeURIComponent(clientId)}&edit_token=${encodeURIComponent(editToken)}&in_lobby=${lobbyParam}`;
      eventSource = new EventSource(q);
      eventSource.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          applyRemoteState(msg, true);
        } catch (e) {}
      };
      eventSource.onerror = () => {
        const statusEl = document.getElementById("saveStatus");
        if (statusEl) statusEl.textContent = "백업 동기화 중...";
      };
    }

    async function initApp() {
      const lobbyParam = inLobby ? 1 : 0;
      const q = `/api/state?channel=${encodeURIComponent(currentChannel)}&client_id=${encodeURIComponent(clientId)}&in_lobby=${lobbyParam}`;
      const res = await fetch(q, { headers: authHeaders() });
      state = await res.json();
      if (localViewStyle && state && state.data && state.data.scoreboard) {
        state.data.scoreboard.view_style = localViewStyle;
      }
      localVersion = state.version || 1;
      fullEdit = Boolean(state.full_edit ?? state.logged_in);

      renderAuthBar();
      renderTabs();
      syncShellVisibility();
      renderLobby();
      connectRealtimeStream();
      startPresenceLoop();
      startSyncBackupLoop();
    }

    window.addEventListener("beforeunload", () => {
      flushPendingOnUnload();
      sendPresenceHeartbeat(false);
    });

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
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
