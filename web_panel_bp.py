"""
Among Us Bot — Web Panel v3
============================
Auth-Flow:
  1. User klickt "Mit Discord einloggen"
  2. Discord OAuth2 → Callback mit Code
  3. Panel tauscht Code gegen Access-Token
  4. Panel holt Discord-Profil + Guild-Mitgliedschaft
  5. Wenn User NICHT auf dem Discord-Server → 403
  6. Wenn User neu → Registrierungsseite (Panel-Passwort + Invite-Code)
  7. Wenn User bekannt → direkt einloggen

.env Pflichtfelder:
  DISCORD_TOKEN        = Bot-Token (für Guild-Check)
  DISCORD_CLIENT_ID    = OAuth2 App Client-ID
  DISCORD_CLIENT_SECRET= OAuth2 App Client-Secret
  DISCORD_GUILD_ID     = ID des Servers, auf dem man sein muss
  DISCORD_REDIRECT_URI = https://amgpanel.pierbit.de/auth/callback
  INVITE_CODE          = Geheimer Einladungscode
  SECRET_KEY           = (optional) Flask Session Secret

Einrichtung Discord Developer Portal:
  https://discord.com/developers/applications
  → Deine App → OAuth2 → Redirects → https://amgpanel.pierbit.de/auth/callback hinzufügen
  → Scopes: identify, guilds.members.read

pip install flask flask-cors pytz bcrypt requests
"""

from flask import (Blueprint, jsonify, request, send_from_directory,
                   Response, redirect, session, current_app)
from flask_cors import CORS
from functools import wraps
import json, os, re, time, threading, secrets, hashlib
from datetime import datetime, timedelta
import urllib.parse
import pytz

try:
    import requests as http
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request, urllib.error

try:
    import bcrypt
    USE_BCRYPT = True
except ImportError:
    USE_BCRYPT = False

from dotenv import load_dotenv
load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

DISCORD_CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID",     "")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
DISCORD_GUILD_ID      = os.environ.get("DISCORD_GUILD_ID",      "")
DISCORD_REDIRECT_URI  = os.environ.get("DISCORD_REDIRECT_URI",  "https://amgpanel.pierbit.de/auth/callback")
DISCORD_BOT_TOKEN     = os.environ.get("DISCORD_TOKEN",         "")
INVITE_CODE           = os.environ.get("INVITE_CODE",           "")

DISCORD_API    = "https://discord.com/api/v10"
DISCORD_SCOPES = "identify guilds.members.read"

DATA_DIR   = os.environ.get("DATA_DIR", ".")
DATA_FILE  = os.path.join(DATA_DIR, "amogus_data.json")
USERS_FILE = os.path.join(DATA_DIR, "amogus_users.json")
TIMEZONE   = pytz.timezone("Europe/Berlin")
SESSION_LIFETIME = 7 * 24 * 3600   # 7 Tage

web_bp = Blueprint("web", __name__)

_subscribers      = []
_subscribers_lock = threading.Lock()

# ════════════════════════════════════════════════════════════════════
#  Discord API Helpers
# ════════════════════════════════════════════════════════════════════

def discord_exchange_code(code: str) -> dict | None:
    """Tauscht OAuth2-Code gegen Token. Loggt Discord-Fehler detailliert."""
    data = {
        "client_id":     DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  DISCORD_REDIRECT_URI,
    }
    print(f"[OAuth] Token exchange | redirect_uri={DISCORD_REDIRECT_URI}")
    print(f"[OAuth] client_id={DISCORD_CLIENT_ID[:10] if DISCORD_CLIENT_ID else 'MISSING'}... | secret={'OK' if DISCORD_CLIENT_SECRET else 'MISSING'}")
    UA = "AmongUsPanel/1.0 (https://amgpanel.pierbit.de)"
    if HAS_REQUESTS:
        r = http.post(
            f"{DISCORD_API}/oauth2/token", data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": UA,
            }
        )
        print(f"[OAuth] Discord status={r.status_code} body={r.text[:400]}")
        if r.ok:
            return r.json()
        print(f"[OAuth] FAILED: {r.status_code} {r.text}")
        return None
    else:
        enc = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(
            f"{DISCORD_API}/oauth2/token", data=enc,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "AmongUsPanel/1.0 (https://amgpanel.pierbit.de)",
            }
        )
        try:
            with urllib.request.urlopen(req) as resp:
                body = resp.read()
                print(f"[OAuth] urllib ok: {body[:300]}")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"[OAuth] urllib HTTPError {e.code}: {body}")
            return None
        except Exception as ex:
            print(f"[OAuth] urllib Exception: {ex}")
            return None


