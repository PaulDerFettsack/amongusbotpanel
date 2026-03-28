"""
🚀 Among Us Discord Bot
========================
Slash Commands:
  /amogus start       — Startet Tagesumfrage im aktuellen Kanal
  /amogus stop        — Schließt Umfrage + postet Zusammenfassung
  /amogus reset       — Setzt alles zurück
  /amogus status      — Zeigt aktuellen Stand
  /amogus uhrzeit HH:MM — Setzt Spielzeit

Buttons (auf der Umfragenanricht):
  ✅ Pünktlich | 🕒 Später (mit Uhrzeit-Modal) | ❌ Abwesend

Automatisch:
  - 15 min vor Spielstart: Erinnerung posten
  - 5 min vor Spielstart: Zusammenfassung posten
  - Polling alle 5s: pending_action aus amogus_data.json ausführen

Env-Variablen:
  DISCORD_TOKEN   = Bot-Token
  DISCORD_GUILD_ID = (optional) Standard-Guild
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import json, os, asyncio, re
from datetime import datetime, date, timedelta
import pytz
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────

TOKEN      = os.environ.get("DISCORD_TOKEN", "")
TIMEZONE   = pytz.timezone("Europe/Berlin")
DATA_FILE  = "amogus_data.json"
LOG_FILE   = "amogus_logs.json"

if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN fehlt in .env / Railway Variables!")

# ─────────────────────────────────────────────────────────────
#  Data helpers — thread-safe JSON lesen/schreiben
# ─────────────────────────────────────────────────────────────

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_logs() -> dict:
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"commands": [], "users": {}, "guilds": {}}

def save_logs(logs: dict):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def today_str() -> str:
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")

def now_str() -> str:
    return datetime.now(TIMEZONE).isoformat()

# ─────────────────────────────────────────────────────────────
#  Logging helpers
# ─────────────────────────────────────────────────────────────

def log_command(user: discord.User | discord.Member, guild: discord.Guild | None, action: str, params: str = ""):
    logs = load_logs()
    uid  = str(user.id)
    gid  = str(guild.id) if guild else "dm"

    # Command log
    logs.setdefault("commands", []).append({
        "ts":       now_str(),
        "user_id":  uid,
        "username": user.name,
        "display":  user.display_name,
        "guild_id": gid,
        "action":   action,
        "params":   params,
    })
    # Keep only last 500
    logs["commands"] = logs["commands"][-500:]

    # User stats
    users = logs.setdefault("users", {})
    if uid not in users:
        users[uid] = {
            "user_id":       uid,
            "username":      user.name,
            "display":       user.display_name,
            "avatar_url":    str(user.display_avatar.url) if user.display_avatar else "",
            "first_seen":    now_str(),
            "last_seen":     now_str(),
            "guilds":        [],
            "total_games":   0,
            "on_time_count": 0,
            "late_count":    0,
            "absent_count":  0,
            "command_count": 0,
            "vote_history":  [],
        }
    u = users[uid]
    u["last_seen"]     = now_str()
    u["username"]      = user.name
    u["display"]       = user.display_name
    u["avatar_url"]    = str(user.display_avatar.url) if user.display_avatar else u.get("avatar_url","")
    u["command_count"] = u.get("command_count", 0) + 1
    if gid not in u.get("guilds", []):
        u.setdefault("guilds", []).append(gid)

    # Guild stats
    guilds = logs.setdefault("guilds", {})
    if guild:
        if gid not in guilds:
            guilds[gid] = {
                "guild_id":      gid,
                "guild_name":    guild.name,
                "member_count":  guild.member_count,
                "first_seen":    now_str(),
                "last_activity": now_str(),
                "total_polls":   0,
                "total_commands":0,
                "daily_stats":   {},
            }
        g = guilds[gid]
        g["last_activity"]   = now_str()
        g["guild_name"]      = guild.name
        g["total_commands"]  = g.get("total_commands", 0) + 1
        # Daily stats
        td = today_str()
        g.setdefault("daily_stats", {}).setdefault(td, {"votes": 0, "commands": 0})
        g["daily_stats"][td]["commands"] += 1

    save_logs(logs)

def log_vote(user: discord.User | discord.Member, guild: discord.Guild | None,
             vote: str, poll_id: str, game_time: str):
    """Loggt eine Abstimmung und aktualisiert User-Statistiken."""
    logs = load_logs()
    uid  = str(user.id)
    gid  = str(guild.id) if guild else "dm"

    users = logs.setdefault("users", {})
    if uid not in users:
        users[uid] = {
            "user_id": uid, "username": user.name, "display": user.display_name,
            "avatar_url": str(user.display_avatar.url) if user.display_avatar else "",
            "first_seen": now_str(), "last_seen": now_str(),
            "guilds": [], "total_games": 0,
            "on_time_count": 0, "late_count": 0, "absent_count": 0,
            "command_count": 0, "vote_history": [],
        }
    u = users[uid]
    u["last_seen"] = now_str()

    # Vote history (max 50)
    u.setdefault("vote_history", []).append({
        "ts": now_str(), "vote": vote, "poll_id": poll_id, "game_time": game_time
    })
    u["vote_history"] = u["vote_history"][-50:]

    # Count stats (only count new votes, not changes — handled by caller)
    if vote == "on_time":
        u["on_time_count"] = u.get("on_time_count", 0) + 1
    elif vote == "late":
        u["late_count"] = u.get("late_count", 0) + 1
    elif vote == "absent":
        u["absent_count"] = u.get("absent_count", 0) + 1

    if gid not in u.get("guilds", []):
        u.setdefault("guilds", []).append(gid)

    # Guild daily stats
    if guild:
        guilds = logs.setdefault("guilds", {})
        g = guilds.setdefault(gid, {
            "guild_id": gid, "guild_name": guild.name, "member_count": guild.member_count,
            "first_seen": now_str(), "last_activity": now_str(),
            "total_polls": 0, "total_commands": 0, "daily_stats": {},
        })
        td = today_str()
        g.setdefault("daily_stats", {}).setdefault(td, {"votes": 0, "commands": 0})
        g["daily_stats"][td]["votes"] += 1
        g["last_activity"] = now_str()

    save_logs(logs)

# ─────────────────────────────────────────────────────────────
#  Embed Builder
# ─────────────────────────────────────────────────────────────

def build_poll_embed(gd: dict, guild_id: str) -> discord.Embed:
    """Baut das Hauptembed für die Umfrage."""
    parts    = gd.get("participants", {"on_time": [], "late": {}, "absent": []})
    on_time  = parts.get("on_time", [])
    late     = parts.get("late", {})
    absent   = parts.get("absent", [])
    gh, gm   = gd.get("game_hour", 20), gd.get("game_minute", 0)
    game_time= f"{gh:02d}:{gm:02d}"
    poll_date= gd.get("date", today_str())
    closed   = gd.get("closed", False)
    total    = len(on_time) + len(late)

    color = discord.Color.green() if total >= 4 else discord.Color.yellow() if total >= 1 else discord.Color.red()
    if closed:
        color = discord.Color.greyple()

    embed = discord.Embed(
        title=f"{'🔒 ' if closed else '🚀 '}Among Us — {poll_date}",
        description=f"**Spielstart: {game_time} Uhr** {'🔒 Umfrage geschlossen' if closed else '● Abstimmung läuft'}",
        color=color,
    )

    # On time
    if on_time:
        names = "\n".join(f"✅ <@{uid}>" for uid in on_time)
    else:
        names = "*Noch niemand*"
    embed.add_field(name=f"✅ Pünktlich ({len(on_time)})", value=names, inline=True)

    # Late
    if late:
        names = "\n".join(
            f"🕒 <@{uid}> — {t if t != '?' else 'ausstehend'}"
            for uid, t in late.items()
        )
    else:
        names = "*Niemand*"
    embed.add_field(name=f"🕒 Kommt später ({len(late)})", value=names, inline=True)

    # Absent
    if absent:
        names = "\n".join(f"❌ <@{uid}>" for uid in absent)
    else:
        names = "*Niemand*"
    embed.add_field(name=f"❌ Abwesend ({len(absent)})", value=names, inline=False)

    embed.add_field(
        name="👨‍🚀 Gesamt",
        value=f"**{total}** Spieler {'✅ Genug!' if total >= 4 else '⚠️ Zu wenig'}",
        inline=True
    )
    embed.set_footer(text=f"Poll ID: {gd.get('poll_id','—')} • Panel: /admin")
    return embed

def build_summary_embed(gd: dict) -> discord.Embed:
    """Baut das Zusammenfassungs-Embed."""
    parts   = gd.get("participants", {"on_time": [], "late": {}, "absent": []})
    on_time = parts.get("on_time", [])
    late    = parts.get("late", {})
    absent  = parts.get("absent", [])
    gh, gm  = gd.get("game_hour", 20), gd.get("game_minute", 0)
    total   = len(on_time) + len(late)

    embed = discord.Embed(
        title=f"📊 Among Us — Zusammenfassung",
        description=f"Spielstart: **{gh:02d}:{gm:02d} Uhr** • {total} Spieler",
        color=discord.Color.green() if total >= 4 else discord.Color.red(),
    )

    players = []
    for uid in on_time:
        players.append(f"✅ <@{uid}>")
    for uid, t in late.items():
        players.append(f"🕒 <@{uid}> ({t if t != '?' else '?'})")

    embed.add_field(
        name=f"🎮 Spieler ({total})",
        value="\n".join(players) if players else "*Niemand*",
        inline=False,
    )
    if absent:
        embed.add_field(
            name=f"❌ Abwesend ({len(absent)})",
            value="\n".join(f"<@{uid}>" for uid in absent),
            inline=False,
        )

    if total >= 4:
        embed.add_field(name="✅ Status", value="**Genug Spieler — Spiel kann starten!**", inline=False)
    else:
        embed.add_field(name="⚠️ Status", value=f"**Nur {total} Spieler — zu wenig!**", inline=False)

    return embed

# ─────────────────────────────────────────────────────────────
#  View (Buttons)
# ─────────────────────────────────────────────────────────────

class PollView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # persistent

    @discord.ui.button(label="✅ Pünktlich", style=discord.ButtonStyle.success, custom_id="vote_on_time")
    async def vote_on_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_vote(interaction, "on_time", None)

    @discord.ui.button(label="🕒 Komme später", style=discord.ButtonStyle.primary, custom_id="vote_late")
    async def vote_late(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LateTimeModal())

    @discord.ui.button(label="❌ Abwesend", style=discord.ButtonStyle.danger, custom_id="vote_absent")
    async def vote_absent(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_vote(interaction, "absent", None)


class LateTimeModal(discord.ui.Modal, title="Um wie viel Uhr kommst du?"):
    time_input = discord.ui.TextInput(
        label="Uhrzeit (z.B. 20:45)",
        placeholder="HH:MM",
        max_length=5,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        val = self.time_input.value.strip()
        if not re.match(r"^\d{1,2}:\d{2}$", val):
            await interaction.response.send_message("❌ Format: HH:MM (z.B. 20:45)", ephemeral=True)
            return
        h, m = map(int, val.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            await interaction.response.send_message("❌ Ungültige Uhrzeit", ephemeral=True)
            return
        await handle_vote(interaction, "late", f"{h:02d}:{m:02d}")

# ─────────────────────────────────────────────────────────────
#  Vote handler
# ─────────────────────────────────────────────────────────────

async def handle_vote(interaction: discord.Interaction, vote_type: str, late_time: str | None):
    gid  = str(interaction.guild_id)
    uid  = str(interaction.user.id)
    data = load_data()

    if gid not in data:
        await interaction.response.send_message("❌ Keine aktive Umfrage.", ephemeral=True)
        return

    gd = data[gid]
    if gd.get("closed"):
        await interaction.response.send_message("🔒 Die Umfrage ist bereits geschlossen.", ephemeral=True)
        return

    parts = gd.setdefault("participants", {"on_time": [], "late": {}, "absent": []})
    parts.setdefault("on_time", [])
    parts.setdefault("late",    {})
    parts.setdefault("absent",  [])

    # Remove from all lists first
    old_vote = None
    if uid in parts["on_time"]:
        parts["on_time"].remove(uid)
        old_vote = "on_time"
    if uid in parts["late"]:
        del parts["late"][uid]
        old_vote = "late"
    if uid in parts["absent"]:
        parts["absent"].remove(uid)
        old_vote = "absent"

    # Add to new list
    if vote_type == "on_time":
        parts["on_time"].append(uid)
    elif vote_type == "late":
        parts["late"][uid] = late_time or "?"
    elif vote_type == "absent":
        parts["absent"].append(uid)

    save_data(data)

    # Log vote (only new votes, not changes count)
    gh, gm = gd.get("game_hour", 20), gd.get("game_minute", 0)
    game_time = f"{gh:02d}:{gm:02d}"
    if old_vote != vote_type:
        log_vote(interaction.user, interaction.guild, vote_type, gd.get("poll_id",""), game_time)

    # Update the poll message
    await update_poll_message(interaction.guild, gid)

    # Respond
    msgs = {
        "on_time": "✅ Du bist als **pünktlich** eingetragen!",
        "late":    f"🕒 Du bist als **später** eingetragen ({late_time} Uhr)!",
        "absent":  "❌ Du bist als **abwesend** eingetragen.",
    }
    await interaction.response.send_message(msgs[vote_type], ephemeral=True)

# ─────────────────────────────────────────────────────────────
#  Poll message updater
# ─────────────────────────────────────────────────────────────

async def update_poll_message(guild: discord.Guild, guild_id: str):
    """Aktualisiert die Umfragenachricht im Discord."""
    data = load_data()
    gd   = data.get(guild_id)
    if not gd:
        return

    msg_id = gd.get("poll_message_id")
    ch_id  = gd.get("channel_id")
    if not msg_id or not ch_id:
        return

    try:
        channel = guild.get_channel(int(ch_id))
        if not channel:
            channel = await guild.fetch_channel(int(ch_id))
        msg = await channel.fetch_message(int(msg_id))
        embed = build_poll_embed(gd, guild_id)
        view  = PollView() if not gd.get("closed") else discord.ui.View()
        await msg.edit(embed=embed, view=view)
    except Exception as e:
        print(f"[Bot] update_poll_message fehler: {e}")

# ─────────────────────────────────────────────────────────────
#  Bot Setup
# ─────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ─────────────────────────────────────────────────────────────
#  Slash Commands
# ─────────────────────────────────────────────────────────────

amogus_group = app_commands.Group(name="amogus", description="Among Us Bot Befehle")

@amogus_group.command(name="start", description="Startet die Tagesumfrage")
async def cmd_start(interaction: discord.Interaction):
    gid  = str(interaction.guild_id)
    data = load_data()
    log_command(interaction.user, interaction.guild, "start")

    gd = data.setdefault(gid, {
        "game_hour":   20,
        "game_minute": 0,
        "participants": {"on_time": [], "late": {}, "absent": []},
        "reminder_sent": False,
        "summary_sent":  False,
        "closed":        False,
    })

    # Reset für heute
    if gd.get("date") == today_str() and gd.get("poll_message_id"):
        await interaction.response.send_message(
            "⚠️ Es gibt bereits eine aktive Umfrage für heute! Nutze `/amogus reset` um sie zurückzusetzen.",
            ephemeral=True
        )
        return

    gh, gm = gd.get("game_hour", 20), gd.get("game_minute", 0)
    import uuid
    poll_id = str(uuid.uuid4())[:8].upper()

    gd.update({
        "date":          today_str(),
        "poll_id":       poll_id,
        "channel_id":    str(interaction.channel_id),
        "participants":  {"on_time": [], "late": {}, "absent": []},
        "reminder_sent": False,
        "summary_sent":  False,
        "closed":        False,
        "pending_action": None,
    })
    save_data(data)

    embed = build_poll_embed(gd, gid)
    view  = PollView()

    await interaction.response.send_message(embed=embed, view=view)
    msg = await interaction.original_response()

    # Save message ID
    data = load_data()
    data[gid]["poll_message_id"] = str(msg.id)
    save_data(data)

    # Log guild poll count
    logs = load_logs()
    guilds = logs.setdefault("guilds", {})
    if gid in guilds:
        guilds[gid]["total_polls"] = guilds[gid].get("total_polls", 0) + 1
        save_logs(logs)

    print(f"[Bot] Umfrage gestartet — Guild {gid} | Poll {poll_id}")


@amogus_group.command(name="stop", description="Schließt die Umfrage und postet Zusammenfassung")
async def cmd_stop(interaction: discord.Interaction):
    gid  = str(interaction.guild_id)
    data = load_data()
    log_command(interaction.user, interaction.guild, "stop")

    gd = data.get(gid)
    if not gd or not gd.get("poll_message_id"):
        await interaction.response.send_message("❌ Keine aktive Umfrage gefunden.", ephemeral=True)
        return

    if gd.get("closed"):
        await interaction.response.send_message("🔒 Umfrage ist bereits geschlossen.", ephemeral=True)
        return

    gd["closed"]       = True
    gd["summary_sent"] = True
    save_data(data)

    # Update original message
    await update_poll_message(interaction.guild, gid)

    # Post summary
    embed = build_summary_embed(gd)
    await interaction.response.send_message(embed=embed)
    print(f"[Bot] Umfrage geschlossen — Guild {gid}")


@amogus_group.command(name="reset", description="Setzt die Umfrage komplett zurück")
async def cmd_reset(interaction: discord.Interaction):
    gid  = str(interaction.guild_id)
    data = load_data()
    log_command(interaction.user, interaction.guild, "reset")

    if gid in data:
        for k in ("poll_message_id", "channel_id", "date", "poll_id"):
            data[gid].pop(k, None)
        data[gid].update({
            "participants":  {"on_time": [], "late": {}, "absent": []},
            "reminder_sent": False,
            "summary_sent":  False,
            "closed":        False,
            "pending_action": None,
        })
        save_data(data)

    await interaction.response.send_message("🔄 Umfrage zurückgesetzt! Nutze `/amogus start` für eine neue.", ephemeral=True)


@amogus_group.command(name="status", description="Zeigt den aktuellen Abstimmungsstand")
async def cmd_status(interaction: discord.Interaction):
    gid  = str(interaction.guild_id)
    data = load_data()
    log_command(interaction.user, interaction.guild, "status")

    gd = data.get(gid)
    if not gd or not gd.get("date"):
        await interaction.response.send_message("❌ Keine aktive Umfrage.", ephemeral=True)
        return

    embed = build_poll_embed(gd, gid)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@amogus_group.command(name="uhrzeit", description="Setzt die Spielzeit")
@app_commands.describe(zeit="Spielzeit im Format HH:MM, z.B. 20:30")
async def cmd_uhrzeit(interaction: discord.Interaction, zeit: str):
    gid  = str(interaction.guild_id)
    data = load_data()
    log_command(interaction.user, interaction.guild, "uhrzeit", zeit)

    if not re.match(r"^\d{1,2}:\d{2}$", zeit):
        await interaction.response.send_message("❌ Format: HH:MM (z.B. 20:30)", ephemeral=True)
        return

    h, m = map(int, zeit.split(":"))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        await interaction.response.send_message("❌ Ungültige Uhrzeit", ephemeral=True)
        return

    data.setdefault(gid, {})
    data[gid]["game_hour"]   = h
    data[gid]["game_minute"] = m
    save_data(data)

    # Update poll message if active
    if data[gid].get("poll_message_id"):
        await update_poll_message(interaction.guild, gid)

    await interaction.response.send_message(f"✅ Spielzeit auf **{h:02d}:{m:02d} Uhr** gesetzt!", ephemeral=True)


@amogus_group.command(name="hilfe", description="Zeigt alle Befehle")
async def cmd_hilfe(interaction: discord.Interaction):
    log_command(interaction.user, interaction.guild, "hilfe")
    embed = discord.Embed(
        title="🚀 Among Us Bot — Hilfe",
        color=discord.Color.blue(),
    )
    embed.add_field(name="/amogus start",           value="Startet die Tagesumfrage",              inline=False)
    embed.add_field(name="/amogus stop",            value="Schließt Umfrage + postet Summary",     inline=False)
    embed.add_field(name="/amogus reset",           value="Setzt alles zurück",                    inline=False)
    embed.add_field(name="/amogus status",          value="Zeigt aktuellen Stand (nur für dich)",  inline=False)
    embed.add_field(name="/amogus uhrzeit HH:MM",   value="Setzt die Spielzeit",                   inline=False)
    embed.add_field(name="Panel",                   value="Echtzeit-Übersicht: /panel",            inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ─────────────────────────────────────────────────────────────
#  Background Tasks
# ─────────────────────────────────────────────────────────────

@tasks.loop(seconds=5)
async def poll_pending_actions():
    """Prüft alle 5s ob das Panel eine Aktion angefordert hat."""
    try:
        data = load_data()
        changed = False
        for gid, gd in data.items():
            action = gd.get("pending_action")
            if not action:
                continue

            guild = bot.get_guild(int(gid))
            if not guild:
                continue

            print(f"[Bot] Pending action: {action} für Guild {gid}")

            if action == "update_poll_message":
                await update_poll_message(guild, gid)

            elif action == "close_poll":
                if not gd.get("closed"):
                    gd["closed"]       = True
                    gd["summary_sent"] = True
                    await update_poll_message(guild, gd)
                    # Post summary in channel
                    ch_id = gd.get("channel_id")
                    if ch_id:
                        try:
                            channel = guild.get_channel(int(ch_id))
                            if not channel:
                                channel = await guild.fetch_channel(int(ch_id))
                            embed = build_summary_embed(gd)
                            await channel.send(embed=embed)
                        except Exception as e:
                            print(f"[Bot] Summary senden fehler: {e}")

            gd["pending_action"] = None
            changed = True

        if changed:
            save_data(data)
    except Exception as e:
        print(f"[Bot] poll_pending_actions fehler: {e}")


@tasks.loop(minutes=1)
async def check_reminders():
    """Prüft jede Minute ob Erinnerung oder Zusammenfassung gepostet werden soll."""
    try:
        now  = datetime.now(TIMEZONE)
        data = load_data()
        changed = False

        for gid, gd in data.items():
            if gd.get("date") != today_str():
                continue
            if gd.get("closed"):
                continue

            guild = bot.get_guild(int(gid))
            if not guild:
                continue

            ch_id = gd.get("channel_id")
            if not ch_id:
                continue

            gh = gd.get("game_hour", 20)
            gm = gd.get("game_minute", 0)
            game_dt = now.replace(hour=gh, minute=gm, second=0, microsecond=0)

            # Erinnerung: 15 min vorher
            reminder_dt = game_dt - timedelta(minutes=15)
            if (not gd.get("reminder_sent")
                    and now >= reminder_dt
                    and now < game_dt):
                try:
                    channel = guild.get_channel(int(ch_id))
                    if not channel:
                        channel = await guild.fetch_channel(int(ch_id))

                    parts   = gd.get("participants", {})
                    on_time = parts.get("on_time", [])
                    late    = parts.get("late", {})
                    total   = len(on_time) + len(late)

                    mentions = " ".join(f"<@{uid}>" for uid in on_time + list(late.keys()))

                    embed = discord.Embed(
                        title="⏰ Erinnerung — Among Us startet bald!",
                        description=f"**{gh:02d}:{gm:02d} Uhr** — noch 15 Minuten!\n\n{mentions if mentions else '*Noch niemand eingetragen!*'}",
                        color=discord.Color.yellow(),
                    )
                    embed.add_field(name="👨‍🚀 Spieler", value=str(total), inline=True)
                    embed.add_field(name="Status", value="✅ Genug!" if total >= 4 else "⚠️ Zu wenig!", inline=True)
                    await channel.send(embed=embed)

                    gd["reminder_sent"] = True
                    changed = True
                    print(f"[Bot] Erinnerung gesendet — Guild {gid}")
                except Exception as e:
                    print(f"[Bot] Erinnerung fehler: {e}")

            # Zusammenfassung: 5 min vorher
            summary_dt = game_dt - timedelta(minutes=5)
            if (not gd.get("summary_sent")
                    and now >= summary_dt
                    and now < game_dt):
                try:
                    channel = guild.get_channel(int(ch_id))
                    if not channel:
                        channel = await guild.fetch_channel(int(ch_id))

                    gd["closed"]       = True
                    gd["summary_sent"] = True
                    changed = True

                    await update_poll_message(guild, gid)
                    embed = build_summary_embed(gd)
                    await channel.send(embed=embed)
                    print(f"[Bot] Zusammenfassung gesendet — Guild {gid}")
                except Exception as e:
                    print(f"[Bot] Zusammenfassung fehler: {e}")

        if changed:
            save_data(data)
    except Exception as e:
        print(f"[Bot] check_reminders fehler: {e}")

# ─────────────────────────────────────────────────────────────
#  Bot Events
# ─────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"""
╔══════════════════════════════════════════╗
║  🤖 Among Us Bot — Online               ║
║  User: {bot.user} ({bot.user.id})
║  Guilds: {len(bot.guilds)}
╚══════════════════════════════════════════╝
    """)

    # Register persistent view (für Button-Klicks nach Neustart)
    bot.add_view(PollView())

    # Register slash commands
    tree.add_command(amogus_group)
    try:
        synced = await tree.sync()
        print(f"[Bot] {len(synced)} Slash Commands synchronisiert")
    except Exception as e:
        print(f"[Bot] Slash Command sync fehler: {e}")

    # Start background tasks
    poll_pending_actions.start()
    check_reminders.start()
    print("[Bot] Background Tasks gestartet")

@bot.event
async def on_guild_join(guild: discord.Guild):
    print(f"[Bot] Neuer Server: {guild.name} ({guild.id})")
    logs = load_logs()
    gid  = str(guild.id)
    guilds = logs.setdefault("guilds", {})
    if gid not in guilds:
        guilds[gid] = {
            "guild_id":      gid,
            "guild_name":    guild.name,
            "member_count":  guild.member_count,
            "first_seen":    now_str(),
            "last_activity": now_str(),
            "total_polls":   0,
            "total_commands":0,
            "daily_stats":   {},
        }
        save_logs(logs)

# ─────────────────────────────────────────────────────────────
#  Start
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🤖 Starte Among Us Bot...")
    bot.run(TOKEN)
