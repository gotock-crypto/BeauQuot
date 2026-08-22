#!/usr/bin/env bash
set -euo pipefail
BASE="$(cd "$(dirname "$0")" && pwd)"
python3 -m py_compile "$BASE/main.py"
grep -q 'TEMPORAL_COMPOSITION_ENABLED' "$BASE/main.py"
grep -q 'temporal_composition' "$BASE/main.py"
grep -q 'temporal_beats' "$BASE/main.py"
grep -q 'three-panel illustration' "$BASE/main.py"
grep -q 'BeauQuot 3.1.4 Visual Engine started' "$BASE/main.py"
echo 'BeauQuot 3.1.4 static checks: OK'
