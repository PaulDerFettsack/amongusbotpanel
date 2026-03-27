"""
🚀 Main Entry Point für Railway Deployment
Kombiniert beide Flask-Apps mit gemeinsamen Assets
"""

import os
import sys
from flask import Flask, jsonify, redirect, send_from_directory
from flask_cors import CORS

# ─────────────────────────────────────────────────────────────
#  Initialisiere Hauptapp
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", __import__('secrets').token_hex(32))
CORS(app, supports_credentials=True)

# ─────────────────────────────────────────────────────────────
#  Importiere beide Module 
# ─────────────────────────────────────────────────────────────

print("[STARTUP] Laden der Module...")
try:
    # Importiere die Blueprints/Apps
    from web_panel import app as web_app_instance
    from admin_server import app as admin_app_instance
    print("[STARTUP] ✅ web_panel geladen")
    print("[STARTUP] ✅ admin_server geladen")
except Exception as e:
    print(f"[ERROR] Fehler beim Importieren: {e}")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
#  Merge alle Routes in die Hauptapp
# ─────────────────────────────────────────────────────────────

def merge_app_routes(source_app, target_app, url_prefix=""):
    """Kopiert alle Routes von source_app zu target_app"""
    for rule in source_app.url_map.iter_rules():
        if rule.endpoint.startswith('static'):
            continue  # Überspringe statische Dateien
        
        # Hole den Endpoint-Handler
        endpoint = rule.endpoint
        view_func = source_app.view_functions.get(endpoint)
        
        if view_func and endpoint not in target_app.view_functions:
            # Registriere die Route in der Ziel-App
            methods = list(rule.methods - {'HEAD', 'OPTIONS'})
            rule_str = url_prefix + rule.rule if url_prefix else rule.rule
            try:
                target_app.add_url_rule(
                    rule_str, 
                    endpoint, 
                    view_func, 
                    methods=methods
                )
            except Exception as e:
                print(f"[WARN] Route-Merge fehlgeschlagen: {endpoint} - {e}")

# Merge web_panel Routes (sind hauptsächlich)
merge_app_routes(web_app_instance, app)

# Merge admin_server Routes 
merge_app_routes(admin_app_instance, app)

print("[STARTUP] ✅ Alle Routes registriert")

# ─────────────────────────────────────────────────────────────
#  Health Check für Railway
# ─────────────────────────────────────────────────────────────

@app.route("/healthz")
@app.route("/health")
def health():
    """Health-Check Endpoint für Railway"""
    return jsonify({
        "status": "healthy",
        "service": "Among Us Panel",
        "version": "3.0"
    }), 200

# ─────────────────────────────────────────────────────────────
#  Catch-All & Fehlerbehandlung
# ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error):
    """Zeige verfügbare Endpoints bei 404"""
    return jsonify({
        "error": "Not Found",
        "routes": [
            "/",
            "/admin",
            "/login",
            "/register",
            "/health"
        ]
    }), 404

@app.errorhandler(500)
def server_error(error):
    """Fehlerbehandlung für 500er"""
    print(f"[ERROR] 500: {error}", file=sys.stderr)
    return jsonify({"error": "Internal Server Error"}), 500

# ─────────────────────────────────────────────────────────────
#  Local Development
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║  🚀 Among Us Panel — Production Server                   ║
╠═══════════════════════════════════════════════════════════╣
║  🌐 http://localhost:{port:<45}  ║
║  📊 /                      (Main Panel)                   ║
║  🔐 /admin                 (Admin Console)                ║
║  ❤️  /health               (Health Check)                 ║
╚═══════════════════════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
