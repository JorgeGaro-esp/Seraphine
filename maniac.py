import discord
from discord.ext import commands
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import urllib.parse, urllib.request, re
import webserver

class MusicControls(discord.ui.View):
    def __init__(self, ctx, voice_clients, queues, client):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.voice_clients = voice_clients
        self.queues = queues
        self.client = client

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.secondary, emoji="⏸️")
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.voice_clients.get(self.ctx.guild.id)
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("Paused ⏸️", ephemeral=True)

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.success, emoji="▶️")
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.voice_clients.get(self.ctx.guild.id)
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("Resumed ▶️", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, emoji="⏭️")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.voice_clients.get(self.ctx.guild.id)
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("Skipped ⏭️", ephemeral=True)


def run_bot():
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    intents = discord.Intents.default()
    intents.message_content = True
    client = commands.Bot(command_prefix=".", intents=intents)

    queues = {}
    voice_clients = {}
    youtube_base_url = 'https://www.youtube.com/'
    youtube_results_url = youtube_base_url + 'results?'
    youtube_watch_url = youtube_base_url + 'watch?v='
    yt_dl_options = {
        "format": "bestaudio/best",
        "cookiefile": "cookies.txt"
    }
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5','options': '-vn -filter:a "volume=0.25"'}

    @client.event
    async def on_ready():
        print(f'{client.user} is now jamming')

    async def play_next(ctx):
        if queues[ctx.guild.id]:
            link = queues[ctx.guild.id].pop(0)
            await play(ctx, link=link)

    @client.command(name="play")
    async def play(ctx, *, link):
        await ctx.message.delete()
        try:
            vc = voice_clients.get(ctx.guild.id)
            if not vc or not vc.is_connected():
                vc = await ctx.author.voice.channel.connect()
                voice_clients[ctx.guild.id] = vc
        except Exception as e:
            await ctx.send(f"Error al conectar al canal de voz: {e}")
            return

        if youtube_base_url not in link:
            query_string = urllib.parse.urlencode({'search_query': link})
            content = urllib.request.urlopen(youtube_results_url + query_string)
            search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
            link = youtube_watch_url + search_results[0]

        data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
        song_url = data['url']
        title = data.get('title')
        thumbnail = data.get('thumbnail')
        player = discord.FFmpegOpusAudio(song_url, **ffmpeg_options)

        embed = discord.Embed(title=f'Now Playing: {title}', color=discord.Color.blue())
        embed.set_thumbnail(url=thumbnail)
        await ctx.send(embed=embed, view=MusicControls(ctx, voice_clients, queues, client))

        vc.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))

    webserver.keep_alive()
    client.run(TOKEN)
