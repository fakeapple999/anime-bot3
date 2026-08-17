import os
import re
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8847925560:AAE9Zdr35Dj5mkqpROoK-ksW4SrTSNwrRMo"
bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}

BASE = "https://anidb.app"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://anidb.app",
    "Accept": "application/json, text/html, */*",
}

def search_anime(query):
    r = requests.get(
        f"{BASE}/browse",
        params={"q": query},
        headers=HEADERS,
        timeout=15
    )
    r.raise_for_status()
    # Parse results: ani-cli extracts <a href="/anime/ID">Name</a>
    results = []
    for match in re.finditer(r'<a href="/anime/(\d+)"[^>]*>([^<]+)</a>', r.text):
        anime_id = match.group(1)
        name = match.group(2).strip()
        if name and anime_id:
            results.append({"id": anime_id, "name": name})
    # Deduplicate by id
    seen = set()
    unique = []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            unique.append(r)
    return unique[:10]

def get_episodes(anime_id):
    r = requests.get(
        f"{BASE}/api/frontend/anime/{anime_id}/episodes",
        headers=HEADERS,
        timeout=15
    )
    r.raise_for_status()
    data = r.json()
    # Returns list of episodes with their IDs
    return data

def get_stream_url(episode_id):
    r = requests.get(
        f"{BASE}/api/frontend/episode/{episode_id}/languages",
        headers=HEADERS,
        timeout=15
    )
    r.raise_for_status()
    data = r.json()
    return data

# ── Handlers ────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def start(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔍 Search Anime", callback_data="search"))
    bot.send_message(
        message.chat.id,
        "🎌 *Welcome to AnimeStream Bot!*\n\nSearch any anime and get stream URLs.\nTap below to start!",
        parse_mode="Markdown",
        reply_markup=markup,
    )

@bot.callback_query_handler(func=lambda call: call.data == "search")
def ask_anime_name(call):
    msg = bot.send_message(
        call.message.chat.id,
        "📝 *Enter anime name:*\n\nType and send it!",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_search)

def process_search(message):
    query = message.text.strip()
    if not query:
        bot.send_message(message.chat.id, "❌ Empty query. Try /start again.")
        return

    bot.send_message(message.chat.id, f"🔍 Searching for *{query}*...", parse_mode="Markdown")

    try:
        results = search_anime(query)
    except Exception as e:
        bot.send_message(message.chat.id, f"💥 Search error: {e}")
        return

    if not results:
        bot.send_message(message.chat.id, "❌ No results found. Try /start again.")
        return

    user_data[message.chat.id] = {"results": results}

    markup = InlineKeyboardMarkup()
    for i, anime in enumerate(results):
        markup.add(InlineKeyboardButton(f"{i+1}. {anime['name'][:45]}", callback_data=f"anime_{i}"))

    bot.send_message(
        message.chat.id,
        f"📺 *Found {len(results)} results:*\n\nTap to select:",
        parse_mode="Markdown",
        reply_markup=markup,
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("anime_"))
def anime_selected(call):
    idx = int(call.data.split("_")[1])
    chat_id = call.message.chat.id

    if chat_id not in user_data:
        bot.send_message(chat_id, "❌ Session expired. Use /start again.")
        return

    anime = user_data[chat_id]["results"][idx]
    user_data[chat_id]["selected"] = anime

    # Fetch episode list
    try:
        episodes = get_episodes(anime["id"])
        user_data[chat_id]["episodes"] = episodes
        ep_count = len(episodes) if isinstance(episodes, list) else "?"
    except Exception as e:
        ep_count = "?"
        user_data[chat_id]["episodes"] = []

    bot.edit_message_text(
        f"🎬 *{anime['name']}*\n\n"
        f"📺 Episodes available: {ep_count}\n\n"
        f"📝 Enter episode number:",
        chat_id=chat_id,
        message_id=call.message.message_id,
        parse_mode="Markdown",
    )
    bot.register_next_step_handler_by_chat_id(chat_id, process_episode)

def process_episode(message):
    chat_id = message.chat.id

    if chat_id not in user_data or "selected" not in user_data[chat_id]:
        bot.send_message(chat_id, "❌ Session expired. Use /start again.")
        return

    try:
        ep_num = int(message.text.strip())
        if ep_num < 1:
            raise ValueError
    except ValueError:
        msg = bot.send_message(chat_id, "❌ Invalid number. Enter a valid episode number:")
        bot.register_next_step_handler(msg, process_episode)
        return

    anime = user_data[chat_id]["selected"]
    episodes = user_data[chat_id].get("episodes", [])

    bot.send_message(
        chat_id,
        f"⏳ Getting stream for *{anime['name']}* Ep {ep_num}...",
        parse_mode="Markdown",
    )

    # Find the episode ID from the list
    ep_id = None
    if isinstance(episodes, list):
        for ep in episodes:
            # Episode objects have epno or episode_number field
            ep_no = ep.get("epno") or ep.get("episode_number") or ep.get("number")
            if str(ep_no) == str(ep_num):
                ep_id = ep.get("id") or ep.get("episode_id")
                break

    if not ep_id:
        bot.send_message(
            chat_id,
            f"❌ Episode {ep_num} not found for *{anime['name']}*.\n\nCheck episode number and try again.",
            parse_mode="Markdown",
        )
        # Debug: show what the episode data actually looks like
        if episodes and len(episodes) > 0:
            bot.send_message(chat_id, f"🔍 Debug - first episode data:\n`{str(episodes[0])[:300]}`", parse_mode="Markdown")
        return

    try:
        stream_data = get_stream_url(ep_id)
        # Find the best m3u8/mp4 URL
        url = extract_url(stream_data)
    except Exception as e:
        bot.send_message(chat_id, f"💥 Stream error: {e}")
        return

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔄 Search Again", callback_data="search"),
        InlineKeyboardButton("▶️ Next Ep", callback_data=f"nexts_{ep_num}"),
    )

    if url:
        bot.send_message(
            chat_id,
            f"✅ *Stream Ready!*\n\n"
            f"🎬 *{anime['name']}*\n"
            f"📺 Episode {ep_num}\n\n"
            f"🔗 *URL:*\n`{url}`\n\n"
            f"📋 Paste into browser or VLC!",
            parse_mode="Markdown",
            reply_markup=markup,
        )
    else:
        bot.send_message(
            chat_id,
            f"⚠️ Got data but couldn't find URL.\n\nRaw:\n`{str(stream_data)[:400]}`",
            parse_mode="Markdown",
        )

def extract_url(data):
    """Extract best stream URL from anidb.app response."""
    if not data:
        return None
    text = str(data)
    # Look for m3u8 or mp4 URLs
    for pattern in [r'https?://[^\s\'"]+\.m3u8[^\s\'"]*', r'https?://[^\s\'"]+\.mp4[^\s\'"]*']:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None

@bot.callback_query_handler(func=lambda call: call.data.startswith("nexts_"))
def next_episode(call):
    ep_num = int(call.data.split("_")[1]) + 1
    chat_id = call.message.chat.id
    # Fake a message to reuse process_episode
    call.message.text = str(ep_num)
    call.message.chat.id = chat_id
    process_episode(call.message)

print("🤖 Bot is running...")
bot.infinity_polling()
