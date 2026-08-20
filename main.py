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

QUOTE_CORPUS_FILE = os.getenv("QUOTE_CORPUS_FILE", "quotes_corpus.json")
QUOTE_CORPUS_URL = os.getenv(
    "QUOTE_CORPUS_URL",
    "https://raw.githubusercontent.com/dwyl/quotes/main/quotes.json",
)

IMAGE_TIMEOUT = int(os.getenv("IMAGE_TIMEOUT", "180"))
MIN_IMAGE_BYTES = 15000
MAX_IMAGE_BYTES = 12 * 1024 * 1024

LEXICAL_DUP_THRESHOLD = float(os.getenv("LEXICAL_DUP_THRESHOLD", "0.88"))
SEMANTIC_DUP_THRESHOLD = float(os.getenv("SEMANTIC_DUP_THRESHOLD", "0.90"))
RECENT_DIVERSITY_WINDOW = int(os.getenv("RECENT_DIVERSITY_WINDOW", "8"))

HF_TOKEN = os.getenv("HF_TOKEN", os.getenv("HUGGINGFACE_TOKEN", "")).strip()
HF_TOKEN_2 = os.getenv("HF_TOKEN_2", "").strip()
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell").strip()
HF_IMAGE_PROVIDER = os.getenv("HF_IMAGE_PROVIDER", "auto").strip() or "auto"
HF_IMAGE_WIDTH = int(os.getenv("HF_IMAGE_WIDTH", "1024"))
HF_IMAGE_HEIGHT = int(os.getenv("HF_IMAGE_HEIGHT", "1280"))
HF_IMAGE_STEPS = int(os.getenv("HF_IMAGE_STEPS", "4"))
HF_IMAGE_TIMEOUT = int(os.getenv("HF_IMAGE_TIMEOUT", str(IMAGE_TIMEOUT)))
HF_LLM_MODEL = os.getenv("HF_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct").strip()
HF_LLM_PROVIDER = os.getenv("HF_LLM_PROVIDER", "auto").strip() or "auto"
HF_LLM_MAX_TOKENS = int(os.getenv("HF_LLM_MAX_TOKENS", "1400"))
HF_LLM_TEMPERATURE = float(os.getenv("HF_LLM_TEMPERATURE", "0.55"))

DEFAULT_HEADERS = {"User-Agent": "BeauQuot/2.0 (+Telegram quote bot)"}

NEGATIVE_PROMPT = (
    "text, words, letters, numbers, typography, watermark, logo, signature, "
    "caption, poster, quote card, UI, sign, label, book, newspaper, screen, "
    "phone screen, packaging, billboard, storefront, menu, document, "
    "pseudo-text, fake letters, writing, subtitles, captions, "
    "deformed hands, extra fingers, extra limbs, bad anatomy, plastic skin, "
    "waxy face, stock photo, fashion advertisement, motivational poster, "
    "oversaturated, excessive HDR, fake glow, surreal artifacts"
)

POST_LOCK = asyncio.Lock()

# ============================================================
# CONTENT RULES
# ============================================================

