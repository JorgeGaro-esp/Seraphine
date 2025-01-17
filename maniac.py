import discord
from discord.ext import commands
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import urllib.parse
import re
import webserver

queues = {}
voice_clients = {}
youtube_base_url = 'https://www.youtube.com/'
youtube_results_url = youtube_base_url + 'results?'
youtube_watch_url = youtube_base_url + 'watch?v='
yt_dl_options = {
    "format": "bestaudio/best",
    "cookiefile": "cookies.txt",
    "quiet": True  # Desactivar la salida en consola de yt-dlp
}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)
ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn -filter:a "volume=0.25"'}

async def play_next(ctx):
    """ Reproducir la siguiente canción de la cola de manera eficiente """
    if queues.get(ctx.guild.id):
        link = queues[ctx.guild.id].pop(0)
        await play(ctx, link=link)

async def play(ctx, *, link):
    """ Reproducir una canción de la cola """
    vc = voice_clients.get(ctx.guild.id)

    # Reutilizar la conexión de voz si ya estamos conectados
    if not vc or not vc.is_connected():
        try:
            # Comprobar si el bot tiene permisos para unirse y hablar
            if not ctx.author.voice:
                await ctx.send("¡Necesitas estar en un canal de voz para reproducir música!")
                return
            if not ctx.author.voice.channel.permissions_for(ctx.guild.me).connect or not ctx.author.voice.channel.permissions_for(ctx.guild.me).speak:
                await ctx.send("No tengo permisos para unirme o hablar en ese canal de voz.")
                return
            
            vc = await ctx.author.voice.channel.connect()
            voice_clients[ctx.guild.id] = vc
        except Exception as e:
            await ctx.send(f"Error al conectar al canal de voz: {e}")
            return

    # Si es un enlace de YouTube, no necesitamos buscarlo
    if youtube_base_url not in link:
        query_string = urllib.parse.urlencode({'search_query': link})
        content = await asyncio.to_thread(urllib.request.urlopen, youtube_results_url + query_string)
        search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
        link = youtube_watch_url + search_results[0]

    # Obtener datos de la canción de forma eficiente
    data = await asyncio.to_thread(ytdl.extract_info, link, download=False)
    song_url = data['url']
    title = data.get('title')
    thumbnail = data.get('thumbnail')

    player = discord.FFmpegOpusAudio(song_url, **ffmpeg_options)

    # No es necesario cargar una nueva Embed cada vez si es repetitivo
    embed = discord.Embed(title=f'**🎵 Now Playing: {title}**', color=discord.Color.purple())
    embed.set_image(url=thumbnail)
    await ctx.send(embed=embed, view=MusicControls(ctx))

    # Reproducir la canción sin detenerse
    if not vc.is_playing():
        vc.play(player, after=lambda e: asyncio.create_task(play_next(ctx)))

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
            await interaction.response.defer()  # Mantenemos la interacción activa
            vc.stop()
            await asyncio.sleep(1)
            await play_next(self.ctx)

# Clase para el Bot, usando commands.Bot
class MusicBot(commands.Bot):
    async def on_ready(self):
        print(f'{self.user} is now jamming')

    # Definir el comando 'p' correctamente
    @commands.command(name="p")
    async def play_command(self, ctx, *, link):
        """ Comando para reproducir música """
        try:
            await ctx.message.delete()
        except discord.errors.NotFound:
            pass  # El mensaje ya fue eliminado
        await play(ctx, link=link)

    @commands.command(name="q")
    async def queue(self, ctx, *, link):
        """ Comando para agregar canciones a la cola """
        try:
            await ctx.message.delete()
        except discord.errors.NotFound:
            pass  # El mensaje ya fue eliminado

        if ctx.guild.id not in queues:
            queues[ctx.guild.id] = []
        queues[ctx.guild.id].append(link)

        # Obtener datos de la canción de forma eficiente
        data = await asyncio.to_thread(ytdl.extract_info, link, download=False)
        title = data.get('title')
        await ctx.send(f"Se ha añadido **{title}** a la cola")

    @commands.command(name="queue")
    async def show_queue(self, ctx):
        """ Comando para ver la cola de reproducción """
        if ctx.guild.id not in queues or not queues[ctx.guild.id]:
            await ctx.send("La cola está vacía.")
            return
        
        queue_list = "\n".join([f"{idx+1}. {item}" for idx, item in enumerate(queues[ctx.guild.id])])
        await ctx.send(f"**Cola de música:**\n{queue_list}")

    @commands.command(name="disconnect")
    async def disconnect_bot(self, ctx):
        """ Comando para desconectar el bot del canal de voz """
        vc = voice_clients.get(ctx.guild.id)
        if vc and vc.is_connected():
            await vc.disconnect()
            del voice_clients[ctx.guild.id]
            await ctx.send("Me he desconectado del canal de voz.")
        else:
            await ctx.send("No estoy conectado a un canal de voz.")

def run_bot():
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    intents = discord.Intents.default()
    intents.message_content = True
    client = MusicBot(command_prefix=".", intents=intents)

    webserver.keep_alive()
    client.run(TOKEN, reconnect=True)
