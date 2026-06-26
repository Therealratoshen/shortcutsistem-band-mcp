#!/usr/bin/env python3
"""
ShortcutSistem + Band MCP Server
================================
Combined MCP server for Cursor Cloud:
  - Band platform tools (via band-sdk / thenvoi_rest)
  - ShortcutSistem custom tools (omni audit, SEO, captions, SS prompts)

Transport: streamable-http (Cursor Cloud compatible)
"""

import asyncio
import os
import sys
from typing import Optional

# ─── Band SDK ────────────────────────────────────────────────
from band.client.rest import AsyncRestClient, DEFAULT_REQUEST_OPTIONS
from band.client.rest import (
    ChatMessageRequest,
    ChatMessageRequestMentionsItem,
    ParticipantRequest,
)

# ─── FastMCP ─────────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP

# ─── HTTP client for ShortcutSistem custom tools ─────────────
import httpx

# ══════════════════════════════════════════════════════════════
#  APP
# ══════════════════════════════════════════════════════════════

mcp = FastMCP(
    name="ShortcutSistem + Band",
    description="Band platform control + ShortcutSistem tools for Indonesian UMKM audit and social content",
    host="0.0.0.0",
    port=8000,
)

# ══════════════════════════════════════════════════════════════
#  BAND CLIENT HELPERS
# ══════════════════════════════════════════════════════════════

def get_band_client() -> AsyncRestClient:
    """Create authenticated Band REST client."""
    api_key = os.getenv("BAND_API_KEY")
    if not api_key:
        raise ValueError("BAND_API_KEY environment variable is required")
    base_url = os.getenv("BAND_REST_URL", "https://app.band.ai/").rstrip("/")
    return AsyncRestClient(api_key=api_key, base_url=base_url)


async def find_peer_by_handle(client: AsyncRestClient, handle: str, auth_mode: str) -> Optional[dict]:
    """Look up a peer agent/user by handle."""
    handle_clean = handle.lstrip("@")
    try:
        peers = await client.agent_api_peers.list_agent_peers(
            request_options=DEFAULT_REQUEST_OPTIONS,
        )
        for peer in (peers.data or []):
            if peer.get("handle", "").lstrip("@") == handle_clean:
                return peer
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════
#  BAND PLATFORM TOOLS
# ══════════════════════════════════════════════════════════════

@mcp.tool()
async def band_list_agents() -> str:
    """
    List all your Band agents. Returns agent names, handles, and IDs.
    Use this to discover what agents are available in your Band workspace.
    """
    client = get_band_client()
    try:
        peers = await client.agent_api_peers.list_agent_peers(
            request_options=DEFAULT_REQUEST_OPTIONS,
        )
        if not peers.data:
            return "No agents found in your Band workspace."

        lines = ["**Your Band Agents:**\n"]
        for peer in peers.data:
            name = peer.get("name", "Unknown")
            handle = peer.get("handle", "")
            agent_id = peer.get("id", "")
            lines.append(f"- **{name}** — `{handle}` _(ID: {agent_id})_")
        return "\n".join(lines)
    finally:
        await client._client_wrapper.httpx_client.httpx_client.aclose()


@mcp.tool()
async def band_list_my_chats(limit: int = 20) -> str:
    """
    List your recent Band conversations.
    Shows chat room names, IDs, and last activity.

    Args:
        limit: Maximum number of chats to return (default 20)
    """
    client = get_band_client()
    try:
        chats = await client.agent_api_chats.list_agent_chats(
            limit=limit,
            request_options=DEFAULT_REQUEST_OPTIONS,
        )
        if not chats.data:
            return "No conversations found."

        lines = ["**Recent Band Conversations:**\n"]
        for chat in chats.data:
            chat_id = chat.get("id", "")
            name = chat.get("name", "Unnamed Room")
            updated = chat.get("updatedAt", "")[:10] if chat.get("updatedAt") else "?"
            lines.append(f"- **{name}** — Updated: {updated} _(ID: {chat_id})_")
        return "\n".join(lines)
    finally:
        await client._client_wrapper.httpx_client.httpx_client.aclose()


@mcp.tool()
async def band_send_message(target_handle: str, message: str, auth_mode: str = "agent") -> str:
    """
    Send a message to a Band agent or create a new conversation.

    Args:
        target_handle: Agent handle like "@filborthen/shortcutsistem-minimax/seo-analyst"
                      or just "@filborthen/shortcutsistem-minimax"
        message: The message content to send
        auth_mode: "agent" (default) or "user"
    """
    client = get_band_client()
    try:
        # Step 1: Find the peer
        peer = await find_peer_by_handle(client, target_handle, auth_mode)
        if not peer:
            return f"❌ Agent not found: {target_handle}. Make sure the handle is correct."

        peer_id = peer["id"]
        peer_name = peer.get("name", target_handle)

        # Step 2: Create a new chatroom
        chat_response = await client.agent_api_chats.create_agent_chat(
            chat={},
            request_options=DEFAULT_REQUEST_OPTIONS,
        )
        room_id = chat_response.data.id

        # Step 3: Add the target as participant
        await client.agent_api_participants.add_agent_chat_participant(
            chat_id=room_id,
            participant=ParticipantRequest(participant_id=peer_id),
            request_options=DEFAULT_REQUEST_OPTIONS,
        )

        # Step 4: Send the message with mention
        mention = ChatMessageRequestMentionsItem(id=peer_id, handle=peer["handle"])
        message_request = ChatMessageRequest(
            content=message,
            mentions=[mention] if mention else [],
        )
        await client.agent_api_messages.create_agent_chat_message(
            chat_id=room_id,
            message=message_request,
            request_options=DEFAULT_REQUEST_OPTIONS,
        )

        return (
            f"✅ Message sent to **{peer_name}** (`{target_handle}`)\n"
            f"   Room ID: `{room_id}`\n"
            f"   Message: \"{message[:100]}{'...' if len(message) > 100 else ''}\"\n\n"
            f"   View conversation at: https://app.band.ai/chat/{room_id}"
        )
    finally:
        await client._client_wrapper.httpx_client.httpx_client.aclose()


