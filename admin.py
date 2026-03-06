import os
from datetime import datetime
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, and_

# Mahalliy modullarni import qilish
from database import AsyncSessionLocal, Operator, PhoneNumber, Booking, get_distribution_status, toggle_distribution_status
import config
from utils import export_to_excel

# Routerni e'lon qilish
admin_router = Router()

# ==========================================
# 🎛 ASOSIY ADMIN PANEL VA HIMOYA (FILTER)
# ==========================================
# Faqat config.py dagi ADMIN_IDS ro'yxatida bor foydalanuvchilar bu routerga kira oladi
admin_router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))
admin_router.callback_query.filter(F.from_user.id.in_(config.ADMIN_IDS))

# 🆕 DINAMIK ADMIN TUGMALARI (Tarqatish holatiga qarab o'zgaradi)
async def get_admin_kb():
    is_active = await get_distribution_status()
    dist_btn_text = "⏸ Tarqatishni to'xtatish" if is_active else "▶️ Tarqatishni boshlash"
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=dist_btn_text)], # Dinamik tugma
            [KeyboardButton(text="📊 Umumiy statistika"), KeyboardButton(text="📥 Excel hisobot")],
            [KeyboardButton(text="👥 Operatorlar ro'yxati"), KeyboardButton(text="🔐 Tasdiqlash kutayotganlar")]
        ],
        resize_keyboard=True
    )

@admin_router.message(Command("admin"))
async def admin_start(message: types.Message):
    """Admin panelni ishga tushirish va asosiy menyuni chiqarish"""
    kb = await get_admin_kb()
    await message.answer(
        "👑 <b>Admin panelga xush kelibsiz!</b>\n\nQuyidagi menyudan kerakli bo'limni tanlang:", 
        reply_markup=kb, 
        parse_mode="HTML"
    )

# ==========================================
# 🚦 UMUMIY RAQAM TARQATISHNI BOSHQARISH
# ==========================================
@admin_router.message(F.text.in_(["▶️ Tarqatishni boshlash", "⏸ Tarqatishni to'xtatish"]))
async def toggle_dist_handler(message: types.Message):
    """Admin tomonidan umumiy raqam tarqatish tizimini yoqish yoki o'chirish"""
    new_status = await toggle_distribution_status()
    kb = await get_admin_kb() # Klaviatura holatga qarab yangilanadi
    
    if new_status:
        await message.answer(
            "✅ <b>Umumiy raqam tarqatish boshlandi!</b>\nEndi operatorlar mijoz raqamlarini olishi mumkin.", 
            reply_markup=kb, 
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "⏸ <b>Umumiy raqam tarqatish to'xtatildi!</b>\nOperatorlar vaqtincha yangi raqam ola bilmaydi.", 
            reply_markup=kb, 
            parse_mode="HTML"
        )

