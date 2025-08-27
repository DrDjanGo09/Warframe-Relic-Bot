# Warframe Relic Comparison Discord Bot

A comprehensive Discord bot for Warframe players that automatically fetches and compares relic inventories with real-time platinum market pricing from Warframe.Market. Features automatic relic data updates, encrypted token storage, and detailed comparison reports.

## 🌟 Features

- **Automatic Relic Inventory Sync**: Connect your AlecaFrame API token for automatic 6-hourly updates
- **Real-time Platinum Pricing**: Live market data from Warframe.Market with smart caching
- **Multi-user Comparisons**: Compare relic inventories between up to 4 players
- **Vaulted Status Detection**: Identifies vaulted vs available relics automatically  
- **Detailed Reports**: Generate comprehensive comparison reports with drop information
- **Secure Token Storage**: Encrypted API token storage with Fernet encryption
- **Smart Price Caching**: 1-hour price cache to minimize API calls and improve performance
- **Interactive Pagination**: Browse comparison results with Discord UI components
- **Admin Controls**: Complete administrative commands for bot management

## 📋 Prerequisites

- Python 3.8+
- Discord Bot Token
- AlecaFrame Public API Token (optional for auto-updates)

## 🚀 Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/your-username/warframe-relic-bot.git
   cd warframe-relic-bot
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create Environment File**
   ```bash
   cp .env.example .env
   ```

4. **Configure Environment Variables**
   Edit `.env` file:
   ```env
   DISCORD_TOKEN=your_discord_bot_token_here
   ```

5. **Set Channel IDs**
   Edit `bot.py` and update `ALLOWED_CHANNEL_IDS` with your Discord channel IDs:
   ```python
   ALLOWED_CHANNEL_IDS = {
       1234567890123456789,  # Your channel ID here
       # Add more channel IDs as needed
   }
   ```

6. **Run the Bot**
   ```bash
   python bot.py
   ```

## 🔧 Setup Guide

### Getting Your Discord Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section
4. Create a bot and copy the token
5. Add the token to your `.env` file

### Getting Your AlecaFrame API Token

