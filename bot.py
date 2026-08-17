import os
import re
import subprocess
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# HARDCODED TOKEN
BOT_TOKEN = "8732910407:AAFH5C8tg_WM81irgED45A0pLaUx-bN4uRA"

bot = telebot.TeleBot(BOT_TOKEN)

user_data = {}

def ani_cli_search(query):
    env = os.environ.copy()
    env["ANI_CLI_PLAYER"] = "debug"
    env["ANI_CLI_NON_INTERACTIVE"] = "1"
    
    result = subprocess.run(
        ["ani-cli", "-N", "-S", "1", "-q", "best", query],
        capture_output=True, text=True, env=env, timeout=60
    )
    
    output = result.stdout + result.stderr
    animes = []
    lines = output.split('\n')
    for line in lines:
        match = re.match(r'^\s*(\d+)\)\s+(.+)$', line)
        if match:
            animes.append(match.group(2).strip())
    
    return animes[:10]

def ani_cli_get_url(anime_name, episode):
    env = os.environ.copy()
    env["ANI_CLI_PLAYER"] = "debug"
    env["ANI_CLI_NON_INTERACTIVE"] = "1"
    
    result = subprocess.run(
        ["ani-cli", "-N", "-S", "1", "-q", "best", "-e", str(episode), anime_name],
        capture_output=True, text=True, env=env, timeout=120
    )
    
    output = result.stdout + result.stderr
    for line in output.split('\n'):
        if 'http' in line and ('.m3u8' in line or '.mp4' in line or 'vidstream' in line or 'mcloud' in line):
            return line.strip()
    return None

@bot.message_handler(commands=['start'])
def start(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔍 Search Anime", callback_data="search"))
    
    welcome_text = (
        "🎌 *Welcome to AnimeStream Bot!*\n\n"
        "Watch any anime, any episode — instantly.\n"
        "Tap below to start searching!"
    )
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "search")
def ask_anime_name(call):
    msg = bot.send_message(
        call.message.chat.id,
        "📝 *Enter anime name:*\n\nType the name and send it!",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_search)

def process_search(message):
    query = message.text.strip()
    if not query:
        bot.send_message(message.chat.id, "❌ Empty query. Try /start again.")
        return
    
    bot.send_message(message.chat.id, f"🔍 Searching for *{query}*...", parse_mode='Markdown')
    
    try:
        results = ani_cli_search(query)
        if not results:
            bot.send_message(message.chat.id, "❌ No results found. Try /start again.")
            return
        
        user_data[message.chat.id] = {'results': results}
        
        markup = InlineKeyboardMarkup()
        for i, name in enumerate(results):
            markup.add(InlineKeyboardButton(f"{i+1}. {name[:40]}", callback_data=f"anime_{i}"))
        
        bot.send_message(
            message.chat.id,
            f"📺 *Found {len(results)} results:*\n\nTap to select:",
            parse_mode='Markdown',
            reply_markup=markup
        )
        
    except Exception as e:
        bot.send_message(message.chat.id, f"💥 Error: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("anime_"))
def ask_episode(call):
    idx = int(call.data.split("_")[1])
    chat_id = call.message.chat.id
    
    anime_name = user_data[chat_id]['results'][idx]
    user_data[chat_id]['selected_anime'] = anime_name
    
    bot.edit_message_text(
        f"🎬 *Selected:* {anime_name}\n\n"
        f"📝 *Enter episode number:*\n\n"
        f"Type a number and send it!\n"
        f"Example: `1` or `1100`",
        chat_id=chat_id,
        message_id=call.message.message_id,
        parse_mode='Markdown'
    )
    
    bot.register_next_step_handler_by_chat_id(chat_id, process_episode)

def process_episode(message):
    chat_id = message.chat.id
    
    if chat_id not in user_data or 'selected_anime' not in user_data[chat_id]:
        bot.send_message(chat_id, "❌ Session expired. Start again with /start")
        return
    
    anime_name = user_data[chat_id]['selected_anime']
    
    try:
        episode = int(message.text.strip())
        if episode < 1:
            raise ValueError
    except ValueError:
        msg = bot.send_message(chat_id, "❌ Invalid episode number. Enter a valid number:")
        bot.register_next_step_handler(msg, process_episode)
        return
    
    bot.send_message(chat_id, f"⏳ Getting stream for *{anime_name}* — Episode {episode}...", parse_mode='Markdown')
    
    try:
        url = ani_cli_get_url(anime_name, episode)
        
        if url:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔄 Search Again", callback_data="search"))
            
            bot.send_message(
                chat_id,
                f"✅ *Stream Ready!*\n\n"
                f"🎬 *{anime_name}*\n"
                f"📺 Episode {episode}\n\n"
                f"🔗 *URL:*\n`{url}`\n\n"
                f"📋 Copy and paste into VLC or your browser!",
                parse_mode='Markdown',
                reply_markup=markup
            )
        else:
            bot.send_message(
                chat_id,
                f"❌ Couldn't extract stream URL.\n\n"
                f"🎬 *{anime_name}* — Ep {episode}\n\n"
                f"Try a different episode or anime.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        bot.send_message(chat_id, f"💥 Error: {str(e)}")

print("🤖 Bot is running...")
bot.polling()
