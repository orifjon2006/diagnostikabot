from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import select, func, and_, update

# Mahalliy modullarni import qilish
from database import (
    AsyncSessionLocal, Operator, PhoneNumber, Booking, 
    get_number_for_operator, check_booking_conflict, 
    get_distribution_status
)
import keyboards as kb
import config

# Routerni e'lon qilish
user_router = Router()

# ==========================================
# 🧠 FSM (HOLATLAR MASHINASI)
# ==========================================
class RegState(StatesGroup):
    name = State()   # Operator ismini kutish
    phone = State()  # Operator telefon raqamini kutish

class CallState(StatesGroup):
    current_number = State()  # Operator ishlayotgan joriy raqam
    client_name = State()     # Mijoz ismini tasdiqlash
    problem = State()         # Mijoz muammosi
    booking_date = State()    # Kelish sanasi
    booking_time = State()    # Kelish vaqti

# ==========================================
# 🎛 TUGMALAR (DINAMIK VA QULAY)
# ==========================================
def contact_kb() -> ReplyKeyboardMarkup:
    """Telefon raqamni yuborish uchun tayyor tugma"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def dynamic_date_kb() -> ReplyKeyboardMarkup:
    """Bugun, Ertaga va Indinga uchun dinamik sana tugmalari"""
    bugun = datetime.now()
    ertaga = bugun + timedelta(days=1)
    indinga = bugun + timedelta(days=2)
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=bugun.strftime("%d-%m-%Y"))],
            [KeyboardButton(text=ertaga.strftime("%d-%m-%Y"))],
            [KeyboardButton(text=indinga.strftime("%d-%m-%Y"))],
            [KeyboardButton(text="🔙 Bekor qilish")]
        ],
        resize_keyboard=True
    )

def time_kb() -> ReplyKeyboardMarkup:
    """Asosiy ish soatlari uchun tayyor vaqt tugmalari"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="10:00"), KeyboardButton(text="11:00"), KeyboardButton(text="12:00")],
            [KeyboardButton(text="14:00"), KeyboardButton(text="15:00"), KeyboardButton(text="16:00")],
            [KeyboardButton(text="17:00"), KeyboardButton(text="18:00"), KeyboardButton(text="🔙 Bekor qilish")]
        ],
        resize_keyboard=True
    )

# ==========================================
# 🚀 START VA REGISTRATSIYA TIZIMI
# ==========================================
@user_router.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    """Botni ishga tushirish va foydalanuvchi statusini aniqlash"""
    await state.clear()
    
    # 👑 1. ADMIN TEKSHIRUVI
    if message.from_user.id in config.ADMIN_IDS:
        # Adminning klaviaturasi admin.py da dinamik shakllanadi, bu yerda shunchaki panelga o'tkazamiz
        from admin import get_admin_kb
        kb_admin = await get_admin_kb()
        return await message.answer(
            "👑 <b>Admin panelga xush kelibsiz!</b>\n\nQuyidagi menyudan kerakli bo'limni tanlang:", 
            reply_markup=kb_admin, 
            parse_mode="HTML"
        )

    # 👤 2. OPERATOR TEKSHIRUVI
    async with AsyncSessionLocal() as session:
        operator = await session.get(Operator, message.from_user.id)
        
        if operator:
            if operator.is_banned:
                return await message.answer("🚫 <b>Sizning akkauntingiz bloklangan.</b>\nIltimos, admin bilan bog'laning.", parse_mode="HTML")
            
            if not operator.is_approved:
                return await message.answer("⏳ <b>Arizangiz ko'rib chiqilmoqda.</b>\nIltimos, adminlar tasdiqlashini kuting.", parse_mode="HTML")
            
            await message.answer(
                "👋 <b>Operator paneliga xush kelibsiz!</b>\nIshni boshlashingiz mumkin.", 
                reply_markup=kb.main_operator_kb(), 
                parse_mode="HTML"
            )
        else:
            # 📝 3. YANGI FOYDALANUVCHI (Registratsiya)
            await message.answer(
                "📝 <b>Ro'yxatdan o'tish</b>\n\nIsm va familiyangizni kiriting:", 
                reply_markup=ReplyKeyboardRemove(), 
                parse_mode="HTML"
            )
            await state.set_state(RegState.name)

