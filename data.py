import re
import json
import difflib
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_BASE_URL          = "https://raw.githubusercontent.com/bannernews/langrisser/master/js/"
_GITHUB_API        = "https://api.github.com/repos/bannernews/langrisser/commits"
_IMG               = "https://bannernews.github.io/langrisser/images/"
_PORTRAIT_BASE     = _IMG + "head/"
_HERO_PAGE_BASE    = "https://bannernews.github.io/langrisser/hero_en.html?name="
_CLASS_ICON_BASE   = _IMG + "classes/"
_SOLDIER_ICON_BASE = _IMG + "soldIcons/all/"
_FACTION_ICON_BASE = _IMG + "hero_filter/factions/"
_CHIBI_BASE        = _IMG + "heroes/heroes_list/"
_ITEM_ICON_BASE    = _IMG + "itemIcons/all/"
_TALENT_ICON_BASE  = _IMG + "skills/personal/"
_UA                = {"User-Agent": "KillerWhalesBot"}

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

_GENDER     = {"М", "Ж"}
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

_WEAPON_EN = {
    "топор": "Axe", "копье": "Spear", "меч": "Sword", "лук": "Bow",
    "жезл": "Staff", "книга": "Tome", "кинжал": "Dagger", "молот": "Hammer",
    "коса": "Scythe", "посох": "Staff", "катана": "Katana", "нож": "Knife",
}

_ARMOR_EN = {
    "тяжелая": "Heavy", "легкая": "Light", "волшебная": "Magic",
    "водная": "Aqua", "обычная": "Normal", "тканевая": "Cloth",
}

HEROES:     dict[str, dict] = {}
BONDS:      dict[str, dict] = {}
SOLDIERS:   dict[str, dict] = {}
BUILDS:     dict[str, dict] = {}
HERO_NAMES: list[str]       = []

_RU_TO_EN:      dict[str, str] = {}
_SOLDIER_RU_EN: dict[str, str] = {}
_last_commit_sha: str = ""


# ---------------------------------------------------------------------------
# Fetching & parsing
# ---------------------------------------------------------------------------

