import asyncio
import io
import logging
import os
import difflib

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import data

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN is not set. Add it to your .env file.")

ANNOUNCE_CHANNEL_ID = int(os.getenv("ANNOUNCE_CHANNEL_ID", "0"))

BUILD_DIR = "builds"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

RARITY_COLOR = {
    "LLR": 0xFF4500,
    "SSR": 0xFFD700,
    "SR":  0xA8A8C8,
    "R":   0xCD7F32,
    "N":   0x808080,
}

RARITY_LABEL = {
    "LLR": "★★★★★ LLR",
    "SSR": "★★★★ SSR",
    "SR":  "★★★ SR",
    "R":   "★★ R",
    "N":   "★ N",
}

_FOOTER     = "Data: bannernews.github.io/langrisser"
_SITE_URL   = "https://bannernews.github.io/langrisser/heroes_en.html"
_NOT_LOADED = "Game data is still loading — try again in a moment."

intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)


# ---------------------------------------------------------------------------
# Local image helpers (kept for /quickinfo fallback)
# ---------------------------------------------------------------------------

def find_image(hero_key: str) -> str | None:
    if not os.path.isdir(BUILD_DIR):
        return None
    no_sp = hero_key.replace(" ", "")
    and_form = hero_key.lower().replace(" & ", "and").replace(" ", "")
    # Build a set of lowercase candidate stems to match against (case-insensitive)
    candidates = {hero_key.lower(), no_sp.lower(), no_sp.replace("&", "").lower(), and_form}
    for fn in os.listdir(BUILD_DIR):
        base, ext = os.path.splitext(fn)
        if ext.lower() in IMAGE_EXTS and base.lower() in candidates:
            return os.path.join(BUILD_DIR, fn)
    return None


# ---------------------------------------------------------------------------
# Autocomplete callbacks
# ---------------------------------------------------------------------------

