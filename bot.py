import os
import re
import asyncio
import requests
import discord
from discord.ext import commands

DEFAULT_API_URL = "https://ds.rg.dedyn.io/ht/getServer"
REFRESH_INTERVAL = 4  # seconds

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")  # get token from environment

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
        name = server.get("name", "N/A")
        address = f"{server.get('ip')}:{server.get('port')}" if server.get("ip") and server.get("port") else "N/A"
        players = f"{server.get('numPlayers', '?')}/{server.get('maxPlayers', '?')}"
        map_name = server.get("mapName", "N/A").split("-")[0].strip()
        embed.add_field(
            name=name,
            value=f"📡 `{address}`\n👥 {players}\n🗺 {map_name}",
            inline=False
        )
    embed.set_footer(text="Data refreshes automatically every few seconds.")
    return embed

@bot.command()
async def search(ctx, *, query: str):
    servers = fetch_servers()
    matches = filter_servers(servers, query)
    msg = await ctx.send(embed=format_embed(matches, query))

    async def refresher():
        while True:
            await asyncio.sleep(REFRESH_INTERVAL)
            servers = fetch_servers()
            matches = filter_servers(servers, query)
            try:
                await msg.edit(embed=format_embed(matches, query))
            except discord.NotFound:
                break

    bot.loop.create_task(refresher())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: DISCORD_BOT_TOKEN not set in environment")
    else:
        bot.run(BOT_TOKEN)
