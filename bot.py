# COMPLETE WARFRAME DISCORD BOT WITH PLATINUM VALUES - FIXED PARSING
# This bot includes relic comparison with platinum market pricing

import os
import re
import json
import logging
import requests
import base64
import struct
import glob
import asyncio
import time
import aiohttp
from datetime import datetime
from typing import Dict, Optional

import discord
from discord import File, Intents, ButtonStyle, Embed
from discord.ui import View, Button
from discord.ext import commands
from discord.ext import tasks
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# Token storage configuration
USER_TOKENS_FILE = "user_tokens_encrypted.json"
TOKEN_KEY_FILE = "token_key.key"

# Directory configuration
RELICS_DIR = "user_relics"
REPORTS_DIR = "comparison_reports"
TEMP_DIR = "temp_files"

# Create directories if they don't exist
os.makedirs(RELICS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set in .env")

# Channel configuration
ALLOWED_CHANNEL_IDS = {
    1409131107261349980,  # Channel ID in Server 1
    1409169518323957780,  # Channel ID in Server 2
    # Add more as needed
}

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Bot setup
intents = Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Global variables
RELIC_DATA = {}
PLATINUM_CACHE = {}
CACHE_EXPIRY = 3600  # 1 hour in seconds
LAST_CACHE_UPDATE = 0

# Rate limiting for warframe.market API
MAX_CONCURRENT_REQUESTS = 3  # Max 3 concurrent requests to respect rate limits

# Persistent price cache configuration
PRICE_CACHE_FILE = "platinum_price_cache.json"

def fetch_and_save_relic_data():
    """Fetch relic data from external sources and save to relic_data.json."""
    drops_url = "https://raw.githubusercontent.com/WFCD/warframe-drop-data/main/data/relics.json"
    vaulted_url = "https://api.warframestat.us/items"

    response = requests.get(drops_url)
    response.raise_for_status()
    data = response.json()

    try:
        items_response = requests.get(vaulted_url, timeout=10)
        items_data = items_response.json() if items_response.status_code == 200 else []
    except Exception:
        items_data = []

    vaulted_mapping = {item.get('name', ''): item.get('vaulted', False)
                      for item in items_data if item.get('category') == 'Relics'}

    relic_data = {}
    for relic in data.get("relics", []):
        tier = relic.get("tier", "")
        relic_name = relic.get("relicName", "")
        state = relic.get("state", "")
        full_relic_name = f"{tier} {relic_name}{' ' + state if state else ''}".strip()

        vaulted = vaulted_mapping.get(full_relic_name, False) or ("Vaulted" in full_relic_name) or relic.get("vaulted", False)

        drops = []
        for reward in relic.get("rewards", []):
            item_name = reward.get("itemName")
            if item_name and item_name not in drops:
                drops.append(item_name)

        if full_relic_name:
            relic_data[full_relic_name] = {
                "drops": drops,
                "vaulted": vaulted
            }

    with open("relic_data.json", "w", encoding="utf-8") as f:
        json.dump(relic_data, f, indent=2, ensure_ascii=False)

    return len(relic_data), sum(1 for r in relic_data.values() if r["vaulted"])

def load_relic_data():
    """Load relic data from the JSON file"""
    global RELIC_DATA
    try:
        with open('relic_data.json', 'r', encoding='utf-8') as f:
            RELIC_DATA = json.load(f)
        logging.info(f"Loaded {len(RELIC_DATA)} relics from JSON file")
        return True
    except Exception as e:
        logging.error(f"Failed to load relic_data.json: {e}")
        return False

def normalize_relic_name(relic_name):
    """Convert user relic format to JSON relic format"""
    normalized = re.sub(r'\s+', ' ', relic_name.strip())
    normalized = normalized.replace(' - ', ' ')
    return normalized

def get_relic_contents():
    """Get relic contents from the loaded JSON data"""
    return RELIC_DATA

def sanitize_item_name_for_api(item_name: str) -> str:
    """Convert item name to warframe.market URL format - keep Prime in the name"""
    name = item_name.lower()
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    # Handle special characters
    name = name.replace("&", "and")
    name = name.replace("+", "plus")
    # Remove other special characters but keep underscores
    name = re.sub(r'[^\w_]', '', name)
    return name

async def fetch_price_concurrent(session, sem, item_name, api_name):
    """Fetch a single item price with concurrency control"""
    async with sem:
        url = f"https://api.warframe.market/v1/items/{api_name}/orders"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    orders = data.get('payload', {}).get('orders', [])

                    # Get average price of online sellers
                    sell_orders = [
                        order for order in orders 
                        if order.get('order_type') == 'sell' 
                        and order.get('user', {}).get('status') == 'ingame'
                    ]

                    if sell_orders:
                        sell_orders.sort(key=lambda x: x.get('platinum', 999))
                        top_orders = sell_orders[:3]
                        avg_price = sum(order.get('platinum', 0) for order in top_orders) / len(top_orders)
                        price = round(avg_price, 1)
                        logging.info(f"Found price for {item_name}: {price}p")
                        await asyncio.sleep(0.35)  # Rate limit: ~3 requests per second
                        return price
                    else:
                        logging.info(f"No sell orders found for {item_name}")
                        await asyncio.sleep(0.35)
                        return None
                else:
                    logging.warning(f"API call failed for {item_name}: Status {response.status}")
                    await asyncio.sleep(0.35)
                    return None
        except Exception as e:
            logging.warning(f"Error fetching price for {item_name}: {e}")
            await asyncio.sleep(0.35)
            return None

async def fetch_platinum_prices(item_names: list) -> Dict[str, Optional[float]]:
    """Fetch platinum prices with persistent caching to avoid 429 errors"""
    global PLATINUM_CACHE, LAST_CACHE_UPDATE
    
    current_time = time.time()
    prices = {}
    
    # Check if we need to refresh cache
    if current_time - LAST_CACHE_UPDATE > CACHE_EXPIRY:
        logging.info("Price cache expired, will refresh prices for new items")
        cache_expired = True
    else:
        cache_expired = False
    
    # Common item name mappings for warframe.market
    name_mappings = {
        "Zylok Prime Blueprint": "zylok_prime_blueprint",
        "Revenant Prime Neuroptics Blueprint": "revenant_prime_neuroptics",
        "Phantasma Prime Blueprint": "phantasma_prime_blueprint", 
        "Afuris Prime Blueprint": "afuris_prime_blueprint",
        "Gunsen Prime Blueprint": "gunsen_prime_blueprint",
        "Forma Blueprint": "forma_blueprint",
        "2X Forma Blueprint": "forma_blueprint"
    }
    
    # Separate cached and uncached items
    uncached_items = []
    uncached_names = []
    
    for item_name in item_names:
        if not cache_expired and item_name in PLATINUM_CACHE:
            # Use cached price if cache is still valid
            prices[item_name] = PLATINUM_CACHE[item_name]
        elif any(skip in item_name.lower() for skip in ['forma blueprint']):
            # Forma blueprints are always 0 value
            prices[item_name] = 0.0
            PLATINUM_CACHE[item_name] = 0.0
        else:
            # Need to fetch this item
            if item_name in name_mappings:
                api_name = name_mappings[item_name]
            else:
                api_name = sanitize_item_name_for_api(item_name)
            
            uncached_items.append((item_name, api_name))
            uncached_names.append(item_name)
    
    # Fetch uncached items with concurrency control
    if uncached_items:
        logging.info(f"Fetching prices for {len(uncached_items)} items...")
        sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        
        async with aiohttp.ClientSession() as session:
            tasks = [
                fetch_price_concurrent(session, sem, item_name, api_name)
                for item_name, api_name in uncached_items
            ]
            
            results = await asyncio.gather(*tasks)
            
            # Store results in cache and prices dict
            for item_name, result in zip(uncached_names, results):
                prices[item_name] = result
                PLATINUM_CACHE[item_name] = result
        
        # Update cache timestamp and save to disk
        LAST_CACHE_UPDATE = current_time
        save_price_cache()
        logging.info(f"Updated cache with {len(uncached_items)} new prices")
    
    return prices

def calculate_relic_value(relic_name: str, relic_data: dict, platinum_prices: dict) -> float:
    """Calculate the expected platinum value of a relic"""
    if 'drops' not in relic_data:
        return 0.0
        
    drops = relic_data['drops']
    if not drops:
        return 0.0
    
    total_value = 0.0
    for drop in drops:
        price = platinum_prices.get(drop)
        if price is not None and price > 0:
            total_value += price
    
    return round(total_value / len(drops), 1) if drops else 0.0

def parse_relic_file(filepath):
    """Parse user relic file and return a flattened dictionary"""
    relic_dict = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logging.error(f"Error reading file {filepath}: {e}")
        return {}

    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if 'Found' in line or line.strip() == '' or ':' not in line:
            continue
        
        match = re.match(r'^(.+?)\s*:\s*(\d+)\s*pcs?\s*$', line)
        if match:
            relic_name = match.group(1).strip()
            count = int(match.group(2))
            normalized_name = normalize_relic_name(relic_name)
            
            relic_dict[normalized_name] = {
                'count': count,
                'original_name': relic_name,
                'normalized_name': normalized_name
            }

    logging.info(f"Parsed {len(relic_dict)} relics from {filepath}")
    return relic_dict

def get_latest_relic_file(identifier):
    """Get the latest relic file for a user identifier from the relics directory"""
    patterns = [
        os.path.join(RELICS_DIR, f"relics_{identifier}_*.txt"),
        os.path.join(RELICS_DIR, f"relics_*{identifier}*.txt"),
    ]

    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))

    if not files:
        return None

    return max(files, key=os.path.getctime)

