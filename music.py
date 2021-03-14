# ANCHOR import
import discord, asyncio, os, youtube_dl, functools, itertools, math, random, re
import mysql.connector, json, io, textwrap, contextlib

from discord.ext import commands
from async_timeout import timeout

from discord.ext.buttons import Paginator
from discord.ext import buttons

from traceback import format_exception
from discord.ext.commands.cooldowns import BucketType

from time import gmtime, strftime

class VoiceError(Exception):
    pass

class YTDLError(Exception):
    pass

class YTDLSource(discord.PCMVolumeTransformer):
    # ANCHOR -- YTDLSource --
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': False,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -loglevel -8',
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(self, ctx: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        # ANCHOR __init__
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        date = data.get('upload_date')
        self.upload_date = date[6:8] + '.' + date[4:6] + '.' + date[0:4]
        self.title = data.get('title')
        self.title_limited = self.parse_limited_title(str(data.get('title')))
        self.title_limited_embed = self.parse_limited_title_embed(str(data.get('title')))
        self.thumbnail = data.get('thumbnail')
        self.description = data.get('description')
        self.duration = self.parse_duration(int(data.get('duration')))
        self.duration_raw = int(data.get('duration'))
        self.tags = data.get('tags')
        self.url = data.get('webpage_url')
        self.views = self.parse_number(int(data.get('view_count')))
        self.likes = self.parse_number(int(data.get('like_count')))
        self.dislikes = self.parse_number(int(data.get('dislike_count')))
        self.stream_url = data.get('url')

    def __str__(self):
        return f'**{self.title}** by **{self.uploader}**'

    @classmethod
    async def search_source(self, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None, bot):
        # ANCHOR search_source
        self.bot = bot
        channel = ctx.channel

        loop = loop or asyncio.get_event_loop()

        self.search_query = '%s%s:%s' % ('ytsearch', 10, ''.join(search))

        partial = functools.partial(self.ytdl.extract_info, self.search_query, download=False, process=False)
        info = await loop.run_in_executor(None, partial)

        self.search = {}
        self.search["title"] = f'Search results for:\n**{search}**'
        self.search["type"] = 'rich'
        self.search["color"] = 7506394
        self.search["author"] = {'name': f'{ctx.author.name}', 'url': f'{ctx.author.avatar_url}',
                                'icon_url': f'{ctx.author.avatar_url}'}

        lst = []
        count = 0
        e_list = []
        for e in info['entries']:
            VId = e.get('id')
            VUrl = 'https://www.youtube.com/watch?v=%s' % (VId)
            lst.append(f'`{count + 1}.` [{e.get("title")}]({VUrl})\n')
            count += 1
            e_list.append(e)

        lst.append('\n**Type a number to make a choice, Type `cancel` to exit**')
        self.search["description"] = "\n".join(lst)

        em = discord.Embed.from_dict(self.search)
        await ctx.send(embed=em, delete_after=20.0)

        def check(msg):
            return msg.content.isdigit() == True and msg.channel == channel or msg.content == 'cancel' or msg.content == 'Cancel'

        try:
            m = await self.bot.wait_for('message', check=check, timeout=20.0)
        except asyncio.TimeoutError:
            rtrn = 'timeout'
        else:
            if m.content.isdigit() == True:
                sel = int(m.content)
                if 0 < sel <= 10:
                    for key, value in info.items():
                        if key == 'entries':
                            """data = value[sel - 1]"""
                            VId = e_list[sel-1]['id']
                            VUrl = 'https://www.youtube.com/watch?v=%s' % (VId)
                            partial = functools.partial(self.ytdl.extract_info, VUrl, download=False)
                            data = await loop.run_in_executor(None, partial)
                    rtrn = self(ctx, discord.FFmpegPCMAudio(data['url'], **self.FFMPEG_OPTIONS), data=data)
                else:
                    rtrn = 'sel_invalid'
            elif m.content == 'cancel':
                rtrn = 'cancel'
            else:
                rtrn = 'sel_invalid'
                
        return rtrn

    @classmethod
    async def check_type(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        # ANCHOR check_type
        # Tells if a youtube url is a playlist, cannot get playlist by name
        try:
            loop = loop or asyncio.get_event_loop()
    
            partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
            data = await loop.run_in_executor(None, partial)
    
            return data["_type"]
        except:
            pass

    @classmethod
    async def create_source_playlist(cls, ctx: commands.Context, typ, search: str, *, loop: asyncio.BaseEventLoop = None):
        # Put all the numbers in a list
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if typ == 'playlist_alt':
            # Here we found the data of the playlist NOT the contents so we have to re-search the actual url
            search = data["url"]

            partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
            data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError(f'Couldn\'t find anything that matches `{search}`')

        numbers = []

        for entry in data["entries"]:
            if entry:
                numbers.append(entry)

        return numbers

    @classmethod
    async def playlist_put(cls, ctx, number):
        return cls(ctx, discord.FFmpegPCMAudio(number['url'], **cls.FFMPEG_OPTIONS), data=number)

    @classmethod
    async def create_source_single(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        # ANCHOR create_source_single

        # This is the part that 'searches' on youtube, if it could not find any match return otherwise return the song data
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError(f'Couldn\'t find anything that matches `{search}`')

        webpage_url = data['webpage_url']
        
        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError('Couldn\'t fetch `{}`'.format(webpage_url))
        
        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError('Couldn\'t retrieve any matches for `{}`'.format(webpage_url))
    
        return cls(ctx, discord.FFmpegPCMAudio(info['url'], **cls.FFMPEG_OPTIONS), data=info)

    @staticmethod
    def parse_duration(duration: int):
        # ANCHOR parse_duration
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration = []
        if days > 0:
            duration.append(f'{days} days')
        if hours > 0:
            duration.append(f'{hours} hours')
        if minutes > 0:
            duration.append(f'{minutes} minutes')
        if seconds > 0:
            duration.append(f'{seconds} seconds')

        return ', '.join(duration)

    @staticmethod
    def parse_number(number: int):
        # ANCHOR parse_number
        if number < 10000:
            return f'{number}'
        elif number > 10000 and number < 1000000:
            return f'{round(number/1000, 2)}K'
        elif number > 1000000 and number < 1000000000:
            return f'{round(number/1000000, 2)}M'
        else:
            return f'{round(number/1000000000, 2)}B'

    @staticmethod
    def parse_limited_title(title: str):
        # ANCHOR parse_limited_title
        title = title.replace('||', '')
        if len(title) > 72:
            return (title[:72] + '...')
        else:
            return title

    @staticmethod
    def parse_limited_title_embed(title: str):
        # ANCHOR parse_limited_title_embed
        # These characters can break the title
        title = title.replace('[', '')
        title = title.replace(']', '')
        title = title.replace('||', '')

        if len(title) > 45:
            return (title[:43] + '...')
        else:
            return title

class VoiceState:
    # -- VoiceState --
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        # ANCHOR __init__
        self.bot = bot
        self._ctx = ctx

        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()
        self.music_history = []
        
        self.processing = False
        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self):
        # ANCHOR audio_player_task
        while True:
            self.next.clear()
            await self._ctx.channel.purge(limit=100)

            if self.loop == False:
                try:
                    async with timeout(180):
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    self.bot.loop.create_task(self.stop())
                    return
                except:
                    # concurrent.futures._base.TimeoutError
                    self.bot.loop.create_task(self.stop())
                    return
                self.current.source.volume = self._volume
                self.voice.play(self.current.source, after=self.play_next_song)

            elif self.loop == True:
                self.now = discord.FFmpegPCMAudio(self.current.source.stream_url, **YTDLSource.FFMPEG_OPTIONS)
                self.voice.play(self.now, after=self.play_next_song)

            await self.current.source.channel.send(embed=self.current.create_embed(self.songs, self.loop))

            await self.next.wait()

    def play_next_song(self, error=None):
        # ANCHOR play_next_song
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        # ANCHOR skip
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        # ANCHOR stop
        self.songs.clear()

        if self.voice:
            await self.voice.disconnect()
            self.voice = None

class Song:
    # ANCHOR -- Song --
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self, songs, looped):
        # ANCHOR create_embed
        queue = ''
        if len(songs) == 0:
            queue = 'Empty queue.'
        else:
            for i, song in enumerate(songs[0:5], start=0):
                queue += f'`{i + 1}.` [**{song.source.title_limited_embed}**]({song.source.url} "{song.source.title}")\n'

        if len(songs) > 6:
            queue += f'And {len(songs) - 5} more.'

        if looped == True:
            looped = 'Currently looped'
        else:
            looped = 'Not looped'

        embed = (
            discord.Embed(
                title='Now playing',
                description=f'```css\n{self.source.title}\n```',
                color=discord.Color.blurple()
                )
            .set_image(url=self.source.thumbnail)
            .add_field(name='Duration', value=self.source.duration)
            .add_field(name='Requested by', value=self.requester.mention)
            .add_field(name='Looped', value=f'{looped}')
            .add_field(name='URL', value=f'[Click]({self.source.url})')
            .add_field(name='Views', value=f'{self.source.views}')
            .add_field(name='Likes/Dislikes', value=f'{self.source.likes}/{self.source.dislikes}')
            .add_field(name=f'Queue:', value=f'{queue}', inline=False)
            )
        return embed

class SongQueue(asyncio.Queue):
    # ANCHOR -- SongQueue --
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]

