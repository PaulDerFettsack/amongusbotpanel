# 🚀 Among Us Bot — Ready for Railway Deployment

## Quick Start für Railway

### 1️⃣ Repository auf Railway deployen
```bash
# Link deinen GitHub-Repository zu Railway
# Oder Connected GitHub Repository
```

### 2️⃣ Umgebungsvariablen setzen

Gehe in Railway Dashboard → **Environment Variables** und füge diese hinzu:

```
DISCORD_TOKEN=<dein_bot_token>
DISCORD_CLIENT_ID=<oauth_client_id>
DISCORD_CLIENT_SECRET=<oauth_client_secret>
DISCORD_GUILD_ID=<server_id>
DISCORD_REDIRECT_URI=https://<railway-app-url>/auth/callback
ADMIN_TOKEN=<sicherer_token>
INVITE_CODE=<geheimer_code>
```

### 3️⃣ Build & Deploy

Railway erkennt automatisch:
- ✅ `requirements.txt` → Python Abhängigkeiten
- ✅ `Procfile` → Start-Befehl
- ✅ `app.py` → Flask Hauptanwendung

## 📋 Verfügbare Endpoints

### User Panel
- `GET /` → Hauptansicht
- `GET /login` → Loginseite
- `GET /register` → Registrierung
- `POST /api/login` → Login API
- `POST /api/register` → Registrierung API

### Admin Panel
- `GET /admin` → Admin Dashboard (mit Token-Auth)
- `GET /admin/login` → Admin Loginseite
- `GET /api/status` → Poll Status
- `GET /api/admin/users` → User Liste
- `GET /api/admin/guilds` → Guild Liste
- `GET /api/admin/commands` → Command Logs

### System
- `GET /health` → Health Check für Railway
- `GET /healthz` → Alias für /health

## 🔧 Lokales Testing

```bash
# 1. Dependencies installieren
pip install -r requirements.txt

# 2. .env erstellen
cp .env.example .env
# → Editiere .env mit deinen Credentials

# 3. App starten
python app.py
# Oder für Production:
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app

# 4. Öffne im Browser
# → http://localhost:5000/
# → http://localhost:5000/admin
```

## 📊 App-Struktur

```
├── app.py                   # Main Entry Point (Railway/Gunicorn)
├── web_panel.py            # User Panel (Discord OAuth, Login)
├── admin_server.py         # Admin Dashboard (Token Auth)
├── panel.html              # User Panel UI
├── admin_panel.html        # Admin Panel UI
├── login.html              # Login Page
├── register.html           # Registration Page (falls vorhanden)
├── requirements.txt        # Python Dependencies
├── Procfile                # Railway Web Process
├── .env.example            # Umgebungsvariablen Template
└── README.md              # Diese Datei
```

## 🔐 Authentifizierung

### Admin Panel
- Token-basiert: Beim ersten Start wird `/admin/login?token=<TOKEN>` angezeigt
- Session-Cookies: Automatisch nach Login gespeichert

### User Panel
- Discord OAuth2: Benutzer loggen sich via Discord ein
- Panel-Passwort: Optional, für zusätzliche Sicherheit

## 🚨 Troubleshooting

### Panel lädt nicht
```
✅ Lösung: 
   1. Browser Debugger (F12) öffnen
   2. Console auf Fehler prüfen
   3. Network Tab → HTML-Dateien auf 404 prüfen
   4. Sicherstellen dass /panel.html neben app.py ist
```

### OAuth funktioniert nicht
```
✅ Prüfen:
   1. DISCORD_REDIRECT_URI stimmt mit Discord App überein
   2. DISCORD_CLIENT_ID / SECRET korrekt in .env
   3. Scope: identify, guilds.members.read
```

### Datenbanken sind leer nach Redeploy
```
⚠️  Wichtig: Railway-Container werden bei jedem Redeploy zurückgesetzt
   
   Lösungen:
   - Nutze Railway PostgreSQL / Persistent Storage
   - Oder implementiere backup in JSON-Datei zu externer Cloud
```

## 📝 Wichtige Notizen

- **Cold Starts**: Railway kann beim ersten Request langsam sein (Startup ~10s)
- **Persistent Storage**: Standard JSON-Dateien gehen beim Redeploy verloren
- **Gunicorn**: Nutzt 4 Worker für bessere Concurrency
- **Session Management**: Flask Session-Cookies sind HTTP-only & Secure

## 🔗 Hilfreiche Links

- [Railway Docs](https://docs.railway.app/)
- [Flask Docs](https://flask.palletsprojects.com/)
- [Discord.py Docs](https://discordpy.readthedocs.io/)
- [Gunicorn Docs](https://docs.gunicorn.org/)

---

**Version**: 3.0  
**Last Updated**: 2026-03-27  
**Status**: ✅ Production Ready for Railway
