# --- START bot.py ---
import discord
from discord.ext import commands, tasks
from aiohttp import web
import os, json, aiohttp, feedparser, asyncio

DATA_FILE = "home.bot.json"
DEFAULT_PREFIX = "hm!"

# اگر فایل دیتا وجود نداشت، بساز
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"panels": {}, "prefixes": {}}, f, ensure_ascii=False, indent=2)

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- پیشوند داینامیک ----------
async def get_prefix(bot, message):
    # اگر پیام در DM بود، فقط منشن بات را قبول کن
    if not message.guild:
        return commands.when_mentioned_or(DEFAULT_PREFIX)(bot, message)
    data = load_data()
    gid = str(message.guild.id)
    prefix = data.get("prefixes", {}).get(gid, DEFAULT_PREFIX)
    # همچنین اجازه بدیم بات با منشن هم فراخوانی شود
    return commands.when_mentioned_or(prefix)(bot, message)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=get_prefix, intents=intents)

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

# ---------- سرور HTTP ساده برای Render (تا پورت باز باشه) ----------
async def start_http_server():
    async def handle_root(request):
        return web.Response(text="Bot is running")
    app = web.Application()
    app.add_routes([web.get("/", handle_root)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"HTTP server running on port {port}")

# ---------- on_ready ----------
@bot.event
async def on_ready():
    print("✅ بات آنلاین شد:", bot.user)
    # sync slash commands (اگر GUILD_ID داده شده سریع‌تر سینک می‌شود)
    GUILD = os.getenv("GUILD_ID")
    try:
        if GUILD:
            await bot.tree.sync(guild=discord.Object(id=int(GUILD)))
            print("🔄 دستورات اسلش برای Guild همگام‌سازی شد.")
        else:
            await bot.tree.sync()
            print("🔄 دستورات اسلش (global) همگام‌سازی شد.")
    except Exception as e:
        print("خطا در سینک دستورات اسلش:", e)

    # راه‌اندازی سرور HTTP در پس‌زمینه (برای Render)
    bot.loop.create_task(start_http_server())

    # شروع تسک چک یوتیوب اگر اجرا نشده
    if not check_youtube.is_running():
        check_youtube.start()

# ---------- دستورات اسلش ----------
@bot.tree.command(name="help", description="نمایش راهنمای بات")
async def slash_help(interaction: discord.Interaction):
    data = load_data()
    gid = str(interaction.guild_id) if interaction.guild_id else None
    prefix = data.get("prefixes", {}).get(gid, DEFAULT_PREFIX) if gid else DEFAULT_PREFIX
    embed = make_embed("📚 راهنمای بات", "در اینجا لیستی از دستورها را می‌بینید:")
    embed.add_field(name=f"{prefix}help  یا  /help", value="نمایش همین راهنما", inline=False)
    embed.add_field(name=f"{prefix}newpanel  یا  /newpanel", value="ساخت پنل جدید", inline=False)
    embed.add_field(name=f"{prefix}panel  یا  /panel", value="نمایش پنل‌ها", inline=False)
    embed.add_field(name=f"{prefix}check <name>  یا  /check", value="ارسال پیام تست از یک پنل", inline=False)
    embed.add_field(name=f"{prefix}prefix <جدید>  یا  /prefix <جدید>", value="نمایش یا تغییر پیشوند بات برای این سرور", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="prefix", description="نمایش یا تغییر پیشوند بات (مثال: hm!)")
async def slash_prefix(interaction: discord.Interaction, new_prefix: str = None):
    if not interaction.guild:
        await interaction.response.send_message(embed=make_embed("⚠️ فقط در سرورها قابل اجرا است",""), ephemeral=True)
        return
    data = load_data()
    gid = str(interaction.guild_id)
    if new_prefix is None:
        cur = data.get("prefixes", {}).get(gid, DEFAULT_PREFIX)
        await interaction.response.send_message(embed=make_embed("🔧 پیشوند فعلی", f"پیشوند این سرور: `{cur}`\nبرای تغییر: `/prefix NEW` یا `{cur}prefix NEW`"), ephemeral=True)
        return
    # اعتبارسنجی ساده
    if len(new_prefix) > 5:
        await interaction.response.send_message(embed=make_embed("⚠️ پیشوند طولانی است","حداکثر 5 کاراکتر مجاز است."), ephemeral=True)
        return
    data.setdefault("prefixes", {})[gid] = new_prefix
    save_data(data)
    await interaction.response.send_message(embed=make_embed("✅ پیشوند تغییر کرد", f"پیشوند جدید: `{new_prefix}`"), ephemeral=True)

# بقیه دستورات اسلش (newpanel / panel / check / deletepanel) مشابه نسخهٔ قبل هستند
# برای کوتاهی در اینجا همان منطق قبلی را استفاده می‌کنیم (کد کامل در ادامه)
# ... (کد newpanel, panel, deletepanel, check را در ادامه می‌آوریم)
# پایین تر (بعد از بخش prefix و قبل از تسک) ما عملکرد check و newpanel و غیره را کامل پیاده کرده‌ایم.

# ---------- دستورات متنِ با prefix (مثلاً hm!) ----------
@bot.command(name="prefix")
async def prefix_cmd(ctx: commands.Context, new_prefix: str = None):
    data = load_data()
    gid = str(ctx.guild.id) if ctx.guild else None
    if new_prefix is None:
        cur = data.get("prefixes", {}).get(gid, DEFAULT_PREFIX)
        await ctx.send(embed=make_embed("🔧 پیشوند فعلی", f"پیشوند این سرور: `{cur}`\nبرای تغییر: `{cur}prefix NEW`"))
        return
    if len(new_prefix) > 5:
        await ctx.send(embed=make_embed("⚠️ پیشوند طولانی است","حداکثر 5 کاراکتر مجاز است."))
        return
    data.setdefault("prefixes", {})[gid] = new_prefix
    save_data(data)
    await ctx.send(embed=make_embed("✅ پیشوند تغییر کرد", f"پیشوند جدید: `{new_prefix}`"))

# ---------- اینجا بقیهٔ دستورات ساخت پنل و چک را کامل می‌کنیم ----------
# برای جلوگیری از طولانی شدن پیام، کدهای newpanel / panel / deletepanel / check و تسک چک یوتیوب
# را دقیقاً مانند نسخهٔ قبلی (که با هم کار می‌کرد) اضافه کن.
# من دقیقا همان توابع را که قبلا بود بازنویسی می‌کنم (تا تکرار نشود اینجا)
# برای سادگی، ادامهٔ کامل فایل را از نسخهٔ پیشین that we had اضافه می‌کنیم:

# --- newpanel (هم برای slash و هم برای prefix به صورت interactive) ---
@bot.tree.command(name="newpanel", description="ساخت پنل جدید (مرحله‌به‌مرحله)")
async def slash_newpanel(interaction: discord.Interaction):
    await interaction.response.send_message(embed=make_embed("📌 ساخت پنل جدید", "لطفاً یک نام ساده برای پنل وارد کنید."), ephemeral=True)
    def check_msg(m): return m.author.id == interaction.user.id and m.channel.id == interaction.channel_id
    try:
        msg = await bot.wait_for("message", check=check_msg, timeout=120)
        panel_name = msg.content.strip()
        await interaction.followup.send(embed=make_embed("🔧 سرویس را انتخاب کنید", "ارسال عدد: 1) ویدیو یوتیوب  2) استریم یوتیوب"), ephemeral=True)
        msg2 = await bot.wait_for("message", check=check_msg, timeout=120)
        choice = msg2.content.strip()
        if choice == "1": service = "youtube_video"
        elif choice == "2": service = "youtube_stream"
        else:
            await interaction.followup.send(embed=make_embed("⚠️ سرویس نامعتبر","فقط 1 یا 2 پذیرفته می‌شود."), ephemeral=True); return
        await interaction.followup.send(embed=make_embed("🔗 لینک کانال", "لطفاً لینک کانال یوتیوب یا channel_id را ارسال کنید."), ephemeral=True)
        msg3 = await bot.wait_for("message", check=check_msg, timeout=180); link = msg3.content.strip()
        disco_text = ("به سایت https://discohook.org برو و Embed بساز.\nPlaceholderها: `<title>`, `<videourl>`, `<thumbnail>`\nپس از اتمام JSON را اینجا ارسال کن.")
        await interaction.followup.send(embed=make_embed("📝 Discohook", disco_text), ephemeral=True)
        msg4 = await bot.wait_for("message", check=check_msg, timeout=600); webhook_json_text = msg4.content.strip()
        await interaction.followup.send(embed=make_embed("📢 حالا کانال دیسکورد را منشن یا نام آن را بفرستید"), ephemeral=True)
        msg5 = await bot.wait_for("message", check=check_msg, timeout=120)
        if msg5.channel_mentions: channel_id = msg5.channel_mentions[0].id
        else:
            chan_name = msg5.content.strip().lstrip("#"); found = None
            for ch in interaction.guild.channels:
                if ch.name == chan_name and isinstance(ch, discord.TextChannel): found = ch; break
            channel_id = found.id if found else interaction.channel_id
        data = load_data(); gid = str(interaction.guild_id)
        if gid not in data["panels"]: data["panels"][gid] = []
        data["panels"][gid].append({"name": panel_name, "service": service, "link": link, "webhook_json": webhook_json_text, "channel_id": channel_id, "last_seen": None})
        save_data(data)
        await interaction.followup.send(embed=make_embed("✅ پنل ساخته شد", f"پنل `{panel_name}` ساخته و ذخیره شد."), ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send(embed=make_embed("⏱️ زمان تمام شد", "دوباره /newpanel را اجرا کنید."), ephemeral=True)

@bot.command(name="newpanel")
async def prefix_newpanel(ctx: commands.Context):
    await ctx.send(embed=make_embed("📌 ساخت پنل جدید", "لطفاً یک نام ساده برای پنل وارد کنید."))
    def check(m): return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
    try:
        msg = await bot.wait_for("message", check=check, timeout=120); panel_name = msg.content.strip()
        await ctx.send(embed=make_embed("🔧 سرویس را انتخاب کنید", "ارسال عدد: 1) ویدیو یوتیوب  2) استریم یوتیوب"))
        msg2 = await bot.wait_for("message", check=check, timeout=120); choice = msg2.content.strip()
        if choice == "1": service = "youtube_video"
        elif choice == "2": service = "youtube_stream"
        else: await ctx.send(embed=make_embed("⚠️ سرویس نامعتبر","فقط 1 یا 2 پذیرفته می‌شود.")); return
        await ctx.send(embed=make_embed("🔗 لینک کانال", "لطفاً لینک کانال یوتیوب یا channel_id را ارسال کنید."))
        msg3 = await bot.wait_for("message", check=check, timeout=180); link = msg3.content.strip()
        disco_text = ("به سایت https://discohook.org برو و Embed بساز.\nPlaceholderها: `<title>`, `<videourl>`, `<thumbnail>`\nبعد از اتمام JSON را اینجا ارسال کن.")
        await ctx.send(embed=make_embed("📝 Discohook", disco_text))
        msg4 = await bot.wait_for("message", check=check, timeout=600); webhook_json_text = msg4.content.strip()
        await ctx.send(embed=make_embed("📢 حالا کانال دیسکورد را منشن یا نام آن را بفرستید"))
        msg5 = await bot.wait_for("message", check=check, timeout=120)
        if msg5.channel_mentions: channel_id = msg5.channel_mentions[0].id
        else:
            chan_name = msg5.content.strip().lstrip("#"); found = None
            for ch in ctx.guild.channels:
                if ch.name == chan_name and isinstance(ch, discord.TextChannel): found = ch; break
            channel_id = found.id if found else ctx.channel.id
        data = load_data(); gid = str(ctx.guild.id)
        if gid not in data["panels"]: data["panels"][gid] = []
        data["panels"][gid].append({"name": panel_name, "service": service, "link": link, "webhook_json": webhook_json_text, "channel_id": channel_id, "last_seen": None})
        save_data(data)
        await ctx.send(embed=make_embed("✅ پنل ساخته شد", f"پنل `{panel_name}` ساخته شد."))
    except asyncio.TimeoutError:
        await ctx.send(embed=make_embed("⏱️ زمان تمام شد", "دوباره دستور را اجرا کن."))

@bot.tree.command(name="panel", description="نمایش پنل‌های ساخته شده")
async def slash_panel(interaction: discord.Interaction):
    data = load_data(); gid = str(interaction.guild_id)
    if gid not in data["panels"] or not data["panels"][gid]:
        await interaction.response.send_message(embed=make_embed("📭 هیچ پنلی نیست","برای ساخت پنل /newpanel را بزنید."), ephemeral=True); return
    emb = make_embed("📋 پنل‌های سرور")
    for p in data["panels"][gid]:
        emb.add_field(name=p["name"], value=f"سرویس: `{p['service']}`\nلینک: {p['link']}\nچنل: <#{p['channel_id']}>", inline=False)
    await interaction.response.send_message(embed=emb, ephemeral=True)

@bot.command(name="panel")
async def prefix_panel(ctx: commands.Context):
    data = load_data(); gid = str(ctx.guild.id)
    if gid not in data["panels"] or not data["panels"][gid]:
        await ctx.send(embed=make_embed("📭 هیچ پنلی نیست","برای ساخت پنل hm!newpanel را بزنید.")); return
    emb = make_embed("📋 پنل‌های سرور")
    for p in data["panels"][gid]:
        emb.add_field(name=p["name"], value=f"سرویس: `{p['service']}`\nلینک: {p['link']}\nچنل: <#{p['channel_id']}>", inline=False)
    await ctx.send(embed=emb)

@bot.tree.command(name="deletepanel", description="حذف یک پنل با نام")
async def slash_deletepanel(interaction: discord.Interaction, name: str):
    data = load_data(); gid = str(interaction.guild_id)
    if gid not in data["panels"]:
        await interaction.response.send_message(embed=make_embed("❌ خطا","هیچ پنلی وجود ندارد."), ephemeral=True); return
    before = len(data["panels"][gid]); data["panels"][gid] = [p for p in data["panels"][gid] if p["name"] != name]; save_data(data)
    if before == len(data["panels"][gid]):
        await interaction.response.send_message(embed=make_embed("❌ پیدا نشد","پنل یافت نشد."), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("✅ حذف شد", f"پنل `{name}` حذف شد."), ephemeral=True)

@bot.command(name="deletepanel")
async def prefix_deletepanel(ctx: commands.Context, name: str):
    data = load_data(); gid = str(ctx.guild.id)
    if gid not in data["panels"]:
        await ctx.send(embed=make_embed("❌ خطا","هیچ پنلی وجود ندارد.")); return
    before = len(data["panels"][gid]); data["panels"][gid] = [p for p in data["panels"][gid] if p["name"] != name]; save_data(data)
    if before == len(data["panels"][gid]):
        await ctx.send(embed=make_embed("❌ پیدا نشد","پنل یافت نشد."))
    else:
        await ctx.send(embed=make_embed("✅ حذف شد", f"پنل `{name}` حذف شد."))

# check command (both slash and prefix call this helper)
async def perform_check_and_send_internal(guild_obj, panel_name):
    data = load_data(); gid = str(guild_obj.id)
    if gid not in data["panels"]:
        return False, "هیچ پنلی برای این سرور ثبت نشده است."
    panel = None
    for p in data["panels"][gid]:
        if p["name"] == panel_name:
            panel = p; break
    if not panel:
        return False, "پنل یافت نشد."
    if panel["service"].startswith("youtube"):
        rss = youtube_rss_from_channel_link(panel["link"])
        if not rss:
            return False, "لینک کانال یوتیوب معتبر نیست (از کانال با /channel/ یا از channel_id استفاده کنید)."
        async with aiohttp.ClientSession() as session:
            parsed = await fetch_rss(session, rss)
            if not parsed or not parsed.entries:
                return False, "هیچ ویدیویی پیدا نشد."
            latest = parsed.entries[0]
            video_id = latest.get("yt_videoid") or ""
            video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else latest.get("link","")
            thumbnail = ""
            if latest.get("media_thumbnail"):
                try: thumbnail = latest.get("media_thumbnail")[0].get("url","")
                except: thumbnail = ""
            mapping = {"title": latest.get("title",""), "videourl": video_url, "thumbnail": thumbnail, "channelname": parsed.feed.get("title","")}
            try:
                filled = replace_placeholders_in_json_string(panel["webhook_json"], mapping)
                data_json = json.loads(filled)
                ch = bot.get_channel(panel["channel_id"])
                if not ch: return False, "کانال مشخص‌شده پیدا نشد."
                if isinstance(data_json, dict) and data_json.get("embeds"):
                    for e in data_json["embeds"]:
                        try:
                            emb = discord.Embed.from_dict(e)
                            await ch.send(embed=emb)
                        except Exception as e:
                            print("embed send error:", e)
                    return True, f"پیام تست در {ch.mention} ارسال شد."
                else:
                    await ch.send(f"🔔 تست: {mapping['title']} - {mapping['videourl']}")
                    return True, f"پیام تست در {ch.mention} ارسال شد."
            except Exception as e:
                return False, f"خطا در پردازش قالب JSON: {e}"
    else:
        return False, "فعلاً فقط یوتیوب پشتیبانی می‌شود."

@bot.tree.command(name="check", description="ارسال پیام تست از یک پنل")
async def slash_check(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)
    ok, msg = await perform_check_and_send_internal(interaction.guild, name)
    if ok:
        await interaction.followup.send(embed=make_embed("✅ ارسال شد", msg), ephemeral=True)
    else:
        await interaction.followup.send(embed=make_embed("❌ خطا", msg), ephemeral=True)

@bot.command(name="check")
async def prefix_check(ctx: commands.Context, name: str):
    ok, msg = await perform_check_and_send_internal(ctx.guild, name)
    if ok:
        await ctx.send(embed=make_embed("✅ ارسال شد", msg))
    else:
        await ctx.send(embed=make_embed("❌ خطا", msg))

# ---------- تسک چک یوتیوب (هر 5 دقیقه) ----------
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
                    try: thumbnail = newest.get("media_thumbnail")[0].get("url","")
                    except: thumbnail = ""
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

# ---------- اجرا ----------
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERROR: ENV var DISCORD_TOKEN را تنظیم نکرده‌اید.")
    else:
        bot.run(token)
# --- END bot.py ---
