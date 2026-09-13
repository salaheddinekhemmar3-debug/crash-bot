import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8576788403:AAEiiGrDgrrw9caeai20B1R-4WsWvGdXVRk"

dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📍 ولاية خنشلة (Khenchela)", callback_data="khenchela_menu")
        ]
    ])
    
    await message.answer(
        f"أهلاً بك يا {html.quote(message.from_user.first_name)} في دليل مطاعم خنشلة 🍔🍕\n\nاضغط على الزر أدناه لعرض المطاعم والخدمات المتوفرة في الولاية:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "khenchela_menu")
async def khenchela_restaurants(callback: CallbackQuery) -> None:
    restaurants_text = (
        "🍔 **قائمة المطاعم والوجبات السريعة في خنشلة:**\n\n"
        "1. **مطعم الشاطئ (El Chott)** - وجبات سريعة ومشويات.\n"
        "2. **بيتزا الحوت (Pizza Al Hout)** - بيتزا عصرية وخفيفة.\n"
        "3. **سناكس البشير** - تكسوس وتطبيقات توصيل سريعة.\n\n"
        "📞 للتسجيل أو إضافة مطعمك معنا، تواصل معنا!"
    )
    
    await callback.message.edit_text(
        text=restaurants_text,
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
