from discord.ext import commands, tasks
import aioredis
import discord 
from datetime import datetime, timedelta, time

def ttl_delta(**td_kwargs) -> timedelta:
    """
    Get timedelta until end of day on the datetime passed, or current time.
    """
    return datetime.combine(datetime.now() + timedelta(**(td_kwargs or dict(days=1))), time.min) - datetime.now()


class TrackerBot(commands.Bot):
    def __init__(self, config : dict):
        self.config = config
        self.redis = None 

        super().__init__(**config)

        self.worker.start() 

        self.cached_message = {}
        self.cached_embed = {} 
        self.load_extension("jishaku")
        self.run(config['token'])

    async def create(self):
        if not self.redis:
            uri = self.config.get('redis-uri')
            self.redis : aioredis.Redis = await aioredis.from_url(uri, encoding='utf-8',)
            await self.redis.ping() 
    
    async def on_ready(self) -> None:
        await self.create()
        print(f"Connected to {self.user.name} ({self.user.id})")
    
    
    # message tracker
    async def on_message(self, message : discord.Message) -> None:
        if not self.is_ready():
            return
        
        
        await self.process_commands(message)

        if not message.author.bot:
            user = f"{message.author.id}"
            

            await self.redis.zincrby("lb:daily", 1, user)
            await self.redis.zincrby("lb:weekly", 1, user)  

            if not await self.redis.ttl("lb:daily"):
                await self.redis.expire("lb:daily", ttl_delta(days=1))
            if not await self.redis.ttl("lb:weekly"):
                await self.redis.expire('lb:weekly', ttl_delta(weeks=1))
        
            
    # messaage updator 
    @tasks.loop(seconds=5)
    async def worker(self):
        if not self.redis:
            print("No redis...")
            return
        if chn_id := self.config.get("channel"):
            if channel := self.get_channel(int(chn_id)):
                txt = ""
                for user, score in await self.redis.zrevrange("lb:daily", 0, -1, True, int):
                    txt += f"\n<@{user.decode()}> - `{score}`"
                
                embed = discord.Embed(title="Daily Message Leaderboard", description='\n'.join([f"{pos}. {t}" for pos, t in enumerate(txt.split('\n')[1:20], start=1)]))
                
                if embed.to_dict() != self.cached_embed.get("daily"):
                    if not ( msg := self.cached_message.get('daily')):
                        msg = await channel.history(limit=100).filter(lambda m : m.author.id == self.user.id).find(lambda m : m.embeds and m.embeds[0].title == "Daily Message Leaderboard")
                        if not msg:
                            msg = await channel.send(embed=discord.Embed(title="Daily Message Leaderboard"))
                        self.cached_message['daily'] = msg

                    if msg:
                        await msg.edit(embed=embed)

                txt = ""
                for user, score in await self.redis.zrevrange("lb:weekly", 0, -1, True, int):
                    txt += f"\n<@{user.decode()}> - `{score}`"
                
                embed = discord.Embed(title="Weekly Message Leaderboard", description='\n'.join([f"{pos}. {t}" for pos, t in enumerate(txt.split('\n')[1:20], start=1)]))
                
                if embed.to_dict() != self.cached_embed.get("weekly"):
                    if not ( msg := self.cached_message.get('weekly')):
                        msg = await channel.history(limit=100).filter(lambda m : m.author.id == self.user.id).find(lambda m : m.embeds and m.embeds[0].title == "Weekly Message Leaderboard")
                        if not msg:
                            msg = await channel.send(embed=discord.Embed(title="Weekly Message Leaderboard"))
                        self.cached_message['weekly'] = msg

                    if msg:
                        await msg.edit(embed=embed)
        
    @worker.before_loop 
    async def waiter(self):
        await self.wait_until_ready()
    
    @commands.command()
    async def embedmessage(self, ctx, message : str):
        print(message)
        
if __name__ == "__main__":
    import os, json

    with open("./config.json", "r") as fp:
        data = json.load(fp)

    for k in data.copy().keys():
        if value := os.getenv("o_" + k):
            data[k] = value

    TrackerBot(data)