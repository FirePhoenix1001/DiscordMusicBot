import sys
import os
import ctypes # 新增：用來強制載入 DLL 的工具

# --- 終極路徑補丁 ---
if hasattr(sys, '_MEIPASS'):
    # 打包後的環境
    base_path = sys._MEIPASS
    tools_path = os.path.join(base_path, "tools")
    # 關鍵：強迫 Windows 把 tools 加入 DLL 搜尋路徑
    if os.path.exists(tools_path):
        os.environ["PATH"] = tools_path + os.pathsep + os.environ["PATH"]
        if hasattr(os, 'add_dll_directory'): # 針對 Python 3.8+ 的新安全機制
            os.add_dll_directory(tools_path)
else:
    # 開發環境
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tools_path = os.path.join(base_path, "tools")

import discord

def force_load_opus():
    if discord.opus.is_loaded():
        return
    
    # 嘗試多種可能的路徑
    target_dll = os.path.join(tools_path, "libopus-0.dll")
    
    try:
        # 使用 ctypes 預載入 DLL，這能解決大多數「找不到模組」的報錯
        ctypes.CDLL(target_dll)
        discord.opus.load_opus(target_dll)
        print(f"[系統] Opus 庫強制載入成功！位置: {target_dll}")
    except Exception as e:
        print(f"[嚴重錯誤] 無法載入 Opus: {e}")

force_load_opus()

import subprocess
import sys
import os
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import random

# --- 1. PyInstaller 路徑處理函式 ---
def get_resource_path(relative_path):
    """ 取得檔案的絕對路徑，相容開發環境與 PyInstaller 打包環境 """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包後的暫存目錄
        return os.path.join(sys._MEIPASS, relative_path)
    # 開發環境：假設 main.py 在 src 資料夾下，根目錄就是上一層
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

# --- 2. 自動更新與環境檢查 ---
def sync_requirements():
    """ 確保虛擬環境內的套件是最新的 """
    print("正在檢查套件更新...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
        print("yt-dlp 更新檢查完成。")
    except Exception as e:
        print(f"套件更新跳過或失敗: {e}")

# 如果不是在打包後的環境，執行自動更新
if not hasattr(sys, '_MEIPASS'):
    sync_requirements()

# --- 3. 外部工具與路徑配置 ---
# 定義工具的正確位置
TOOLS_DIR = get_resource_path("tools")
FFMPEG_EXE_PATH = os.path.join(TOOLS_DIR, "ffmpeg.exe")
DENO_EXE_PATH = os.path.join(TOOLS_DIR, "deno.exe")

# 注入環境變數，讓 yt-dlp 能找到 deno.exe
os.environ["PATH"] = TOOLS_DIR + os.pathsep + os.environ["PATH"]

# 配置變數
ALLOWED_CHANNELS = ['music', 'bot-commands']

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'allow_untracked': True,
    'remote_components': ['ejs:github'], # 必須是 list 格式
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 
    'options': '-vn'
}

# --- 4. 音樂播放器邏輯 ---
class MusicPlayer:
    def __init__(self, bot, guild_id):
        self.bot = bot
        self.guild_id = guild_id
        self.queue = []
        self.index = 0
        self.loop = False
        self.shuffle = False
        self.current = None
        self.last_panel = None
        self.manual_skip = False

    def get_next(self, force_index=None):
        if not self.queue: return None
        
        if force_index is not None:
            self.index = force_index
        elif self.manual_skip:
            self.manual_skip = False
        elif self.current is None:
            self.index = 0
        elif self.shuffle:
            self.index = random.randrange(len(self.queue))
        else:
            self.index += 1

        if self.index >= len(self.queue):
            if self.loop: self.index = 0
            else:
                self.current = None
                return None
        
        self.current = self.queue[self.index]
        return self.current

players = {}

def create_music_embed(player):
    if not player.current:
        return discord.Embed(title="⌛ 播放已結束", description="清單已空，可點擊 **⏯️** 重播或繼續點歌", color=0x2f3136)
    
    embed = discord.Embed(title=f"🎶 {player.current['title']}", url=player.current['webpage_url'], color=discord.Color.blurple())
    if player.current.get('thumbnail'):
        embed.set_image(url=player.current['thumbnail'])
    
    l_status = "✅" if player.loop else "❌"
    s_status = "✅" if player.shuffle else "❌"
    embed.set_footer(text=f"歌曲序號：{player.index + 1}/{len(player.queue)} | 循環：{l_status} | 隨機：{s_status}")
    return embed

class SongSelect(discord.ui.Select):
    def __init__(self, player, ctx):
        options = [discord.SelectOption(label=f"{i+1}. {s['title'][:90]}", value=str(i)) 
                   for i, s in enumerate(player.queue[:25])]
        super().__init__(placeholder="📜 展開播放清單...", options=options)
        self.player, self.ctx = player, ctx

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        target_index = int(self.values[0])
        await start_playing(self.ctx, self.player, force_index=target_index)

