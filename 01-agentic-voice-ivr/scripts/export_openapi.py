"""Write the OpenAPI spec to docs/openapi.json. Usage: python scripts/export_openapi.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

spec = create_app(Settings(log_level="WARNING")).openapi()
(ROOT / "docs" / "openapi.json").write_text(json.dumps(spec, indent=2) + "\n")
print(f"wrote {len(spec['paths'])} paths to docs/openapi.json")
