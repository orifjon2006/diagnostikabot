import asyncio
import re
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
from database import init_db, add_phone_number
from admin import admin_router
from user import user_router


logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

dp.include_router(admin_router)
dp.include_router(user_router)

@dp.message(F.chat.id == config.GROUP_ID)
async def group_message_handler(message: types.Message):
    """
    Guruhga tushgan anketani o'qib, Ism, Manzil va Raqamni bazaga saqlash.
    Kutilyotgan format:
    Hozirda qayerda istiqomat qilasiz
    toshkent_shahar
    Ismingiz
    Shahnoza
    raqam
    998890520
    """
    text = message.text
    if not text:
        return

    try:
        
        location_match = re.search(r"istiqomat qilasiz\s*\n+(.+)", text, re.IGNORECASE)
        location = location_match.group(1).strip() if location_match else "Noma'lum hudud"

        # 2. Ismni ajratib olish ("Ismingiz" dan keyingi qatorni ushlaymiz)
        name_match = re.search(r"Ismingiz\s*\n+(.+)", text, re.IGNORECASE)
        client_name = name_match.group(1).strip() if name_match else "Noma'lum mijoz"

        # 3. Telefon raqamni ushlash ("raqam" so'zidan keyingi raqamlarni yoki umumiy formatni ushlash)
        # O'zbekiston raqamlari standarti bo'yicha regex (Bo'shliqlar bilan yoki bo'shliqsiz)
        phone_pattern = r"(?:\+?998)?\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}|\b\d{9}\b"
        numbers = re.findall(phone_pattern, text)

        for num in numbers:
            # Raqam ichidagi faqat sonlarni olamiz (probellar, + belgilarini tozalaymiz)
            clean_number = "".join(filter(str.isdigit, num))
            
            # Agar raqam 9 xonali bo'lsa (masalan 998890520 yoki 901234567), boshiga 998 qo'shamiz
            if len(clean_number) == 9:
                clean_number = "998" + clean_number
                
            # Agar to'g'ri o'zbek raqami (12 xonali) shakllangan bo'lsa, bazaga yozamiz
            if len(clean_number) >= 12:
                await add_phone_number(
                    number=clean_number, 
                    client_name=client_name, 
                    location=location
                )
                
    except Exception as e:
        logging.error(f"Guruh xabarini parchalashda xatolik yuz berdi: {e}")

# ==========================================
# 🚀 BOTNI ISHGA TUSHIRISH
# ==========================================
async def main():
    # Baza jadvallarini yaratish/ulanish
    await init_db()
    logging.info("Ma'lumotlar bazasiga muvaffaqiyatli ulandi.")
    
    # Botni yangi xabarlarni eshitish rejimida ishga tushirish
    logging.info("Bot ishga tushdi va xabarlarni kutmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        # Asinxron loopni ishga tushirish
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot o'chirildi.")