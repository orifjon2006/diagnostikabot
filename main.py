import asyncio
import re
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Mahalliy modullarni import qilish
import config
from database import init_db, add_phone_number
from admin import admin_router
from user import user_router

# Loglarni terminalda chiroyli ko'rsatish uchun
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Bot va Dispatcher obyektlarini yaratish
bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Routerlarni (admin va user) asosiy dispatcherga ulash
dp.include_router(admin_router)
dp.include_router(user_router)

# ==========================================
# 📥 GURUHDAN XABARLARNI USHLASH (PARSING)
# ==========================================
@dp.message(F.chat.id == config.GROUP_ID)
async def group_message_handler(message: types.Message):
    """
    Guruhga tushgan anketani o'qib, Ism, Manzil va Raqamni bazaga saqlash.
    """
    text = message.text
    if not text:
        return

    try:
        # 1. Manzilni ajratib olish (Kuchaytirilgan Regex: pastdagi yoki yondagi matnni ham taniydi)
        location_match = re.search(r"istiqomat qilasiz[:\?\s]*\n*(.+)", text, re.IGNORECASE)
        location = location_match.group(1).strip() if location_match else "Noma'lum hudud"

        # 2. Ismni ajratib olish
        name_match = re.search(r"Ismingiz[:\s]*\n*(.+)", text, re.IGNORECASE)
        client_name = name_match.group(1).strip() if name_match else "Noma'lum mijoz"

        # 3. Telefon raqamni ushlash (O'zbekiston standarti)
        phone_pattern = r"(?:\+?998)?\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}|\b\d{9}\b"
        numbers = re.findall(phone_pattern, text)

        for num in numbers:
            # Raqam ichidagi faqat sonlarni olamiz
            clean_number = "".join(filter(str.isdigit, num))
            
            # Agar raqam 9 xonali bo'lsa (masalan 998890520), boshiga 998 qo'shamiz
            if len(clean_number) == 9:
                clean_number = "998" + clean_number
                
            # Agar to'g'ri o'zbek raqami shakllangan bo'lsa, bazaga yozamiz
            if len(clean_number) >= 12:
                await add_phone_number(
                    number=clean_number, 
                    client_name=client_name, 
                    location=location
                )
                # Terminalda aniq ko'rinishi uchun tasdiq xabari
                logging.info(f"✅ YANGI RAQAM BAZAGA YOZILDI: Ism: {client_name} | Raqam: {clean_number} | Manzil: {location}")
                
    except Exception as e:
        logging.error(f"❌ Guruh xabarini parchalashda xatolik yuz berdi: {e}")

# ==========================================
# 🚀 BOTNI ISHGA TUSHIRISH
# ==========================================
async def main():
    # Baza jadvallarini yaratish/ulanish
    await init_db()
    logging.info("Ma'lumotlar bazasiga muvaffaqiyatli ulandi.")
    
    # Botni yangi xabarlarni eshitish rejimida ishga tushirish
    logging.info("Bot ishga tushdi va guruhdagi xabarlarni kutmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        # Asinxron loopni ishga tushirish
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot o'chirildi.")