@user_router.message(RegState.name)
async def process_reg_name(message: types.Message, state: FSMContext):
    """Operator ismini qabul qilish"""
    await state.update_data(name=message.text)
    await message.answer(
        "📞 Telefon raqamingizni pastdagi tugma orqali yuboring yoki qo'lda kiriting:", 
        reply_markup=contact_kb()
    )
    await state.set_state(RegState.phone)

@user_router.message(RegState.phone)
async def process_reg_phone(message: types.Message, state: FSMContext):
    """Operator telefon raqamini qabul qilish va bazaga yozish"""
    phone_number = message.contact.phone_number if message.contact else message.text
    user_data = await state.get_data()
    
    async with AsyncSessionLocal() as session:
        new_operator = Operator(
            tg_id=message.from_user.id, 
            name=user_data['name'], 
            phone=phone_number, 
            is_approved=False,
            is_banned=False
        )
        session.add(new_operator)
        await session.commit()
        
    await message.answer(
        "✅ <b>Arizangiz adminga muvaffaqiyatli yuborildi!</b>\nTasdiqlashlarini kuting.", 
        reply_markup=ReplyKeyboardRemove(), 
        parse_mode="HTML"
    )
    await state.clear()

# ==========================================
# 📞 NOMER OLISH VA QO'NG'IROQ NATIJALARI
# ==========================================
@user_router.message(F.text == "📥 Nomer olish")
async def get_number_handler(message: types.Message):
    """Operatorga bazadagi eng eski bo'sh raqamni biriktirish"""
    # 0. Admin tekshiruvi
    if message.from_user.id in config.ADMIN_IDS:
        return await message.answer("⚠️ Adminlar mijoz raqamini ola bilmaydi.")

    # 1. TIZIM HOLATINI TEKSHIRAMIZ (Tarqatish yoqilganmi?)
    is_active = await get_distribution_status()
    if not is_active:
        return await message.answer(
            "⏸ <b>Hozirgi vaqtda admin tomonidan raqam tarqatish to'xtatilgan!</b>\n"
            "Iltimos, ruxsat berilishini kuting.", 
            parse_mode="HTML"
        )

    # 2. OPERATOR RUXSATINI TEKSHIRAMIZ
    async with AsyncSessionLocal() as session:
        operator = await session.get(Operator, message.from_user.id)
        if not operator or not operator.is_approved or operator.is_banned:
            return await message.answer("⚠️ Sizga raqam olish huquqi berilmagan.")
            
        # 🆕 YANGI QO'SHILGAN QISM: Agar admin operatorni vaqtincha to'xtatgan bo'lsa
        if operator.is_paused:
            return await message.answer(
                "⏸ <b>Sizga raqam tarqatish admin tomonidan vaqtincha to'xtatib qo'yilgan!</b>\n"
                "Iltimos, ruxsat berilishini kuting.", 
                parse_mode="HTML"
            )
            
    # 3. BAZADAN YANGI MIJOZNI OLAMIZ
    client_data = await get_number_for_operator(message.from_user.id)
    
    if client_data:
        text = (
            f"🎯 <b>YANGI MIJOZ QABUL QILINDI!</b>\n\n"
            f"👤 <b>Ism:</b> {client_data.client_name}\n"
            f"📍 <b>Hudud:</b> {client_data.location}\n"
            f"📞 <b>Raqam:</b> <code>+{client_data.number}</code>\n\n"
            f"<i>Mijoz bilan bog'langach, natijani quyidagi tugmalar orqali belgilang:</i>"
        )
        await message.answer(text, reply_markup=kb.call_result_kb(client_data.number), parse_mode="HTML")
    else:
        await message.answer("📭 Hozircha bazada bo'sh raqamlar yo'q. Iltimos, birozdan so'ng yana urinib ko'ring.")

