"""
🚀 Main Entry Point für Railway Deployment
Nutzt Flask Blueprints statt Route-Merge
"""

import os
import sys
import secrets
from flask import Flask, jsonify
from flask_cors import CORS

# ─────────────────────────────────────────────────────────────
#  Eine einzige Flask-App, ein einziger secret_key
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)

# SECRET_KEY MUSS in Railway Variables gesetzt sein — sonst werden
# Sessions bei jedem Redeploy ungültig!
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    print("[WARN] ⚠️  SECRET_KEY nicht gesetzt! Sessions überleben keinen Neustart.")
    print("[WARN]    Railway Variables → SECRET_KEY = <zufälliger langer String>")
    secret_key = secrets.token_hex(32)
app.secret_key = secret_key

# Session-Cookies: 7 Tage
from datetime import timedelta
app.permanent_session_lifetime = timedelta(days=7)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_NAME="amogus_sess",
)

CORS(app, supports_credentials=True)

# ─────────────────────────────────────────────────────────────
#  Blueprints registrieren
# ─────────────────────────────────────────────────────────────

print("[STARTUP] Laden der Module...")

try:
    from web_panel_bp import web_bp
    app.register_blueprint(web_bp)
    print("[STARTUP] ✅ web_panel Blueprint geladen")
except Exception as e:
    print(f"[ERROR] web_panel_bp: {e}")
    sys.exit(1)

try:
    from admin_server_bp import admin_bp
    app.register_blueprint(admin_bp)
    print("[STARTUP] ✅ admin_server Blueprint geladen")
except Exception as e:
    print(f"[ERROR] admin_server_bp: {e}")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
#  Health Check für Railway
# ─────────────────────────────────────────────────────────────

@app.route("/healthz")
@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "Among Us Panel",
        "version": "3.1"
    }), 200

# ─────────────────────────────────────────────────────────────
#  Fehlerbehandlung
# ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not Found"}), 404

@app.errorhandler(500)
def server_error(error):
    print(f"[ERROR] 500: {error}", file=sys.stderr)
    return jsonify({"error": "Internal Server Error"}), 500

# ─────────────────────────────────────────────────────────────
#  Local Development
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
