import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# بارگذاری توکن از فایل .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# تعریف بات با پرمیژن های پایه
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# وقتی بات آماده شد
@bot.event
async def on_ready():
    print(f"✅ {bot.user} آماده است!")

# دستور تست /ping
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("🏓 Pong! بات آنلاین است ✅")

# ران کردن بات
bot.run(TOKEN)
