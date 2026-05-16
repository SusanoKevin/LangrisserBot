import io
import difflib
import discord
from discord import app_commands

import data

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

TROOP_CLASS_COLOR = {
    "sword":   0xDC143C,
    "lance":   0xFF8C00,
    "cavalry": 0x8B4513,
    "bow":     0x228B22,
    "mage":    0x6A0DAD,
    "holy":    0xFFD700,
}

_FOOTER   = "Data: bannernews.github.io/langrisser"
_SITE_URL = "https://bannernews.github.io/langrisser/heroes_en.html"
_NOT_LOADED = "Game data is still loading — try again in a moment."


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


async def _troop_ac(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    q = current.lower()
    results: list[app_commands.Choice[str]] = []
    for s in data.SOLDIERS.values():
        if q in s["name"].lower():
            results.append(app_commands.Choice(name=s["name"], value=s["name"]))
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

def _hero_embed(hero: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"{hero['name']}  {RARITY_LABEL.get(hero['rarity'], hero['rarity'])}",
        color=RARITY_COLOR.get(hero["rarity"], 0x4169E1),
        url=_SITE_URL,
    )
    portrait = data.get_portrait_url(hero)
    if portrait:
        embed.set_thumbnail(url=portrait)
    chibi = data.get_chibi_url(hero)
    if chibi:
        embed.set_image(url=chibi)
    factions_str = ", ".join(hero["factions"]) if hero.get("factions") else "Unknown"
    embed.add_field(name="Faction(s)", value=factions_str, inline=True)
    codes = hero.get("faction_codes", [])
    faction_icon = data.get_faction_icon_url(codes[0]) if codes else ""
    if hero.get("gender"):
        embed.add_field(name="Gender", value=hero["gender"], inline=True)
    if hero.get("story"):
        embed.add_field(name="Story", value=hero["story"], inline=True)
    tags = []
    if hero.get("forge"):
        tags.append("Forge")
    if hero.get("sp"):
        tags.append("SP")
    if tags:
        embed.add_field(name="Tags", value=", ".join(tags), inline=True)
    if faction_icon:
        embed.set_footer(text=_FOOTER, icon_url=faction_icon)
    else:
        embed.set_footer(text=_FOOTER)
    return embed


def _build_embeds(hero: dict, build: dict | None) -> list[discord.Embed]:
    color = RARITY_COLOR.get(hero.get("rarity", ""), 0x4169E1)
    hero_page = data.get_hero_page_url(hero) or _SITE_URL
    portrait = data.get_portrait_url(hero)

    e1 = discord.Embed(title=hero["name"], color=color, url=hero_page)
    if hero.get("factions"):
        e1.add_field(name="Faction(s)", value=", ".join(hero["factions"]), inline=True)
    if hero.get("rarity"):
        e1.add_field(name="Rarity", value=RARITY_LABEL.get(hero["rarity"], hero["rarity"]), inline=True)
    if portrait:
        e1.set_thumbnail(url=portrait)

    if not build:
        e1.description = f"No build data found for this hero.\n[View on bannernews]({_SITE_URL})"
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

    e1.set_footer(text=_FOOTER)

    # Embed 2: personal item with its icon as thumbnail
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
    e2.add_field(name="Personal Item", value=item_val, inline=False)
    item_icon = data.get_item_icon_url(hero)
    if item_icon:
        e2.set_thumbnail(url=item_icon)

    return [e1, e2]


def _soldier_embed(s: dict) -> discord.Embed:
    embed = discord.Embed(title=s["name"], color=TROOP_CLASS_COLOR.get(s["troop_class"], 0x4169E1))
    icon_url = data.get_soldier_icon_url(s) or data.get_class_icon_url(s["troop_class"])
    if icon_url:
        embed.set_thumbnail(url=icon_url)
    embed.add_field(name="HP",       value=s["hp"],       inline=True)
    embed.add_field(name="ATK",      value=s["atk"],      inline=True)
    embed.add_field(name="DEF",      value=s["def"],      inline=True)
    embed.add_field(name="MDEF",     value=s["mdef"],     inline=True)
    embed.add_field(name="Mobility", value=s["mobility"], inline=True)
    embed.add_field(name="Range",    value=s["range"],    inline=True)
    embed.add_field(name="Class",    value=s["troop_class"].title(), inline=True)
    embed.add_field(name="Movement", value=s["move_type"],           inline=True)
    if s["desc"]:
        embed.add_field(name="Ability", value=s["desc"][:1024], inline=False)
    if s["heroes"]:
        hero_str = ", ".join(s["heroes"][:30])
        if len(s["heroes"]) > 30:
            hero_str += f" +{len(s['heroes']) - 30} more"
        embed.add_field(name="Used by", value=hero_str[:1024], inline=False)
    embed.set_footer(text=_FOOTER)
    return embed


def _bonds_embed(hero_name: str, bond: dict, hero: dict) -> discord.Embed:
    embed = discord.Embed(title=f"{hero_name} — Bonds", color=0x00BFFF)
    # Hero's own portrait as thumbnail
    portrait = data.get_portrait_url(hero)
    if portrait:
        embed.set_thumbnail(url=portrait)
    # Bond partner portrait as main image (prefer DEF, fallback ATK)
    partner_name = bond.get("def_bond") or bond.get("atk_bond")
    if partner_name:
        partner_hero = data.HEROES.get(partner_name.lower())
        if partner_hero:
            embed.set_image(url=data.get_portrait_url(partner_hero))
    if bond.get("def_bond"):
        embed.add_field(name="DEF Bond Partner", value=bond["def_bond"], inline=True)
    if bond.get("atk_bond"):
        embed.add_field(name="ATK Bond Partner", value=bond["atk_bond"], inline=True)
    if bond.get("needed_for_def"):
        embed.add_field(name="Needed for DEF bonds by", value=", ".join(bond["needed_for_def"])[:1024], inline=False)
    if bond.get("needed_for_atk"):
        embed.add_field(name="Needed for ATK bonds by", value=", ".join(bond["needed_for_atk"])[:1024], inline=False)
    if not any([bond.get("def_bond"), bond.get("atk_bond"),
                bond.get("needed_for_def"), bond.get("needed_for_atk")]):
        embed.description = "No bond information available for this hero."
    embed.set_footer(text=_FOOTER)
    return embed


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
# Command registration
# ---------------------------------------------------------------------------

def register(tree: app_commands.CommandTree) -> None:

    @tree.command(name="hero", description="Look up a Langrisser hero, or list all heroes")
    @app_commands.describe(name="Hero name (leave blank to list all heroes)")
    @app_commands.autocomplete(name=_hero_ac)
    async def cmd_hero(interaction: discord.Interaction, name: str = None):
        if not data.HEROES:
            await interaction.response.send_message(_NOT_LOADED, ephemeral=True)
            return

        if name is None:
            hero_list = "\n".join(data.HERO_NAMES)
            file = discord.File(io.BytesIO(hero_list.encode()), filename="heroes.txt")
            embed = discord.Embed(
                title=f"Langrisser Heroes — {len(data.HERO_NAMES)} total",
                description="Full list attached. Use `/hero <name>` for details.",
                color=0x4169E1,
            )
            preview = "\n".join(f"• {n}" for n in data.HERO_NAMES[:20])
            if len(data.HERO_NAMES) > 20:
                preview += f"\n… and {len(data.HERO_NAMES) - 20} more"
            embed.add_field(name="Preview", value=preview, inline=False)
            embed.set_footer(text=_FOOTER)
            await interaction.response.send_message(embed=embed, file=file)
            return

        key = data.find_hero(name)
        if key is None:
            await interaction.response.send_message(f"Hero `{name}` not found.", ephemeral=True)
            return
        await interaction.response.send_message(embed=_hero_embed(data.HEROES[key]))

    @tree.command(name="build", description="Show build info for a hero")
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
        build_info = data.BUILDS.get(hero_key)
        await interaction.response.send_message(embeds=_build_embeds(hero_info, build_info))

    @tree.command(name="troop", description="Look up a troop type, or list all troops")
    @app_commands.describe(name="Troop name (leave blank to list all)")
    @app_commands.autocomplete(name=_troop_ac)
    async def cmd_troop(interaction: discord.Interaction, name: str = None):
        if not data.SOLDIERS:
            await interaction.response.send_message(_NOT_LOADED, ephemeral=True)
            return

        if name is None:
            by_class: dict[str, list[str]] = {}
            for s in data.SOLDIERS.values():
                by_class.setdefault(s["troop_class"].title(), []).append(s["name"])
            embed = discord.Embed(title="Langrisser Troops", color=0x8B0000)
            for cls in sorted(by_class):
                embed.add_field(name=cls, value=", ".join(sorted(by_class[cls]))[:1024], inline=False)
            embed.set_footer(text=f"{len(data.SOLDIERS)} troops total • {_FOOTER}")
            await interaction.response.send_message(embed=embed)
            return

        key = name.lower().strip()
        if key not in data.SOLDIERS:
            matched = data.best_match(name, list(data.SOLDIERS.keys()))
            if matched is None:
                await interaction.response.send_message(f"Troop `{name}` not found.", ephemeral=True)
                return
            key = matched
        await interaction.response.send_message(embed=_soldier_embed(data.SOLDIERS[key]))

    @tree.command(name="faction", description="List all heroes in a faction")
    @app_commands.describe(name="Faction name")
    @app_commands.autocomplete(name=_faction_ac)
    async def cmd_faction(interaction: discord.Interaction, name: str):
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

    @tree.command(name="bonds", description="Show bond information for a hero")
    @app_commands.describe(hero="Hero name")
    @app_commands.autocomplete(hero=_hero_ac)
    async def cmd_bonds(interaction: discord.Interaction, hero: str):
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
            await interaction.response.send_message(f"No bond data found for **{hero_info['name']}**.", ephemeral=True)
            return
        await interaction.response.send_message(embed=_bonds_embed(hero_info["name"], bond, hero_info))
