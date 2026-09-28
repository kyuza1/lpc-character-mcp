"""Builds dist/smithery.mcpb: the MCPB bundle plus each tool's inputSchema, which Smithery
requires (the official MCPB validator rejects that field, so this bundle is only for Smithery).

    python tools/smithery_bundle.py
    npx @smithery/cli@latest auth login
    npx @smithery/cli@latest mcp publish dist/smithery.mcpb -n digitalinovadora/lpc-character-mcp
"""
import asyncio
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lpc_character_mcp import server  # noqa: E402

tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
manifest = json.loads((ROOT / "mcpb" / "manifest.json").read_text(encoding="utf8"))
for tool in manifest["tools"]:
    tool["inputSchema"] = tools[tool["name"]].input_schema

out = ROOT / "dist" / "smithery.mcpb"
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("manifest.json", json.dumps(manifest, indent=2))
    for f in (ROOT / "mcpb").rglob("*"):
        if f.is_file() and f.name != "manifest.json":
            z.write(f, f.relative_to(ROOT / "mcpb").as_posix())
print(out)
