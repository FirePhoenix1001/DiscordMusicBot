import sys, os, ctypes, subprocess, discord, yt_dlp, asyncio, random
from discord.ext import commands

# --- 環境設定 ---
IS_BUNDLE = hasattr(sys, '_MEIPASS')
BASE_PATH = sys._MEIPASS if IS_BUNDLE else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(BASE_PATH, "tools")
os.environ["PATH"] = f"{TOOLS_DIR}{os.pathsep}{os.environ['PATH']}"

if not discord.opus.is_loaded():
    try:
        dll = os.path.join(TOOLS_DIR, "libopus-0.dll")
        ctypes.CDLL(dll); discord.opus.load_opus(dll)
    except: pass

# --- 配置 ---
YDL_OPTS = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'remote_components': ['ejs:github']}
FF_OPTS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

def create_music_embed(p):
    is_end = p.current is None
    emb = discord.Embed(title=f"🎶 {p.current['title']}" if not is_end else "⌛ 播放已結束", 
                        url=p.current.get('webpage_url') if not is_end else None,
                        description="清單已空，可點擊 **⏯️** 重播" if is_end else None, 
                        color=0x2f3136 if is_end else 0x5865F2)
    if not is_end and p.current.get('thumbnail'): emb.set_image(url=p.current['thumbnail'])
    emb.set_footer(text=f"歌曲：{p.index + 1}/{len(p.queue)} | 循環：{'✅' if p.loop else '❌'} | 隨機：{'✅' if p.shuffle else '❌'}")
    return emb

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
        self.current = self.queue[self.index]; return self.current

players = {}

class SongSelect(discord.ui.Select):
    def __init__(self, player, ctx):
        options = [discord.SelectOption(label=f"{i+1}. {s['title'][:90]}", value=str(i)) for i, s in enumerate(player.queue[:25])]
        super().__init__(placeholder="📜 展開播放清單...", options=options)
        self.player, self.ctx = player, ctx
    async def callback(self, inter):
        await inter.response.defer()
        await play_next(self.ctx, self.player, int(self.values[0]))

class MusicControlView(discord.ui.View):
    def __init__(self, player, ctx):
        super().__init__(timeout=None); self.player, self.ctx = player, ctx
        if player.queue: self.add_item(SongSelect(player, ctx))

    async def acknowledge(self, inter):
        # 統一處理按鈕更新，確保不會交互失敗
        await inter.response.edit_message(embed=create_music_embed(self.player), view=self)

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.grey, row=1)
    async def prev(self, inter, btn): 
        await inter.response.defer(); await play_next(self.ctx, self.player, max(0, self.player.index-1))
    
    @discord.ui.button(label="⏯️", style=discord.ButtonStyle.green, row=1)
    async def pp(self, inter, btn):
        vc = self.ctx.voice_client
        if vc and vc.is_playing(): vc.pause()
        elif vc and vc.is_paused(): vc.resume()
        else: await play_next(self.ctx, self.player)
        await self.acknowledge(inter)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.grey, row=1)
    async def next(self, inter, btn): await inter.response.defer(); self.ctx.voice_client.stop()

    @discord.ui.button(label="🔁 循環", style=discord.ButtonStyle.blurple, row=2)
    async def lp(self, inter, btn): self.player.loop = not self.player.loop; await self.acknowledge(inter)

    @discord.ui.button(label="🔀 隨機", style=discord.ButtonStyle.blurple, row=2)
    async def sf(self, inter, btn): self.player.shuffle = not self.player.shuffle; await self.acknowledge(inter)

    @discord.ui.button(label="💡 說明", style=discord.ButtonStyle.secondary, row=2)
    async def hp(self, inter, btn):
        e = discord.Embed(title="📖 說明", description="• **!play [網址]**：點歌\n• **!menu**：呼叫面板", color=0x5865F2)
        await inter.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="⏹️ 退出", style=discord.ButtonStyle.danger, row=2)
    async def st(self, inter, btn): await self.ctx.invoke(self.ctx.bot.get_command('stop')); await inter.response.defer()

async def play_next(ctx, player, force_idx=None):
    if not ctx.voice_client: return
    if force_idx is not None and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        player.manual_skip, player.index = True, force_idx
        return ctx.voice_client.stop()
    song = player.get_next(force_idx)
    if song:
        if ctx.voice_client.is_playing(): ctx.voice_client.stop()
        ctx.voice_client.play(discord.FFmpegPCMAudio(song['url'], executable=os.path.join(TOOLS_DIR, "ffmpeg.exe"), **FF_OPTS),
                             after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, player), ctx.bot.loop))
    else: player.current = None
    
    view, emb = MusicControlView(player, ctx), create_music_embed(player)
    if player.last_panel:
        try: await player.last_panel.edit(embed=emb, view=view); return
        except: pass
    player.last_panel = await ctx.send(embed=emb, view=view)

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
        p.last_panel = None
        # 重新呼叫 play_next 內的更新邏輯來產生新面板
        view, emb = MusicControlView(p, ctx), create_music_embed(p)
        p.last_panel = await ctx.send(embed=emb, view=view)

@bot.command()
async def stop(ctx):
    if ctx.voice_client: await ctx.voice_client.disconnect()
    p = players.pop(ctx.guild.id, None)
    if p and p.last_panel:
        try: await p.last_panel.delete()
        except: pass

bot.run(os.getenv('DISCORD_TOKEN') or "你的TOKEN")