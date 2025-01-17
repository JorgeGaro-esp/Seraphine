import discord
from discord.ext import commands
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import urllib.parse, urllib.request, re
import webserver

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
        "cookiesfrombrowser": "cookies.txt"  # Asegúrate de que cookies.txt esté en el directorio correcto
    }
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5','options': '-vn -filter:a "volume=0.25"'}

    @client.event
    async def on_ready():
        print(f'{client.user} is now jamming')

    async def play_next(ctx):
        if queues[ctx.guild.id] != []:
            link = queues[ctx.guild.id].pop(0)
            await play(ctx, link=link)

    @client.command(name="play")
    async def play(ctx, *, link):
        try:
            # Intento de conexión al canal de voz
            voice_client = await ctx.author.voice.channel.connect()
            voice_clients[voice_client.guild.id] = voice_client
        except Exception as e:
            print(f"Error al conectar al canal de voz: {e}")

        try:
            # Verificación de la URL y obtención de información de YouTube
            if youtube_base_url not in link:
                query_string = urllib.parse.urlencode({'search_query': link})
                content = urllib.request.urlopen(youtube_results_url + query_string)
                search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
                link = youtube_watch_url + search_results[0]

            loop = asyncio.get_event_loop()
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
            except Exception as e:
                print(f"Error al extraer información de YouTube: {e}")
                return

            song = data['url']
            player = discord.FFmpegOpusAudio(song, **ffmpeg_options)

            # Reproducción del audio en el canal de voz
            try:
                voice_clients[ctx.guild.id].play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            except Exception as e:
                print(f"Error al reproducir la canción: {e}")
        except Exception as e:
            print(f"Error general al intentar reproducir la canción: {e}")

    @client.command(name="clear_queue")
    async def clear_queue(ctx):
        try:
            if ctx.guild.id in queues:
                queues[ctx.guild.id].clear()
                await ctx.send("Queue cleared!")
            else:
                await ctx.send("There is no queue to clear")
        except Exception as e:
            print(f"Error al limpiar la cola: {e}")

    @client.command(name="pause")
    async def pause(ctx):
        try:
            voice_clients[ctx.guild.id].pause()
        except Exception as e:
            print(f"Error al pausar la reproducción: {e}")

    @client.command(name="resume")
    async def resume(ctx):
        try:
            voice_clients[ctx.guild.id].resume()
        except Exception as e:
            print(f"Error al reanudar la reproducción: {e}")

    @client.command(name="stop")
    async def stop(ctx):
        try:
            voice_clients[ctx.guild.id].stop()
            await voice_clients[ctx.guild.id].disconnect()
            del voice_clients[ctx.guild.id]
        except Exception as e:
            print(f"Error al detener la reproducción: {e}")

    @client.command(name="queue")
    async def queue(ctx, *, url):
        try:
            if ctx.guild.id not in queues:
                queues[ctx.guild.id] = []
            queues[ctx.guild.id].append(url)
            await ctx.send("Added to queue!")
        except Exception as e:
            print(f"Error al agregar a la cola: {e}")

    webserver.keep_alive()
    client.run(TOKEN)
