# BeauQuot 3.1.5 — Visual Engine

Image generation is now handled exclusively by free AI Horde. Hugging Face is reserved for semantic analysis and visual judging.

Default image model: `Flux.1-Schnell fp8 (Compact)`

Default anonymous AI Horde key: `0000000000`

The semantic pipeline remains: quote → semantic analysis → visual concept → temporal composition → AI Horde image → OCR → visual judge → Telegram.

# BeauQuot Visual Engine 3.1.4

## Что изменилось

3.1.4 не меняет модель генерации и сохраняет весь pipeline 3.1.3. Улучшение находится в semantic art direction.

### 1. Temporal semantic composition
Если семантический аналитик определяет, что цитата содержит несколько логических состояний или временную дугу, он теперь дополнительно возвращает:
- `clause_count`
- `temporal_composition`: `none`, `before_after` или `past_present_future`
- `temporal_beats`

Для `past_present_future` требуются три визуальных beat-а: прошлое, настоящее и будущее.

### 2. Одна сцена вместо коллажа
Многочастный смысл кодируется внутри одной непрерывной сцены:
- передний план / средний план / фон;
- физические следы прошлого;
- настоящее как главный фокус;
- направление/открытие/продолжение как визуальный намёк на будущее.

Запрещены split-screen, триптих, панели, инфографика и буквальная timeline-графика.

### 3. Более строгий concept judge
Judge получает temporal beats и отклоняет красивую, но статичную сцену, если цитата требует временной или причинной структуры.

### 4. Сохранена обратная совместимость
- `.env` не меняется автоматически;
- HF multi-token failover 3.1.3 сохраняется;
- FLUX.1-schnell сохраняется;
- новые настройки имеют безопасные значения по умолчанию;
- новые Python-зависимости не требуются;
- база не сбрасывается.

## Новые настройки

```env
TEMPORAL_COMPOSITION_ENABLED=1
TEMPORAL_COMPOSITION_MIN_CLAUSES=2
```

Оставлять по умолчанию. Отключение: `TEMPORAL_COMPOSITION_ENABLED=0`.
