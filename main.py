import os
import re
import json
import html
import time
import random
import hashlib
import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from urllib.parse import quote
from difflib import SequenceMatcher

import requests
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Bot,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

load_dotenv()

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@BeauQuot").strip()

try:
    ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
except Exception:
    ADMIN_CHAT_ID = 0

DB_FILE = os.getenv("DB_FILE", "quotes.db")
CONFIG_FILE = os.getenv("CONFIG_FILE", "bot_config.json")
ADMIN_ID_FILE = os.getenv("ADMIN_ID_FILE", "admin_id.txt")

# Optional Pollinations key. The pipeline also tries the legacy public
# endpoint without a key, but current Pollinations API documentation
# recommends authenticated generation.
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "").strip()

QUOTE_CORPUS_FILE = os.getenv("QUOTE_CORPUS_FILE", "quotes_corpus.json")
QUOTE_CORPUS_URL = os.getenv(
    "QUOTE_CORPUS_URL",
    "https://raw.githubusercontent.com/dwyl/quotes/main/quotes.json",
)

IMAGE_TIMEOUT = int(os.getenv("IMAGE_TIMEOUT", "180"))
MIN_IMAGE_BYTES = 15000
MAX_IMAGE_BYTES = 12 * 1024 * 1024

# Similarity thresholds:
# 1.0 = identical. The higher the threshold, the more aggressively we reject.
LEXICAL_DUP_THRESHOLD = float(os.getenv("LEXICAL_DUP_THRESHOLD", "0.88"))
SEMANTIC_DUP_THRESHOLD = float(os.getenv("SEMANTIC_DUP_THRESHOLD", "0.90"))

# Number of recent posts used to diversify visuals/topics.
RECENT_DIVERSITY_WINDOW = int(os.getenv("RECENT_DIVERSITY_WINDOW", "8"))

DEFAULT_HEADERS = {
    "User-Agent": "BeauQuot/2.0 (+Telegram quote bot)",
}

NEGATIVE_PROMPT = (
    "text, words, letters, numbers, typography, watermark, logo, signature, "
    "caption, poster, quote card, UI, sign, label, book, newspaper, screen, "
    "phone screen, packaging, billboard, storefront, menu, document, "
    "deformed hands, extra fingers, extra limbs, bad anatomy, plastic skin, "
    "waxy face, stock photo, fashion advertisement, motivational poster, "
    "oversaturated, excessive HDR, fake glow, surreal artifacts"
)

POST_LOCK = asyncio.Lock()

# ============================================================
# CONTENT RULES
# ============================================================

# Strong semantic/topic signals. These are deliberately broader than the
# old "two keywords or reject" rule.
TOPIC_WEIGHTS = {
    "self_love": {
        "keywords": {
            "self": 2.5, "yourself": 3.0, "worth": 3.0, "worthy": 3.0,
            "enough": 3.0, "accept": 2.5, "acceptance": 2.5,
            "value": 2.0, "respect": 2.0, "confidence": 2.5,
        },
        "phrases": ["love yourself", "believe in yourself", "be yourself"],
    },
    "femininity": {
        "keywords": {
            "woman": 3.0, "women": 3.0, "she": 2.0, "her": 1.5,
            "feminine": 3.0, "womanhood": 3.0, "girl": 1.5,
        },
        "phrases": ["being a woman", "woman you are"],
    },
    "love": {
        "keywords": {
            "love": 2.5, "heart": 2.0, "affection": 2.5, "beloved": 2.5,
            "romance": 2.5, "cherish": 2.5, "intimacy": 2.0,
        },
        "phrases": ["fall in love", "love deeply", "love someone"],
    },
    "healing": {
        "keywords": {
            "heal": 3.0, "healing": 3.0, "recover": 2.5, "restore": 2.5,
            "peace": 1.5, "release": 2.0, "forgive": 2.0, "renew": 2.5,
        },
        "phrases": ["let go", "move on", "inner peace"],
    },
    "strength": {
        "keywords": {
            "strong": 2.5, "strength": 3.0, "courage": 3.0, "brave": 2.5,
            "fearless": 3.0, "resilient": 3.0, "resilience": 3.0,
            "power": 2.0, "rise": 1.5,
        },
        "phrases": ["stand strong", "keep going", "rise again"],
    },
    "growth": {
        "keywords": {
            "grow": 2.5, "growth": 3.0, "change": 2.0, "transform": 3.0,
            "become": 2.5, "evolve": 3.0, "journey": 2.0, "learn": 1.5,
        },
        "phrases": ["become yourself", "grow through", "new beginning"],
    },
    "dreams": {
        "keywords": {
            "dream": 2.5, "hope": 2.5, "future": 1.5, "vision": 2.0,
            "imagine": 2.0, "believe": 2.0, "possibility": 2.0,
        },
        "phrases": ["follow your dreams", "believe in your dreams"],
    },
    "beauty": {
        "keywords": {
            "beauty": 3.0, "beautiful": 3.0, "grace": 2.0, "elegance": 2.5,
            "radiant": 2.5, "shine": 2.0, "glow": 2.0,
        },
        "phrases": ["inner beauty", "true beauty"],
    },
    "relationships": {
        "keywords": {
            "friend": 2.0, "friendship": 2.5, "mother": 2.5, "daughter": 2.5,
            "sister": 2.5, "connection": 2.0, "together": 1.5,
        },
        "phrases": ["close to", "by your side"],
    },
    "freedom": {
        "keywords": {
            "free": 2.5, "freedom": 3.0, "independent": 3.0, "independence": 3.0,
            "wild": 1.5, "liberate": 2.5,
        },
        "phrases": ["be free", "live freely"],
    },
}

EXCLUDED_WORDS = {
    "war", "violence", "death", "kill", "murder", "blood", "hate",
    "revenge", "destroy", "enemy", "suffer", "torture", "prison",
    "politics", "politician", "election", "weapon", "terror",
}

# Generic inspirational material is allowed, but these are useful quality
# penalties so the channel does not become a stream of slogans.
GENERIC_WORDS = {
    "success", "successfully", "winning", "winner", "motivation",
    "motivational", "greatness", "dream", "believe",
}

