import discord
from discord.ext import commands
import os

# گرفتن توکن از Environment Variable
TOKEN = os.getenv("DISCORD_TOKEN")

# تعریف Intents (برای کار با ممبرا و مسیج‌ها باید روشن باشن)
intents = discord.Intents.default()
intents.message_content = True  # دسترسی به پیام‌ها
intents.guilds = True
intents.members = True

# تعریف بات با prefix
bot = commands.Bot(command_prefix="/", intents=intents)

# رویداد وقتی بات بالا میاد
@bot.event
async def on_ready():
    print(f"✅ ربات {bot.user} با موفقیت آنلاین شد!")

# یک دستور تست ساده
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong! ربات آنلاین است.")

# اجرای بات
if __name__ == "__main__":
    bot.run(TOKEN)
