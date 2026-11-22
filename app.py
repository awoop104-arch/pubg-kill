import json
import os
import threading
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DATA_FILE = os.environ.get("DATA_FILE", "pubg_kill_match_data.json")
FILE_LOCK = threading.Lock()

MODES = [
    ("solo", "솔로", 1),
    ("duo", "듀오", 2),
    ("squad", "스쿼드", 4),
]

TIERS = [
    "1최상", "1상", "1중", "1하",
    "2최상", "2상", "2중", "2하",
    "3최상", "3상", "3중", "3하",
    "4최상", "4상", "4중", "4하",
    "새싹", "씨앗",
]
PENALTIES = [0] + [-n for n in range(1, 11)]
HANDICAPS = list(range(0, 11))


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
        }
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
    return base


def save_db(data):
    parent_dir = os.path.dirname(os.path.abspath(DATA_FILE))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    tmp_file = f"{DATA_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, DATA_FILE)


class ModeStatePayload(BaseModel):
    team_count: int
    teams: list


app = FastAPI(title="PUBG 킬내기 관리 웹")


@app.get("/api/state")
def get_state():
    with FILE_LOCK:
        data = load_db()
    return {
        "modes_meta": [
            {"key": k, "label": label, "max_members": max_m}
            for k, label, max_m in MODES
        ],
        "tiers": TIERS,
        "penalties": PENALTIES,
        "handicaps": HANDICAPS,
        "data": data,
    }


@app.put("/api/modes/{mode_key}")
def update_mode(mode_key: str, payload: ModeStatePayload):
    valid_keys = {k for k, _, _ in MODES}
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
    return {"ok": True, "mode": mode_key, "data": data}


