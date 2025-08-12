# --- START bot.py ---
import discord
from discord.ext import commands, tasks
import os, json, aiohttp, feedparser, asyncio

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
# پیش‌وند مورد نظر برای دستورات متنی (prefix)
PREFIX = "hm!"
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# --- توابع کمکی ---
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

# --- رویداد راه‌اندازی ---
@bot.event
async def on_ready():
    print("✅ بات آنلاین شد:", bot.user)
    # Register slash commands faster for one guild if provided
    GUILD = os.getenv("GUILD_ID")
    if GUILD:
        try:
            await bot.tree.sync(guild=discord.Object(id=int(GUILD)))
            print("🔄 دستورات اسلش برای Guild همگام‌سازی شد.")
        except Exception as e:
            print("خطا در سینک گیلد:", e)
    else:
        try:
            await bot.tree.sync()
            print("🔄 دستورات اسلش (global) همگام‌سازی شد.")
        except Exception as e:
            print("خطا در سینک global:", e)

    # start background task
    if not check_youtube.is_running():
        check_youtube.start()

# ---------------- Slash commands (دستورات اسلش) ----------------
@bot.tree.command(name="help", description="نمایش راهنمای بات")
async def slash_help(interaction: discord.Interaction):
    embed = make_embed("📚 راهنمای بات", "دستورهای قابل استفاده:")
    embed.add_field(name=f"{PREFIX}help  یا  /help", value="نمایش این راهنما", inline=False)
    embed.add_field(name=f"{PREFIX}newpanel  یا  /newpanel", value="ساخت پنل جدید", inline=False)
    embed.add_field(name=f"{PREFIX}panel  یا  /panel", value="نمایش پنل‌های ساخته‌شده", inline=False)
    embed.add_field(name=f"{PREFIX}check <name>  یا  /check", value="ارسال پیام تست از یک پنل", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="newpanel", description="ساخت پنل جدید (مرحله‌به‌مرحله)")