MOODS = {
    "tender": {
        "keywords": {"soft", "gentle", "tender", "warm", "kind", "care", "grace"},
        "visual": "quiet, intimate, delicate, warm natural light",
    },
    "empowered": {
        "keywords": {"strong", "strength", "power", "courage", "brave", "rise", "bold"},
        "visual": "grounded, confident, cinematic contrast, controlled light",
    },
    "dreamy": {
        "keywords": {"dream", "hope", "imagine", "wonder", "magic", "star"},
        "visual": "dreamlike atmosphere, airy depth, luminous twilight",
    },
    "romantic": {
        "keywords": {"love", "heart", "passion", "kiss", "embrace", "beloved", "cherish"},
        "visual": "intimate, warm, emotionally restrained, golden-hour light",
    },
    "introspective": {
        "keywords": {"soul", "inner", "reflect", "truth", "self", "mindful", "become"},
        "visual": "contemplative, quiet, cinematic, soft directional light",
    },
    "healing": {
        "keywords": {"heal", "recover", "grow", "rebuild", "transform", "renew", "peace"},
        "visual": "restful, spacious, soft morning light, subtle renewal",
    },
    "peaceful": {
        "keywords": {"peace", "calm", "serene", "still", "quiet", "tranquil", "harmony"},
        "visual": "minimal, serene, balanced composition, soft daylight",
    },
    "confident": {
        "keywords": {"enough", "worthy", "beautiful", "shine", "confident", "proud", "fearless"},
        "visual": "elegant, assured, editorial, clean directional lighting",
    },
}

VISUAL_ARCHETYPES = [
    {
        "name": "quiet_window",
        "description": "a quiet architectural interior with one adult woman near a tall window, morning light, subtle reflection, private moment",
        "avoid": "fashion pose, glamour, mirror selfie",
        "subjects": "one adult woman, natural posture",
        "camera": "50mm editorial photography, eye-level, shallow but believable depth of field",
        "composition": "asymmetrical composition, subject on a third, generous negative space",
    },
    {
        "name": "solitary_landscape",
        "description": "one adult woman standing small within a vast natural landscape, wind moving fabric, distant horizon, contemplative stillness",
        "avoid": "fantasy landscape, giant flowers, heroic pose",
        "subjects": "one adult woman, small in frame",
        "camera": "35mm cinematic landscape photography",
        "composition": "wide establishing shot, strong foreground-midground-background separation",
    },
    {
        "name": "intimate_portrait",
        "description": "close editorial portrait of an adult woman with natural skin texture, restrained expression, quiet confidence",
        "avoid": "beauty-ad aesthetics, plastic skin, exaggerated makeup",
        "subjects": "one adult woman",
        "camera": "85mm portrait lens, soft falloff, realistic skin detail",
        "composition": "tight portrait, eyes slightly off-axis, clean background",
    },
    {
        "name": "two_people_connection",
        "description": "two adult people sharing a quiet believable moment of closeness, subtle gesture and body language, no staged romance",
        "avoid": "wedding pose, kissing cliché, melodrama",
        "subjects": "two adult people, natural body language",
        "camera": "50mm documentary editorial photography",
        "composition": "medium shot, layered positioning, intimate but spacious framing",
    },
    {
        "name": "hands_gesture",
        "description": "cinematic close-up of adult hands performing a simple meaningful everyday gesture, tactile materials, quiet emotion",
        "avoid": "manicure advertisement, jewelry advertisement, text-bearing objects",
        "subjects": "adult hands only",
        "camera": "85mm macro-like editorial detail, realistic texture",
        "composition": "single focal gesture, uncluttered frame",
    },
    {
        "name": "threshold",
        "description": "an adult woman crossing from a dim interior into a softly illuminated open space through an architectural doorway",
        "avoid": "fantasy portal, glowing doorway, surreal effects",
        "subjects": "one adult woman, natural silhouette",
        "camera": "35mm cinematic photography",
        "composition": "strong frame-within-frame, leading lines toward open space",
    },
    {
        "name": "urban_dawn",
        "description": "one adult woman moving through a quiet modern city at dawn after rain, reflective pavement, authentic documentary atmosphere",
        "avoid": "fashion campaign, crowds, neon cyberpunk",
        "subjects": "one adult woman, candid movement",
        "camera": "35mm street photography, natural motion",
        "composition": "off-center subject, architectural leading lines",
    },
    {
        "name": "still_life_meaning",
        "description": "a refined still life of a few ordinary unmarked objects arranged with visual restraint, natural window light, subtle signs of a lived life",
        "avoid": "product photography, luxury advertising, books, labels, screens, writing",
        "subjects": "objects only, no people",
        "camera": "50mm still-life editorial photography",
        "composition": "three-object maximum, strong negative space, tactile realism",
    },
    {
        "name": "nature_detail",
        "description": "an intimate natural detail suggesting renewal: fresh leaves, rain on stone, morning grass, or a new bud in realistic scale",
        "avoid": "giant fantasy flowers, magical glow, surreal colors",
        "subjects": "natural elements only",
        "camera": "macro-inspired nature photography, realistic optics",
        "composition": "single focal detail, soft environmental context",
    },
    {
        "name": "open_road",
        "description": "a quiet open path through real countryside with one distant adult woman walking freely toward a broad horizon",
        "avoid": "travel advertisement, car commercial, fantasy sky",
        "subjects": "one distant adult woman",
        "camera": "35mm cinematic landscape photography",
        "composition": "strong leading lines, low visual clutter, horizon balance",
    },
    {
        "name": "architectural_strength",
        "description": "one adult woman standing calmly inside monumental modern architecture, surrounded by clean geometry and controlled daylight",
        "avoid": "superhero pose, corporate advertisement",
        "subjects": "one adult woman",
        "camera": "28mm architectural editorial photography",
        "composition": "geometric symmetry with a deliberately offset human figure",
    },
    {
        "name": "soft_domestic_moment",
        "description": "an adult woman alone in a simple elegant home, doing an ordinary quiet activity, soft late-afternoon light",
        "avoid": "luxury showroom, staged influencer lifestyle",
        "subjects": "one adult woman, candid",
        "camera": "50mm cinematic lifestyle photography",
        "composition": "observational medium-wide shot, natural framing through architecture",
    },
    {
        "name": "water_reflection",
        "description": "one adult woman near calm water at dusk, subtle reflection, restrained atmosphere, realistic landscape",
        "avoid": "mermaid fantasy, dramatic sunset cliché, glowing effects",
        "subjects": "one adult woman",
        "camera": "50mm cinematic photography",
        "composition": "horizontal balance between person, water, and open space",
    },
    {
        "name": "editorial_detail",
        "description": "an elegant detail of fabric, skin, hair, shadow, and natural material in a quiet editorial composition",
        "avoid": "fashion catalog, sexualized framing, glossy commercial look",
        "subjects": "abstract human detail, no face required",
        "camera": "85mm fine-art editorial photography",
        "composition": "minimal close crop, one dominant form and soft negative space",
    },
]

