import re
import json
import difflib
import logging
import urllib.parse
import requests

logger = logging.getLogger(__name__)

_BASE_URL          = "https://raw.githubusercontent.com/bannernews/langrisser/master/js/"
_GITHUB_API        = "https://api.github.com/repos/bannernews/langrisser/commits"
_IMG              = "https://bannernews.github.io/langrisser/images/"
_PORTRAIT_BASE    = _IMG + "head/"
_HERO_PAGE_BASE   = "https://bannernews.github.io/langrisser/hero_en.html?name="
_CLASS_ICON_BASE  = _IMG + "classes/"
_SOLDIER_ICON_BASE = _IMG + "soldIcons/all/"
_FACTION_ICON_BASE = _IMG + "hero_filter/factions/"
_CHIBI_BASE        = _IMG + "heroes/heroes_list/"
_ITEM_ICON_BASE    = _IMG + "itemIcons/all/"
_TALENT_ICON_BASE  = _IMG + "skills/personal/"

FACTION_MAP = {
    "ЛС":   "Legion of Glory",
    "ИМП":  "Empire's Honor",
    "АП":   "Princess Alliance",
    "ИС":   "Origins of Light",
    "МС":   "Strategic Masters",
    "ТР":   "Dark Reincarnation",
    "ГГ":   "Protagonist",
    "ГЙ":   "Yless Legends",
    "МУ":   "Meteor",
    "ТАИР": "Mythical Realms",
    "РЕ":   "Langrisser Re:incarnation Tensei",
    "ГВ":   "Heroes of Time",
}

_GENDER = {"М", "Ж"}
_SKIP_CODES = {"ФБ"}

_MOVE_TYPE_EN = {
    "ходьба":  "Walking",
    "полет":   "Flying",
    "пловец":  "Swimming",
    "всадник": "Riding",
    "парение": "Hovering",
}

STORY_MAP = {
    "Л13":  "Ch. 1-3",
    "Л45":  "Ch. 4-5",
    "М1":   "Mobile Ch. 1",
    "М2":   "Mobile Ch. 2",
    "М3":   "Mobile Ch. 3",
    "РЕИ":  "Reincarnation",
    "Т":    "Tactical",
    "Мил":  "Militia",
}

# en_data.js field indices (confirmed from file header comment)
# 0-name 1-factions 2-rank 3-forge 4-sp 5-story
# 6-talent_name 7-talent_desc
# 8-item_name 9-item_type 10-item_hp 11-item_atk 12-item_int 13-item_def 14-item_mdef 15-item_skill 16-item_desc
# 17-unique_skill 18-sold_hp% 19-sold_atk% 20-sold_def% 21-sold_mdef%
# 22-soldiers 23-soldiers_sp 24-weapons 25-armor_type

_WEAPON_EN = {
    "топор": "Axe", "копье": "Spear", "меч": "Sword", "лук": "Bow",
    "жезл": "Staff", "книга": "Tome", "кинжал": "Dagger", "молот": "Hammer",
    "коса": "Scythe", "посох": "Staff", "катана": "Katana", "нож": "Knife",
}

_ARMOR_EN = {
    "тяжелая": "Heavy", "легкая": "Light", "волшебная": "Magic",
    "водная": "Aqua", "обычная": "Normal", "тканевая": "Cloth",
}

# Module-level data stores
HEROES:     dict[str, dict] = {}
BONDS:      dict[str, dict] = {}
SOLDIERS:   dict[str, dict] = {}
BUILDS:     dict[str, dict] = {}
HERO_NAMES: list[str]       = []

_RU_TO_EN:      dict[str, str] = {}   # Russian hero name -> English
_SOLDIER_RU_EN: dict[str, str] = {}   # Russian soldier name -> English
_last_commit_sha: str = ""


# ---------------------------------------------------------------------------
# Fetching & parsing
# ---------------------------------------------------------------------------