TOPIC_WEIGHTS = {
    "self_love": {"keywords": {"self": 2.5, "yourself": 3.0, "worth": 3.0, "worthy": 3.0, "enough": 3.0, "accept": 2.5, "acceptance": 2.5, "value": 2.0, "respect": 2.0, "confidence": 2.5}, "phrases": ["love yourself", "believe in yourself", "be yourself"]},
    "femininity": {"keywords": {"woman": 3.0, "women": 3.0, "she": 2.0, "her": 1.5, "feminine": 3.0, "womanhood": 3.0, "girl": 1.5}, "phrases": ["being a woman", "woman you are"]},
    "love": {"keywords": {"love": 2.5, "heart": 2.0, "affection": 2.5, "beloved": 2.5, "romance": 2.5, "cherish": 2.5, "intimacy": 2.0}, "phrases": ["fall in love", "love deeply", "love someone"]},
    "healing": {"keywords": {"heal": 3.0, "healing": 3.0, "recover": 2.5, "restore": 2.5, "peace": 1.5, "release": 2.0, "forgive": 2.0, "renew": 2.5}, "phrases": ["let go", "move on", "inner peace"]},
    "strength": {"keywords": {"strong": 2.5, "strength": 3.0, "courage": 3.0, "brave": 2.5, "fearless": 3.0, "resilient": 3.0, "resilience": 3.0, "power": 2.0, "rise": 1.5}, "phrases": ["stand strong", "keep going", "rise again"]},
    "growth": {"keywords": {"grow": 2.5, "growth": 3.0, "change": 2.0, "transform": 3.0, "become": 2.5, "evolve": 3.0, "journey": 2.0, "learn": 1.5}, "phrases": ["become yourself", "grow through", "new beginning"]},
    "dreams": {"keywords": {"dream": 2.5, "hope": 2.5, "future": 1.5, "vision": 2.0, "imagine": 2.0, "believe": 2.0, "possibility": 2.0}, "phrases": ["follow your dreams", "believe in your dreams"]},
    "beauty": {"keywords": {"beauty": 3.0, "beautiful": 3.0, "grace": 2.0, "elegance": 2.5, "radiant": 2.5, "shine": 2.0, "glow": 2.0}, "phrases": ["inner beauty", "true beauty"]},
    "relationships": {"keywords": {"friend": 2.0, "friendship": 2.5, "mother": 2.5, "daughter": 2.5, "sister": 2.5, "connection": 2.0, "together": 1.5}, "phrases": ["close to", "by your side"]},
    "freedom": {"keywords": {"free": 2.5, "freedom": 3.0, "independent": 3.0, "independence": 3.0, "wild": 1.5, "liberate": 2.5}, "phrases": ["be free", "live freely"]},
}

EXCLUDED_WORDS = {"war", "violence", "death", "kill", "murder", "blood", "hate", "revenge", "destroy", "enemy", "suffer", "torture", "prison", "politics", "politician", "election", "weapon", "terror"}
GENERIC_WORDS = {"success", "successfully", "winning", "winner", "motivation", "motivational", "greatness", "dream", "believe"}

MOODS = {
    "tender": {"keywords": {"soft", "gentle", "tender", "warm", "kind", "care", "grace"}, "visual": "quiet, intimate, delicate, warm natural light"},
    "empowered": {"keywords": {"strong", "strength", "power", "courage", "brave", "rise", "bold"}, "visual": "grounded, confident, cinematic contrast, controlled light"},
    "dreamy": {"keywords": {"dream", "hope", "imagine", "wonder", "magic", "star"}, "visual": "dreamlike atmosphere, airy depth, luminous twilight"},
    "romantic": {"keywords": {"love", "heart", "passion", "kiss", "embrace", "beloved", "cherish"}, "visual": "intimate, warm, emotionally restrained, golden-hour light"},
    "introspective": {"keywords": {"soul", "inner", "reflect", "truth", "self", "mindful", "become"}, "visual": "contemplative, quiet, cinematic, soft directional light"},
    "healing": {"keywords": {"heal", "recover", "grow", "rebuild", "transform", "renew", "peace"}, "visual": "restful, spacious, soft morning light, subtle renewal"},
    "peaceful": {"keywords": {"peace", "calm", "serene", "still", "quiet", "tranquil", "harmony"}, "visual": "minimal, serene, balanced composition, soft daylight"},
    "confident": {"keywords": {"enough", "worthy", "beautiful", "shine", "confident", "proud", "fearless"}, "visual": "elegant, assured, editorial, clean directional lighting"},
}

# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""
    value = html.unescape(str(value))
    return re.sub(r"\s+", " ", value).strip()


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
    return [name for name, score in ranked if score >= 1.5][:4] or ["soul"]


