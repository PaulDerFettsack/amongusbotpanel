"""
Among Us — Admin Panel Backend
Nur erreichbar für Discord-ID 148269980024688240
Login via Discord OAuth2 ODER einfacher Secret-Token
"""

from flask import Blueprint, jsonify, request, send_from_directory, Response, session, redirect, current_app
from flask_cors import CORS
import json, os, re, time, threading, secrets
from datetime import datetime
import pytz

admin_bp = Blueprint("admin", __name__)

DATA_FILE  = "amogus_data.json"
LOG_FILE   = "amogus_logs.json"
TIMEZONE   = pytz.timezone("Europe/Berlin")

# ── EINZIGE ERLAUBTE DISCORD-ID ──────────────────────────────────────────────
ADMIN_DISCORD_ID = "148269980024688240"

# Simple Token-Auth: Beim ersten Start wird ein Token generiert und gespeichert
TOKEN_FILE = "admin_token.txt"

def get_or_create_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    token = secrets.token_urlsafe(32)
    with open(TOKEN_FILE, "w") as f:
        f.write(token)
    print(f"\n{'='*50}")
    print(f"ADMIN TOKEN (nur einmal angezeigt):")
    print(f"  {token}")
    print(f"Öffne: http://localhost:5001/admin/login?token={token}")
    print(f"{'='*50}\n")
    return token

ADMIN_TOKEN = get_or_create_token()

# SSE subscribers
_subscribers      = []
_subscribers_lock = threading.Lock()

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_logs():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"commands": [], "users": {}, "guilds": {}}

def today_str():
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")

def is_authed():
    return session.get("authed") == True

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_authed():
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

def build_poll_status():
    data   = load_data()
    result = []
    for guild_id, gd in data.items():
        parts = gd.get("participants", {})
        late  = parts.get("late", {})
        if not isinstance(late, dict): late = {}
        gh    = gd.get("game_hour",   20)
        gm    = gd.get("game_minute",  0)
        result.append({
            "guild_id":      guild_id,
            "poll_id":       gd.get("poll_id", ""),
            "date":          gd.get("date", "—"),
            "is_today":      gd.get("date") == today_str(),
            "game_time":     f"{gh:02d}:{gm:02d}",
            "on_time":       parts.get("on_time", []),
            "late":          late,
            "absent":        parts.get("absent", []),
            "reminder_sent": gd.get("reminder_sent", False),
            "summary_sent":  gd.get("summary_sent",  False),
            "closed":        gd.get("closed", False),
            "total_players": len(parts.get("on_time", [])) + len(late),
        })
    return result

def notify_subscribers():
    payload = json.dumps(build_poll_status())
    with _subscribers_lock:
        dead = []
        for q in _subscribers:
            try: q.append(payload)
            except: dead.append(q)
        for q in dead: _subscribers.remove(q)

def watch_files():
    last = {}
    while True:
        for f in (DATA_FILE, LOG_FILE):
            try:
                if os.path.exists(f):
                    mtime = os.path.getmtime(f)
                    if mtime != last.get(f):
                        last[f] = mtime
                        pass  # polling: no SSE push needed
            except: pass
        time.sleep(0.5)

# ══════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════