def _fetch(filename: str) -> str:
    r = requests.get(_BASE_URL + filename, timeout=15)
    r.raise_for_status()
    return r.text


def _extract_array(js: str, var_name: str) -> list:
    """Extract a JS array assigned to var_name and parse it as JSON."""
    m = re.search(rf'var\s+{re.escape(var_name)}\s*=', js)
    if not m:
        raise ValueError(f"Variable '{var_name}' not found in JS")
    start = js.index("[", m.end())
    depth, in_str, escape = 0, False, False
    i = start
    while i < len(js):
        c = js[i]
        if escape:
            escape = False
        elif c == "\\" and in_str:
            escape = True
        elif c == '"' and not in_str:
            in_str = True
        elif c == '"' and in_str:
            in_str = False
        elif not in_str:
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    break
        i += 1
    return json.loads(js[start : i + 1])


def _parse_factions(raw: str) -> tuple[list[str], list[str], str | None]:
    codes = [c.strip() for c in raw.split(",") if c.strip()]
    faction_codes = [c for c in codes if c not in _GENDER and c not in _SKIP_CODES]
    factions = [FACTION_MAP.get(c, c) for c in faction_codes]
    gender = "Female" if "Ж" in codes else "Male" if "М" in codes else None
    return factions, faction_codes, gender


def _field(row: list, i: int) -> str:
    """Safely get a string field from a row."""
    return row[i].strip() if i < len(row) and row[i] else ""


def _split_ru(s: str, tr: dict[str, str]) -> list[str]:
    """Split a comma-separated Russian string and translate each term."""
    return [tr.get(p.strip(), p.strip()) for p in s.split(",") if p.strip()] if s else []


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_heroes() -> None:
    global HEROES, HERO_NAMES, _RU_TO_EN
    rows = _extract_array(_fetch("heroesDat_en.js"), "heroesDat")
    heroes: dict[str, dict] = {}
    ru_map: dict[str, str] = {}
    for row in rows[1:]:
        name_en = row[1].strip()
        if not name_en:
            continue
        name_ru = row[0].strip()
        factions, faction_codes, gender = _parse_factions(row[2])
        key = name_en.lower()
        heroes[key] = {
            "name":          name_en,
            "name_ru":       name_ru,
            "factions":      factions,
            "faction_codes": faction_codes,
            "gender":        gender,
            "rarity":   row[3],
            "forge":    row[4] == "forge",
            "sp":       row[5] == "SP",
            "story":    STORY_MAP.get(row[6], row[6]),
        }
        ru_map[name_ru] = name_en
    HEROES     = heroes
    HERO_NAMES = sorted(h["name"] for h in heroes.values())
    _RU_TO_EN  = ru_map
    logger.info(f"Loaded {len(HEROES)} heroes")


def load_bonds() -> None:
    global BONDS

    def _tr(s: str) -> str:
        return _RU_TO_EN.get(s.strip(), s.strip())

    def _tr_list(s: str) -> list[str]:
        return [_tr(n) for n in s.split(",") if n.strip()] if s else []

    rows = _extract_array(_fetch("bondDat_en.js"), "bondDat")
    bonds: dict[str, dict] = {}
    for row in rows[1:]:
        name_en = _tr(row[0])
        key = name_en.lower()
        bonds[key] = {
            "name":           name_en,
            "def_bond":       _tr(row[1]) if row[1] else None,
            "atk_bond":       _tr(row[2]) if row[2] else None,
            "needed_for_def": _tr_list(row[3]),
            "needed_for_atk": _tr_list(row[4]),
            "rarity":         row[6],
        }
    BONDS = bonds
    logger.info(f"Loaded {len(BONDS)} bond entries")


