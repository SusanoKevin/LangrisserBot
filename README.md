# LangrisserBot

A Discord bot for [Langrisser Mobile](https://langrisser.zlongame.com/main.html) that provides hero info, build, faction, and bond lookups via slash commands. Game data is pulled live from the bannernews community repository and refreshed automatically every 4 hours.

## Commands

| Command | Description |
|---|---|
| `/hero [name]` | Hero stats, faction, rarity, and portrait. Omit name to list all heroes. |
| `/build <name>` | Talent, personal item, recommended soldiers, and gear restrictions. |
| `/troop [name]` | Troop stats and which heroes use them. Omit name to list all troops. |
| `/faction <name>` | All heroes in a faction grouped by rarity. |
| `/bonds <name>` | A hero's DEF/ATK bond partners and who needs them. |

## Setup

**Requirements:** Python 3.11+

1. Clone the repo and create a virtual environment:
   ```bash
   git clone https://github.com/SusanoKevin/LangrisserBot.git
   cd LangrisserBot
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Create a `.env` file:
   ```
   DISCORD_TOKEN=your_token_here
   ANNOUNCE_CHANNEL_ID=0        # optional: channel ID for new-hero announcements
   BUILDS_DIR=builds            # optional: path to local build image overrides
   ```

3. Run:
   ```bash
   python bot.py
   ```

## Data source

All game data is fetched from the [bannernews/langrisser](https://github.com/bannernews/langrisser) repository. The bot checks for upstream commits every 4 hours and reloads automatically. If `ANNOUNCE_CHANNEL_ID` is set, new heroes are announced in that channel when detected.