@admin_bp.route("/admin/login")
def admin_login():
    token = request.args.get("token", "")
    if token == ADMIN_TOKEN:
        session["authed"] = True
        return redirect("/admin")
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Admin Login</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=IBM+Plex+Mono&display=swap" rel="stylesheet">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#04060f; color:#c8d8f0; font-family:'IBM Plex Mono',monospace;
         display:flex; align-items:center; justify-content:center; min-height:100vh; }
  .box { background:rgba(10,20,45,0.85); border:1px solid rgba(0,229,160,0.3);
         border-radius:16px; padding:40px; max-width:400px; width:90%; text-align:center;
         backdrop-filter:blur(20px); }
  h1 { font-family:'Orbitron',monospace; color:#00e5a0; font-size:20px; margin-bottom:8px; }
  p  { color:#4a6080; font-size:12px; margin-bottom:24px; }
  input { width:100%; background:rgba(0,0,0,0.4); border:1px solid rgba(100,160,255,0.2);
          border-radius:8px; padding:12px 16px; color:#00e5a0; font-family:'Orbitron',monospace;
          font-size:14px; outline:none; margin-bottom:16px; }
  input:focus { border-color:#4db8ff; }
  button { width:100%; height:44px; background:rgba(0,229,160,0.1); border:1px solid #00e5a0;
           border-radius:8px; color:#00e5a0; font-family:'IBM Plex Mono',monospace;
           font-size:12px; letter-spacing:0.1em; text-transform:uppercase; cursor:pointer; }
  button:hover { background:#00e5a0; color:#030a18; }
</style></head>
<body>
<div class="box">
  <h1>🔐 ADMIN ACCESS</h1>
  <p>Among Us Bot Control Panel<br>Nur für autorisierte Nutzer</p>
  <input type="password" id="t" placeholder="Token eingeben…" onkeydown="if(event.key==='Enter')login()">
  <button onclick="login()">🚀 Einloggen</button>
</div>
<script>
function login() {
  const t = document.getElementById('t').value.trim();
  if (t) window.location.href = '/admin/login?token=' + encodeURIComponent(t);
}
</script>
</body></html>"""

@admin_bp.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")

@admin_bp.route("/admin/check")
def admin_check():
    return jsonify({"authed": is_authed()})

# ══════════════════════════════════════════════
#  PROTECTED API — POLL DATA
# ══════════════════════════════════════════════

@admin_bp.route("/api/status")
@require_auth
def api_status():
    return jsonify(build_poll_status())

@admin_bp.route("/api/events")
@require_auth
def api_events():
    return jsonify(build_poll_status())


@admin_bp.route("/api/set_time", methods=["POST"])
@require_auth
def api_set_time():
    body = request.json or {}
    gid  = body.get("guild_id"); ts = body.get("time","")
    if not gid or not re.match(r"^\d{1,2}:\d{2}$", ts):
        return jsonify({"error":"Ungültig"}), 400
    h, m = map(int, ts.split(":"))
    if not (0<=h<=23 and 0<=m<=59): return jsonify({"error":"Ungültige Zeit"}), 400
    data = load_data()
    data.setdefault(gid, {})
    data[gid]["game_hour"] = h; data[gid]["game_minute"] = m
    save_data(data); pass  # polling: no SSE push needed
    return jsonify({"ok":True,"time":f"{h:02d}:{m:02d}"})

@admin_bp.route("/api/close_poll", methods=["POST"])
@require_auth
def api_close_poll():
    gid = (request.json or {}).get("guild_id")
    if not gid: return jsonify({"error":"guild_id fehlt"}), 400
    data = load_data()
    if gid in data:
        data[gid]["closed"] = True; data[gid]["poll_message_id"] = None
        save_data(data)
    pass  # polling: no SSE push needed
    return jsonify({"ok":True})

@admin_bp.route("/api/reset", methods=["POST"])
@require_auth
def api_reset():
    gid = (request.json or {}).get("guild_id")
    if not gid: return jsonify({"error":"guild_id fehlt"}), 400
    data = load_data()
    if gid in data:
        for k in ("poll_message_id","channel_id","date","poll_id"): data[gid].pop(k,None)
        data[gid].update({"participants":{"on_time":[],"late":{},"absent":[]},
                           "reminder_sent":False,"summary_sent":False,"closed":False})
        save_data(data)
    pass  # polling: no SSE push needed
    return jsonify({"ok":True})

# ══════════════════════════════════════════════
#  PROTECTED API — ADMIN / LOGS
# ══════════════════════════════════════════════

@admin_bp.route("/api/admin/users")
@require_auth
def api_users():
    """Alle User mit Stats."""
    logs  = load_logs()
    users = list(logs.get("users", {}).values())
    # Sort by last_seen desc
    users.sort(key=lambda u: u.get("last_seen",""), reverse=True)
    return jsonify(users)

@admin_bp.route("/api/admin/user/<uid>")
@require_auth
def api_user(uid):
    """Detailinfo für einen User."""
    logs = load_logs()
    u    = logs.get("users", {}).get(uid)
    if not u: return jsonify({"error":"User nicht gefunden"}), 404
    # Enrich: add guild names
    data   = load_data()
    guilds = logs.get("guilds", {})
    u["guild_details"] = [
        {"guild_id": gid, "name": guilds.get(gid, {}).get("guild_name", f"Guild {gid}")}
        for gid in u.get("guilds", [])
    ]
    return jsonify(u)

@admin_bp.route("/api/admin/guilds")
@require_auth
def api_guilds():
    """Alle Guilds mit Stats."""
    logs   = load_logs()
    guilds = list(logs.get("guilds", {}).values())
    guilds.sort(key=lambda g: g.get("last_activity",""), reverse=True)
    return jsonify(guilds)

@admin_bp.route("/api/admin/commands")
@require_auth
def api_commands():
    """Letzte Bot-Commands (max 200)."""
    logs  = load_logs()
    cmds  = logs.get("commands", [])[-200:]
    cmds  = list(reversed(cmds))  # newest first
    limit = int(request.args.get("limit", 100))
    return jsonify(cmds[:limit])

@admin_bp.route("/api/admin/stats")
@require_auth
def api_stats():
    """Globale Statistiken."""
    logs   = load_logs()
    data   = load_data()
    users  = logs.get("users", {})
    guilds = logs.get("guilds", {})
    cmds   = logs.get("commands", [])

    total_votes = sum(
        u.get("on_time_count",0) + u.get("late_count",0) + u.get("absent_count",0)
        for u in users.values()
    )
    total_games = sum(g.get("total_polls",0) for g in guilds.values())

    # Most active users (by total_games)
    top_users = sorted(users.values(), key=lambda u: u.get("total_games",0), reverse=True)[:5]

    # Activity last 7 days
    from datetime import date, timedelta as td
    daily = {}
    for i in range(7):
        d = (date.today() - td(days=i)).isoformat()
        votes = 0
        for g in guilds.values():
            votes += g.get("daily_stats", {}).get(d, {}).get("votes", 0)
        daily[d] = votes

    return jsonify({
        "total_users":   len(users),
        "total_guilds":  len(guilds),
        "total_commands":len(cmds),
        "total_votes":   total_votes,
        "total_games":   total_games,
        "top_users":     top_users,
        "daily_votes":   daily,
    })

# ══════════════════════════════════════════════
#  SERVE FRONTENDS
# ══════════════════════════════════════════════

@admin_bp.route("/")
def index():
    if not is_authed():
        return redirect("/admin/login")
    return redirect("/admin")

@admin_bp.route("/admin")
def admin_panel():
    if not is_authed():
        return redirect("/admin/login")
    return send_from_directory(".", "admin_panel.html")

@admin_bp.route("/panel")
def main_panel():
    # Main panel also requires auth
    if not is_authed():
        return redirect("/admin/login")
    return send_from_directory(".", "panel.html")