# FIXED BINARY PARSING FUNCTIONS
def parse_relic_data(binary_data):
    """Parse binary relic data from API - FIXED VERSION"""
    relics = []
    
    try:
        # Validate minimum data length
        if len(binary_data) < 4:
            logging.warning("Binary data too short to read number of relics")
            return relics
            
        # First 4 bytes: number of relics (little-endian unsigned int)
        (num_relics,) = struct.unpack('<I', binary_data[0:4])
        logging.info(f"Parsing {num_relics} relics from binary data")
        
        # Sanity check
        if num_relics > 10000:  # Reasonable upper limit
            logging.warning(f"Suspicious number of relics: {num_relics}, limiting to 1000")
            num_relics = min(num_relics, 1000)
        
        offset = 4
        for i in range(num_relics):
            # Each relic should be at least 9 bytes: type(1) + refinement(1) + name(3) + count(4)
            if offset + 9 > len(binary_data):
                logging.warning(f"Incomplete data for relic #{i+1}, stopping parse at offset {offset}")
                break
            
            try:
                relic_type = binary_data[offset]
                refinement = binary_data[offset + 1]
                
                # Name is 3 bytes, decode and clean
                name_bytes = binary_data[offset + 2:offset + 5]
                relic_code = name_bytes.decode('ascii', errors='ignore').strip('\x00').strip()
                
                # Count is 4 bytes (little-endian unsigned int)
                (count,) = struct.unpack('<I', binary_data[offset + 5:offset + 9])
                
                # Sanity check on count
                if count > 999999:  # Reasonable upper limit for relic count
                    logging.warning(f"Suspicious relic count {count} for relic #{i+1}, skipping")
                    offset += 9
                    continue
                
                relics.append({
                    'type': relic_type,
                    'refinement': refinement,
                    'name': relic_code,
                    'count': count
                })
                
                offset += 9  # Move to next relic
                
            except (struct.error, UnicodeDecodeError) as e:
                logging.warning(f"Error parsing relic #{i+1} at offset {offset}: {e}")
                break
        
        logging.info(f"Successfully parsed {len(relics)} relics")
        return relics
        
    except Exception as e:
        logging.error(f"Critical error parsing binary relic data: {e}")
        return relics