class MusicControlView(discord.ui.View):
    def __init__(self, player, ctx):
        super().__init__(timeout=None)
        self.player, self.ctx = player, ctx
        if player.queue:
            self.add_item(SongSelect(player, ctx))

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.grey, row=1)
    async def prev(self, interaction: discord.Interaction, button):
        if self.player.index > 0:
            await start_playing(self.ctx, self.player, force_index=self.player.index - 1)
        await interaction.response.defer()

    @discord.ui.button(label="⏯️", style=discord.ButtonStyle.green, row=1)
    async def play_pause(self, interaction: discord.Interaction, button):
        vc = self.ctx.voice_client
        if vc.is_playing(): vc.pause()
        elif vc.is_paused(): vc.resume()
        else: await start_playing(self.ctx, self.player)
        await interaction.response.defer()

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.grey, row=1)
    async def next(self, interaction: discord.Interaction, button):
        if self.ctx.voice_client:
            self.ctx.voice_client.stop()
        await interaction.response.defer()

    @discord.ui.button(label="🔁 循環", style=discord.ButtonStyle.blurple, row=2)
    async def loop_btn(self, interaction: discord.Interaction, button):
        self.player.loop = not self.player.loop
        await interaction.response.edit_message(embed=create_music_embed(self.player), view=self)

    @discord.ui.button(label="🔀 隨機", style=discord.ButtonStyle.blurple, row=2)
    async def shuffle_btn(self, interaction: discord.Interaction, button):
        self.player.shuffle = not self.player.shuffle
        await interaction.response.edit_message(embed=create_music_embed(self.player), view=self)

    @discord.ui.button(label="⏹️ 退出", style=discord.ButtonStyle.danger, row=2)
    async def stop_btn(self, interaction: discord.Interaction, button):
        await self.ctx.invoke(self.player.bot.get_command('stop'))
        await interaction.response.defer()

# --- 5. 播放與介面管理 ---
async def start_playing(ctx, player, force_index=None):
    if not ctx.voice_client: return
    
    if force_index is not None:
        player.manual_skip = True
        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            player.index = force_index 
            ctx.voice_client.stop()
            return 

    next_song = player.get_next(force_index=force_index)
    
    if next_song:
        source = discord.FFmpegPCMAudio(next_song['url'], executable=FFMPEG_EXE_PATH, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            asyncio.run_coroutine_threadsafe(start_playing(ctx, player), bot.loop)

        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            ctx.voice_client.stop()

        ctx.voice_client.play(source, after=after_playing)

        embed = create_music_embed(player)
        view = MusicControlView(player, ctx)

        if player.last_panel:
            try: await player.last_panel.edit(embed=embed, view=view)
            except: player.last_panel = await ctx.send(embed=embed, view=view)
        else:
            player.last_panel = await ctx.send(embed=embed, view=view)
    else:
        player.current = None
        if player.last_panel:
            await player.last_panel.edit(embed=create_music_embed(player), view=MusicControlView(player, ctx))

# --- 6. 機器人啟動入口 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.command()
@commands.check(lambda ctx: ctx.channel.name in ALLOWED_CHANNELS)
async def play(ctx, url: str = None):
    player = players.get(ctx.guild.id) or MusicPlayer(bot, ctx.guild.id)
    players[ctx.guild.id] = player

    if url:
        if not ctx.voice_client:
            if ctx.author.voice: await ctx.author.voice.channel.connect()
            else: return await ctx.send("請先進入語音頻道。")
        
        async with ctx.typing():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
                player.queue.append({
                    'url': info['url'], 'title': info['title'], 
                    'thumbnail': info.get('thumbnail'), 'webpage_url': info.get('webpage_url')
                })

    if ctx.voice_client and not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
        if player.queue: await start_playing(ctx, player)
    else:
        if player.last_panel:
            await player.last_panel.edit(view=MusicControlView(player, ctx))

@bot.command()
async def menu(ctx):
    try: await ctx.message.delete()
    except: pass
    player = players.get(ctx.guild.id)
    if player:
        if player.last_panel: 
            try: await player.last_panel.delete()
            except: pass
        player.last_panel = await ctx.send(embed=create_music_embed(player), view=MusicControlView(player, ctx))

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        player = players.get(ctx.guild.id)
        if player and player.last_panel:
            try: await player.last_panel.delete()
            except: pass
        if ctx.guild.id in players: del players[ctx.guild.id]

# --- Token 啟動邏輯 ---
if __name__ == "__main__":
    # 如果 Token 還是預設值，嘗試從環境變數或 input 取得
    FINAL_TOKEN = os.getenv('DISCORD_TOKEN') or bot.run("")
    
    # 注意：bot.run 是阻塞的，如果上面的寫法報錯，請直接改回：
    # bot.run("你的Token")