@app.post("/api/modes/{mode_key}/reset")
def reset_mode(mode_key: str):
    valid_keys = {k for k, _, _ in MODES}
    if mode_key not in valid_keys:
        raise HTTPException(status_code=400, detail="지원하지 않는 모드입니다.")

    with FILE_LOCK:
        data = load_db()
        data["modes"][mode_key] = default_mode_data()
        save_db(data)
    return {"ok": True, "mode": mode_key, "data": data}


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
      max-width: 1160px;
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
      gap: 8px;
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
    button.primary {
      background: #2563eb;
      border-color: #2563eb;
      color: #fff;
    }
    button.primary:hover {
      background: #1d4ed8;
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
    .status-toast {
      font-size: 12px;
      color: #64748b;
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
        <div class="settings-left">
          <label for="teamCountInput"><strong>참가 팀 수</strong></label>
          <input type="number" id="teamCountInput" min="2" max="10" value="2" />
          <span class="info-text" id="slotInfo"></span>
        </div>
        <div class="settings-actions">
          <span class="status-toast" id="saveStatus">공용 데이터 동기화됨</span>
          <button onclick="reloadFromServer()">새로고침</button>
          <button class="primary" onclick="saveCurrentMode(true)">저장</button>
          <button class="danger" onclick="resetCurrentMode()">초기화</button>
        </div>
      </div>
    </div>

    <div id="teamsList"></div>
  </div>

  <script>
    let state = null;
    let currentMode = "solo";

    function getModeMeta(modeKey = currentMode) {
      return state.modes_meta.find(m => m.key === modeKey) || { key: modeKey, label: modeKey, max_members: 4 };
    }

    function getModeData(modeKey = currentMode) {
      if (!state.data.modes[modeKey]) {
        state.data.modes[modeKey] = { team_count: 2, teams: [] };
      }
      return state.data.modes[modeKey];
    }

    function collectCurrentUI() {
      const meta = getModeMeta(currentMode);
      const countInput = parseInt(document.getElementById("teamCountInput").value, 10);
      const teamCount = Math.max(2, Math.min(10, Number.isNaN(countInput) ? 2 : countInput));
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

    function renderTeams() {
      const meta = getModeMeta(currentMode);
      const modeData = getModeData(currentMode);
      const teamCount = Math.max(2, Math.min(10, parseInt(modeData.team_count || 2, 10)));

      document.getElementById("teamCountInput").value = teamCount;
      document.getElementById("modeInfo").textContent =
        `[${meta.label}] AI 밸런스 조절 제외 · 최대 10팀 / 팀당 최대 ${meta.max_members}명`;
      document.getElementById("slotInfo").textContent =
        `${meta.label} 기준 · 팀당 최대 ${meta.max_members}명`;

      const listEl = document.getElementById("teamsList");
      listEl.innerHTML = "";
      const savedTeams = modeData.teams || [];

      for (let tIdx = 0; tIdx < teamCount; tIdx++) {
        const saved = savedTeams[tIdx] || {};
        const teamName = saved.name || `TEAM ${tIdx + 1}`;
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
          <input type="text" class="team-name-input" value="${escapeHtml(teamName)}" style="width:160px;" />
        `;

        const right = document.createElement("div");
        right.className = "team-right";

        const summarySpan = document.createElement("span");
        summarySpan.className = "summary-text";
        summarySpan.textContent = summary;

        const doneBtn = document.createElement("button");
        doneBtn.textContent = "완료";
        doneBtn.onclick = () => completeTeam(card, tIdx);

        right.appendChild(summarySpan);
        right.appendChild(doneBtn);

        header.appendChild(left);
        header.appendChild(right);
        card.appendChild(header);

        for (let slot = 1; slot <= meta.max_members; slot++) {
          const mSaved = savedMembers[slot - 1] || {};
          const row = document.createElement("div");
          row.className = "member-row";

          const tierOptions = [`<option value="">선택</option>`]
            .concat(state.tiers.map(t => `<option value="${t}" ${mSaved.tier === t ? "selected" : ""}>${t}</option>`))
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
            <input type="text" class="member-name" placeholder="멤버 이름" value="${escapeHtml(mSaved.name || "")}" />
            <span class="field-label">티어</span>
            <select class="member-tier">${tierOptions}</select>
            <span class="field-label">감점</span>
            <select class="member-penalty">${penaltyOptions}</select>
            <span class="field-label">킬핸디</span>
            <select class="member-handicap">${handicapOptions}</select>
          `;
          card.appendChild(row);
        }

        listEl.appendChild(card);
      }
    }

    function escapeHtml(str) {
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    async function completeTeam(card, tIdx) {
      let penaltySum = 0;
      let handicapSum = 0;
      card.querySelectorAll(".member-row").forEach(row => {
        penaltySum += parseInt(row.querySelector(".member-penalty").value, 10) || 0;
        handicapSum += parseInt(row.querySelector(".member-handicap").value, 10) || 0;
      });
      card.querySelector(".summary-text").textContent =
        `완료 · 감점 합계: ${penaltySum} | 킬핸디 합계: ${handicapSum}`;
      await saveCurrentMode(false);
    }

    async function saveCurrentMode(showAlert = false) {
      const payload = collectCurrentUI();
      state.data.modes[currentMode] = payload;
      document.getElementById("saveStatus").textContent = "저장 중...";

      const res = await fetch(`/api/modes/${currentMode}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        document.getElementById("saveStatus").textContent = "저장 실패";
        alert("저장 중 오류가 발생했습니다.");
        return;
      }
      const result = await res.json();
      state.data = result.data;
      document.getElementById("saveStatus").textContent = "공용 저장소에 반영됨";
      if (showAlert) {
        alert("저장되었습니다.");
      }
    }

    async function switchMode(nextMode) {
      if (nextMode === currentMode) return;
      await saveCurrentMode(false);
      currentMode = nextMode;
      renderTabs();
      renderTeams();
    }

    async function resetCurrentMode() {
      const meta = getModeMeta(currentMode);
      if (!confirm(`[${meta.label}] 모드 데이터를 초기화할까요?`)) return;

      const res = await fetch(`/api/modes/${currentMode}/reset`, { method: "POST" });
      if (!res.ok) {
        alert("초기화 중 오류가 발생했습니다.");
        return;
      }
      const result = await res.json();
      state.data = result.data;
      renderTeams();
      document.getElementById("saveStatus").textContent = `${meta.label} 초기화 완료`;
    }

    async function reloadFromServer() {
      const res = await fetch("/api/state");
      state = await res.json();
      renderTabs();
      renderTeams();
      document.getElementById("saveStatus").textContent = "최신 데이터 불러옴";
    }

    document.getElementById("teamCountInput").addEventListener("change", () => {
      const current = collectCurrentUI();
      state.data.modes[currentMode] = current;
      renderTeams();
    });

    reloadFromServer();
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
