import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# ضع هنا توكن البوت الذي أعطاه لك BotFather بين العلامتين ''
TOKEN = "ضع_الـ_Token_هنا"

# دالة رسالة البدء واختيار الولاية
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    # إنشاء الأزرار التفاعلية للولايات
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📍 الجزائر العاصمة", callback_data="state_algiers"),
            InlineKeyboardButton(text="📍 قسنطينة", callback_data="state_constantine")
        ],
        [
            InlineKeyboardButton(text="📍 خنشلة", callback_data="state_khenchela"),
            InlineKeyboardButton(text="📍 وهران", callback_data="state_oran")
        ]
    ])
    
    await message.answer(
        f"أهلاً بك يا {html.quote(message.from_user.first_name)} في دليل المطاعم والوجبات السريعة الجزائري 🍔🍕\n\nيرجى اختيار ولايتك لمعرفة المطاعم المتوفرة:",
        reply_markup=keyboard
    )

async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