def load_soldiers() -> None:
    global SOLDIERS, _SOLDIER_RU_EN
    rows = _extract_array(_fetch("soldDat_en.js"), "soldDat")
    soldiers: dict[str, dict] = {}
    ru_en: dict[str, str] = {}
    for row in rows[1:]:
        name_en = row[1].strip()
        if not name_en:
            continue
        name_ru = row[0].strip()
        ru_en[name_ru] = name_en
        key = name_en.lower()
        soldiers[key] = {
            "name":        name_en,
            "name_ru":     name_ru,
            "hp":          row[2],
            "atk":         row[3],
            "def":         row[4],
            "mdef":        row[5],
            "mobility":    row[6],
            "range":       row[7],
            "desc":        row[9],
            "troop_class": row[10],
            "heroes":      [_RU_TO_EN.get(h.strip(), h.strip()) for h in row[11].split(",") if h.strip()] if row[11] else [],
            "move_type":   _MOVE_TYPE_EN.get(row[12].strip(), row[12].strip()) if len(row) > 12 else "",
        }
    SOLDIERS       = soldiers
    _SOLDIER_RU_EN = ru_en
    logger.info(f"Loaded {len(SOLDIERS)} soldiers")


def load_builds() -> None:
    """Parse en_data.js for per-hero talent, personal item, and troop build info."""
    global BUILDS
    rows = _extract_array(_fetch("en_data.js"), "dataTable")

    # Fetch Russian data.js to get Russian talent names (used for icon filenames)
    ru_talent: dict[str, str] = {}
    try:
        rows_ru = _extract_array(_fetch("data.js"), "dataTable")
        for row_ru in rows_ru[1:]:
            name_ru = _field(row_ru, 0)
            if name_ru:
                ru_talent[name_ru] = _field(row_ru, 6)
    except Exception as e:
        logger.warning(f"Could not load Russian talent names: {e}")

    builds: dict[str, dict] = {}
    for row in rows[1:]:
        name_ru = _field(row, 0)
        if not name_ru:
            continue
        name_en = _RU_TO_EN.get(name_ru, name_ru)
        key = name_en.lower()

        # Soldier stat bonuses (stored as plain integers like "10", "35")
        def bonus(i: int) -> str:
            v = _field(row, i)
            return f"+{v}%" if v else ""

        # Translate Russian soldier names using the _SOLDIER_RU_EN map
        soldiers_raw = _field(row, 22)
        soldiers_en  = _split_ru(soldiers_raw, _SOLDIER_RU_EN)

        sp_soldiers_raw = _field(row, 23)
        sp_soldiers_en  = _split_ru(sp_soldiers_raw, _SOLDIER_RU_EN)

        weapons_raw = _field(row, 24)
        weapons_en  = _split_ru(weapons_raw, _WEAPON_EN)

        armor_raw = _field(row, 25)
        armor_en  = _ARMOR_EN.get(armor_raw, armor_raw) if armor_raw else ""

        # Personal item stat string — only include non-empty stats
        item_stat_parts = []
        for label, idx in [("HP", 10), ("ATK", 11), ("INT", 12), ("DEF", 13), ("MDEF", 14), ("SKILL", 15)]:
            v = _field(row, idx)
            if v:
                item_stat_parts.append(f"{label} +{v}")

        builds[key] = {
            "name":           name_en,
            "talent_name":    _field(row, 6),
            "talent_name_ru": ru_talent.get(name_ru, ""),
            "talent_desc":    _field(row, 7),
            "item_name":      _field(row, 8),
            "item_type":      _field(row, 9),
            "item_stats":     ", ".join(item_stat_parts),
            "item_desc":      _field(row, 16),
            "unique_skill":   _field(row, 17),
            "sold_hp":        bonus(18),
            "sold_atk":       bonus(19),
            "sold_def":       bonus(20),
            "sold_mdef":      bonus(21),
            "soldiers":       soldiers_en,
            "soldiers_sp":    sp_soldiers_en,
            "weapons":        weapons_en,
            "armor":          armor_en,
        }
    BUILDS = builds
    logger.info(f"Loaded {len(BUILDS)} build entries")


