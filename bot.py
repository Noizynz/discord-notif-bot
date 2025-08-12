# --- START bot.py ---
import discord
from discord.ext import commands, tasks
import os, json, aiohttp, feedparser, asyncio
from datetime import datetime

DATA_FILE = "home.bot.json"

# اگر فایل دیتا وجود نداشت بساز
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"panels": {}}, f, ensure_ascii=False, indent=2)

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# ----- توابع کمکی -----
def make_embed(title="", description="", color=0x3498db):
    return discord.Embed(title=title, description=description, color=color)

def replace_placeholders_in_json_string(json_text: str, mapping: dict):
    out = json_text
    for k, v in mapping.items():
        out = out.replace(f"<{k}>", str(v))
    return out

async def fetch_rss(session, url):
    try:
        async with session.get(url, timeout=20) as resp:
            text = await resp.text()
            return feedparser.parse(text)
    except Exception as e:
        print("RSS fetch error:", e)
        return None

def youtube_rss_from_channel_link(link_or_id: str):
    if "channel/" in link_or_id:
        channel_id = link_or_id.split("channel/")[-1].split("?")[0].split("/")[0]
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    if link_or_id.startswith("UC"):
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={link_or_id}"
    return None

# ----- رویدادها و دستورات -----
@bot.event
async def on_ready():
    print("✅ بات آنلاین شد:", bot.user)
    check_youtube.start()

@bot.tree.command(name="help", description="نمایش راهنمای بات")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 راهنمای بات نوتیف", color=discord.Color.blue())
    embed.add_field(name="/newpanel", value="ساخت پنل جدید (مرحله‌به‌مرحله)", inline=False)
    embed.add_field(name="/panel", value="نمایش همه پنل‌های ساخته‌شده", inline=False)
    embed.add_field(name="/check", value="تست سریع یک پنل و فرستادن پیام تست", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="newpanel", description="ساخت پنل جدید به صورت مرحله به مرحله")