# These are intentionally literal enough to be understandable by image models,
# but avoid the repetitive "woman + flowers + golden light" pattern.
THEME_VISUALS = {
    "self_love": "visual metaphor of self-acceptance and being comfortable in one's own presence",
    "femininity": "quiet visual celebration of womanhood without stereotypes or sexualization",
    "love": "subtle human closeness and emotional connection, never a literal heart symbol",
    "healing": "visual sense of recovery, breathing room, and a new calm chapter",
    "strength": "quiet resilience rather than aggression; grounded posture and emotional control",
    "growth": "a transition from one life phase to another, expressed through environment and movement",
    "dreams": "a sense of possibility and looking toward something not yet reached",
    "beauty": "natural elegance, authentic presence, understated visual refinement",
    "relationships": "warm connection between people, candid and emotionally believable",
    "freedom": "open space, movement, independence, and absence of confinement",
}

FALLBACK_QUOTES = [
    ("You yourself, as much as anybody in the entire universe, deserve your love and affection.", "Buddha"),
    ("Beauty begins the moment you decide to be yourself.", "Coco Chanel"),
    ("A woman is the full circle. Within her is the power to create, nurture and transform.", "Diane Mariechild"),
    ("Be the woman you needed as a girl.", "Unknown"),
    ("You are allowed to be both a masterpiece and a work in progress, simultaneously.", "Sophia Bush"),
    ("The most courageous act is still to think for yourself. Aloud.", "Coco Chanel"),
    ("The strongest women are not those who have never been broken, but those who have rebuilt themselves.", "Unknown"),
]

# ============================================================
# LOGGING / CONFIG
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("beauquot")


