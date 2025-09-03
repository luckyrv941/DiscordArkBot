import os
import re
import time
import sys
import asyncio
import requests
import discord
from discord.ext import commands
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- CONFIGURATION ---
DEFAULT_API_URL = "http://arkdedicated.com/arkuse/cache/officialarkuseserverlist.json"
REFRESH_INTERVAL = 4       # seconds
UPDATE_DURATION = 300      # 5 minutes per search
PORT = int(os.environ.get("PORT", 8000))  # Render requires a port
LOCK_FILE = "/tmp/bot.lock"                # singleton file to prevent double runs

# --- SINGLETON CHECK ---
if os.path.exists(LOCK_FILE):
    print("Bot already running. Exiting.")
    sys.exit(0)
else:
    open(LOCK_FILE, "w").close()

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

# --- CLEAR OLD STATE ---
active_searches = {}  # { channel_id: {'message': discord.Message, 'task': asyncio.Task} }
locks = {}            # per-channel locks

# --- HELPER FUNCTIONS ---
def fetch_servers():
    try:
        response = requests.get(DEFAULT_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()

        servers = []
        for s in data:
            # Normalize ARK JSON
            name = s.get("SessionName", "N/A")
            # Remove version tag like " - (v14.0)"
            if " - (" in name:
                name = name.split(" - (")[0].strip()

            servers.append({
                "name": name,
                "ip": s.get("IP", None),
                "port": s.get("Port", None),
                "numPlayers": s.get("NumPlayers", "?"),
                "maxPlayers": s.get("MaxPlayers", "?"),
                "mapName": s.get("MapName", "N/A").split("_")[0].strip(),  # clean _P
                "ping": s.get("ServerPing", "?")
            })
        return servers

    except Exception as e:
        print("Error fetching servers:", e)
        return []

def filter_servers(servers, query):
    try:
        pattern = re.compile(query, re.IGNORECASE)
        return [s for s in servers if pattern.search(s.get("name", ""))]
    except re.error:
        return []

def ping_emoji(ping_value):
    if ping_value == "?" or ping_value is None:
        return "❔"
    try:
        ping_value = int(ping_value)
    except:
        return "❔"
    if ping_value < 50:
        return "🟢"
    elif ping_value < 100:
        return "🟡"
    else:
        return "🔴"

def format_embed(servers, query):
    embed = discord.Embed(
        title=f"Server Search: {query}",
        description=f"Showing {len(servers)} result(s)",
        color=discord.Color.green()
    )

    for server in servers[:10]:
        name = server.get("name", "N/A")
        ip = server.get("ip")
        port = server.get("port")
        address = f"{ip}:{port}" if ip and port else "N/A"

        players = f"{server.get('numPlayers', '?')}/{server.get('maxPlayers', '?')}"
        map_name = server.get("mapName", "N/A")
        emoji = ping_emoji(server.get("ping"))

        embed.add_field(
            name=name,
            value=f"📡 `{address}`\n👥 {players}\n{emoji} Ping\n🗺️ {map_name}",
            inline=False
        )

    embed.set_footer(text=f"Live data | Refreshes every {REFRESH_INTERVAL} seconds.")
    return embed

# --- UPDATE TASK ---
async def update_task(message: discord.Message, query: str, channel_id: int):
    locks.setdefault(channel_id, asyncio.Lock())
    lock = locks[channel_id]
    end_time = time.time() + UPDATE_DURATION
    try:
        while time.time() < end_time:
            await asyncio.sleep(REFRESH_INTERVAL)
            servers = fetch_servers()
            matches = filter_servers(servers, query)
            async with lock:
                try:
                    await message.edit(embed=format_embed(matches, query))
                except discord.NotFound:
                    break
    except asyncio.CancelledError:
        pass
    finally:
        active_searches.pop(channel_id, None)
        try:
            final_embed = message.embeds[0]
            final_embed.set_footer(text="This search is no longer updating.")
            final_embed.color = discord.Color.greyple()
            await message.edit(embed=final_embed)
        except (discord.NotFound, IndexError):
            pass

# --- COMMAND ---
@bot.command(name="ark")
async def ark(ctx, *, query: str):
    channel_id = ctx.channel.id

    # Cancel old search in this channel
    if channel_id in active_searches:
        old_search = active_searches[channel_id]
        old_task = old_search['task']
        old_message = old_search['message']
        old_task.cancel()
        await asyncio.sleep(0)
        try:
            await old_message.delete()
        except discord.NotFound:
            pass

    # Send new message
    servers = fetch_servers()
    matches = filter_servers(servers, query)
    new_msg = await ctx.send(embed=format_embed(matches, query))

    # Store task
    new_task = bot.loop.create_task(update_task(new_msg, query, channel_id))
    active_searches[channel_id] = {'message': new_msg, 'task': new_task}

# --- READY EVENT ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# --- MINIMAL HTTP SERVER FOR RENDER ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_server():
    server = HTTPServer(("", PORT), DummyHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# --- OPTIONAL HEARTBEAT ---
def keep_alive():
    import requests
    while True:
        try:
            requests.get(f"http://localhost:{PORT}")
        except:
            pass
        time.sleep(60)

threading.Thread(target=keep_alive, daemon=True).start()

# --- RUN BOT ---
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: DISCORD_BOT_TOKEN not set in environment")
    else:
        bot.run(BOT_TOKEN)
