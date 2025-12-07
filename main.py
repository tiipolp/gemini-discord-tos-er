import discord
import google.generativeai as genai
import os
import logging
import json
import re
import traceback
import threading
import asyncio
import pystray
import time
import subprocess
from PIL import Image, ImageDraw
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configuration State
isModerationActive = True
enforcementLevel = "Standard"
apiTier = "Free"  # "Free" or "Tier 1"
moderationMode = "Hybrid"  # "Hybrid", "Edit Only", "Delete Only"
customReplacement = "I follow Discord ToS"
customPromptInstruction = "" # Custom instruction for Gemini replacements

# API State
apiKeys = []
currentKeyIndex = 0
lastRequestTime = 0

# Runtime State
botThread = None
trayIcon = None
processingTask = None

CONFIG_FILE = 'config.json'

def save_config():
    config = {
        "isModerationActive": isModerationActive,
        "enforcementLevel": enforcementLevel,
        "apiTier": apiTier,
        "moderationMode": moderationMode,
        "customReplacement": customReplacement,
        "customPromptInstruction": customPromptInstruction,
        "currentKeyIndex": currentKeyIndex
    }
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        log.error(f"Failed to save config: {e}")

def load_config():
    global isModerationActive, enforcementLevel, apiTier, moderationMode, customReplacement, customPromptInstruction, currentKeyIndex
    if not os.path.exists(CONFIG_FILE):
        return

    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            
        isModerationActive = config.get("isModerationActive", True)
        enforcementLevel = config.get("enforcementLevel", "Standard")
        apiTier = config.get("apiTier", "Free")
        moderationMode = config.get("moderationMode", "Hybrid")
        customReplacement = config.get("customReplacement", "I follow Discord ToS")
        customPromptInstruction = config.get("customPromptInstruction", "")
        currentKeyIndex = config.get("currentKeyIndex", 0)
        
        log.info("Config loaded successfully")
    except Exception as e:
        log.error(f"Failed to load config: {e}")

jsonRegex = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)

# Setup logging but keep it simple
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('tos.log'), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# Load API Keys
env_keys = os.getenv('GEMINI_API_KEYS')
if env_keys:
    apiKeys = [k.strip() for k in env_keys.split(',') if k.strip()]
else:
    single_key = os.getenv('GEMINI_API_KEY')
    if single_key:
        apiKeys = [single_key]

if not apiKeys:
    log.error("No API keys found! Set GEMINI_API_KEYS (comma separated) or GEMINI_API_KEY in .env")

# Load config before configuring GenAI so we use the saved key index
load_config()

# Ensure key index is valid
if apiKeys and currentKeyIndex >= len(apiKeys):
    currentKeyIndex = 0
    save_config()

def configure_genai():
    global currentKeyIndex
    if not apiKeys:
        return
    try:
        genai.configure(api_key=apiKeys[currentKeyIndex])
        log.info(f"Switched to API Key index: {currentKeyIndex}")
    except Exception as e:
        log.error(f"Failed to configure API key: {e}")

configure_genai()
model = genai.GenerativeModel('gemini-2.5-flash-lite')

client = discord.Client()

BASE_TOS_CONTEXT = """You are an AI assistant that analyzes messages for Discord Terms of Service violations based on the Official ToS (Effective Sept 29, 2025).

Discord's Terms of Service specifically prohibit the following behaviors (Section 9):

1. HARM TO OTHERS:
- Exploiting, harassing, or bullying users
- Spamming, auto-messaging, or auto-dialing
- Infringing Intellectual Property (Copyright/Trademark)
- Attempting to access another user's account
- Planning or causing real-world harm

2. HARM TO DISCORD:
- Intentionally overburdening or attacking Discord systems
- Scraping or using automation (bots/spiders) without written consent
- Transmitting viruses or malicious code
- Using unauthorized software to modify the client (Reverse Engineering)
- Selling or commercializing user data

3. ILLEGAL ACTIVITIES:
- Planning or committing any crime
- Sexual content involving minors (CSAM)
- Threats of violence

Response format (JSON only):
{
    "violates_tos": true/false,
    "severity": "partial" or "full",
    "rewritten_message": "safe version of the full message (optional)",
    "violations": [
        {
            "phrase": "exact phrase that violates",
            "reason": "brief reason linking to specific prohibition above",
            "replacement": "suggested safe replacement" or null
        }
    ],
    "action": "edit" or "delete"
}

IMPORTANT GUIDELINES:
1. IGNORE ALL URLs, LINKS, and GIFs. Do not flag a message just because it contains a link, even if the link looks suspicious. Assume all links are safe.
2. CONTEXTUAL ACCURACY: Interpret the ToS as Discord intends. The prohibition on "Harm" and "Violence" applies to REAL-WORLD threats and targeted harassment. It does NOT apply to standard video game terminology (e.g., "killing", "shooting") unless it is used to threaten or harass a specific user.
3. CSAM DISTINCTION: Do NOT flag general adult content, fetishes (e.g., scat, gore, roleplay), or NSFW humor as CSAM unless it EXPLICITLY depicts or describes minors. "Scat" or "poop" jokes are NOT CSAM.
4. If the message contains ANY safe content that can be preserved, set severity to "partial" and action to "edit".
5. Only set severity to "full" and action to "delete" if the ENTIRE message is a violation.
6. Ensure the "phrase" field matches the text in the message EXACTLY.
7. CONSISTENCY CHECK: If "violates_tos" is false, "violations" MUST be empty and "action" MUST be null. Do not provide replacements for non-violations.
"""