class BotConfig:
    def __init__(self):
        self.interval_hours = 6
        self.auto_posting = True
        self.last_post_time = None

    def save_config(self):
        data = {
            "interval_hours": self.interval_hours,
            "auto_posting": self.auto_posting,
            "last_post_time": self.last_post_time.isoformat() if self.last_post_time else None,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.interval_hours = int(data.get("interval_hours", 6))
            self.auto_posting = bool(data.get("auto_posting", True))
            value = data.get("last_post_time")
            self.last_post_time = datetime.fromisoformat(value) if value else None
        except FileNotFoundError:
            self.save_config()
        except Exception as e:
            logger.warning("Config load error: %s", e)
            self.save_config()


config = BotConfig()


def load_admin_id():
    global ADMIN_CHAT_ID
    if ADMIN_CHAT_ID > 0:
        return
    try:
        if os.path.exists(ADMIN_ID_FILE):
            with open(ADMIN_ID_FILE, "r", encoding="utf-8") as f:
                ADMIN_CHAT_ID = int(f.read().strip())
    except Exception as e:
        logger.warning("Admin id load error: %s", e)


def save_admin_id(user_id):
    global ADMIN_CHAT_ID
    ADMIN_CHAT_ID = int(user_id)
    try:
        with open(ADMIN_ID_FILE, "w", encoding="utf-8") as f:
            f.write(str(ADMIN_CHAT_ID))
    except Exception as e:
        logger.warning("Admin id save error: %s", e)


def is_admin(update: Update):
    user = update.effective_user
    return bool(user and user.id == ADMIN_CHAT_ID)

# ============================================================
# DB
# ============================================================


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_text TEXT NOT NULL,
                author TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                quote_hash TEXT NOT NULL UNIQUE,
                source TEXT DEFAULT '',
                source_url TEXT DEFAULT '',
                topic_json TEXT DEFAULT '[]',
                mood TEXT DEFAULT '',
                quality_score REAL DEFAULT 0,
                used_count INTEGER DEFAULT 0,
                last_used_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS published_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_id INTEGER,
                quote_hash TEXT NOT NULL UNIQUE,
                quote_text TEXT NOT NULL,
                author TEXT NOT NULL,
                published_at TEXT DEFAULT CURRENT_TIMESTAMP,
                image_hash TEXT DEFAULT '',
                image_provider TEXT DEFAULT '',
                visual_archetype TEXT DEFAULT '',
                prompt_hash TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visual_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archetype TEXT NOT NULL,
                theme TEXT NOT NULL,
                mood TEXT NOT NULL,
                published_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quotes_hash ON quotes(quote_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quotes_used ON quotes(used_count, last_used_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_published_hash ON published_quotes(quote_hash)")
        conn.commit()


def normalize_text(text):
    text = html.unescape(str(text or "")).lower()
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def quote_hash(text, author):
    payload = normalize_text(text) + "|" + normalize_text(author)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def image_hash(data):
    return hashlib.sha256(data).hexdigest() if data else ""


def upsert_quote(text, author, source="", source_url="", quality_score=0, topics=None, mood=""):
    text = clean_text(text)
    author = clean_text(author) or "Unknown"
    if not text:
        return None
    h = quote_hash(text, author)
    topics = topics or []
    with get_db() as conn:
        conn.execute("""
            INSERT INTO quotes
                (quote_text, author, normalized_text, quote_hash, source,
                 source_url, topic_json, mood, quality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(quote_hash) DO UPDATE SET
                source = CASE WHEN quotes.source = '' THEN excluded.source ELSE quotes.source END,
                source_url = CASE WHEN quotes.source_url = '' THEN excluded.source_url ELSE quotes.source_url END,
                quality_score = MAX(quotes.quality_score, excluded.quality_score)
        """, (
            text, author, normalize_text(text), h, source, source_url,
            json.dumps(topics, ensure_ascii=False), mood, float(quality_score)
        ))
        conn.commit()
        row = conn.execute("SELECT * FROM quotes WHERE quote_hash=?", (h,)).fetchone()
        return dict(row) if row else None


def is_published(text, author):
    h = quote_hash(text, author)
    with get_db() as conn:
        return conn.execute(
            "SELECT 1 FROM published_quotes WHERE quote_hash=?", (h,)
        ).fetchone() is not None


def mark_published(content, image_bytes=None, provider="", archetype=""):
    q = content["quote"]
    h = quote_hash(q["quote_text"], q["author"])

    # Idempotent: Telegram may have accepted the post even if DB recording
    # encounters an error.
    with get_db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO published_quotes
                (quote_id, quote_hash, quote_text, author, image_hash,
                 image_provider, visual_archetype, prompt_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            q.get("id"), h, q["quote_text"], q["author"],
            image_hash(image_bytes), provider, archetype,
            hashlib.sha256(content["image_prompt"].encode("utf-8")).hexdigest()
        ))

        themes = content.get("themes") or content.get("topics") or []
        visual_concept = content.get("visual_concept") or {}
        theme = themes[0] if themes else visual_concept.get("theme", "soul")
        mood = content.get("mood") or visual_concept.get("mood") or "introspective"

        conn.execute("""
            UPDATE quotes
            SET used_count = used_count + 1, last_used_at = ?
            WHERE quote_hash = ?
        """, (datetime.now(timezone.utc).isoformat(), h))

        conn.execute("""
            INSERT INTO visual_history(archetype, theme, mood)
            VALUES (?, ?, ?)
        """, (archetype or "unknown", theme, mood))

        conn.commit()


def get_recent_visuals(limit=RECENT_DIVERSITY_WINDOW):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT archetype, theme, mood
            FROM visual_history
            ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_stats():
    with get_db() as conn:
        quotes = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
        published = conn.execute("SELECT COUNT(*) FROM published_quotes").fetchone()[0]
        return quotes, published

# ============================================================
# CORPUS
# ============================================================


def clean_text(value):
    if not value:
        return ""
    value = html.unescape(str(value))
    value = re.sub(r"\s+", " ", value).strip()
    return value


def download_quote_corpus():
    if os.path.exists(QUOTE_CORPUS_FILE):
        try:
            with open(QUOTE_CORPUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 100:
                return data
        except Exception:
            pass

    try:
        logger.info("Downloading quote corpus...")
        r = requests.get(QUOTE_CORPUS_URL, headers=DEFAULT_HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            with open(QUOTE_CORPUS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return data
    except Exception as e:
        logger.warning("Quote corpus download failed: %s", e)

    return FALLBACK_QUOTES


def score_topics(text):
    low = normalize_text(text)
    words = set(re.findall(r"\b\w+\b", low, flags=re.UNICODE))
    scores = {}

    for topic, rules in TOPIC_WEIGHTS.items():
        score = 0.0
        for word, weight in rules["keywords"].items():
            if word in words:
                score += weight
        for phrase in rules["phrases"]:
            if phrase in low:
                score += 3.0
        scores[topic] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    topics = [name for name, score in ranked if score >= 1.5][:4]
    return topics or ["soul"]


def quality_score(text, author):
    low = normalize_text(text)
    words = low.split()

    if len(words) < 6 or len(words) > 70:
        return -100.0
    if any(w in low.split() for w in EXCLUDED_WORDS):
        return -100.0

    score = 0.0
    if 10 <= len(words) <= 42:
        score += 3.0
    elif len(words) <= 55:
        score += 1.0

    if len(set(words)) / max(len(words), 1) > 0.55:
        score += 1.5

    topics = score_topics(text)
    score += min(sum(
        TOPIC_WEIGHTS.get(t, {}).get("keywords", {}).get(w, 0)
        for t in topics for w in words
    ), 8.0)

    if author and author.lower() not in {"unknown", "anonymous"}:
        score += 1.0

    generic_count = sum(1 for w in words if w in GENERIC_WORDS)
    score -= generic_count * 0.4

    if text.endswith((".", "!", "?")):
        score += 0.5

    return round(score, 3)


def analyze_mood(text):
    low = normalize_text(text)
    words = set(low.split())
    scores = {
        mood: sum(1 for w in rules["keywords"] if w in words)
        for mood, rules in MOODS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "introspective"


def seed_database():
    corpus = download_quote_corpus()
    inserted = 0
    for item in corpus:
        if isinstance(item, dict):
            text = clean_text(item.get("text") or item.get("quote"))
            author = clean_text(item.get("author"))
            source_url = clean_text(item.get("source"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            text, author = clean_text(item[0]), clean_text(item[1])
            source_url = ""
        else:
            continue

        if not text or not author:
            continue

        qscore = quality_score(text, author)
        if qscore < 3.0:
            continue

        topics = score_topics(text)
        mood = analyze_mood(text)
        before = get_stats()[0]
        upsert_quote(
            text, author,
            source="dwyl/quotes" if isinstance(item, dict) else "fallback",
            source_url=source_url,
            quality_score=qscore,
            topics=topics,
            mood=mood,
        )
        after = get_stats()[0]
        inserted += max(0, after - before)

    logger.info("Quote database ready: %s new candidates", inserted)

# ============================================================
# DEDUPLICATION
# ============================================================


def token_set(text):
    return set(re.findall(r"\b[a-zA-Zа-яА-ЯёЁ0-9]{3,}\b", normalize_text(text)))


def lexical_similarity(a, b):
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = token_set(a), token_set(b)
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    return max(seq, jaccard)

# Optional CPU semantic model. It is NOT used for image generation.
# If unavailable, the pipeline remains fully functional with lexical checks.
_semantic_model = None
_semantic_failed = False


def load_semantic_model():
    global _semantic_model, _semantic_failed
    if _semantic_failed:
        return None
    if _semantic_model is not None:
        return _semantic_model

    try:
        from sentence_transformers import SentenceTransformer
        _semantic_model = SentenceTransformer(
            os.getenv(
                "EMBEDDING_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2"
            ),
            device="cpu",
        )
        return _semantic_model
    except Exception as e:
        _semantic_failed = True
        logger.warning(
            "Optional semantic model unavailable; using lexical dedup: %s", e
        )
        return None


def semantic_similarity(a, b):
    model = load_semantic_model()
    if model is None:
        return 0.0
    try:
        emb = model.encode([a, b], normalize_embeddings=True)
        return float(emb[0] @ emb[1])
    except Exception:
        return 0.0


def is_semantic_duplicate(candidate_text, published_rows):
    for row in published_rows:
        lex = lexical_similarity(candidate_text, row["quote_text"])
        if lex >= LEXICAL_DUP_THRESHOLD:
            return True

    # Only use the CPU model when lexical similarity is inconclusive.
    model = load_semantic_model()
    if model is None:
        return False

    for row in published_rows[-250:]:
        sim = semantic_similarity(candidate_text, row["quote_text"])
        if sim >= SEMANTIC_DUP_THRESHOLD:
            return True
    return False


def get_candidate_rows(limit=500):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT *
            FROM quotes
            WHERE quality_score >= 3
            ORDER BY quality_score DESC, used_count ASC, RANDOM()
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_published_rows(limit=500):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT quote_text, author
            FROM published_quotes
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def choose_unique_quote():
    candidates = get_candidate_rows()
    published = get_published_rows()

    recent_topics = {}
    for row in get_recent_visuals():
        recent_topics[row["theme"]] = recent_topics.get(row["theme"], 0) + 1

    scored = []

    for q in candidates:
        if is_published(q["quote_text"], q["author"]):
            continue

        if is_semantic_duplicate(q["quote_text"], published):
            continue

        topics = json.loads(q.get("topic_json") or "[]")
        diversity_bonus = 0.0
        for t in topics:
            diversity_bonus += max(0, 2 - recent_topics.get(t, 0))

        # Prefer quality, but do not always take the top item.
        final_score = (
            float(q["quality_score"])
            + diversity_bonus
            - min(q["used_count"], 5) * 2
            + random.uniform(0, 2.0)
        )
        scored.append((final_score, q))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    # Never reset the published database. If the corpus is exhausted, try
    # fallback quotes and report failure instead of recycling history.
    for text, author in FALLBACK_QUOTES:
        if not is_published(text, author):
            q = upsert_quote(
                text, author,
                source="built-in fallback",
                quality_score=5,
                topics=score_topics(text),
                mood=analyze_mood(text),
            )
            if q:
                return q

    return None

# ============================================================
# VISUAL CONCEPT
# ============================================================


def select_archetype(themes, mood):
    recent = get_recent_visuals()
    used = {r["archetype"] for r in recent}
    theme = themes[0] if themes else "soul"

    # Theme-to-visual routing: the same theme can be expressed through people,
    # spaces, objects, or nature. This prevents the channel from becoming
    # "woman + flowers + golden light".
    theme_preferences = {
        "self_love": {"intimate_portrait", "quiet_window", "soft_domestic_moment", "editorial_detail"},
        "femininity": {"intimate_portrait", "editorial_detail", "soft_domestic_moment", "nature_detail"},
        "love": {"two_people_connection", "water_reflection", "soft_domestic_moment", "quiet_window"},
        "healing": {"quiet_window", "nature_detail", "water_reflection", "threshold", "soft_domestic_moment"},
        "strength": {"architectural_strength", "intimate_portrait", "open_road", "urban_dawn"},
        "growth": {"threshold", "nature_detail", "open_road", "quiet_window"},
        "dreams": {"solitary_landscape", "open_road", "water_reflection", "threshold"},
        "beauty": {"nature_detail", "editorial_detail", "still_life_meaning", "intimate_portrait"},
        "relationships": {"two_people_connection", "hands_gesture", "soft_domestic_moment"},
        "freedom": {"solitary_landscape", "open_road", "urban_dawn", "water_reflection"},
    }
    mood_preferences = {
        "tender": {"two_people_connection", "soft_domestic_moment", "quiet_window"},
        "romantic": {"two_people_connection", "water_reflection", "quiet_window"},
        "introspective": {"quiet_window", "water_reflection", "editorial_detail", "still_life_meaning"},
        "healing": {"nature_detail", "threshold", "quiet_window"},
        "empowered": {"architectural_strength", "open_road", "urban_dawn", "intimate_portrait"},
        "confident": {"architectural_strength", "intimate_portrait", "urban_dawn"},
    }

    candidates = [a for a in VISUAL_ARCHETYPES if a["name"] not in used]
    if not candidates:
        candidates = VISUAL_ARCHETYPES[:]

    preferred = theme_preferences.get(theme, set()) | mood_preferences.get(mood, set())
    preferred_candidates = [a for a in candidates if a["name"] in preferred]
    pool = preferred_candidates or candidates
    return random.choice(pool)


def build_visual_concept(quote_text, themes, mood):
    archetype = select_archetype(themes, mood)
    theme = themes[0] if themes else "soul"
    theme_description = THEME_VISUALS.get(
        theme, "quiet emotional depth and authentic human presence"
    )
    mood_description = MOODS.get(mood, MOODS["introspective"])["visual"]

    return {
        "archetype": archetype["name"],
        "scene": archetype["description"],
        "avoid_scene": archetype["avoid"],
        "subjects": archetype["subjects"],
        "camera": archetype["camera"],
        "composition": archetype["composition"],
        "theme": theme,
        "theme_description": theme_description,
        "mood": mood,
        "mood_description": mood_description,
        "quote_intent": quote_text,
    }


def generate_image_prompt(quote_text, themes, mood):
    concept = build_visual_concept(quote_text, themes, mood)

    # IMPORTANT: do not put the original quote in the image prompt. Even with
    # negative prompting, models sometimes render quoted text as typography.
    # The image should communicate the emotional thesis, not reproduce words.
    prompt = f"""
Create a premium cinematic editorial photograph for an inspirational culture
channel. The image must communicate an emotional idea through visual storytelling,
not through text, symbols, or literal illustration.

VISUAL THESIS:
Theme: {concept["theme"]}.
Emotional meaning: {concept["theme_description"]}.
Mood: {concept["mood_description"]}.
Scene: {concept["scene"]}.

SUBJECT:
{concept["subjects"]}.
Human beings, if present, must be clearly adult, anatomically plausible, naturally
proportioned, non-sexualized, with realistic skin and subtle facial expression.
Emotion must come from posture, distance, gaze, gesture, light, and environment.

CAMERA AND COMPOSITION:
{concept["camera"]}.
{concept["composition"]}.
Create one clear focal point. Use foreground, middle ground and background
when appropriate. Avoid clutter. Use realistic depth and natural perspective.
The frame should feel like a still from a high-end independent film or a premium
editorial magazine, never like a stock photo or motivational poster.

LIGHT AND MATERIALS:
physically believable natural or practical light, nuanced shadows, soft highlight
rolloff, realistic skin and fabric, tactile surfaces, restrained sophisticated
color palette, subtle atmospheric depth, photographic realism, fine detail.
No excessive HDR, no plastic skin, no fantasy glow.

ABSOLUTE TEXT BAN:
No text anywhere in the image. No letters, numbers, words, captions, subtitles,
logos, signatures, watermarks, typography, signs, labels, posters, books,
newspapers, screens, phones, packaging, menus, documents, cards, tickets,
billboards, storefront lettering, road signs, brand marks, UI, or readable symbols.
Avoid any object that normally contains writing. Replace it with a plain,
unmarked object or remove it entirely.

AVOID:
{concept["avoid_scene"]}; cliché inspirational imagery; hearts; angel wings;
halo; giant flowers; fake lens flares; surreal glow; beauty-ad aesthetics;
overly posed models; duplicated people; deformed hands; extra fingers;
extra limbs; malformed faces; waxy skin; oversaturation; heavy blur.

The result must look like a professionally art-directed photograph with a single
strong idea and zero graphic design elements.
""".strip()

    return re.sub(r"\s+", " ", prompt)[:2400], concept


# ============================================================
# IMAGE GENERATION
# ============================================================


def is_valid_image(data):
    if (not isinstance(data, bytes) or len(data) < MIN_IMAGE_BYTES or len(data) > MAX_IMAGE_BYTES):
        return False
    return (
        data[:3] == b"\xff\xd8\xff"
        or data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:4] == b"RIFF"
    )


def _download_image(url, headers=None):
    try:
        r = requests.get(url, headers=headers or DEFAULT_HEADERS, timeout=IMAGE_TIMEOUT)
        if r.status_code == 200 and is_valid_image(r.content):
            return r.content
        logger.warning("Image endpoint returned HTTP %s", r.status_code)
    except Exception as e:
        logger.warning("Image request error: %s", e)
    return None


def generate_image_pollinations_legacy(prompt, width=1024, height=1024):
    """
    Free compatibility route. Current Pollinations generation docs require
    authentication, so this route is best-effort. It remains the default
    because the user requested a no-cost pipeline.
    """
    seed = random.randint(1, 2_000_000_000)
    negative = (
        "text, words, letters, numbers, typography, watermark, logo, signature, "
        "caption, poster, quote card, sign, label, book, newspaper, screen, "
        "phone screen, packaging, billboard, storefront, menu, document, "
        "deformed hands, extra fingers, extra limbs, bad anatomy, plastic skin, "
        "stock photo, fashion advertisement, motivational poster, oversaturated"
    )
    url = (
        "https://image.pollinations.ai/prompt/"
        + quote(prompt, safe="")
        + f"?width={width}&height={height}&model=flux"
        + f"&seed={seed}&nologo=true&enhance=false&safe=true"
        + "&negative_prompt=" + quote(negative, safe="")
    )
    data = _download_image(url)
    if data:
        return data, "Pollinations-legacy"
    return None, ""


def generate_image_pollinations_api(prompt, width=1024, height=1024):
    if not POLLINATIONS_API_KEY:
        return None, ""

    seed = random.randint(1, 2_000_000_000)
    negative = (
        "text, words, letters, numbers, typography, watermark, logo, signature, "
        "caption, poster, quote card, signs, labels, books, screens, packaging, "
        "billboards, storefronts, menus, documents, bad anatomy, plastic skin, "
        "stock photo, motivational poster"
    )
    url = (
        "https://gen.pollinations.ai/image/"
        + quote(prompt, safe="")
        + f"?model=flux&width={width}&height={height}"
        + f"&seed={seed}&safe=true&enhance=false"
        + "&negative_prompt=" + quote(negative, safe="")
    )
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {POLLINATIONS_API_KEY}"}
    data = _download_image(url, headers)
    if data:
        return data, "Pollinations"
    return None, ""


def image_has_obvious_text(data):
    """
    Optional OCR gate. If pytesseract + tesseract are installed, reject images
    containing obvious text and let the generator retry. If OCR is unavailable,
    do not fail generation.
    """
    try:
        import pytesseract
        from PIL import Image
        from io import BytesIO

        img = Image.open(BytesIO(data)).convert("RGB")
        info = pytesseract.image_to_data(
            img,
            config="--psm 11",
            output_type=pytesseract.Output.DICT,
        )
        hits = 0
        for text, conf in zip(info.get("text", []), info.get("conf", [])):
            token = (text or "").strip()
            try:
                confidence = float(conf)
            except Exception:
                confidence = 0
            letters = re.sub(r"[^A-Za-zА-Яа-яЁё]", "", token)
            if len(letters) >= 4 and confidence >= 75:
                hits += 1
        return hits >= 1
    except Exception:
        return False


def generate_image(prompt):
    # Generate several candidates and reject obvious text artifacts. The first
    # candidate is not automatically accepted anymore.
    providers = [generate_image_pollinations_legacy]
    if POLLINATIONS_API_KEY:
        providers.append(generate_image_pollinations_api)

    for provider in providers:
        for attempt in range(3):
            try:
                image, name = provider(prompt)
                if image and is_valid_image(image):
                    if image_has_obvious_text(image):
                        logger.warning(
                            "%s candidate %s rejected: obvious text detected",
                            name, attempt + 1
                        )
                        continue
                    return image, name
            except Exception as e:
                logger.warning(
                    "%s attempt %s failed: %s",
                    provider.__name__, attempt + 1, e
                )
            if attempt < 2:
                time.sleep(3)

    return None, ""


# ============================================================
# TRANSLATION
# ============================================================

_translation_cache = {}


def translate_google_web(text, dest_lang="ru"):
    url = "https://translate.googleapis.com/translate_a/single"
    params = {"client": "gtx", "sl": "auto", "tl": dest_lang, "dt": "t", "q": text}
    r = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and data and isinstance(data[0], list):
        parts = [p[0] for p in data[0] if isinstance(p, list) and p and p[0]]
        return clean_text(" ".join(parts))
    return ""


def translate_mymemory(text, dest_lang="ru"):
    url = "https://api.mymemory.translated.net/get"
    params = {"q": text[:500], "langpair": f"en|{dest_lang}"}
    r = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    result = clean_text(data.get("responseData", {}).get("translatedText", ""))
    if "MYMEMORY WARNING" in result.upper():
        return ""
    return result


def translate_text(text, dest_lang="ru"):
    if not text:
        return ""
    if re.search(r"[а-яА-ЯёЁ]", text):
        return text

    key = hashlib.md5(f"{text}|{dest_lang}".encode()).hexdigest()
    if key in _translation_cache:
        return _translation_cache[key]

    for fn in (translate_google_web, translate_mymemory):
        try:
            result = fn(text, dest_lang)
            if result and result.lower() != text.lower():
                _translation_cache[key] = result
                return result
        except Exception as e:
            logger.warning("Translation error %s: %s", fn.__name__, e)

    return text

# ============================================================
# HASHTAGS / POST
# ============================================================


def make_hashtag(text):
    tag = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ_]+", "", text.replace(" ", ""))
    if not tag:
        return None
    if tag[0].isdigit():
        tag = "author_" + tag
    return tag[:25].lower()


def generate_hashtags(quote_text, author):
    topics = score_topics(quote_text)
    mood = analyze_mood(quote_text)

    tags = ["женскиемысли", "цитатыдлядуши"]
    mood_tags = {
        "tender": "нежность",
        "empowered": "сила",
        "dreamy": "мечты",
        "romantic": "любовь",
        "introspective": "душа",
        "healing": "исцеление",
        "peaceful": "гармония",
        "confident": "уверенность",
    }
    topic_tags = {
        "self_love": "самоценность",
        "femininity": "женственность",
        "love": "любовь",
        "healing": "исцеление",
        "strength": "сила",
        "growth": "развитие",
        "dreams": "вдохновение",
        "beauty": "красота",
        "relationships": "отношения",
        "freedom": "свобода",
    }

    if mood in mood_tags:
        tags.append(mood_tags[mood])
    for t in topics[:2]:
        if t in topic_tags:
            tags.append(topic_tags[t])

    author_tag = make_hashtag(author)
    if author_tag:
        tags.append(author_tag)

    result = []
    for t in tags:
        if t and t not in result:
            result.append(t)
    return result[:5]


def fetch_post_content():
    quote = choose_unique_quote()
    if not quote:
        return None

    quote_text = quote["quote_text"]
    author = quote["author"]
    topics = json.loads(quote.get("topic_json") or "[]")
    mood = quote.get("mood") or analyze_mood(quote_text)

    translated_quote = translate_text(quote_text, "ru")
    translated_author = translate_text(author, "ru")
    prompt, concept = generate_image_prompt(quote_text, topics, mood)

    return {
        "quote": quote,
        "translated_quote": translated_quote,
        "translated_author": translated_author,
        "topics": topics,
        "mood": mood,
        "visual_concept": concept,
        "image_prompt": prompt,
        "hashtags": generate_hashtags(quote_text, translated_author),
    }


def build_post_text(content, limit=1024):
    q = html.escape(content["translated_quote"])
    a = html.escape(content["translated_author"])
    hashtags = "  ".join(f"#{x}" for x in content["hashtags"][:4])
    channel_username = CHANNEL_ID.lstrip("@")
    link = f'<a href="https://t.me/{channel_username}">Красивые Цитаты</a>'

    text = f"✨ «{q}» (c) {a}\n\n{hashtags}\n\n{link}"
    if len(text) <= limit:
        return text

    # Caption-safe fallback without silently cutting in the middle too much.
    short = content["translated_quote"][:180].rsplit(" ", 1)[0]
    return (
        f"✨ «{html.escape(short)}…»\n\n"
        f"{hashtags}\n\n{link}"
    )[:limit]

# ============================================================
# POSTING
# ============================================================


async def create_and_send_post(context=None):
    if POST_LOCK.locked():
        logger.warning("Post generation already running.")
        return False

    async with POST_LOCK:
        try:
            content = await asyncio.to_thread(fetch_post_content)
            if not content:
                logger.error("No unused quote available. History was NOT reset.")
                return False

            logger.info("Quote: %s — %s", content["quote"]["quote_text"], content["quote"]["author"])
            logger.info("Visual concept: %s", content["visual_concept"])
            logger.info("Prompt: %s", content["image_prompt"])

            image_bytes, provider = await asyncio.to_thread(
                generate_image, content["image_prompt"]
            )

            bot = context.bot if context and getattr(context, "bot", None) else Bot(token=BOT_TOKEN)

            if image_bytes:
                caption = build_post_text(content, limit=1024)
                await bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=image_bytes,
                    caption=caption,
                    parse_mode="HTML",
                )
            else:
                logger.warning("No free image provider available; text-only fallback.")
                await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=build_post_text(content, limit=4096),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )

            try:
                mark_published(
                    content,
                    image_bytes=image_bytes,
                    provider=provider,
                    archetype=content["visual_concept"]["archetype"],
                )
                logger.info("Publication recorded in SQLite successfully.")
            except Exception:
                logger.exception("Telegram post succeeded, but SQLite recording failed.")

            config.last_post_time = datetime.now()
            config.save_config()

            if ADMIN_CHAT_ID > 0:
                try:
                    await bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=(
                            "✅ Пост опубликован.\n\n"
                            f"Цитата: {content['quote']['quote_text']}\n"
                            f"Автор: {content['quote']['author']}\n"
                            f"Тема: {', '.join(content['topics'])}\n"
                            f"Настроение: {content['mood']}\n"
                            f"Изображение: {provider or 'не доступно'}\n"
                            f"Сцена: {content['visual_concept']['archetype']}\n\n"
                            f"Следующий пост через {config.interval_hours} ч."
                        ),
                    )
                except Exception:
                    pass

            return True

        except Exception as e:
            logger.exception("Post creation error")
            if ADMIN_CHAT_ID > 0:
                try:
                    bot = context.bot if context and getattr(context, "bot", None) else Bot(token=BOT_TOKEN)
                    await bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"❌ Ошибка создания поста:\n{e}",
                    )
                except Exception:
                    pass
            return False

# ============================================================
# REPAIR / MAINTENANCE
# ============================================================


def mark_quote_as_published_by_text(quote_text, author):
    """Idempotently mark an already-published Telegram post in SQLite."""
    h = quote_hash(quote_text, author)

    with get_db() as conn:
        q = conn.execute(
            "SELECT id, quote_text, author FROM quotes WHERE quote_hash=?",
            (h,),
        ).fetchone()

        if not q:
            raise RuntimeError("Quote is not present in quotes table.")

        conn.execute("""
            INSERT OR IGNORE INTO published_quotes
                (quote_id, quote_hash, quote_text, author)
            VALUES (?, ?, ?, ?)
        """, (q["id"], h, q["quote_text"], q["author"]))

        conn.execute("""
            UPDATE quotes
            SET used_count = CASE WHEN used_count < 1 THEN 1 ELSE used_count END,
                last_used_at = COALESCE(last_used_at, ?)
            WHERE quote_hash=?
        """, (datetime.now(timezone.utc).isoformat(), h))

        conn.commit()

    return h

# ============================================================
# SCHEDULER
# ============================================================


async def scheduled_post_job(context):
    await create_and_send_post(context)


def configure_job_queue(application):
    queue = application.job_queue
    if not queue:
        logger.warning("JobQueue unavailable. Install python-telegram-bot[job-queue].")
        return

    for job in queue.get_jobs_by_name("auto_post"):
        job.schedule_removal()

    if not config.auto_posting:
        return

    if config.last_post_time:
        next_time = config.last_post_time + timedelta(hours=config.interval_hours)
        delay = max(60, (next_time - datetime.now()).total_seconds())
    else:
        delay = 20

    queue.run_repeating(
        scheduled_post_job,
        interval=timedelta(hours=config.interval_hours),
        first=delay,
        name="auto_post",
    )


async def post_init(application):
    await asyncio.to_thread(seed_database)
    configure_job_queue(application)

# ============================================================
# ADMIN UI
# ============================================================


def admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🚀 Отправить пост", "📊 Статистика"],
            ["⚙️ Автопостинг", "⏰ Интервал"],
            ["🧪 Тест картинки", "🔎 Тест уникальности"],
        ],
        resize_keyboard=True,
    )


