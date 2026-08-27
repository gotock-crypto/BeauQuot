
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
from io import BytesIO
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

# Hugging Face is used for semantic LLM / visual analysis only.
# Image generation is provided by the free AI Horde volunteer network.
HF_TOKEN = os.getenv("HF_TOKEN", os.getenv("HUGGINGFACE_TOKEN", "")).strip()
HF_TOKEN_2 = os.getenv("HF_TOKEN_2", "").strip()
HF_TOKEN_3 = os.getenv("HF_TOKEN_3", "").strip()
HF_TOKEN_ORDER = [x.strip() for x in os.getenv("HF_TOKEN_ORDER", "HF_TOKEN,HF_TOKEN_2,HF_TOKEN_3").split(",") if x.strip()]
# AI Horde image generation is intentionally independent of all HF image settings.
AIHORDE_API_BASE = os.getenv("AIHORDE_API_BASE", "https://aihorde.net/api/v2").strip().rstrip("/")
AIHORDE_API_KEY = os.getenv("AIHORDE_API_KEY", "0000000000").strip() or "0000000000"
AIHORDE_CLIENT_AGENT = os.getenv(
    "AIHORDE_CLIENT_AGENT",
    "BeauQuot:3.1.5-free-image:https://github.com/gotock-crypto/BeauQuot",
).strip()
AIHORDE_IMAGE_MODEL = os.getenv(
    "AIHORDE_IMAGE_MODEL",
    "Flux.1-Schnell fp8 (Compact)",
).strip()
AIHORDE_IMAGE_WIDTH = int(os.getenv("AIHORDE_IMAGE_WIDTH", "1024"))
AIHORDE_IMAGE_HEIGHT = int(os.getenv("AIHORDE_IMAGE_HEIGHT", "1024"))
AIHORDE_IMAGE_STEPS = int(os.getenv("AIHORDE_IMAGE_STEPS", "4"))
AIHORDE_IMAGE_CFG = float(os.getenv("AIHORDE_IMAGE_CFG", "1"))
AIHORDE_IMAGE_SAMPLER = os.getenv("AIHORDE_IMAGE_SAMPLER", "k_euler").strip() or "k_euler"
AIHORDE_IMAGE_TIMEOUT = int(os.getenv("AIHORDE_IMAGE_TIMEOUT", "360"))
AIHORDE_POLL_INTERVAL = float(os.getenv("AIHORDE_POLL_INTERVAL", "5"))

# Hugging Face LLM is used as a semantic art director before realistic image generation.
# It converts each quote into a bespoke visual concept/prompt instead of relying
# on a fixed archetype or a recurring metaphor.
HF_LLM_MODEL = os.getenv(
    "HF_LLM_MODEL",
    "Qwen/Qwen3-8B",
).strip()
# 3.1 shipped with Qwen2.5-7B-Instruct, which may appear in the Hub catalog but
# can be unroutable for a given Inference Provider. Auto-migrate that exact legacy
# default without touching any other user-selected model.
if HF_LLM_MODEL == "Qwen/Qwen2.5-7B-Instruct":
    HF_LLM_MODEL = "Qwen/Qwen3-8B"
# Backward-compatible provider setting. For the chat layer we use the official
# Hugging Face OpenAI-compatible router and can fail over across live providers.
HF_LLM_PROVIDER = os.getenv("HF_LLM_PROVIDER", "nscale").strip() or "nscale"
HF_LLM_PROVIDERS = [
    p.strip() for p in os.getenv("HF_LLM_PROVIDERS", "nscale,featherless-ai").split(",")
    if p.strip()
]
if HF_LLM_PROVIDER and HF_LLM_PROVIDER != "auto":
    HF_LLM_PROVIDERS = [HF_LLM_PROVIDER] + [p for p in HF_LLM_PROVIDERS if p != HF_LLM_PROVIDER]
HF_LLM_MAX_TOKENS = int(os.getenv("HF_LLM_MAX_TOKENS", "1600"))
HF_LLM_TEMPERATURE = float(os.getenv("HF_LLM_TEMPERATURE", "0.45"))
HF_LLM_TIMEOUT = int(os.getenv("HF_LLM_TIMEOUT", "90"))
HF_LLM_DISABLE_THINKING = os.getenv("HF_LLM_DISABLE_THINKING", "1").strip() != "0"
HF_VISION_MODEL = os.getenv(
    "HF_VISION_MODEL",
    "Salesforce/blip-image-captioning-base",
).strip()
VISUAL_SEMANTIC_GATE = os.getenv("VISUAL_SEMANTIC_GATE", "1").strip() != "0"
VISUAL_SEMANTIC_MIN_SCORE = float(os.getenv("VISUAL_SEMANTIC_MIN_SCORE", "0.68"))

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
RECENT_DIVERSITY_WINDOW = int(os.getenv("RECENT_DIVERSITY_WINDOW", "12"))
VISUAL_GENERATION_ATTEMPTS = int(os.getenv("VISUAL_GENERATION_ATTEMPTS", "4"))
VISUAL_RETRY_DIVERSITY = os.getenv("VISUAL_RETRY_DIVERSITY", "1").strip() != "0"
LLM_VISUAL_JUDGE = os.getenv("LLM_VISUAL_JUDGE", "1").strip() != "0"
VISUAL_CONCEPT_CANDIDATES = int(os.getenv("VISUAL_CONCEPT_CANDIDATES", "3"))
VISUAL_CONCEPT_MIN_SCORE = float(os.getenv("VISUAL_CONCEPT_MIN_SCORE", "0.74"))
TEMPORAL_COMPOSITION_ENABLED = os.getenv("TEMPORAL_COMPOSITION_ENABLED", "1").strip() != "0"
TEMPORAL_COMPOSITION_MIN_CLAUSES = int(os.getenv("TEMPORAL_COMPOSITION_MIN_CLAUSES", "2"))
VISUAL_INFERENCE_MIN_SCORE = float(os.getenv("VISUAL_INFERENCE_MIN_SCORE", "0.70"))
VISUAL_CAPTION_DUP_THRESHOLD = float(os.getenv("VISUAL_CAPTION_DUP_THRESHOLD", "0.84"))
# 3.1.3 raises the semantic bar: a beautiful image is not enough if the
# visible mechanism does not explain the quote.
VISUAL_GENERICITY_PENALTY = float(os.getenv("VISUAL_GENERICITY_PENALTY", "0.18"))
ADULT_AUDIENCE_STYLE = os.getenv(
    "ADULT_AUDIENCE_STYLE",
    "sophisticated editorial fine-art, emotionally mature, elegant, realistic, non-glossy",
).strip()

DEFAULT_HEADERS = {
    "User-Agent": "BeauQuot/3.1 (+Telegram quote bot)",
}

NEGATIVE_PROMPT = (
    "text, words, letters, numbers, typography, watermark, logo, signature, "
    "caption, poster, quote card, UI, sign, label, book, newspaper, screen, "
    "phone screen, packaging, billboard, storefront, menu, document, readable text, "
    "deformed hands, extra fingers, extra limbs, bad anatomy, plastic skin, "
    "waxy face, stock photo, fashion advertisement, motivational poster, "
    "oversaturated, excessive HDR, fake glow, surreal artifacts, CGI, cartoon, anime, "
    "vector art, childish illustration, cheesy inspirational imagery"
)
POST_LOCK = asyncio.Lock()

# Runtime quota/auth circuit breaker. A token that returns 402/401 is skipped
# for the remainder of the process lifetime so we do not repeatedly burn
# requests against an exhausted/invalid credential.
_HF_TOKEN_DISABLED = {}
_HF_TOKEN_DISABLED_REASONS = {}

class HFTokenUnavailable(RuntimeError):
    def __init__(self, reason, status_code=None):
        self.reason = reason
        self.status_code = status_code
        super().__init__(reason)

def _hf_token_pool():
    configured = {
        "HF_TOKEN": HF_TOKEN,
        "HF_TOKEN_2": HF_TOKEN_2,
        "HF_TOKEN_3": HF_TOKEN_3,
    }
    tokens = []
    for name in HF_TOKEN_ORDER + [n for n in configured if n not in HF_TOKEN_ORDER]:
        value = configured.get(name, "")
        if value and value not in [t[0] for t in tokens]:
            if value in _HF_TOKEN_DISABLED:
                continue
            tokens.append((value, name))
    return tokens

def _disable_hf_token(token, reason):
    if token:
        _HF_TOKEN_DISABLED[token] = time.time()
        _HF_TOKEN_DISABLED_REASONS[token] = reason
        logger.warning("HF token disabled for this process: reason=%s", reason)

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
        self.interval_hours = 3
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
            self.interval_hours = int(data.get("interval_hours", 3))
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
        # Safe migration for installations created by earlier BeauQuot versions.
        # The new column stores the concrete visual motif used in the illustration,
        # allowing us to avoid repeating the same metaphor (doorway, bridge, path,
        # etc.) even when the high-level archetype is different.
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(visual_history)").fetchall()
        }
        if "visual_motif" not in columns:
            conn.execute("ALTER TABLE visual_history ADD COLUMN visual_motif TEXT DEFAULT ''")
        if "visual_profile" not in columns:
            conn.execute("ALTER TABLE visual_history ADD COLUMN visual_profile TEXT DEFAULT ''")
        if "image_caption" not in columns:
            conn.execute("ALTER TABLE visual_history ADD COLUMN image_caption TEXT DEFAULT ''")
        if "semantic_score" not in columns:
            conn.execute("ALTER TABLE visual_history ADD COLUMN semantic_score REAL DEFAULT 0")
        if "visual_hash" not in columns:
            conn.execute("ALTER TABLE visual_history ADD COLUMN visual_hash TEXT DEFAULT ''")

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


def visual_perceptual_hash(data, size=16):
    """Lightweight dHash-like visual fingerprint using PIL; no new dependency required."""
    if not data:
        return ""
    try:
        from PIL import Image
        img = Image.open(BytesIO(data)).convert("L").resize((size + 1, size))
        pixels = list(img.getdata())
        bits = []
        for y in range(size):
            row = pixels[y * (size + 1):(y + 1) * (size + 1)]
            bits.extend(1 if row[x] > row[x + 1] else 0 for x in range(size))
        value = 0
        for bit in bits:
            value = (value << 1) | bit
        return f"{value:0{(size*size + 3)//4}x}"
    except Exception:
        return ""


