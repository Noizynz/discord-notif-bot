import discord
from discord.ext import commands
import os
import sys

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("❌ توکن یافت نشد! لطفا در Render یک Environment Variable با نام DISCORD_TOKEN بسازید.")
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ ربات {bot.user} با موفقیت آنلاین شد!")

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong! ربات آنلاین است.")

if __name__ == "__main__":
    bot.run(TOKEN)