def load_all() -> None:
    for name, fn in [
        ("heroes",   load_heroes),
        ("bonds",    load_bonds),
        ("soldiers", load_soldiers),
        ("builds",   load_builds),
    ]:
        try:
            fn()
        except Exception as e:
            logger.error(f"Failed to load {name}: {e}")


# ---------------------------------------------------------------------------
# Update detection
# ---------------------------------------------------------------------------

def check_for_updates() -> tuple[bool, list[str]]:
    """
    Poll the GitHub API for the latest commit.
    Returns (data_was_reloaded, list_of_new_hero_names).
    On the very first call just stores the SHA and returns (False, []).
    """
    global _last_commit_sha

    r = requests.get(_GITHUB_API, params={"per_page": 1}, timeout=10)
    r.raise_for_status()
    sha = r.json()[0]["sha"]

    if not _last_commit_sha:
        _last_commit_sha = sha
        return False, []

    if sha == _last_commit_sha:
        return False, []

    # New commit — reload and diff
    old_names = set(HERO_NAMES)
    _last_commit_sha = sha
    load_all()
    new_names = [n for n in HERO_NAMES if n not in old_names]
    return True, new_names


# ---------------------------------------------------------------------------
# Portrait URL
# ---------------------------------------------------------------------------

def get_portrait_url(hero: dict) -> str:
    name_ru = hero.get("name_ru", "")
    if not name_ru:
        return ""
    return _PORTRAIT_BASE + urllib.parse.quote(name_ru + ".png")


def get_hero_page_url(hero: dict) -> str:
    name_ru = hero.get("name_ru", "")
    if not name_ru:
        return ""
    return _HERO_PAGE_BASE + urllib.parse.quote(name_ru)


def get_class_icon_url(troop_class: str) -> str:
    if not troop_class:
        return ""
    return _CLASS_ICON_BASE + troop_class.lower() + ".png"


def get_soldier_icon_url(soldier: dict) -> str:
    name_ru = soldier.get("name_ru", "")
    return (_SOLDIER_ICON_BASE + urllib.parse.quote(name_ru + ".png")) if name_ru else ""


def get_faction_icon_url(code: str) -> str:
    return (_FACTION_ICON_BASE + urllib.parse.quote(code + ".png")) if code else ""


def get_faction_code(faction_name: str) -> str:
    return next((code for code, name in FACTION_MAP.items() if name == faction_name), "")


def get_chibi_url(hero: dict) -> str:
    name_ru = hero.get("name_ru", "")
    return (_CHIBI_BASE + urllib.parse.quote(name_ru) + "/Chibi/0A.png") if name_ru else ""


def get_item_icon_url(hero: dict) -> str:
    name_ru = hero.get("name_ru", "")
    return (_ITEM_ICON_BASE + urllib.parse.quote(name_ru + ".png")) if name_ru else ""


def get_talent_icon_url(build: dict) -> str:
    name_ru = build.get("talent_name_ru", "")
    return (_TALENT_ICON_BASE + urllib.parse.quote(name_ru + ".png")) if name_ru else ""


# ---------------------------------------------------------------------------
# Local build-image override (optional — drop an image in builds/ to override)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[\s\-]+", "_", text)
    return re.sub(r"_+", "_", text)


def best_match(query: str, candidates: list[str]) -> str | None:
    if not candidates:
        return None
    q = normalize(query)
    norm = {normalize(c): c for c in candidates}
    if q in norm:
        return norm[q]
    subs = [orig for nk, orig in norm.items() if q in nk]
    if subs:
        return min(subs, key=len)
    close = difflib.get_close_matches(q, list(norm.keys()), n=1, cutoff=0.55)
    return norm[close[0]] if close else None


def find_hero(query: str) -> str | None:
    """Return the HEROES dict key (lowercase English name) for a user query."""
    if not HEROES:
        return None
    q = query.strip().lower()
    if q in HEROES:
        return q
    return best_match(query, list(HEROES.keys()))