def format_relic_data(relics):
    """Format relic data for text output - ENHANCED VERSION"""
    if not relics:
        return "No relic data found"
    
    # Enhanced mappings with more comprehensive coverage
    relic_map = {
        0: "Lith", 1: "Meso", 2: "Neo", 3: "Axi", 10: "Requiem",
        # Add more mappings if discovered
        4: "Unknown_Era", 5: "Unknown_Era", 6: "Unknown_Era", 7: "Unknown_Era", 8: "Unknown_Era", 9: "Unknown_Era",
        11: "Unknown_Requiem", 12: "Unknown_Special"
    }
    
    refinement_map = {
        0: "Intact", 1: "Exceptional", 2: "Flawless", 3: "Radiant",
        # Add more mappings for unknown values
        4: "Unknown_Ref", 5: "Unknown_Ref", 6: "Unknown_Ref", 7: "Unknown_Ref"
    }

    lines = []
    lines.append(f"Found {len(relics)} relic types:")
    
    for relic in relics:
        try:
            relic_tier = relic_map.get(relic['type'], f"Unknown_Type({relic['type']})")
            refinement = refinement_map.get(relic['refinement'], f"Unknown_Ref({relic['refinement']})")
            
            relic_name = relic['name'].strip()
            count = relic['count']
            
            if relic['type'] == 10:  # Requiem relics
                formatted_name = f"{relic_tier} {relic_name}"
            else:
                formatted_name = f"{relic_tier} {relic_name} - {refinement}"
            
            lines.append(f"{formatted_name} : {count} pcs")
            
        except Exception as e:
            logging.warning(f"Error formatting relic {relic}: {e}")
            lines.append(f"Error_Relic : 0 pcs")

    return "\n".join(lines)

def generate_full_detailed_report_with_platinum(user_data, relic_drops, vaulted_relics, users, user_names, platinum_prices, relic_values):
    """Generate detailed comparison report with platinum values"""
    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("WARFRAME RELIC COMPARISON REPORT WITH PLATINUM VALUES")
    report_lines.append("=" * 70)

    display_names = [user_names[user_id] for user_id in users]
    report_lines.append(f"Users: {', '.join(display_names)}")
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Prices fetched from warframe.market")
    report_lines.append("")

    # Summary statistics
    total_potential_value = sum(value for _, value in relic_values)
    avg_value = round(total_potential_value / len(relic_values), 1) if relic_values else 0
    vaulted_count = sum(1 for relic, _ in relic_values 
                       if relic in vaulted_relics or relic_drops.get(relic, {}).get('vaulted', False))

    report_lines.append(f"Total common relics: {len(relic_values)}")
    report_lines.append(f"Average relic value: {avg_value}p")
    report_lines.append(f"Highest value relic: {relic_values[0][1]}p" if relic_values else "No valued relics")
    report_lines.append(f"Vaulted relics: {vaulted_count}")
    report_lines.append(f"Available relics: {len(relic_values) - vaulted_count}")
    report_lines.append("")

    # Top 10 most valuable relics
    report_lines.append("TOP 10 MOST VALUABLE RELICS")
    report_lines.append("-" * 50)
    for i, (relic, value) in enumerate(relic_values[:10]):
        is_vaulted = relic in vaulted_relics or relic_drops.get(relic, {}).get('vaulted', False)
        vault_status = "🔒 VAULTED" if is_vaulted else "✅ Available"
        report_lines.append(f"{i+1:2d}. {relic} - {value}p - {vault_status}")
    report_lines.append("")

    # Detailed relic information (sorted by value)
    report_lines.append("DETAILED RELIC ANALYSIS (SORTED BY PLATINUM VALUE)")
    report_lines.append("=" * 70)

    for relic, plat_value in relic_values:
        is_vaulted = relic in vaulted_relics or relic_drops.get(relic, {}).get('vaulted', False)
        vault_status = "🔒 VAULTED" if is_vaulted else "✅ Available"
        
        report_lines.append(f"\n{relic} - {vault_status} - VALUE: {plat_value}p")
        report_lines.append("-" * 60)

        # Show drops with prices
        if relic in relic_drops:
            drops = relic_drops[relic].get('drops', [])
            if drops:
                report_lines.append("Possible Drops with Market Prices:")
                drop_values = []
                for drop in drops:
                    price = platinum_prices.get(drop, 0) or 0
                    drop_values.append((drop, price))
                
                drop_values.sort(key=lambda x: x[1], reverse=True)
                
                for drop, price in drop_values:
                    if price > 0:
                        report_lines.append(f" • {drop}: {price}p")
                    else:
                        report_lines.append(f" • {drop}: No market data")

        # Show user inventories
        report_lines.append("User Inventory:")
        for user_id in users:
            if relic in user_data[user_id]:
                count = user_data[user_id][relic]['count']
                display_name = user_names[user_id]
                original_name = user_data[user_id][relic]['original_name']
                total_potential = round(count * plat_value, 1)
                report_lines.append(f" {display_name}: {count} relics (potential: {total_potential}p) [{original_name}]")

    return "\n".join(report_lines)

