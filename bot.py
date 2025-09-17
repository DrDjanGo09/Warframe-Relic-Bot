#  WARFRAME DISCORD BOT 

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
from datetime import datetime, timedelta
from typing import Dict, Optional, List

import discord
from discord import File, Intents, ButtonStyle, Embed
from discord.ui import View, Button
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# =============================================================================
# ENHANCED CONFIGURATION AND CONSTANTS
# =============================================================================

# Enemy faction icons for fissures
ENEMY_FACTION_ICONS = {
    "grineer": "⚔️",        # Crossed swords
    "corpus": "💰",         # Money bag
    "infested": "🦠",       # Microbe
    "corrupted": "☠️",      # Skull and crossbones
    "sentient": "🤖",       # Robot face
    "orokin": "👑",         # Crown
}

# Relic tier icons - universal emoji substitutes
RELIC_TIER_ICONS = {
    "lith": "🥉",           # Bronze medal
    "meso": "🥈",           # Silver medal
    "neo": "🥇",            # Gold medal
    "axi": "💎",            # Gem stone
    "requiem": "🔮",         # Crystal ball
    "omnia": "🧿"            # Nazar amulet
}

# Mission type icons - universal emojis
MISSION_TYPE_ICONS = {
    "normal": "🔹",          # Small blue diamond
    "steel_path": "🔥",      # Fire for Steel Path
    "railjack": "🚀",       # Rocket for Railjack/Void Storms
    "void_storm": "⚡"       # Lightning bolt for Void Storms
}

# Cycle location icons for visual distinction with universal emojis
CYCLE_LOCATION_ICONS = {
    "cetus": {
        "day": "☀️",
        "night": "🌙"
    },
    "fortuna": {
        "warm": "🔥",
        "cold": "❄️"
    },
    "deimos": {
        "fass": "🦠",        # Substitute for infested factions
        "vome": "👾"         # Alien monster emoji for vome
    },
    "zariman": {
        "grineer": "⚔️",
        "corpus": "💰"
    },
    "duviri": "🎭"           # Performing arts mask for Duviri
}

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

# Global variables for relic system
RELIC_DATA = {}
PLATINUM_CACHE = {}
CACHE_EXPIRY = 3600  # 1 hour in seconds
LAST_CACHE_UPDATE = 0

# Rate limiting for warframe.market API
MAX_CONCURRENT_REQUESTS = 3  # Max 3 concurrent requests to respect rate limits

# Persistent price cache configuration
PRICE_CACHE_FILE = "platinum_price_cache.json"

# Global variables for Warframe information system
warframe_data_manager = None
subscription_manager = None
embed_generator = None
notification_manager = None
channel_manager = None

# =============================================================================
# ENHANCED TIME UTILITY FUNCTIONS
# =============================================================================

def parse_warframe_time_to_discord_timestamp(time_string):
    """
    Convert Warframe API time strings to Discord timestamp format
    Examples: "2h 34m 12s", "1d 5h 23m", "45m 12s" -> Discord timestamps
    """
    # Add debug logging
    logging.info(f"DEBUG: Raw time string received: '{time_string}' (type: {type(time_string)})")
    
    if not time_string or time_string == "Unknown" or time_string is None:
        logging.warning(f"DEBUG: Invalid time string: {time_string}")
        return "Unknown"

    # Parse the time string to extract hours, minutes, seconds
    hours = 0
    minutes = 0
    seconds = 0

    # Extract time components using regex
    time_parts = re.findall(r'(\d+)([dhms])', time_string.lower())
    logging.info(f"DEBUG: Parsed time parts: {time_parts}")
    
    for value, unit in time_parts:
        value = int(value)
        if unit == 'd':
            hours += value * 24
        elif unit == 'h':
            hours += value
        elif unit == 'm':
            minutes += value
        elif unit == 's':
            seconds += value

    # Calculate total seconds from now
    total_seconds = hours * 3600 + minutes * 60 + seconds
    logging.info(f"DEBUG: Total seconds calculated: {total_seconds}")
    
    if total_seconds <= 0:
        logging.warning(f"DEBUG: Invalid total seconds: {total_seconds}")
        return time_string  # Return raw string if parsing failed

    # Get current timestamp and add the duration
    current_timestamp = int(datetime.now().timestamp())
    future_timestamp = current_timestamp + total_seconds

    # Return Discord timestamp format for relative time
    discord_timestamp = f"<t:{future_timestamp}:R>"
    logging.info(f"DEBUG: Generated Discord timestamp: {discord_timestamp}")
    return discord_timestamp
    
