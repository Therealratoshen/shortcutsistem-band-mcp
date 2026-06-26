# ShortcutSistem + Band MCP Server

**Combined MCP server for Cursor Cloud** — gives you Band platform control + ShortcutSistem tools in one HTTP connection.

```
Cursor Cloud ──MCP (HTTP)──→ This Server ──REST──→ Band AI
                                            └──→ ShortcutSistem Tools (built-in)
```

## Requirements

- **Python 3.11+** (band-sdk requires 3.11)
- Band API key from https://app.band.ai/settings/api-keys

## Tools Available

### Band Platform Tools (5)
| Tool | Description |
|------|-------------|
| `band_list_agents` | List all your Band agents |
| `band_list_my_chats` | See recent Band conversations |
| `band_send_message` | Send a message to any agent |
| `band_get_chat_history` | Read conversation history |
| `band_trigger_agent` | Trigger a specific agent to run a task |

### ShortcutSistem Tools (7)
| Tool | Description |
|------|-------------|
| `run_omni_audit(url)` | Full digital audit — SEO, AI visibility (GEO), performance, security |
| `check_homepage_seo(url)` | Quick SEO check with scorecard |
| `check_website_health(url)` | Uptime, SSL, response time, security headers |
| `write_tiktok_captions(topic, count)` | Indonesian TikTok captions for UMKM |
| `write_instagram_captions(topic, count)` | Indonesian IG captions for UMKM |
| `get_ss_video_prompt(industry, brand)` | ShortcutSistem fashion video prompts for MiniMax + BytePlus |
| `create_content_calendar(topic, weeks)` | 4-week content calendar for Indonesian social media |

## Setup

### 1. Get Your Band API Key

```
https://app.band.ai/settings/api-keys
```

### 2. Deploy to Railway (Recommended)

1. **Push to GitHub:**
   ```bash
   cd shortcutsistem-band-mcp
   git init && git add . && git commit -m "Initial commit"
   # Create repo on GitHub: https://github.com/new
   git remote add origin https://github.com/Therealratoshen/shortcutsistem-band-mcp.git
   git push -u origin main
   ```

2. **Deploy on Railway:**
   - Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
   - Connect the `shortcutsistem-band-mcp` repo
   - Add environment variable: `BAND_API_KEY` = `band_a_1781922604_x9vo02skdxefhp8JqL3jzesZKGDb5v1b`
   - Railway auto-detects Python from `pyproject.toml`
   - Wait 2-3 minutes → copy the URL (e.g. `https://shortcutsistem-band-mcp.up.railway.app`)

3. **Test the endpoint:**
   ```
   https://shortcutsistem-band-mcp.up.railway.app/mcp/
   ```
   You should see an MCP welcome message.

### 3. Connect to Cursor Cloud

Add to Cursor Cloud MCP settings (`~/.cursor/mcp_settings.json`):

```json
{
  "mcpServers": {
    "shortcutsistem-band": {
      "url": "https://shortcutsistem-band-mcp.up.railway.app/mcp/"
    }
  }
}
```

Restart Cursor. The tools will appear in the agent panel.

### 4. Local Development

```bash
cd shortcutsistem-band-mcp
cp .env.example .env
# Edit .env and add your BAND_API_KEY
uv sync
uv run python server.py
# Server runs on http://localhost:8000/mcp/
```

## Transport

Uses **streamable-http** (FastMCP) — compatible with Cursor Cloud MCP HTTP transport.

Not stdio. Not SSE. HTTP with POST + streaming responses.

## Troubleshooting

### "Module not found: band"
- Make sure `band-client-rest` is installed: `uv sync` or `pip install band-client-rest band-sdk`

### "BAND_API_KEY environment variable is required"
- Set the `BAND_API_KEY` environment variable in Railway dashboard

### Server starts but tools don't appear in Cursor
- Check Cursor Cloud MCP settings use `/mcp/` suffix on the URL
- Verify the URL is accessible from the internet (Cursor Cloud runs in browser)

### Python version error
- Ensure Railway uses **Python 3.11+** (check in Railway dashboard → Runtime)