def analyze_mood(text):
    words = set(normalize_text(text).split())
    scores = {mood: sum(1 for w in rules["keywords"] if w in words) for mood, rules in MOODS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "introspective"

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
                published_at TEXT DEFAULT CURRENT_TIMESTAMP,
                visual_motif TEXT DEFAULT ''
            )
        """)
        columns = {r[1] for r in conn.execute("PRAGMA table_info(visual_history)").fetchall()}
        if "visual_motif" not in columns:
            conn.execute("ALTER TABLE visual_history ADD COLUMN visual_motif TEXT DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quotes_hash ON quotes(quote_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_published_hash ON published_quotes(quote_hash)")
        conn.commit()


def upsert_quote(text, author, source="", source_url="", quality_score=0, topics=None, mood=""):
    text, author = clean_text(text), clean_text(author) or "Unknown"
    if not text:
        return None
    h = quote_hash(text, author)
    with get_db() as conn:
        conn.execute("""
            INSERT INTO quotes (quote_text, author, normalized_text, quote_hash, source, source_url, topic_json, mood, quality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(quote_hash) DO UPDATE SET
                source = CASE WHEN quotes.source = '' THEN excluded.source ELSE quotes.source END,
                source_url = CASE WHEN quotes.source_url = '' THEN excluded.source_url ELSE quotes.source_url END,
                quality_score = MAX(quotes.quality_score, excluded.quality_score)
        """, (text, author, normalize_text(text), h, source, source_url, json.dumps(topics or [], ensure_ascii=False), mood, float(quality_score)))
        conn.commit()
        row = conn.execute("SELECT * FROM quotes WHERE quote_hash=?", (h,)).fetchone()
        return dict(row) if row else None


def is_published(text, author):
    h = quote_hash(text, author)
    with get_db() as conn:
        return conn.execute("SELECT 1 FROM published_quotes WHERE quote_hash=?", (h,)).fetchone() is not None


def get_recent_visuals(limit=RECENT_DIVERSITY_WINDOW):
    with get_db() as conn:
        rows = conn.execute("SELECT archetype, theme, mood, visual_motif FROM visual_history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def mark_published(content, image_bytes=None, provider=""):
    q = content["quote"]
    h = quote_hash(q["quote_text"], q["author"])
    visual = content.get("visual_concept") or {}
    with get_db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO published_quotes
                (quote_id, quote_hash, quote_text, author, image_hash, image_provider, visual_archetype, prompt_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (q.get("id"), h, q["quote_text"], q["author"], image_hash(image_bytes), provider, visual.get("visual_motif", ""), hashlib.sha256(content["image_prompt"].encode("utf-8")).hexdigest()))
        themes = content.get("topics") or ["soul"]
        conn.execute("UPDATE quotes SET used_count = used_count + 1, last_used_at = ? WHERE quote_hash = ?", (datetime.now(timezone.utc).isoformat(), h))
        conn.execute("INSERT INTO visual_history(archetype, theme, mood, visual_motif) VALUES (?, ?, ?, ?)", (visual.get("visual_motif", ""), themes[0], content.get("mood", "introspective"), visual.get("visual_motif", "")))
        conn.commit()

# ============================================================
# CORPUS / DEDUP
# ============================================================

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
        r = requests.get(QUOTE_CORPUS_URL, headers=DEFAULT_HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            with open(QUOTE_CORPUS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return data
    except Exception as exc:
        logging.getLogger("beauquot").warning("Quote corpus download failed: %s", exc)
    return []


def quality_score(text, author):
    words = normalize_text(text).split()
    if len(words) < 6 or len(words) > 70:
        return -100.0
    if any(w in normalize_text(text).split() for w in EXCLUDED_WORDS):
        return -100.0
    score = 0.0
    score += 3.0 if 10 <= len(words) <= 42 else 1.0 if len(words) <= 55 else 0.0
    if len(set(words)) / max(len(words), 1) > 0.55:
        score += 1.5
    topics = score_topics(text)
    score += min(sum(TOPIC_WEIGHTS.get(t, {}).get("keywords", {}).get(w, 0) for t in topics for w in words), 8.0)
    if author and author.lower() not in {"unknown", "anonymous"}:
        score += 1.0
    score -= sum(1 for w in words if w in GENERIC_WORDS) * 0.4
    if text.endswith((".", "!", "?")):
        score += 0.5
    return round(score, 3)


def seed_database():
    corpus = download_quote_corpus()
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
        score = quality_score(text, author)
        if score < 3.0:
            continue
        upsert_quote(text, author, source="dwyl/quotes", source_url=source_url, quality_score=score, topics=score_topics(text), mood=analyze_mood(text))


def get_candidate_rows(limit=500):
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM quotes WHERE quality_score >= 3 ORDER BY quality_score DESC, used_count ASC, RANDOM() LIMIT ?", (limit,)).fetchall()]


def get_published_rows(limit=500):
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT quote_text, author FROM published_quotes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


def choose_unique_quote():
    candidates, published = get_candidate_rows(), get_published_rows()
    for q in candidates:
        if is_published(q["quote_text"], q["author"]):
            continue
        if any(lexical_similarity(q["quote_text"], p["quote_text"]) >= LEXICAL_DUP_THRESHOLD for p in published):
            continue
        return q
    return None

# ============================================================
# HF LLM ART DIRECTOR
# ============================================================

def _hf_clients():
    try:
        from huggingface_hub import InferenceClient
    except Exception as exc:
        logging.getLogger("beauquot").error("huggingface_hub unavailable: %s", exc)
        return []
    tokens = []
    if HF_TOKEN:
        tokens.append((HF_TOKEN, "HF_TOKEN"))
    if HF_TOKEN_2 and HF_TOKEN_2 != HF_TOKEN:
        tokens.append((HF_TOKEN_2, "HF_TOKEN_2"))
    return [(InferenceClient(provider=HF_LLM_PROVIDER, api_key=token), name) for token, name in tokens]


def _extract_json_object(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None


def generate_llm_visual_concept(quote_text, themes, mood, recent_visuals=None):
    recent_visuals = recent_visuals or []
    recent = ", ".join(str(r.get("visual_motif")) for r in recent_visuals if r.get("visual_motif")) or "none"
    system = """You are a senior art director for a premium inspirational quote channel. Turn one quote into a visual concept for an image model.
Return ONLY valid JSON. Do not include markdown or commentary.
The image should usually be realistic fine-art photography or cinematic editorial realism: natural people, natural skin, believable light, elegant composition, soft refined color grading, subtle film grain. You may choose another medium only when it genuinely fits the quote, but do not default to illustration.
Never equate love with romance unless the quote clearly implies romantic love. Never use a generic woman-at-window, doorway-to-sunlight, mountain-horizon, or kiss-as-love cliché unless uniquely demanded by the quote.
The scene must communicate the idea of the quote through a believable human situation, interaction, object, place, or subtle visual metaphor.
Avoid text, logos, watermarks, fake lettering, captions, posters, screens, books, labels, and brand marks in the generated image.
"""
    user = f"""QUOTE: {quote_text}
THEMES: {', '.join(themes or [])}
MOOD: {mood}
RECENT MOTIFS TO AVOID REPEATING: {recent}

Return JSON with exactly these fields:
core_meaning: deeper meaning in plain language
emotional_tension: central feeling/conflict/dilemma
human_change: what a person chooses, does, accepts, releases, repairs, builds, or realizes
relationship_type: one_person, friendship, family, romance, strangers, community, self, or none
scene: concrete believable scene
action: concrete visible action
visual_metaphor: subtle metaphor if useful; otherwise none
medium: preferred visual medium
composition: framing and camera language
lighting: realistic light description
palette: restrained color direction
mood: emotional atmosphere
visual_motif: short reusable motif id
avoid: specific visual clichés to avoid
image_prompt: complete English prompt for the image model

Important: the image_prompt must describe the scene itself and must NOT contain the original quote text."""

    for client, token_name in _hf_clients():
        try:
            completion = client.chat.completions.create(
                model=HF_LLM_MODEL,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=HF_LLM_MAX_TOKENS,
                temperature=HF_LLM_TEMPERATURE,
            )
            text = completion.choices[0].message.content or ""
            data = _extract_json_object(text)
            if not isinstance(data, dict):
                raise ValueError("LLM response is not a JSON object")
            required = ("core_meaning", "emotional_tension", "human_change", "scene", "action", "image_prompt")
            if any(not str(data.get(k, "")).strip() for k in required):
                raise ValueError("LLM concept missing required fields")
            relationship = str(data.get("relationship_type") or "none").strip().lower()
            if relationship not in {"one_person", "friendship", "family", "romance", "strangers", "community", "self", "none"}:
                relationship = "none"
            data["relationship_type"] = relationship
            data["llm_provider"] = token_name
            data["llm_model"] = HF_LLM_MODEL
            return data
        except Exception as exc:
            logging.getLogger("beauquot").warning("HF LLM %s failed: %s", token_name, str(exc)[:300])
    return None


def fallback_visual_concept(quote_text, themes, mood):
    theme = themes[0] if themes else "soul"
    mood_desc = MOODS.get(mood, MOODS["introspective"])["visual"]
    return {
        "core_meaning": f"A nuanced visual interpretation of {theme}.",
        "emotional_tension": mood_desc,
        "human_change": "a quiet, visible emotional shift",
        "relationship_type": "one_person",
        "scene": "a refined, realistic everyday scene that suggests emotional meaning without literal symbolism",
        "action": "a subtle natural action with clear emotional purpose",
        "visual_metaphor": "none",
        "medium": "realistic fine-art photography",
        "composition": "cinematic editorial framing with generous negative space",
        "lighting": "soft natural daylight with gentle directional shadows",
        "palette": "warm neutrals, soft cream, muted sage, blush and blue",
        "mood": mood_desc,
        "visual_motif": f"fallback_{theme}",
        "avoid": "generic inspirational poster, doorway cliché, sunrise cliché, stock photo",
        "image_prompt": "Elegant realistic fine-art photograph, believable everyday human scene, subtle emotional storytelling, natural skin, authentic materials, soft natural light, restrained pastel-neutral palette, cinematic composition, no text or logos.",
        "llm_provider": "fallback",
        "llm_model": "none",
    }


def build_visual_concept(quote_text, themes, mood):
    concept = generate_llm_visual_concept(quote_text, themes, mood, get_recent_visuals())
    return concept or fallback_visual_concept(quote_text, themes, mood)


def generate_image_prompt(quote_text, themes, mood):
    concept = build_visual_concept(quote_text, themes, mood)
    style = (
        "realistic fine-art photography, cinematic editorial realism, natural skin texture, "
        "believable anatomy, physically plausible lighting, authentic materials, subtle film grain, "
        "soft elegant color grading, gentle pastel-neutral palette, refined premium aesthetic, "
        "emotionally restrained, photorealistic but poetic"
    )
    prompt = " ".join([
        concept.get("image_prompt", ""),
        f"Core meaning: {concept.get('core_meaning', '')}.",
        f"Emotional tension: {concept.get('emotional_tension', '')}.",
        f"Human change/action: {concept.get('human_change', '')}.",
        f"Relationship type: {concept.get('relationship_type', 'none')}.",
        f"Scene: {concept.get('scene', '')}.",
        f"Visible action: {concept.get('action', '')}.",
        f"Visual metaphor: {concept.get('visual_metaphor', 'none')}.",
        f"Composition: {concept.get('composition', '')}.",
        f"Lighting: {concept.get('lighting', '')}.",
        f"Palette: {concept.get('palette', '')}.",
        f"Style: {style}.",
        f"Avoid: {concept.get('avoid', '')}; text, words, letters, numbers, logos, signatures, watermarks, pseudo-text, posters, labels, screens, books, packaging, signs, captions, UI, branding.",
    ])
    return re.sub(r"\s+", " ", prompt)[:6000], concept

# ============================================================
# IMAGE GENERATION
# ============================================================

def is_valid_image(data):
    if not isinstance(data, bytes) or len(data) < MIN_IMAGE_BYTES or len(data) > MAX_IMAGE_BYTES:
        return False
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF"


def _hf_image_clients():
    try:
        from huggingface_hub import InferenceClient
    except Exception:
        return []
    clients = []
    if HF_TOKEN:
        clients.append((InferenceClient(provider=HF_IMAGE_PROVIDER, api_key=HF_TOKEN), "HF_TOKEN"))
    if HF_TOKEN_2 and HF_TOKEN_2 != HF_TOKEN:
        clients.append((InferenceClient(provider=HF_IMAGE_PROVIDER, api_key=HF_TOKEN_2), "HF_TOKEN_2"))
    return clients


def generate_image_huggingface(prompt):
    for client, token_name in _hf_image_clients():
        try:
            image = client.text_to_image(
                prompt,
                model=HF_IMAGE_MODEL,
                width=HF_IMAGE_WIDTH,
                height=HF_IMAGE_HEIGHT,
                num_inference_steps=HF_IMAGE_STEPS,
            )
            from io import BytesIO
            buf = BytesIO()
            image.save(buf, format="PNG")
            data = buf.getvalue()
            if is_valid_image(data):
                return data, f"HuggingFace:{HF_IMAGE_MODEL}", token_name
        except Exception as exc:
            logging.getLogger("beauquot").warning("HF image %s failed: %s", token_name, str(exc)[:300])
    return None, "", ""


def image_has_obvious_text(data):
    try:
        import pytesseract
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(data)).convert("RGB")
        info = pytesseract.image_to_data(img, config="--psm 11", output_type=pytesseract.Output.DICT)
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
        if hits:
            logging.getLogger("beauquot").info("OCR text candidate(s) detected: total=%s", hits)
        return hits >= 1
    except Exception:
        return False


def generate_image(prompt):
    image, provider, token_name = generate_image_huggingface(prompt)
    if image and not image_has_obvious_text(image):
        return image, provider
    return None, ""

# ============================================================
# TRANSLATION / POST
# ============================================================

_translation_cache = {}


def translate_text(text, dest_lang="ru"):
    if not text or re.search(r"[а-яА-ЯёЁ]", text):
        return text
    key = hashlib.md5(f"{text}|{dest_lang}".encode()).hexdigest()
    if key in _translation_cache:
        return _translation_cache[key]
    try:
        r = requests.get("https://translate.googleapis.com/translate_a/single", params={"client": "gtx", "sl": "auto", "tl": dest_lang, "dt": "t", "q": text}, headers=DEFAULT_HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        result = clean_text(" ".join(p[0] for p in data[0] if isinstance(p, list) and p and p[0]))
        if result:
            _translation_cache[key] = result
            return result
    except Exception:
        pass
    return text


def generate_hashtags(quote_text, author):
    tags = ["женскиемысли", "цитатыдлядуши"]
    topics = score_topics(quote_text)
    mapping = {"self_love": "самоценность", "love": "любовь", "healing": "исцеление", "strength": "сила", "growth": "развитие", "dreams": "мечты", "beauty": "красота", "relationships": "отношения", "freedom": "свобода"}
    for t in topics[:2]:
        if t in mapping:
            tags.append(mapping[t])
    return list(dict.fromkeys(tags))[:4]


def fetch_post_content():
    quote = choose_unique_quote()
    if not quote:
        return None
    quote_text, author = quote["quote_text"], quote["author"]
    topics = json.loads(quote.get("topic_json") or "[]")
    mood = quote.get("mood") or analyze_mood(quote_text)
    translated_quote = translate_text(quote_text, "ru")
    translated_author = translate_text(author, "ru")
    prompt, concept = generate_image_prompt(quote_text, topics, mood)
    return {"quote": quote, "translated_quote": translated_quote, "translated_author": translated_author, "topics": topics, "mood": mood, "visual_concept": concept, "image_prompt": prompt, "hashtags": generate_hashtags(quote_text, translated_author)}


def build_post_text(content, limit=1024):
    q = html.escape(content["translated_quote"])
    a = html.escape(content["translated_author"])
    hashtags = "  ".join(f"#{x}" for x in content["hashtags"][:4])
    channel_username = CHANNEL_ID.lstrip("@")
    link = f'<a href="https://t.me/{channel_username}">Красивые Цитаты</a>'
    text = f"✨ «{q}» (c) {a}\n\n{hashtags}\n\n{link}"
    return text if len(text) <= limit else text[:limit]

# ============================================================
# POSTING
# ============================================================

async def create_and_send_post(context=None):
    if POST_LOCK.locked():
        return False
    async with POST_LOCK:
        try:
            content = await asyncio.to_thread(fetch_post_content)
            if not content:
                return False
            image_bytes, provider = await asyncio.to_thread(generate_image, content["image_prompt"])
            if not image_bytes:
                logging.getLogger("beauquot").error("Image generation failed after HF_TOKEN -> HF_TOKEN_2 failover; post not published.")
                return False
            bot = context.bot if context and getattr(context, "bot", None) else Bot(token=BOT_TOKEN)
            await bot.send_photo(chat_id=CHANNEL_ID, photo=image_bytes, caption=build_post_text(content), parse_mode="HTML")
            mark_published(content, image_bytes=image_bytes, provider=provider)
            return True
        except Exception as exc:
            logging.getLogger("beauquot").exception("Post creation error: %s", exc)
            return False

# ============================================================
# SCHEDULER / ADMIN
# ============================================================

class BotConfig:
    def __init__(self):
        self.interval_hours = 3
        self.auto_posting = True
        self.last_post_time = None
    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"interval_hours": self.interval_hours, "auto_posting": self.auto_posting, "last_post_time": self.last_post_time.isoformat() if self.last_post_time else None}, f, ensure_ascii=False, indent=2)
    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.interval_hours = int(data.get("interval_hours", 3))
            self.auto_posting = bool(data.get("auto_posting", True))
            self.last_post_time = datetime.fromisoformat(data["last_post_time"]) if data.get("last_post_time") else None
        except Exception:
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
    except Exception:
        pass


def save_admin_id(user_id):
    global ADMIN_CHAT_ID
    ADMIN_CHAT_ID = int(user_id)
    try:
        with open(ADMIN_ID_FILE, "w", encoding="utf-8") as f:
            f.write(str(ADMIN_CHAT_ID))
    except Exception:
        pass


def is_admin(update: Update):
    return bool(update.effective_user and update.effective_user.id == ADMIN_CHAT_ID)


def admin_keyboard():
    return ReplyKeyboardMarkup([["🚀 Отправить пост", "📊 Статистика"], ["⚙️ Автопостинг", "⏰ Интервал"], ["🧪 Тест картинки", "🔎 Тест уникальности"]], resize_keyboard=True)


def status_text():
    return f"🤖 BeauQuot\n\nАвтопостинг: {'✅' if config.auto_posting else '❌'}\nИнтервал: {config.interval_hours} ч.\nИзображения: Hugging Face → HF_TOKEN_2 failover"

async def scheduled_post_job(context):
    await create_and_send_post(context)


def configure_job_queue(application):
    queue = application.job_queue
    if not queue:
        return
    for job in queue.get_jobs_by_name("auto_post"):
        job.schedule_removal()
    if config.auto_posting:
        delay = 20 if not config.last_post_time else max(60, (config.last_post_time + timedelta(hours=config.interval_hours) - datetime.now()).total_seconds())
        queue.run_repeating(scheduled_post_job, interval=timedelta(hours=config.interval_hours), first=delay, name="auto_post")

async def post_init(application):
    init_db()
    await asyncio.to_thread(seed_database)
    config.load_config()
    configure_job_queue(application)

async def start_command(update, context):
    if ADMIN_CHAT_ID <= 0:
        save_admin_id(update.effective_user.id)
    if not is_admin(update):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text(status_text(), reply_markup=admin_keyboard())

async def send_post_now(update, context):
    await update.message.reply_text("⏳ Создаю пост…")
    ok = await create_and_send_post(context)
    await update.message.reply_text("✅ Пост опубликован." if ok else "❌ Не удалось создать/опубликовать пост.", reply_markup=admin_keyboard())

async def show_statistics(update, context):
    await update.message.reply_text(status_text(), reply_markup=admin_keyboard())

async def toggle_autoposting(update, context):
    config.auto_posting = not config.auto_posting
    config.save_config()
    configure_job_queue(context.application)
    await update.message.reply_text(status_text(), reply_markup=admin_keyboard())

async def test_image(update, context):
    await update.message.reply_text("⏳ Тестирую генерацию на реальной цитате…")
    content = await asyncio.to_thread(fetch_post_content)
    if not content:
        await update.effective_message.reply_text("❌ Не удалось выбрать цитату.")
        return
    image, provider = await asyncio.to_thread(generate_image, content["image_prompt"])
    if not image:
        await update.effective_message.reply_text("❌ HF не вернул валидное изображение.")
        return
    await update.effective_message.reply_photo(photo=image, caption=f"Готово: {provider}\n\n«{content['quote']['quote_text']}» — {content['quote']['author']}")

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
    elif text == "🧪 Тест картинки":
        await test_image(update, context)
    else:
        await update.message.reply_text(status_text(), reply_markup=admin_keyboard())


def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    if not HF_TOKEN and not HF_TOKEN_2:
        raise RuntimeError("HF_TOKEN or HF_TOKEN_2 is required")
    init_db()
    load_admin_id()
    config.load_config()
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_message))
    logging.getLogger("beauquot").info("BeauQuot started")
    logging.getLogger("beauquot").info("Image provider: Hugging Face only; HF_TOKEN -> HF_TOKEN_2 failover.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