def visual_hash_similarity(hash_a, hash_b):
    if not hash_a or not hash_b or len(hash_a) != len(hash_b):
        return 0.0
    try:
        a = int(hash_a, 16)
        b = int(hash_b, 16)
        distance = (a ^ b).bit_count()
        total = len(hash_a) * 4
        return 1.0 - (distance / total)
    except Exception:
        return 0.0

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

        visual_motif = visual_concept.get("visual_motif", "")
        visual_profile = json.dumps({
            "subject_type": visual_concept.get("subject_type", ""),
            "visual_mode": visual_concept.get("visual_mode", ""),
            "narrative_mode": visual_concept.get("narrative_mode", ""),
            "environment": visual_concept.get("environment", ""),
            "composition_type": visual_concept.get("composition_type", ""),
            "medium": visual_concept.get("medium", ""),
            "relationship_type": visual_concept.get("relationship_type", "none"),
            "visual_motif": visual_motif,
        }, ensure_ascii=False)
        image_caption = str(content.get("image_caption") or "")[:1200]
        semantic_score = float(content.get("semantic_score") or 0.0)
        visual_hash = visual_perceptual_hash(image_bytes)
        conn.execute("""
            INSERT INTO visual_history(
                archetype, theme, mood, visual_motif, visual_profile, image_caption, semantic_score, visual_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            archetype or "unknown", theme, mood, visual_motif, visual_profile,
            image_caption, semantic_score, visual_hash,
        ))

        conn.commit()

def get_recent_visuals(limit=RECENT_DIVERSITY_WINDOW):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT archetype, theme, mood, visual_motif, visual_profile, image_caption, semantic_score, visual_hash
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

def extract_visual_intent(quote_text, themes, mood):
    """Convert the quote into a concrete visual story before prompting the model.

    The previous pipeline mostly selected an aesthetic archetype from topic/mood.
    That produced attractive but interchangeable images.  This layer looks for
    the *action/relationship/change* expressed by the quote and turns it into a
    photographic thesis.
    """
    low = normalize_text(quote_text)

    rules = [
        {
            "id": "care_for_others",
            "patterns": [
                "care for others", "care about others", "help others",
                "help someone", "think of others", "serve others",
                "look after others", "support others", "others", "других",
                "другом", "другими", "заботься", "заботиться", "помогать",
                "помочь", "поддержать", "поддерживать", "сочувствие",
                "сострадание",
            ],
            "thesis": "A person deliberately turns attention away from their own worries toward another person's needs.",
            "action": "One adult person offers calm, practical help to another adult person; the gesture is subtle and believable.",
            "archetype": "two_people_connection",
            "subjects": "two adult people in an authentic everyday setting; one is quietly helping or reassuring the other",
            "composition": "the helper and the person receiving help share the frame, with the gesture clearly readable without posing",
            "avoid": "romance, kissing, wedding imagery, staged charity photo, exaggerated emotional display",
        },
        {
            "id": "letting_go",
            "patterns": [
                "let go", "letting go", "move on", "leave behind", "release",
                "перестать", "отпустить", "отпускай", "оставить прошлое",
                "двигаться дальше", "идти дальше", "освободиться",
            ],
            "thesis": "A person releases an old burden and continues into a calmer new chapter.",
            "action": "An adult person walks away from a confined or shadowed space toward an open, calm environment.",
            "archetype": "threshold",
            "subjects": "one adult person in natural, unposed movement",
            "composition": "clear transition from compressed foreground to open background; the direction of movement is obvious",
            "avoid": "fantasy portal, luggage symbolism, dramatic crying, cliché sunrise",
        },
        {
            "id": "growth_change",
            "patterns": [
                "grow", "growth", "become", "becoming", "change", "transform",
                "rebuilt", "rebuild", "new chapter", "evolve", "развиваться",
                "развитие", "становиться", "измениться", "изменение",
                "преобразиться", "новая глава", "вырасти", "рост",
            ],
            "thesis": "A visible transition from an earlier state into a more capable and settled one.",
            "action": "An adult person moves through a real environment that naturally shows a transition from one state to another.",
            "archetype": "threshold",
            "subjects": "one adult person, candid and purposeful",
            "composition": "two distinct visual zones connected by a natural path or doorway, with the person crossing between them",
            "avoid": "before-and-after collage, fantasy transformation, glowing effects, motivational poster",
        },
        {
            "id": "courage",
            "patterns": [
                "courage", "brave", "fearless", "bold", "dare", "face your fears",
                "смелость", "смелым", "храбрость", "бесстрашие", "не бояться",
                "страх", "мужество",
            ],
            "thesis": "Quiet courage is shown as a person choosing to move forward despite uncertainty.",
            "action": "An adult person takes a deliberate step into an uncertain but realistic environment.",
            "archetype": "open_road",
            "subjects": "one adult person walking or standing at the beginning of a real path",
            "composition": "the person is small enough to show the scale of what lies ahead, with a clear directional path",
            "avoid": "superhero pose, mountain-top triumph, arms raised, epic fantasy landscape",
        },
        {
            "id": "inner_peace",
            "patterns": [
                "inner peace", "peace of mind", "calm", "serene", "tranquil",
                "quiet mind", "stillness", "спокойствие", "внутренний покой",
                "душевный покой", "тишина", "умиротворение", "гармония",
            ],
            "thesis": "The outside world becomes visually spacious and quiet as the person settles internally.",
            "action": "An adult person pauses alone in a simple, spacious real environment with no performance or spectacle.",
            "archetype": "water_reflection",
            "subjects": "one adult person, naturally seated or standing, absorbed in a quiet moment",
            "composition": "large calm negative space around the person; reflection or horizon may reinforce stillness",
            "avoid": "yoga cliché, meditation pose, spa advertising, fantasy glow, dramatic sunset",
        },
        {
            "id": "self_acceptance",
            "patterns": [
                "love yourself", "accept yourself", "acceptance", "be yourself",
                "believe in yourself", "know your worth", "self worth",
                "люби себя", "прими себя", "принять себя", "быть собой",
                "ценить себя", "самоценность", "достоинство", "уверенность в себе",
            ],
            "thesis": "A person is comfortable in their own presence without needing external approval.",
            "action": "An adult person is alone and at ease in an ordinary private environment, behaving naturally rather than posing.",
            "archetype": "soft_domestic_moment",
            "subjects": "one adult woman in an ordinary elegant home, candid and completely unposed",
            "composition": "observational framing that makes the person feel grounded and self-contained, not like a portrait session",
            "avoid": "mirror selfie, beauty campaign, glamour, cosmetics, exaggerated smile",
        },
        {
            "id": "love_connection",
            "patterns": [
                "love", "beloved", "cherish", "affection", "embrace",
                "любовь", "любить", "любимый", "нежность", "близость",
                "отношения", "забота друг о друге",
            ],
            "thesis": "Emotional connection is shown through a small, believable act of closeness.",
            "action": "Two adults share a quiet everyday moment where attention and body language show mutual care.",
            "archetype": "two_people_connection",
            "subjects": "two adult people with natural body language and subtle emotional connection",
            "composition": "medium observational frame, physical distance close enough to read the relationship but not staged",
            "avoid": "kissing, wedding, roses, heart symbols, melodrama, commercial romance",
        },
        {
            "id": "freedom",
            "patterns": [
                "freedom", "free", "independent", "no longer trapped", "open",
                "свобода", "свободен", "независимость", "независимой",
                "не быть в плену", "открытое пространство",
            ],
            "thesis": "Freedom is experienced as physical and psychological space without confinement.",
            "action": "An adult person moves freely through a wide real landscape with no barriers or crowd around them.",
            "archetype": "solitary_landscape",
            "subjects": "one adult person moving freely, small within a broad natural environment",
            "composition": "wide frame dominated by open space and a visible direction of movement",
            "avoid": "airplane advertisement, running with arms raised, fantasy sky, travel brochure",
        },
        {
            "id": "choice_direction",
            "patterns": [
                "choose", "choice", "decision", "path", "direction", "step forward",
                "выбор", "выбирать", "решение", "решить", "путь", "направление",
                "сделать шаг", "шаг вперед",
            ],
            "thesis": "A meaningful choice is represented by a person deciding where to go next.",
            "action": "An adult person pauses at a genuine fork, doorway, or crossing and clearly chooses one direction.",
            "archetype": "open_road",
            "subjects": "one adult person seen from behind or three-quarter view, naturally considering the route",
            "composition": "two possible directions are visible but one is visually stronger because the person has begun moving toward it",
            "avoid": "literal signposts, road text, crossroads clichés, fortune-telling imagery",
        },
        {
            "id": "action_over_intention",
            "patterns": [
                "intention", "intentions", "action", "actions", "without action",
                "take action", "do something", "change your life", "change your life",
                "намерение", "намерения", "действие", "действия", "без действия",
                "действовать", "сделать", "поступок", "изменить свою жизнь",
                "ничего не изменить", "бесполезно", "только намерением",
            ],
            "thesis": "A desired change becomes real only when an idea is turned into a small, tangible act.",
            "action": "The protagonist is in the middle of doing the first concrete thing that makes the desired future possible.",
            "archetype": "nature_detail",
            "subjects": "one or two adult figures engaged in a simple purposeful act; the act itself is the visual focal point",
            "composition": "show the unfinished state and the first completed action in one poetic frame; the viewer should understand what is being done",
            "avoid": "doorway, generic walking toward light, person merely looking at a horizon, motivational poster, checklist, clock, literal words",
        },
        {
            "id": "resilience",
            "patterns": [
                "stronger", "resilience", "rebuild", "rise again", "overcome",
                "сильнее", "стойкость", "восстановиться", "восстановление",
                "преодолеть", "преодоление", "подняться", "выстоять",
            ],
            "thesis": "Strength is visible in calm recovery rather than aggression or victory.",
            "action": "An adult person has returned to an ordinary routine after difficulty and moves with quiet purpose.",
            "archetype": "urban_dawn",
            "subjects": "one adult person walking through a real city or neighborhood after rain, calm and purposeful",
            "composition": "documentary-style frame with the person moving from shadow into clearer light without theatricality",
            "avoid": "victory pose, clenched fists, superhero imagery, disaster scenes",
        },
    ]

    matched = None
    best_score = 0
    for rule in rules:
        score = 0
        for pattern in rule["patterns"]:
            if pattern in low:
                score += 2 if " " in pattern else 1
        if score > best_score:
            best_score = score
            matched = rule

    if matched:
        return matched

    # Theme/mood fallback still uses the existing curated archetype system,
    # but the quote itself remains part of the visual thesis.
    archetype = select_archetype(themes, mood)
    theme = themes[0] if themes else "soul"
    theme_description = THEME_VISUALS.get(
        theme, "quiet emotional depth and authentic human presence"
    )
    return {
        "id": "theme_fallback",
        "thesis": theme_description,
        "action": "Show the emotional idea through a believable everyday human situation or environment.",
        "archetype": archetype["name"],
        "subjects": archetype["subjects"],
        "composition": archetype["composition"],
        "avoid": archetype["avoid"],
    }



# ============================================================
# ABSTRACT STORYBOOK VISUAL STYLE
# ============================================================

ABSTRACT_VISUAL_STYLE = {
    "medium": (
        "delicate hand-painted illustration, refined digital watercolor and gouache, "
        "soft brushwork, subtle paper texture, elegant painterly edges, illustrated "
        "rather than photographic"
    ),
    "mood": (
        "tender, dreamy, hopeful, intimate, quietly magical, emotionally warm, "
        "calm and sophisticated"
    ),
    "palette": (
        "soft pastel palette: dusty blue, powder blue, warm ivory, blush pink, "
        "peach, muted lavender, sage and a touch of warm gold; harmonious, airy, "
        "low-saturation colors"
    ),
    "light": (
        "diffused dawn or late-afternoon light, soft luminous atmosphere, gentle "
        "backlight, delicate glow through haze, no harsh studio lighting"
    ),
    "composition": (
        "poetic vertical storybook composition, clear foreground/midground/background, "
        "one readable narrative action, elegant negative space, cinematic depth, "
        "balanced asymmetry, visually calm"
    ),
}

VISUAL_METAPHORS = {
    "care_for_others": (
        "connection and human warmth: two figures form a gentle visual relationship, "
        "with one helping, guiding, comforting or reaching toward the other"
    ),
    "letting_go": (
        "release and transition: something that once confined the protagonist opens "
        "into a spacious landscape, with a visible movement from heaviness toward freedom"
    ),
    "growth_change": (
        "organic growth: a small living element becomes part of a larger unfolding "
        "world, suggesting change through time rather than a literal transformation"
    ),
    "courage": (
        "a delicate crossing over uncertainty: a person takes a meaningful step across "
        "a narrow bridge, ridge, stream or other graceful passage"
    ),
    "inner_peace": (
        "stillness and spaciousness: a quiet figure rests beside water or beneath open "
        "sky while the surrounding world becomes soft, balanced and almost weightless"
    ),
    "self_worth": (
        "inner light and self-acceptance: a person gently embraces their own presence, "
        "surrounded by a calm natural environment that feels protective rather than grand"
    ),
    "freedom": (
        "release into open air: a figure moves through a vast landscape with fabric, "
        "birds, wind or clouds suggesting freedom without literal symbolism"
    ),
    "dreams_future": (
        "a dreamed future made visible: a small human figure looks toward a luminous "
        "distant landscape where a winding path, horizon or imagined destination unfolds"
    ),
    "choice": (
        "a meaningful choice: two possible paths or spaces diverge naturally, while the "
        "protagonist has already begun moving toward one of them"
    ),
    "resilience": (
        "quiet recovery: after a storm or difficult passage, a small human figure "
        "returns to a gentle everyday world where light and life are beginning again"
    ),
    "love": (
        "emotional closeness: two figures are connected through a simple shared gesture, "
        "distance, touch or mirrored movement rather than romance clichés"
    ),
    "hope": (
        "a small source of light in a wide quiet world, with the protagonist moving "
        "toward it or protecting it, suggesting hope without literal stars or halos"
    ),
}

# ============================================================
# NARRATIVE VISUAL MOTIF DIVERSIFICATION
# ============================================================

# The style stays recognizable across the channel, but the *story device* changes.
# This prevents the generator from repeatedly falling back to "woman + doorway +
# warm light". Each motif is a concrete visual metaphor with an observable action.
VISUAL_MOTIF_VARIANTS = {
    "action_over_intention": [
        {
            "id": "first_stone",
            "scene": "A quiet hillside garden under construction: the protagonist kneels and places the first smooth stone into the foundation of a small path or wall, while the unfinished structure continues into the distance.",
            "action": "The person is physically placing the first piece of something that did not exist before.",
            "metaphor": "turning intention into reality by beginning with one tangible act",
            "avoid": "doorways, horizons-only compositions, generic walking, checklists, clocks, written plans",
        },
        {
            "id": "planting_seed",
            "scene": "A small hand-painted garden at early spring: the protagonist carefully plants a seedling in dark soil while rows around it remain unfinished, with a gentle suggestion of the future garden beyond.",
            "action": "The person is planting and tending the first living thing in an unfinished garden.",
            "metaphor": "a future is created by a small act of care repeated in the present",
            "avoid": "giant flowers, gardening advertisement, generic woman standing, doorway",
        },
        {
            "id": "weaving_first_thread",
            "scene": "A dreamy studio-like landscape where a long unfinished tapestry stretches across the scene; the protagonist is weaving one luminous thread into it while the rest remains loose and incomplete.",
            "action": "The person is actively weaving one new thread into an unfinished whole.",
            "metaphor": "action gradually gives form to what was previously only an idea",
            "avoid": "literal words, books, screens, sewing commercial, generic portrait",
        },
        {
            "id": "building_bridge",
            "scene": "A narrow stream between two soft green banks; the protagonist places the final plank of a small footbridge while several earlier planks are already in place and the far bank is visible.",
            "action": "The person is completing a real step in building a crossing.",
            "metaphor": "progress is made through concrete steps rather than intention alone",
            "avoid": "epic suspension bridge, mountain hero shot, doorway, sunrise cliché",
        },
        {
            "id": "first_brushstroke",
            "scene": "A quiet atelier-like room opening onto a pale landscape; a large blank canvas stands nearby while the protagonist makes the first broad brushstroke, with unfinished paint and soft natural light around it.",
            "action": "The person has stopped planning and is physically making the first mark.",
            "metaphor": "creation begins when thought becomes a visible action",
            "avoid": "readable painting, text on canvas, artist portrait, commercial studio photo",
        },
    ],
    "letting_go": [
        {
            "id": "birds_release",
            "scene": "A quiet meadow beside a fading evening sky; an open simple cage rests on the ground while a few birds have already flown toward a wide calm landscape, and the protagonist gently lowers the empty cage.",
            "action": "The protagonist releases what was confined and then lets it go.",
            "metaphor": "letting go creates space for movement",
            "avoid": "doorway, generic walking into sunlight, giant birds, melodrama",
        },
        {
            "id": "untied_ribbon",
            "scene": "A long pale ribbon once tied around a weathered tree has just been loosened by the protagonist; the free end moves softly in the wind across an open field.",
            "action": "The person physically unties a restraint and releases it.",
            "metaphor": "release as a quiet physical unbinding",
            "avoid": "literal chains, dramatic prison imagery, doorway, generic sunrise",
        },
        {
            "id": "boat_leaves_shore",
            "scene": "A small hand-painted boat drifts gently away from a quiet shore at dawn while the protagonist remains on the bank after giving it a final push.",
            "action": "The protagonist deliberately lets the boat move away.",
            "metaphor": "accepting distance and allowing the past to continue without you",
            "avoid": "romantic sailing poster, storm, dramatic sunset, doorway",
        },
    ],
    "growth_change": [
        {
            "id": "sprout_sequence",
            "scene": "A poetic garden where one small plant is visibly at the center of a gradual sequence from seed to young stem to flowering form, with the protagonist watering the smallest stage.",
            "action": "The protagonist tends the beginning of a change that will unfold over time.",
            "metaphor": "growth is gradual, living and earned through attention",
            "avoid": "giant flower, time-lapse collage, motivational poster",
        },
        {
            "id": "mended_ceramic",
            "scene": "A delicate ceramic bowl repaired with subtle warm-gold seams rests in the protagonist's hands beside a few broken fragments that have been transformed into a small vase of flowers.",
            "action": "The person carefully turns something broken into something useful and beautiful.",
            "metaphor": "change can preserve the past while giving it a new form",
            "avoid": "literal before-after collage, luxury product advertisement",
        },
        {
            "id": "unfolding_fabric",
            "scene": "A long folded piece of pale fabric unfolds across a meadow as the protagonist gently opens it, revealing more color and pattern with each section.",
            "action": "The protagonist actively unfolds a new section of an unfinished form.",
            "metaphor": "a new chapter appears through gradual movement",
            "avoid": "fashion shoot, runway, doorway, giant flag",
        },
    ],
    "courage": [
        {
            "id": "stepping_stones",
            "scene": "A shallow stream in a misty pastel valley; the protagonist has already stepped onto one of a few delicate stones leading toward the opposite bank.",
            "action": "The person commits to the next step despite not seeing the whole route.",
            "metaphor": "courage is a sequence of small decisions across uncertainty",
            "avoid": "tightrope cliché, superhero pose, mountain summit",
        },
        {
            "id": "bridge_between_cliffs",
            "scene": "A graceful narrow footbridge connects two low cliffs above soft clouds; the protagonist is halfway across, balanced and calm rather than triumphant.",
            "action": "The person continues across an uncertain crossing.",
            "metaphor": "courage as steady movement through vulnerability",
            "avoid": "epic fantasy bridge, arms raised, victory pose",
        },
        {
            "id": "entering_the_water",
            "scene": "At a quiet lake in pale morning light, the protagonist takes the first few steps into clear shallow water while the shoreline remains behind.",
            "action": "The person deliberately enters an unfamiliar element.",
            "metaphor": "courage as willingness to begin before certainty arrives",
            "avoid": "swimwear advertising, dramatic storm, doorway",
        },
    ],
    "inner_peace": [
        {
            "id": "floating_leaves",
            "scene": "A calm lake with a few floating leaves forming a subtle circular pattern around a seated figure on a low stone at the water's edge.",
            "action": "The protagonist remains still while tiny natural movements continue around them.",
            "metaphor": "inner peace is not stopping the world, but becoming still within it",
            "avoid": "yoga advertising, lotus pose, fantasy glow",
        },
        {
            "id": "quiet_window_light",
            "scene": "A quiet room with sheer curtains moving in a soft breeze, a cup of tea on an unmarked table, and the protagonist resting nearby while pale garden light enters.",
            "action": "The person pauses without performing or seeking anything.",
            "metaphor": "peace as a small ordinary moment fully inhabited",
            "avoid": "doorway, spa advertisement, readable books",
        },
        {
            "id": "water_reflection",
            "scene": "A still lake at dusk reflects a muted pastel sky and a small solitary figure sitting quietly at the shore, with almost no visual clutter.",
            "action": "The protagonist simply remains present in a quiet landscape.",
            "metaphor": "inner calm mirrored by the outer world",
            "avoid": "generic meditation poster, dramatic sunset",
        },
    ],
    "dreams_future": [
        {
            "id": "winding_luminous_path",
            "scene": "A tiny figure stands on a high meadow above a vast pastel valley where a winding luminous path crosses fields and disappears toward distant mountains.",
            "action": "The protagonist chooses to begin along the visible path toward a destination not yet reached.",
            "metaphor": "a dream becomes a direction that can be followed",
            "avoid": "doorway, generic road-to-sunrise, motivational poster",
        },
        {
            "id": "island_ahead",
            "scene": "A calm sea of clouds surrounds a small floating island with a flowering tree in the far distance; the protagonist stands on a quiet ridge where a delicate bridge of mist begins.",
            "action": "The protagonist approaches the first part of an unusual but graceful route toward a distant possibility.",
            "metaphor": "a dreamed future exists first as something imagined, then as something approached",
            "avoid": "fantasy game art, excessive magic, generic sunrise",
        },
        {
            "id": "constellation_garden",
            "scene": "A twilight garden where tiny points of warm light rise from newly planted flowers and form a subtle constellation above the protagonist.",
            "action": "The protagonist tends the garden while its future pattern begins to appear.",
            "metaphor": "dreams become visible through patient creation",
            "avoid": "literal astrology, horoscope symbols, star charts",
        },
    ],
    "choice_direction": [
        {
            "id": "branching_river",
            "scene": "A gentle river divides into two clear channels through a pastel meadow; the protagonist has stepped toward one branch while the other continues quietly in another direction.",
            "action": "The person begins moving along one of two genuine routes.",
            "metaphor": "choice is made through movement, not contemplation alone",
            "avoid": "literal road signs, doorway, crossroads cliché",
        },
        {
            "id": "two_gardens",
            "scene": "Two different garden paths emerge from the same meadow, one wild and one carefully cultivated; the protagonist has already turned toward one of them.",
            "action": "The person chooses a direction and begins walking.",
            "metaphor": "different futures grow from different choices",
            "avoid": "signposts, doorway, fortune-telling imagery",
        },
        {
            "id": "split_light",
            "scene": "A soft interior landscape opens into two pools of different colored light, and the protagonist reaches toward one while the other fades into the background.",
            "action": "The person makes a visible choice between two possibilities.",
            "metaphor": "choice as commitment to one possibility",
            "avoid": "literal doors, neon colors, abstract geometry without story",
        },
    ],
    "care_for_others": [
        {
            "id": "helping_up",
            "scene": "On a gentle hillside after rain, one adult reaches down to help another person stand, with soft wild grasses and warm light around them.",
            "action": "One person physically helps another regain balance.",
            "metaphor": "care is shown through a small act that changes another person's situation",
            "avoid": "romance, heroic rescue, charity advertisement",
        },
        {
            "id": "shared_shelter",
            "scene": "Two adults sit beneath a small tree during a light rain; one quietly moves a coat or umbrella so the other is sheltered too.",
            "action": "One person notices another's discomfort and makes room for them.",
            "metaphor": "compassion as noticing and responding",
            "avoid": "romantic embrace, staged charity photo",
        },
        {
            "id": "lantern_passed",
            "scene": "At blue hour, one person carefully passes a small warm lantern to another on a quiet path, illuminating both faces and the nearby ground.",
            "action": "A source of light is deliberately passed from one person to another.",
            "metaphor": "care as sharing what helps you move forward",
            "avoid": "magic spell, halo, fantasy costume",
        },
    ],
    "freedom": [
        {
            "id": "wind_fabric",
            "scene": "A wide meadow above the sea, with a loose pale scarf or fabric ribbon carried by the wind as the protagonist walks freely through tall grass.",
            "action": "The person moves without barriers while the wind carries the fabric outward.",
            "metaphor": "freedom as space, movement and breath",
            "avoid": "fashion shoot, arms-raised cliché, doorway",
        },
        {
            "id": "open_field_birds",
            "scene": "A broad field after rain with a flock of small birds crossing the sky while the protagonist follows a narrow natural trail through the grass.",
            "action": "The protagonist walks onward in an unobstructed landscape.",
            "metaphor": "freedom as the ability to choose one's own direction",
            "avoid": "airplane advertisement, generic road-to-sunrise",
        },
        {
            "id": "shoreline_walk",
            "scene": "A quiet open shoreline with a long curve of pale sand and water; the protagonist walks alone where land and sea meet, leaving a temporary trail of footprints.",
            "action": "The person chooses their own pace and direction in a wide open space.",
            "metaphor": "freedom as movement without confinement",
            "avoid": "travel brochure, luxury resort advertisement",
        },
    ],
    "resilience": [
        {
            "id": "after_storm",
            "scene": "A small garden after rain: some stems are bent but one person gently ties a young plant upright while warm light returns through the clouds.",
            "action": "The protagonist restores something fragile after difficulty.",
            "metaphor": "strength as careful recovery rather than victory",
            "avoid": "disaster spectacle, clenched fists, superhero pose",
        },
        {
            "id": "repaired_window",
            "scene": "A quiet house after a storm, with one cracked window carefully repaired and warm interior light returning; the protagonist finishes the last small repair.",
            "action": "The person completes a modest repair and restores shelter.",
            "metaphor": "resilience as rebuilding ordinary life",
            "avoid": "doorway, catastrophe imagery, construction advertisement",
        },
        {
            "id": "new_shoot",
            "scene": "A small green shoot emerges beside a weathered stone wall after rain while the protagonist clears fallen leaves from around it.",
            "action": "The protagonist makes space for fragile new growth.",
            "metaphor": "resilience as making room for life to return",
            "avoid": "giant flower, cliché sunrise",
        },
    ],
}

def choose_visual_motif(intent_id, recent_visuals):
    variants = VISUAL_MOTIF_VARIANTS.get(intent_id, [])
    if not variants:
        return None

    recent_motifs = {
        str(row.get("visual_motif") or "")
        for row in recent_visuals
        if row.get("visual_motif")
    }

    available = [v for v in variants if v["id"] not in recent_motifs]
    if not available:
        available = variants[:]
    return random.choice(available)

def abstract_visual_direction(intent_id, themes, mood):
    """Return a consistent illustration language while keeping each quote narrative."""
    metaphor = VISUAL_METAPHORS.get(
        intent_id,
        "a gentle symbolic transformation in which the human situation is expressed "
        "through landscape, gesture, scale and light rather than literal objects"
    )
    return {
        "medium": ABSTRACT_VISUAL_STYLE["medium"],
        "style_mood": ABSTRACT_VISUAL_STYLE["mood"],
        "palette": ABSTRACT_VISUAL_STYLE["palette"],
        "light": ABSTRACT_VISUAL_STYLE["light"],
        "composition": ABSTRACT_VISUAL_STYLE["composition"],
        "visual_metaphor": metaphor,
    }

def _clean_llm_text(text):
    """Normalize common Qwen/inference wrappers before JSON parsing."""
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"```(?:json|text|markdown)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "")
    return text.strip()


def _parse_llm_json(text):
    """Extract the first valid JSON object from an LLM response."""
    cleaned = _clean_llm_text(text)
    if not cleaned:
        return None

    candidates = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start:end + 1])

    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except Exception:
            continue
    return None


def _visual_diversity_summary(recent_visuals):
    """Summarize recent visual choices as hard anti-repetition guidance."""
    counts = {}
    motifs = []
    for row in recent_visuals or []:
        profile = {}
        raw = row.get("visual_profile")
        if raw:
            try:
                profile = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                profile = {}
        for key in ("subject_type", "visual_mode", "narrative_mode", "environment",
                    "composition_type", "medium", "relationship_type"):
            value = str(profile.get(key) or "").strip().lower()
            if value:
                counts.setdefault(key, {})
                counts[key][value] = counts[key].get(value, 0) + 1
        motif = str(row.get("visual_motif") or profile.get("visual_motif") or "").strip()
        if motif:
            motifs.append(motif)

    lines = []
    for key, values in counts.items():
        top = sorted(values.items(), key=lambda x: x[1], reverse=True)[:4]
        if top:
            lines.append(f"{key}: " + ", ".join(f"{v}({n})" for v, n in top))
    if motifs:
        lines.append("recent motifs: " + ", ".join(motifs[:12]))
    return "\n".join(lines) if lines else "No visual history yet."

def _concept_has_cliche(concept):
    """Reject common AI inspirational shortcuts unless the concept explicitly needs them."""
    blob = " ".join(
        str(concept.get(k) or "")
        for k in (
            "scene", "action", "visual_summary", "metaphor", "image_prompt",
            "subjects", "environment", "visual_motif", "core_meaning",
        )
    ).lower()
    patterns = {
        "woman_by_window": ("woman", "window"),
        "road_sunrise": ("road", "sunrise"),
        "mountain_sunrise": ("mountain", "sunrise"),
        "person_staring_mountains": ("person", "staring", "mountain"),
        "arms_raised": ("arms raised",),
        "generic_flowers": ("flowers", "bouquet"),
        "butterflies": ("butterflies",),
        "romantic_kiss": ("kissing",),
        "wedding_romance": ("wedding",),
        "mirror_selfie": ("mirror selfie",),
        "candle_cliche": ("candle", "romantic"),
        "sunset_couple": ("couple", "sunset"),
        "spa_healing": ("spa",),
        "yoga_healing": ("yoga",),
        "girlboss_stock": ("girlboss",),
        "motivational_poster": ("motivational poster",),
    }
    for name, terms in patterns.items():
        if all(term in blob for term in terms):
            return name
    return ""


def _concept_diversity_penalty(concept, recent_visuals):
    """Deterministic penalty for repeating recent visual dimensions."""
    if not concept or not recent_visuals:
        return 0.0
    fields = (
        "subject_type", "visual_mode", "narrative_mode", "environment",
        "composition_type", "medium", "relationship_type", "visual_motif",
    )
    penalty = 0.0
    for field in fields:
        value = str(concept.get(field) or "").strip().lower()
        if not value:
            continue
        repeats = 0
        for row in recent_visuals:
            profile = {}
            raw = row.get("visual_profile")
            if raw:
                try:
                    profile = json.loads(raw) if isinstance(raw, str) else (raw or {})
                except Exception:
                    profile = {}
            old = str(profile.get(field) or row.get(field) or "").strip().lower()
            if old and old == value:
                repeats += 1
        if repeats >= 3:
            penalty += 0.08
        elif repeats == 2:
            penalty += 0.04
    return min(0.30, penalty)

def _normalize_relationship(value):
    value = str(value or "none").strip().lower()
    allowed = {"one_person", "friendship", "family", "romance", "strangers",
               "community", "self", "none"}
    return value if value in allowed else "none"

def _hf_chat_completion(token, messages, max_tokens, temperature):
    """Call HF Router with provider failover, stopping immediately on quota/auth errors."""
    if not token:
        raise ValueError("HF token is missing")
    if token in _HF_TOKEN_DISABLED:
        reason = _HF_TOKEN_DISABLED_REASONS.get(token, "disabled")
        raise HFTokenUnavailable(reason)

    last_error = None
    for provider in HF_LLM_PROVIDERS or ["auto"]:
        model = HF_LLM_MODEL
        if provider and provider != "auto":
            model = f"{HF_LLM_MODEL}:{provider}"
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
        }
        if HF_LLM_DISABLE_THINKING:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            response = requests.post(
                "https://router.huggingface.co/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
                timeout=HF_LLM_TIMEOUT,
            )
            if response.ok:
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    raise ValueError("HF chat response has no choices")
                message = choices[0].get("message") or {}
                content = message.get("content") or ""
                reasoning = message.get("reasoning_content") or ""
                combined = content if content else reasoning
                if not combined:
                    raise ValueError("HF chat response has empty message content")
                logger.info("HF LLM chat succeeded: model=%s", model)
                return combined, data

            detail = response.text[:600]
            if response.status_code in (401, 402):
                reason = "quota_exhausted" if response.status_code == 402 else "unauthorized"
                _disable_hf_token(token, f"{reason} via {provider}")
                raise HFTokenUnavailable(
                    f"HF chat {response.status_code} via {provider}: {detail}",
                    status_code=response.status_code,
                )

            last_error = RuntimeError(f"HF chat {response.status_code} via {provider}: {detail}")
            logger.warning("HF LLM provider failed: %s", last_error)
        except HFTokenUnavailable:
            raise
        except Exception as exc:
            last_error = exc
            logger.warning("HF LLM provider exception via %s: %s", provider, exc)
    raise last_error or RuntimeError("No HF LLM provider succeeded")


def _llm_tokens():
    return _hf_token_pool()


def analyze_quote_semantics(quote_text, themes, mood):
    """Stage 1: semantic analyst. No visual styling; extract the actual claim and constraints."""
    if not quote_text or not HF_TOKEN and not HF_TOKEN_2:
        return None
    tokens = _hf_token_pool()

    prompt = f"""
You are a semantic analyst, not an image prompt writer. Analyze the exact human idea in this quote.
Do not invent a visual yet. Do not optimize for beauty. Do not use generic inspirational language.

QUOTE:
{quote_text}

TOPICS: {', '.join(themes[:5]) if themes else 'general reflection'}
MOOD: {mood}

Return ONLY JSON with:
{{
  "core_claim": "the precise claim the quote makes",
  "emotional_tension": "the central conflict, contrast, loss, choice or transition",
  "human_change": "what a person chooses, does, stops doing, accepts, releases or learns",
  "relationship_logic": "who is related to whom, if anyone; otherwise none",
  "idea_structure": "the logical structure of the quote, such as cause_effect, contrast, before_after, past_present_future, choice, boundary, reciprocity, acceptance, release, growth, or stillness",
  "clause_count": "integer count of distinct logical beats/clauses that materially need visual representation",
  "temporal_composition": "none, before_after, or past_present_future; choose past_present_future when the quote genuinely contains past/present/future progression",
  "temporal_beats": ["objects with fields phase, visual_state, evidence, placement; use phase=past|present|future and placement=foreground|midground|background|left|center|right"],
  "visual_mechanism": "the concrete mechanism that can make the abstract claim visible: action, interaction, transformation, contrast, accumulation, separation, repair, consequence, spatial relationship, or object arrangement",
  "specificity_anchor": "one or two concrete visible facts that would make this image uniquely about this quote rather than a generic inspirational image",
  "must_show": ["2-5 concrete things that a correct visual should communicate"],
  "must_not_show": ["2-6 likely wrong interpretations or clichés"],
  "visual_truth_test": "one sentence: if the viewer saw only the image, what should they be able to infer?"
}}
""".strip()

    for token, token_name in tokens:
        try:
            content, _ = _hf_chat_completion(
                token,
                [
                    {"role": "system", "content": "Be a rigorous semantic analyst. Return only JSON. Do not discuss your reasoning."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=min(HF_LLM_MAX_TOKENS, 1000),
                temperature=0.10,
            )
            data = _parse_llm_json(content) or {}
            required = ("core_claim", "emotional_tension", "human_change", "visual_truth_test", "visual_mechanism", "specificity_anchor")
            if not all(str(data.get(k) or "").strip() for k in required):
                raise ValueError("semantic analyst returned incomplete JSON")
            data["must_show"] = [str(x).strip() for x in (data.get("must_show") or []) if str(x).strip()][:6]
            data["must_not_show"] = [str(x).strip() for x in (data.get("must_not_show") or []) if str(x).strip()][:8]
            try:
                data["clause_count"] = max(1, min(6, int(data.get("clause_count") or 1)))
            except Exception:
                data["clause_count"] = 1
            data["temporal_composition"] = str(data.get("temporal_composition") or "none").strip().lower()
            if data["temporal_composition"] not in {"none", "before_after", "past_present_future"}:
                data["temporal_composition"] = "none"
            beats = []
            for beat in (data.get("temporal_beats") or [])[:3]:
                if isinstance(beat, dict):
                    beats.append({
                        "phase": clean_text(beat.get("phase"))[:40].lower() or "state",
                        "visual_state": clean_text(beat.get("visual_state"))[:280],
                        "evidence": clean_text(beat.get("evidence"))[:240],
                        "placement": clean_text(beat.get("placement"))[:80],
                    })
            data["temporal_beats"] = beats
            if TEMPORAL_COMPOSITION_ENABLED and data["temporal_composition"] != "none":
                needed = 3 if data["temporal_composition"] == "past_present_future" else 2
                if len(beats) < needed:
                    data["temporal_composition"] = "none"
                    data["temporal_beats"] = []
            data["source"] = token_name
            logger.info("Semantic analysis succeeded with %s: claim=%s", token_name, data["core_claim"][:220])
            return data
        except Exception as exc:
            logger.warning("Semantic analysis failed with %s: %s", token_name, exc)
    return None


def judge_visual_concept(quote_text, semantic, concept, token):
    """Stage 2 gate: ask a second LLM to infer the quote from the concept and score semantic truth."""
    if not quote_text or not concept or not token or not LLM_VISUAL_JUDGE:
        return True, 0.75, "judge skipped"
    try:
        prompt = f"""
You are a brutally strict visual editor. Decide whether this proposed scene is a genuine visual translation of the quote, not merely a beautiful mood.

QUOTE:
{quote_text}

SEMANTIC ANALYSIS:
core_claim: {semantic.get('core_claim','')}
emotional_tension: {semantic.get('emotional_tension','')}
human_change: {semantic.get('human_change','')}
must_show: {json.dumps(semantic.get('must_show', []), ensure_ascii=False)}
must_not_show: {json.dumps(semantic.get('must_not_show', []), ensure_ascii=False)}
visual_truth_test: {semantic.get('visual_truth_test','')}
visual_mechanism: {semantic.get('visual_mechanism','')}
specificity_anchor: {semantic.get('specificity_anchor','')}
idea_structure: {semantic.get('idea_structure','')}

PROPOSED CONCEPT:
{json.dumps(concept, ensure_ascii=False)}

First infer the message a viewer would get from the concept WITHOUT quoting the source. Then compare it with the source meaning.
Reject generic mood-only concepts, relationship substitutions, decorative metaphors, and clichés.
A beautiful scene that could fit hundreds of quotes is a weak concept.
If temporal_composition is before_after or past_present_future, reject concepts that collapse the quote into one static state.
The temporal beats must be inferable as one coherent spatially layered scene, not a literal collage or three-panel triptych.

Return ONLY JSON:
{{
  "semantic_fit": 0.0,
  "quote_inference_match": 0.0,
  "cliche_penalty": 0.0,
  "genericity_penalty": 0.0,
  "inferred_message": "what a viewer would think the scene means",
  "reason": "short decisive reason",
  "approve": true
}}
""".strip()
        raw, _ = _hf_chat_completion(
            token,
            [
                {"role": "system", "content": "Be a strict art director. Return only JSON. Do not discuss your reasoning."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=700,
            temperature=0.05,
        )
        data = _parse_llm_json(raw) or {}
        fit = max(0.0, min(1.0, float(data.get("semantic_fit", 0))))
        inf = max(0.0, min(1.0, float(data.get("quote_inference_match", 0))))
        cliche = max(0.0, min(1.0, float(data.get("cliche_penalty", 0))))
        genericity = max(0.0, min(1.0, float(data.get("genericity_penalty", 0))))
        deterministic_cliche = _concept_has_cliche(concept)
        score = (fit * 0.48) + (inf * 0.38) - (cliche * 0.08) - (genericity * 0.06)
        if deterministic_cliche:
            score -= VISUAL_GENERICITY_PENALTY
        score = max(0.0, min(1.0, score))
        approve = bool(data.get("approve", False)) and score >= VISUAL_CONCEPT_MIN_SCORE and fit >= 0.68 and inf >= VISUAL_INFERENCE_MIN_SCORE and not deterministic_cliche
        reason = clean_text(data.get("reason", ""))[:360]
        return approve, score, reason or str(data.get("inferred_message", ""))[:360]
    except Exception as exc:
        logger.warning("Visual concept judge unavailable: %s", exc)
        return False, 0.0, "judge unavailable"


def generate_llm_visual_concept(
    quote_text, themes, mood, recent_visuals=None, diversity_feedback="", semantic_analysis=None, variation_hint=""
):
    """Interpret the quote first, then design a distinct adult editorial scene."""
    if not quote_text:
        return None

    tokens = _hf_token_pool()
    if not tokens:
        logger.warning("No Hugging Face tokens configured for LLM art direction")
        return None

    recent = _visual_diversity_summary(recent_visuals or [])
    theme_text = ", ".join(themes[:5]) if themes else "general life reflection"
    semantic = semantic_analysis or {}
    semantic_text = json.dumps(semantic, ensure_ascii=False) if semantic else "No semantic analyst output; infer carefully."

    system_prompt = f"""
You are the senior visual editor for an elegant inspirational quote channel
aimed at an ADULT WOMEN'S AUDIENCE. Your job is NOT to make a generic beautiful
AI image. Your job is to visually express the exact human idea of THIS quote.

CORE PRINCIPLE:
The image must contain a clear visual answer to: "What is actually happening
here that makes the quote feel true?" Beauty is secondary to semantic truth.
Do not illustrate an emotion with a decorative symbol when the quote contains
an action, cause, choice, consequence, contrast or transformation. SHOW THE
MECHANISM. If the quote has multiple logical parts, encode those parts through
one coherent scene with visible relationships, stages, objects, or spatial
contrast rather than reducing the quote to one mood.
If the semantic analyst marks a temporal composition, build a single spatially layered narrative: foreground/midground/background, environmental traces, evolving light, or a physically plausible progression. Never make a graphic triptych, split-screen, collage, infographic, or three-panel illustration.
For past-present-future, the past should leave a visible trace, the present should be the focal state, and the future should be suggested by a plausible continuation/opening/trajectory.
A person is optional. Use people only when they improve the story.
The semantic analyst output below is the source of truth. Do not replace it with a generic
relationship, mood, landscape or aesthetic metaphor.

DEFAULT AESTHETIC:
{ADULT_AUDIENCE_STYLE}. Prefer realistic fine-art photography / cinematic
realism with natural anatomy, authentic materials, subtle imperfections,
restrained color grading, sophisticated composition, real environments and
plausible light. No childish or cartoon look. Painterly treatment is allowed
only when it is genuinely better for the meaning.

DO NOT DEFAULT TO:
woman + flowers, woman + window, woman + sunset, road + sunrise, mountains,
open arms, romantic couple, mirror selfie, candles, butterflies, generic
landscape, inspirational poster. These are allowed ONLY when the quote truly
requires them.

VISUAL MODES:
Choose exactly one:
- direct: a believable real-life moment literally embodies the idea;
- metaphorical: a physical visual metaphor makes an abstract idea tangible;
- hybrid: a real-life scene contains one subtle metaphorical element.

DIVERSITY:
Vary subject and visual language aggressively. A good scene may use one person,
two people, family, hands, an object, architecture, interior, nature, animal,
still life, city, landscape, or no human at all.
Also vary environment, narrative action, composition and medium.
Do not repeat recent choices merely because they are safe.

SEMANTIC DISCIPLINE:
love != automatic romance.
freedom != automatic mountains/sunrise.
hope != automatic sunrise.
growth != automatic seedling.
healing != automatic spa/yoga.
self-worth != automatic beauty portrait.
strength != automatic mountain summit.
letting go != automatic doorway.
success != automatic office/trophy.
If the quote contains a relationship, preserve the relationship exactly.

ADULT WOMEN'S AUDIENCE:
Aim for emotional maturity, taste, quiet confidence, natural beauty, lived-in
spaces, nuanced relationships and editorial sophistication. Avoid glossy
commercial "girlboss" aesthetics, plastic beauty, exaggerated youthfulness,
and social-media stock photography.

RECENT VISUAL HISTORY:
{recent}

SEMANTIC ANALYST OUTPUT:
{semantic_text}

EXTRA DIVERSITY PRESSURE:
{diversity_feedback or "none"}

VARIATION REQUEST:
{variation_hint or "Choose the strongest concept; do not imitate a previous concept."}

Return ONLY valid JSON.
""".strip()

    user_prompt = f"""
SOURCE QUOTE:
{quote_text}

TOPICS:
{theme_text}

MOOD:
{mood}

Create one original visual concept for this exact quote. The scene must satisfy the semantic analyst's must_show and must_not_show constraints.

Required JSON:
{{
  "core_meaning": "deep meaning in plain language",
  "emotional_tension": "central emotional conflict or transition",
  "human_change": "what is chosen, done, released, repaired, accepted or changed",
  "relationship_type": "one_person, friendship, family, romance, strangers, community, self, or none",
  "visual_mode": "direct, metaphorical, or hybrid",
  "visual_summary": "one sentence explaining why this image expresses the quote",
  "semantic_anchor": "the exact visible evidence that makes this scene about this quote",
  "temporal_composition": "none, before_after, or past_present_future",
  "temporal_beats": [
   "temporal_beats": ["objects with fields phase, visual_state, evidence, placement; use phase=past|present|future and placement=foreground|midground|background|left|center|right"],
  ],
  "continuity_device": "the physical/environmental device that makes the multiple stages read as one scene",
  "causal_logic": "how the visible action/relationship/transformation makes the quote true",
  "specificity": "why this scene could not be swapped onto 100 other inspirational quotes",
  "scene": "one concrete scene with one clear narrative moment",
  "action": "the physically observable action",
  "subjects": "specific people/objects/environment",
  "subject_type": "person, two_people, group, hands, object, still_life, architecture, nature, animal, landscape, mixed, or abstract_physical",
  "narrative_mode": "action, interaction, transformation, choice, release, repair, creation, observation, discovery, contrast, aftermath, or stillness",
  "environment": "specific setting",
  "composition_type": "close_up, medium, wide, overhead, low_angle, side_profile, negative_space, symmetrical, asymmetrical, layered, or detail",
  "metaphor": "one subtle metaphor if useful, otherwise none",
  "medium": "realistic fine-art photography, cinematic photography, editorial photography, still life photography, architectural photography, documentary-like photography, painterly realism, or another tasteful medium",
  "lighting": "specific believable light",
  "palette": "restrained sophisticated palette",
  "mood": "emotional atmosphere",
  "visual_motif": "unique 2-6 word label",
  "avoid": "specific wrong interpretations and clichés",
  "image_prompt": "polished English prompt for the image model"
}}

IMAGE PROMPT:
- ONE image, ONE story, ONE focal idea.
- Make the semantic connection obvious without writing the quote into the image.
- Prefer a meaningful action, relationship, consequence, contrast or physical transformation.
- SHOW THE SEMANTIC MECHANISM, not merely the emotion.
- If the quote has several clauses, use a coherent visual structure that lets the viewer infer those clauses.
- If temporal_composition is active, use layered depth or a believable progression within one continuous location. Past = visible trace, present = focal action/state, future = plausible continuation or opening. Never use split-screen, triptych, collage, panels, timeline graphics, or duplicated subjects.
- The viewer should understand the sequence through physical evidence, not labels or text.
- Avoid decorative symbols that merely label an emotion (hearts, butterflies, generic flowers, glowing light, random birds) unless the quote specifically depends on them.
- No text, letters, numbers, logos, watermarks, signs, posters, readable books,
  screens, packaging, UI or fake credits.
- Realistic and sophisticated by default.
- No generic stock-photo pose.
- Do not automatically include a woman.
- If people appear, they should look like real adults, naturally styled and
  naturally posed; avoid fashion-ad poses and exaggerated beauty.
- No romance unless the quote supports romance.
- Avoid cliché inspirational imagery unless semantically essential.
""".strip()

    for token, token_name in tokens:
        try:
            content, _ = _hf_chat_completion(
                token,
                [
                    {"role": "system", "content": system_prompt + "\nDo not discuss your reasoning; return the requested JSON only."},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=HF_LLM_MAX_TOKENS,
                temperature=HF_LLM_TEMPERATURE,
            )
            data = _parse_llm_json(content)
            if not data:
                raise ValueError("LLM returned invalid JSON")

            required = (
                "core_meaning", "emotional_tension", "human_change",
                "scene", "action", "image_prompt", "subject_type", "semantic_anchor", "causal_logic", "specificity",
                "narrative_mode", "environment", "visual_mode",
            )
            if not all(str(data.get(key) or "").strip() for key in required):
                raise ValueError("LLM response is missing required visual fields")

            data["relationship_type"] = _normalize_relationship(data.get("relationship_type"))
            data["visual_mode"] = str(data.get("visual_mode") or "direct").strip().lower()
            if data["visual_mode"] not in {"direct", "metaphorical", "hybrid"}:
                data["visual_mode"] = "direct"
            data["visual_motif"] = str(data.get("visual_motif") or "bespoke scene").strip()[:120]
            data["medium"] = str(data.get("medium") or "realistic fine-art photography").strip()[:300]
            data["subject_type"] = str(data.get("subject_type") or "mixed").strip()[:80]
            data["narrative_mode"] = str(data.get("narrative_mode") or "observation").strip()[:80]
            data["environment"] = str(data.get("environment") or "real interior or exterior").strip()[:160]
            data["composition_type"] = str(data.get("composition_type") or "medium").strip()[:80]
            data["semantic_anchor"] = str(data.get("semantic_anchor") or "").strip()[:420]
            data["causal_logic"] = str(data.get("causal_logic") or "").strip()[:420]
            data["specificity"] = str(data.get("specificity") or "").strip()[:420]
            data["temporal_composition"] = str(data.get("temporal_composition") or semantic.get("temporal_composition") or "none").strip().lower()
            if data["temporal_composition"] not in {"none", "before_after", "past_present_future"}:
                data["temporal_composition"] = "none"
            temporal_beats = []
            for beat in (data.get("temporal_beats") or [])[:3]:
                if not isinstance(beat, dict):
                    continue
                temporal_beats.append({
                    "phase": str(beat.get("phase") or "state").strip().lower(),
                    "visual_state": clean_text(beat.get("visual_state"))[:280],
                    "evidence": clean_text(beat.get("evidence"))[:240],
                    "placement": clean_text(beat.get("placement"))[:80],
                })
            if not temporal_beats and semantic.get("temporal_beats"):
                temporal_beats = semantic.get("temporal_beats", [])[:3]
            data["temporal_beats"] = temporal_beats
            data["continuity_device"] = clean_text(data.get("continuity_device"))[:320]
            if TEMPORAL_COMPOSITION_ENABLED and semantic.get("temporal_composition") != "none":
                expected = 3 if semantic.get("temporal_composition") == "past_present_future" else 2
                if data["temporal_composition"] == "none":
                    data["temporal_composition"] = semantic.get("temporal_composition")
                if len(data["temporal_beats"]) < expected:
                    data["temporal_beats"] = semantic.get("temporal_beats", [])[:expected]
                if len(data["temporal_beats"]) < expected:
                    raise ValueError("temporal concept is missing required beats")
                if not data["continuity_device"]:
                    data["continuity_device"] = "one continuous environment with layered depth and a visible trace of change"

            cliche = _concept_has_cliche(data)
            if cliche and diversity_feedback:
                raise ValueError(f"concept still uses rejected cliché: {cliche}")

            data["source"] = "hf_llm"
            data["llm_model"] = HF_LLM_MODEL
            logger.info(
                "HF LLM art direction succeeded with %s: mode=%s subject=%s environment=%s motif=%s",
                token_name, data["visual_mode"], data["subject_type"],
                data["environment"], data["visual_motif"],
            )
            return data
        except Exception as exc:
            logger.warning("HF LLM art direction failed with %s: %s", token_name, exc)

    return None


def build_visual_concept(quote_text, themes, mood, diversity_feedback=""):
    recent_visuals = get_recent_visuals()

    semantic = analyze_quote_semantics(quote_text, themes, mood)
    if semantic is None:
        logger.warning("Semantic analyst unavailable; using legacy quote-specific director fallback.")

    # Generate several genuinely different concepts, then judge them independently.
    candidates = []
    tokens = [token for token, _name in _hf_token_pool()]

    variation_modes = [
        "Prefer a DIRECT real-life scene. Make the quote's claim physically observable through an action, interaction, consequence or choice.",
        "Prefer a METAPHORICAL or object-led scene using architecture, still life, nature, materials or spatial contrast. No people unless they are semantically necessary. The physical arrangement must explain the claim, not merely decorate it.",
        "Prefer a HYBRID or temporal/contrast scene: show a visible before/after, two states, reciprocal action, separation/repair, or another concrete structure that maps onto the quote's logic. Keep it subtle and editorial.",
    ]

    if semantic and tokens:
        for i in range(max(1, VISUAL_CONCEPT_CANDIDATES)):
            hint = variation_modes[i % len(variation_modes)]
            if i >= len(variation_modes):
                hint += " Use a substantially different subject and environment from the other candidates."
            concept = generate_llm_visual_concept(
                quote_text, themes, mood, recent_visuals=recent_visuals,
                diversity_feedback=diversity_feedback,
                semantic_analysis=semantic, variation_hint=hint,
            )
            if not concept:
                continue
            penalty = _concept_diversity_penalty(concept, recent_visuals)
            approve = False
            score = 0.0
            reason = ""
            for token in tokens:
                approve, score, reason = judge_visual_concept(quote_text, semantic, concept, token)
                if reason != "judge unavailable":
                    break
            score = max(0.0, score - penalty)
            concept["concept_judge_score"] = score
            concept["concept_judge_reason"] = reason
            concept["semantic_analysis"] = semantic
            concept["diversity_penalty"] = penalty
            if approve and score >= VISUAL_CONCEPT_MIN_SCORE:
                candidates.append(concept)
            logger.info(
                "Visual concept candidate %s: score=%.2f approved=%s subject=%s environment=%s reason=%s",
                i + 1, score, approve, concept.get("subject_type"), concept.get("environment"), reason[:180],
            )

    if candidates:
        candidates.sort(key=lambda c: float(c.get("concept_judge_score", 0)), reverse=True)
        best = candidates[0]
        logger.info("Selected best visual concept: score=%.2f motif=%s", best.get("concept_judge_score", 0), best.get("visual_motif", ""))
        llm_concept = best
        return {
            "archetype": "llm_bespoke",
            "scene": llm_concept.get("scene", ""),
            "avoid_scene": llm_concept.get("avoid", ""),
            "subjects": llm_concept.get("subjects", ""),
            "camera": "chosen by the visual art director",
            "composition": llm_concept.get("composition", ""),
            "theme": themes[0] if themes else "soul",
            "theme_description": THEME_VISUALS.get(themes[0] if themes else "soul", "quiet emotional depth and authentic human presence"),
            "mood": mood,
            "mood_description": llm_concept.get("mood", mood),
            "quote_intent": quote_text,
            "core_meaning": llm_concept.get("core_meaning", semantic.get("core_claim", "") if semantic else ""),
            "emotional_tension": llm_concept.get("emotional_tension", semantic.get("emotional_tension", "") if semantic else ""),
            "human_change": llm_concept.get("human_change", semantic.get("human_change", "") if semantic else ""),
            "relationship_type": llm_concept.get("relationship_type", "none"),
            "visual_mode": llm_concept.get("visual_mode", "direct"),
            "subject_type": llm_concept.get("subject_type", "mixed"),
            "narrative_mode": llm_concept.get("narrative_mode", "observation"),
            "environment": llm_concept.get("environment", ""),
            "composition_type": llm_concept.get("composition_type", "medium"),
            "visual_thesis": llm_concept.get("visual_summary", semantic.get("visual_truth_test", "") if semantic else ""),
            "temporal_composition": llm_concept.get("temporal_composition", semantic.get("temporal_composition", "none") if semantic else "none"),
            "temporal_beats": llm_concept.get("temporal_beats", semantic.get("temporal_beats", []) if semantic else []),
            "continuity_device": llm_concept.get("continuity_device", ""),
            "semantic_anchor": llm_concept.get("semantic_anchor", semantic.get("specificity_anchor", "") if semantic else ""),
            "causal_logic": llm_concept.get("causal_logic", semantic.get("visual_mechanism", "") if semantic else ""),
            "specificity": llm_concept.get("specificity", ""),
            "narrative_action": llm_concept.get("action", ""),
            "visual_metaphor": llm_concept.get("metaphor", ""),
            "visual_motif": llm_concept.get("visual_motif", "llm_bespoke"),
            "medium": llm_concept.get("medium", "realistic fine-art photography"),
            "style_mood": llm_concept.get("mood", "tender, beautiful, sophisticated"),
            "palette": llm_concept.get("palette", "soft harmonious restrained colors"),
            "light": llm_concept.get("lighting", "soft natural cinematic light"),
            "intent_id": "llm_bespoke",
            "llm_image_prompt": llm_concept.get("image_prompt", ""),
            "llm_model": llm_concept.get("llm_model", HF_LLM_MODEL),
            "source": "hf_llm",
            "semantic_analysis": semantic or {},
            "must_show": (semantic or {}).get("must_show", []),
            "must_not_show": (semantic or {}).get("must_not_show", []),
            "concept_judge_score": llm_concept.get("concept_judge_score", 0),
            "concept_judge_reason": llm_concept.get("concept_judge_reason", ""),
        }

    # Reliable local fallback if HF LLM/semantic judge is temporarily unavailable.
    intent = extract_visual_intent(quote_text, themes, mood)
    archetype_by_name = {a["name"]: a for a in VISUAL_ARCHETYPES}
    archetype = archetype_by_name.get(intent["archetype"]) or select_archetype(themes, mood)
    motif = choose_visual_motif(intent["id"], recent_visuals)
    theme = themes[0] if themes else "soul"
    theme_description = THEME_VISUALS.get(theme, "quiet emotional depth and authentic human presence")
    direction = abstract_visual_direction(intent["id"], themes, mood)
    return {
        "archetype": archetype["name"],
        "scene": motif["scene"] if motif else archetype["description"],
        "avoid_scene": f'{archetype["avoid"]}; {intent.get("avoid", "")}; {motif.get("avoid", "") if motif else ""}'.strip("; "),
        "subjects": intent.get("subjects") or archetype["subjects"],
        "camera": archetype["camera"],
        "composition": direction["composition"],
        "theme": theme,
        "theme_description": theme_description,
        "mood": mood,
        "mood_description": MOODS.get(mood, MOODS["introspective"])["visual"],
        "quote_intent": quote_text,
        "visual_thesis": (semantic or {}).get("core_claim") or intent["thesis"],
        "temporal_composition": (semantic or {}).get("temporal_composition", "none"),
        "temporal_beats": (semantic or {}).get("temporal_beats", []),
        "continuity_device": "one continuous environment with layered depth" if (semantic or {}).get("temporal_composition", "none") != "none" else "",
        "semantic_anchor": (semantic or {}).get("specificity_anchor", "") or (motif["metaphor"] if motif else ""),
        "causal_logic": (semantic or {}).get("visual_mechanism", "") or (motif["action"] if motif else ""),
        "specificity": "Use one concrete visible mechanism rather than a generic mood image.",
        "narrative_action": (semantic or {}).get("human_change") or (motif["action"] if motif else intent["action"]),
        "visual_metaphor": motif["metaphor"] if motif else direction["visual_metaphor"],
        "visual_motif": motif["id"] if motif else "",
        "medium": "realistic fine-art photography / cinematic realism",
        "style_mood": "sophisticated, emotionally mature, restrained, editorial",
        "palette": "natural restrained colors, subtle filmic contrast, no pastel fantasy",
        "light": "soft believable natural or cinematic light",
        "visual_mode": "direct",
        "subject_type": "mixed",
        "narrative_mode": "action",
        "environment": "specific real-world setting",
        "composition_type": "medium",
        "intent_id": intent["id"],
        "source": "local_fallback",
        "semantic_analysis": semantic or {},
        "must_show": (semantic or {}).get("must_show", []),
        "must_not_show": (semantic or {}).get("must_not_show", []),
        "concept_judge_score": 0.0,
        "concept_judge_reason": "local fallback",
    }


def generate_image_prompt(quote_text, themes, mood, diversity_feedback=""):
    concept = build_visual_concept(quote_text, themes, mood, diversity_feedback=diversity_feedback)

    # When HF LLM succeeded, its quote-specific English prompt is the primary
    # instruction. We only append channel-wide safety/style constraints here.
    llm_prompt = str(concept.get("llm_image_prompt") or "").strip()
    if llm_prompt:
        prompt = f"""
{llm_prompt}

SEMANTIC ART-DIRECTOR CHECK:
Core meaning: {concept.get("core_meaning", "")}
Emotional tension: {concept.get("emotional_tension", "")}
Human change/action: {concept.get("human_change", concept.get("narrative_action", ""))}
Semantic anchor: {concept.get("semantic_anchor", "")}
Causal visual logic: {concept.get("causal_logic", "")}
Specificity test: {concept.get("specificity", "")}
Relationship type: {concept.get("relationship_type", "none")}
Visual mode: {concept.get("visual_mode", "direct")}
Subject type: {concept.get("subject_type", "mixed")}
Narrative mode: {concept.get("narrative_mode", "action")}
Environment: {concept.get("environment", "")}
Composition type: {concept.get("composition_type", "medium")}
Temporal composition: {concept.get("temporal_composition", "none")}
Temporal beats: {json.dumps(concept.get("temporal_beats", []), ensure_ascii=False)}
Continuity device: {concept.get("continuity_device", "")}
MUST VISUALLY COMMUNICATE: {json.dumps(concept.get("must_show", []), ensure_ascii=False)}
MUST NOT VISUALLY SUGGEST: {json.dumps(concept.get("must_not_show", []), ensure_ascii=False)}
Diversity instruction: {diversity_feedback or "Choose a visual approach not overrepresented in recent posts."}

GLOBAL VISUAL QUALITY:
Sophisticated adult editorial / fine-art sensibility. Realistic fine-art
photography or cinematic realism by default. Believable adult anatomy, natural
skin texture, authentic materials, physically plausible light, subtle depth of
field, restrained filmic color grading and lived-in environments. Beautiful
without looking glossy, commercial, childish or over-processed.

SEMANTIC PRIORITY:
The exact meaning of the source quote is more important than generic beauty.
Every major visual element should support the story described above. Avoid
filler scenery and generic inspirational imagery.
SHOW THE MECHANISM: if the quote is about choice, show the choice; if it is
about release, show what is released; if it is about reciprocity, show the
reciprocal act; if it is about time or transformation, show a visible before/
after relationship or progression. For past-present-future concepts, use layered depth and environmental continuity so the viewer reads a past trace, present focal state, and future direction in one believable scene. Do not substitute a symbol for the claim.

ABSOLUTE TEXT BAN:
No text, letters, numbers, words, captions, subtitles, logos, signatures,
watermarks, typography, readable signs, posters, books with readable pages,
newspapers, screens, phones, packaging, menus, documents, cards, tickets,
billboards, storefront lettering or UI.

NEGATIVE STYLE:
{NEGATIVE_PROMPT}; generic woman standing alone; doorway cliché; person walking
into sunrise; person staring at mountains; romantic couple unless explicitly
supported by the quote; kissing; wedding imagery; engagement-photo aesthetic;
stock-photo pose; fashion campaign; beauty advertisement; motivational poster;
generic inspirational landscape; forced symbolism; excessive surrealism;
oversaturation; harsh HDR; plastic CGI; cartoon; anime; vector art; obvious
watercolor or storybook treatment; fake photographer credit; random letters;
visible watermark; logo; signature; text-like marks.

ONE IMAGE, ONE STORY, ONE FOCAL IDEA. Vertical 4:5 composition suitable for
Telegram.
""".strip()
        return re.sub(r"\s+", " ", prompt)[:5000], concept

    # Local fallback: preserve the proven hf5 pipeline if the LLM endpoint is
    # temporarily unavailable.
    prompt = f"""
Create ONE beautiful vertical visual scene inspired by the exact meaning of the
source quote. The image may be an elegant fine-art photograph or a refined
painterly illustration, whichever serves the quote better. Do not force a
single medium.

CORE IDEA: {concept["visual_thesis"]}

STORY / HUMAN ACTION: {concept["narrative_action"]}

VISUAL METAPHOR: {concept["visual_metaphor"]}

SCENE: {concept["scene"]}

SUBJECTS: {concept["subjects"]}

MEDIUM: {concept["medium"]}

EMOTIONAL ATMOSPHERE: {concept["style_mood"]}

COLOR PALETTE: {concept["palette"]}

LIGHT: {concept["light"]}

COMPOSITION: {concept["composition"]}

SOURCE QUOTE — MEANING ONLY:
{quote_text}

Translate the emotional meaning into one coherent scene. Do not draw the
literal words. Do not make a beautiful woman the default subject. Prefer a
specific action or relationship when the quote contains one.

GLOBAL QUALITY: elegant, emotionally mature, sophisticated, realistic,
quietly beautiful, adult editorial-art sensibility, soft believable light,
restrained natural colors, authentic materials and skin texture.

AVOID: {concept["avoid_scene"]}; {NEGATIVE_PROMPT}; generic doorway silhouette;
generic road-to-sunrise; generic mountain-top triumph; motivational poster;
forced symbolism; stock-photo posing; cartoon illustration; watercolor;
storybook style; fantasy concept art unless semantically necessary.

ABSOLUTE TEXT BAN: no text, letters, numbers, words, captions, subtitles,
logos, signatures, watermarks, typography, readable signs or UI.

ONE IMAGE, ONE STORY, ONE FOCAL IDEA. Vertical 4:5 composition suitable for
Telegram.
""".strip()
    return re.sub(r"\s+", " ", prompt)[:5000], concept


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

def _image_bytes_from_pil(image):
    """Serialize a PIL image to PNG bytes for Telegram."""
    try:
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    except Exception as exc:
        logger.warning("Could not serialize generated image: %s", exc)
        return None


def _aihorde_headers():
    return {
        "Content-Type": "application/json",
        "apikey": AIHORDE_API_KEY,
        "Client-Agent": AIHORDE_CLIENT_AGENT,
    }


def generate_image_ai_horde(prompt, width=None, height=None):
    """Generate one image through the free AI Horde volunteer network.

    No Hugging Face image token is required. The anonymous AI Horde key is used
    by default and has the lowest queue priority; a personal AI Horde key is
    optional and can be supplied through AIHORDE_API_KEY.
    """
    if not prompt:
        return None, ""

    width = width or AIHORDE_IMAGE_WIDTH
    height = height or AIHORDE_IMAGE_HEIGHT
    # AI Horde expects dimensions divisible by 64.
    width = max(64, int(width // 64 * 64))
    height = max(64, int(height // 64 * 64))

    payload = {
        "prompt": f"{prompt}###{NEGATIVE_PROMPT}",
        "models": [AIHORDE_IMAGE_MODEL],
        "params": {
            "width": width,
            "height": height,
            "steps": max(1, AIHORDE_IMAGE_STEPS),
            "cfg_scale": AIHORDE_IMAGE_CFG,
            "sampler_name": AIHORDE_IMAGE_SAMPLER,
            "n": 1,
        },
        "nsfw": False,
    }

    try:
        response = requests.post(
            f"{AIHORDE_API_BASE}/generate/async",
            headers=_aihorde_headers(),
            json=payload,
            timeout=30,
        )
        if response.status_code >= 400:
            logger.warning("AI Horde submit failed: HTTP %s %s", response.status_code, response.text[:500])
            return None, ""
        job = response.json()
        job_id = job.get("id")
        if not job_id:
            logger.warning("AI Horde returned no generation id: %s", job)
            return None, ""

        logger.info("AI Horde image job submitted: id=%s model=%s", job_id, AIHORDE_IMAGE_MODEL)
        deadline = time.time() + AIHORDE_IMAGE_TIMEOUT
        last_status = None

        while time.time() < deadline:
            time.sleep(max(1.0, AIHORDE_POLL_INTERVAL))
            status_response = requests.get(
                f"{AIHORDE_API_BASE}/generate/check/{job_id}",
                headers={"Client-Agent": AIHORDE_CLIENT_AGENT},
                timeout=20,
            )
            if status_response.status_code >= 400:
                logger.warning("AI Horde check failed: HTTP %s %s", status_response.status_code, status_response.text[:300])
                continue

            status = status_response.json()
            if status != last_status:
                logger.info(
                    "AI Horde job %s: done=%s queue=%s wait=%s finished=%s",
                    job_id,
                    status.get("done"),
                    status.get("queue_position"),
                    status.get("wait_time"),
                    status.get("finished"),
                )
                last_status = status

            if status.get("done"):
                break
        else:
            logger.warning("AI Horde image job timed out: id=%s", job_id)
            return None, ""

        final_response = requests.get(
            f"{AIHORDE_API_BASE}/generate/status/{job_id}",
            headers={"Client-Agent": AIHORDE_CLIENT_AGENT},
            timeout=30,
        )
        if final_response.status_code >= 400:
            logger.warning("AI Horde final status failed: HTTP %s %s", final_response.status_code, final_response.text[:500])
            return None, ""

        final = final_response.json()
        generations = final.get("generations") or []
        if not generations:
            logger.warning("AI Horde completed without an image: %s", final)
            return None, ""

        image_url = generations[0].get("img")
        if not image_url:
            logger.warning("AI Horde generation has no image URL: %s", generations[0])
            return None, ""

        image_response = requests.get(image_url, timeout=60)
        if image_response.status_code != 200 or not is_valid_image(image_response.content):
            logger.warning("AI Horde image download failed: HTTP %s", image_response.status_code)
            return None, ""

        model = generations[0].get("model") or AIHORDE_IMAGE_MODEL
        worker = generations[0].get("worker_name") or "unknown"
        logger.info("AI Horde image received: model=%s worker=%s bytes=%s", model, worker, len(image_response.content))
        return image_response.content, f"AIHorde:{model}"
    except requests.RequestException as exc:
        logger.warning("AI Horde image generation network error: %s", exc)
    except Exception as exc:
        logger.warning("AI Horde image generation failed: %s", exc)

    return None, ""


def image_has_obvious_text(data):
    """Reject generated images containing likely text, watermarks or credits."""
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(BytesIO(data)).convert("RGB")
        width, height = img.size
        info = pytesseract.image_to_data(
            img,
            config="--psm 11",
            output_type=pytesseract.Output.DICT,
        )
        hits = []
        for text, conf, left, top, w, h in zip(
            info.get("text", []),
            info.get("conf", []),
            info.get("left", []),
            info.get("top", []),
            info.get("width", []),
            info.get("height", []),
        ):
            token = (text or "").strip()
            try:
                confidence = float(conf)
            except Exception:
                confidence = 0
            letters = re.sub(r"[^A-Za-zА-Яа-яЁё]", "", token)
            if len(letters) >= 4 and confidence >= 70:
                hits.append((token, confidence, int(left or 0), int(top or 0), int(w or 0), int(h or 0)))

        if hits:
            bottom_hits = [h for h in hits if h[3] > height * 0.78]
            logger.info("OCR text candidate(s) detected: total=%s bottom=%s", len(hits), len(bottom_hits))
            return True
        return False
    except ImportError:
        logger.warning("OCR gate unavailable: install pytesseract and tesseract-ocr")
        return False
    except Exception as exc:
        logger.debug("OCR gate skipped: %s", exc)
        return False


def caption_image_huggingface(data, token):
    """Get a plain-language description of the generated image when HF vision is available."""
    if not data or not token or not HF_VISION_MODEL:
        return ""
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(
            provider=HF_LLM_PROVIDER,
            api_key=token,
            timeout=HF_LLM_TIMEOUT,
        )
        result = client.image_to_text(image=data, model=HF_VISION_MODEL)
        text = getattr(result, "generated_text", "") or ""
        return clean_text(text)[:1200]
    except Exception as exc:
        logger.info("HF vision captioning unavailable: %s", exc)
        return ""

def judge_image_semantic_match(quote_text, concept, image_caption, token):
    if not quote_text or not image_caption or not token or not LLM_VISUAL_JUDGE:
        return True, 1.0, "judge skipped"
    try:
        semantic = concept.get("semantic_analysis") or {}
        prompt = f"""
You are the final quality-control editor for a sophisticated adult quote channel.
Judge the ACTUAL image, not the prompt. Do not reward beauty or a matching mood.

SOURCE QUOTE:
{quote_text}

SEMANTIC TRUTH:
{json.dumps(semantic, ensure_ascii=False)}

PLANNED VISUAL THESIS:
{concept.get("core_meaning", "")}

SEMANTIC ANCHOR:
{concept.get("semantic_anchor", "")}

CAUSAL VISUAL LOGIC:
{concept.get("causal_logic", "")}

SPECIFICITY TEST:
{concept.get("specificity", "")}

PLANNED ACTION:
{concept.get("narrative_action") or concept.get("action", "")}

ACTUAL IMAGE DESCRIPTION:
{image_caption}

Infer the message a viewer would get from the image alone. Then compare it with the quote.
Reject if the image merely depicts a pleasant mood, a generic relationship, a generic landscape, or a common inspirational cliché.
Reject if the visible relationship/action contradicts the quote.

Return ONLY JSON:
{{
  "semantic_match": 0.0,
  "quote_inference_match": 0.0,
  "cliche_penalty": 0.0,
  "genericity_penalty": 0.0,
  "mechanism_visible": true,
  "inferred_message": "what the image actually communicates",
  "reason": "brief decisive reason"
}}
""".strip()
        raw, _ = _hf_chat_completion(
            token,
            [
                {"role": "system", "content": "Be brutally strict. Return only JSON. Do not discuss your reasoning."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=650,
            temperature=0.05,
        )
        data = _parse_llm_json(raw) or {}
        fit = max(0.0, min(1.0, float(data.get("semantic_match", 0))))
        inf = max(0.0, min(1.0, float(data.get("quote_inference_match", 0))))
        cliche = max(0.0, min(1.0, float(data.get("cliche_penalty", 0))))
        genericity = max(0.0, min(1.0, float(data.get("genericity_penalty", 0))))
        mechanism_visible = bool(data.get("mechanism_visible", True))
        score = max(0.0, min(1.0, fit * 0.50 + inf * 0.40 - cliche * 0.06 - genericity * 0.04))
        if not mechanism_visible:
            score = max(0.0, score - 0.18)
        ok = score >= VISUAL_SEMANTIC_MIN_SCORE and fit >= 0.66 and inf >= VISUAL_INFERENCE_MIN_SCORE and mechanism_visible
        reason = clean_text(data.get("reason", ""))[:320]
        return ok, score, reason or clean_text(data.get("inferred_message", ""))[:320]
    except Exception as exc:
        logger.warning("Visual semantic judge unavailable: %s", exc)
        return False, 0.0, "judge unavailable"


def validate_generated_image_semantics(image_bytes, quote_text, concept):
    """Validate OCR, semantic truth and recent visual caption repetition."""
    if not image_bytes:
        return False, "", 0.0

    if image_has_obvious_text(image_bytes):
        logger.warning("Image rejected by OCR/text gate.")
        return False, "", 0.0

    if not VISUAL_SEMANTIC_GATE:
        return True, "", 1.0

    tokens = [token for token, _name in _hf_token_pool()]

    recent_visuals = get_recent_visuals(RECENT_DIVERSITY_WINDOW)
    recent_captions = [
        str(row.get("image_caption") or "").strip()
        for row in recent_visuals
        if str(row.get("image_caption") or "").strip()
    ]
    current_visual_hash = visual_perceptual_hash(image_bytes)
    recent_hash_similarity = max(
        (visual_hash_similarity(current_visual_hash, str(row.get("visual_hash") or "")) for row in recent_visuals),
        default=0.0,
    )
    if recent_hash_similarity >= 0.94:
        logger.warning("Image rejected for near-duplicate visual composition: hash_similarity=%.2f", recent_hash_similarity)
        return False, "", 0.0

    for token in tokens:
        caption = caption_image_huggingface(image_bytes, token)
        if not caption:
            continue

        # A caption that is almost the same as a recent image is a strong sign of visual repetition.
        caption_dup = max((lexical_similarity(caption, old) for old in recent_captions), default=0.0)
        if caption_dup >= VISUAL_CAPTION_DUP_THRESHOLD:
            logger.warning("Image rejected for visual repetition: caption_similarity=%.2f", caption_dup)
            return False, caption, 0.0

        ok, score, reason = judge_image_semantic_match(quote_text, concept, caption, token)
        logger.info(
            "Visual semantic gate: score=%.2f ok=%s caption_similarity=%.2f hash_similarity=%.2f caption=%s reason=%s",
            score, ok, caption_dup, recent_hash_similarity, caption[:220], reason,
        )
        if ok:
            return True, caption, score
        return False, caption, score

    # External vision/judge unavailable: do not break the existing deployment.
    logger.warning("Visual semantic gate could not obtain an HF vision/judge response; accepting image after OCR gate.")
    return True, "", 1.0


def crop_image_to_square(data, target_size=1024):
    """Normalize generated artwork to a square locally.

    AI Horde is requested at 1024x1024 so anonymous/free requests stay within
    the no-upfront-kudos budget. If a worker returns a different aspect ratio,
    crop the centered square locally before OCR/semantic validation/publication.
    """
    try:
        from PIL import Image
        img = Image.open(BytesIO(data)).convert("RGB")
        w, h = img.size
        side = min(w, h)
        left = max(0, (w - side) // 2)
        top = max(0, (h - side) // 2)
        img = img.crop((left, top, left + side, top + side))
        if img.size != (target_size, target_size):
            img = img.resize((target_size, target_size), Image.Resampling.LANCZOS)
        result = _image_bytes_from_pil(img)
        if result and is_valid_image(result):
            logger.info("Local image normalization: %sx%s -> %sx%s", w, h, target_size, target_size)
            return result
    except Exception as exc:
        logger.warning("Local square crop failed: %s", exc)
    return data


def generate_image(prompt, width=None, height=None):
    """Generate images exclusively through the free AI Horde network.

    Hugging Face credentials are intentionally not involved in image generation.
    They remain available only for semantic analysis / visual judging.
    """
    # Always request the free-friendly square dimensions at the Horde boundary.
    image, provider = generate_image_ai_horde(
        prompt, width=AIHORDE_IMAGE_WIDTH, height=AIHORDE_IMAGE_HEIGHT
    )
    if image and is_valid_image(image):
        image = crop_image_to_square(image, target_size=1024)
        if image_has_obvious_text(image):
            logger.warning("AI Horde candidate rejected: obvious text detected")
            return None, ""
        return image, provider

    logger.error("AI Horde image generation failed; no image returned")
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

def build_diversity_feedback(recent_visuals):
    """Tell the next art director which visual dimensions are overused."""
    profiles = []
    for row in recent_visuals or []:
        raw = row.get("visual_profile")
        if raw:
            try:
                profiles.append(json.loads(raw) if isinstance(raw, str) else raw)
            except Exception:
                pass
    if not profiles:
        return "No recent profile. Explore freely."

    dimensions = ["subject_type", "visual_mode", "narrative_mode",
                  "environment", "composition_type", "medium", "relationship_type"]
    lines = []
    for dim in dimensions:
        vals = [str(p.get(dim) or "").strip() for p in profiles if p.get(dim)]
        if vals:
            counts = {}
            for v in vals:
                counts[v] = counts.get(v, 0) + 1
            top = max(counts.items(), key=lambda x: x[1])
            if top[1] >= 2:
                lines.append(f"AVOID OVERUSING {dim}: {top[0]} used {top[1]} times recently.")
    motifs = [str(p.get("visual_motif") or "").strip() for p in profiles if p.get("visual_motif")]
    if motifs:
        lines.append("DO NOT REUSE THESE RECENT MOTIFS: " + ", ".join(motifs[:10]))
    captions = [str(row.get("image_caption") or "").strip() for row in recent_visuals if row.get("image_caption")]
    if captions:
        lines.append("Recent image descriptions exist; do not recreate the same visible scene or action.")
    # Encourage non-human scenes when the feed is too people-heavy.
    people = sum(
        1 for p in profiles
        if str(p.get("subject_type") or "").lower() in {"person", "two_people", "group", "mixed"}
    )
    if people >= max(4, int(len(profiles) * 0.65)):
        lines.append("PEOPLE ARE OVERREPRESENTED: strongly prefer object, still life, architecture, nature or landscape if semantically valid.")
    return "\n".join(lines)

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
    recent_visuals = get_recent_visuals(RECENT_DIVERSITY_WINDOW)
    diversity_feedback = build_diversity_feedback(recent_visuals)
    prompt, concept = generate_image_prompt(
        quote_text, topics, mood, diversity_feedback=diversity_feedback
    )

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

            image_bytes = None
            provider = ""
            content["image_caption"] = ""
            content["semantic_score"] = 0.0
            best_concept = content["visual_concept"]
            best_prompt = content["image_prompt"]
            diversity_feedback = build_diversity_feedback(
                get_recent_visuals(RECENT_DIVERSITY_WINDOW)
            )

            # Generate several genuinely different concepts when a provider
            # succeeds but the first concept is not desirable. We keep the
            # existing .env contract and do not require any new dependency.
            for attempt in range(1, max(1, VISUAL_GENERATION_ATTEMPTS) + 1):
                if attempt == 1:
                    prompt = content["image_prompt"]
                    concept = content["visual_concept"]
                else:
                    forced = (
                        (diversity_feedback if VISUAL_RETRY_DIVERSITY else "")
                        + "\nTHIS IS RETRY %d. Choose a substantially different subject, "
                        "environment or narrative device from the previous concept. "
                        "Do not merely rephrase it." % attempt
                    )
                    prompt, concept = await asyncio.to_thread(
                        generate_image_prompt,
                        content["quote"]["quote_text"],
                        content["topics"],
                        content["mood"],
                        forced,
                    )

                candidate, candidate_provider = await asyncio.to_thread(
                    generate_image, prompt
                )
                if candidate:
                    semantic_ok, image_caption, semantic_score = validate_generated_image_semantics(
                        candidate,
                        content["quote"]["quote_text"],
                        concept,
                    )
                    if not semantic_ok:
                        logger.warning(
                            "Visual generation attempt %s/%s rejected by semantic gate: score=%.2f",
                            attempt, VISUAL_GENERATION_ATTEMPTS, semantic_score
                        )
                        continue
                    image_bytes = candidate
                    provider = candidate_provider
                    best_concept = concept
                    best_prompt = prompt
                    content["image_caption"] = image_caption
                    content["semantic_score"] = semantic_score
                    logger.info(
                        "Visual generation attempt %s/%s accepted; semantic_score=%.2f.",
                        attempt, VISUAL_GENERATION_ATTEMPTS, semantic_score
                    )
                    break
                logger.warning("Visual generation attempt %s/%s failed.", attempt, VISUAL_GENERATION_ATTEMPTS)

            content["visual_concept"] = best_concept
            content["image_prompt"] = best_prompt

            bot = context.bot if context and getattr(context, "bot", None) else Bot(token=BOT_TOKEN)

            if not image_bytes:
                logger.error("Image generation failed after %s attempts; post was not published.", VISUAL_GENERATION_ATTEMPTS)
                if ADMIN_CHAT_ID > 0:
                    try:
                        await bot.send_message(
                            chat_id=ADMIN_CHAT_ID,
                            text="❌ Изображение не сгенерировано. Пост НЕ опубликован.",
                        )
                    except Exception:
                        pass
                return False

            caption = build_post_text(content, limit=1024)
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=image_bytes,
                caption=caption,
                parse_mode="HTML",
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
                            f"Сцена: {content['visual_concept']['archetype']}\n"
                            f"Метафора: {content['visual_concept'].get('visual_motif') or 'default'}\n"
                            f"Semantic score: {content.get('semantic_score', 0):.2f}\n"
                            f"Concept score: {content['visual_concept'].get('concept_judge_score', 0):.2f}\n\n"
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
        "Изображения: AI Horde (бесплатная volunteer-сеть, без HF-токенов)"
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
        q = choose_unique_quote()
        if q:
            topic_json = q.get("topic_json", [])
            if isinstance(topic_json, str):
                try:
                    topic_json = json.loads(topic_json)
                except Exception:
                    topic_json = []
            if not isinstance(topic_json, list):
                topic_json = []
            prompt, concept = generate_image_prompt(
                q["quote_text"],
                topic_json,
                q.get("mood") or "introspective",
            )
            image, provider = generate_image(prompt)
            return image, provider, q, concept

        prompt = (
            "An elegant, tender fine-art visual about self-acceptance, with one "
            "specific human action, soft natural light, restrained beautiful colors, "
            "no text, no logo."
        )
        image, provider = generate_image(prompt)
        return image, provider, None, None

    async def job():
        image, provider, quote, concept = await asyncio.to_thread(make_test)
        if image:
            caption = f"Готово: {provider}"
            if quote:
                caption += f"\n\n«{quote['quote_text']}»\n— {quote['author']}"
            if concept and concept.get("visual_motif"):
                caption += f"\n\nМетафора: {concept['visual_motif']}"
            await update.effective_message.reply_photo(
                photo=image,
                caption=caption[:1024],
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
            hours = 3

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

    logger.info("BeauQuot 3.1.5 Visual Engine started — temporal semantic composition + free AI Horde image generation enabled")
    logger.info("Quote source: local SQLite corpus seeded from dwyl/quotes")
    logger.info("Image provider: AI Horde free/anonymous; Hugging Face tokens are used only for semantic LLM/vision.")
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
