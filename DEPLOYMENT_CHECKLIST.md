# 🚀 Railway Deployment Checklist

## ✅ Lokales Testing VOR Railway

- [ ] Git Repository erstellt: `git init`
- [ ] Alle Dateien committed: `git add . && git commit -m "Initial commit"`
- [ ] Python Dependencies lokal installiert:
  ```bash
  pip install -r requirements.txt
  ```
- [ ] `.env` Datei erstellt (basierend auf `.env.example`):
  ```bash
  cp .env.example .env
  # Fülle JETZT alle Discord Credentials aus!
  ```
- [ ] Lokale Tests erfolgreich:
  ```bash
  python app.py
  # Öffne http://localhost:5000/ im Browser
  ```
- [ ] Admin Panel erreichbar:
  ```
  http://localhost:5000/admin/login
  ```
- [ ] Login/Register Pages laden (nicht 404):
  ```
  http://localhost:5000/login
  http://localhost:5000/register
  ```

## 🔑 Discord App konfigurieren (WICHTIG!)

1. Gehe zu [Discord Developer Portal](https://discord.com/developers/applications)
2. Erstelle neue App oder öffne bestehende
3. Kopiere **Client ID** und **Client Secret** zu `.env`:
   ```
   DISCORD_CLIENT_ID=<Copy here>
   DISCORD_CLIENT_SECRET=<Copy here>
   ```
4. Gehe zu **OAuth2 → URL Generator**
   - Scopes: `identify`, `guilds.members.read`
   - Permissions: (keine nötig für User Panel)
5. Gehe zu **OAuth2 → Redirects**
   - JETZT: `http://localhost:3000/auth/callback` (für lokales Testing)
   - Später bei Railway: `https://<your-app>.up.railway.app/auth/callback`

## 🌐 Railway Setup

### Schritt 1: GitHub verbinden
- [ ] Alle Dateien auf GitHub pushen:
  ```bash
  git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
  git branch -M main
  git push -u origin main
  ```
- [ ] [Railway Dashboard](https://railway.app/) öffnen
- [ ] "New Project" → "Deploy from GitHub"
- [ ] Repository auswählen

### Schritt 2: Environment Variables setzen

Im Railway Dashboard → **Variables** Tab, füge folgende hinzu:

```
DISCORD_TOKEN=xxx_your_bot_token_xxx
DISCORD_CLIENT_ID=xxx_oauth_client_id_xxx
DISCORD_CLIENT_SECRET=xxx_oauth_secret_xxx
DISCORD_GUILD_ID=xxx_your_server_id_xxx
DISCORD_REDIRECT_URI=https://your-app-name.up.railway.app/auth/callback
ADMIN_TOKEN=generate_something_secure_like_this_abc123XYZ
INVITE_CODE=your_secret_code_if_you_use_one
SECRET_KEY=(leer lassen = wird automatisch generiert)
```

⚠️ **WICHTIG**: Die `DISCORD_REDIRECT_URI` MUSS automatisch gemampfit werden von Railway!
Sobald Railway dir einen Domain-Namen gibt (z.B. `my-app-abc123.up.railway.app`), nutze: `https://my-app-abc123.up.railway.app/auth/callback`

### Schritt 3: Prozess starten

- [ ] Railway führt automatisch aus:
  1. `pip install -r requirements.txt`
  2. Kommando aus `Procfile`: `gunicorn --workers 4 --worker-class sync --bind 0.0.0.0:$PORT app:app`
- [ ] Logs prüfen auf Fehler

### Schritt 4: Domain konfigurieren

- [ ] Railway generiert automatisch Domain: `your-app-xyz.up.railway.app`
- [ ] Kopiere diese URL
- [ ] Aktualisiere auf deinem Discord Developer Portal:
  - **OAuth2 → Redirects**: `https://your-app-xyz.up.railway.app/auth/callback`

## 🧪 Nach dem Deployment

- [ ] Health-Check: Öffne `https://your-app.up.railway.app/health`
  - Sollte grünes OK zurückgeben
- [ ] Hauptseite laden: `https://your-app.up.railway.app/`
- [ ] Login Page: `https://your-app.up.railway.app/login`
- [ ] Admin Panel: `https://your-app.up.railway.app/admin/login`
  - Mit Token: `https://your-app.up.railway.app/admin/login?token=<ADMIN_TOKEN>`

## 🔴 Häufige Fehler

### ❌ 502 Bad Gateway
**Ursache**: Gunicorn startet nicht
```
☑ Lösung: 
1. Prüfe `requirements.txt` - alle Packages installiert?
2. Prüfe Logs im Railway Dashboard
3. Starte neu: Railway → Restart Deploy
```

### ❌ 404 Beim Login
**Ursache**: `login.html`, `register.html` nicht gefunden
```
☑ Lösung:
1. Prüfe: Sind login.html + register.html im Repo?
2. Pushe neu: git add . && git commit && git push
3. Starte Railway Deployment neu
```

### ❌ Discord OAuth funktioniert nicht
**Ursache**: Redirect URI stimmt nicht
```
☑ Lösung:
1. Railway Domain kopieren: z.B. my-app-abc.up.railway.app
2. Discord Developer Portal öffnen
3. OAuth2 → Redirects → Ändern zu:
   https://my-app-abc.up.railway.app/auth/callback
4. Reusertest
```

### ❌ 403 "Sie sind nicht auf dem Server"
**Ursache**: DISCORD_GUILD_ID ist falsch oder User nicht im Server
```
☑ Lösung:
1. Prüfe Guild ID: Rechtsklick auf Server (Discord) → Server ID kopieren
2. Railway Variable aktualisieren
3. Oder: DISCORD_GUILD_ID leer lassen → keine Guild-Überprüfung
```

### ❌ Admin Token funktioniert nicht
**Ursache**: Token ist falscher String
```
☑ Lösung:
1. Erstelle neuen Token: python -c "import secrets; print(secrets.token_urlsafe(32))"
2. Kopiere Output
3. Railway → Variables → ADMIN_TOKEN = [paste]
4. Schreib dir den Token auf - wird nicht angezeigt!
```

## 💾 Daten Persistenz auf Railway

**Problem**: JSON-Dateien gehen beim Redeploy verloren!

### Lösung 1: Railway PostgreSQL (empfohlen)
```bash
# Railway Dashboard:
# 1. New Service → PostgreSQL
# 2. Railway generiert DATABASE_URL automatisch
# 3. Code anpassen um Daten in DB zu speichern (komplexer)
```

### Lösung 2: Persistent Storage
```bash
# Railway Dashboard:
# 1. Storage Tab → New Volume
# 2. Mount Path: /app/data
# 3. Alle .json Dateien davon speichern
```

### Lösung 3: Externe Cloud (einfachste)
```python
# Mit Google Drive / AWS S3 / etc
# Alle 5 Minuten Backup hochladen
```

## 🤝 Support & Links

- [Railway Docs](https://docs.railway.app/)
- [Flask Deployment](https://flask.palletsprojects.com/deployment/)
- [Discord OAuth Guide](https://discord.com/developers/docs/topics/oauth2)
- [Gunicorn Docs](https://docs.gunicorn.org/)

## 📝 Fortschritt Tracker

```
Status: ○ Geplant | ⚙️  In Bearbeitung | ✅ Fertig

Lokales Setup:
  ○ Python 3.8+ installiert
  ○ requirements.txt Packages installiert
  ○ .env erstellt & ausgefüllt
  ○ Lokale Tests bestanden

Discord Setup:
  ○ Developer Application erstellt
  ○ OAuth2 Credentials kopiert
  ○ Redirect URIs konfiguriert
  ○ Bot lädt Serve richtig

Railway Setup:
  ○ GitHub Repository öffentlich/privat
  ○ Railway Project erstellt
  ○ Environment Variables gesetzt
  ○ Deploy erfolgreich
  ○ Domain & Redirect URI aktualisiert
  ○ Funktioniert in Production!
```

---

**Last Updated**: 2026-03-27  
**Version**: 3.0  
✅ **Ready for Production**
