import os
import re
import asyncio
import requests
import discord
import time
from discord.ext import commands

# --- CONFIGURATION ---
DEFAULT_API_URL = "https://ds.rg.dedyn.io/ht/getServer"
REFRESH_INTERVAL = 4  # seconds
UPDATE_DURATION = 300 # How long to keep updating in seconds (300s = 5 minutes)

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

# This dictionary will store the active search for each channel
# Format: { channel_id: {'message': discord.Message, 'task': asyncio.Task} }
active_searches = {}

# --- HELPER FUNCTIONS (fetch, filter, format) ---
def fetch_servers():
    try:
        response = requests.get(DEFAULT_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []
    except:
        return []

def filter_servers(servers, query):
    try:
        pattern = re.compile(query, re.IGNORECASE)
        return [s for s in servers if pattern.search(s.get("name", ""))]
    except re.error:
        return []

def format_embed(servers, query):
    embed = discord.Embed(
        title=f"Server Search: {query}",
        description=f"Showing {len(servers)} result(s)",
        color=discord.Color.green()
    )
    for server in servers[:10]:
        name, address, players, map_name = (server.get("name", "N/A"),
                                          f"{server.get('ip')}:{server.get('port')}" if server.get("ip") and server.get("port") else "N/A",
                                          f"{server.get('numPlayers', '?')}/{server.get('maxPlayers', '?')}",
                                          server.get("mapName", "N/A").split("-")[0].strip())
        embed.add_field(name=name, value=f"📡 `{address}`\n👥 {players}\n🗺️ {map_name}", inline=False)
    embed.set_footer(text=f"Live data | Refreshes every {REFRESH_INTERVAL} seconds.")
    return embed

async def update_task(message: discord.Message, query: str):
    """This function is the update loop, now separated to be a cancellable task."""
    end_time = time.time() + UPDATE_DURATION
    try:
        while time.time() < end_time:
            await asyncio.sleep(REFRESH_INTERVAL)
            servers = fetch_servers()
            matches = filter_servers(servers, query)
            await message.edit(embed=format_embed(matches, query))
    except asyncio.CancelledError:
        # The task was cancelled by a new command, which is expected.
        pass
    except discord.NotFound:
        # The message was deleted manually.
        pass
    finally:
        # Edit the message one last time to show it's no longer updating.
        try:
            final_embed = message.embeds[0]
            final_embed.set_footer(text="This search is no longer updating.")
            final_embed.color = discord.Color.greyple()
            await message.edit(embed=final_embed)
        except (discord.NotFound, IndexError):
            pass

@bot.command(name="ark")
async def ark(ctx, *, query: str):
    channel_id = ctx.channel.id

    # 1. Check for and clean up an old search in the same channel
    if channel_id in active_searches:
        old_search = active_searches[channel_id]
        old_task = old_search['task']
        old_message = old_search['message']

        old_task.cancel()  # Stop the old update loop
        try:
            await old_message.delete()  # Delete the old message
        except discord.NotFound:
            pass  # It was already deleted, no problem.

    # 2. Send the new initial message
    initial_servers = fetch_servers()
    matches = filter_servers(initial_servers, query)
    new_msg = await ctx.send(embed=format_embed(matches, query))

    # 3. Create and store the new task and message
    new_task = bot.loop.create_task(update_task(new_msg, query))
    active_searches[channel_id] = {'message': new_msg, 'task': new_task}

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: DISCORD_BOT_TOKEN not set in environment")
    else:
        bot.run(BOT_TOKEN)
