import sys, os, ctypes, subprocess, discord, yt_dlp, asyncio, random
from discord.ext import commands

# --- 1. 環境與路徑優化 ---
IS_BUNDLE = hasattr(sys, '_MEIPASS')
BASE_PATH = sys._MEIPASS if IS_BUNDLE else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(BASE_PATH, "tools")
os.environ["PATH"] = f"{TOOLS_DIR}{os.pathsep}{os.environ['PATH']}"

# 強制載入 Opus (僅執行一次)
if not discord.opus.is_loaded():
    try:
        dll = os.path.join(TOOLS_DIR, "libopus-0.dll")
        ctypes.CDLL(dll)
        discord.opus.load_opus(dll)
    except Exception as e: print(f"Opus Error: {e}")

# 僅在開發環境更新套件
if not IS_BUNDLE:
    subprocess.Popen([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"], stdout=subprocess.DEVNULL)

# --- 2. 常數與配置 ---
FFMPEG_PATH = os.path.join(TOOLS_DIR, "ffmpeg.exe")
YDL_OPTS = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'remote_components': ['ejs:github']}
FF_OPTS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

# --- 3. 核心邏輯：播放器 ---
class MusicPlayer:
    def __init__(self, bot, guild_id):
        self.bot, self.guild_id, self.queue, self.index = bot, guild_id, [], 0
        self.loop, self.shuffle, self.current, self.last_panel, self.manual_skip = False, False, None, None, False

    def get_next(self, force_idx=None):
        if not self.queue: return None
        if force_idx is not None: self.index = force_idx
        elif not self.manual_skip:
            if self.current is None: self.index = 0
            else: self.index = random.randrange(len(self.queue)) if self.shuffle else self.index + 1
        self.manual_skip = False
        
        if self.index >= len(self.queue):
            if self.loop: self.index = 0
            else: return None
        self.current = self.queue[self.index]
        return self.current

players = {}

async def update_panel(ctx, player):
    is_end = player.current is None
    emb = discord.Embed(title=f"🎶 {player.current['title']}" if not is_end else "⌛ 播放已結束", 
                        url=player.current.get('webpage_url') if not is_end else None,
                        description="清單已空，可點擊 **⏯️** 重播" if is_end else None, color=0x2f3136 if is_end else 0x5865F2)
    if not is_end and player.current.get('thumbnail'): emb.set_image(url=player.current['thumbnail'])
    emb.set_footer(text=f"歌曲：{player.index + 1}/{len(player.queue)} | 循環：{'✅' if player.loop else '❌'} | 隨機：{'✅' if player.shuffle else '❌'}")
    
    view = MusicControlView(player, ctx)
    if player.last_panel:
        try: await player.last_panel.edit(embed=emb, view=view); return
        except: pass
    player.last_panel = await ctx.send(embed=emb, view=view)

async def play_next(ctx, player, force_idx=None):
    if not ctx.voice_client: return
    if force_idx is not None and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        player.manual_skip = True
        player.index = force_idx
        return ctx.voice_client.stop()

    song = player.get_next(force_idx)
    if song:
        if ctx.voice_client.is_playing(): ctx.voice_client.stop()
        ctx.voice_client.play(discord.FFmpegPCMAudio(song['url'], executable=FFMPEG_PATH, **FF_OPTS),
                             after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, player), ctx.bot.loop))
    else: player.current = None
    await update_panel(ctx, player)

# --- 4. UI 元件 ---
class SongSelect(discord.ui.Select):
    def __init__(self, player, ctx):
        super().__init__(placeholder="📜 展開播放清單...", options=[discord.SelectOption(label=f"{i+1}. {s['title'][:90]}", value=str(i)) for i, s in enumerate(player.queue[:25])])
        self.player, self.ctx = player, ctx
    async def callback(self, inter):
        await inter.response.defer(); await play_next(self.ctx, self.player, int(self.values[0]))

class MusicControlView(discord.ui.View):
    def __init__(self, player, ctx):
        super().__init__(timeout=None); self.player, self.ctx = player, ctx
        if player.queue: self.add_item(SongSelect(player, ctx))

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.grey, row=1)
    async def prev(self, inter, btn): 
        await inter.response.defer(); await play_next(self.ctx, self.player, max(0, self.player.index-1))
    
    @discord.ui.button(label="⏯️", style=discord.ButtonStyle.green, row=1)
    async def pp(self, inter, btn):
        vc = self.ctx.voice_client
        if vc.is_playing(): vc.pause()
        elif vc.is_paused(): vc.resume()
        else: await play_next(self.ctx, self.player)
        await inter.response.defer()

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.grey, row=1)
    async def next(self, inter, btn): await inter.response.defer(); self.ctx.voice_client.stop()

    @discord.ui.button(label="🔁 循環", style=discord.ButtonStyle.blurple, row=2)
    async def lp(self, inter, btn): self.player.loop = not self.player.loop; await inter.response.edit_message(embed=create_music_embed(self.player), view=self)

    @discord.ui.button(label="🔀 隨機", style=discord.ButtonStyle.blurple, row=2)
    async def sf(self, inter, btn): self.player.shuffle = not self.player.shuffle; await inter.response.edit_message(embed=create_music_embed(self.player), view=self)

    @discord.ui.button(label="💡 說明", style=discord.ButtonStyle.secondary, row=2)
    async def hp(self, inter, btn):
        e = discord.Embed(description="• **!play [網址]**：點歌\n• **!menu**：呼叫面板", color=0x5865F2)
        await inter.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="⏹️ 退出", style=discord.ButtonStyle.danger, row=2)
    async def st(self, inter, btn): await self.ctx.invoke(self.ctx.bot.get_command('stop')); await inter.response.defer()

# --- 5. 指令系統 ---
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

@bot.command()
async def play(ctx, url=None):
    if ctx.channel.name not in ['music', 'bot-commands']: return
    p = players.setdefault(ctx.guild.id, MusicPlayer(bot, ctx.guild.id))
    if url:
        if not ctx.voice_client:
            if ctx.author.voice: await ctx.author.voice.channel.connect()
            else: return await ctx.send("請進入語音頻道")
        async with ctx.typing():
            with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                d = ydl.extract_info(url, download=False)
                p.queue.append({'url': d['url'], 'title': d['title'], 'thumbnail': d.get('thumbnail'), 'webpage_url': d.get('webpage_url')})
    if ctx.voice_client and not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused() and p.queue: await play_next(ctx, p)
    elif p.last_panel: await p.last_panel.edit(view=MusicControlView(p, ctx))

@bot.command()
async def menu(ctx):
    p = players.get(ctx.guild.id)
    if p:
        try: await ctx.message.delete()
        except: pass
        if p.last_panel: 
            try: await p.last_panel.delete()
            except: pass
        p.last_panel = None; await update_panel(ctx, p)

@bot.command()
async def stop(ctx):
    if ctx.voice_client: await ctx.voice_client.disconnect()
    p = players.pop(ctx.guild.id, None)
    if p and p.last_panel:
        try: await p.last_panel.delete()
        except: pass

bot.run(os.getenv('DISCORD_TOKEN') or "你的TOKEN")