1. Visit [AlecaFrame Stats](https://stats.alecaframe.com)
2. Click "Get Public Token"
3. Log in with your Warframe credentials
4. Copy your Public Token
5. Paste it in any monitored Discord channel - the bot will detect and save it

### Bot Permissions

Ensure your bot has these Discord permissions:
- Send Messages
- Read Messages/View Channels
- Use Slash Commands
- Attach Files
- Use External Emojis
- Add Reactions

## 📂 Directory Structure

```
warframe-relic-bot/
├── bot.py                          # Main bot file
├── .env.example                   # Example environment file
├── .gitignore                     # Git ignore file
├── requirements.txt               # Python dependencies
├── README.md                      # This file
├── user_relics/                   # User relic data storage (User relic info will be stored here)
├── comparison_reports/            # Generated reports (Comparison report will be stored here)
├── temp_files/                    # Temporary files (Relic info of someone you checked)
├── relic_data.json               # Warframe relic database
├── platinum_price_cache.json     # Price cache file
├── user_tokens_encrypted.json    # Encrypted user tokens
└── token_key.key                 # Encryption key
```

## 🎮 How to Use

### Initial Setup

1. **Invite the bot** to your Discord server with appropriate permissions
2. **Configure monitored channels** by adding channel IDs to `ALLOWED_CHANNEL_IDS` in `bot.py`
3. **Get your AlecaFrame token** from https://stats.alecaframe.com
4. **Paste your token** in any monitored channel
5. **Confirm ownership** when prompted by clicking "✅ This is MY API key"

### Basic Workflow

1. **First Time Users**: Paste your AlecaFrame API token in a monitored channel
2. **Auto-Updates**: Your relic data will automatically update every 6 hours
3. **Compare Inventories**: Use `/compare user1 user2` to compare with friends
4. **View Your Data**: Use `/my_relics` to see your current inventory
5. **Check Status**: Use `/status` to verify bot configuration

## 🔨 Commands Reference

### User Commands

#### `/compare user1 [user2] [user3] [user4]`
Compare relic inventories between 2-4 users with platinum values
- **user1**: Required - First user identifier (Discord ID or username)
- **user2-4**: Optional - Additional users to compare
- **Output**: Interactive paginated comparison with platinum values, vaulted status, and detailed reports

**Example:**
```
/compare user1:123456789 user2:987654321
```

#### `/my_relics`
Display your personal relic inventory data
- **Access**: Private (ephemeral message)
- **Output**: Text file with your current relic counts

#### `/auto_update_status`
Check your automatic update configuration
- **Access**: Private (ephemeral message)
- **Output**: Shows if auto-updates are enabled, token save date, update frequency

#### `/disable_auto_update`
Disable automatic relic data updates and remove stored API token
- **Access**: Private (ephemeral message)
- **Effect**: Stops auto-updates and deletes your encrypted token

#### `/list_users`
View all users with stored relic data
- **Access**: Public
- **Output**: List of users with profile timestamps and file counts

#### `/list_commands`
Show all available slash commands
- **Access**: Public
- **Output**: Complete command reference

#### `/status`
Check bot operational status and configuration
- **Access**: Public
- **Output**: Monitored channels, loaded data counts, available commands

#### `/cache_status`
View platinum price cache information
- **Access**: Public
- **Output**: Cache size, age, expiry status

### Administrator Commands

#### `/update_relics`
**[ADMIN ONLY]** - Update relic database from external sources
- **Requirement**: Administrator permissions
- **Effect**: Fetches latest relic data from WFCD and WarframeStats APIs
- **Output**: Success message with total relics and vaulted counts

#### `/remove_user_data user_id [reason]`
**[ADMIN ONLY]** - Remove all relic data for a specific user
- **user_id**: Discord user ID to remove data for
- **reason**: Optional reason for removal (logged for auditing)
- **Effect**: Deletes all relic files for the specified user

#### `/clear_price_cache`
**[ADMIN ONLY]** - Clear the platinum price cache
- **Requirement**: Administrator permissions
- **Effect**: Forces fresh price fetching on next comparison

## 🔄 Automatic Features

### Auto-Updates
- **Frequency**: Every 6 hours
- **Trigger**: Automatic background task
- **Requirements**: Saved and encrypted API token
- **Process**: Fetches fresh relic data and saves timestamped files

### Price Caching
- **Duration**: 1 hour cache expiry
- **Source**: Warframe.Market API
- **Rate Limiting**: Max 3 concurrent requests, 0.35s delays
- **Persistence**: Cached prices saved to disk across bot restarts

### Data Storage
- **Relic Files**: Timestamped text files per user
- **Encryption**: Fernet encryption for API tokens
- **Reports**: Detailed comparison reports with platinum analysis

## 🔐 Security Features

### Token Encryption
- **Algorithm**: Fernet (symmetric encryption)
- **Key Storage**: Local `token_key.key` file
- **Auto-generation**: Encryption key generated on first run
- **Data Protection**: API tokens encrypted at rest

### Access Control
- **Channel Restrictions**: Bot only responds in configured channels
- **Owner Verification**: Users must confirm API token ownership
- **Admin Commands**: Restricted to users with Administrator permissions
- **Audit Logging**: All admin actions are logged with reasons

## 📊 Data Sources

### Relic Information
- **Primary**: [WFCD Warframe Drop Data](https://github.com/WFCD/warframe-drop-data)
- **Vaulted Status**: [WarframeStats API](https://api.warframestat.us/)
- **Update Frequency**: Manual admin updates via `/update_relics`

### Platinum Prices
- **Source**: [Warframe.Market API](https://warframe.market/)
- **Method**: Average of top 3 online seller prices
- **Cache**: 1-hour intelligent caching system
- **Rate Limits**: Respected with delays and concurrent request limits

### Personal Data
- **Source**: [AlecaFrame Stats](https://stats.alecaframe.com/)
- **Method**: Binary data parsing from public token API
- **Storage**: Encrypted tokens, timestamped relic files
- **Updates**: Automatic 6-hourly refresh

## 🛠️ Troubleshooting

### Common Issues

**Bot not responding to commands:**
- Check if the channel ID is in `ALLOWED_CHANNEL_IDS`
- Verify bot permissions (Send Messages, Use Slash Commands)
- Confirm the bot is online and properly invited

**API token not saving:**
- Ensure you clicked "✅ This is MY API key" when prompted
- Check if the token format is valid (AlecaFrame tokens are long base64 strings)
- Verify the bot has file write permissions

**Relic data appears corrupted:**
- This usually indicates binary parsing issues
- Check AlecaFrame API status
- Try re-saving your API token

**Price fetching errors:**
- Check internet connectivity
- Warframe.Market API may be temporarily down
- Use `/clear_price_cache` to reset cache if needed

**Auto-updates not working:**
- Check `/auto_update_status` to verify configuration
- Ensure your API token is still valid on AlecaFrame
- Check bot logs for error messages

### Log Files
The bot outputs detailed logs to console including:
- API request success/failures
- Data parsing results
- User interactions
- Error conditions

### File Permissions
Ensure the bot can read/write to:
- `user_relics/` directory
- `comparison_reports/` directory
- `temp_files/` directory
- Configuration files (JSON, key files)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 style guidelines
- Add docstrings to new functions
- Test commands thoroughly before submitting
- Update documentation for new features

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **Warframe Community**: For continued support and feedback
- **Digital Extremes**: For creating Warframe
- **WFCD Team**: For maintaining comprehensive drop data
- **Warframe.Market**: For providing market price APIs
- **AlecaFrame**: For relic inventory API access

## 📧 Support

- **Issues**: Create a GitHub issue for bug reports
- **Features**: Submit feature requests via GitHub issues
- **Questions**: Join our Discord support server (link in bio)

---

**Disclaimer**: This bot is not affiliated with Digital Extremes or Warframe. It's a community-created tool for player convenience.