def _fetch(filename: str) -> str:
    req = urllib.request.Request(_BASE_URL + filename, headers=_UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()


def _extract_array(js: str, var_name: str) -> list:
    """Locate a JS variable assignment and extract its array value as JSON."""
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
    return row[i].strip() if i < len(row) and row[i] else ""


def _split_ru(s: str, tr: dict[str, str]) -> list[str]:
    return [tr.get(p.strip().lower(), p.strip()) for p in s.split(",") if p.strip()] if s else []


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_heroes() -> None:
    global HEROES, HERO_NAMES, _RU_TO_EN
    rows = _extract_array(_fetch("heroesDat_en.js"), "heroesDat")
    heroes, ru_map = {}, {}
    for row in rows[1:]:
        if not (name_en := row[1].strip()):
            continue
        name_ru = row[0].strip()
        factions, faction_codes, gender = _parse_factions(row[2])
        heroes[name_en.lower()] = {
            "name":          name_en,
            "name_ru":       name_ru,
            "factions":      factions,
            "faction_codes": faction_codes,
            "gender":        gender,
            "rarity":        row[3],
            "forge":         row[4] == "forge",
            "sp":            row[5] == "SP",
            "story":         STORY_MAP.get(row[6], row[6]),
        }
        ru_map[name_ru.lower()] = name_en
    HEROES, HERO_NAMES, _RU_TO_EN = heroes, sorted(h["name"] for h in heroes.values()), ru_map
    logger.info(f"Loaded {len(HEROES)} heroes")


def load_bonds() -> None:
    global BONDS
    tr  = lambda s: _RU_TO_EN.get(s.strip().lower(), s.strip())
    # Bond partner fields can contain comma-separated lists; translate each name individually
    trp = lambda s: (", ".join(tr(p) for p in s.split(",") if p.strip())) if s else None
    rows = _extract_array(_fetch("bondDat_en.js"), "bondDat")
    bonds: dict[str, dict] = {}
    for row in rows[1:]:
        name_en = tr(row[0])
        bonds[name_en.lower()] = {
            "name":           name_en,
            "def_bond":       trp(row[1]),
            "atk_bond":       trp(row[2]),
            "needed_for_def": _split_ru(row[3], _RU_TO_EN),
            "needed_for_atk": _split_ru(row[4], _RU_TO_EN),
        }
    BONDS = bonds
    logger.info(f"Loaded {len(BONDS)} bond entries")


def load_soldiers() -> None:
    global SOLDIERS, _SOLDIER_RU_EN
    rows = _extract_array(_fetch("soldDat_en.js"), "soldDat")
    soldiers, ru_en = {}, {}
    for row in rows[1:]:
        if not (name_en := row[1].strip()):
            continue
        name_ru = row[0].strip()
        ru_en[name_ru.lower()] = name_en
        soldiers[name_en.lower()] = {
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
            "heroes":      _split_ru(row[11], _RU_TO_EN),
            "move_type":   _MOVE_TYPE_EN.get(v := _field(row, 12), v),
        }
    SOLDIERS, _SOLDIER_RU_EN = soldiers, ru_en
    logger.info(f"Loaded {len(SOLDIERS)} soldiers")


def load_builds() -> None:
    global BUILDS
    rows = _extract_array(_fetch("en_data.js"), "dataTable")
    # data.js (Russian) is the source of talent names used as icon filenames
    ru_talent: dict[str, str] = {}
    try:
        rows_ru = _extract_array(_fetch("data.js"), "dataTable")
        for row_ru in rows_ru[1:]:
            if name_ru := _field(row_ru, 0):
                ru_talent[name_ru] = _field(row_ru, 6)
    except Exception as e:
        logger.warning(f"Could not load Russian talent names: {e}")
    builds: dict[str, dict] = {}
    for row in rows[1:]:
        if not (name_ru := _field(row, 0)):
            continue
        name_en = _RU_TO_EN.get(name_ru.lower(), name_ru)
        builds[name_en.lower()] = {
            "name":           name_en,
            "talent_name":    _field(row, 6),
            "talent_name_ru": ru_talent.get(name_ru, ""),
            "talent_desc":    _field(row, 7),
            "item_name":      _field(row, 8),
            "item_stats":     ", ".join(
                f"{lbl} +{v}"
                for lbl, idx in [("HP",10),("ATK",11),("INT",12),("DEF",13),("MDEF",14),("SKILL",15)]
                if (v := _field(row, idx))
            ),
            "item_desc":      _field(row, 16),
            "sold_hp":        f"+{hp}%" if (hp := _field(row, 18)) else "",
            "sold_atk":       f"+{atk}%" if (atk := _field(row, 19)) else "",
            "sold_def":       f"+{df}%" if (df := _field(row, 20)) else "",
            "sold_mdef":      f"+{mdef}%" if (mdef := _field(row, 21)) else "",
            "soldiers":       _split_ru(_field(row, 22), _SOLDIER_RU_EN),
            "soldiers_sp":    _split_ru(_field(row, 23), _SOLDIER_RU_EN),
            "weapons":        _split_ru(_field(row, 24), _WEAPON_EN),
            "armor":          _ARMOR_EN.get(ar, ar) if (ar := _field(row, 25)) else "",
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
    Poll GitHub for the latest commit SHA. First call seeds the baseline and
    returns (False, []). Subsequent calls reload all data when the SHA changes.
    """
    global _last_commit_sha
    req = urllib.request.Request(f"{_GITHUB_API}?per_page=1", headers=_UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        sha = json.loads(r.read())[0]["sha"]
    if not _last_commit_sha:
        _last_commit_sha = sha
        return False, []
    if sha == _last_commit_sha:
        return False, []
    old_names = set(HERO_NAMES)
    _last_commit_sha = sha
    load_all()
    return True, [n for n in HERO_NAMES if n not in old_names]


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def get_portrait_url(hero: dict) -> str:
    name_ru = hero.get("name_ru", "")
    return (_PORTRAIT_BASE + urllib.parse.quote(name_ru + ".png")) if name_ru else ""


def get_hero_page_url(hero: dict) -> str:
    name_ru = hero.get("name_ru", "")
    return (_HERO_PAGE_BASE + urllib.parse.quote(name_ru)) if name_ru else ""


def get_class_icon_url(troop_class: str) -> str:
    return (_CLASS_ICON_BASE + troop_class.lower() + ".png") if troop_class else ""


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
    if not HEROES:
        return None
    q = query.strip().lower()
    return q if q in HEROES else best_match(query, list(HEROES.keys()))
