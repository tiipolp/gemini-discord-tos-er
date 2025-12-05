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
from PIL import Image, ImageDraw
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

isModerationActive = True
enforcementLevel = "Standard"
botThread = None
trayIcon = None

jsonRegex = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)

# Setup logging but keep it simple
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('tos.log'), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# API setup
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
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
2. If the message contains ANY safe content that can be preserved, set severity to "partial" and action to "edit".
3. Only set severity to "full" and action to "delete" if the ENTIRE message is a violation.
4. For "partial" violations, the "replacement" MUST be exactly: "I follow discord tos".
5. Ensure the "phrase" field matches the text in the message EXACTLY."""

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
    try:
        levelInstructions = getEnforcementInstructions(enforcementLevel)
        prompt = f"{BASE_TOS_CONTEXT}\n{levelInstructions}\n\nMessage to analyze:\n\"{messageContent}\"\n\nProvide your analysis in JSON format."
        
        response = model.generate_content(prompt)
        responseText = response.text.strip()
        
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
        log.error(f"Gemini API error: {e}")
        return {"violates_tos": False}

async def moderateMessage(message, analysis):
    try:
        if not analysis.get('violates_tos', False):
            return
        
        action = analysis.get('action', 'edit')
        violations = analysis.get('violations', [])
        
        if action == 'delete':
            log.warning(f"Deleting message: {message.content}")
            await message.delete()
            
        elif action == 'edit' and violations:
            editedContent = message.content
            
            # optimization: sort by length so we dont replace substrings incorrectly
            violations.sort(key=lambda v: len(v.get('phrase', '')), reverse=True)
            
            for violation in violations:
                phrase = violation.get('phrase', '')
                replacement = violation.get('replacement')
                
                if phrase and replacement:
                    editedContent = re.sub(re.escape(phrase), replacement, editedContent, flags=re.IGNORECASE)
                elif phrase:
                    editedContent = re.sub(re.escape(phrase), "I follow discord tos", editedContent, flags=re.IGNORECASE)
            
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
    global trayIcon, isModerationActive, enforcementLevel

    def onClicked(icon, item):
        global isModerationActive
        strItem = str(item)
        if strItem == "Enable Moderation":
            isModerationActive = not isModerationActive
            state = "Enabled" if isModerationActive else "Disabled"
            icon.notify(f"ToS Moderation: {state}", "Discord Bot")
            log.info(f"Toggled moderation: {state}")

    def onLevelSelect(icon, item):
        global enforcementLevel
        enforcementLevel = str(item)
        icon.notify(f"Level: {enforcementLevel}", "Discord Bot")
        log.info(f"Level set to: {enforcementLevel}")

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