# ==========================================
# 🔐 OPERATORLARNI TASDIQLASH TIZIMI
# ==========================================
@admin_router.message(F.text == "🔐 Tasdiqlash kutayotganlar")
async def pending_operators(message: types.Message):
    """Tasdiqlanmagan arizalarni bazadan olib, adminlarga ko'rsatish"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Operator).where(Operator.is_approved == False))
        operators = result.scalars().all()
        
        if not operators:
            return await message.answer("✅ Hozirgi vaqtda tasdiqlash kutayotgan arizalar yo'q.")
            
        for op in operators:
            builder = InlineKeyboardBuilder()
            builder.button(text="✅ Tasdiqlash", callback_data=f"approve_{op.tg_id}")
            builder.button(text="❌ Rad etish", callback_data=f"reject_{op.tg_id}")
            builder.adjust(2)
            
            text = (
                f"📝 <b>Yangi ariza:</b>\n\n"
                f"👤 <b>Ism:</b> {op.name}\n"
                f"📞 <b>Telefon:</b> {op.phone}\n"
                f"🆔 <b>Telegram ID:</b> <code>{op.tg_id}</code>"
            )
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@admin_router.callback_query(F.data.startswith("approve_"))
async def process_approve(callback: types.CallbackQuery):
    """Operatorni tasdiqlash va unga xabar yuborish"""
    op_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        operator = await session.get(Operator, op_id)
        if operator:
            operator.is_approved = True
            await session.commit()
            await callback.message.edit_text(f"✅ Operator <b>{operator.name}</b> tasdiqlandi!", parse_mode="HTML")
            
            # Operatorga xabar yuborish
            try:
                await callback.bot.send_message(
                    op_id, 
                    "🎉 <b>Tabriklaymiz!</b>\nArizangiz admin tomonidan tasdiqlandi. \n/start ni bosib ishni boshlashingiz mumkin.",
                    parse_mode="HTML"
                )
            except Exception:
                pass 
                
    await callback.answer()

@admin_router.callback_query(F.data.startswith("reject_"))
async def process_reject(callback: types.CallbackQuery):
    """Operator arizasini rad etish va bazadan o'chirish"""
    op_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        operator = await session.get(Operator, op_id)
        if operator:
            await session.delete(operator)
            await session.commit()
            await callback.message.edit_text(f"❌ Operator <b>{operator.name}</b> arizasi rad etildi va o'chirildi.", parse_mode="HTML")
            
            try:
                await callback.bot.send_message(op_id, "❌ Uzr, arizangiz adminlar tomonidan rad etildi.")
            except Exception:
                pass
                
    await callback.answer()

# ==========================================
# 👥 OPERATORLAR RO'YXATI VA SHAXSIY CHEKLOVLAR
# ==========================================
@admin_router.message(F.text == "👥 Operatorlar ro'yxati")
async def operators_list(message: types.Message):
    """Barcha tasdiqlangan operatorlarni chiqarish va boshqarish"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Operator).where(Operator.is_approved == True))
        operators = result.scalars().all()
        
        if not operators:
            return await message.answer("Bazada tasdiqlangan operatorlar yo'q.")
            
        for op in operators:
            # 1. Operator holatini aniqlaymiz
            if op.is_banned:
                status = "🔴 BAN qilingan"
            elif op.is_paused:
                status = "⏸ Tarqatish to'xtatilgan"
            else:
                status = "🟢 Faol"
            
            builder = InlineKeyboardBuilder()
            
            # 2. Ban / Unban tugmalari
            if op.is_banned:
                builder.button(text="🔓 Bandan olish", callback_data=f"unban_{op.tg_id}")
            else:
                builder.button(text="🚫 Ban qilish", callback_data=f"ban_{op.tg_id}")
                
                # 3. Shaxsiy Tarqatishni yoqish / o'chirish tugmalari (faqat ban bo'lmaganlarga chiqadi)
                if getattr(op, 'is_paused', False):
                    builder.button(text="▶️ Raqam berishni yoqish", callback_data=f"playop_{op.tg_id}")
                else:
                    builder.button(text="⏸ Raqam berishni to'xtatish", callback_data=f"pauseop_{op.tg_id}")
            
            builder.adjust(1) # Tugmalarni ustma-ust teramiz
                
            text = (
                f"👤 <b>{op.name}</b>\n"
                f"📊 Status: {status}\n"
                f"📞 {op.phone} | 🆔 <code>{op.tg_id}</code>"
            )
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- BAN LOGIKASI ---
@admin_router.callback_query(F.data.startswith("ban_"))
async def process_ban(callback: types.CallbackQuery):
    op_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        operator = await session.get(Operator, op_id)
        if operator:
            operator.is_banned = True
            await session.commit()
            await callback.message.edit_text(f"🚫 <b>{operator.name}</b> tizimdan ban qilindi!", parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("unban_"))
async def process_unban(callback: types.CallbackQuery):
    op_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        operator = await session.get(Operator, op_id)
        if operator:
            operator.is_banned = False
            await session.commit()
            await callback.message.edit_text(f"🔓 <b>{operator.name}</b> bandan olindi!", parse_mode="HTML")
    await callback.answer()

# --- SHAXSIY TARQATISHNI TO'XTATISH/YOQISH LOGIKASI ---
@admin_router.callback_query(F.data.startswith("pauseop_"))
async def process_pause_op(callback: types.CallbackQuery):
    op_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        operator = await session.get(Operator, op_id)
        if operator:
            operator.is_paused = True
            await session.commit()
            await callback.message.edit_text(f"⏸ <b>{operator.name}</b> uchun raqam berish vaqtincha to'xtatildi!", parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("playop_"))
async def process_play_op(callback: types.CallbackQuery):
    op_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        operator = await session.get(Operator, op_id)
        if operator:
            operator.is_paused = False
            await session.commit()
            await callback.message.edit_text(f"▶️ <b>{operator.name}</b> uchun raqam berish qayta yoqildi!", parse_mode="HTML")
    await callback.answer()

# ==========================================
# 📊 STATISTIKA TIZIMI
# ==========================================
@admin_router.message(F.text == "📊 Umumiy statistika")
async def show_statistics(message: types.Message):
    """Admin uchun bugungi raqamlar bo'yicha hisobot"""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    async with AsyncSessionLocal() as session:
        total_nums = await session.scalar(select(func.count(PhoneNumber.id)))
        today_nums = await session.scalar(select(func.count(PhoneNumber.id)).where(PhoneNumber.created_at >= today_start))
        today_assigned = await session.scalar(
            select(func.count(PhoneNumber.id))
            .where(and_(PhoneNumber.created_at >= today_start, PhoneNumber.status != "new"))
        )
        today_bookings = await session.scalar(select(func.count(Booking.id)).where(Booking.created_at >= today_start))
        
        text = (
            f"📈 <b>BOT STATISTIKASI</b>\n\n"
            f"📥 <b>Umumiy bazadagi raqamlar:</b> {total_nums or 0} ta\n\n"
            f"📅 <b>Bugungi statistika:</b>\n"
            f" ├ Yangi kelgan raqamlar: {today_nums or 0} ta\n"
            f" ├ Operatorlar olgan raqamlar: {today_assigned or 0} ta\n"
            f" └ Muvaffaqiyatli qilingan bronlar: {today_bookings or 0} ta\n"
        )
        
        await message.answer(text, parse_mode="HTML")