@user_router.callback_query(F.data.regexp(r"^res_(no|in|wr)_(.+)$"))
async def call_failed_results(callback: types.CallbackQuery):
    """Aloqa muvaffaqiyatsiz bo'lgan holatlarni bazaga yozish"""
    action = callback.data.split("_")[1]
    phone_number = callback.data.split("_")[2]
    
    status_mapping = {
        "no": "no_answer",     # Telefonni ko'tarmadi
        "in": "inactive",      # Raqam faol emas yoki o'chirilgan
        "wr": "wrong_number"   # Noto'g'ri raqam
    }
    new_status = status_mapping.get(action, "assigned")
    
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(PhoneNumber)
            .where(PhoneNumber.number == phone_number)
            .values(status=new_status, updated_at=datetime.utcnow())
        )
        await session.commit()
        
    await callback.message.edit_text(
        f"📝 Raqam: <code>+{phone_number}</code>\nHolat belgilandi: <b>{new_status.upper()}</b>", 
        parse_mode="HTML"
    )
    await callback.answer("Holat saqlandi", show_alert=False)

# ==========================================
# 📝 BRON QILISH JARAYONI (MUVAFFAQIYATLI ALOQA)
# ==========================================
@user_router.message(F.text == "🔙 Bekor qilish")
async def cancel_booking_process(message: types.Message, state: FSMContext):
    """Bron qilish jarayonini to'xtatish va bekor qilish"""
    current_state = await state.get_state()
    if current_state is None:
        return
        
    await state.clear()
    await message.answer("🚫 Bron qilish jarayoni bekor qilindi.", reply_markup=kb.main_operator_kb())

@user_router.callback_query(F.data.startswith("res_ok_"))
async def call_success_handler(callback: types.CallbackQuery, state: FSMContext):
    """Aloqa muvaffaqiyatli bo'lsa, mijoz ismini so'rashni boshlash"""
    phone_number = callback.data.split("_")[2]
    
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(PhoneNumber)
            .where(PhoneNumber.number == phone_number)
            .values(status="contacted", updated_at=datetime.utcnow())
        )
        await session.commit()
        
    await state.update_data(current_number=phone_number)
    
    await callback.message.delete()
    await callback.message.answer(
        f"✅ Raqam: <code>+{phone_number}</code>\n\n👤 <b>Mijozning ismini tasdiqlang yoki aniq qilib kiriting:</b>", 
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Bekor qilish")]], resize_keyboard=True),
        parse_mode="HTML"
    )
    await state.set_state(CallState.client_name)

@user_router.message(CallState.client_name)
async def ask_client_problem(message: types.Message, state: FSMContext):
    """Mijoz ismini saqlab, muammosini so'rash"""
    await state.update_data(client_name=message.text)
    await message.answer("📝 <b>Muammosi nimada?</b> (Qisqacha ta'riflang):", parse_mode="HTML")
    await state.set_state(CallState.problem)

@user_router.message(CallState.problem)
async def ask_booking_date(message: types.Message, state: FSMContext):
    """Mijoz muammosini saqlab, kelish sanasini so'rash"""
    await state.update_data(problem=message.text)
    await message.answer(
        "📅 <b>Qaysi kunga keladi?</b>\nPastdagi tayyor sanalardan birini tanlang yoki DD-MM-YYYY formatida kiriting:", 
        reply_markup=dynamic_date_kb(), 
        parse_mode="HTML"
    )
    await state.set_state(CallState.booking_date)

@user_router.message(CallState.booking_date)
async def ask_booking_time(message: types.Message, state: FSMContext):
    """Kelish sanasini saqlab, vaqtni so'rash"""
    await state.update_data(booking_date=message.text)
    await message.answer(
        "⏰ <b>Soat nechaga?</b>\nTayyor vaqtlardan birini tanlang yoki HH:MM formatida kiriting:", 
        reply_markup=time_kb(), 
        parse_mode="HTML"
    )
    await state.set_state(CallState.booking_time)

