from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_operator_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📥 Nomer olish")], [KeyboardButton(text="📊 Mening statistikam")]],
        resize_keyboard=True
    )

def admin_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Umumiy statistika"), KeyboardButton(text="📥 Excel hisobot")],
            [KeyboardButton(text="👥 Operatorlar"), KeyboardButton(text="🔐 Tasdiqlash kutayotganlar")]
        ],
        resize_keyboard=True
    )

def call_result_kb(number: str):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Aloqaga chiqildi", callback_data=f"res_ok_{number}"))
    builder.row(
        InlineKeyboardButton(text="❌ Tel ko‘tarmadi", callback_data=f"res_no_{number}"),
        InlineKeyboardButton(text="⚠ Aktiv emas", callback_data=f"res_in_{number}")
    )
    builder.row(InlineKeyboardButton(text="🚫 Noto‘g‘ri raqam", callback_data=f"res_wr_{number}"))
    return builder.as_markup()