def discord_get_user(access_token: str) -> dict | None:
    """Holt Discord-Nutzerprofil."""
    UA = "AmongUsPanel/1.0 (https://amgpanel.pierbit.de)"
    if HAS_REQUESTS:
        r = http.get(f"{DISCORD_API}/users/@me",
                     headers={"Authorization": f"Bearer {access_token}", "User-Agent": UA})
        print(f"[OAuth] get_user status={r.status_code}")
        return r.json() if r.ok else None
    else:
        req = urllib.request.Request(f"{DISCORD_API}/users/@me",
                                      headers={
                                          "Authorization": f"Bearer {access_token}",
                                          "User-Agent": "AmongUsPanel/1.0 (https://amgpanel.pierbit.de)",
                                      })
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except Exception as ex:
            print(f"[OAuth] get_user error: {ex}")
            return None


def discord_check_guild_member(discord_user_id: str, access_token: str) -> bool:
    """
    Prüft ob User Mitglied des konfigurierten Servers ist.
    Nutzt guilds.members.read scope mit dem User-Token.
    """
    if not DISCORD_GUILD_ID:
        return True  # Kein Guild-Check konfiguriert → alle erlaubt

    # Methode 1: User-Token (guilds.members.read)
    if HAS_REQUESTS:
        UA = "AmongUsPanel/1.0 (https://amgpanel.pierbit.de)"
        r = http.get(
            f"{DISCORD_API}/users/@me/guilds/{DISCORD_GUILD_ID}/member",
            headers={"Authorization": f"Bearer {access_token}", "User-Agent": UA}
        )
        if r.status_code == 200:
            return True
        if r.status_code == 403:
            return False

        # Methode 2: Bot-Token als Fallback
        if DISCORD_BOT_TOKEN:
            r2 = http.get(
                f"{DISCORD_API}/guilds/{DISCORD_GUILD_ID}/members/{discord_user_id}",
                headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "User-Agent": UA}
            )
            return r2.status_code == 200
        return False
    else:
        # urllib Fallback
        req = urllib.request.Request(
            f"{DISCORD_API}/users/@me/guilds/{DISCORD_GUILD_ID}/member",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        try:
            urllib.request.urlopen(req)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404 and DISCORD_BOT_TOKEN:
                req2 = urllib.request.Request(
                    f"{DISCORD_API}/guilds/{DISCORD_GUILD_ID}/members/{discord_user_id}",
                    headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
                )
                try:
                    urllib.request.urlopen(req2)
                    return True
                except:
                    return False
            return False


def discord_get_avatar_url(user: dict) -> str:
    uid   = user.get("id","")
    avatar= user.get("avatar")
    if avatar:
        ext = "gif" if avatar.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.{ext}?size=64"
    discrim = int(user.get("discriminator","0") or "0")
    return f"https://cdn.discordapp.com/embed/avatars/{discrim % 5}.png"


def build_oauth_url(state: str) -> str:
    params = {
        "client_id":     DISCORD_CLIENT_ID,
        "redirect_uri":  DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope":         DISCORD_SCOPES,
        "state":         state,
        "prompt":        "none",
    }
    return f"https://discord.com/oauth2/authorize?{urllib.parse.urlencode(params)}"

# ════════════════════════════════════════════════════════════════════
#  Password Helpers
# ════════════════════════════════════════════════════════════════════

def hash_password(pw: str) -> str:
    if USE_BCRYPT:
        return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    salt = secrets.token_hex(16)
    h    = hashlib.sha256((salt + pw).encode()).hexdigest()
    return f"sha256:{salt}:{h}"

def check_password(pw: str, stored: str) -> bool:
    if USE_BCRYPT and not stored.startswith("sha256:"):
        return bcrypt.checkpw(pw.encode(), stored.encode())
    if stored.startswith("sha256:"):
        _, salt, h = stored.split(":", 2)
        return hashlib.sha256((salt + pw).encode()).hexdigest() == h
    return False

# ════════════════════════════════════════════════════════════════════
#  User Store
# ════════════════════════════════════════════════════════════════════

def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(u: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(u, f, ensure_ascii=False, indent=2)

def get_user_by_discord_id(discord_id: str) -> dict | None:
    for u in load_users().values():
        if u.get("discord_id") == discord_id:
            return u
    return None

def get_user_by_username(username: str) -> dict | None:
    return load_users().get(username.lower())

def create_user(discord_id: str, discord_username: str,
                discord_avatar: str, panel_username: str,
                panel_password: str) -> dict:
    users = load_users()
    is_first = len(users) == 0
    key   = panel_username.lower()
    users[key] = {
        "username":        panel_username,
        "password":        hash_password(panel_password),
        "discord_id":      discord_id,
        "discord_username":discord_username,
        "discord_avatar":  discord_avatar,
        "role":            "admin" if is_first else "user",
        "created_at":      datetime.now(TIMEZONE).isoformat(),
    }
    save_users(users)
    return users[key]

def update_discord_info(panel_username: str, discord_username: str, discord_avatar: str):
    """Aktualisiert Discord-Infos beim Login."""
    users = load_users()
    key   = panel_username.lower()
    if key in users:
        users[key]["discord_username"] = discord_username
        users[key]["discord_avatar"]   = discord_avatar
        save_users(users)

# ════════════════════════════════════════════════════════════════════
#  Session / Auth Middleware
# ════════════════════════════════════════════════════════════════════

def get_current_user() -> dict | None:
    username = session.get("username")
    if not username:
        return None
    return get_user_by_username(username)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            if request.path.startswith("/api/"):
                return jsonify({"error": "not_authenticated", "redirect": "/login"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

def set_session(username: str):
    session.permanent = True
    current_app.permanent_session_lifetime = timedelta(seconds=SESSION_LIFETIME)
    session["username"] = username.lower()
    session.modified = True

# ════════════════════════════════════════════════════════════════════
#  Data / SSE
# ════════════════════════════════════════════════════════════════════

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def today_str():
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")

def build_status():
    data   = load_data()
    logs   = load_logs()
    users  = logs.get("users", {})

    def user_info(uid):
        u = users.get(str(uid), {})
        return {
            "id":      uid,
            "name":    u.get("display") or u.get("username") or uid,
            "avatar":  u.get("avatar_url", ""),
        }

    result = []
    for guild_id, gd in data.items():
        parts = gd.get("participants", {"on_time":[],"late":{},"absent":[]})
        late  = parts.get("late", {})
        if not isinstance(late, dict): late = {}
        gh, gm = gd.get("game_hour",20), gd.get("game_minute",0)
        result.append({
            "guild_id":      guild_id,
            "poll_id":       gd.get("poll_id",""),
            "date":          gd.get("date","—"),
            "is_today":      gd.get("date") == today_str(),
            "game_time":     f"{gh:02d}:{gm:02d}",
            "on_time":       parts.get("on_time",[]),
            "late":          late,
            "absent":        parts.get("absent",[]),
            "reminder_sent": gd.get("reminder_sent",False),
            "summary_sent":  gd.get("summary_sent",False),
            "closed":        gd.get("closed",False),
            "total_players": len(parts.get("on_time",[])) + len(late),
            "time_changed":  gd.get("time_changed", False),
            # User info map: uid → {name, avatar}
            "user_info":     {uid: user_info(uid) for uid in
                              parts.get("on_time",[]) +
                              list(late.keys()) +
                              parts.get("absent",[])},
        })
    return result

def notify_subscribers():
    payload = json.dumps(build_status())
    with _subscribers_lock:
        dead = []
        for q in _subscribers:
            try: q.append(payload)
            except: dead.append(q)
        for q in dead: _subscribers.remove(q)

def watch_data_file():
    last_mtime = 0
    while True:
        try:
            if os.path.exists(DATA_FILE):
                mtime = os.path.getmtime(DATA_FILE)
                if mtime != last_mtime:
                    last_mtime = mtime
                    pass  # polling: no SSE push needed
        except: pass
        time.sleep(0.5)

# ════════════════════════════════════════════════════════════════════
#  ROUTES — OAuth2 Flow
# ════════════════════════════════════════════════════════════════════

@web_bp.route("/login")
def login_page():
    if get_current_user():
        return redirect("/")
    return send_from_directory(".", "login.html")

@web_bp.route("/auth/discord")
def auth_discord():
    """Startet den Discord OAuth2 Flow."""
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    return redirect(build_oauth_url(state))

@web_bp.route("/auth/callback")
def auth_callback():
    """Discord ruft diese URL nach der Authorisierung auf."""
    error = request.args.get("error")
    if error:
        return redirect(f"/login?error={urllib.parse.quote(error)}")

    code  = request.args.get("code","")
    state = request.args.get("state","")

    # State prüfen (CSRF-Schutz)
    if not code or state != session.pop("oauth_state", None):
        return redirect("/login?error=invalid_state")

    # Code → Token
    token_data = discord_exchange_code(code)
    if not token_data or "access_token" not in token_data:
        return redirect("/login?error=token_exchange_failed")

    access_token = token_data["access_token"]

    # Discord-Profil holen
    discord_user = discord_get_user(access_token)
    if not discord_user:
        return redirect("/login?error=profile_failed")

    discord_id       = discord_user["id"]
    discord_username = discord_user.get("global_name") or discord_user.get("username","")
    discord_avatar   = discord_get_avatar_url(discord_user)

    # ── Guild-Check ──────────────────────────────────────────────────
    if not discord_check_guild_member(discord_id, access_token):
        return redirect("/login?error=not_in_guild")

    # ── Bekannter User → direkt einloggen ────────────────────────────
    existing = get_user_by_discord_id(discord_id)
    if existing:
        update_discord_info(existing["username"], discord_username, discord_avatar)
        set_session(existing["username"])
        return redirect("/")

    # ── Neuer User → Registrierung ───────────────────────────────────
    # Discord-Daten in Session für Registrierungsseite
    session["pending_discord_id"]       = discord_id
    session["pending_discord_username"] = discord_username
    session["pending_discord_avatar"]   = discord_avatar
    session["pending_discord_tag"]      = discord_user.get("username","")
    return redirect("/register")

@web_bp.route("/register")
def register_page():
    if get_current_user():
        return redirect("/")
    # Muss durch Discord OAuth gegangen sein
    if not session.get("pending_discord_id"):
        return redirect("/login?error=no_discord_auth")
    return send_from_directory(".", "register.html")

@web_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ════════════════════════════════════════════════════════════════════
#  API — Auth
# ════════════════════════════════════════════════════════════════════

@web_bp.route("/api/register", methods=["POST"])
def api_register():
    """Registriert einen neuen User nach Discord-Auth."""
    # Discord-Daten müssen in der Session sein
    discord_id       = session.get("pending_discord_id")
    discord_username = session.get("pending_discord_username","")
    discord_avatar   = session.get("pending_discord_avatar","")

    if not discord_id:
        return jsonify({"error": "Nicht autorisiert — zuerst mit Discord einloggen"}), 401

    body           = request.json or {}
    panel_username = body.get("username","").strip()
    panel_password = body.get("password","")
    invite = body.get("invite_code", body.get("invite", "")).strip()

    # Validierung
    if not panel_username or not panel_password:
        return jsonify({"error": "Alle Felder ausfüllen"}), 400
    if len(panel_username) < 3 or len(panel_username) > 32:
        return jsonify({"error": "Benutzername: 3–32 Zeichen"}), 400
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", panel_username):
        return jsonify({"error": "Benutzername: nur a-z, 0-9, _ - ."}), 400
    if len(panel_password) < 6:
        return jsonify({"error": "Passwort min. 6 Zeichen"}), 400

    # Invite-Code Prüfung
    if INVITE_CODE and invite != INVITE_CODE:
        return jsonify({"error": "Ungültiger Einladungscode"}), 403

    # Doppelt prüfen ob Discord-ID schon registriert
    if get_user_by_discord_id(discord_id):
        return jsonify({"error": "Diese Discord-Account ist bereits registriert"}), 409

    # Username bereits vergeben?
    if get_user_by_username(panel_username):
        return jsonify({"error": "Benutzername bereits vergeben"}), 409

    user = create_user(discord_id, discord_username, discord_avatar, panel_username, panel_password)

    # Pending-Daten aus Session entfernen + einloggen
    for k in ("pending_discord_id","pending_discord_username","pending_discord_avatar","pending_discord_tag"):
        session.pop(k, None)

    set_session(panel_username)
    return jsonify({"ok": True, "username": user["username"], "role": user["role"]})

@web_bp.route("/api/login", methods=["POST"])
def api_login():
    """Normaler Login mit Panel-Passwort (nach Discord-Auth nicht nötig, aber als Fallback)."""
    body     = request.json or {}
    username = body.get("username","").strip()
    password = body.get("password","")
    if not username or not password:
        return jsonify({"error": "Felder ausfüllen"}), 400
    user = get_user_by_username(username)
    if not user or not check_password(password, user["password"]):
        return jsonify({"error": "Ungültige Anmeldedaten"}), 401
    set_session(username)
    return jsonify({"ok": True, "username": user["username"], "role": user["role"]})

@web_bp.route("/api/me")
def api_me():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({
        "authenticated":    True,
        "username":         user["username"],
        "role":             user.get("role","user"),
        "discord_username": user.get("discord_username",""),
        "discord_avatar":   user.get("discord_avatar",""),
    })

@web_bp.route("/api/pending_discord")
def api_pending_discord():
    """Gibt Discord-Daten für die Registrierungsseite zurück."""
    if not session.get("pending_discord_id"):
        return jsonify({"ok": False}), 401
    return jsonify({
        "ok":       True,
        "username": session.get("pending_discord_username",""),
        "avatar":   session.get("pending_discord_avatar",""),
        "tag":      session.get("pending_discord_tag",""),
        "is_first": len(load_users()) == 0,
    })

@web_bp.route("/api/config")
def api_config():
    """Gibt Panel-Konfiguration zurück (kein Auth nötig, nur öffentliche Infos)."""
    return jsonify({
        "discord_configured": bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET),
        "guild_check":        bool(DISCORD_GUILD_ID),
        "invite_required":    bool(INVITE_CODE),
    })

# ════════════════════════════════════════════════════════════════════
#  API — Panel (Auth-geschützt)
# ════════════════════════════════════════════════════════════════════

@web_bp.route("/api/status")
@require_auth
def api_status():
    return jsonify(build_status())

@web_bp.route("/api/events")
@require_auth
def api_events():
    # Simple polling endpoint — no streaming, no blocked threads
    return jsonify(build_status())


@web_bp.route("/api/set_time", methods=["POST"])
@require_auth
def api_set_time():
    body = request.json or {}
    gid  = body.get("guild_id")
    ts   = body.get("time","")
    if not gid or not re.match(r"^\d{1,2}:\d{2}$", ts):
        return jsonify({"error":"Ungültig"}), 400
    h, m = map(int, ts.split(":"))
    if not (0<=h<=23 and 0<=m<=59):
        return jsonify({"error":"Ungültige Uhrzeit"}), 400
    data = load_data()
    data.setdefault(gid,{})
    data[gid]["game_hour"]    = h
    data[gid]["game_minute"]  = m
    # Verändert nur wenn anders als Original
    orig_h = data[gid].get("original_hour", h)
    orig_m = data[gid].get("original_minute", m)
    data[gid]["time_changed"] = not (h == orig_h and m == orig_m)
    # Signal an Bot: Umfragenachricht updaten
    data[gid]["pending_action"] = "update_poll_message"
    save_data(data); pass  # polling: no SSE push needed
    return jsonify({"ok":True,"time":f"{h:02d}:{m:02d}"})

@web_bp.route("/api/close_poll", methods=["POST"])
@require_auth
def api_close_poll():
    gid = (request.json or {}).get("guild_id")
    if not gid: return jsonify({"error":"guild_id fehlt"}), 400
    data = load_data()
    if gid in data:
        # Signal an Bot: Umfrage schließen + Nachricht löschen + Zusammenfassung posten
        data[gid]["pending_action"] = "close_poll"
    save_data(data); pass  # polling: no SSE push needed
    return jsonify({"ok":True})

@web_bp.route("/api/reset", methods=["POST"])
@require_auth
def api_reset():
    gid = (request.json or {}).get("guild_id")
    if not gid: return jsonify({"error":"guild_id fehlt"}), 400
    data = load_data()
    if gid in data:
        for k in ("poll_message_id","channel_id","date","poll_id"):
            data[gid].pop(k, None)
        data[gid].update({"participants":{"on_time":[],"late":{},"absent":[]},
                           "reminder_sent":False,"summary_sent":False,"closed":False})
        save_data(data)
    pass  # polling: no SSE push needed
    return jsonify({"ok":True})

@web_bp.route("/")
@require_auth
def index():
    return send_from_directory(".", "panel.html")

# ════════════════════════════════════════════════════════════════════
#  Start
# ════════════════════════════════════════════════════════════════════


@web_bp.route("/api/debug_config")
def api_debug_config():
    """Zeigt Konfiguration — NUR für Debugging, danach entfernen!"""
    return jsonify({
        "DISCORD_CLIENT_ID":     DISCORD_CLIENT_ID[:10]+"..." if DISCORD_CLIENT_ID else "MISSING",
        "DISCORD_CLIENT_SECRET": "OK ("+str(len(DISCORD_CLIENT_SECRET))+" chars)" if DISCORD_CLIENT_SECRET else "MISSING",
        "DISCORD_GUILD_ID":      DISCORD_GUILD_ID or "NOT SET",
        "DISCORD_REDIRECT_URI":  DISCORD_REDIRECT_URI,
        "DISCORD_BOT_TOKEN":     "OK" if DISCORD_BOT_TOKEN else "MISSING",
        "INVITE_CODE":           "SET" if INVITE_CODE else "NOT SET",
        "HAS_REQUESTS":          HAS_REQUESTS,
        "USE_BCRYPT":            USE_BCRYPT,
    })
