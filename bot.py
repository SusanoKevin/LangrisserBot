import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import data
import commands

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Optional: set ANNOUNCE_CHANNEL_ID in .env to receive new-hero announcements
ANNOUNCE_CHANNEL_ID = int(os.getenv("ANNOUNCE_CHANNEL_ID", "0"))

intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)

commands.register(tree)


# ---------------------------------------------------------------------------
# Auto-update: check for new commits every 4 hours
# ---------------------------------------------------------------------------

@tasks.loop(hours=4)
async def auto_refresh():
    loop = asyncio.get_event_loop()
    try:
        updated, new_heroes = await loop.run_in_executor(None, data.check_for_updates)
    except Exception as e:
        logger.error(f"Update check failed: {e}")
        return

    if not updated:
        return

    logger.info(f"Data refreshed. {len(new_heroes)} new hero(es): {new_heroes}")

    if new_heroes and ANNOUNCE_CHANNEL_ID:
        channel = client.get_channel(ANNOUNCE_CHANNEL_ID)
        if channel:
            hero_list = ", ".join(f"**{h}**" for h in new_heroes)
            embed = discord.Embed(
                title="New heroes added!",
                description=f"{hero_list}",
                color=0x00FF7F,
            )
            embed.set_footer(text="Use /hero <name> to look them up")
            try:
                await channel.send(embed=embed)
            except discord.HTTPException as e:
                logger.error(f"Failed to send new-hero announcement: {e}")


@auto_refresh.before_loop
async def before_refresh():
    await client.wait_until_ready()


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} — loading game data...")
    loop = asyncio.get_event_loop()

    # Initial full load
    await loop.run_in_executor(None, data.load_all)

    # Seed the commit SHA baseline (so the first auto_refresh doesn't re-announce everything)
    try:
        await loop.run_in_executor(None, data.check_for_updates)
    except Exception as e:
        logger.warning(f"Could not seed commit SHA: {e}")

    await tree.sync()
    logger.info(
        f"Ready — {len(data.HEROES)} heroes, "
        f"{len(data.SOLDIERS)} troops, "
        f"{len(data.BONDS)} bonds, "
        f"{len(data.BUILDS)} builds loaded."
    )

    auto_refresh.start()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN is not set. Add it to your .env file.")

client.run(token)