async def slash_newpanel(interaction: discord.Interaction):
    await interaction.response.send_message(embed=make_embed("📌 ساخت پنل جدید", "لطفاً یک نام ساده برای پنل وارد کنید."), ephemeral=True)

    def check_msg(m):
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel_id

    try:
        msg = await bot.wait_for("message", check=check_msg, timeout=120)
        panel_name = msg.content.strip()

        await interaction.followup.send(embed=make_embed("🔧 سرویس را انتخاب کنید", "ارسال عدد: 1) ویدیو یوتیوب  2) استریم یوتیوب"), ephemeral=True)
        msg2 = await bot.wait_for("message", check=check_msg, timeout=120)
        choice = msg2.content.strip()
        if choice == "1":
            service = "youtube_video"
        elif choice == "2":
            service = "youtube_stream"
        else:
            await interaction.followup.send(embed=make_embed("⚠️ سرویس نامعتبر","فقط 1 یا 2 پذیرفته می‌شود."), ephemeral=True)
            return

        await interaction.followup.send(embed=make_embed("🔗 لینک کانال", "لطفاً لینک کانال یوتیوب یا channel_id را ارسال کنید."), ephemeral=True)
        msg3 = await bot.wait_for("message", check=check_msg, timeout=180)
        link = msg3.content.strip()

        disco_text = ("به سایت https://discohook.org برو و Embed بساز.\n"
                      "Placeholderها:\n`<title>` عنوان\n`<videourl>` لینک\n`<thumbnail>` عکس\n"
                      "پس از اتمام، دکمه JSON را زده و متن JSON را اینجا ارسال کن.")
        await interaction.followup.send(embed=make_embed("📝 Discohook", disco_text), ephemeral=True)
        msg4 = await bot.wait_for("message", check=check_msg, timeout=600)
        webhook_json_text = msg4.content.strip()

        await interaction.followup.send(embed=make_embed("📢 حالا کانال دیسکورد را منشن یا نام آن را بفرستید"), ephemeral=True)
        msg5 = await bot.wait_for("message", check=check_msg, timeout=120)
        if msg5.channel_mentions:
            channel_id = msg5.channel_mentions[0].id
        else:
            chan_name = msg5.content.strip().lstrip("#")
            found = None
            for ch in interaction.guild.channels:
                if ch.name == chan_name and isinstance(ch, discord.TextChannel):
                    found = ch
                    break
            channel_id = found.id if found else interaction.channel_id

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
        await interaction.followup.send(embed=make_embed("✅ پنل ساخته شد", f"پنل `{panel_name}` ساخته و ذخیره شد."), ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send(embed=make_embed("⏱️ زمان تمام شد", "دوباره /newpanel را اجرا کنید."), ephemeral=True)

@bot.tree.command(name="panel", description="نمایش پنل‌های ساخته شده")
async def slash_panel(interaction: discord.Interaction):
    data = load_data()
    gid = str(interaction.guild_id)
    if gid not in data["panels"] or not data["panels"][gid]:
        await interaction.response.send_message(embed=make_embed("📭 هیچ پنلی نیست","برای ساخت پنل /newpanel را بزنید."), ephemeral=True)
        return
    emb = make_embed("📋 پنل‌های سرور")
    for p in data["panels"][gid]:
        emb.add_field(name=p["name"], value=f"سرویس: `{p['service']}`\nلینک: {p['link']}\nچنل: <#{p['channel_id']}>", inline=False)
    await interaction.response.send_message(embed=emb, ephemeral=True)

@bot.tree.command(name="deletepanel", description="حذف یک پنل با نام")
async def slash_deletepanel(interaction: discord.Interaction, name: str):
    data = load_data(); gid = str(interaction.guild_id)
    if gid not in data["panels"]:
        await interaction.response.send_message(embed=make_embed("❌ خطا","هیچ پنلی وجود ندارد."), ephemeral=True); return
    before = len(data["panels"][gid])
    data["panels"][gid] = [p for p in data["panels"][gid] if p["name"] != name]
    save_data(data)
    if before == len(data["panels"][gid]):
        await interaction.response.send_message(embed=make_embed("❌ پیدا نشد","پنل یافت نشد."), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("✅ حذف شد", f"پنل `{name}` حذف شد."), ephemeral=True)

@bot.tree.command(name="check", description="ارسال پیام تست از یک پنل")
async def slash_check(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)
    await perform_check_and_send(interaction.guild, name, interaction_user=interaction.user, reply_target=interaction)

# ---------------- Prefix commands (با پیش‌وند hm!) ----------------
@bot.command(name="help")
async def prefix_help(ctx: commands.Context):
    embed = make_embed("📚 راهنمای بات", "دستورها:")
    embed.add_field(name=f"{PREFIX}help  یا  /help", value="نمایش این راهنما", inline=False)
    embed.add_field(name=f"{PREFIX}newpanel  یا  /newpanel", value="ساخت پنل جدید", inline=False)
    embed.add_field(name=f"{PREFIX}panel  یا  /panel", value="نمایش پنل‌ها", inline=False)
    embed.add_field(name=f"{PREFIX}check <name>  یا  /check", value="ارسال پیام تست از یک پنل", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="newpanel")
async def prefix_newpanel(ctx: commands.Context):
    await ctx.send(embed=make_embed("📌 ساخت پنل جدید", "لطفاً یک نام ساده برای پنل وارد کنید."))

    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    try:
        msg = await bot.wait_for("message", check=check, timeout=120)
        panel_name = msg.content.strip()

        await ctx.send(embed=make_embed("🔧 سرویس را انتخاب کنید", "ارسال عدد: 1) ویدیو یوتیوب  2) استریم یوتیوب"))
        msg2 = await bot.wait_for("message", check=check, timeout=120)
        choice = msg2.content.strip()
        if choice == "1":
            service = "youtube_video"
        elif choice == "2":
            service = "youtube_stream"
        else:
            await ctx.send(embed=make_embed("⚠️ سرویس نامعتبر","فقط 1 یا 2 پذیرفته می‌شود.")); return

        await ctx.send(embed=make_embed("🔗 لینک کانال", "لطفاً لینک کانال یوتیوب یا channel_id را ارسال کنید."))
        msg3 = await bot.wait_for("message", check=check, timeout=180)
        link = msg3.content.strip()

        disco_text = ("به سایت https://discohook.org برو و Embed بساز.\n"
                      "Placeholderها: `<title>`, `<videourl>`, `<thumbnail>`\n"
                      "بعد از اتمام JSON را اینجا ارسال کن.")
        await ctx.send(embed=make_embed("📝 Discohook", disco_text))
        msg4 = await bot.wait_for("message", check=check, timeout=600)
        webhook_json_text = msg4.content.strip()

        await ctx.send(embed=make_embed("📢 حالا کانال دیسکورد را منشن یا نام آن را بفرستید"))
        msg5 = await bot.wait_for("message", check=check, timeout=120)
        if msg5.channel_mentions:
            channel_id = msg5.channel_mentions[0].id
        else:
            chan_name = msg5.content.strip().lstrip("#")
            found = None
            for ch in ctx.guild.channels:
                if ch.name == chan_name and isinstance(ch, discord.TextChannel):
                    found = ch; break
            channel_id = found.id if found else ctx.channel.id

        data = load_data(); gid = str(ctx.guild.id)
        if gid not in data["panels"]: data["panels"][gid] = []
        data["panels"][gid].append({
            "name": panel_name, "service": service, "link": link,
            "webhook_json": webhook_json_text, "channel_id": channel_id, "last_seen": None
        })
        save_data(data)
        await ctx.send(embed=make_embed("✅ پنل ساخته شد", f"پنل `{panel_name}` ساخته شد."))
    except asyncio.TimeoutError:
        await ctx.send(embed=make_embed("⏱️ زمان تمام شد", "دوباره دستور را اجرا کن."))

@bot.command(name="panel")
async def prefix_panel(ctx: commands.Context):
    data = load_data(); gid = str(ctx.guild.id)
    if gid not in data["panels"] or not data["panels"][gid]:
        await ctx.send(embed=make_embed("📭 هیچ پنلی نیست","برای ساخت پنل hm!newpanel را بزنید.")); return
    emb = make_embed("📋 پنل‌های سرور")
    for p in data["panels"][gid]:
        emb.add_field(name=p["name"], value=f"سرویس: `{p['service']}`\nلینک: {p['link']}\nچنل: <#{p['channel_id']}>", inline=False)
    await ctx.send(embed=emb)

@bot.command(name="deletepanel")
async def prefix_deletepanel(ctx: commands.Context, name: str):
    data = load_data(); gid = str(ctx.guild.id)
    if gid not in data["panels"]:
        await ctx.send(embed=make_embed("❌ خطا","هیچ پنلی وجود ندارد.")); return
    before = len(data["panels"][gid])
    data["panels"][gid] = [p for p in data["panels"][gid] if p["name"] != name]
    save_data(data)
    if before == len(data["panels"][gid]):
        await ctx.send(embed=make_embed("❌ پیدا نشد","پنل یافت نشد."))
    else:
        await ctx.send(embed=make_embed("✅ حذف شد", f"پنل `{name}` حذف شد."))

@bot.command(name="check")
async def prefix_check(ctx: commands.Context, name: str):
    await perform_check_and_send(ctx.guild, name, ctx_user=ctx.author, reply_target=ctx)

# --- وظیفهٔ مشترک برای /check و hm!check (ارسال پیام تست و پردازش قالب JSON) ---
async def perform_check_and_send(guild_obj, panel_name, interaction_user=None, reply_target=None, ctx_user=None, reply_ctx=None):
    data = load_data(); gid = str(guild_obj.id)
    if gid not in data["panels"]:
        if reply_target:
            await reply_target.response.send_message(embed=make_embed("❌ هیچ پنلی نیست",""), ephemeral=True)
        elif reply_ctx:
            await reply_ctx.send(embed=make_embed("❌ هیچ پنلی نیست",""))
        return
    panel = None
    for p in data["panels"][gid]:
        if p["name"] == panel_name:
            panel = p; break
    if not panel:
        if reply_target:
            await reply_target.response.send_message(embed=make_embed("❌ پنل یافت نشد",""), ephemeral=True)
        elif reply_ctx:
            await reply_ctx.send(embed=make_embed("❌ پنل یافت نشد",""))
        return

    # فعلاً فقط یوتیوب پیاده شده
    if panel["service"].startswith("youtube"):
        rss = youtube_rss_from_channel_link(panel["link"])
        if not rss:
            if reply_target:
                await reply_target.response.send_message(embed=make_embed("⚠️ RSS ساخته نشد","لینک کانال را به فرم channel بفرست."), ephemeral=True)
            elif reply_ctx:
                await reply_ctx.send(embed=make_embed("⚠️ RSS ساخته نشد",""))
            return
        async with aiohttp.ClientSession() as session:
            parsed = await fetch_rss(session, rss)
            if not parsed or not parsed.entries:
                if reply_target:
                    await reply_target.response.send_message(embed=make_embed("ℹ️ ویدیویی نیست",""), ephemeral=True)
                elif reply_ctx:
                    await reply_ctx.send(embed=make_embed("ℹ️ ویدیویی نیست",""))
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
            mapping = {"title": latest.get("title",""), "videourl": video_url, "thumbnail": thumbnail, "channelname": parsed.feed.get("title","")}
            try:
                filled = replace_placeholders_in_json_string(panel["webhook_json"], mapping)
                data_json = json.loads(filled)
                ch = bot.get_channel(panel["channel_id"])
                if not ch:
                    if reply_target:
                        await reply_target.response.send_message(embed=make_embed("❌ کانال پیدا نشد",""), ephemeral=True)
                    elif reply_ctx:
                        await reply_ctx.send(embed=make_embed("❌ کانال پیدا نشد",""))
                    return
                if isinstance(data_json, dict) and data_json.get("embeds"):
                    for e in data_json["embeds"]:
                        try:
                            emb = discord.Embed.from_dict(e)
                            await ch.send(embed=emb)
                        except Exception as e:
                            print("embed send error:", e)
                    if reply_target:
                        await reply_target.response.send_message(embed=make_embed("✅ پیام تست ارسال شد", f"در {ch.mention} ارسال شد."), ephemeral=True)
                    elif reply_ctx:
                        await reply_ctx.send(embed=make_embed("✅ پیام تست ارسال شد", f"در {ch.mention} ارسال شد."))
                    # به‌روزرسانی last_seen انجام نخواهد شد برای تست
                    return
                else:
                    await ch.send(f"🔔 تست: {mapping['title']} - {mapping['videourl']}")
                    if reply_target:
                        await reply_target.response.send_message(embed=make_embed("✅ پیام تست ارسال شد", f"در {ch.mention} ارسال شد."), ephemeral=True)
                    elif reply_ctx:
                        await reply_ctx.send(embed=make_embed("✅ پیام تست ارسال شد", f"در {ch.mention} ارسال شد."))
                    return
            except Exception as e:
                if reply_target:
                    await reply_target.response.send_message(embed=make_embed("❌ خطا در پردازش JSON", str(e)), ephemeral=True)
                elif reply_ctx:
                    await reply_ctx.send(embed=make_embed("❌ خطا در پردازش JSON", str(e)))
                return
    else:
        if reply_target:
            await reply_target.response.send_message(embed=make_embed("ℹ️ سرویس هنوز پیاده نشده","فعلاً فقط یوتیوب پشتیبانی می‌شود."), ephemeral=True)
        elif reply_ctx:
            await reply_ctx.send(embed=make_embed("ℹ️ سرویس هنوز پیاده نشده",""))

# --- چک یوتیوب هر 5 دقیقه ---
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
                mapping = {"title": newest.get("title",""), "videourl": video_url, "thumbnail": thumbnail, "channelname": parsed.feed.get("title",""), "published": newest.get("published","")}
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

# --- اجرای بات ---
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERROR: ENV var DISCORD_TOKEN را تنظیم نکرده‌اید.")
    else:
        bot.run(token)
# --- END bot.py ---