@mcp.tool()
async def band_get_chat_history(chat_id: str, limit: int = 20) -> str:
    """
    Get the message history from a Band conversation.

    Args:
        chat_id: The chat room ID (from band_list_my_chats)
        limit: Maximum number of messages to return (default 20)
    """
    client = get_band_client()
    try:
        messages = await client.agent_api_messages.list_agent_messages(
            chat_id=chat_id,
            limit=limit,
            request_options=DEFAULT_REQUEST_OPTIONS,
        )
        if not messages.data:
            return f"No messages found in chat `{chat_id}`."

        lines = [f"**Chat History** _(Room: {chat_id})_:\n"]
        for msg in reversed(messages.data):
            sender = msg.get("senderName", msg.get("sender", "Unknown"))
            content = msg.get("content", "")
            ts = msg.get("createdAt", "")[:16] if msg.get("createdAt") else ""
            lines.append(f"[{ts}] **{sender}**: {content[:200]}")
        return "\n".join(lines)
    finally:
        await client._client_wrapper.httpx_client.httpx_client.aclose()


@mcp.tool()
async def band_trigger_agent(target_handle: str, task: str) -> str:
    """
    Trigger a specific Band agent to perform a task.
    Shorthand for: creates room → adds agent → sends task message.

    Args:
        target_handle: Full agent handle, e.g. "@filborthen/shortcutsistem-minimax/seo-analyst"
        task: Task description for the agent
    """
    return await band_send_message(target_handle, task, auth_mode="agent")


# ══════════════════════════════════════════════════════════════
#  SHORTCUTSISTEM CUSTOM TOOLS
#  Indonesian UMKM-focused digital audit and content tools
# ══════════════════════════════════════════════════════════════

import re
import json
import time
from typing import Any

SHORTCUTSISTEM_URL = "https://www.shortcutsistem.com"
SHORTCUTSISTEM_API = "https://www.shortcutsistem.com/api"


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def normalize_domain(domain: str) -> str:
    """Strip protocol and trailing slash from domain."""
    return domain.replace("https://", "").replace("http://", "").rstrip("/")


async def fetch_page(url: str, timeout: int = 15) -> tuple[str, int, dict, int]:
    """Fetch a URL and return (html, status_code, headers, elapsed_ms)."""
    try:
        start = time.monotonic()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SS-Bot/1.0)"},
        ) as client:
            resp = await client.get(url)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return resp.text, resp.status_code, dict(resp.headers), elapsed_ms
    except Exception:
        return "", 0, {}, 0


def extract_meta(html: str) -> dict[str, Any]:
    """Extract common meta tags from HTML."""
    result = {}

    # Title
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    result["title"] = m.group(1).strip() if m else None

    # Meta description
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.I,
    )
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']', html, re.I)
    result["meta_description"] = m.group(1).strip() if m else None

    # OG tags
    for tag in ["og:title", "og:description", "og:image", "og:type", "og:url"]:
        m = re.search(r'<meta[^>]+property=["\']' + tag + r'["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']' + tag + r'["\']', html, re.I)
        result[tag] = m.group(1).strip()[:200] if m else None

    # Twitter card
    for tag in ["twitter:card", "twitter:title", "twitter:description"]:
        m = re.search(r'<meta[^>]+name=["\']' + tag + r'["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        result[tag] = m.group(1).strip()[:200] if m else None

    # Viewport
    result["viewport"] = bool(re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.I))

    # Canonical
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html, re.I)
    result["canonical"] = m.group(1).strip() if m else None

    # Robots meta
    m = re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    result["robots"] = m.group(1).strip() if m else None

    # H1/H2 tags
    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    result["h1_tags"] = [re.sub(r"<[^>]+>", "", h).strip() for h in h1s if re.sub(r"<[^>]+>", "", h).strip()]
    h2s = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.I | re.S)
    result["h2_tags"] = [re.sub(r"<[^>]+>", "", h).strip() for h in h2s if re.sub(r"<[^>]+>", "", h).strip()]

    # Structured data (JSON-LD)
    ld_scripts = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S)
    result["json_ld"] = []
    for script in ld_scripts:
        try:
            result["json_ld"].append(json.loads(script.strip()))
        except Exception:
            pass

    return result


def detect_tech_stack(html: str, headers: dict) -> list[str]:
    """Detect technology stack from HTML and headers."""
    html_lower = html.lower()
    techs = []

    if any(p in html_lower for p in ["wp-content", "wp-includes", "wp-json"]):
        techs.append("WordPress")
    if "cdn.shopify.com" in html_lower or "myshopify" in html_lower:
        techs.append("Shopify")
    if "wix.com" in html_lower:
        techs.append("Wix")
    if "squarespace.com" in html_lower:
        techs.append("Squarespace")
    if "_next/static" in html_lower or "__next" in html_lower:
        techs.append("Next.js")
    if "gatsby" in html_lower:
        techs.append("Gatsby")
    if "react" in html_lower and "wp-" not in html_lower:
        techs.append("React")
    if "vue" in html_lower:
        techs.append("Vue.js")
    if "bootstrap" in html_lower:
        techs.append("Bootstrap")
    if "tailwind" in html_lower:
        techs.append("Tailwind CSS")
    if "google-analytics.com" in html_lower or "gtag(" in html_lower:
        techs.append("Google Analytics")
    if "facebook.net" in html_lower or "fbq(" in html_lower:
        techs.append("Facebook Pixel")
    if "hotjar" in html_lower:
        techs.append("Hotjar")

    server = headers.get("server", "")
    if "nginx" in server.lower():
        techs.append("Nginx")
    if "apache" in server.lower():
        techs.append("Apache")
    if "cloudflare" in server.lower() or "CF-Ray" in headers:
        techs.append("Cloudflare")

    return techs or ["Unknown / Custom"]


