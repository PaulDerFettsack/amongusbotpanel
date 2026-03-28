#!/bin/bash
# 🚀 Among Us — Startet Bot + Web Panel parallel

echo "🤖 Starte Discord Bot..."
python bot.py &
BOT_PID=$!

echo "🌐 Starte Web Panel..."
exec gunicorn --workers 4 --worker-class sync --bind 0.0.0.0:$PORT app:app --timeout 120

# Wenn Gunicorn stirbt → Bot auch beenden
kill $BOT_PID 2>/dev/null