def generate_full_detailed_report(user_data, relic_drops, vaulted_relics, users, user_names=None):
    """Generate a detailed comparison report with drops and vaulted status"""
    if user_names is None:
        user_names = {user_id: f"User_{user_id}" for user_id in users}

    report_lines = []
    report_lines.append("=" * 60)
    report_lines.append("WARFRAME RELIC COMPARISON REPORT")
    report_lines.append("=" * 60)

    display_names = [user_names[user_id] for user_id in users]
    report_lines.append(f"Users: {', '.join(display_names)}")
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")

    # Find common relics
    all_relics = set()
    for user_relics in user_data.values():
        all_relics.update(user_relics.keys())

    common_relics = set.intersection(*[set(rd.keys()) for rd in user_data.values()])

    report_lines.append(f"Total unique relics across all users: {len(all_relics)}")
    report_lines.append(f"Common relics (owned by all users): {len(common_relics)}")
    report_lines.append("")

    # Count vaulted vs available
    vaulted_count = 0
    available_count = 0

    for relic in common_relics:
        is_vaulted = relic in vaulted_relics or relic_drops.get(relic, {}).get('vaulted', False)
        if is_vaulted:
            vaulted_count += 1
        else:
            available_count += 1

    report_lines.append(f"Vaulted relics: {vaulted_count}")
    report_lines.append(f"Available relics: {available_count}")
    report_lines.append("")

    # Group by relic type
    relic_types = {}
    for relic in sorted(common_relics):
        relic_type = relic.split()[0]
        if relic_type not in relic_types:
            relic_types[relic_type] = []
        relic_types[relic_type].append(relic)

    for relic_type in sorted(relic_types.keys()):
        report_lines.append(f"\n{relic_type.upper()} RELICS ({len(relic_types[relic_type])})")
        report_lines.append("-" * 50)

        for relic in sorted(relic_types[relic_type]):
            is_vaulted = relic in vaulted_relics or relic_drops.get(relic, {}).get('vaulted', False)
            vaulted_status = "🔒 VAULTED" if is_vaulted else "✅ Available"

            report_lines.append(f"\n{relic} - {vaulted_status}")

            # Show drops if available
            if relic in relic_drops:
                drops = relic_drops[relic].get('drops', [])
                if drops:
                    report_lines.append(" Possible Drops:")
                    for drop in drops:
                        report_lines.append(f" • {drop}")

            # Show user counts with display names
            report_lines.append(" User Inventory:")
            for user_id in users:
                if relic in user_data[user_id]:
                    count = user_data[user_id][relic]['count']
                    display_name = user_names[user_id]
                    original_name = user_data[user_id][relic]['original_name']
                    report_lines.append(f" {display_name}: {count} ({original_name})")

    return "\n".join(report_lines)

class Pagination(View):
    def __init__(self, interaction, user_data, relic_drops, vaulted_relics, users):
        super().__init__(timeout=300)
        self.interaction = interaction
        self.user_data = user_data
        self.relic_drops = relic_drops
        self.vaulted_relics = vaulted_relics
        self.users = users
        
        # Get common relics
        self.common_relics = list(set.intersection(*[set(rd.keys()) for rd in user_data.values()]))
        self.common_relics.sort()
        
        # Pagination settings
        self.relics_per_page = 8
        self.total_pages = max(1, (len(self.common_relics) + self.relics_per_page - 1) // self.relics_per_page)
        self.page = 0
        
        # Platinum prices (will be set if available)
        self.platinum_prices = {}

    def create_embed(self):
        start_idx = self.page * self.relics_per_page
        end_idx = min(start_idx + self.relics_per_page, len(self.common_relics))

        # Check if we have platinum data
        has_platinum = hasattr(self, 'platinum_prices') and self.platinum_prices
        title_prefix = "💰 Relic Comparison (by Platinum Value)" if has_platinum else "🔍 Relic Comparison"
        
        embed = Embed(
            title=f"{title_prefix} - Page {self.page + 1}/{self.total_pages}",
            color=0x4CAF50
        )

        embed.set_footer(text=f"Showing {start_idx + 1}-{end_idx} of {len(self.common_relics)} common relics")

        if not self.common_relics:
            embed.description = "❌ No common relics found among all users."
            return embed

        description_lines = []

        for i in range(start_idx, end_idx):
            if i >= len(self.common_relics):
                break

            # Handle both tuple format (relic, value) and string format
            if isinstance(self.common_relics[i], tuple):
                relic = self.common_relics[i][0]
                plat_value = self.common_relics[i][1]
            else:
                relic = self.common_relics[i]
                plat_value = 0.0

            # Check vaulted status
            is_vaulted = relic in self.vaulted_relics or self.relic_drops.get(relic, {}).get('vaulted', False)
            vault_emoji = "🔒" if is_vaulted else "✅"
            vault_text = "VAULTED" if is_vaulted else "Available"

            # Get user counts
            counts = []
            for user_id in self.users:
                if relic in self.user_data[user_id]:
                    count = self.user_data[user_id][relic]['count']
                    counts.append(f"<@{user_id}>: {count}")

            counts_str = " | ".join(counts) if counts else "No data"

            # Get drops info with prices if available
            drops_info = ""
            if relic in self.relic_drops:
                drops = self.relic_drops[relic].get('drops', [])
                if drops and has_platinum:
                    # Show most valuable drops first
                    drop_values = []
                    for drop in drops:
                        price = self.platinum_prices.get(drop, 0) or 0
                        drop_values.append((drop, price))
                    
                    drop_values.sort(key=lambda x: x[1], reverse=True)
                    top_drops = drop_values[:2]
                    
                    drops_preview = []
                    for drop, price in top_drops:
                        if price > 0:
                            drops_preview.append(f"{drop} ({price}p)")
                        else:
                            drops_preview.append(drop)
                    
                    drops_info = f"\n 🎁 {', '.join(drops_preview)}"
                    if len(drops) > 2:
                        drops_info += f" (+{len(drops)-2} more)"
                elif drops:
                    # Show first 2 drops without prices
                    drops_preview = drops[:2]
                    drops_info = f"\n 🎁 {', '.join(drops_preview)}"
                    if len(drops) > 2:
                        drops_info += f" (+{len(drops)-2} more)"

            # Format platinum value if available
            plat_display = ""
            if has_platinum and plat_value > 0:
                plat_display = f" - 💰 ~{plat_value}p avg"
            elif has_platinum:
                plat_display = " - 💰 Low value"

            description_lines.append(
                f"{vault_emoji} **{relic}** ({vault_text}){plat_display}\n"
                f" 📊 {counts_str}{drops_info}"
            )

        embed.description = "\n\n".join(description_lines)
        return embed

    async def interaction_check(self, interaction) -> bool:
        if interaction.user == self.interaction.user:
            return True
        else:
            await interaction.response.send_message("Only the command invoker can control this.", ephemeral=True)
            return False

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):
        self.page = (self.page - 1) % self.total_pages
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def forward(self, interaction, button):
        self.page = (self.page + 1) % self.total_pages
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