@user_router.message(CallState.booking_time)
async def finalize_client_booking(message: types.Message, state: FSMContext):
    """Barcha ma'lumotlarni tekshirib, bronni ma'lumotlar bazasiga saqlash"""
    user_data = await state.get_data()
    date_str = user_data.get('booking_date')
    time_str = message.text
    
    try:
        booking_datetime = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M")
        
        # O'tib ketgan vaqtni tekshirish
        if booking_datetime < datetime.now():
            return await message.answer(
                "⚠️ <b>Xatolik:</b> O'tib ketgan vaqtni kiritish mumkin emas.\nIltimos, kelajakdagi vaqtni tanlang:", 
                reply_markup=time_kb(), 
                parse_mode="HTML"
            )
            
        # Konfliktni tekshirish
        is_conflict = await check_booking_conflict(booking_datetime)
        if is_conflict:
            return await message.answer(
                "⚠️ <b>Band vaqt!</b> Boshqa operator bu vaqtga yoki unga juda yaqin oraliqqa mijoz yozgan.\n"
                "Iltimos, boshqa vaqt tanlang:", 
                reply_markup=time_kb(), 
                parse_mode="HTML"
            )
        
        async with AsyncSessionLocal() as session:
            new_booking = Booking(
                operator_id=message.from_user.id,
                client_name=user_data['client_name'],
                problem=user_data['problem'],
                booking_time=booking_datetime
            )
            session.add(new_booking)
            
            await session.execute(
                update(PhoneNumber)
                .where(PhoneNumber.number == user_data['current_number'])
                .values(status="booked", updated_at=datetime.utcnow())
            )
            await session.commit()
            
        success_text = (
            f"🎉 <b>Muvaffaqiyatli bron qilindi!</b>\n\n"
            f"👤 Mijoz: <b>{user_data['client_name']}</b>\n"
            f"⏰ Vaqt: <b>{booking_datetime.strftime('%d-%m-%Y %H:%M')}</b>"
        )
        await message.answer(success_text, reply_markup=kb.main_operator_kb(), parse_mode="HTML")
        await state.clear()
        
    except ValueError:
        await message.answer(
            "❌ <b>Format noto'g'ri!</b>\nIltimos, tugmalardan foydalaning yoki vaqtni to'g'ri formatda kiriting (Masalan: 14:30).", 
            parse_mode="HTML"
        )

# ==========================================
# 📊 OPERATORNING SHAXSIY STATISTIKASI
# ==========================================
@user_router.message(F.text == "📊 Mening statistikam")
async def show_operator_statistics(message: types.Message):
    """Operatorning o'ziga tegishli umumiy statistikasini ko'rsatish"""
    operator_id = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        total_received = await session.scalar(
            select(func.count(PhoneNumber.id)).where(PhoneNumber.operator_id == operator_id)
        )
        
        total_contacted = await session.scalar(
            select(func.count(PhoneNumber.id))
            .where(and_(PhoneNumber.operator_id == operator_id, PhoneNumber.status.in_(["contacted", "booked"])))
        )
        
        total_bookings = await session.scalar(
            select(func.count(Booking.id)).where(Booking.operator_id == operator_id)
        )
        
    stats_text = (
        "📊 <b>SIZNING KO'RSATKICHLARINGIZ</b>\n\n"
        f"📥 Olingan umumiy raqamlar: <b>{total_received or 0} ta</b>\n"
        f"✅ Aloqaga chiqilgan raqamlar: <b>{total_contacted or 0} ta</b>\n"
        f"🎯 Muvaffaqiyatli bronlar: <b>{total_bookings or 0} ta</b>\n\n"
        f"<i>Izoh: Ushbu statistika sizning botdagi butun faoliyatingizni aks ettiradi.</i>"
    )
    
    await message.answer(stats_text, parse_mode="HTML")
