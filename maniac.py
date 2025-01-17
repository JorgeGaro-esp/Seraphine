import discord
from discord.ext import commands
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import urllib.parse, urllib.request, re
import webserver

queues = {}
voice_clients = {}
youtube_base_url = 'https://www.youtube.com/'
youtube_results_url = youtube_base_url + 'results?'
youtube_watch_url = youtube_base_url + 'watch?v='
yt_dl_options = {
    "format": "bestaudio/best",  # Solo extrae el mejor formato de audio.
    "cookiefile": "cookies.txt",
    "quiet": True,  # Reduce los mensajes de log innecesarios.
    "extract_flat": True,  # Solo extrae metadatos, sin descargar el video completo.
    "noplaylist": True,  # No procesa listas de reproducción.
    "progress_hooks": [lambda d: None],  # Desactiva los hooks de progreso.
    "writethumbnail": False,  # No descarga miniaturas.
    "geo_bypass": True,  # Elimina restricciones geográficas (si es necesario).
    "source_address": None,  # Evita problemas con direcciones de red, si fuera necesario.
}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 1',  # Reducir tiempo de reconexión.
    'options': '-vn -filter:a "volume=0.25"'  # Ajuste para volumen y omitir video.
}

async def play_next(ctx):
    if queues.get(ctx.guild.id):
        link = queues[ctx.guild.id].pop(0)
        await play(ctx, link=link)

async def play(ctx, *, link):
    try:
        # Conectar al canal de voz si no está conectado
        vc = voice_clients.get(ctx.guild.id)
        if not vc or not vc.is_connected():
            vc = await ctx.author.voice.channel.connect()
            voice_clients[ctx.guild.id] = vc
    except Exception as e:
        await ctx.send(f"Error al conectar al canal de voz: {e}")
        return

    # Si el enlace no es de YouTube, buscar el video
    if youtube_base_url not in link:
        query_string = urllib.parse.urlencode({'search_query': link})
        content = urllib.request.urlopen(youtube_results_url + query_string)
        search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
        link = youtube_watch_url + search_results[0]

    # Extraer la información de YouTube usando yt-dlp
    data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
    song_url = data['url']
    title = data.get('title')
    thumbnail = data.get('thumbnail')
    player = discord.FFmpegOpusAudio(song_url, **ffmpeg_options)

    # Enviar mensaje de embed con la información de la canción
    embed = discord.Embed(title=f'**🎵 Now Playing: {title}**', color=discord.Color.blue())
    embed.set_image(url=thumbnail)
    await ctx.send(embed=embed, view=MusicControls(ctx))

    # Reproducir el audio y gestionar la siguiente canción cuando termine
    vc.play(player, after=lambda e: asyncio.ensure_future(play_next(ctx)))

class MusicControls(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.is_paused = False

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.danger, emoji="⏸️")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = voice_clients.get(self.ctx.guild.id)
        if vc:
            if vc.is_playing():
                vc.pause()
                button.label = "Resume"
                button.style = discord.ButtonStyle.success
                button.emoji = "▶️"
            elif vc.is_paused():
                vc.resume()
                button.label = "Pause"
                button.style = discord.ButtonStyle.danger
                button.emoji = "⏸️"
            await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, emoji="⏭️")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = voice_clients.get(self.ctx.guild.id)
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await asyncio.sleep(1)
            await play_next(self.ctx)
            await interaction.response.defer()

def run_bot():
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    intents = discord.Intents.default()
    intents.message_content = True
    client = commands.Bot(command_prefix=".", intents=intents)

    @client.event
    async def on_ready():
        print(f'{client.user} is now jamming')

    @client.command(name="p")
    async def play_command(ctx, *, link):
        await ctx.message.delete()
        await play(ctx, link=link)

    @client.command(name="q")
    async def queue(ctx, *, link):
        await ctx.message.delete()
        if ctx.guild.id not in queues:
            queues[ctx.guild.id] = []
        queues[ctx.guild.id].append(link)

        data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
        title = data.get('title')
        await ctx.send(f"Se ha añadido **{title}** a la cola")

    webserver.keep_alive()
    client.run(TOKEN, reconnect=True)