async def _hero_ac(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    q = current.lower()
    seen: set[str] = set()
    results: list[app_commands.Choice[str]] = []
    for name in data.HERO_NAMES:
        if q in name.lower():
            results.append(app_commands.Choice(name=name, value=name))
            seen.add(name)
        if len(results) >= 25:
            return results
    if q and len(results) < 25:
        for name in data.HERO_NAMES:
            if name in seen:
                continue
            if difflib.SequenceMatcher(None, q, name.lower()).ratio() > 0.45:
                results.append(app_commands.Choice(name=name, value=name))
            if len(results) >= 25:
                break
    return results


async def _faction_ac(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    q = current.lower()
    seen: set[str] = set()
    for hero in data.HEROES.values():
        for f in hero["factions"]:
            if f not in seen and q in f.lower():
                seen.add(f)
    return [app_commands.Choice(name=f, value=f) for f in sorted(seen)][:25]


# ---------------------------------------------------------------------------
# Embed builders
# ---------------------------------------------------------------------------

def _quickinfo_embeds(hero: dict, build: dict | None) -> list[discord.Embed]:
    color    = RARITY_COLOR.get(hero.get("rarity", ""), 0x4169E1)
    hero_page = data.get_hero_page_url(hero) or _SITE_URL
    portrait  = data.get_portrait_url(hero)
    codes     = hero.get("faction_codes", [])
    faction_icon = data.get_faction_icon_url(codes[0]) if codes else ""

    e1 = discord.Embed(
        title=f"{hero['name']}  {RARITY_LABEL.get(hero['rarity'], hero['rarity'])}",
        color=color,
        url=hero_page,
    )
    if portrait:
        e1.set_thumbnail(url=portrait)

    factions_str = ", ".join(hero["factions"]) if hero.get("factions") else "Unknown"
    e1.add_field(name="Faction(s)", value=factions_str, inline=True)
    if hero.get("gender"):
        e1.add_field(name="Gender", value=hero["gender"], inline=True)
    if hero.get("story"):
        e1.add_field(name="Story", value=hero["story"], inline=True)
    tags = []
    if hero.get("forge"):
        tags.append("Forge")
    if hero.get("sp"):
        tags.append("SP")
    if tags:
        e1.add_field(name="Tags", value=", ".join(tags), inline=True)

    if not build:
        chibi = data.get_chibi_url(hero)
        if chibi:
            e1.set_image(url=chibi)
        e1.description = f"No build data found.\n[View on bannernews]({_SITE_URL})"
        if faction_icon:
            e1.set_footer(text=_FOOTER, icon_url=faction_icon)
        else:
            e1.set_footer(text=_FOOTER)
        return [e1]

    if build.get("talent_name"):
        talent_val = build["talent_name"]
        if build.get("talent_desc"):
            desc = build["talent_desc"]
            if len(desc) > 300:
                desc = desc[:297] + "…"
            talent_val += f"\n*{desc}*"
        e1.add_field(name="Talent", value=talent_val, inline=False)
    talent_icon = data.get_talent_icon_url(build)
    if talent_icon:
        e1.set_image(url=talent_icon)
    else:
        chibi = data.get_chibi_url(hero)
        if chibi:
            e1.set_image(url=chibi)

    bonuses = []
    for label, key in [("HP", "sold_hp"), ("ATK", "sold_atk"), ("DEF", "sold_def"), ("MDEF", "sold_mdef")]:
        if build.get(key):
            bonuses.append(f"{label} {build[key]}")
    if bonuses:
        e1.add_field(name="Soldier Bonuses", value="  ".join(bonuses), inline=True)

    gear_parts = []
    if build.get("weapons"):
        gear_parts.append("**Weapons:** " + ", ".join(build["weapons"]))
    if build.get("armor"):
        gear_parts.append("**Armor:** " + build["armor"])
    if gear_parts:
        e1.add_field(name="Equipment Restrictions", value="\n".join(gear_parts), inline=True)

    if build.get("soldiers"):
        soldiers_str = ", ".join(build["soldiers"])
        if len(soldiers_str) > 1024:
            soldiers_str = soldiers_str[:1021] + "…"
        e1.add_field(name="Recommended Soldiers", value=soldiers_str, inline=False)
    if build.get("soldiers_sp"):
        e1.add_field(name="SP Soldiers", value=", ".join(build["soldiers_sp"])[:1024], inline=False)

    if faction_icon:
        e1.set_footer(text=_FOOTER, icon_url=faction_icon)
    else:
        e1.set_footer(text=_FOOTER)

    if not build.get("item_name"):
        return [e1]

    e2 = discord.Embed(color=color)
    item_val = f"**{build['item_name']}**"
    if build.get("item_stats"):
        item_val += f"\n{build['item_stats']}"
    if build.get("item_desc"):
        desc = build["item_desc"]
        if len(desc) > 300:
            desc = desc[:297] + "…"
        item_val += f"\n{desc}"
    e2.add_field(name="Exclusive Equipment", value=item_val, inline=False)
    item_icon = data.get_item_icon_url(hero)
    if item_icon:
        e2.set_thumbnail(url=item_icon)

    return [e1, e2]


_GALLERY_URL = "https://raw.githubusercontent.com/bannernews/langrisser/master/"


def _bonds_embeds(hero_name: str, bond: dict, hero: dict) -> list[discord.Embed]:
    def_partner = bond.get("def_bond")
    atk_partner = bond.get("atk_bond")

    # Shared url causes Discord to render all image embeds as a side-by-side gallery.
    # Blank description lines push the bond fields below the thumbnail rather than beside it.
    e1 = discord.Embed(title=f"{hero_name} — Bonds", color=0x00BFFF, url=_GALLERY_URL,
                       description="​\n​\n​")
    portrait = data.get_portrait_url(hero)
    if portrait:
        e1.set_thumbnail(url=portrait)

    if def_partner:
        e1.add_field(name="DEF Bond Partner", value=def_partner, inline=True)
    if atk_partner:
        e1.add_field(name="ATK Bond Partner", value=atk_partner, inline=True)
    if bond.get("needed_for_def"):
        e1.add_field(name="Needed for DEF bonds by", value=", ".join(bond["needed_for_def"])[:1024], inline=False)
    if bond.get("needed_for_atk"):
        e1.add_field(name="Needed for ATK bonds by", value=", ".join(bond["needed_for_atk"])[:1024], inline=False)
    if not any([def_partner, atk_partner, bond.get("needed_for_def"), bond.get("needed_for_atk")]):
        e1.description = "No bond heroes needed."
    e1.set_footer(text=_FOOTER)

    embeds = [e1]
    def_first = (def_partner or "").split(",")[0].strip().lower()
    atk_first = (atk_partner or "").split(",")[0].strip().lower()

    if def_first and (def_hero := data.HEROES.get(def_first)):
        e_def = discord.Embed(color=0x00BFFF, url=_GALLERY_URL)
        e_def.set_image(url=data.get_portrait_url(def_hero))
        embeds.append(e_def)

    if atk_first and atk_first != def_first and (atk_hero := data.HEROES.get(atk_first)):
        e_atk = discord.Embed(color=0x00BFFF, url=_GALLERY_URL)
        e_atk.set_image(url=data.get_portrait_url(atk_hero))
        embeds.append(e_atk)

    return embeds


def _faction_embed(faction_name: str, heroes: list[dict], faction_code: str = "") -> discord.Embed:
    embed = discord.Embed(title=f"{faction_name} — Heroes", color=0x2E8B57)
    if faction_code:
        embed.set_thumbnail(url=data.get_faction_icon_url(faction_code))
    by_rarity: dict[str, list[str]] = {}
    for h in heroes:
        by_rarity.setdefault(h["rarity"], []).append(h["name"])
    for rarity in ["LLR", "SSR", "SR", "R", "N"]:
        if rarity not in by_rarity:
            continue
        embed.add_field(
            name=RARITY_LABEL.get(rarity, rarity),
            value=", ".join(sorted(by_rarity[rarity]))[:1024],
            inline=False,
        )
    embed.set_footer(text=f"{len(heroes)} heroes total • {_FOOTER}")
    return embed


# ---------------------------------------------------------------------------
# Auto-refresh loop
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
                description=hero_list,
                color=0x00FF7F,
            )
            embed.set_footer(text="Use /quickinfo <name> to look them up")
            try:
                await channel.send(embed=embed)
            except discord.HTTPException as e:
                logger.error(f"Failed to send new-hero announcement: {e}")


@auto_refresh.before_loop
async def before_refresh():
    await client.wait_until_ready()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@tree.command(name="quickinfo", description="Hero info + build for a Langrisser hero, or list all heroes")
@app_commands.describe(hero="Hero name (leave blank to list all heroes)")
@app_commands.autocomplete(hero=_hero_ac)
async def quickinfo(interaction: discord.Interaction, hero: str = None):
    if not data.HEROES:
        await interaction.response.send_message(_NOT_LOADED, ephemeral=True)
        return

    if hero is None:
        hero_list = "\n".join(data.HERO_NAMES)
        file = discord.File(io.BytesIO(hero_list.encode()), filename="heroes.txt")
        embed = discord.Embed(
            title=f"Langrisser Heroes — {len(data.HERO_NAMES)} total",
            description="Full list attached. Use `/quickinfo <name>` for details.",
            color=0x4169E1,
        )
        preview = "\n".join(f"• {n}" for n in data.HERO_NAMES[:20])
        if len(data.HERO_NAMES) > 20:
            preview += f"\n… and {len(data.HERO_NAMES) - 20} more"
        embed.add_field(name="Preview", value=preview, inline=False)
        embed.set_footer(text=_FOOTER)
        await interaction.response.send_message(embed=embed, file=file)
        return

    hero_key = data.find_hero(hero)
    if hero_key is None:
        await interaction.response.send_message(f"Hero `{hero}` not found.", ephemeral=True)
        return

    hero_info = data.HEROES[hero_key]
    build_info = data.BUILDS.get(hero_key)
    embeds = _quickinfo_embeds(hero_info, build_info)

    if not build_info:
        local_img = find_image(hero_key)
        if local_img:
            await interaction.response.send_message(embeds=embeds, file=discord.File(local_img))
            return

    await interaction.response.send_message(embeds=embeds)


@tree.command(name="build", description="Show the build image for a Langrisser hero")
@app_commands.describe(hero="Hero name")
@app_commands.autocomplete(hero=_hero_ac)
async def cmd_build(interaction: discord.Interaction, hero: str):
    if not data.HEROES:
        await interaction.response.send_message(_NOT_LOADED, ephemeral=True)
        return
    hero_key = data.find_hero(hero)
    if hero_key is None:
        await interaction.response.send_message(f"Hero `{hero}` not found.", ephemeral=True)
        return
    hero_info = data.HEROES[hero_key]
    img_path = find_image(hero_key)
    if not img_path:
        await interaction.response.send_message(
            f"No build image available for **{hero_info['name']}**.", ephemeral=True
        )
        return
    embed = discord.Embed(title=f"{hero_info['name']} — Build", color=0x4169E1)
    embed.set_image(url=f"attachment://{os.path.basename(img_path)}")
    embed.set_footer(text=_FOOTER)
    await interaction.response.send_message(embed=embed, file=discord.File(img_path))


@tree.command(name="bonds", description="Show bond information for a hero")
@app_commands.describe(hero="Hero name")
@app_commands.autocomplete(hero=_hero_ac)
async def bonds(interaction: discord.Interaction, hero: str):
    if not data.BONDS:
        await interaction.response.send_message(_NOT_LOADED, ephemeral=True)
        return
    key = data.find_hero(hero)
    if key is None:
        await interaction.response.send_message(f"Hero `{hero}` not found.", ephemeral=True)
        return
    hero_info = data.HEROES[key]
    bond = data.BONDS.get(key)
    if bond is None:
        await interaction.response.send_message(
            f"No bond data found for **{hero_info['name']}**.", ephemeral=True
        )
        return
    await interaction.response.send_message(embeds=_bonds_embeds(hero_info["name"], bond, hero_info))


@tree.command(name="faction", description="List all heroes in a faction")
@app_commands.describe(name="Faction name")
@app_commands.autocomplete(name=_faction_ac)
async def faction(interaction: discord.Interaction, name: str):
    if not data.HEROES:
        await interaction.response.send_message(_NOT_LOADED, ephemeral=True)
        return
    q = name.lower().strip()
    matched = [h for h in data.HEROES.values() if any(q in f.lower() for f in h["factions"])]
    if not matched:
        await interaction.response.send_message(f"No heroes found for faction `{name}`.", ephemeral=True)
        return
    faction_display = name.title()
    faction_code = ""
    for h in matched:
        for i, f in enumerate(h.get("factions", [])):
            if q in f.lower():
                faction_display = f
                codes = h.get("faction_codes", [])
                faction_code = codes[i] if i < len(codes) else ""
                break
        if faction_code:
            break
    if not faction_code:
        faction_code = data.get_faction_code(faction_display)
    await interaction.response.send_message(embed=_faction_embed(faction_display, matched, faction_code))


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} — loading game data...")
    loop = asyncio.get_event_loop()

    await loop.run_in_executor(None, data.load_all)

    try:
        await loop.run_in_executor(None, data.check_for_updates)
    except Exception as e:
        logger.warning(f"Could not seed commit SHA: {e}")

    await tree.sync()
    logger.info(
        f"Ready — {len(data.HEROES)} heroes, "
        f"{len(data.BONDS)} bonds, "
        f"{len(data.BUILDS)} builds loaded."
    )
    auto_refresh.start()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

client.run(token)