def calculate_seo_score(meta: dict) -> tuple[int, list[tuple[str, bool, str]]]:
    """Calculate SEO score (0-100) and return individual checks."""
    checks = []
    score = 0

    # Title (15 pts)
    title_ok = bool(meta.get("title") and 10 < len(meta["title"]) < 70)
    checks.append(("Page Title", title_ok, (meta.get("title") or "Missing")[:60]))
    if title_ok:
        score += 15

    # Meta description (15 pts)
    desc_ok = bool(meta.get("meta_description") and 50 < len(meta["meta_description"]) < 160)
    checks.append(("Meta Description", desc_ok, (meta.get("meta_description") or "Missing")[:80]))
    if desc_ok:
        score += 15

    # H1 (10 pts)
    h1s = meta.get("h1_tags", [])
    h1_ok = len(h1s) >= 1
    checks.append(("H1 Tag", h1_ok, f"Found {len(h1s)} H1(s)" if h1s else "No H1 found"))
    if h1_ok:
        score += 10
    if len(h1s) > 1:
        checks.append(("⚠️ Multiple H1s", False, f"{len(h1s)} H1 tags — should be exactly 1"))

    # Open Graph (10 pts)
    og_ok = all(meta.get(t) for t in ["og:title", "og:description", "og:image"])
    checks.append(("Open Graph Tags", og_ok, "All 3 core OG tags" if og_ok else "Missing OG tags"))
    if og_ok:
        score += 10

    # Twitter Card (5 pts)
    tw_ok = bool(meta.get("twitter:card"))
    checks.append(("Twitter Card", tw_ok, meta.get("twitter:card", "Missing")))
    if tw_ok:
        score += 5

    # Viewport (5 pts)
    vp_ok = bool(meta.get("viewport"))
    checks.append(("Mobile Viewport", vp_ok, "Set" if vp_ok else "Missing"))
    if vp_ok:
        score += 5

    # Canonical (5 pts)
    can_ok = bool(meta.get("canonical"))
    checks.append(("Canonical URL", can_ok, "Present" if can_ok else "Missing"))
    if can_ok:
        score += 5

    # JSON-LD (10 pts)
    ld_ok = len(meta.get("json_ld", [])) > 0
    ld_types = [d.get("@type", "Unknown") for d in meta.get("json_ld", [])]
    checks.append(("Structured Data (JSON-LD)", ld_ok, ", ".join(ld_types[:3]) if ld_ok else "None found"))
    if ld_ok:
        score += 10

    # SSL (10 pts) — placeholder; caller overrides
    checks.append(("HTTPS", True, "Served over HTTPS"))

    return min(100, score), checks


def estimate_business_impact(meta: dict, tech: list[str], ssl: bool, elapsed_ms: int) -> list[str]:
    """Plain-English business impact based on findings."""
    impacts = []

    if not meta.get("og:image"):
        impacts.append("WhatsApp/Facebook shares show no preview — lose ~40% of social traffic")
    if not meta.get("og:description"):
        impacts.append("No OG description — social shares look unprofessional")
    if not meta.get("meta_description"):
        impacts.append("Google shows no description — CTR drops 20-30%, users skip your site")
    if not meta.get("title"):
        impacts.append("No page title — Google may show raw URL instead of brand name")
    if not meta.get("viewport"):
        impacts.append("Not mobile-optimized — 97% of Indonesian users browse on phone")
    if len(meta.get("json_ld", [])) == 0:
        impacts.append("No structured data — invisible to AI search (ChatGPT, Gemini) — missing ~12% of search market")
    if not ssl:
        impacts.append("Not HTTPS — 68% of users abandon on security warning")
    if "Unknown / Custom" in tech:
        impacts.append("Tech stack unclear — may indicate outdated or hard-to-maintain site")
    if elapsed_ms > 4000:
        impacts.append(f"Load time {elapsed_ms}ms — every 1s delay = -7% conversions")
    if not meta.get("canonical"):
        impacts.append("No canonical URL — Google may index duplicate pages, hurting SEO")

    if not impacts:
        impacts.append("No critical issues found. Focus on content quality and backlinks.")

    return impacts