# API processing code
API_KEY_PATTERN = re.compile(r'([A-Za-z0-9+/=_-]+(?:\n[A-Za-z0-9+/=_-]*)*)', re.MULTILINE)
pending_verifications = {}

class OwnershipVerificationView(View):
    def __init__(self, api_key, requester_id, requester_name):
        super().__init__(timeout=300)
        self.api_key = api_key
        self.requester_id = requester_id
        self.requester_name = requester_name

    @discord.ui.button(label="✅ This is MY API key", style=ButtonStyle.green, emoji="🔐")
    async def confirm_my_api(self, interaction, button):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "❌ Only the person who posted the API key can confirm this!", ephemeral=True)
            return

        await interaction.response.edit_message(content="✅ Ownership confirmed! Processing your relic data...", view=None)
        await self.process_api_key(interaction, self.api_key, interaction.user, is_own_data=True)

        if self.api_key in pending_verifications:
            del pending_verifications[self.api_key]

    @discord.ui.button(label="👥 This is SOMEONE ELSE's API key", style=ButtonStyle.secondary, emoji="🔍")
    async def confirm_others_api(self, interaction, button):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "❌ Only the person who posted the API key can confirm this!", ephemeral=True)
            return

        await interaction.response.edit_message(
            content="👥 Checking someone else's data. Processing without saving to your profile...", view=None)
        await self.process_api_key(interaction, self.api_key, interaction.user, is_own_data=False)

        if self.api_key in pending_verifications:
            del pending_verifications[self.api_key]

    @discord.ui.button(label="❌ Cancel", style=ButtonStyle.red, emoji="🚫")
    async def cancel_verification(self, interaction, button):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "❌ Only the person who posted the API key can cancel this!", ephemeral=True)
            return

        await interaction.response.edit_message(content="❌ API key processing cancelled.", view=None)

        if self.api_key in pending_verifications:
            del pending_verifications[self.api_key]

    async def on_timeout(self):
        if self.api_key in pending_verifications:
            del pending_verifications[self.api_key]

    async def process_api_key(self, interaction, api_key, user, is_own_data=True):
        try:
            relics = fetch_relic_data(api_key)
            formatted_data = format_relic_data(relics)

            safe_username = re.sub(r'[^a-zA-Z0-9_-]', '_', user.display_name)
            timestamp = interaction.created_at.strftime('%Y%m%d_%H%M%S')

            if is_own_data:
                filename = os.path.join(RELICS_DIR, f"relics_{user.id}_{safe_username}_{timestamp}.txt")
                save_message = f"✅ {user.mention} Your relic inventory has been saved and will auto-update every 6 hours!"
                
                # Save the API token for automatic updates
                if save_user_token(str(user.id), api_key, safe_username):
                    save_message += f"\n🔄 **Auto-updates enabled** - Your relic data will refresh automatically."
                else:
                    save_message += f"\n⚠️ Could not enable auto-updates. Manual updates will still work."
                    
            else:
                filename = os.path.join(TEMP_DIR, f"relic_check_{safe_username}_{timestamp}.txt")
                save_message = f"👥 {user.mention} Someone else's relic data (not saved to your profile):"

            with open(filename, 'w', encoding='utf-8') as f:
                f.write(formatted_data)

            logging.info(f"Relic data saved to {filename} (own_data: {is_own_data})")
            await interaction.followup.send(save_message, file=File(filename))

        except requests.exceptions.RequestException as e:
            logging.error(f"API request error: {e}")
            await interaction.followup.send(f"❌ Error fetching data from Alecaframe API: {e}")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            await interaction.followup.send(f"❌ An unexpected error occurred: {e}")

def fetch_relic_data(public_token):
    """Fetch relic data from Alecaframe API"""
    clean_token = ''.join(public_token.split())

    possible_endpoints = [
        "https://stats.alecaframe.com/api/v1/relic/inventory",
        "https://stats.alecaframe.com/api/stats/public/getRelicInventory",
        "https://stats.alecaframe.com/api/relic/inventory"
    ]

    for url in possible_endpoints:
        try:
            params = {'publicToken': clean_token}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                logging.info(f"Success with endpoint: {url}")
                break
        except requests.RequestException:
            continue
    else:
        response.raise_for_status()

    b64_data = response.text.strip().strip('"')
    missing_padding = len(b64_data) % 4
    if missing_padding:
        b64_data += '=' * (4 - missing_padding)

    binary_blob = base64.b64decode(b64_data)
    return parse_relic_data(binary_blob)

