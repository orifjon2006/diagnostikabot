import os
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select
from database import AsyncSessionLocal, PhoneNumber, Operator

async def export_to_excel(period: str) -> str:
    """
    Belgilangan davr (kunlik, haftalik, oylik) bo'yicha bazadagi 
    ma'lumotlarni yig'ib, Excel fayl yaratib beradi.
    """
    now = datetime.now()
 
    if period == "daily":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "monthly":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = datetime.min 

    async with AsyncSessionLocal() as session:
     
        ops_result = await session.execute(select(Operator))
        operators = {op.tg_id: op.name for op in ops_result.scalars().all()}

        stmt = select(PhoneNumber).where(PhoneNumber.created_at >= start_date).order_by(PhoneNumber.created_at.desc())
        phones_res = await session.execute(stmt)
        phones = phones_res.scalars().all()

        # Agar bu davrda hech qanday raqam bo'lmasa, None qaytaramiz (admin panel xato bermasligi uchun)
        if not phones:
            return None

        # 3. Ma'lumotlarni chiroyli formatda ro'yxatga joylaymiz
        data = []
        status_translations = {
            "new": "Yangi",
            "assigned": "Operatorga berildi",
            "contacted": "Aloqaga chiqildi",
            "booked": "Bron qilindi",
            "no_answer": "Ko'tarmadi",
            "inactive": "Aktiv emas",
            "wrong_number": "Noto'g'ri raqam"
        }

        for p in phones:
            operator_name = operators.get(p.operator_id, "Biriktirilmagan")
            translated_status = status_translations.get(p.status, p.status)

            data.append({
                "ID": p.id,
                "Mijoz Ismi": p.client_name or "Noma'lum",
                "Telefon Raqam": f"+{p.number}",
                "Hudud (Manzil)": p.location or "Noma'lum",
                "Holati (Status)": translated_status,
                "Operator": operator_name,
                "Baza kiritilgan vaqt": p.created_at.strftime("%d-%m-%Y %H:%M"),
                "So'nggi o'zgarish": p.updated_at.strftime("%d-%m-%Y %H:%M")
            })

        df = pd.DataFrame(data)
        
        filename = f"Hisobot_{period.capitalize()}_{now.strftime('%Y%m%d_%H%M')}.xlsx"
        
        df.to_excel(filename, index=False, engine='openpyxl')
        
        return filename