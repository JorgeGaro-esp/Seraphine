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
        "cookiefile": "cookies.txt"
    }
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn -filter:a "volume=0.25"'}

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
            voice_client = await ctx.author.voice.channel.connect()
            voice_clients[voice_client.guild.id] = voice_client
        except Exception as e:
            print(f"Error al conectar al canal de voz: {e}")

        try:
            if youtube_base_url not in link:
                query_string = urllib.parse.urlencode({'search_query': link})
                content = urllib.request.urlopen(youtube_results_url + query_string)
                search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
                link = youtube_watch_url + search_results[0]

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
            song = data['url']
            player = discord.FFmpegOpusAudio(song, **ffmpeg_options)

            voice_clients[ctx.guild.id].play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            await ctx.send("Reproduciendo canción!")
        except Exception as e:
            print(f"Error general al intentar reproducir la canción: {e}")
            await ctx.send("No se pudo reproducir la canción.")

    @client.command(name="clear_queue")
    async def clear_queue(ctx):
        try:
            if ctx.guild.id in queues:
                queues[ctx.guild.id].clear()
                await ctx.send("Cola limpiada!")
            else:
                await ctx.send("No hay cola que limpiar.")
        except Exception as e:
            print(f"Error al limpiar la cola: {e}")

    @client.command(name="pause")
    async def pause(ctx):
        try:
            voice_clients[ctx.guild.id].pause()
            await ctx.send("Canción pausada!")
        except Exception as e:
            print(f"Error al pausar la reproducción: {e}")
            await ctx.send("No se pudo pausar la canción.")

    @client.command(name="resume")
    async def resume(ctx):
        try:
            voice_clients[ctx.guild.id].resume()
            await ctx.send("Canción reanudada!")
        except Exception as e:
            print(f"Error al reanudar la reproducción: {e}")
            await ctx.send("No se pudo reanudar la canción.")

    @client.command(name="stop")
    async def stop(ctx):
        try:
            voice_clients[ctx.guild.id].stop()
            await voice_clients[ctx.guild.id].disconnect()
            del voice_clients[ctx.guild.id]
            await ctx.send("Reproducción detenida y desconectado del canal de voz!")
        except Exception as e:
            print(f"Error al detener la reproducción: {e}")
            await ctx.send("No se pudo detener la reproducción.")

    @client.command(name="queue")
    async def queue(ctx, *, url):
        try:
            if ctx.guild.id not in queues:
                queues[ctx.guild.id] = []
            queues[ctx.guild.id].append(url)
            await ctx.send("Añadido a la cola!")
        except Exception as e:
            print(f"Error al agregar a la cola: {e}")
            await ctx.send("No se pudo añadir a la cola.")

    webserver.keep_alive()
    client.run(TOKEN)