# Bot commands
@bot.tree.command(name="compare", description="Compare relic inventories by platinum value with vaulted status and drops")
async def compare(
    interaction: discord.Interaction,
    user1: str,
    user2: str = None,
    user3: str = None,
    user4: str = None
):
    await interaction.response.defer()

    users = [user1]
    if user2:
        users.append(user2)
    if user3:
        users.append(user3)
    if user4:
        users.append(user4)

    if len(users) < 2:
        await interaction.followup.send("❌ Need at least 2 users to compare!")
        return

    # Load user data
    user_data = {}
    for u in users:
        fpath = get_latest_relic_file(u)
        if not fpath:
            await interaction.followup.send(f"❌ Could not find relic profile for user: {u}")
            return
        user_data[u] = parse_relic_file(fpath)

    # Find common relics
    common = set.intersection(*[set(rd.keys()) for rd in user_data.values()])
    if not common:
        await interaction.followup.send("❌ No common relics found among users.")
        return

    relic_drops = get_relic_contents()
    vaulted_relics = {name for name, data in relic_drops.items() if data.get('vaulted', False)}

    # Fetch platinum prices for all items in common relics
    await interaction.followup.send("💰 Fetching current platinum prices... This may take a moment.")
    
    all_items = set()
    for relic in common:
        if relic in relic_drops:
            all_items.update(relic_drops[relic].get('drops', []))
    
    platinum_prices = await fetch_platinum_prices(list(all_items))
    
    # Calculate relic values and sort by value
    relic_values = []
    for relic in common:
        relic_data = relic_drops.get(relic, {})
        value = calculate_relic_value(relic, relic_data, platinum_prices)
        relic_values.append((relic, value))
    
    # Sort by platinum value (highest first)
    relic_values.sort(key=lambda x: x[1], reverse=True)

    # Count vaulted vs available
    vaulted_common = sum(1 for relic, _ in relic_values 
                        if relic in vaulted_relics or relic_drops.get(relic, {}).get('vaulted', False))
    available_common = len(relic_values) - vaulted_common

    # Create summary embed with platinum info
    display_mentions = [f"<@{user_id}>" for user_id in users]
    total_potential_value = sum(value for _, value in relic_values)
    avg_value = round(total_potential_value / len(relic_values), 1) if relic_values else 0

    summary_embed = Embed(title="💰 Relic Comparison Summary (by Platinum Value)", color=0x2196F3)
    summary_embed.add_field(name="👥 Users", value=", ".join(display_mentions), inline=False)
    summary_embed.add_field(name="📦 Total Common Relics", value=str(len(relic_values)), inline=True)
    summary_embed.add_field(name="🔒 Vaulted Relics", value=str(vaulted_common), inline=True)
    summary_embed.add_field(name="✅ Available Relics", value=str(available_common), inline=True)
    summary_embed.add_field(name="💰 Avg. Relic Value", value=f"{avg_value}p", inline=True)
    summary_embed.add_field(name="💎 Top Relic Value", value=f"{relic_values[0][1]}p" if relic_values else "0p", inline=True)

    await interaction.followup.send(embed=summary_embed)

    # Create enhanced pagination with platinum data
    paginator = Pagination(interaction, user_data, relic_drops, vaulted_relics, users)
    paginator.common_relics = relic_values  # Now contains (relic, value) tuples
    paginator.platinum_prices = platinum_prices  # Add platinum prices to paginator
    
    await interaction.followup.send(embed=paginator.create_embed(), view=paginator)

    # Generate enhanced report with platinum values
    try:
        user_names = {}
        for user_id in users:
            try:
                user = await bot.fetch_user(int(user_id))
                user_names[user_id] = user.display_name or user.global_name or user.name
            except:
                user_names[user_id] = f"User_{user_id}"

        # Pass platinum data to report function
        report_text = generate_full_detailed_report_with_platinum(
            user_data, relic_drops, vaulted_relics, users, user_names, 
            platinum_prices, relic_values
        )
        
        display_names = [user_names[user_id] for user_id in users]
        filename = os.path.join(REPORTS_DIR, f"plat_comparison_{'_vs_'.join(display_names)}_{interaction.created_at.strftime('%Y%m%d_%H%M%S')}.txt")
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_text)
            
        await interaction.followup.send("📄 Full detailed platinum comparison report:", file=File(filename))

    except Exception as e:
        logging.error(f"Error generating platinum report: {e}")
        await interaction.followup.send("⚠️ Comparison completed, but there was an error creating the detailed report file.")