def status_text():
    quotes, published = get_stats()
    next_post = "неизвестно"
    if config.last_post_time:
        next_post = (
            config.last_post_time + timedelta(hours=config.interval_hours)
        ).strftime("%d.%m.%Y %H:%M")

    return (
        "🤖 BeauQuot 2.2\n\n"
        f"Кандидатов в БД: {quotes}\n"
        f"Опубликовано: {published}\n"
        f"Автопостинг: {'✅' if config.auto_posting else '❌'}\n"
        f"Интервал: {config.interval_hours} ч.\n"
        f"Последний пост: "
        f"{config.last_post_time.strftime('%d.%m.%Y %H:%M') if config.last_post_time else 'нет'}\n"
        f"Следующий: {next_post}\n\n"
        "Уникальность: exact + normalized + optional semantic\n"
        "Изображения: бесплатные Pollinations routes"
    )


def spawn_job(context, coro):
    if hasattr(context.application, "create_task"):
        context.application.create_task(coro)
    else:
        asyncio.create_task(coro)


async def start_command(update: Update, context):
    global ADMIN_CHAT_ID
    if ADMIN_CHAT_ID <= 0:
        ADMIN_CHAT_ID = update.effective_user.id
        save_admin_id(ADMIN_CHAT_ID)

    if not is_admin(update):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    await update.message.reply_text(
        status_text(),
        reply_markup=admin_keyboard(),
    )


