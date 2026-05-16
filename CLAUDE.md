# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the bot

```bash
# Activate the virtual environment
source .venv/bin/activate

# Run the bot
python bot.py
```

## Environment setup

Copy `.env` and fill in your values:

```
DISCORD_TOKEN=your_token_here
ANNOUNCE_CHANNEL_ID=0          # optional: channel ID for new-hero announcements
BUILDS_DIR=builds              # optional: path to local build image overrides
```

## Installing dependencies

```bash
pip install -r requirements.txt
```

## Architecture

**`bot.py`** is the main entry point. It creates the Discord client, registers slash commands directly (see below), loads game data on `on_ready`, and runs an `auto_refresh` background loop every 4 hours that calls `data.check_for_updates()` to detect upstream changes and optionally announce new heroes to a configured channel.

**`commands.py`** defines all five slash commands (`/hero`, `/build`, `/troop`, `/faction`, `/bonds`) inside a single `register(tree)` function, along with autocomplete callbacks and embed builders. To activate these commands, call `commands.register(tree)` from `bot.py` after creating the `CommandTree`.

**`data.py`** is the data layer. It fetches JS files from the bannernews GitHub repo at startup (`heroesDat_en.js`, `bondDat_en.js`, `soldDat_en.js`, `en_data.js`) using `_extract_array()` to parse embedded JS arrays as JSON. All game data lives in module-level dicts (`HEROES`, `BONDS`, `SOLDIERS`, `BUILDS`, `HERO_NAMES`). Hero keys are always lowercase English names. Russian↔English name translation maps (`_RU_TO_EN`, `_SOLDIER_RU_EN`) are built during `load_heroes()` and `load_soldiers()`, and must be populated before `load_bonds()` or `load_builds()` are called — the order in `load_all()` matters.

## Adding a new slash command

Add the command inside `commands.register()` in `commands.py`. Use the existing autocomplete callbacks (`_hero_ac`, `_troop_ac`, `_faction_ac`) if the command takes a hero/troop/faction argument.

## Local build image overrides

Drop an image file named after the hero (e.g., `builds/leon.png`) into the `builds/` directory. The `/build` command will prefer this image over structured data from `en_data.js`. Supported extensions: `.png`, `.jpg`, `.jpeg`, `.webp`.

## Data source

All game data is fetched from `https://raw.githubusercontent.com/bannernews/langrisser/master/js/`. The `FACTION_MAP`, `STORY_MAP`, `_WEAPON_EN`, and `_ARMOR_EN` dicts in `data.py` translate Russian codes from that source into English labels.