@bot.tree.command(name="update_relics", description="Admin command to update relic data from external sources")
async def update_relics(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need admin permissions to run this command.", ephemeral=True)
        return

    await interaction.response.defer()

    loop = asyncio.get_event_loop()
    try:
        total_relics, vaulted_count = await loop.run_in_executor(None, fetch_and_save_relic_data)

        # Reload relic data in bot memory after update
        if load_relic_data():
            await interaction.followup.send(f"✅ Relic data updated! Total relics: {total_relics}, Vaulted: {vaulted_count}")
        else:
            await interaction.followup.send("⚠️ Updated relic_data.json but failed to reload in bot memory.")
    except Exception as e:
        await interaction.followup.send(f"❌ Update failed: {e}")

@bot.event
async def on_ready():
    logging.info(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    logging.info(f"Monitoring channels: {', '.join(str(cid) for cid in ALLOWED_CHANNEL_IDS)}")

    # Load relic data
    if load_relic_data():
        logging.info("✅ Relic data loaded successfully")
    else:
        logging.error("❌ Failed to load relic data")

    # Load price cache
    load_price_cache()

    # Start auto-update task
    auto_update_user_relics.start()
    logging.info("🔄 Auto-update task started")

    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} commands")
    except Exception as e:
        logging.error(f"Failed to sync commands: {e}")

    logging.info("------")

def load_price_cache():
    """Load platinum price cache from disk"""
    global PLATINUM_CACHE, LAST_CACHE_UPDATE
    
    try:
        if os.path.exists(PRICE_CACHE_FILE):
            with open(PRICE_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            PLATINUM_CACHE = cache_data.get('prices', {})
            LAST_CACHE_UPDATE = cache_data.get('last_update', 0)
            
            # Check if cache is still valid
            current_time = time.time()
            if current_time - LAST_CACHE_UPDATE > CACHE_EXPIRY:
                logging.info("Loaded price cache is expired, will refresh on next use")
                PLATINUM_CACHE.clear()
                LAST_CACHE_UPDATE = 0
            else:
                cache_age_minutes = int((current_time - LAST_CACHE_UPDATE) / 60)
                logging.info(f"Loaded {len(PLATINUM_CACHE)} cached prices ({cache_age_minutes} minutes old)")
                
        else:
            logging.info("No price cache file found, starting with empty cache")
            PLATINUM_CACHE = {}
            LAST_CACHE_UPDATE = 0
            
    except Exception as e:
        logging.error(f"Error loading price cache: {e}")
        PLATINUM_CACHE = {}
        LAST_CACHE_UPDATE = 0

def generate_or_load_key():
    """Generate or load encryption key for storing API tokens"""
    if os.path.exists(TOKEN_KEY_FILE):
        with open(TOKEN_KEY_FILE, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(TOKEN_KEY_FILE, 'wb') as f:
            f.write(key)
        return key

def encrypt_token(token: str) -> str:
    """Encrypt API token for secure storage"""
    key = generate_or_load_key()
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt stored API token"""
    key = generate_or_load_key()
    f = Fernet(key)
    return f.decrypt(encrypted_token.encode()).decode()

def save_user_token(user_id: str, api_token: str, username: str):
    """Save user's API token for automatic updates"""
    try:
        if os.path.exists(USER_TOKENS_FILE):
            with open(USER_TOKENS_FILE, 'r', encoding='utf-8') as f:
                user_tokens = json.load(f)
        else:
            user_tokens = {}
        
        user_tokens[user_id] = {
            'token': encrypt_token(api_token),
            'username': username,
            'last_updated': time.time()
        }
        
        with open(USER_TOKENS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_tokens, f, indent=2)
        
        logging.info(f"Saved API token for user {username} ({user_id})")
        return True
    except Exception as e:
        logging.error(f"Error saving user token: {e}")
        return False

def load_user_tokens():
    """Load all stored user tokens"""
    try:
        if os.path.exists(USER_TOKENS_FILE):
            with open(USER_TOKENS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logging.error(f"Error loading user tokens: {e}")
        return {}

def get_user_token(user_id: str) -> str:
    """Get decrypted API token for a user"""
    try:
        user_tokens = load_user_tokens()
        if user_id in user_tokens:
            return decrypt_token(user_tokens[user_id]['token'])
        return None
    except Exception as e:
        logging.error(f"Error getting user token: {e}")
        return None

@tasks.loop(hours=6)  # Update every 6 hours
async def auto_update_user_relics():
    """Automatically update all users' relic data"""
    user_tokens = load_user_tokens()
    
    if not user_tokens:
        logging.info("No stored user tokens for auto-update")
        return
    
    logging.info(f"Starting auto-update for {len(user_tokens)} users")
    
    for user_id, token_data in user_tokens.items():
        try:
            api_token = decrypt_token(token_data['token'])
            username = token_data['username']
            
            # Fetch updated relic data
            relics = fetch_relic_data(api_token)
            formatted_data = format_relic_data(relics)
            
            # Save updated data
            safe_username = re.sub(r'[^a-zA-Z0-9_-]', '_', username)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(RELICS_DIR, f"relics_{user_id}_{safe_username}_{timestamp}.txt")
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(formatted_data)
            
            logging.info(f"Auto-updated relic data for {username} ({user_id})")
            
            # Small delay between users to avoid rate limits
            await asyncio.sleep(2)
            
        except Exception as e:
            logging.error(f"Error auto-updating for user {user_id}: {e}")
    
    logging.info("Auto-update completed")

@auto_update_user_relics.before_loop
async def before_auto_update():
    await bot.wait_until_ready()

def save_price_cache():
    """Save platinum price cache to disk"""
    try:
        cache_data = {
            'prices': PLATINUM_CACHE,
            'last_update': LAST_CACHE_UPDATE
        }
        
        with open(PRICE_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
        logging.info(f"Saved {len(PLATINUM_CACHE)} prices to cache file")
        
    except Exception as e:
        logging.error(f"Error saving price cache: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id not in ALLOWED_CHANNEL_IDS:
        await bot.process_commands(message)
        return

    logging.info(f"Processing message in monitored channel from {message.author}")

    match = API_KEY_PATTERN.search(message.content)
    if not match:
        logging.info("No API key pattern found in message")
        await bot.process_commands(message)
        return

    api_key = match.group(1).strip()
    logging.info(f"Detected API key: {api_key[:8]}... (length: {len(api_key)})")

    if api_key in pending_verifications:
        await message.channel.send(f"⏳ This API key is already pending verification.")
        await bot.process_commands(message)
        return

    pending_verifications[api_key] = {
        'user_id': message.author.id,
        'timestamp': message.created_at
    }

    view = OwnershipVerificationView(api_key, message.author.id, message.author.display_name)
    embed_message = (
        f"🔐 **{message.author.mention} API Key Ownership Declaration**\n\n"
        f"Please declare whether this API key belongs to you or someone else:\n\n"
        f"🔐 **My API Key** - Data will be saved to your profile for comparisons\n"
        f"👥 **Someone Else's** - Data will be shown but NOT saved to your profile\n"
        f"🚫 **Cancel** - Stop processing\n\n"
        f"⚠️ **Important:** Only click 'My API Key' if this is YOUR personal Warframe account!"
    )

    await message.channel.send(embed=discord.Embed(description=embed_message, color=0xFF9800), view=view)
    await bot.process_commands(message)

# Additional slash commands
@bot.tree.command(name="remove_user_data", description="[ADMIN] Remove relic data for a user")
@discord.app_commands.describe(
    user_id="The Discord user ID to remove data for",
    reason="Reason for removal (optional)"
)
async def remove_user_data(interaction, user_id: str, reason: str = "Admin removal"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Administrator permission required to use this command.", ephemeral=True)
        return

    files_to_remove = glob.glob(os.path.join(RELICS_DIR, f"relics_{user_id}_*.txt"))
    removed_count = 0

    for file in files_to_remove:
        try:
            os.remove(file)
            removed_count += 1
            logging.warning(f"ADMIN REMOVAL: {interaction.user} removed {file} for user {user_id}. Reason: {reason}")
        except Exception as e:
            logging.error(f"Error removing {file}: {e}")

    await interaction.response.send_message(
        f"✅ Removed {removed_count} relic data files for user {user_id}.\nReason: {reason}\nAction logged for audit purposes."
    )

@bot.tree.command(name="list_users", description="List users who have relic data stored")
async def list_users(interaction):
    relic_files = glob.glob(os.path.join(RELICS_DIR, "relics_*.txt"))

    if not relic_files:
        await interaction.response.send_message("❌ No user profile relic data found.")
        return

    users = {}
    for file in relic_files:
        try:
            base_name = os.path.basename(file).replace('.txt', '')
            parts = base_name.split('_')

            if len(parts) < 3:
                continue

            user_id = parts[1]

            if len(parts) >= 5:
                username = parts[2]
                timestamp = f"{parts[3]}_{parts[4]}"
            elif len(parts) == 4:
                username = parts[2]
                timestamp = parts[3]
            else:
                username = f"User_{user_id}"
                timestamp = "unknown"

            if user_id not in users:
                users[user_id] = {'username': username, 'files': []}

            users[user_id]['files'].append((file, timestamp))

        except Exception as e:
            logging.warning(f"Error parsing filename {file}: {e}")
            continue

    if not users:
        await interaction.response.send_message("❌ No valid user profile relic data found.")
        return

    user_lines = ["# Users with Saved Relic Profiles\n"]

    for user_id, info in users.items():
        try:
            latest_file = max(info['files'], key=lambda x: x[1])
            user_lines.append(f"**{info['username']}** (ID: {user_id})")
            user_lines.append(f"- Latest: {latest_file[1]}")
            user_lines.append(f"- Total profiles: {len(info['files'])}\n")
        except Exception:
            user_lines.append(f"**{info['username']}** (ID: {user_id})")
            user_lines.append(f"- Profiles: {len(info['files'])}\n")

    await interaction.response.send_message('\n'.join(user_lines))

@bot.tree.command(name="status", description="Check bot status and monitored channel")
async def status_slash(interaction):
    if interaction.channel.id in ALLOWED_CHANNEL_IDS:
        relic_count = len(RELIC_DATA) if RELIC_DATA else 0
        cache_items = len(PLATINUM_CACHE)
        
        await interaction.response.send_message(
            f"✅ This channel is being monitored for API keys.\n"
            f"**Monitored Channel IDs:** {', '.join(str(cid) for cid in ALLOWED_CHANNEL_IDS)}\n"
            f"**Loaded Relics:** {relic_count}\n"
            f"**Cached Prices:** {cache_items}\n"
            f"**Available commands:** `/compare`, `/status`, `/list_users`, `/my_relics`\n"
            f"**Admin commands:** `/remove_user_data`, `/update_relics`"
        )
    else:
        await interaction.response.send_message(
            f"❌ This channel is NOT being monitored.\n"
            f"**Monitored Channel IDs:** {', '.join(str(cid) for cid in ALLOWED_CHANNEL_IDS)}"
        )

@bot.tree.command(name="clear_price_cache", description="[ADMIN] Clear the platinum price cache")
async def clear_price_cache(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Administrator permission required to use this command.", ephemeral=True)
        return

    global PLATINUM_CACHE, LAST_CACHE_UPDATE
    old_count = len(PLATINUM_CACHE)
    PLATINUM_CACHE.clear()
    LAST_CACHE_UPDATE = 0
    save_price_cache()

    await interaction.response.send_message(
        f"✅ Cleared {old_count} cached prices. Next comparison will fetch fresh prices.")

@bot.tree.command(name="cache_status", description="Show platinum price cache status")
async def cache_status(interaction: discord.Interaction):
    current_time = time.time()
    cache_age = current_time - LAST_CACHE_UPDATE if LAST_CACHE_UPDATE > 0 else 0
    cache_age_minutes = int(cache_age / 60)

    is_expired = cache_age > CACHE_EXPIRY
    status_emoji = "❌" if is_expired else "✅"

    embed = Embed(title="💰 Platinum Price Cache Status", color=0x4CAF50)
    embed.add_field(name="Cached Items", value=str(len(PLATINUM_CACHE)), inline=True)
    embed.add_field(name="Cache Age", value=f"{cache_age_minutes} minutes", inline=True)
    embed.add_field(name="Status", value=f"{status_emoji} {'Expired' if is_expired else 'Valid'}", inline=True)
    embed.add_field(name="Expiry", value="1 hour", inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="auto_update_status", description="Check your automatic update status")
async def auto_update_status(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_tokens = load_user_tokens()

    if user_id in user_tokens:
        token_data = user_tokens[user_id]
        last_updated = datetime.fromtimestamp(token_data['last_updated']).strftime('%Y-%m-%d %H:%M:%S')

        embed = Embed(title="🔄 Auto-Update Status", color=0x4CAF50)
        embed.add_field(name="Status", value="✅ Enabled", inline=True)
        embed.add_field(name="Username", value=token_data['username'], inline=True)
        embed.add_field(name="Token Saved", value=last_updated, inline=True)
        embed.add_field(name="Update Frequency", value="Every 6 hours", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(
            "❌ Auto-updates not enabled. Paste your API key to enable automatic updates.",
            ephemeral=True
        )

@bot.tree.command(name="disable_auto_update", description="Disable automatic relic data updates")
async def disable_auto_update(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_tokens = load_user_tokens()

    if user_id in user_tokens:
        del user_tokens[user_id]

        with open(USER_TOKENS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_tokens, f, indent=2)

        await interaction.response.send_message(
            "✅ Auto-updates disabled. Your stored API token has been removed.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "❌ Auto-updates were not enabled for your account.",
            ephemeral=True
        )

@bot.tree.command(name="my_relics", description="Show your saved relic profile data")
async def my_relics(interaction: discord.Interaction):
    user_id_str = str(interaction.user.id)

    fpath = get_latest_relic_file(user_id_str)
    if not fpath:
        await interaction.response.send_message(
            "❌ Could not find your relic data file associated with your Discord ID.",
            ephemeral=True)
        return

    relic_data = parse_relic_file(fpath)
    if not relic_data:
        await interaction.response.send_message(
            "❌ Your relic data appears empty or corrupted.",
            ephemeral=True)
        return

    lines = [f"Relic data for your profile:\n"]
    for relic, info in sorted(relic_data.items()):
        lines.append(f"- {relic}: {info['count']} pcs")

    text_content = "\n".join(lines)

    # Write to a temp file
    filename = f"relics_{user_id_str}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(text_content)

    await interaction.response.send_message(
        "📄 Here is your relic data:",
        file=File(filename),
        ephemeral=True
    )

    # Clean up the temp file after sending
    try:
        os.remove(filename)
    except Exception as e:
        print(f"Error deleting temp file {filename}: {e}")

@bot.tree.command(name="list_commands", description="Show all registered slash commands")
async def list_commands(interaction):
    cmds = [cmd.name for cmd in bot.tree.get_commands()]
    await interaction.response.send_message(
        "**Registered Commands:**\n" + "\n".join(f"• /{c}" for c in cmds)
    )

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)