async def newpanel(interaction: discord.Interaction):
    await interaction.response.send_message(embed=make_embed("📌 ساخت پنل جدید", "لطفاً یک نام ساده برای پنل وارد کنید (مثال: my-youtube)."), ephemeral=True)

    def check(m):
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel_id

    try:
        msg = await bot.wait_for("message", check=check, timeout=120)
        panel_name = msg.content.strip()

        await interaction.followup.send(embed=make_embed("🔧 سرویس را انتخاب کنید", "ارسال عدد:\n1️⃣ ویدیو یوتیوب\n2️⃣ استریم یوتیوب"), ephemeral=True)
        msg2 = await bot.wait_for("message", check=check, timeout=120)
        choice = msg2.content.strip()

        if choice == "1":
            service = "youtube_video"
        elif choice == "2":
            service = "youtube_stream"
        else:
            await interaction.followup.send(embed=make_embed("⚠️ سرویس نامعتبر", "لطفا 1 یا 2 را ارسال کنید."), ephemeral=True)
            return

        await interaction.followup.send(embed=make_embed("🔗 لینک کانال", "لطفاً لینک کانال یوتیوب (یا channel_id) را ارسال کنید.\nمثال: https://www.youtube.com/channel/UCxxxx"), ephemeral=True)
        msg3 = await bot.wait_for("message", check=check, timeout=180)
        link = msg3.content.strip()

        disco_text = ("🔔 حالا به سایت https://discohook.org برو و یک Embed بساز.\n"
                      "از placeholderها استفاده کن:\n"
                      "`<title>` → عنوان\n`<videourl>` → لینک\n`<thumbnail>` → عکس\n"
                      "بعد از اتمام دکمه JSON را بزن و متن JSON را اینجا ارسال کن.")
        await interaction.followup.send(embed=make_embed("📝 راهنمای Discohook", disco_text), ephemeral=True)

        msg4 = await bot.wait_for("message", check=check, timeout=600)
        webhook_json_text = msg4.content.strip()

        await interaction.followup.send(embed=make_embed("📢 حالا کانال دیسکورد را منشن یا نام آن را بفرستید (مثلاً #announcements)"), ephemeral=True)
        msg5 = await bot.wait_for("message", check=check, timeout=120)
        if msg5.channel_mentions:
            channel_id = msg5.channel_mentions[0].id
        else:
            chan_name = msg5.content.strip().lstrip("#")
            found = None
            for ch in interaction.guild.channels:
                if ch.name == chan_name and isinstance(ch, discord.TextChannel):
                    found = ch
                    break
            if found:
                channel_id = found.id
            else:
                channel_id = interaction.channel_id

        data = load_data()
        gid = str(interaction.guild_id)
        if gid not in data["panels"]:
            data["panels"][gid] = []
        data["panels"][gid].append({
            "name": panel_name,
            "service": service,
            "link": link,
            "webhook_json": webhook_json_text,
            "channel_id": channel_id,
            "last_seen": None
        })
        save_data(data)

        await interaction.followup.send(embed=make_embed("✅ پنل ساخته شد", f"نام پنل: `{panel_name}`\nسرویس: `{service}`\nکانال ارسال: <#{channel_id}>"), ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send(embed=make_embed("⏱️ زمان تمام شد", "فرآیند ساخت پنل منقضی شد. دوباره /newpanel را اجرا کن."), ephemeral=True)

@bot.tree.command(name="panel", description="نمایش پنل‌های ساخته شده در سرور")
async def panel_list(interaction: discord.Interaction):
    data = load_data()
    gid = str(interaction.guild_id)
    if gid not in data["panels"] or len(data["panels"][gid]) == 0:
        await interaction.response.send_message(embed=make_embed("📭 هیچ پنلی پیدا نشد", "برای ساخت پنل از /newpanel استفاده کنید."), ephemeral=True)
        return
    emb = discord.Embed(title="📋 پنل‌های سرور", color=discord.Color.blue())
    for p in data["panels"][gid]:
        emb.add_field(name=p["name"], value=f"سرویس: `{p['service']}`\nلینک: {p['link']}\nچنل: <#{p['channel_id']}>", inline=False)
    await interaction.response.send_message(embed=emb, ephemeral=True)

@bot.tree.command(name="deletepanel", description="حذف یک پنل با نام")
async def delete_panel(interaction: discord.Interaction, name: str):
    data = load_data()
    gid = str(interaction.guild_id)
    if gid not in data["panels"]:
        await interaction.response.send_message(embed=make_embed("❌ خطا", "هیچ پنلی وجود ندارد."), ephemeral=True); return
    before = len(data["panels"][gid])
    data["panels"][gid] = [p for p in data["panels"][gid] if p["name"] != name]
    save_data(data)
    after = len(data["panels"][gid])
    if before == after:
        await interaction.response.send_message(embed=make_embed("❌ پیدا نشد", "پنل با این نام یافت نشد."), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("✅ حذف شد", f"پنل `{name}` حذف شد."), ephemeral=True)

@bot.tree.command(name="check", description="ارسال پیام تست با آخرین محتوای پنل")
async def check_panel(interaction: discord.Interaction, name: str):
    data = load_data()
    gid = str(interaction.guild_id)
    if gid not in data["panels"]:
        await interaction.response.send_message(embed=make_embed("❌ هیچ پنلی پیدا نشد", ""), ephemeral=True); return
    panel = None
    for p in data["panels"][gid]:
        if p["name"] == name:
            panel = p
            break
    if not panel:
        await interaction.response.send_message(embed=make_embed("❌ پنل یافت نشد", ""), ephemeral=True); return

    if panel["service"].startswith("youtube"):
        rss = youtube_rss_from_channel_link(panel["link"])
        if not rss:
            await interaction.response.send_message(embed=make_embed("⚠️ نمی‌توان RSS ساخت", "لطفاً لینک کانال یوتیوب را به صورت `https://www.youtube.com/channel/UC...` وارد کنید."), ephemeral=True)
            return
        async with aiohttp.ClientSession() as session:
            parsed = await fetch_rss(session, rss)
            if not parsed or not parsed.entries:
                await interaction.response.send_message(embed=make_embed("ℹ️ هیچ ویدیویی یافت نشد", ""), ephemeral=True)
                return
            latest = parsed.entries[0]
            video_id = latest.get("yt_videoid") or ""
            video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else latest.get("link","")
            thumbnail = ""
            if latest.get("media_thumbnail"):
                try:
                    thumbnail = latest.get("media_thumbnail")[0].get("url","")
                except:
                    thumbnail = ""
            mapping = {
                "title": latest.get("title",""),
                "videourl": video_url,
                "thumbnail": thumbnail,
                "channelname": parsed.feed.get("title","")
            }
            try:
                filled = replace_placeholders_in_json_string(panel["webhook_json"], mapping)
                data_json = json.loads(filled)
                ch = bot.get_channel(panel["channel_id"])
                if not ch:
                    await interaction.response.send_message(embed=make_embed("❌ کانال پیدا نشد", ""), ephemeral=True); return
                if isinstance(data_json, dict) and data_json.get("embeds"):
                    for e in data_json["embeds"]:
                        try:
                            emb = discord.Embed.from_dict(e)
                            await ch.send(embed=emb)
                        except Exception as e:
                            print("embed send error:", e)
                    await interaction.response.send_message(embed=make_embed("✅ پیام تست ارسال شد", f"به کانال {ch.mention} ارسال شد."), ephemeral=True)
                    return
                else:
                    await ch.send(f"🔔 تست: {mapping['title']} - {mapping['videourl']}")
                    await interaction.response.send_message(embed=make_embed("✅ پیام تست ارسال شد", f"به کانال {ch.mention} ارسال شد."), ephemeral=True)
                    return
            except Exception as e:
                await interaction.response.send_message(embed=make_embed("❌ خطا در پردازش قالب JSON", str(e)), ephemeral=True)
                return
    else:
        await interaction.response.send_message(embed=make_embed("ℹ️ سرویس هنوز پیاده نشده", "فعلاً فقط یوتیوب پشتیبانی می‌شود."), ephemeral=True)

# تسک چک یوتیوب هر 5 دقیقه
@tasks.loop(minutes=5)
async def check_youtube():
    await bot.wait_until_ready()
    data = load_data()
    async with aiohttp.ClientSession() as session:
        for gid, panels in data.get("panels", {}).items():
            for panel in panels:
                if not panel["service"].startswith("youtube"):
                    continue
                rss = youtube_rss_from_channel_link(panel["link"])
                if not rss:
                    continue
                parsed = await fetch_rss(session, rss)
                if not parsed or not parsed.entries:
                    continue
                newest = parsed.entries[0]
                video_id = newest.get("yt_videoid") or ""
                if not video_id:
                    continue
                if panel.get("last_seen") == video_id:
                    continue
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                thumbnail = ""
                if newest.get("media_thumbnail"):
                    try:
                        thumbnail = newest.get("media_thumbnail")[0].get("url","")
                    except:
                        thumbnail = ""
                mapping = {
                    "title": newest.get("title",""),
                    "videourl": video_url,
                    "thumbnail": thumbnail,
                    "channelname": parsed.feed.get("title",""),
                    "published": newest.get("published","")
                }
                try:
                    filled = replace_placeholders_in_json_string(panel["webhook_json"], mapping)
                    data_json = json.loads(filled)
                    ch = bot.get_channel(panel["channel_id"])
                    if ch and isinstance(data_json, dict) and data_json.get("embeds"):
                        for e in data_json["embeds"]:
                            try:
                                emb = discord.Embed.from_dict(e)
                                await ch.send(embed=emb)
                            except Exception as e:
                                print("Error sending embed:", e)
                    elif ch:
                        await ch.send(f"🔔 ویدیوی جدید: {mapping['title']} - {mapping['videourl']}")
                    panel["last_seen"] = video_id
                    save_data(data)
                except Exception as e:
                    print("Error processing panel JSON:", e)

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERROR: ENV var DISCORD_TOKEN را تنظیم نکرده‌اید.")
    else:
        bot.run(token)
# --- END bot.py ---
