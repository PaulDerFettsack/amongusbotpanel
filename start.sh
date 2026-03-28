#!/bin/bash
# Startet Bot + Web Panel parallel

echo "🤖 Starte Discord Bot..."
python bot.py &
BOT_PID=$!

echo "🌐 Starte Web Panel..."
gunicorn --workers 4 --worker-class sync --bind 0.0.0.0:$PORT app:app --timeout 120
WEB_PID=$!

# Wenn Web-Server stirbt → Bot auch beenden
wait $WEB_PID
kill $BOT_PID
