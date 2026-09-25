# BeauQuot 3.1.7 GigaChat

Changes:
- Semantic quote analysis -> GigaChat
- Visual concept and image prompt -> GigaChat
- GigaChat built-in text2image is the primary image generator
- AI Horde remains automatic fallback
- Hugging Face is no longer required for normal generation; optional HF BLIP captioning can still be configured

Required environment variable:
GIGACHAT_CREDENTIALS=<Authorization key from GigaChat Studio>

Restart the existing service after replacing main.py and adding the variable to the existing .env.