class music(commands.Cog):
    # ANCHOR -- Music --
    def __init__(self, bot: commands.Bot):
        # ANCHOR __init__
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        # ANCHOR get_voice_state
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state
        return state

    def cog_unload(self):
        # ANCHOR cog_unload
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        # ANCHOR cog_check
        if not ctx.guild:
            raise commands.NoPrivateMessage('This command can\'t be used in DM channels.')
        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        # ANCHOR cog_before_invoke
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # ANCHOR cog_command_error
        await ctx.send(f'An error occurred: {str(error)}')

    async def r_command_succes(self, ctx, time):
        # ANCHOR r_command_succes
        try:
            await ctx.message.add_reaction('✅')
        except:
            pass

        await asyncio.sleep(time)

        try:
            await ctx.message.delete()
        except:
            # Catch 404 message not found
            pass

    async def r_command_error(self, ctx):
        # ANCHOR r_command_error
        try:
            await ctx.message.add_reaction('❌')
        except:
            pass

        await asyncio.sleep(20)

        try:
            await ctx.message.delete()
        except:
            pass

    async def r_refresh_embed(self, ctx):
        # ANCHOR r_refresh_embed
        #await Pag(title='k', color=3447003, entries=['**Duration**      |      **Requested by**'], length=1, use_defaults=False).start(ctx)

        #await message.add_reaction('⏯️')
        #await message.add_reaction('⏩')
        #await message.add_reaction('⏹️')
        #await message.add_reaction('🔀')
        #await message.add_reaction('🔁')

        #def check(reaction, user):
        #    return user != self.bot.user
        #    
        #reaction = None

        #while True:
        #    if str(reaction) == '⏯️':
        #        if ctx.voice_state.paused:
        #            ctx.voice_client.resume()
        #            ctx.voice_state.paused = False
        #        else:
        #            ctx.voice_client.pause()
        #            ctx.voice_state.paused = True
        #    if str(reaction) == '⏩':
        #        await ctx.invoke(self._skip)
        #    if str(reaction) == '⏹️':
        #        await ctx.invoke(self._stop)
        #    if str(reaction) == '🔀':
        #        await ctx.invoke(self._shuffle)
        #    if str(reaction) == '🔁':
        #        await ctx.invoke(self._loop)
        #    try:
        #        reaction, user = await self.bot.wait_for('reaction_add', timeout = 900.0, check = check)
        #        await message.remove_reaction(reaction, user)
        #    except:
        #        break

        #await message.clear_reactions()

        await ctx.channel.purge(limit=100)
        await ctx.send(embed=ctx.voice_state.current.create_embed(ctx.voice_state.songs, ctx.voice_state.loop))

    @commands.command(
        name='join', invoke_without_subcommand=True, aliases=['j', 'connect', 'summon', 'con'], 
        description='Joins the voice channel the user is currently in.',
        brief='Joins the voice channel the user is currently in. This allows the bot to play music.')
    async def _join(self, ctx: commands.Context):
        # ANCHOR join
        if ctx.voice_state.voice:
            await ctx.voice_state.stop()
            del self.voice_states[ctx.guild.id]
            await ctx.voice_state.voice.move_to(ctx.author.voice.channel)
            return

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]

        ctx.voice_state.voice = await ctx.author.voice.channel.connect()
        await self.r_command_succes(ctx, 10)

    @commands.command(
        name='pause', aliases=['pau', 'break', 'wait'], description='Pause the audio.',
        brief='Pause the audio that is currently playing. Resume the audio with the command resume.')
    async def pause_(self, ctx):
        # ANCHOR pause
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send('I\'m currently not playing anything!', delete_after=20)
            await self.r_command_error(ctx)
            return
        elif ctx.voice_client.is_paused():
            return

        ctx.voice_client.pause()
        await self.r_command_succes(ctx, 5)

    @commands.command(
        name='resume', aliases=['res', 'continue', 'cont', 'go'], description='Resume the audio.',
        brief='Resume the audio that was playing.')
    async def resume_(self, ctx):
        # ANCHOR resume
        # ANCHOR display in embed
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await ctx.send('I am not currently playing anything!', delete_after=20)
            await self.r_command_error(ctx)
            return
        elif not ctx.voice_client.is_paused():
            return

        ctx.voice_client.resume()
        await self.r_command_succes(ctx, 5)

    @commands.command(
        name='leave', aliases=['disconnect', 'dc', 'disconn'], description='Leave the current voice channel.',
        brief='Leave the current voice channel.')
    @commands.has_permissions(manage_guild=True)
    async def _leave(self, ctx: commands.Context):
        # ANCHOR leave
        if not ctx.voice_state.voice:
            await ctx.send('Not connected to any voice channel.', delete_after=20)
            await self.r_command_error(ctx)
            return

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]
        await self.r_command_succes(ctx, 30)

    @commands.command(
        name='now', aliases=['currently', 'playing', 'np'], description='Send a message about what is currently playing.', 
        brief='Send a message about what is currently playing. And a small part of the queue.')
    async def _now(self, ctx: commands.Context):
        # ANCHOR now
        await ctx.message.delete()
        await ctx.send(embed=ctx.voice_state.current.create_embed(ctx.voice_state.songs, ctx.voice_state.loop))

    @commands.command(
        name='skip', aliases=['next', 'skipper'], description='Skip the current song.',
        brief=(
            'Skip the current song. '
            'If you are not the one that has requested the song you need to have atleast 2 other people that will vote with you.')
            )
    async def _skip(self, ctx: commands.Context):
        # ANCHOR skip
        if not ctx.voice_state.is_playing:
            await ctx.send('Not playing any music right now...', delete_after=20)
            await self.r_command_error(ctx)
            return

        voter = ctx.message.author
        if voter == ctx.voice_state.current.requester:
            ctx.voice_state.skip()
            await self.r_command_succes(ctx, 10)

        elif voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= 3:
                await ctx.message.add_reaction('⏭')
                ctx.voice_state.skip()
            else:
                await ctx.send(f'Skip vote added, currently at **{total_votes}/3**', delete_after=60)
                await self.r_command_succes(ctx, 15)
                await asyncio.sleep(60)
        else:
            await ctx.send('You have already voted to skip this song.', delete_after=15)
            await self.r_command_error(ctx)

    @commands.command(
        name='queue', aliases=['q', 'que', 'qlist'], description='Send the queue list that the bot currently has.',
        brief='Send the queue list that the bot currently has.')
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        # ANCHOR queue
        if len(ctx.voice_state.songs) == 0:
            await ctx.send('Empty queue.', delete_after=15)
            await self.r_command_error(ctx)
            return

        queue = ''
        for i, song in enumerate(ctx.voice_state.songs[((page - 1) * 10):(((page - 1) * 10) + 10)], start=((page - 1) * 10)):
            queue += f'`{i + 1}.` [**{song.source.title_limited}**]({song.source.url} "{song.source.title}")\n'

        embed = (discord.Embed(description=f'**{len(ctx.voice_state.songs)} tracks:**\n\n{queue}')
                .set_footer(text=f'Viewing page {page}/{math.ceil(len(ctx.voice_state.songs) / 10)}'))
        await ctx.send(embed=embed, delete_after=20)
        await self.r_command_succes(ctx, 15)

    @commands.command(
        name='shuffle', aliases=['shuf', 'mix'], description='Mix all the current song\'s in the playlist.',
        brief='Mix all the current song\'s in the playlist.')
    async def _shuffle(self, ctx: commands.Context):
        # ANCHOR shuffle
        if len(ctx.voice_state.songs) == 0:
            await ctx.send('Empty queue.', delete_after=15)
            await self.r_command_error(ctx)
            return

        ctx.voice_state.songs.shuffle()
        await self.r_command_succes(ctx, 5)

        await self.r_refresh_embed(ctx)

    @commands.command(
        name='remove', aliases=['rem', 'erase'], description='Remove a song inside the queue.',
        brief='Remove a song inside the queue. Give the song queue number to remove it.')
    async def _remove(self, ctx: commands.Context, index: int):
        # ANCHOR remove
        if len(ctx.voice_state.songs) == 0:
            await ctx.send('Empty queue.', delete_after=15)
            await self.r_command_error(ctx)
            return

        ctx.voice_state.songs.remove(index - 1)
        await self.r_command_succes(ctx, 10)

        if len(ctx.voice_state.songs) < 6:
            await self.r_refresh_embed(ctx)

    @commands.command(
        name='clear', aliases=['cc', 'clean'], description='Clears the whole queue.',
        brief='Clears the whole queue.')
    async def _clear(self, ctx: commands.context):
        # ANCHOR clear
        if ctx.voice_state.processing is False:
            if len(ctx.voice_state.songs) == 0:
                await ctx.send('Empty queue.', delete_after=15)
                await self.r_command_error(ctx)
                return
    
            ctx.voice_state.songs.clear()
            await self.r_command_succes(ctx, 5)
            
            await self.r_refresh_embed(ctx)
        else:
            await ctx.send('I\'m currently processing the previous request.', delete_after=10)

    @commands.command(
        name='stop', aliases=['silence'], description='Clears the whole queue. And stop the current song.',
        brief='Clears the whole queue. And stop the current song.')
    async def _stop(self, ctx: commands.Context):
        # ANCHOR stop
        if ctx.voice_state.processing is False:
            if not ctx.voice_client or not ctx.voice_client.is_connected():
                await ctx.send('I am not currently playing anything!', delete_after=20)
                return await ctx.send('Empty queue.', delete_after=15)
    
            ctx.voice_state.songs.clear()
            ctx.voice_state.skip()
            await self.r_command_succes(ctx, 15)
    
            await ctx.channel.purge(limit=100)
        else:
            await ctx.send('I\'m currently processing the previous request.', delete_after=10)

    @commands.command(
        name='loop', aliases=['loopn'], description='Loop a song.',
        brief='Loop a song.')
    async def _loop(self, ctx: commands.Context):
        # ANCHOR loop
        await ctx.message.delete()
        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing being played at the moment.', delete_after=15)

        # Inverse boolean value to loop and unloop.
        ctx.voice_state.loop = not ctx.voice_state.loop

        await self.r_refresh_embed(ctx)
        #await ctx.send('Looped, retype to unloop.', delete_after=100)

    @commands.command(
        name='play', aliases=['p', 'song'], description='Play a song trough the bot.',
        brief='Play a song trough the bot, by searching a song with the name or by URL.')
    async def _play(self, ctx: commands.Context, *, search: str):
        # ANCHOR play
        proccesing_state = ctx.voice_state.processing
        now = ctx.voice_state.current

        if not ctx.voice_state.voice:
            if ctx.voice_state.voice:
                await ctx.voice_state.stop()
                del self.voice_states[ctx.guild.id]
                await ctx.voice_state.voice.move_to(ctx.author.voice.channel)
                return

            ctx.voice_state.voice = await ctx.author.voice.channel.connect()

        async with ctx.typing():
            try:
                typ = await YTDLSource.check_type(ctx, search, loop=self.bot.loop)
                if 'https://www.youtube.com/' in search:
                    if 'list' in search:
                        # For some reason youtube uses 2 types of youtube playlist urls
                        typ = 'playlist_alt'

                if typ == 'playlist' or typ == 'playlist_alt':
                    if proccesing_state is False:
                        ctx.voice_state.processing = True
                        playlist = None
                        skipped = 0

                        playlist = await YTDLSource.create_source_playlist(ctx, typ, search, loop=self.bot.loop)

                        await ctx.channel.purge(limit=100)
                        await ctx.send(f'Adding {len(playlist)} song\'s. This will take about {int(round(0.75 * len(playlist), 0) + 3)} seconds.')
    
                        for x in playlist:
                            if x is not None:
                                url = x["url"]
                                search = f'https://www.youtube.com/watch?v={url}'
    
                                try:
                                    source = await YTDLSource.create_source_single(ctx, search, loop=self.bot.loop)
                                    song = Song(source)
    
                                    await ctx.voice_state.songs.put(song)
                                    ctx.voice_state.music_history.append(source)
                                except:
                                    skipped += 1

                        ctx.voice_state.processing = False
                else:
                    if proccesing_state is False:
                        ctx.voice_state.processing = True
                        source = await YTDLSource.create_source_single(ctx, search, loop=self.bot.loop)
                        #if source.duration_raw > 901:
                        #    return await ctx.send(f'The song `{source.title}` is too long, provide songs under 15 minutes.', delete_after=10)
                        #if source.duration_raw < 11:
                        #    return await ctx.send(f'The song `{source.title}` is too short, provide songs above 10 seconds.', delete_after=10)
    
                        song = Song(source)
    
                        await ctx.voice_state.songs.put(song)
                        ctx.voice_state.music_history.append(source)
                        try:
                            await ctx.message.add_reaction('✅')
                        except:
                            pass
                        ctx.voice_state.processing = False
            except YTDLError as e:
                await ctx.send(f'An error occurred while processing this request: {str(e)}', delete_after=15)
            else:
                if typ == 'playlist':
                    if proccesing_state is False:
                        if skipped != 0:
                            await ctx.send(f'Playlist added. Removed {skipped} songs.', delete_after=10)
                    else:
                        await ctx.send('I\'m currently already processing a playlist.', delete_after=10)
                else:
                    # If there is nothing playing do not send message
                    if proccesing_state is False:
                        if now is not None:
                            await ctx.send(f'Enqueued {str(source)}', delete_after=10)
                    else:
                        await ctx.send('I\'m currently processing the previous request.', delete_after=10)
        try:
            if len(ctx.voice_state.songs) < 6:
                await self.r_refresh_embed(ctx)
            if typ == 'playlist':
                await self.r_refresh_embed(ctx)
        except:
            pass

    @commands.command(
        name='history', aliases=['his', 'previous'], description='Get the songs that have been played by the bot.',
        brief='Get the songs that have been played by the bot.')
    async def _history(self, ctx: commands.Context, *, page: int = 1):
        # ANCHOR history
        if len(ctx.voice_state.music_history) == 0:
            await ctx.send(f'No history just yet! Start listening with {ctx.prefix}play.', delete_after=15)
            await self.r_command_error(ctx)
            return

        his_rev = list(reversed(ctx.voice_state.music_history))

        history = ''
        for i, source in enumerate(his_rev[((page - 1) * 10):(((page - 1) * 10) + 10)], start=((page - 1) * 10)):
            history += f'`{i + 1}.` [**{source.title_limited}**]({source.url} "{source.title}")\n'

        embed = (discord.Embed(description=f'**{len(ctx.voice_state.music_history)} tracks:**\n\n{history}')
                .set_footer(text=f'Viewing page {page}/{math.ceil(len(ctx.voice_state.music_history) / 10)}'))
        await ctx.send(embed=embed, delete_after=20)

        await self.r_command_succes(ctx, 20)

    @commands.command(
        name='search', aliases=['lookup'], description='Search a song up on youtube', 
        brief=(
            'Search a song up on youtube. The search will appear for 25 second, '
            'you then have the ability to send 1 to 10 to select the right song.')
            )
    async def _search(self, ctx: commands.Context, *, search: str):
        async with ctx.typing():
            try:
                source = await YTDLSource.search_source(ctx, search, loop=self.bot.loop, bot=self.bot)
            except YTDLError as e:
                await ctx.send('An error occurred while processing this request: {}'.format(str(e)))
            else:
                if source == 'sel_invalid':
                    await ctx.send('Invalid selection')
                    await asyncio.sleep(5)
                    await self.r_refresh_embed(ctx)
                elif source == 'cancel':
                    await ctx.send(':white_check_mark:')
                    await asyncio.sleep(5)
                    await self.r_refresh_embed(ctx)
                elif source == 'timeout':
                    await ctx.send('You took too long to make a choice.')
                    await asyncio.sleep(5)
                    await self.r_refresh_embed(ctx)
                else:
                    if not ctx.voice_state.voice:
                        await ctx.invoke(self._join)

                    song = Song(source)
                    await ctx.voice_state.songs.put(song)
                    await ctx.send('Enqueued {}'.format(str(source)))

                    await asyncio.sleep(5)
                    await self.r_refresh_embed(ctx)

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        # ANCHOR ensure_voice_state
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError('You are not connected to any voice channel.')

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError('Bot is already in a voice channel.')

def setup(bot):
    bot.add_cog(music(bot))