# ==========================================
# 📥 EXCEL EXPORT TIZIMI
# ==========================================
@admin_router.message(F.text == "📥 Excel hisobot")
async def generate_excel_menu(message: types.Message):
    """Qaysi davr uchun Excel kerakligini so'rash tugmalari"""
    builder = InlineKeyboardBuilder()
    builder.button(text="Kunlik", callback_data="excel_daily")
    builder.button(text="Haftalik", callback_data="excel_weekly")
    builder.button(text="Oylik", callback_data="excel_monthly")
    builder.adjust(3)
    
    await message.answer("📊 Qaysi davr uchun hisobotni yuklab olmoqchisiz?", reply_markup=builder.as_markup())

@admin_router.callback_query(F.data.startswith("excel_"))
async def process_excel_export(callback: types.CallbackQuery):
    """utils.py orqali Excel faylni shakllantirish va adminga yuborish"""
    period = callback.data.split("_")[1]
    
    await callback.message.edit_text("⏳ Excel fayl shakllantirilmoqda, biroz kuting...")
    
    try:
        # Excel faylni utils.py dan olamiz
        file_path = await export_to_excel(period) 
        
        if file_path and os.path.exists(file_path):
            excel_doc = FSInputFile(file_path)
            await callback.message.answer_document(
                document=excel_doc,
                caption=f"📁 {period.capitalize()} Excel hisoboti tayyor!"
            )
            # Serverda joyni tejash uchun yuborib bo'lgach o'chiramiz
            os.remove(file_path) 
            await callback.message.delete()
        else:
            await callback.message.edit_text("❌ Fayl shakllantirishda xatolik yuz berdi yoki ushbu davr uchun ma'lumot yo'q.")
    except Exception as e:
        await callback.message.edit_text(f"⚠️ Xatolik yuz berdi: {str(e)}")
        
    await callback.answer()
