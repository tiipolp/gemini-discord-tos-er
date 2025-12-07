# Discord ToS Self-Bot Moderator

An AI-powered self-bot that monitors your Discord messages to prevent Terms of Service violations using Google's Gemini AI.

## Important Warning

Using self-bots is against Discord's Terms of Service. This project is for educational purposes only. Use at your own risk.

## Setup

### 1. Prerequisites
- Python 3.8 or higher
- Discord user token
- Google Gemini API key

### 2. Installation
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file based on `.env.example` and add your tokens:
   ```bash
   cp .env.example .env
   ```

### 3. Configuration

**Discord Token:**
How to Get Your Discord Token From the Browser Console

1. Open the browser console with F12 or Ctrl + Shift + I.
2. Enable mobile device emulation with Ctrl + Shift + M. (may not be needed for some)
3. Paste the following code into the console and press Enter:

```javascript
const iframe = document.createElement('iframe');
console.log(
  'Token: %c%s',
  'font-size:16px;',
  JSON.parse(document.body.appendChild(iframe).contentWindow.localStorage.token)
);
iframe.remove();
```

Alternatively, you can just go to the Application tab, then Local Storage, and find the token key under https://discord.com/ after you have enabled mobile device emulation.

**Gemini API Key:**
1. Visit https://aistudio.google.com/app/api-keys
2. Create an API key in the top left corner.
3. Create a new project if you don't have one.
4. Names of key or project do not matter.
5. Copy the API key and paste it into your `.env` file.

**Multiple API Keys (Optional):**
If you want to use multiple keys to avoid rate limits or downtime, you can provide a comma-separated list in the `.env` file:
```env
GEMINI_API_KEYS=key1,key2,key3
```
The bot will automatically rotate to the next key if one fails.

**Note on Gemini API Tiers:**
It is highly recommended to use the **Tier 1 (Pay-as-you-go)** plan for the Gemini API.
- **Free Tier:** Has lower rate limits (15 RPM) which may cause the bot to lag or miss messages during rapid conversation.
- **Tier 1:** This is still free for personal use levels, but requires setting up billing in Google Cloud. It significantly increases rate limits (4000 RPM). You will not be charged unless you exceed massive usage limits, but simply having billing set up unlocks the higher tier. Additionally, you can disable the billing and keep the tier 1 benefits. 

How to disable billing for a project: https://docs.cloud.google.com/billing/docs/how-to/modify-project#how-to-disable-billing

How to set up billing: https://docs.cloud.google.com/billing/docs/how-to/modify-project#enable_billing_for_a_project

## Usage

### Running the Bot
Run the main script:
```bash
python main.py
```
The bot will appear in your system tray (taskbar).

### System Tray Controls
Right-click the tray icon to:
- **Enable/Disable Moderation**: Toggle the bot on or off.
- **Enforcement Level**: Change how strict the bot is.
- **API Tier**: Select your API tier to adjust rate limiting (Free vs Tier 1).
- **Moderation Mode**: Choose how the bot handles violations (Hybrid, Edit Only, Delete Only).
- **Set Replacement Text**: Customize the text used when editing messages (Default: "I follow Discord ToS").
- **Exit**: Completely stop the bot.

### Enforcement Levels
- **Strict**: Zero tolerance. Flags everything including mild profanity and suggestive jokes.
- **Standard** (Default): Allows mild profanity and casual conversation. Blocks hate speech, threats, and explicit content.
- **Lenient**: Very permissive. Allows all profanity and sexual humor. Only blocks severe violations like hard slurs, real threats, doxxing, or illegal content.

### Moderation Modes
- **Hybrid** (Default): Edits messages with partial violations (e.g., one bad phrase) and deletes messages with full violations (e.g., hate speech).
- **Edit Only**: Always attempts to edit the message to remove the violation, never deletes.
- **Delete Only**: Always deletes the message if a violation is found, never edits.

### API Tiers & Rate Limiting
- **Free Tier**: Enforces a 3-second delay between requests (20 RPM) to prevent errors.
- **Tier 1**: Removes the delay, allowing for much faster processing (4000 RPM). Select this in the tray menu if you have a paid/billed account.

### Add to Startup
To have the bot start automatically with Windows:
1. Run the `install_startup.bat` file included in the folder.
2. The bot will now launch silently in the background when you log in.

## Logs
All activity is logged to `tos.log`.