async def send_post_now(update, context):
    await update.message.reply_text(
        "⏳ Создаю пост. Картинка может генерироваться до нескольких минут."
    )

    async def job():
        ok = await create_and_send_post(context)
        if not ok:
            await update.effective_message.reply_text(
                "❌ Не удалось создать/опубликовать пост."
            )

    spawn_job(context, job())


async def show_statistics(update, context):
    await update.message.reply_text(status_text(), reply_markup=admin_keyboard())


async def toggle_autoposting(update, context):
    config.auto_posting = not config.auto_posting
    config.save_config()
    configure_job_queue(context.application)
    await update.message.reply_text(status_text(), reply_markup=admin_keyboard())


async def show_interval_menu(update, context):
    keyboard = [
        [
            InlineKeyboardButton("1 ч", callback_data="interval:1"),
            InlineKeyboardButton("3 ч", callback_data="interval:3"),
            InlineKeyboardButton("6 ч", callback_data="interval:6"),
        ],
        [
            InlineKeyboardButton("12 ч", callback_data="interval:12"),
            InlineKeyboardButton("24 ч", callback_data="interval:24"),
        ],
    ]
    await update.message.reply_text(
        "Выберите интервал:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def test_image(update, context):
    await update.message.reply_text("⏳ Тестирую бесплатную генерацию...")

    def make_test():
        prompt = (
            "editorial fine-art photograph of an adult woman sitting beside a large "
            "window at dawn, quiet self-acceptance, natural skin texture, realistic "
            "materials, cinematic depth, restrained colors, no text, no logo"
        )
        return generate_image(prompt)

    async def job():
        image, provider = await asyncio.to_thread(make_test)
        if image:
            await update.effective_message.reply_photo(
                photo=image,
                caption=f"Готово: {provider}",
            )
        else:
            await update.effective_message.reply_text(
                "❌ Бесплатный image endpoint сейчас недоступен."
            )

    spawn_job(context, job())


async def test_uniqueness(update, context):
    q = choose_unique_quote()
    if not q:
        await update.message.reply_text(
            "❌ Новых неповторяющихся цитат не найдено. История публикаций НЕ сброшена."
        )
        return

    await update.message.reply_text(
        "🔎 Кандидат:\n\n"
        f"«{q['quote_text']}»\n\n"
        f"— {q['author']}\n\n"
        f"Score: {q['quality_score']}\n"
        f"Topics: {q['topic_json']}\n"
        f"Mood: {q['mood']}"
    )


async def handle_admin_message(update, context):
    if not is_admin(update):
        return

    text = update.message.text
    if text == "🚀 Отправить пост":
        await send_post_now(update, context)
    elif text == "📊 Статистика":
        await show_statistics(update, context)
    elif text == "⚙️ Автопостинг":
        await toggle_autoposting(update, context)
    elif text == "⏰ Интервал":
        await show_interval_menu(update, context)
    elif text == "🧪 Тест картинки":
        await test_image(update, context)
    elif text == "🔎 Тест уникальности":
        await test_uniqueness(update, context)
    else:
        await update.message.reply_text(
            status_text(),
            reply_markup=admin_keyboard(),
        )


async def handle_callback(update, context):
    query = update.callback_query
    if not is_admin(update):
        await query.answer("Нет доступа")
        return

    if query.data.startswith("interval:"):
        try:
            hours = int(query.data.split(":")[1])
        except Exception:
            hours = 6

        if 1 <= hours <= 24:
            config.interval_hours = hours
            config.save_config()
            configure_job_queue(context.application)
            await query.answer(f"Интервал: {hours} ч.")
            await query.edit_message_text("✅ Интервал обновлён.")

# ============================================================
# MAIN
# ============================================================


def main():
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN is missing.")
        return

    init_db()
    load_admin_id()
    config.load_config()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_message)
    )

    logger.info("BeauQuot 2.2 started")
    logger.info("Quote source: local SQLite corpus seeded from dwyl/quotes")
    logger.info("No paid LLM/image API is required.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "repair-published":
        if len(sys.argv) != 4:
            print('Usage: python main.py repair-published "QUOTE TEXT" "AUTHOR"')
            raise SystemExit(2)
        quote_text, author = sys.argv[2], sys.argv[3]
        repaired_hash = mark_quote_as_published_by_text(quote_text, author)
        print(f"Marked as published: {repaired_hash}")
    else:
        main()
