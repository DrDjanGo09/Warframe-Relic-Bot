# 🤖 Enhanced Warframe Discord Bot

A comprehensive Discord bot for **Warframe** players featuring real-time worldstate information, relic comparison, platinum pricing, and advanced notification systems. This bot combines powerful Warframe data management with user-friendly Discord integrations.

![Python](https://img.shields.io/badge/python-v3.8+-blue.svg)
![Discord.py](https://img.shields.io/badge/discord.py-v2.3+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)

## ✨ Features

### 🌟 **Core Functionality**
- **Real-time Warframe Data** - Live worldstate information with automatic updates
- **Relic Management** - Compare relic inventories with platinum market pricing
- **Market Integration** - Real-time warframe.market API integration for pricing
- **Multi-API Fallback** - Redundant API endpoints ensure 99.9% uptime
- **Discord Timestamps** - Native Discord time formatting for all countdowns

### 🔔 **Advanced Notification System**
- **Event Subscriptions** - Get notified for specific Warframe events
- **Custom Filtering** - Filter by relic tiers, mission types, and more  
- **DM Notifications** - Receive instant notifications in your DMs
- **Smart Matching** - Intelligent notification filtering and matching

### 📊 **Auto-Updating Channels**
- **Persistent Message Editing** - Updates existing messages instead of spam
- **Separate Embeds** - Different embed types for cycles and fissures
- **Channel Management** - Easy setup and testing of auto-update channels
- **Message ID Tracking** - Efficient message management system

### 🎨 **Enhanced Visual Design**
- **Custom Emojis** - Faction, relic tier, and mission type icons
- **Color-Coded Embeds** - Visual indicators for different content types
- **Organized Layout** - Clean, readable information presentation
- **Discord Integration** - Native Discord timestamp and mention support

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token
- Warframe.market access (optional, for platinum pricing)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/enhanced-warframe-bot.git
   cd enhanced-warframe-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   Create a `.env` file in the root directory:
   ```env
   DISCORD_TOKEN=your_discord_bot_token_here
   ```

4. **Run the bot**
   ```bash
   python bot.py
   ```

## 📁 Directory Structure

```
enhanced-warframe-bot/
├── bot.py                          # Main bot file with all functionality
├── .env                            # Environment variables (create this)
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── user_relics/                    # User relic inventory storage
│   └── *.txt                       # Individual user relic files
├── comparison_reports/             # Generated comparison reports
│   └── *.txt                       # User comparison reports
├── temp_files/                     # Temporary processing files
├── user_tokens_encrypted.json      # Encrypted user API tokens
├── token_key.key                   # Encryption key for tokens
└── platinum_price_cache.json       # Cached platinum prices
```

## 🛠️ Configuration

### Environment Variables
The bot requires the following environment variable:

| Variable | Description | Required |
|----------|-------------|----------|
| `DISCORD_TOKEN` | Your Discord bot token | Yes |

### Channel Configuration
Update the `ALLOWED_CHANNEL_IDS` in the bot code to specify which channels can use certain commands:

```python
ALLOWED_CHANNEL_IDS = [
    1234567890123456789,  # Your channel ID here
    # Add more channel IDs as needed
]
```

## 📋 Commands Reference

### 🌍 **Worldstate Information**

#### `/cycles`
Display current cycle information for all Warframe locations with Discord timestamps.
- **Locations**: Cetus, Fortuna, Deimos, Zariman, Duviri
- **Features**: Real-time countdowns, visual indicators

#### `/fissures [fissure_type]`
Show void fissures organized by mission type in separate embeds.
- **Options**: `all`, `normal`, `steelpath`, `railjack`
- **Features**: Separate embeds per type, relic tier filtering

#### `/steel-path`
Display current Steel Path incursions and rewards.
- **Info**: Active missions, time remaining, rewards

#### `/arbitration`
Show current arbitration mission details.
- **Info**: Mission type, location, enemy faction, time remaining

#### `/sortie`
Display today's sortie missions with modifiers.
- **Info**: Boss, faction, mission variants, time remaining

#### `/baro`
Show Baro Ki'Teer void trader information.
- **Info**: Status, location, inventory, next arrival time

#### `/wf-status`
Show overall Warframe worldstate status.
- **Info**: Active systems, API connectivity, data freshness

### 🔔 **Notification System**

#### `/subscribe <event> [tier] [mission_type]`
Subscribe to specific Warframe event notifications.

**Event Types:**
- `cetusnight` - Cetus night cycle for Eidolon hunting
- `fortunawarm` - Fortuna warm cycle for resource farming  
- `fissuremissions` - Fissure missions (with tier/mission filters)
- `steelpathfissures` - Steel Path fissures specifically
- `arbitration` - Arbitration changes

**Tier Options:**
- `any`, `lith`, `meso`, `neo`, `axi`, `requiem`

**Mission Types:**
- `any`, `survival`, `capture`, `exterminate`, `defense`, `mobiledefense`, `spy`, `rescue`, `sabotage`, `interception`

**Examples:**
```
/subscribe fissuremissions tier:neo mission_type:survival
/subscribe cetusnight
/subscribe steelpathfissures tier:axi
```

#### `/unsubscribe <event> [tier] [mission_type]`
Unsubscribe from specific event notifications.
- Same parameters as `/subscribe`

#### `/my-subscriptions`
View all your current subscriptions with details.

### 🏗️ **Channel Management**

#### `/set-cycles-channel <channel>`
Set up auto-updating cycles information channel.
- **Permissions**: Administrator only
- **Features**: Immediate test update, persistent message editing

#### `/set-fissures-channel <channel>`  
Set up auto-updating fissures information channel.
- **Permissions**: Administrator only
- **Features**: Separate embeds per mission type, automatic updates

#### `/test-channels`
Manually test all configured auto-update channels.
- **Permissions**: Administrator only
- **Use**: Verify channel configurations are working

### 💎 **Relic Management**

#### `/compare <comparison_type> [user_mention]`
Compare relic inventories with platinum market values.
- **Types**: Various comparison algorithms available
- **Features**: Platinum pricing, detailed analysis, exportable reports

#### `/my-relics`
View your saved relic profile and statistics.

#### `/upload-relics`
Upload your relic inventory for comparison and tracking.

### ⚙️ **Admin & Utility**

#### `/bot-features`
Display all enhanced bot features and capabilities.

#### `/api-status`
Show current API endpoint status and health.
- **Info**: Active endpoints, failure counts, response times

#### `/cleanup-messages`
Clean up stored message IDs (Admin only).

#### `/list-users`
List users with stored relic data (Admin only).

## 🔧 Technical Details

### Architecture
- **Modular Design**: Separate classes for different functionalities
- **Async/Await**: Full asynchronous operation for optimal performance
- **Error Handling**: Comprehensive try-catch blocks throughout
- **Rate Limiting**: Respect for API rate limits and concurrent request management

### Key Components
1. **WarframeDataManager** - Handles all Warframe API interactions
2. **SubscriptionManager** - Manages user event subscriptions
3. **EmbedGenerator** - Creates formatted Discord embeds
4. **NotificationManager** - Handles user notifications
5. **ChannelManager** - Manages auto-updating channels

### API Integration
- **Primary**: Official Warframe Worldstate API
- **Secondary**: Alternative endpoints for redundancy
- **Market**: warframe.market API for platinum pricing
- **Fallback System**: Automatic failover between endpoints

### Data Storage
- **Relics**: Text-based storage for user inventories
- **Tokens**: Encrypted storage with Fernet encryption
- **Cache**: JSON-based caching for performance
- **Messages**: Persistent message ID tracking

## 🚦 Status & Monitoring

The bot includes comprehensive monitoring and status reporting:

- **API Health**: Real-time API endpoint monitoring
- **Update Loop**: 5-minute update cycle for worldstate data  
- **Error Logging**: Detailed logging for debugging
- **Performance**: Concurrent request handling with rate limiting

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

### Development Setup
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Make your changes
4. Add tests if applicable
5. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
6. Push to the branch (`git push origin feature/AmazingFeature`)
7. Open a Pull Request

## 📝 Requirements

```txt
discord.py>=2.3.0
aiohttp>=3.8.0
requests>=2.28.0
python-dotenv>=1.0.0
cryptography>=41.0.0
```

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Warframe Community Developers** - For providing excellent APIs
- **Discord.py Community** - For the amazing Discord library
- **warframe.market** - For platinum pricing data
- **Digital Extremes** - For creating Warframe

## 📞 Support

If you encounter any issues or have questions:

1. Check the [Issues](https://github.com/your-username/enhanced-warframe-bot/issues) page
2. Create a new issue with detailed information
3. Join our Discord server for community support

## 🔄 Update History

### Latest Version Features:
- ✅ Enhanced visual design with custom emojis
- ✅ Discord timestamp integration
- ✅ Separate fissure embeds by mission type
- ✅ Advanced notification system with filtering
- ✅ Multi-API fallback system
- ✅ Auto-updating channels with message editing
- ✅ Comprehensive error handling and logging
- ✅ Modular architecture for easy maintenance

---

**Built with ❤️ for the Warframe community**
