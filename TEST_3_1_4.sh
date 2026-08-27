#!/usr/bin/env bash
set -euo pipefail
BASE="$(cd "$(dirname "$0")" && pwd)"
python3 -m py_compile "$BASE/main.py"
grep -q 'TEMPORAL_COMPOSITION_ENABLED' "$BASE/main.py"
grep -q 'temporal_composition' "$BASE/main.py"
grep -q 'temporal_beats' "$BASE/main.py"
grep -q 'three-panel illustration' "$BASE/main.py"
grep -q 'BeauQuot 3.1.5 Visual Engine started' "$BASE/main.py"
grep -q 'AIHORDE_IMAGE_MODEL' "$BASE/main.py"
grep -q 'generate_image_ai_horde' "$BASE/main.py"
echo 'BeauQuot 3.1.5 free-image static checks: OK'