def calculate_eta_from_expiry(expiry_string):
        """Calculate time remaining from ISO timestamp"""
        if not expiry_string:
            return "Unknown"
    
        try:
            # Parse the ISO timestamp
            expiry_time = datetime.fromisoformat(expiry_string.replace('Z', '+00:00'))
            current_time = datetime.now(expiry_time.tzinfo)
        
            # Calculate difference
            time_diff = expiry_time - current_time
        
            if time_diff.total_seconds() <= 0:
                return "Expired"
        
            # Convert to hours, minutes, seconds format
            total_seconds = int(time_diff.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
        
            # Format as string
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
            
        except Exception as e:
            logging.error(f"Error calculating ETA from expiry: {e}")
            return "Unknown"

    
def get_enemy_faction_icon(enemy):
    """Get the appropriate icon for an enemy faction"""
    enemy_lower = enemy.lower()
    
    # Check for faction keywords in the enemy string
    if "grineer" in enemy_lower:
        return ENEMY_FACTION_ICONS["grineer"]
    elif "corpus" in enemy_lower:
        return ENEMY_FACTION_ICONS["corpus"]
    elif "infested" in enemy_lower:
        return ENEMY_FACTION_ICONS["infested"]
    elif "corrupted" in enemy_lower:
        return ENEMY_FACTION_ICONS["corrupted"]
    elif "sentient" in enemy_lower:
        return ENEMY_FACTION_ICONS["sentient"]
    elif "orokin" in enemy_lower:
        return ENEMY_FACTION_ICONS["orokin"]
    else:
        return "🏴"  # Default black flag for unknown factions


def get_relic_tier_icon(tier):
    """Get the appropriate icon for a relic tier"""
    return RELIC_TIER_ICONS.get(tier.lower(), "🔸")

def get_mission_type_icon(mission_type):
    """Get the appropriate icon for mission type"""
    if mission_type == "steel_path":
        return MISSION_TYPE_ICONS["steel_path"]
    elif mission_type == "railjack":
        return MISSION_TYPE_ICONS["railjack"]
    else:
        return MISSION_TYPE_ICONS["normal"]

# =============================================================================
# ENHANCED WARFRAME INFORMATION SYSTEM CLASSES
# =============================================================================

class WarframeDataManager:
    def __init__(self):
        # NEW: Multiple API endpoints for fallback
        self.api_endpoints = [
            {
                "name": "WFCD Primary",
                "base": "https://api.warframestat.us/pc",
                "type": "parsed",
                "status": "unknown"
            },
            {
                "name": "WFCD Console",
                "base": "https://api.warframestat.us/ps4",
                "type": "parsed",
                "status": "unknown"
            },
            {
                "name": "DE Raw Worldstate",
                "base": "https://content.warframe.com/dynamic/worldState.php",
                "type": "raw",
                "status": "unknown"
            }
        ]
        
        # Keep all your existing variables
        self.cache = {}
        self.cache_duration = 300
        self.last_fetch = {}
        
        # NEW: Add these for API tracking
        self.last_successful_api = None
        self.api_failure_count = {}
        
        for i, endpoint in enumerate(self.api_endpoints):
            self.api_failure_count[i] = 0

    # NEW: Add this method
    def get_current_api_status(self):
        """Get current API status for embed footers"""
        if self.last_successful_api is not None:
            api_info = self.api_endpoints[self.last_successful_api]
            return {
                "working": True,
                "message": f"Data from {api_info['name']}",
                "api_name": api_info['name']
            }
        else:
            return {
                "working": False, 
                "message": "⚠️ All Warframe APIs unavailable - Data may be outdated",
                "api_name": "None"
            }
       
    async def fetch_data(self, endpoint: str = "") -> Optional[Dict]:
        """Fetch data from Warframe APIs with fallback support"""
    
        cache_key = endpoint if endpoint else "root"
        if (cache_key in self.cache and
            cache_key in self.last_fetch and
            datetime.now() - self.last_fetch[cache_key] < timedelta(seconds=self.cache_duration)):
            return self.cache[cache_key]

        # Try each API endpoint in order
        for api_index in range(len(self.api_endpoints)):
            api_config = self.api_endpoints[api_index]
        
            if api_config["type"] == "parsed":
                url = f"{api_config['base']}/{endpoint}" if endpoint else api_config['base']
            else:
                url = api_config['base']
        
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status == 200:
                            data = await response.json()
                        
                            # Success! Update tracking
                            self.cache[cache_key] = data
                            self.last_fetch[cache_key] = datetime.now()
                            self.last_successful_api = api_index
                            self.api_failure_count[api_index] = 0
                            api_config["status"] = "working"
                        
                            logging.info(f"✅ Successfully fetched data from {api_config['name']}")
                            return data
                        else:
                            logging.warning(f"❌ {api_config['name']} returned status {response.status}")
                            api_config["status"] = f"error_{response.status}"
                        
            except Exception as e:
                logging.error(f"❌ {api_config['name']} failed: {e}")
                api_config["status"] = "failed"
                self.api_failure_count[api_index] += 1

        # All APIs failed
        logging.error("❌ All Warframe APIs failed to respond")
        self.last_successful_api = None
        return None
   
    async def get_cycles(self) -> Dict:
        """Get all cycle information"""
        data = await self.fetch_data()
        if not data:
            return {}
            
        return {
            "cetus": data.get("cetusCycle", {}),
            "fortuna": data.get("vallisCycle", {}),
            "deimos": data.get("cambionCycle", {}),
            "zariman": data.get("zarimanCycle", {}),
            "duviri": data.get("duviriCycle", {})
        }
    
    async def get_fissures(self, include_storms: bool = True) -> List[Dict]:
        """Get void fissure missions"""
        data = await self.fetch_data()
        if not data:
            return []
            
        fissures = data.get("fissures", [])
        
        if not include_storms:
            fissures = [f for f in fissures if not f.get("isStorm", False)]
            
        return fissures
    
    async def get_fissures_by_type(self) -> Dict[str, List[Dict]]:
        """Get fissures organized by type (normal, steel path, railjack)"""
        data = await self.fetch_data()
        if not data:
            return {"normal": [], "steel_path": [], "railjack": []}
        
        fissures = data.get("fissures", [])
        
        categorized = {
            "normal": [],
            "steel_path": [],
            "railjack": []
        }
        
        for fissure in fissures:
            if fissure.get("isStorm", False):
                categorized["railjack"].append(fissure)
            elif fissure.get("isHard", False):
                categorized["steel_path"].append(fissure)
            else:
                categorized["normal"].append(fissure)
        
        return categorized
    
    async def get_steel_path_info(self) -> Dict:
        """Get Steel Path incursions and rewards"""
        data = await self.fetch_data()
        if not data:
            return {}
            
        steel_path = data.get("steelPath", {})
        return steel_path
    
    async def get_arbitration(self) -> Dict:
        """Get current arbitration mission"""
        data = await self.fetch_data()
        if not data:
            return {}
        return data.get("arbitration", {})
    
    async def get_sortie(self) -> Dict:
        """Get current sortie missions"""
        data = await self.fetch_data()
        if not data:
            return {}
        return data.get("sortie", {})

class SubscriptionManager:
    """Manages user subscriptions for different events"""
    
    def __init__(self, bot):
        self.bot = bot
        self.subscriptions_file = "warframe_subscriptions.json"
        self.subscriptions = self.load_subscriptions()
        
    def load_subscriptions(self) -> Dict:
        """Load subscriptions from file"""
        try:
            if os.path.exists(self.subscriptions_file):
                with open(self.subscriptions_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logging.error(f"Error loading subscriptions: {e}")
        return {}
    
    def save_subscriptions(self):
        """Save subscriptions to file"""
        try:
            with open(self.subscriptions_file, 'w') as f:
                json.dump(self.subscriptions, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving subscriptions: {e}")
            
    def get_all_fissure_subscribers(self) -> Dict[int, str]:
        """Get all users subscribed to fissure missions with their filter details"""
        subscribers = {}
        for user_id_str, user_subs in self.subscriptions.items():
            if "fissure_missions" in user_subs:
                for sub in user_subs["fissure_missions"]:
                    subscribers[int(user_id_str)] = sub.get("details", "")
                    break  # Take the first/most recent subscription
        return subscribers
   
    def add_subscription(self, user_id: int, event_type: str, event_details: str = "") -> bool:
        """Add a subscription for a user"""
        user_id_str = str(user_id)
        
        if user_id_str not in self.subscriptions:
            self.subscriptions[user_id_str] = {}
            
        if event_type not in self.subscriptions[user_id_str]:
            self.subscriptions[user_id_str][event_type] = []
            
        subscription = {"details": event_details, "added": datetime.now().isoformat()}
        
        # Check if already subscribed
        for sub in self.subscriptions[user_id_str][event_type]:
            if sub.get("details") == event_details:
                return False  # Already subscribed
                
        self.subscriptions[user_id_str][event_type].append(subscription)
        self.save_subscriptions()
        return True
    
    def remove_subscription(self, user_id: int, event_type: str, event_details: str = "") -> bool:
        """Remove a subscription for a user"""
        user_id_str = str(user_id)

        # If user has never subscribed, nothing to remove
        if user_id_str not in self.subscriptions:
            return False

        # If they have no subscriptions for this event, nothing to remove
        user_subs = self.subscriptions[user_id_str]
        if event_type not in user_subs:
            return False

        original_count = len(user_subs[event_type])
        # Filter out matching details
        user_subs[event_type] = [
            sub for sub in user_subs[event_type]
            if sub.get("details") != event_details
        ]

        # Clean up if now empty
        if not user_subs[event_type]:
            del user_subs[event_type]
        if not user_subs:
            del self.subscriptions[user_id_str]

        self.save_subscriptions()
        # Return True if we removed at least one entry
        new_count = len(self.subscriptions.get(user_id_str, {}).get(event_type, []))
        return new_count < original_count

    
    def get_subscribers(self, event_type: str, event_details: str = "") -> List[int]:
        """Get all users subscribed to a specific event"""
        subscribers = []
        
        for user_id_str, user_subs in self.subscriptions.items():
            if event_type in user_subs:
                for sub in user_subs[event_type]:
                    if sub.get("details") == event_details:
                        subscribers.append(int(user_id_str))
                        break
                        
        return subscribers
    
    def get_user_subscriptions(self, user_id: int) -> Dict:
        """Get all subscriptions for a specific user"""
        user_id_str = str(user_id)
        return self.subscriptions.get(user_id_str, {})
        

class EmbedGenerator:
    """Enhanced embed generator with improved visuals and Discord timestamps"""

    @staticmethod
    def create_cycles_embed(cycles_data: Dict, api_status: dict = None) -> Embed:
        """Create enhanced embed for cycle information with Discord timestamps and API status footer"""
        embed = Embed(title="🌍 Warframe Open World Cycles", color=0x4CAF50)
        embed.timestamp = datetime.utcnow()

        # Debug log the entire cycles data
        logging.info(f"DEBUG: Full cycles_data: {cycles_data}")

        for location, cycle in cycles_data.items():
            if not cycle:
                continue

            location_name = location.title()
            if location == "cetus":
                location_name = "Plains of Eidolon"
            elif location == "fortuna":
                location_name = "Orb Vallis"
            elif location == "deimos":
                location_name = "Cambion Drift"
            elif location == "zariman":
                location_name = "Zariman Ten Zero"

            state = cycle.get("state", "Unknown")
            # NEW: Enhanced time_left extraction that handles missing timeLeft
            time_left = cycle.get("timeLeft")
            if not time_left and cycle.get("expiry"):
                time_left = calculate_eta_from_expiry(cycle.get("expiry"))
            else:
                time_left = time_left or "Unknown"

        
            # Debug log each cycle's data
            logging.info(f"DEBUG: {location} cycle - state: '{state}', timeLeft: '{time_left}'")

            # Get appropriate icon based on location and state
            if location in CYCLE_LOCATION_ICONS:
                if isinstance(CYCLE_LOCATION_ICONS[location], dict):
                    icon = CYCLE_LOCATION_ICONS[location].get(state, "🔸")
                else:
                    icon = CYCLE_LOCATION_ICONS[location]
            else:
                icon = "🔸"

            # Convert time to Discord timestamp with fallback
            discord_time = parse_warframe_time_to_discord_timestamp(time_left)
        
            # Fallback to raw time if parsing failed
            if discord_time == "Unknown" and time_left != "Unknown":
                discord_time = f"in {time_left}"
                logging.info(f"DEBUG: Using raw time fallback for {location}: {discord_time}")

            field_name = f"{icon} {location_name}"
            field_value = f"**{state.title()}**\nEnds {discord_time}"

            embed.add_field(
                name=field_name,
                value=field_value,
                inline=True
            )

        # Add API status footer if available
        if api_status:
            if not api_status["working"]:
                embed.set_footer(text=api_status["message"])
            elif api_status["api_name"] != "WFCD Primary":
                embed.set_footer(text=f"⚠️ Using fallback API: {api_status['api_name']}")

        return embed

    @staticmethod
    def create_fissures_embed(fissures: List[Dict], fissure_type: str, api_status: dict = None) -> Embed:
        """Create enhanced embed for specific fissure type with API status footer"""
        # Configure embed based on fissure type
        if fissure_type == "normal":
            title = f"{MISSION_TYPE_ICONS['normal']} Normal Void Fissures"
            color = 0xFF9800
        elif fissure_type == "steel_path":
            title = f"{MISSION_TYPE_ICONS['steel_path']} Steel Path Fissures"
            color = 0xE91E63
        elif fissure_type == "railjack":
            title = f"{MISSION_TYPE_ICONS['railjack']} Railjack Void Storms"
            color = 0x673AB7
        else:
            title = "🌀 Void Fissures"
            color = 0xFF9800

        embed = Embed(
            title=title,
            color=color,
            description=f"Active missions: {len(fissures)}"
        )
        embed.timestamp = datetime.utcnow()

        if not fissures:
            embed.description = "No active missions of this type"
            if api_status:
                if not api_status["working"]:
                    embed.set_footer(text=api_status["message"])
                elif api_status["api_name"] != "WFCD Primary":
                    embed.set_footer(text=f"⚠️ Using fallback API: {api_status['api_name']}")
            return embed

        # Group by tier
        tiers = {"Lith": [], "Meso": [], "Neo": [], "Axi": [], "Requiem": [], "Omnia": []}
        for fissure in fissures:
            tier = fissure.get("tier", "Unknown")
            if tier in tiers:
                tiers[tier].append(fissure)

        for tier, tier_fissures in tiers.items():
            if not tier_fissures:
                continue

            tier_icon = get_relic_tier_icon(tier)
            fissure_list = []
            for fissure in tier_fissures[:5]:  # Limit to 5 per tier
                node = fissure.get("node", "Unknown")
                mission_type = fissure.get("missionType", "Unknown")
                enemy = fissure.get("enemy", "Unknown")
            
                # NEW: Calculate ETA from expiry timestamp
                eta = calculate_eta_from_expiry(fissure.get("expiry"))
            
                # Debug log each fissure's ETA
                logging.info(f"DEBUG: Fissure {node} calculated ETA: '{eta}'")
            
                # Convert ETA to Discord timestamp
                if eta and eta != "Unknown":
                    discord_time = f"<t:{int(datetime.fromisoformat(fissure.get('expiry').replace('Z', '+00:00')).timestamp())}:R>"
                else:
                    discord_time = "Unknown"
            
                # Get enemy faction icon
                enemy_icon = get_enemy_faction_icon(enemy)
                fissure_list.append(
                    f"**{mission_type}** - {node}\n"
                    f"{enemy_icon} {enemy} • Ends {discord_time}"
                )

            embed.add_field(
                name=f"{tier_icon} {tier} Relics ({len(tier_fissures)})",
                value="\n\n".join(fissure_list),
                inline=True
            )

        # Add API status footer if available
        if api_status:
            if not api_status["working"]:
                embed.set_footer(text=api_status["message"])
            elif api_status["api_name"] != "WFCD Primary":
                embed.set_footer(text=f"⚠️ Using fallback API: {api_status['api_name']}")

        return embed

class NotificationManager:
    """Handles sending notifications to subscribed users"""
    
    def __init__(self, bot, subscription_manager: SubscriptionManager):
        self.bot = bot
        self.subscription_manager = subscription_manager
        self.last_notifications = {}
        
    async def check_cycle_changes(self, cycles_data: Dict):
        """Enhanced cycle change detection with initial state notifications"""
        for location, cycle in cycles_data.items():
            if not cycle:
                continue

            state = cycle.get("state", "")
            cycle_id = cycle.get("id", "")
        
            # Create a unique key for this cycle state
            state_key = f"{location}_{state}"
        
            # Check if this is a new cycle OR if we haven't notified about this state yet
            is_new_cycle = (location not in self.last_notifications or 
                        self.last_notifications[location] != cycle_id)
        
            # Track if we've already sent notifications for this specific state
            notification_key = f"notified_{state_key}"
            already_notified_this_state = self.last_notifications.get(notification_key, False)
        
            if is_new_cycle:
                # Update our tracking
                self.last_notifications[location] = cycle_id
                # Reset notification flags for this location
                for key in list(self.last_notifications.keys()):
                    if key.startswith(f"notified_{location}_"):
                        del self.last_notifications[key]
        
            # Send notifications for important states (even if not a "new" cycle)
            should_notify = False
            notification_title = ""
            notification_message = ""
        
            if location == "cetus" and state == "night" and not already_notified_this_state:
                should_notify = True
                notification_title = "Cetus Night"
                notification_message = (
                    f"🌙 **Night has fallen on Cetus!**\n"
                    f"Time for Eidolon hunting!\n"
                    f"⏰ {cycle.get('timeLeft', 'Unknown')} remaining"
                )
            
            elif location == "fortuna" and state == "warm" and not already_notified_this_state:
                should_notify = True
                notification_title = "Fortuna Warm"
                notification_message = (
                    f"🔥 **Orb Vallis is now warm!**\n"
                    f"Perfect for resource farming!\n"
                    f"⏰ {cycle.get('timeLeft', 'Unknown')} remaining"
                )
        
            if should_notify:
                # Send the notification
                event_type = f"{location}_{'night' if state == 'night' else 'warm'}"
                await self.notify_subscribers(event_type, notification_title, notification_message)
            
                # Mark that we've notified about this state
                self.last_notifications[notification_key] = True
            
                logging.info(f"Sent {event_type} notification - State: {state}, Time left: {cycle.get('timeLeft', 'Unknown')}")

    
    async def check_fissure_changes(self, fissures: List[Dict]):
        """Enhanced fissure change detection with custom filtering"""
        # Check for specific mission/tier combinations
        for fissure in fissures:
            mission_id = fissure.get("id", "")
            tier = fissure.get("tier", "").lower()
            mission_type = fissure.get("missionType", "").lower()
        
            # Skip if we've already notified about this mission
            if f"fissure_{mission_id}" in self.last_notifications:
                continue
            
            # Mark this mission as notified
            self.last_notifications[f"fissure_{mission_id}"] = True
        
            # Get all subscribers for fissure_missions
            all_subscribers = self.subscription_manager.get_all_fissure_subscribers()
        
            for user_id, subscription_details in all_subscribers.items():
                # Parse the subscription details
                should_notify = self.matches_subscription(
                    subscription_details, tier, mission_type
                )
            
                if should_notify:
                    try:
                        user = await self.bot.fetch_user(user_id)
                        if user:
                            embed = Embed(
                                title=f"🔔 {tier.title()} {mission_type.title()} Available!",
                                description=(
                                    f"🌀 **{tier.title()} {mission_type.title()} Mission Available!**\n"
                                    f"📍 {fissure.get('node', 'Unknown')}\n"
                                    f"🏴 {fissure.get('enemy', 'Unknown')}\n"
                                    f"⏰ {fissure.get('eta', 'Unknown')} remaining"
                                ),
                                color=0x00BCD4
                            )
                            embed.timestamp = datetime.utcnow()
                            await user.send(embed=embed)
                    except Exception as e:
                        logging.warning(f"Failed to notify user {user_id}: {e}")

    def matches_subscription(self, subscription_details: str, tier: str, mission_type: str) -> bool:
        """Check if a mission matches the user's subscription criteria"""
        if not subscription_details:
            return True  # No specific filter means all missions
    
        parts = subscription_details.split("|")
        tier_filter = None
        mission_filter = None
    
        for part in parts:
            if part.startswith("tier:"):
                tier_filter = part.split(":", 1)[1].lower()
            elif part.startswith("mission:"):
                mission_filter = part.split(":", 1)[1].lower()
    
        # Check tier filter
        if tier_filter and tier_filter != tier:
            return False
    
        # Check mission type filter
        if mission_filter and mission_filter != mission_type:
            return False
    
        return True

    
    async def notify_subscribers(self, event_type: str, title: str, message: str):
        """Send notifications to all subscribers of an event type"""
        subscribers = self.subscription_manager.get_subscribers(event_type)
        
        for user_id in subscribers:
            try:
                user = await self.bot.fetch_user(user_id)
                if user:
                    embed = Embed(title=f"🔔 {title}", description=message, color=0x00BCD4)
                    embed.timestamp = datetime.utcnow()
                    await user.send(embed=embed)
            except Exception as e:
                logging.warning(f"Failed to notify user {user_id}: {e}")

class ChannelManager:
    """Enhanced channel manager that properly edits messages instead of creating new ones"""

    def __init__(self, bot):
        self.bot = bot
        self.channels_file = "warframe_channels.json"
        self.message_ids_file = "warframe_message_ids.json"  # New file for message IDs
        self.channels = self.load_channels()
        self.message_ids = self.load_message_ids()

    def load_message_ids(self) -> dict:
        """Load message IDs from persistent storage"""
        try:
            if os.path.exists(self.message_ids_file):
                with open(self.message_ids_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logging.error(f"Error loading message IDs: {e}")
        return {}

    def save_message_ids(self):
        """Save message IDs to persistent storage"""
        try:
            with open(self.message_ids_file, 'w') as f:
                json.dump(self.message_ids, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving message IDs: {e}")

    def load_channels(self) -> dict:
        """Load channel configurations from file"""
        try:
            if os.path.exists(self.channels_file):
                with open(self.channels_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logging.error(f"Error loading channels: {e}")
        return {}

    def save_channels(self):
        """Save channel configurations to file"""
        try:
            with open(self.channels_file, 'w') as f:
                json.dump(self.channels, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving channels: {e}")

    def set_channel(self, guild_id: int, channel_id: int, channel_type: str) -> bool:
        """Set a channel for auto-updates"""
        guild_id_str = str(guild_id)
        if guild_id_str not in self.channels:
            self.channels[guild_id_str] = {}

        self.channels[guild_id_str][channel_type] = channel_id
        self.save_channels()

        # Clear any stored message IDs when channel is changed
        if guild_id_str in self.message_ids:
            if channel_type in self.message_ids[guild_id_str]:
                del self.message_ids[guild_id_str][channel_type]
                self.save_message_ids()
        return True

    def remove_channel(self, guild_id: int, channel_type: str) -> bool:
        """Remove a channel from auto-updates"""
        guild_id_str = str(guild_id)
        if guild_id_str in self.channels and channel_type in self.channels[guild_id_str]:
            del self.channels[guild_id_str][channel_type]

            # Also remove stored message IDs
            if guild_id_str in self.message_ids and channel_type in self.message_ids[guild_id_str]:
                del self.message_ids[guild_id_str][channel_type]
                self.save_message_ids()

            if not self.channels[guild_id_str]:
                del self.channels[guild_id_str]
                if guild_id_str in self.message_ids:
                    del self.message_ids[guild_id_str]
                    self.save_message_ids()

            self.save_channels()
            return True
        return False

    async def find_or_create_message(self, channel, embed, message_type):
        """Find existing bot message to edit, or create new one"""
        guild_id_str = str(channel.guild.id)

        if guild_id_str not in self.message_ids:
            self.message_ids[guild_id_str] = {}

        # Try to find existing message by stored ID
        stored_message_id = self.message_ids[guild_id_str].get(message_type)
        if stored_message_id:
            try:
                message = await channel.fetch_message(stored_message_id)
                if message.author == self.bot.user:
                    await message.edit(embed=embed)
                    logging.info(f"Successfully edited {message_type} message in {channel.name}")
                    return
            except discord.NotFound:
                # Message was deleted, remove from storage
                logging.info(f"Stored {message_type} message was deleted, will create new one")
                del self.message_ids[guild_id_str][message_type]
                self.save_message_ids()
            except Exception as e:
                logging.error(f"Error editing {message_type} message: {e}")

        # If no stored message or editing failed, look for recent bot messages
        try:
            async for message in channel.history(limit=30):
                if (
                    message.author == self.bot.user
                    and message.embeds and len(message.embeds) > 0
                    and message_type.lower() in message.embeds[0].title.lower()
                ):
                    await message.edit(embed=embed)
                    # Store this message ID for future edits
                    self.message_ids[guild_id_str][message_type] = message.id
                    self.save_message_ids()
                    logging.info(f"Found and edited existing {message_type} message in {channel.name}")
                    return
        except Exception as e:
            logging.error(f"Error searching for existing {message_type} messages: {e}")

        # No existing message found, create new one
        try:
            new_message = await channel.send(embed=embed)
            self.message_ids[guild_id_str][message_type] = new_message.id
            self.save_message_ids()
            logging.info(f"Created new {message_type} message in {channel.name}")
        except Exception as e:
            logging.error(f"Error creating new {message_type} message: {e}")

    async def update_fissures_channel(self, channel, embed_generator, data_manager):
        """Update fissures channel with separate embeds that edit existing messages"""
        try:
            guild_id_str = str(channel.guild.id)
            fissures_by_type = await data_manager.get_fissures_by_type()
            api_status = data_manager.get_current_api_status()

            if guild_id_str not in self.message_ids:
                self.message_ids[guild_id_str] = {}
            if "fissures" not in self.message_ids[guild_id_str]:
                self.message_ids[guild_id_str]["fissures"] = {}

            for mission_type in ["normal", "steel_path", "railjack"]:
                fissures = fissures_by_type[mission_type]

                # Create embed even if no missions (to show "No active missions")
                embed = embed_generator.create_fissures_embed(fissures, mission_type, api_status)

                stored_message_id = self.message_ids[guild_id_str]["fissures"].get(mission_type)
                if stored_message_id:
                    try:
                        message = await channel.fetch_message(stored_message_id)
                        if message.author == self.bot.user:
                            await message.edit(embed=embed)
                            logging.info(f"Edited {mission_type} fissures message (ID: {stored_message_id})")
                            continue
                    except discord.NotFound:
                        logging.info(f"Stored {mission_type} message was deleted, will create new one")
                        del self.message_ids[guild_id_str]["fissures"][mission_type]
                        self.save_message_ids()
                    except Exception as e:
                        logging.error(f"Error editing {mission_type} fissures message: {e}")

                found_message = False
                try:
                    async for message in channel.history(limit=50):
                        if (
                            message.author == self.bot.user
                            and message.embeds and len(message.embeds) > 0
                            and mission_type.title() in message.embeds[0].title
                        ):
                            await message.edit(embed=embed)
                            self.message_ids[guild_id_str]["fissures"][mission_type] = message.id
                            self.save_message_ids()
                            logging.info(f"Found and edited {mission_type} fissures message (ID: {message.id})")
                            found_message = True
                            break
                except Exception as e:
                    logging.error(f"Error searching for {mission_type} fissures message: {e}")

                if not found_message:
                    try:
                        new_message = await channel.send(embed=embed)
                        self.message_ids[guild_id_str]["fissures"][mission_type] = new_message.id
                        self.save_message_ids()
                        logging.info(f"Created new {mission_type} fissures message (ID: {new_message.id})")
                    except Exception as e:
                        logging.error(f"Error creating {mission_type} fissures message: {e}")

            # Clean up any message IDs for mission types that no longer exist
            valid_types = ["normal", "steel_path", "railjack"]
            if "fissures" in self.message_ids[guild_id_str]:
                for mission_type in list(self.message_ids[guild_id_str]["fissures"].keys()):
                    if mission_type not in valid_types:
                        del self.message_ids[guild_id_str]["fissures"][mission_type]
                        self.save_message_ids()

        except Exception as e:
            logging.error(f"Error updating fissures channel {channel.name}: {e}")

    async def update_channels(self, embed_generator: EmbedGenerator, data_manager: WarframeDataManager):
        """Update all configured channels with latest data and API status"""
        for guild_id_str, guild_channels in self.channels.items():
            try:
                guild = self.bot.get_guild(int(guild_id_str))
                if not guild:
                    continue

                # Fetch current API status
                api_status = data_manager.get_current_api_status()

                # Update cycles channel
                if "cycles" in guild_channels:
                    channel = guild.get_channel(guild_channels["cycles"])
                    if channel:
                        try:
                            cycles_data = await data_manager.get_cycles()
                            embed = embed_generator.create_cycles_embed(cycles_data, api_status)
                            await self.find_or_create_message(channel, embed, "cycles")
                        except Exception as e:
                            logging.error(f"Error updating cycles channel: {e}")

                # Update fissures channel
                if "fissures" in guild_channels:
                    channel = guild.get_channel(guild_channels["fissures"])
                    if channel:
                        await self.update_fissures_channel(channel, embed_generator, data_manager)

            except Exception as e:
                logging.error(f"Error updating channels for guild {guild_id_str}: {e}")


# =============================================================================
# ENHANCED UPDATE LOOP WITH BETTER ERROR HANDLING
# =============================================================================

@tasks.loop(minutes=5)
async def warframe_info_update_loop():
    """Enhanced update loop with better error handling and logging"""
    global warframe_data_manager, notification_manager, channel_manager, embed_generator

    if not all([warframe_data_manager, notification_manager, channel_manager, embed_generator]):
        logging.warning("Not all components initialized, skipping update")
        return

    try:
        logging.info("Starting Warframe info update loop...")
        
        # Get latest data with error handling
        cycles_data = await warframe_data_manager.get_cycles()
        if cycles_data:
            logging.info(f"Retrieved cycles data for {len(cycles_data)} locations")
        else:
            logging.warning("Failed to retrieve cycles data")

        fissures = await warframe_data_manager.get_fissures()
        if fissures:
            logging.info(f"Retrieved {len(fissures)} fissure missions")
        else:
            logging.warning("Failed to retrieve fissures data")

        # ADD THIS: Log API status
        api_status = warframe_data_manager.get_current_api_status()
        if not api_status["working"]:
            logging.warning(f"⚠️ API Status: {api_status['message']}")
        else:
            logging.info(f"✅ API Status: Using {api_status['api_name']}")

        # Check for changes and notify subscribers
        if cycles_data:
            await notification_manager.check_cycle_changes(cycles_data)
        if fissures:
            await notification_manager.check_fissure_changes(fissures)

        # Update auto-updating channels
        logging.info("Updating auto-updating channels...")
        await channel_manager.update_channels(embed_generator, warframe_data_manager)
        
        logging.info("Warframe info update loop completed successfully")

    except Exception as e:
        logging.error(f"Error in Warframe info update loop: {e}")


# =============================================================================
# ENHANCED CHANNEL SETUP COMMANDS WITH BETTER FEEDBACK
# =============================================================================

@bot.tree.command(name="set-cycles-channel", description="Set channel for auto-updating cycle information")
@app_commands.describe(channel="The channel to use for cycle updates")
@app_commands.default_permissions(administrator=True)
async def set_cycles_channel_command(
    interaction: discord.Interaction, 
    channel: discord.TextChannel
):
    """Set channel for cycle updates with immediate test update"""
    success = channel_manager.set_channel(
        interaction.guild.id, channel.id, "cycles"
    )
    
    if success:
        embed = discord.Embed(
            title="✅ Cycles Channel Set",
            description=f"Cycle information will now auto-update in {channel.mention}",
            color=0x4CAF50
        )
        
        # Send immediate test update
        try:
            cycles_data = await warframe_data_manager.get_cycles()
            if cycles_data:
                cycles_embed = embed_generator.create_cycles_embed(cycles_data)
                await channel.send("🔄 **Test Update** - Cycles channel configured successfully!", embed=cycles_embed)
                embed.add_field(
                    name="✅ Test Update Sent",
                    value="Check the channel for your first update!",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚠️ API Warning", 
                    value="Could not fetch cycles data for test update. Channel is configured but API may be unavailable.",
                    inline=False
                )
        except Exception as e:
            embed.add_field(
                name="❌ Test Update Failed",
                value=f"Channel configured but test update failed: {str(e)[:100]}",
                inline=False
            )
    else:
        embed = discord.Embed(
            title="❌ Failed to Set Channel",
            description="There was an error setting up the channel.",
            color=0xF44336
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set-fissures-channel", description="Set channel for auto-updating fissure information")
@app_commands.describe(channel="The channel to use for fissure updates")
@app_commands.default_permissions(administrator=True)
async def set_fissures_channel_command(
    interaction: discord.Interaction, 
    channel: discord.TextChannel
):
    """Set channel for fissure updates with immediate test update"""
    success = channel_manager.set_channel(
        interaction.guild.id, channel.id, "fissures"
    )
    
    if success:
        embed = discord.Embed(
            title="✅ Fissures Channel Set",
            description=f"Fissure information will now auto-update in {channel.mention}",
            color=0x4CAF50
        )
        
        # Send immediate test update
        try:
            fissures_by_type = await warframe_data_manager.get_fissures_by_type()
            updates_sent = 0
            
            for mission_type in ["normal", "steel_path", "railjack"]:
                fissures = fissures_by_type[mission_type]
                if fissures:
                    fissures_embed = embed_generator.create_fissures_embed(fissures, mission_type)
                    if updates_sent == 0:
                        await channel.send("🔄 **Test Update** - Fissures channel configured successfully!")
                    await channel.send(embed=fissures_embed)
                    updates_sent += 1
            
            if updates_sent > 0:
                embed.add_field(
                    name="✅ Test Updates Sent",
                    value=f"Sent {updates_sent} fissure embed(s). Check the channel!",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚠️ No Active Fissures",
                    value="Channel configured but no active fissures to display right now.",
                    inline=False
                )
                
        except Exception as e:
            embed.add_field(
                name="❌ Test Update Failed",
                value=f"Channel configured but test update failed: {str(e)[:100]}",
                inline=False
            )
    else:
        embed = discord.Embed(
            title="❌ Failed to Set Channel",
            description="There was an error setting up the channel.",
            color=0xF44336
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="test-channels", description="Test all configured auto-update channels")
@app_commands.default_permissions(administrator=True)
async def test_channels_command(interaction: discord.Interaction):
    """Test all configured channels manually"""
    await interaction.response.defer()
    
    try:
        # Force update all channels
        await channel_manager.update_channels(embed_generator, warframe_data_manager)
        
        # Get channel info
        guild_id_str = str(interaction.guild.id)
        guild_channels = channel_manager.channels.get(guild_id_str, {})
        
        if not guild_channels:
            await interaction.followup.send("❌ No channels configured for this server. Use `/set-cycles-channel` or `/set-fissures-channel` first.")
            return
        
        embed = discord.Embed(title="🔄 Channel Update Test", color=0x2196F3)
        
        for channel_type, channel_id in guild_channels.items():
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                embed.add_field(
                    name=f"✅ {channel_type.title()} Channel",
                    value=f"Updated {channel.mention}",
                    inline=True
                )
            else:
                embed.add_field(
                    name=f"❌ {channel_type.title()} Channel",
                    value=f"Channel ID {channel_id} not found",
                    inline=True
                )
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error testing channels: {e}")

# =============================================================================
# ALL EXISTING RELIC COMPARISON SYSTEM (PRESERVED COMPLETELY)
# =============================================================================

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
    name = name.replace("&amp;", "and")
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
        (num_relics,) = struct.unpack('<I', binary_data[:4])
        
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

# =============================================================================
# WARFRAME INFORMATION SYSTEM BACKGROUND TASK
# =============================================================================

@tasks.loop(minutes=5)
async def warframe_info_update_loop():
    """Main update loop for Warframe information system"""
    global warframe_data_manager, notification_manager, channel_manager, embed_generator
    
    if not all([warframe_data_manager, notification_manager, channel_manager, embed_generator]):
        return
    
    try:
        # Get latest data
        cycles_data = await warframe_data_manager.get_cycles()
        fissures = await warframe_data_manager.get_fissures()
        
        # Check for changes and notify subscribers
        await notification_manager.check_cycle_changes(cycles_data)
        await notification_manager.check_fissure_changes(fissures)
        
        # Update auto-updating channels
        await channel_manager.update_channels(embed_generator, warframe_data_manager)
        
    except Exception as e:
        logging.error(f"Error in Warframe info update loop: {e}")

@warframe_info_update_loop.before_loop
async def before_warframe_info_update_loop():
    await bot.wait_until_ready()

# =============================================================================
# ENHANCED SLASH COMMANDS - RELIC COMPARISON SYSTEM (ALL PRESERVED)
# =============================================================================

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

# =============================================================================
# ENHANCED SLASH COMMANDS - WARFRAME INFORMATION SYSTEM
# =============================================================================

@bot.tree.command(name="cycles", description="Show current cycle information with Discord timestamps")
async def cycles_command(interaction: discord.Interaction):
    """Display enhanced cycle information"""
    await interaction.response.defer()
    
    cycles_data = await warframe_data_manager.get_cycles()
    api_status = warframe_data_manager.get_current_api_status()
    if not cycles_data:
        await interaction.followup.send("❌ Failed to fetch cycle information.")
        return
    
    embed = embed_generator.create_cycles_embed(cycles_data, api_status)  # pass api_status here
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="fissures", description="Show void fissures in separate embeds by type")
@app_commands.describe(
    fissure_type="Show specific fissure type, or 'all' for separate embeds"
)
@app_commands.choices(fissure_type=[
    app_commands.Choice(name="All Types (Separate Embeds)", value="all"),
    app_commands.Choice(name="Normal Fissures Only", value="normal"),
    app_commands.Choice(name="Steel Path Fissures Only", value="steel_path"),
    app_commands.Choice(name="Railjack Void Storms Only", value="railjack"),
])
async def fissures_command(
    interaction: discord.Interaction,
    fissure_type: Optional[str] = "all"
):
    """Display fissures in separate embeds by type"""
    await interaction.response.defer()
    
    fissures_by_type = await warframe_data_manager.get_fissures_by_type()
    api_status = warframe_data_manager.get_current_api_status()  # Fetch API status
    
    if not any(fissures_by_type.values()):
        error_embed = discord.Embed(
            title="❌ Failed to fetch fissure information",
            color=0xF44336
        )
        if not api_status["working"]:
            error_embed.set_footer(text=api_status["message"])
        await interaction.followup.send(embed=error_embed)
        return
    
    if fissure_type == "all":
        embeds_sent = 0
        
        for mission_type in ["normal", "steel_path", "railjack"]:
            fissures = fissures_by_type[mission_type]
            if fissures:
                embed = embed_generator.create_fissures_embed(fissures, mission_type, api_status)
                await interaction.followup.send(embed=embed)
                embeds_sent += 1
        
        if embeds_sent == 0:
            msg_embed = discord.Embed(
                title="❌ No active fissures found.",
                color=0xF44336
            )
            if not api_status["working"]:
                msg_embed.set_footer(text=api_status["message"])
            await interaction.followup.send(embed=msg_embed)
    
    else:
        fissures = fissures_by_type.get(fissure_type, [])
        embed = embed_generator.create_fissures_embed(fissures, fissure_type, api_status)
        await interaction.followup.send(embed=embed)


@bot.tree.command(name="steel-path", description="Show Steel Path incursions and rewards")
async def steel_path_command(interaction: discord.Interaction):
    """Display Steel Path information"""
    await interaction.response.defer()
    
    steel_path_data = await warframe_data_manager.get_steel_path_info()
    if not steel_path_data:
        await interaction.followup.send("❌ Failed to fetch Steel Path information.")
        return
    
    embed = discord.Embed(title="🔥 Steel Path", color=0xE91E63)
    embed.timestamp = datetime.utcnow()
    
    # Current reward
    current_reward = steel_path_data.get("currentReward", {})
    if current_reward:
        reward_name = current_reward.get("name", "Unknown")
        reward_cost = current_reward.get("cost", 0)
        embed.add_field(
            name="🎁 Current Reward",
            value=f"**{reward_name}**\n💎 {reward_cost} Steel Essence",
            inline=True
        )
    
    # Time remaining
    remaining = steel_path_data.get("remaining", "Unknown")
    embed.add_field(
        name="⏰ Time Remaining",
        value=remaining,
        inline=True
    )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="arbitration", description="Show current arbitration mission")
async def arbitration_command(interaction: discord.Interaction):
    """Display current arbitration"""
    await interaction.response.defer()
    
    arbitration_data = await warframe_data_manager.get_arbitration()
    
    embed = discord.Embed(title="⚖️ Arbitration", color=0x9C27B0)
    embed.timestamp = datetime.utcnow()
    
    if not arbitration_data:
        embed.description = "No active arbitration mission"
    else:
        node = arbitration_data.get("node", "Unknown")
        mission_type = arbitration_data.get("type", "Unknown")
        enemy = arbitration_data.get("enemy", "Unknown")
        eta = arbitration_data.get("eta", "Unknown")
        
        embed.add_field(
            name="🎯 Current Mission",
            value=f"**{mission_type}** - {node}\n🏴 {enemy}",
            inline=True
        )
        
        embed.add_field(
            name="⏰ Time Remaining",
            value=eta,
            inline=True
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="sortie", description="Show current sortie missions")
async def sortie_command(interaction: discord.Interaction):
    """Display current sortie"""
    await interaction.response.defer()
    
    sortie_data = await warframe_data_manager.get_sortie()
    if not sortie_data:
        await interaction.followup.send("❌ No active sortie or failed to fetch information.")
        return
    
    embed = discord.Embed(title="🎯 Daily Sortie", color=0xFF5722)
    embed.timestamp = datetime.utcnow()
    
    boss = sortie_data.get("boss", "Unknown")
    faction = sortie_data.get("faction", "Unknown")
    eta = sortie_data.get("eta", "Unknown")
    
    embed.add_field(name="Boss", value=boss, inline=True)
    embed.add_field(name="Faction", value=faction, inline=True)
    embed.add_field(name="Time Remaining", value=eta, inline=True)
    
    variants = sortie_data.get("variants", [])
    if variants:
        mission_list = []
        for i, variant in enumerate(variants[:3], 1):
            mission_type = variant.get("missionType", "Unknown")
            node = variant.get("node", "Unknown")
            modifier = variant.get("modifier", "Unknown")
            mission_list.append(f"**{i}.** {mission_type} - {node}\n*{modifier}*")
        
        embed.add_field(
            name="Missions",
            value="\n\n".join(mission_list),
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="baro", description="Show Baro Ki'Teer information")
async def baro_command(interaction: discord.Interaction):
    """Display Baro Ki'Teer information"""
    await interaction.response.defer()
    
    data = await warframe_data_manager.fetch_data()
    if not data:
        await interaction.followup.send("❌ Failed to fetch Baro information.")
        return
    
    void_trader = data.get("voidTrader", {})
    if not void_trader:
        await interaction.followup.send("❌ No Baro Ki'Teer data available.")
        return
    
    embed = discord.Embed(title="💰 Baro Ki'Teer - Void Trader", color=0xFFD700)
    embed.timestamp = datetime.utcnow()
    
    character = void_trader.get("character", "Unknown")
    location = void_trader.get("location", "Unknown")
    
    if void_trader.get("active", False):
        embed.add_field(name="Status", value="🟢 **ACTIVE**", inline=True)
        embed.add_field(name="Location", value=location, inline=True)
        
        end_string = void_trader.get("endString", "Unknown")
        embed.add_field(name="Leaves In", value=end_string, inline=True)
        
        # Show inventory
        inventory = void_trader.get("inventory", [])
        if inventory:
            item_list = []
            for item in inventory[:10]:  # Limit to 10 items
                item_name = item.get("item", "Unknown")
                ducats = item.get("ducats", 0)
                credits = item.get("credits", 0)
                item_list.append(f"**{item_name}**\n💎 {ducats} Ducats + 💰 {credits:,} Credits")
            
            embed.add_field(
                name=f"🏪 Inventory ({len(inventory)} items)",
                value="\n\n".join(item_list),
                inline=False
            )
    else:
        embed.add_field(name="Status", value="🔴 **NOT ACTIVE**", inline=True)
        
        start_string = void_trader.get("startString", "Unknown")
        embed.add_field(name="Next Visit", value=start_string, inline=True)
        embed.add_field(name="Next Location", value=location, inline=True)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="subscribe", description="Subscribe to specific Warframe event notifications")
@app_commands.describe(
    event="Select the main event category",
    tier="Specify relic tier (for fissure missions)",
    mission_type="Specify mission type (for fissure missions)"
)
@app_commands.choices(event=[
    app_commands.Choice(name="Cetus Night (for Eidolon hunting)", value="cetus_night"),
    app_commands.Choice(name="Fortuna Warm (for resource farming)", value="fortuna_warm"),
    app_commands.Choice(name="Fissure Missions (specify tier/mission)", value="fissure_missions"),
    app_commands.Choice(name="Steel Path Fissures", value="steel_path_fissures"),
    app_commands.Choice(name="Arbitration changes", value="arbitration"),
])
@app_commands.choices(tier=[
    app_commands.Choice(name="Any Tier", value="any"),
    app_commands.Choice(name="Lith", value="lith"),
    app_commands.Choice(name="Meso", value="meso"),
    app_commands.Choice(name="Neo", value="neo"),
    app_commands.Choice(name="Axi", value="axi"),
    app_commands.Choice(name="Requiem", value="requiem"),
])
@app_commands.choices(mission_type=[
    app_commands.Choice(name="Any Mission Type", value="any"),
    app_commands.Choice(name="Survival", value="survival"),
    app_commands.Choice(name="Capture", value="capture"),
    app_commands.Choice(name="Exterminate", value="exterminate"),
    app_commands.Choice(name="Defense", value="defense"),
    app_commands.Choice(name="Mobile Defense", value="mobile_defense"),
    app_commands.Choice(name="Spy", value="spy"),
    app_commands.Choice(name="Rescue", value="rescue"),
    app_commands.Choice(name="Sabotage", value="sabotage"),
    app_commands.Choice(name="Interception", value="interception"),
])
async def subscribe_command(
    interaction: discord.Interaction,
    event: str,
    tier: Optional[str] = "any",
    mission_type: Optional[str] = "any"
):
    """Enhanced subscribe command with tier and mission type filtering"""
    
    # Build the details string for specific filtering
    details = ""
    if event == "fissure_missions":
        details_parts = []
        if tier != "any":
            details_parts.append(f"tier:{tier}")
        if mission_type != "any":
            details_parts.append(f"mission:{mission_type}")
        details = "|".join(details_parts)
        
        # Create a more readable event type for fissure missions
        if tier != "any" and mission_type != "any":
            event_display = f"{tier.title()} {mission_type.title()}"
        elif tier != "any":
            event_display = f"{tier.title()} Missions"
        elif mission_type != "any":
            event_display = f"{mission_type.title()} Missions"
        else:
            event_display = "All Fissure Missions"
    else:
        event_display = event.replace("_", " ").title()

    success = subscription_manager.add_subscription(
        interaction.user.id, event, details
    )

    if success:
        embed = discord.Embed(
            title="✅ Subscription Added",
            description=f"You will now receive notifications for: **{event_display}**",
            color=0x4CAF50
        )
        
        # IMMEDIATE NOTIFICATION CHECK
        notified = False
        try:
            if event == "cetus_night":
                cycles_data = await warframe_data_manager.get_cycles()
                cetus = cycles_data.get("cetus", {})
                if cetus.get("state", "").lower() == "night":
                    time_left = cetus.get("timeLeft", "unknown")
                    await interaction.user.send(
                        f"🌙 **Cetus is currently in night cycle!**\n"
                        f"⏰ {time_left} remaining for Eidolon hunting"
                    )
                    notified = True

            elif event == "fortuna_warm":
                cycles_data = await warframe_data_manager.get_cycles()
                fortuna = cycles_data.get("fortuna", {})
                if fortuna.get("state", "").lower() == "warm":
                    time_left = fortuna.get("timeLeft", "unknown")
                    await interaction.user.send(
                        f"🔥 **Orb Vallis is currently warm!**\n"
                        f"⏰ {time_left} remaining for resource farming"
                    )
                    notified = True

            elif event == "fissure_missions":
                fissures = await warframe_data_manager.get_fissures()
                matching_missions = []
                
                for fissure in fissures:
                    # Check tier filter
                    if tier != "any" and fissure.get("tier", "").lower() != tier.lower():
                        continue
                    
                    # Check mission type filter
                    if mission_type != "any" and fissure.get("missionType", "").lower() != mission_type.lower():
                        continue
                    
                    matching_missions.append(fissure)
                
                # Send notification for each matching mission
                for mission in matching_missions[:3]:  # Limit to 3 to avoid spam
                    node = mission.get("node", "Unknown")
                    enemy = mission.get("enemy", "Unknown")
                    eta = mission.get("eta", "Unknown")
                    m_tier = mission.get("tier", "Unknown")
                    m_type = mission.get("missionType", "Unknown")
                    
                    await interaction.user.send(
                        f"🌀 **{m_tier.title()} {m_type} Mission Active!**\n"
                        f"📍 {node}\n"
                        f"🏴 {enemy}\n"
                        f"⏰ {eta} remaining"
                    )
                    notified = True
                    
        except Exception as e:
            logging.warning(f"Immediate notify error during subscription: {e}")

        if notified:
            embed.add_field(
                name="⏰ Heads Up!",
                value="Matching missions are active right now; you have been notified by DM.",
                inline=False
            )
    else:
        embed = discord.Embed(
            title="ℹ️ Already Subscribed",
            description="You are already subscribed to this event.",
            color=0x2196F3
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="unsubscribe", description="Unsubscribe from Warframe event notifications")
@app_commands.describe(
    event="The event type to unsubscribe from",
    tier="Specify relic tier (for fissure missions)",
    mission_type="Specify mission type (for fissure missions)"
)
@app_commands.choices(event=[
    app_commands.Choice(name="Cetus Night (for Eidolon hunting)", value="cetus_night"),
    app_commands.Choice(name="Fortuna Warm (for resource farming)", value="fortuna_warm"),
    app_commands.Choice(name="Fissure Missions (specify tier/mission)", value="fissure_missions"),
    app_commands.Choice(name="Steel Path Fissures", value="steel_path_fissures"),
    app_commands.Choice(name="Arbitration changes", value="arbitration"),
])
@app_commands.choices(tier=[
    app_commands.Choice(name="Any Tier", value="any"),
    app_commands.Choice(name="Lith", value="lith"),
    app_commands.Choice(name="Meso", value="meso"),
    app_commands.Choice(name="Neo", value="neo"),
    app_commands.Choice(name="Axi", value="axi"),
    app_commands.Choice(name="Requiem", value="requiem"),
])
@app_commands.choices(mission_type=[
    app_commands.Choice(name="Any Mission Type", value="any"),
    app_commands.Choice(name="Survival", value="survival"),
    app_commands.Choice(name="Capture", value="capture"),
    app_commands.Choice(name="Exterminate", value="exterminate"),
    app_commands.Choice(name="Defense", value="defense"),
    app_commands.Choice(name="Mobile Defense", value="mobile_defense"),
    app_commands.Choice(name="Spy", value="spy"),
    app_commands.Choice(name="Rescue", value="rescue"),
    app_commands.Choice(name="Sabotage", value="sabotage"),
    app_commands.Choice(name="Interception", value="interception"),
])
async def unsubscribe_command(
    interaction: discord.Interaction,
    event: str,
    tier: Optional[str] = "any",
    mission_type: Optional[str] = "any"
):
    """Enhanced unsubscribe command with tier and mission type filtering"""
    
    # Build the details string for specific filtering (same logic as subscribe)
    details = ""
    if event == "fissure_missions":
        details_parts = []
        if tier != "any":
            details_parts.append(f"tier:{tier}")
        if mission_type != "any":
            details_parts.append(f"mission:{mission_type}")
        details = "|".join(details_parts)

    success = subscription_manager.remove_subscription(
        interaction.user.id, event, details
    )

    if success:
        event_name = event.replace("_", " ").title()
        embed = discord.Embed(
            title="✅ Subscription Removed",
            description=f"You will no longer receive notifications for: **{event_name}**",
            color=0x4CAF50
        )
    else:
        embed = discord.Embed(
            title="❌ Not Subscribed",
            description="You are not subscribed to this event.",
            color=0xF44336
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="my-subscriptions", description="View your current subscriptions")
async def my_subscriptions_command(interaction: discord.Interaction):
    """View user's current subscriptions"""
    subscriptions = subscription_manager.get_user_subscriptions(interaction.user.id)
    
    if not subscriptions:
        embed = discord.Embed(
            title="📭 No Subscriptions",
            description="You are not subscribed to any events.\nUse `/subscribe` to get notifications!",
            color=0x757575
        )
    else:
        embed = discord.Embed(
            title="📬 Your Subscriptions",
            color=0x2196F3
        )
        
        for event_type, event_subs in subscriptions.items():
            event_name = event_type.replace("_", " ").title()
            sub_count = len(event_subs)
            embed.add_field(
                name=event_name,
                value=f"{sub_count} subscription{'s' if sub_count != 1 else ''}",
                inline=True
            )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="wf-status", description="Show overall Warframe worldstate status")
async def wf_status_command(interaction: discord.Interaction):
    """Display overall worldstate status"""
    await interaction.response.defer()
    
    data = await warframe_data_manager.fetch_data()
    if not data:
        embed = discord.Embed(
            title="❌ API Status",
            description="Failed to connect to Warframe API",
            color=0xF44336
        )
    else:
        embed = discord.Embed(
            title="✅ Warframe Worldstate Status",
            description="Successfully connected to API",
            color=0x4CAF50
        )
        embed.timestamp = datetime.utcnow()
        
        # Count active items
        counts = {
            "Fissures": len(data.get("fissures", [])),
            "Invasions": len(data.get("invasions", [])),
            "Events": len(data.get("events", [])),
            "Alerts": len(data.get("alerts", [])),
            "Kuva Missions": len(data.get("kuva", [])),
        }
        
        for item_type, count in counts.items():
            embed.add_field(name=item_type, value=str(count), inline=True)
        
        # Check if major systems are active
        systems = []
        if data.get("sortie"):
            systems.append("Sortie")
        if data.get("arbitration"):
            systems.append("Arbitration")
        if data.get("archonHunt"):
            systems.append("Archon Hunt") 
        if data.get("nightwave"):
            systems.append("Nightwave")
        
        if systems:
            embed.add_field(
                name="🟢 Active Systems",
                value=", ".join(systems),
                inline=False
            )
    
    await interaction.followup.send(embed=embed)

# =============================================================================
# ENHANCED BOT FEATURES COMMAND
# =============================================================================

@bot.tree.command(name="bot-features", description="Show the enhanced bot features")
async def bot_features_command(interaction: discord.Interaction):
    """Display enhanced bot features"""
    embed = Embed(title="🚀 Enhanced Warframe Bot Features", color=0x00BCD4)
    
    features = [
        "⏰ **Discord Timestamps** - All countdowns now show relative Discord time",
        f"{MISSION_TYPE_ICONS['normal']} **Separate Fissure Embeds** - Normal, Steel Path, and Railjack missions in separate embeds",
        f"{RELIC_TIER_ICONS['lith']} **Relic Tier Icons** - Visual icons for Lith, Meso, Neo, Axi tiers",
        f"{CYCLE_LOCATION_ICONS['cetus']['night']} **Enhanced Cycle Display** - Better visual indicators for day/night cycles",
        "📊 **Improved Organization** - Better categorization and filtering options",
        "💰 **Platinum Price Checking** - Real-time warframe.market integration",
        "🔄 **Auto Relic Updates** - Automatic relic inventory updates every 6 hours",
        "🔔 **Event Subscriptions** - Get notified for specific Warframe events"
    ]
    
    embed.add_field(
        name="✨ Enhanced Features",
        value="\n".join(features),
        inline=False
    )
    
    embed.add_field(
        name="🎮 Commands",
        value="`/fissures` - Choose specific types or see all in separate embeds\n"
              "`/cycles` - Enhanced cycle display with Discord timestamps\n"
              "`/compare` - Compare relic inventories with platinum values\n"
              "`/my_relics` - View your saved relic profile",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# =============================================================================
# ALL EXISTING UTILITY AND ADMIN COMMANDS (PRESERVED)
# =============================================================================

@bot.tree.command(name="status", description="Check bot status and monitored channels")
async def status_slash(interaction):
    if interaction.channel.id in ALLOWED_CHANNEL_IDS:
        relic_count = len(RELIC_DATA) if RELIC_DATA else 0
        cache_items = len(PLATINUM_CACHE)

        # Get API status, fallback to default if not initialized
        if warframe_data_manager:
            api_status = warframe_data_manager.get_current_api_status()
        else:
            api_status = {"working": False, "api_name": "Not initialized"}

        await interaction.response.send_message(
            f"✅ This channel is being monitored for API keys.\n"
            f"**API Status:** {'✅ ' + api_status['api_name'] if api_status['working'] else '❌ Unavailable'}\n"
            f"**Monitored Channels:** {', '.join(str(cid) for cid in ALLOWED_CHANNEL_IDS)}\n"
            f"**Loaded Relics:** {relic_count}\n"
            f"**Cached Prices:** {cache_items}\n"
            f"**Features:** Multi-API fallback, Discord timestamps, separate fissure embeds\n"
            f"**Commands:** `/compare`, `/fissures`, `/cycles`, `/api-status`"
        )
    else:
        await interaction.response.send_message(
            f"❌ This channel is NOT being monitored.\n"
            f"**Monitored Channels:** {', '.join(str(cid) for cid in ALLOWED_CHANNEL_IDS)}"
        )
        
@bot.tree.command(name="api-status", description="Show current API status and available endpoints")
async def api_status_command(interaction: discord.Interaction):
    """Display current API status"""
    api_status = warframe_data_manager.get_current_api_status()
    
    embed = discord.Embed(
        title="🛜 Warframe API Status", 
        color=0x4CAF50 if api_status["working"] else 0xF44336
    )
    embed.timestamp = datetime.utcnow()
    
    if api_status["working"]:
        embed.description = f"✅ **Currently Working**: {api_status['api_name']}"
    else:
        embed.description = "❌ **All APIs Unavailable**"
    
    for i, endpoint in enumerate(warframe_data_manager.api_endpoints):
        status_icon = "✅" if endpoint["status"] == "working" else "❌"
        failure_count = warframe_data_manager.api_failure_count.get(i, 0)
        
        status_text = endpoint["status"]
        if failure_count > 0:
            status_text += f" ({failure_count} failures)"
        
        embed.add_field(
            name=f"{status_icon} {endpoint['name']}",
            value=f"Type: {endpoint['type']}\nStatus: {status_text}",
            inline=True
        )
    
    await interaction.response.send_message(embed=embed)


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
    
@bot.tree.command(name="cleanup-messages", description="Admin command to cleanup stored message IDs")
@app_commands.default_permissions(administrator=True)
async def cleanup_messages_command(interaction: discord.Interaction):
    """Cleanup stored message IDs"""
    try:
        # Count before cleanup
        total_before = sum(len(guild_msgs) for guild_msgs in channel_manager.message_ids.values())
        
        # Clean up invalid message IDs
        cleaned_count = 0
        for guild_id_str in list(channel_manager.message_ids.keys()):
            guild = bot.get_guild(int(guild_id_str))
            if not guild:
                # Guild no longer exists, remove all its message IDs
                cleaned_count += len(channel_manager.message_ids[guild_id_str])
                del channel_manager.message_ids[guild_id_str]
                continue
            
            for channel_type in list(channel_manager.message_ids[guild_id_str].keys()):
                message_id = channel_manager.message_ids[guild_id_str][channel_type]
                try:
                    channel_id = channel_manager.channels[guild_id_str][channel_type]
                    channel = guild.get_channel(channel_id)
                    if channel:
                        await channel.fetch_message(message_id)
                    # If no exception, message exists and is valid
                except (discord.NotFound, KeyError):
                    # Message was deleted or channel not found
                    cleaned_count += 1
                    del channel_manager.message_ids[guild_id_str][channel_type]
        
        channel_manager.save_message_ids()
        
        total_after = sum(len(guild_msgs) for guild_msgs in channel_manager.message_ids.values())
        
        embed = discord.Embed(
            title="🧹 Message Cleanup Complete",
            description=f"Cleaned up {cleaned_count} invalid message references",
            color=0x4CAF50
        )
        embed.add_field(name="Total Before", value=str(total_before), inline=True)
        embed.add_field(name="Total After", value=str(total_after), inline=True)
        embed.add_field(name="Removed", value=str(cleaned_count), inline=True)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Error during cleanup: {e}")

# =============================================================================
# ENHANCED SETUP AND EVENT HANDLERS
# =============================================================================

async def setup_warframe_extension():
    """Setup the enhanced Warframe information extension"""
    global warframe_data_manager, subscription_manager, embed_generator, notification_manager, channel_manager
    
    try:
        # Initialize enhanced Warframe information system components
        warframe_data_manager = WarframeDataManager()
        subscription_manager = SubscriptionManager(bot)
        embed_generator = EmbedGenerator()
        notification_manager = NotificationManager(bot, subscription_manager)
        channel_manager = ChannelManager(bot)
        
        # Start the Warframe info update task
        warframe_info_update_loop.start()
        
        logging.info("✅ Enhanced Warframe information extension loaded successfully")
        
    except Exception as e:
        logging.error(f"❌ Failed to load enhanced Warframe information extension: {e}")

@bot.event
async def on_ready():
    logging.info(f"Enhanced Warframe bot logged in as {bot.user} (ID: {bot.user.id})")
    logging.info("🚀 Enhanced features: Discord timestamps, separate fissure embeds, improved icons")
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
    
    # Setup enhanced Warframe information extension
    await setup_warframe_extension()
    
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} enhanced commands")
    except Exception as e:
        logging.error(f"Failed to sync commands: {e}")
    
    logging.info("------")

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

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)

