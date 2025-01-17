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
    "format": "bestaudio/best",
    "cookiefile": "cookies.txt"
}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)
ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5','options': '-vn -filter:a "volume=0.25"'}

async def play_next(ctx):
    # Verifica si hay canciones en la cola
    if queues.get(ctx.guild.id) and queues[ctx.guild.id]:
        link = queues[ctx.guild.id].pop(0)  # Obtener la siguiente canción
        await play(ctx, link=link)  # Reproducir la siguiente canción
    else:
        # Si la cola está vacía, desconectar y avisar al usuario
        vc = voice_clients.get(ctx.guild.id)
        if vc and vc.is_connected():
            await vc.disconnect()  # Desconectar del canal de voz
        await ctx.send("La cola está vacía. No hay más canciones para reproducir.")

async def play(ctx, *, link):
    try:
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
        # Verificar si encontramos resultados antes de intentar acceder
        if not search_results:
            await ctx.send("No se encontraron resultados para la búsqueda.")
            return
        link = youtube_watch_url + search_results[0]

    data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
    song_url = data['url']
    title = data.get('title')
    thumbnail = data.get('thumbnail')
    player = discord.FFmpegOpusAudio(song_url, **ffmpeg_options)

    embed = discord.Embed(title=f'**🎵 Now Playing: {title}**', color=discord.Color.blue())
    embed.set_image(url=thumbnail)
    await ctx.send(embed=embed, view=MusicControls(ctx))

    vc.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))

class MusicControls(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)  # Desactiva el timeout de la vista
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

            # Actualizamos el mensaje con la nueva vista
            await interaction.response.edit_message(view=self)  # Actualiza el mensaje con la nueva vista

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, emoji="⏭️")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = voice_clients.get(self.ctx.guild.id)
        if vc and (vc.is_playing() or vc.is_paused()):
            # Deferimos la interacción para evitar que caduque
            await interaction.response.defer()  # Solo lo hacemos una vez

            vc.stop()  # Detiene la canción actual

            # Esperamos brevemente para asegurarnos de que la canción se detenga antes de seguir
            await asyncio.sleep(1)

            # Reproducimos la siguiente canción en la cola
            await play_next(self.ctx)

            # Confirmamos la acción (puedes agregar algo como una respuesta de mensaje si es necesario)
            await interaction.followup.send("La canción se ha saltado y ahora se está reproduciendo la siguiente.")

def run_bot():
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    intents = discord.Intents.default()
    intents.message_content = True
    
    # Crear el objeto `client` antes de usarlo
    client = commands.Bot(command_prefix=".", intents=intents)

    # Eventos y comandos deben estar dentro de esta función después de que `client` esté creado
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

        # Log la cola para verificar si se agrega correctamente
        print(f"Queue for {ctx.guild.id}: {queues[ctx.guild.id]}")

        data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
        title = data.get('title')
        await ctx.send(f"Se ha añadido **{title}** a la cola")

    # Mantiene la web activa (si es necesario)
    webserver.keep_alive()

    # Corre el bot
    client.run(TOKEN, reconnect=True)
