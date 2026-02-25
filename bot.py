import asyncio
import json
import logging
import re
import os
import subprocess
from datetime import datetime
from pathlib import Path
from telegram.ext import Application
from playwright.async_api import async_playwright

# ==========================================
# 1. قسم الإعدادات
# ==========================================
BOT_TOKEN = "8204515967:AAG6VnSCJ3_-K-XxMRKK2ClB83aW7WZ2dhc"
CHANNEL_ID = -1003678896538

IVASMS_EMAIL = "vipbyr1@gmail.com"
IVASMS_PASSWORD = "svena11.m"

LOGIN_URL = "https://www.ivasms.com/login"
SMS_URL = "https://www.ivasms.com/portal/sms/received/getsms"

CHECK_INTERVAL = 60 
STATE_FILE = "sent_sms.json"

# تصحيح المسار لـ Railway (تغيير حيوي لحل مشكلة libglib)
BROWSER_PATH = "/tmp/pw-browsers"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = BROWSER_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==========================================
# 2. الوظائف المساعدة
# ==========================================
def load_sent():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f: return set(json.load(f))
    except: pass
    return set()

def save_sent(data):
    try:
        with open(STATE_FILE, "w") as f: json.dump(list(data), f)
    except: pass

def extract_code(text):
    m = re.search(r"\b\d{4,8}\b", text)
    return m.group() if m else "N/A"

# ==========================================
# 3. محرك جلب الرسائل (إصلاح انهيار المتصفح)
# ==========================================
async def fetch_sms():
    async with async_playwright() as p:
        browser = None
        try:
            # إضافة وسيطات قوية لتجنب الانهيار في Railway
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            
            logging.info("🌐 جاري محاولة فتح الصفحة...")
            await page.goto(LOGIN_URL, timeout=90000, wait_until="domcontentloaded")
            
            # معالجة الكابتشا/الحماية بالانتظار
            await asyncio.sleep(7)

            # محاولة تسجيل الدخول
            try:
                await page.wait_for_selector('input[name="email"]', timeout=30000)
                await page.fill('input[name="email"]', IVASMS_EMAIL)
                await page.fill('input[name="password"]', IVASMS_PASSWORD)
                await page.click('button[type="submit"]')
                
                # انتظار نجاح الدخول
                await page.wait_for_selector("text=Logout", timeout=30000)
                logging.info("✅ تم تسجيل الدخول بنجاح!")
            except:
                logging.warning("⚠️ تعذر العثور على حقول الدخول (قد تكون كابتشا منعتنا).")
                await page.screenshot(path="debug_error.png")
                await browser.close()
                return []

            # جلب الرسائل
            await page.goto(SMS_URL, timeout=60000, wait_until="networkidle")
            elements = await page.query_selector_all("div.card-body p")
            
            messages = []
            for el in elements:
                text = await el.inner_text()
                if text.strip():
                    messages.append({
                        "id": str(hash(text)),
                        "text": text.strip(),
                        "code": extract_code(text),
                        "time": datetime.utcnow().strftime("%H:%M:%S")
                    })

            await browser.close()
            return messages

        except Exception as e:
            logging.error(f"⚠️ خطأ أثناء العملية: {e}")
            if browser: await browser.close()
            return []

# ==========================================
# 4. تشغيل البوت
# ==========================================
async def job(app):
    sent = load_sent()
    messages = await fetch_sms()
    if not messages: return

    for msg in messages:
        if msg["id"] in sent: continue
        text = f"🔔 **OTP Received**\n\n🔑 **Code:** `{msg['code']}`\n💬 `{msg['text']}`"
        try:
            await app.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
            sent.add(msg["id"])
            save_sent(sent)
        except Exception as e:
            logging.error(f"❌ خطأ إرسال: {e}")

async def main():
    # التأكد من تحميل المتصفح
    subprocess.run(["python3", "-m", "playwright", "install", "chromium"], check=False)
    
    app = Application.builder().token(BOT_TOKEN).build()
    await app.initialize()
    logging.info("🚀 البوت يعمل الآن ويراقب الرسائل...")

    while True:
        try:
            await job(app)
        except Exception as e:
            logging.error(f"⚠️ خطأ الحلقة: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