def getEnforcementInstructions(level):
    if level == "Strict":
        return """
ENFORCEMENT LEVEL: STRICT (Family Friendly & Full Compliance)
- Flag ALL profanity, suggestive jokes, and "zesty" comments.
- Flag ALL mentions of client modifications, scripts, or game exploits (Strict adherence to ToS Section 9 "Harm to Discord").
- Zero tolerance for harassment, even in jest.
"""
    elif level == "Standard":
        return """
ENFORCEMENT LEVEL: STANDARD (ToS Baseline)
- Allow mild profanity (shit, fuck, etc.) in casual conversation.
- Allow suggestive jokes/humor unless it is Explicit Sexual Content (prohibited in non-age-restricted channels).
- Flag Targeted Harassment or Bullying, but allow friendly banter.
- Flag Malicious Automation: Explicit mentions of scraping, token loggers, or DDoS tools (ToS Section 9).
"""
    elif level == "Lenient":
        return """
ENFORCEMENT LEVEL: LENIENT (Minimum ToS Compliance)
- Allow ALL profanity, sexual humor, and "edgy" jokes.
- ONLY flag Severe ToS Violations: Hate Speech (Slurs), Real Threats of Violence, Doxxing, Illegal Content (CSAM), or Malicious Malware distribution.
- Ignore minor ToS infractions like spam, self-bots, or game modding discussion unless it causes real harm.
"""
    return ""

