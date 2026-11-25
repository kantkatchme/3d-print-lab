# Modelling parts with Claude and Autodesk Fusion (MCP)

Autodesk Fusion ships a **built-in MCP server**, so Claude can sketch, extrude and edit parametric designs in a running Fusion session. No plugin to build. It runs locally (`http://127.0.0.1:27182/mcp`), so your design data stays on your machine.

## Setup (about 10 minutes)

1. Update Fusion (the MCP server is a recent feature), start it, open a design.
2. Fusion: Preferences -> General -> **API** -> tick **Fusion MCP Server (runs locally on this device)**.
3. Claude Code: `claude mcp add --transport http --scope user fusion http://127.0.0.1:27182/mcp`
4. Claude Desktop (optional): Settings -> Extensions -> Autodesk Fusion.
5. First test: *"What's in the active design? Take a screenshot."*

Fusion has to be running with a document open. The server edits the current session, it doesn't launch Fusion.

## Prompting that works

- Always give **dimensions in mm**, the reference plane and orientation ("lies flat on XY").
- Ask for **user parameters** (`edge = 20 mm`), so you can tweak the part later.
- State printability: wall >= 1.2 mm, overhangs <= 45 degrees, 0.2-0.3 mm clearance on fits.
- Work in small steps and ask for a screenshot after each.
- Save first. Claude edits your open file, so work on a copy or in a scratch project.

## Pipeline

Idea -> Claude models it in Fusion -> export 3MF/STL -> slice with OrcaSlicer (the CLI works too) -> print queue -> printed.

## Lessons learned

- Tools from the Fusion MCP server don't always show up inside Claude Code sessions. Calling the server directly over HTTP works: send `initialize`, keep the returned session id, then `tools/call`.
- Scripts run through `fusion_mcp_execute` need a `run(context)` function.
- **Script output doesn't come back.** Write results to a file inside the script (e.g. `/tmp/fusion_out.json`) and read that.
- Fusion starts without an open document: create one first with `app.documents.add(...)`.
- After many days of uptime the MCP server can hang (port open, connection closed immediately). Toggling the checkbox or restarting Fusion fixes it.
- Cut features can eat geometry you wanted to keep. Check the result after every cut.
- Measurements read from photos are estimates. Print a small fit test before the real thing.

## Links

- Claude connector for Fusion: https://claude.com/connectors/autodesk-fusion
- Autodesk blog on the Fusion MCP server: https://blog.autodesk.io/fusion-mcp-server/
- Community alternative: https://github.com/faust-machines/fusion360-mcp-server