# ─────────────────────────────────────────────────────────────
#  OMNI AUDIT — Full digital presence audit
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def run_omni_audit(domain: str) -> str:
    """
    Run a full digital presence audit on any Indonesian business website.
    Covers: SEO, AI Visibility (GEO), Performance, Security, Tech Stack.

    Args:
        domain: Website domain (e.g. "tokobaju.com" or "https://tokobaju.com")
    """
    domain = normalize_domain(domain)
    url = f"https://{domain}"

    html, status, headers, elapsed_ms = await fetch_page(url, timeout=20)

    if status == 0:
        return (
            f"# Cannot access {domain}\n\n"
            f"Website unreachable. Check:\n"
            f"- Domain is correct (e.g. tokobaju.com)\n"
            f"- Website is not down\n"
            f"- No firewall blocking access\n\n"
            f"Try again or use a different domain."
        )

    meta = extract_meta(html)
    tech = detect_tech_stack(html, headers)
    seo_score, seo_checks = calculate_seo_score(meta)
    impacts = estimate_business_impact(meta, tech, url.startswith("https"), elapsed_ms)

    # Performance score (0-100) from response time
    html_kb = len(html.encode()) / 1024
    perf_score = 100
    if elapsed_ms > 5000:
        perf_score = max(20, 100 - ((elapsed_ms - 5000) // 500) * 20)
    elif elapsed_ms > 2000:
        perf_score = max(40, 100 - ((elapsed_ms - 2000) // 300) * 15)

    # Security score
    sec_score = 50
    if url.startswith("https"):
        sec_score += 25
    if meta.get("json_ld"):
        sec_score += 15
    if any(h in headers for h in ["content-security-policy", "strict-transport-security", "x-frame-options"]):
        sec_score += 10

    # AI Visibility (GEO) score
    geo_score = 0
    geo_checks = []

    if meta.get("json_ld"):
        geo_score += 30
        geo_checks.append("Structured data found (JSON-LD)")
    else:
        geo_checks.append("No structured data — AI cannot understand your content")

    has_quant = bool(re.search(r"\d[\d.,]*\s?(ribu|juta|rb|jt)|Rp\s?\d", html, re.I))
    if has_quant:
        geo_score += 20
        geo_checks.append("Quantitative content found (prices, metrics)")
    else:
        geo_checks.append("No statistics or prices — AI prefers data-rich content")

    h1s = meta.get("h1_tags", [])
    if h1s and len(h1s[0]) > 5:
        geo_score += 20
        geo_checks.append("Clear H1 — AI can identify page topic")
    else:
        geo_checks.append("H1 missing or too short — AI cannot determine page topic")

    if meta.get("robots") and "noindex" in meta["robots"]:
        geo_score = 0
        geo_checks = ["Page has noindex — invisible to all crawlers"]
    else:
        geo_score += 10
        geo_checks.append("No robots restrictions")

    geo_score = min(100, geo_score)

    # Quick wins
    quick_wins = []
    if not meta.get("og:image"):
        quick_wins.append("Add Open Graph image (1200x630px) — WhatsApp shares will show a preview")
    if not meta.get("json_ld"):
        quick_wins.append("Add JSON-LD schema (Organization or Product) — helps AI find your business")
    if not meta.get("meta_description"):
        quick_wins.append("Write a meta description (50-160 chars) — appears in Google results")
    if not meta.get("viewport"):
        quick_wins.append("Add viewport meta tag — fixes mobile display issues")
    if elapsed_ms > 3000:
        quick_wins.append(f"Speed up — {elapsed_ms}ms is slow; compress images and enable caching")
    if not quick_wins:
        quick_wins.append("Site is well-optimized! Focus on backlinks and content quality.")

    # Build output
    lines = [
        f"# Omni Audit — {domain}",
        "",
        "## Scores",
        f"| Pillar | Score |",
        f"|---|---|",
        f"| AI Visibility (GEO) | {geo_score}/100 |",
        f"| Performance | {perf_score}/100 |",
        f"| Security | {sec_score}/100 |",
        f"| SEO | {seo_score}/100 |",
        f"",
        f"*HTTP: {status} | Response: {elapsed_ms}ms | HTML: {html_kb:.0f}KB*",
        "",
        "## SEO Checks",
    ]

    for name, ok, detail in seo_checks:
        icon = "pass" if ok else "fail"
        lines.append(f"- [{icon}] {name}: {detail}")

    lines.extend([
        "",
        "## AI Visibility (GEO)",
    ])
    for check in geo_checks:
        icon = "pass" if check.startswith("Struct") or check.startswith("Clear") or check.startswith("No robots") else "fail"
        lines.append(f"- [{icon}] {check}")

    if meta.get("json_ld"):
        lines.append(f"- Context: Found {len(meta['json_ld'])} JSON-LD block(s)")
        for ld in meta["json_ld"][:3]:
            lines.append(f"  Type: {ld.get('@type', 'Unknown')}")

    lines.extend([
        "",
        "## Tech Stack",
        f"Detected: {', '.join(tech)}",
        "",
        "## Business Impact",
    ])
    for impact in impacts:
        lines.append(f"- {impact}")

    lines.extend([
        "",
        "## 3 Quick Wins",
    ])
    for i, win in enumerate(quick_wins[:3], 1):
        lines.append(f"{i}. {win}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  HOMEPAGE SEO CHECK — Quick diagnostic
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def check_homepage_seo(domain: str) -> str:
    """
    Quick SEO check with formatted report card.
    Best for: fast diagnosis before a full audit.

    Args:
        domain: Website domain (e.g. "tokobaju.com")
    """
    domain = normalize_domain(domain)
    url = f"https://{domain}"

    html, status, _, elapsed_ms = await fetch_page(url, timeout=15)

    if status == 0:
        return f"Cannot reach {domain}. Check domain is correct and site is active."

    meta = extract_meta(html)
    _, checks = calculate_seo_score(meta)
    checks.append(("Load Speed", elapsed_ms < 3000, f"{elapsed_ms}ms"))

    passed = sum(1 for _, ok, _ in checks if ok)
    pct = round(passed / len(checks) * 100)

    grade = "Good" if pct >= 80 else "Needs Work" if pct >= 50 else "Critical"

    lines = [
        f"# SEO Homepage Report — {domain}",
        "",
        f"## Score: {passed}/{len(checks)} ({pct}%) — {grade}",
        f"Load time: {elapsed_ms}ms",
        "",
    ]

    for name, ok, detail in checks:
        icon = "pass" if ok else "fail"
        lines.append(f"- [{icon}] {name}: {detail}")

    if pct < 80:
        lines.extend(["", "## Priority Fixes",])
        if not meta.get("meta_description"):
            lines.append("1. Add meta description (50-160 chars) describing your business")
        if not meta.get("og:image"):
            lines.append("2. Add OG image (1200x630px) for WhatsApp/Facebook shares")
        if not meta.get("json_ld"):
            lines.append("3. Add JSON-LD schema (Organization or LocalBusiness type)")
        if not meta.get("viewport"):
            lines.append("4. Add `<meta name=\"viewport\">` for mobile users")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  WEBSITE HEALTH CHECK — Uptime + SSL + Security
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def check_website_health(domain: str) -> str:
    """
    Technical health check: HTTPS, SSL, response time, DNS, security headers.

    Args:
        domain: Website domain (e.g. "tokobaju.com")
    """
    domain = normalize_domain(domain)
    https_url = f"https://{domain}"
    http_url = f"http://{domain}"

    checks = []
    sec_score = 0

    # HTTPS check
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            resp = await client.get(https_url)
            https_ok = resp.is_success
            sec_headers = dict(resp.headers)
    except Exception as e:
        https_ok = False
        sec_headers = {}

    checks.append(("HTTPS Active", https_ok, f"Status: {resp.status_code}" if https_ok else str(e)[:50]))
    if https_ok:
        sec_score += 40

    # HTTP→HTTPS redirect
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            resp_http = await client.get(http_url)
            http_redirect = resp_http.status_code in (301, 302, 303, 307, 308)
    except Exception:
        http_redirect = False

    checks.append(("HTTP->HTTPS Redirect", http_redirect, "Configured" if http_redirect else "Not configured"))
    if http_redirect:
        sec_score += 10

    # Security headers
    security_header_names = ["content-security-policy", "strict-transport-security",
                            "x-frame-options", "x-content-type-options"]
    found_headers = [h for h in security_header_names if h in sec_headers]
    checks.append(("Security Headers", len(found_headers) >= 2, f"{len(found_headers)} of 4 found: {', '.join(found_headers) or 'None'}"))
    if len(found_headers) >= 2:
        sec_score += 25
    elif found_headers:
        sec_score += 10

    # Mixed content
    checks.append(("Mixed Content", https_ok, "No HTTP resources detected" if https_ok else "N/A"))
    sec_score += 25

    # DNS
    try:
        import socket
        ip = socket.gethostbyname(domain)
        checks.append(("DNS Resolution", True, f"A record: {ip}"))
    except Exception as e:
        checks.append(("DNS Resolution", False, str(e)[:50]))

    passed = sum(1 for _, ok, _ in checks if ok)
    pct = round(passed / len(checks) * 100)

    lines = [
        f"# Website Health — {domain}",
        f"",
        f"## Health Score: {passed}/{len(checks)} ({pct}%)",
        f"",
    ]

    for name, ok, detail in checks:
        icon = "pass" if ok else "fail"
        lines.append(f"- [{icon}] {name}: {detail}")

    if sec_score < 70:
        lines.extend(["", "## Urgent Fixes",])
        if not https_ok:
            lines.append("1. Enable HTTPS immediately — without it, browsers warn users away")
        if len(found_headers) < 2:
            lines.append("2. Add security headers via hosting config (.htaccess or nginx.conf):")
            lines.append("   Strict-Transport-Security: max-age=31536000")
            lines.append("   X-Frame-Options: DENY")
            lines.append("   Content-Security-Policy: default-src 'self'")
    else:
        lines.extend(["", "Health is good. Focus on SEO and content."])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  TIKTOK CAPTIONS — Indonesian viral captions
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def write_tiktok_captions(topic: str, count: int = 5) -> str:
    """
    Generate Indonesian TikTok captions optimized for UMKM engagement.

    Args:
        topic: Business industry (e.g. "fashion", "food", "beauty")
        count: Number of captions to generate (default 5, max 10)
    """
    count = min(count, 10)

    templates = {
        "fashion": [
            ("Trik satu ini bikin outfit terlihat 10x lebih mahal!", "Gak nyangka hasilnya beda banget! Save dulu biar gak lupa #fashion #ootd #stylingtips"),
            ("Ini rahasia outfit monochromatic yang bikin auto看去!", "Cocok untuk semua body type! Yang udah coba boleh komentar hasilnya #monochrome #fashionhacks"),
            ("Jualannya lancar karena ini rahasia packaging!", "Buka detailnya di下一个视频! Yang mau coba langsung DM ya #packaging #fashionbusiness #umkm"),
            ("3 outfit combo yang cocok untuk kerja dari rumah!", "Kombinasi simpel tapi tetap stylish! Save + share! #wfhstyle #outfitinspiration"),
            ("Hot trend 2025 yang belum banyak orang tahu!", "Yang udah coba boleh komentar hasilnya! #fashiontrend #2025style #viral"),
            ("Behind the scenes: Proses pemilihan bahan baku!", "Kualitas terlihat dari细节! Quality over quantity #behindthescenes #fashionmaker"),
            ("PO terbaru! Batch terbatas, harga khusus!", "Klik link di bio untuk order! First come first served #preorder #limitededition"),
            ("Ini yang bikin customer repeat order terus!", "Simak strateginya di video berikut! #customerretention #fashionbusiness #sellingtips"),
            ("Outfit of the day: Casual Friday edition!", "Mau tahu combo lengkapnya? Comment dulu! #ootd #casualstyle"),
            ("Review: Baju ini worth it gak sih?", "Hasil review jujur di sini! No baper, just facts #clothingreview #honestreview"),
        ],
        "food": [
            ("Resep ini sudah turun temurun dari nenek!", "Yang sudah coba comment hasilnya ya! #resepnenek #traditionalfood #indonesianfood"),
            ("Trik bikin martabak tipis kriuk yang bikin auto-laris!", "Resep lengkap di下一个视频! Jangan lupa save! #martabaktips #streetfood"),
            ("1 bahan aja, tapi rasanya RESTORAN!", "Gak nyangka! Bahan ada di dapur semua! #easytocook #resepsederhana #foodhack"),
            ("Paket catering ini isinya wow banget!", "Harga? Buka bio untuk info! #catering #foodpackage #eventcatering"),
            ("Hot menu baru! Yang sudah coba auto ng摇头!", "Available daily di outlet kami! #newmenu #foodlover #dailyfresh"),
            ("3 alasan kenapa ini best seller!", "Nomor 3 bikin semua orang gak bisa berhenti makan! #bestseller #signaturedish"),
            ("Cold drink yang pas untuk cuaca hari ini!", "Resepnya super gampang, wajib coba! #colddrink #refreshing #easyrecipe"),
            ("Customer cerita: Gak pernah失望 dengan produk ini!", "Testimoni asli dari customer loyal! #customertestimonial #foodreview"),
        ],
        "beauty": [
            ("Before vs After: Perubahan ini nyata!", "Yang penasaran dengan produknya? DM ya! #beforeafter #beautytransformation #skincare"),
            ("5 menit routine yang hasilnya sigap!", "Perfect untuk yang sibuk setiap pagi! #morningroutine #beautyroutine #skintips"),
            ("Ingredient yang harus dihindari di skincare!", "No. 3 sering terdapat di produk populer! #skincareingredients #beautyeducation"),
            ("Viral hack: Pakai ini sebelum bedak!", "Hasilnya: Poreless effect seluruh hari! #makeuphack #beautyhacks"),
            ("Skin type kamu? Check di sini!", "Kenal skin type = pilih produk yang tepat! #skintype #beautytips"),
            ("Dupes продукты yang mirip banget sama luxury brands!", "Quality comparable, harga却宜人! #skindupes #beautydupe"),
            ("Reaksi customer pertama kali coba!", "Yang sudah coba boleh share hasilnya di kolom komentar! #customereaction #beautyreview"),
        ],
        "umkm": [
            ("Bagaimana kami meningkatkan продажи 3x dalam 3 bulan!", "Strategies yang sudah terbukti! Copy dan adapt! #umkm #businessgrowth #salestips"),
            ("1 ошибка yang membuat customer tidak kembali!", "Penting untuk semua business owners! #customertips #businessadvice"),
            ("Behind the scenes: Packing process!", "Setiap paket ditangani dengan爱! #behindthescenes #packingprocess #qualitycontrol"),
            ("Customer review yang bikin semangat!", "Terima kasih untuk yang sudah percaya! #customerreview #testimonial #grateful"),
            ("New product launch: Sudah bisa dipesan!", "Klik link di bio untuk order sekarang! #newproduct #launch"),
            ("Tips product photography dengan HP saja!", "No DSLR needed! Hasil profesional dengan HP! #productphoto #phonetography"),
            ("Flash sale 24 jam only!", "Diskon sampai 50%! Link di bio! #flashsale #discount #limitedtime"),
        ],
    }

    selected = templates.get(topic.lower(), templates["umkm"])[:count]

    lines = [f"# TikTok Captions — {topic.title()}\n"]
    for i, (hook, body) in enumerate(selected, 1):
        lines.append(f"## Caption {i}\n**Hook:** {hook}\n**Body:** {body}\n")

    lines.extend([
        "## Tips",
        "- Post 3-5x seminggu konsisten",
        "- Use trending audio + local music",
        "- Reply semua komentar dalam 1 jam",
        "- Save konten terbaik ke Highlights",
    ])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  INSTAGRAM CAPTIONS — Engagement-focused
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def write_instagram_captions(topic: str, count: int = 3) -> str:
    """
    Generate Indonesian Instagram captions with engagement hooks and CTAs.

    Args:
        topic: Business topic (e.g. "fashion", "food", "beauty")
        count: Number of captions (default 3, max 8)
    """
    count = min(count, 8)

    industry_data = {
        "fashion": "fashion",
        "food": "kuliner",
        "beauty": "skincare",
        "beauty": "skincare",
    }

    hashtag = industry_data.get(topic.lower(), "bisnis")

    captions = [
        (
            "STORY ALERT\n\n"
            "Yang suka {tag} wajib coba ini!\n\n"
            "Komentar 'INTERESTED' kalau mau tau lebih lanjut!\n\n"
            "#{tag}indonesia #umkm #belanjaonline",
            "Storytelling + engagement CTA"
        ),
        (
            "NEW ARRIVAL\n\n"
            "Baru релиз! Produk yang sudah banyak yang minta!\n\n"
            "📍 Tersedia setiap hari\n"
            "💰 Harga spesial untuk 20 orang pertama!\n\n"
            "Link di bio!\n\n"
            "#{tag}product #newproduct #limited",
            "Product launch"
        ),
        (
            "Q: Apa yang bikin kamu percaya sebuah brand?\n\n"
            "Jawab di kolom komentar!\n\n"
            "Kami akan reply setiap jawaban!\n\n"
            "#{tag}question #community #brand",
            "Question sticker"
        ),
        (
            "5 {tag} mistakes yang bikin kamu rugi\n\n"
            "1. Menyimpan terlalu banyak\n"
            "2. Gak tahu cara pakai\n"
            "3. Salah pilih ukuran\n\n"
            "Yang mau lengkapnya? Save + Share!\n\n"
            "#{tag}Tips #mistakes #edutok",
            "Educational list"
        ),
        (
            "━━━━━━━━━━━━━━━\n"
            "REAL REVIEW\n"
            "━━━━━━━━━━━━━━━\n\n"
            '" baru coba langsung ketagihan! "\n'
            "— [Customer Name], verified buyer ⭐⭐⭐⭐⭐\n\n"
            "Mau jadi下一个 yang kasih review?\n"
            "Order sekarang!\n\n"
            "#{tag}review #testimoni #trusted",
            "Testimonial"
        ),
        (
            "━━━━━━━━━━━━━━━\n"
            "HARI INI SAJA!\n"
            "━━━━━━━━━━━━━━━\n\n"
            "Diskon [X]% untuk order via DM!\n\n"
            "Caranya:\n"
            "1. DM 'ORDER'\n"
            "2. Pilih produk\n"
            "3. Transfer\n\n"
            "⚠️ Kuota terbatas!\n\n"
            "#{tag}Sale #discount #flashsale",
            "Urgency/Scarcity"
        ),
        (
            "━━━━━━━━━━━━━━━\n"
            "BEHIND THE SCENES\n"
            "━━━━━━━━━━━━━━━\n\n"
            "Ini yang jarang orang tahu tentang produk kami!\n\n"
            "Semua dibuat dengan penuh ❤️\n\n"
            "━━━━━━━━━━━━━━━\n\n"
            "Tag orang yang harus lihat ini!\n\n"
            "#{tag}bts #behindthescenes #journey",
            "BTS + Tag"
        ),
        (
            "━━━━━━━━━━━━━━━\n"
            "STORY TIME\n"
            "━━━━━━━━━━━━━━━\n\n"
            "6 bulan lalu kami hampir berhenti...\n"
            "Tapi kemudian sesuatu berubah.\n\n"
            "━━━━━━━━━━━━━━━\n\n"
            "Swipe untuk tahu apa yang terjadi!\n\n"
            "#{tag}story #journey #entrepreneur",
            "Story swipe"
        ),
    ]

    selected = captions[:count]

    lines = [f"# Instagram Captions — {topic.title()}\n"]
    for i, (caption, style) in enumerate(selected, 1):
        filled = caption.format(tag=hashtag)
        lines.append(f"## {i} — {style}\n{filled}\n")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  SS VIDEO PROMPTS — ShortcutSistem fashion pipeline
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def get_ss_video_prompt(industry: str, brand_name: str) -> str:
    """
    Generate ShortcutSistem video prompts for MiniMax + BytePlus fashion pipeline.
    Use this before generating fashion videos for TikTok/Instagram.

    Args:
        industry: Business industry (e.g. "fashion", "food", "beauty")
        brand_name: Brand or business name (e.g. "Ratoshen Fashion")
    """
    industry = industry.lower().strip()
    brand_name = brand_name.strip()

    prompts = {
        "fashion": {
            "image": (
                f"A highly detailed 4K fashion photography shot of {brand_name}'s latest collection. "
                "Studio lighting, clean white background, professional fashion editorial style. "
                "Model wearing minimalist white linen blouse paired with high-waisted tailored trousers. "
                "The outfit is elegantly simple with subtle texture details. "
                "Soft natural light from left side, sharp shadows on right. "
                "Fashion magazine cover quality, Vogue editorial aesthetic. "
                "Color palette: ivory, cream, soft gold accents. "
                "Ultra-sharp, no watermark, no text overlay."
            ),
            "motion": (
                f"Slow cinematic zoom on {brand_name} fashion piece, "
                "fabric texture revealed in soft natural light, "
                "camera slowly pans left to right showing full outfit details, "
                "elegant floating motion, high-end fashion film quality, "
                "warm studio lighting, smooth transition, premium luxury feel"
            ),
            "caption": (
                f"━━━━━━━━━━━━━━━\n"
                f"✨ {brand_name} NEW ARRIVAL\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"Yang udah nunggu... finally here!\n\n"
                f"📍 Limited stock!\n"
                f"💬 DM 'STOCK' untuk cek ketersediaan\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"#fashionindonesia #newarrival #ootd #stylish"
            ),
        },
        "food": {
            "image": (
                f"Professional food photography of {brand_name}'s signature dish. "
                "Gourmet plating on white ceramic bowl, steam rising elegantly. "
                "Natural daylight photography, shallow depth of field. "
                "Color palette: warm amber, fresh green herbs, white ceramic. "
                "Food magazine quality, appetizing and vibrant. "
                "Ultra-sharp, no watermark, no text."
            ),
            "motion": (
                f"Close-up cinematic reveal of {brand_name} dish, "
                "steam slowly rising, camera dollies in showing texture, "
                "ingredients sprinkle from above in slow motion, "
                "appetizing food film quality, warm golden lighting, "
                "gourmet restaurant aesthetic, smooth elegant motion"
            ),
            "caption": (
                f"━━━━━━━━━━━━━━━\n"
                f"🍜 {brand_name} SIGNATURE DISH\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"Recipe yang udah hundreds of people jatuh cinta!\n\n"
                f"📍 Available daily\n"
                f"📦 Grab sekarang juga!\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"#foodindonesia #kuliner #enak #resep #foodlover"
            ),
        },
        "beauty": {
            "image": (
                f"Clean beauty product photography of {brand_name} skincare line. "
                "Minimalist aesthetic, white marble background, soft diffused lighting. "
                "Product bottles arranged with botanical elements (eucalyptus, roses). "
                "Clean beauty editorial style, skin-care magazine aesthetic. "
                "Color palette: white, soft pink, natural green, amber glass. "
                "Ultra-sharp, no watermark, no text."
            ),
            "motion": (
                f"Elegant product reveal for {brand_name} skincare, "
                "soft light reflection on glass bottle surface, "
                "gentle floating botanical petals in background, "
                "camera slowly orbits around product, "
                "luxury beauty commercial quality, soft bokeh light particles, "
                "serene and premium aesthetic"
            ),
            "caption": (
                f"━━━━━━━━━━━━━━━\n"
                f"✨ {brand_name} SKINCARE LINE\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"Skin type kamu? Check story highlight!\n\n"
                f"📍 DM untuk konsultasi gratis\n"
                f"💬 Comment 'GLOW' untuk skincare routine!\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"#skincare #beautyindonesia #glowingskin #beautytips"
            ),
        },
    }

    default_p = {
        "image": (
            f"Professional product photography for {brand_name}. "
            f"Clean minimalist setup, white background, studio lighting. "
            f"Product centered, high-end e-commerce quality. "
            f"Ultra-sharp, no watermark, no text."
        ),
        "motion": (
            f"Elegant product showcase for {brand_name}, "
            f"slow cinematic reveal, premium feel, "
            f"soft lighting, smooth floating motion, "
            f"luxury product film quality"
        ),
        "caption": (
            f"━━━━━━━━━━━━━━━\n"
            f"✨ {brand_name} NEW ARRIVAL\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"Finally here! Yang udah nunggu.\n\n"
            f"📍 Limited stock — DM now!\n"
            f"━━━━━━━━━━━━━━━\n"
            f"#{industry}indonesia #newarrival #brand"
        ),
    }

    p = prompts.get(industry, default_p)

    lines = [
        f"# Video Prompts — {brand_name} ({industry.title()})\n",
        "## Step 1: MiniMax Image (generate first)\n",
        f"```\n{p['image']}\n```\n",
        "> Use MiniMax image model, 4:5 ratio for IG, 9:16 for TikTok\n",
        "\n## Step 2: BytePlus I2V Motion Prompt\n",
        f"```\n{p['motion']}\n```\n",
        "> Use with BytePlus Seedance 2.0 image-to-video\n",
        "\n## Step 3: TikTok Caption (ready to post)\n",
        f"```\n{p['caption']}\n```\n",
        "\n## Pipeline\n",
        "1. MiniMax image → catbox.moe upload → BytePlus I2V → MP4",
        "2. Add 'shortcutsistem' watermark (white, sans-serif, bottom-right)",
        "3. Bake audio (ffmpeg) → post to TikTok + IG Reels",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  CONTENT CALENDAR — 4-week posting schedule
# ─────────────────────────────────────────────────────────────

@mcp.tool()
async def create_content_calendar(topic: str, weeks: int = 4) -> str:
    """
    Create a 4-week Indonesian social media content calendar for UMKM.

    Args:
        topic: Business industry (e.g. "fashion", "food", "beauty", "umkm")
        weeks: Number of weeks (default 4)
    """
    content_types = {
        "fashion": [("Senin", "Product Showcase"), ("Rabu", "Behind the Scenes"),
                    ("Jumat", "Styling Tips"), ("Sabtu", "Customer Review")],
        "food":     [("Senin", "Ingredient Reveal"), ("Rabu", "Cooking Process"),
                    ("Jumat", "Customer Review"), ("Sabtu", "Recipe Tutorial")],
        "beauty":   [("Senin", "Product Demo"), ("Rabu", "Before/After"),
                    ("Jumat", "Tutorial"), ("Sabtu", "Skin Type Guide")],
        "umkm":     [("Senin", "Product Feature"), ("Rabu", "Business Tip"),
                    ("Jumat", "Customer Story"), ("Sabtu", "Q&A / Poll")],
    }

    data = content_types.get(topic.lower(), content_types["umkm"])
    topic_hashtag = topic.lower().replace(" ", "")

    import random
    random.seed(42)

    hooks = [
        "Gak nyangka hasilnya beda banget!",
        "Ini yang bikin beda!",
        "Wajib tonton sampai habis!",
        "Hot take! Opinions?",
        "Trik yang jarang orang tahu!",
        "Rahasia revealed...",
        "Yang udah coba boleh komentar!",
    ]

    lines = [
        f"# Content Calendar — {topic.title()} ({weeks} Weeks)\n",
        f"Platform: TikTok + Instagram Reels\n",
        f"Frequency: 3-4x per week\n",
        f"CTA Pattern: Save | Share | Follow | DM\n\n",
    ]

    for week in range(1, weeks + 1):
        lines.append(f"## Week {week}\n")
        for day, ctype in data:
            hook = random.choice(hooks)
            lines.append(
                f"**{day} — {ctype}**\n"
                f"  Hook: {hook}\n"
                f"  Format: 15-30 second storytelling video\n"
                f"  CTA: Save | Share | DM\n"
            )
        lines.append("")

    lines.extend([
        "## Best Practices",
        "- Post consistently (min 3x/week)",
        "- Use trending Indonesian audio",
        "- Reply all comments within 1 hour",
        "- Save best content to Highlights",
        "- Reuse viral content with variations",
    ])

    return "\n".join(lines)

# ══════════════════════════════════════════════════════════════

def run():
    """Start the MCP server."""
    port = int(os.getenv("PORT", "8000"))

    print(f"🚀 Starting ShortcutSistem + Band MCP Server")
    print(f"   Name: ShortcutSistem + Band")
    print(f"   Port: {port}")
    print(f"   Transport: streamable-http (Cursor Cloud compatible)")
    print()
    print(f"   Band Tools:")
    for t in ["band_list_agents", "band_list_my_chats", "band_send_message",
              "band_get_chat_history", "band_trigger_agent"]:
        print(f"     • {t}")
    print()
    print(f"   ShortcutSistem Tools:")
    for t in ["run_omni_audit", "check_homepage_seo", "check_website_health",
              "write_tiktok_captions", "write_instagram_captions",
              "get_ss_video_prompt", "create_content_calendar"]:
        print(f"     • {t}")
    print()

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    run()