async def checkMessageWithGemini(messageContent):
    global currentKeyIndex, lastRequestTime
    
    # Rate Limiting Logic
    now = time.time()
    if apiTier == "Free":
        # 20 RPM = 1 request every 3 seconds
        timeSinceLast = now - lastRequestTime
        if timeSinceLast < 3.0:
            wait_time = 3.0 - timeSinceLast
            log.info(f"Rate limit (Free): Waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
    else:
        # Tier 1: 4000 RPM = ~0.015s per request (negligible, but let's be safe)
        timeSinceLast = now - lastRequestTime
        if timeSinceLast < 0.02:
            await asyncio.sleep(0.02)
            
    lastRequestTime = time.time()

    try:
        levelInstructions = getEnforcementInstructions(enforcementLevel)
        
        # Construct the replacement rule dynamically
        if customPromptInstruction:
            replacementRule = f"REPLACEMENT RULE: You MUST provide a 'rewritten_message' that rewrites the ENTIRE message to be safe, based on this instruction: {customPromptInstruction}"
        elif moderationMode == "Edit Only":
            replacementRule = "REPLACEMENT RULE: You MUST provide a 'rewritten_message' that rewrites the ENTIRE message to be safe. It MUST be exactly: \"I follow discord tos\"."
        else:
            replacementRule = "REPLACEMENT RULE: For 'partial' violations, the 'replacement' MUST be exactly: \"I follow discord tos\"."
            
        prompt = f"{BASE_TOS_CONTEXT}\n{replacementRule}\n{levelInstructions}\n\nMessage to analyze:\n\"{messageContent}\"\n\nProvide your analysis in JSON format."
        
        # Retry logic for multiple keys
        max_retries = len(apiKeys)
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                responseText = response.text.strip()
                break # Success
            except Exception as e:
                log.error(f"API Error with key index {currentKeyIndex}: {e}")
                if attempt < max_retries - 1:
                    currentKeyIndex = (currentKeyIndex + 1) % len(apiKeys)
                    save_config() # Save new key index
                    configure_genai()
                    log.info("Retrying with next key...")
                    await asyncio.sleep(1)
                else:
                    raise e # All keys failed

        jsonMatch = jsonRegex.search(responseText)
        if jsonMatch:
            responseText = jsonMatch.group(1)
        
        analysis = json.loads(responseText)
        log.info(f"Gemini analysis ({enforcementLevel}): {analysis}")
        return analysis
        
    except json.JSONDecodeError as e:
        log.error(f"JSON parse error: {e} | Text: {responseText}")
        return {"violates_tos": False}
    except Exception as e:
        log.error(f"Gemini API error (All keys failed): {e}")
        return {"violates_tos": False}

async def moderateMessage(message, analysis):
    try:
        if not analysis.get('violates_tos', False):
            return
        
        action = analysis.get('action', 'edit')
        violations = analysis.get('violations', [])
        rewritten = analysis.get('rewritten_message')
        
        # Apply Moderation Mode Logic
        if moderationMode == "Delete Only":
            action = "delete"
        elif moderationMode == "Edit Only":
            action = "edit"
        # "Hybrid" keeps the original action
        
        if action == 'delete':
            log.warning(f"Deleting message: {message.content}")
            await message.delete()
            
        elif action == 'edit':
            # Priority 1: Full rewrite from model (Best for custom prompts/Edit Only)
            if rewritten:
                if rewritten != message.content:
                    log.warning(f"Rewriting to: {rewritten}")
                    await message.edit(content=rewritten)
                return

            # Priority 2: Violation replacements (Best for partial/standard mode)
            if violations:
                editedContent = message.content
                
                # optimization: sort by length so we dont replace substrings incorrectly
                violations.sort(key=lambda v: len(v.get('phrase', '')), reverse=True)
                
                for violation in violations:
                    phrase = violation.get('phrase', '')
                    replacement = violation.get('replacement')
                    
                    # Determine final replacement
                    final_replacement = customReplacement # Default to static setting
                    
                    # If user has a custom prompt instruction, trust the model's output
                    if customPromptInstruction and replacement:
                        final_replacement = replacement
                    
                    if phrase:
                        editedContent = re.sub(re.escape(phrase), final_replacement, editedContent, flags=re.IGNORECASE)
                
                if editedContent != message.content:
                    log.warning(f"Editing to: {editedContent}")
                    await message.edit(content=editedContent)
            
    except discord.errors.NotFound:
        log.error("Message gone before we could edit it")
    except discord.errors.Forbidden:
        log.error("Missing permissions to edit/delete")
    except Exception as e:
        log.error(f"Moderation failed: {e}")

@client.event
async def on_ready():
    log.info(f'Logged in as {client.user} ({client.user.id})')
    log.info('Moderation active.')

@client.event
async def on_message(message):
    global isModerationActive
    
    if not isModerationActive:
        return

    if message.author.id != client.user.id or not message.content:
        return
    
    log.info(f"Checking: {message.content}")
    
    analysis = await checkMessageWithGemini(message.content)
    
    if analysis.get('violates_tos', False):
        await moderateMessage(message, analysis)

def createTrayIcon():
    global trayIcon, isModerationActive, enforcementLevel, apiTier, moderationMode, customReplacement

    def onClicked(icon, item):
        global isModerationActive
        strItem = str(item)
        if strItem == "Enable Moderation":
            isModerationActive = not isModerationActive
            save_config()
            state = "Enabled" if isModerationActive else "Disabled"
            icon.notify(f"ToS Moderation: {state}", "Discord Bot")
            log.info(f"Toggled moderation: {state}")

    def onLevelSelect(icon, item):
        global enforcementLevel
        enforcementLevel = str(item)
        save_config()
        icon.notify(f"Level: {enforcementLevel}", "Discord Bot")
        log.info(f"Level set to: {enforcementLevel}")

    def onTierSelect(icon, item):
        global apiTier
        apiTier = str(item)
        save_config()
        icon.notify(f"API Tier: {apiTier}", "Discord Bot")
        log.info(f"API Tier set to: {apiTier}")

    def onModeSelect(icon, item):
        global moderationMode
        moderationMode = str(item)
        save_config()
        icon.notify(f"Mode: {moderationMode}", "Discord Bot")
        log.info(f"Moderation Mode set to: {moderationMode}")

    def onSetReplacement(icon, item):
        global customReplacement
        
        # Use PowerShell for a robust input dialog on Windows
        try:
            safe_current = customReplacement.replace("'", "''")
            ps_script = f"""
            Add-Type -AssemblyName Microsoft.VisualBasic
            $res = [Microsoft.VisualBasic.Interaction]::InputBox('Enter new replacement text:', 'Set Replacement Text', '{safe_current}')
            Write-Output $res
            """
            process = subprocess.Popen(["powershell", "-Command", ps_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=0x08000000)
            result, _ = process.communicate()
            new_text = result.strip()
            
            if new_text:
                customReplacement = new_text
                save_config()
                icon.notify(f"Replacement set to: {customReplacement}", "Discord Bot")
                log.info(f"Custom replacement set to: {customReplacement}")
                
        except Exception as e:
            log.error(f"Failed to open dialog: {e}")
            icon.notify("Error opening input dialog", "Discord Bot")

    def onSetCustomPrompt(icon, item):
        global customPromptInstruction
        
        try:
            safe_current = customPromptInstruction.replace("'", "''")
            ps_script = f"""
            Add-Type -AssemblyName Microsoft.VisualBasic
            $res = [Microsoft.VisualBasic.Interaction]::InputBox('Enter custom prompt instruction (Leave empty for default):', 'Set Custom Prompt', '{safe_current}')
            Write-Output $res
            """
            process = subprocess.Popen(["powershell", "-Command", ps_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=0x08000000)
            result, _ = process.communicate()
            new_text = result.strip()
            
            # Allow clearing it
            customPromptInstruction = new_text
            save_config()
            
            if customPromptInstruction:
                icon.notify(f"Custom Prompt Active", "Discord Bot")
                log.info(f"Custom prompt set to: {customPromptInstruction}")
            else:
                icon.notify(f"Custom Prompt Disabled", "Discord Bot")
                log.info(f"Custom prompt disabled")
                
        except Exception as e:
            log.error(f"Failed to open dialog: {e}")
            icon.notify("Error opening input dialog", "Discord Bot")

    def onExit(icon, item):
        icon.stop()
        os._exit(0)

    # simple icon generation
    image = Image.new('RGB', (64, 64), color=(114, 137, 218))
    dc = ImageDraw.Draw(image)
    dc.rectangle([16, 16, 48, 48], fill=(255, 255, 255))
    
    menu = pystray.Menu(
        pystray.MenuItem(
            "Enable Moderation", 
            onClicked, 
            checked=lambda item: isModerationActive
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Enforcement Level", pystray.Menu(
            pystray.MenuItem("Strict", onLevelSelect, checked=lambda item: enforcementLevel == "Strict"),
            pystray.MenuItem("Standard", onLevelSelect, checked=lambda item: enforcementLevel == "Standard"),
            pystray.MenuItem("Lenient", onLevelSelect, checked=lambda item: enforcementLevel == "Lenient")
        )),
        pystray.MenuItem("API Tier", pystray.Menu(
            pystray.MenuItem("Free", onTierSelect, checked=lambda item: apiTier == "Free"),
            pystray.MenuItem("Tier 1", onTierSelect, checked=lambda item: apiTier == "Tier 1")
        )),
        pystray.MenuItem("Moderation Mode", pystray.Menu(
            pystray.MenuItem("Hybrid", onModeSelect, checked=lambda item: moderationMode == "Hybrid"),
            pystray.MenuItem("Edit Only", onModeSelect, checked=lambda item: moderationMode == "Edit Only"),
            pystray.MenuItem("Delete Only", onModeSelect, checked=lambda item: moderationMode == "Delete Only")
        )),
        pystray.MenuItem("Set Replacement Text", onSetReplacement),
        pystray.MenuItem("Set Custom Prompt", onSetCustomPrompt),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", onExit)
    )

    trayIcon = pystray.Icon("Discord ToS Bot", image, "Discord ToS Moderator", menu)
    trayIcon.run()

def runBot(token):
    try:
        client.run(token)
    except discord.errors.LoginFailure:
        log.error("Bad token in .env file")
    except Exception as e:
        log.error(f"Bot crash: {e}")

def main():
    token = os.getenv('DISCORD_TOKEN')
    apiKey = os.getenv('GEMINI_API_KEY')
    
    if not token or not apiKey:
        log.error("Missing DISCORD_TOKEN or GEMINI_API_KEY in .env")
        return
    
    log.info("Starting up...")
    
    botThread = threading.Thread(target=runBot, args=(token,), daemon=True)
    botThread.start()
    
    createTrayIcon()

if __name__ == '__main__':
    main()