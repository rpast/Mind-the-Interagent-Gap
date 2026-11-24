#!/bin/sh
# Rebuild interagent_gap_index.html from its parts. Run from the repository root.
set -e
D=mvp/docs/dashboard_proposal
.venv/bin/python "$D/mk.py" > "$D/data.json"
{ cat "$D/head.html" "$D/body.html"; printf '<script>\nconst D = '; cat "$D/data.json"; printf ';\n'; cat "$D/app.js"; printf '</script>\n'; } > "$D/interagent_gap_index.html"
rm "$D/data.json"
