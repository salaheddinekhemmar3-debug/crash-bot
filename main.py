import os
import re
import time
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass

import numpy as np
import aiosqlite

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import BaseMiddleware

BOT_TOKEN = "8982678751:AAHIAHoQqsCDGt8Qqw3H5gdUcSEmA8Zth_0"
DATABASE_PATH = "crash_data.db"
RATE_LIMIT_PER_SEC = 1.5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("CrashAnalyticsBot")

@dataclass
class CrashRound:
    id: Optional[int]
    user_id: int
    multiplier: float
    created_at: datetime

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS rounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    multiplier REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_user_rounds ON rounds(user_id, id DESC);")
            await db.commit()

    async def insert_rounds(self, user_id: int, multipliers: List[float]) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            data = [(user_id, m, datetime.utcnow()) for m in multipliers]
            cursor = await db.executemany(
                "INSERT INTO rounds (user_id, multiplier, created_at) VALUES (?, ?, ?)",
                data
            )
            await db.commit()
            return cursor.rowcount

    async def get_user_rounds(self, user_id: int, limit: int = 500) -> List[CrashRound]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, user_id, multiplier, created_at FROM rounds WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    CrashRound(
                        id=row["id"],
                        user_id=row["user_id"],
                        multiplier=row["multiplier"],
                        created_at=datetime.fromisoformat(row["created_at"]) if isinstance(row["created_at"], str) else row["created_at"]
                    ) for row in rows
                ]

    async def reset_user_data(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM rounds WHERE user_id = ?", (user_id,))
            await db.commit()
            return cursor.rowcount

db_manager = DatabaseManager(DATABASE_PATH)

def analyze_multipliers(multipliers: List[float]) -> Dict[str, Any]:
    if not multipliers:
        return {}

    arr = np.array(multipliers)
    
    def get_max_streak(threshold: float) -> int:
        under = arr < threshold
        max_s = current = 0
        for val in under:
            if val:
                current += 1
                max_s = max(max_s, current)
            else:
                current = 0
        return max_s

    q25, q75 = np.percentile(arr, [25, 75])

    return {
        "count": len(arr),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std_dev": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "q25": float(q25),
        "q75": float(q75),
        "freq_under_1_2": float(np.sum(arr < 1.20) / len(arr) * 100),
        "freq_under_1_5": float(np.sum(arr < 1.50) / len(arr) * 100),
        "freq_under_2_0": float(np.sum(arr < 2.00) / len(arr) * 100),
        "max_streak_1_2": get_max_streak(1.20),
        "max_streak_1_5": get_max_streak(1.50),
        "max_streak_2_0": get_max_streak(2.00),
    }

def generate_estimation(stats: Dict[str, Any]) -> Dict[str, Any]:
    if not stats or stats.get("count", 0) < 10:
        return {
            "range": "غير كافٍ",
            "confidence": "ضعيفة جداً",
            "note": "تحتاج على الأقل 10 جولات للحصول على تقدير إحصائي مبدئي."
        }

    low_bound = round(stats["q25"], 2)
    high_bound = round(stats["q75"], 2)
    
    sample_factor = min(stats["count"] / 100.0, 1.0)
    volatility = stats["std_dev"] / stats["mean"] if stats["mean"] > 0 else 1.0
    
    if sample_factor > 0.5 and volatility < 1.5:
        confidence = "متوسطة إحصائياً (عينة مقبولة)"
    else:
        confidence = "منخفضة (تقلبات عالية أو عينة صغيرة)"

    return {
        "range": f"{low_bound:.2f}x - {high_bound:.2f}x",
        "confidence": confidence,
        "note": "تنبيه هام: نتائج Crash تعتمد على RNG عشوائي. هذا التقدير يمثل النطاق الوسيط المعتاد تاريخياً ولا يضمن النتيجة القادمة اطلاقاً."
    }

class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit_sec: float = 1.5):
        self.limit = limit_sec
        self.last_time: Dict[int, float] = {}

    async def __call__(self, handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]], event: Message, data: Dict[str, Any]) -> Any:
        user_id = event.from_user.id
        current_time = time.time()
        
        if user_id in self.last_time and (current_time - self.last_time[user_id]) < self.limit:
            await event.answer("⚠️ الرجاء الإبطاء في إرسال الأوامر لتجنب الحظر.")
            return

        self.last_time[user_id] = current_time
        return await handler(event, data)

def get_main_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="📊 تحليل سريع (آخر 20)", callback_data="analyze_20"),
            InlineKeyboardButton(text="📈 تحليل موسع (آخر 100)", callback_data="analyze_100")
        ],
        [
            InlineKeyboardButton(text="🗑️ مسح بياناتي", callback_data="confirm_reset")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

router = Router()

@router.message(CommandStart())
async def start_cmd(message: Message):
    welcome_text = (
        "<b>مرحباً بك في بوت التحليل الإحصائي لـ Crash</b> 📊\n\n"
        "يقوم هذا البوت بتقديم <b>حسابات إحصائية مجردة</b> بناءً على البيانات التي تقوم بإدخالها.\n\n"
        "⚠️ <b>إخلاء مسؤولية:</b>\n"
        "البوت <b>لا يتوقع</b> النتيجة القادمة ولا يضمن أي أرباح، فاللعبة تعتمد على خوارزميات عشوائية (RNG).\n\n"
        "<b>طريقة الإدخال:</b>\n"
        "قم بإرسال النتائج مفصولة بمسافات مباشرة، مثال:\n"
        "<code>1.24 1.87 3.41 1.09 7.52 2.13</code>"
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())

async def format_analysis_response(user_id: int, limit: int) -> str:
    rounds = await db_manager.get_user_rounds(user_id, limit=limit)
    if not rounds:
        return "⚠️ لا توجد بيانات مسجلة. قم بإرسال أرقام الجولات أولاً."

    multipliers = [r.multiplier for r in rounds]
    stats = analyze_multipliers(multipliers)
    estimation = generate_estimation(stats)

    return (
        f"📊 <b>تحليل آخر {stats['count']} جولة:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 <b>الوسيط (Median):</b> <code>{stats['median']:.2f}x</code>\n"
        f"🔹 <b>المتوسط (Mean):</b> <code>{stats['mean']:.2f}x</code>\n"
        f"🔹 <b>الانحراف المعياري:</b> <code>{stats['std_dev']:.2f}</code>\n"
        f"🔹 <b>أدنى / أعلى:</b> <code>{stats['min']:.2f}x / {stats['max']:.2f}x</code>\n\n"
        f"📉 <b>توزيع النتائج المنخفضة:</b>\n"
        f"• تحت 1.20x: <code>{stats['freq_under_1_2']:.1f}%</code> (أطول سلسلة: {stats['max_streak_1_2']})\n"
        f"• تحت 1.50x: <code>{stats['freq_under_1_5']:.1f}%</code> (أطول سلسلة: {stats['max_streak_1_5']})\n"
        f"• تحت 2.00x: <code>{stats['freq_under_2_0']:.1f}%</code> (أطول سلسلة: {stats['max_streak_2_0']})\n\n"
        f"🎲 <b>التقدير الإحصائي للجولة القادمة:</b>\n"
        f"• النطاق المرجح: <code>{estimation['range']}</code>\n"
        f"• درجة الثقة: <b>{estimation['confidence']}</b>\n\n"
        f"⚠️ <i>{estimation['note']}</i>"
    )

@router.message(Command("stats"))
@router.callback_query(F.data.in_({"analyze_20", "analyze_100"}))
async def handle_analysis(event: Message | CallbackQuery):
    user_id = event.from_user.id
    limit = 20 if (isinstance(event, CallbackQuery) and event.data == "analyze_20") else 100
    
    if isinstance(event, CallbackQuery):
        await event.answer()
        text = await format_analysis_response(user_id, limit)
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_keyboard())
    else:
        text = await format_analysis_response(user_id, limit)
        await event.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

@router.message(Command("reset"))
@router.callback_query(F.data == "confirm_reset")
async def handle_reset(event: Message | CallbackQuery):
    user_id = event.from_user.id
    deleted = await db_manager.reset_user_data(user_id)
    msg = f"🗑️ تم مسح <b>{deleted}</b> سجلاً من بياناتك بنجاح."
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(msg, parse_mode="HTML")
    else:
        await event.answer(msg, parse_mode="HTML")

@router.message(F.text & ~F.text.startswith("/"))
async def handle_multipliers_entry(message: Message):
    text = message.text.strip()
    raw_tokens = re.split(r'[\s,\n]+', text)
    valid_multipliers = []
    
    for token in raw_tokens:
        try:
            val = float(token)
            if 1.00 <= val <= 10000.00:
                valid_multipliers.append(round(val, 2))
        except ValueError:
            continue

    if not valid_multipliers:
        await message.answer("❌ لم يتم العثور على أرقام صالحة. أدخل أرقاماً أكبر من أو تساوي 1.00.")
        return

    inserted_count = await db_manager.insert_rounds(message.from_user.id, valid_multipliers)
    await message.answer(
        f"✅ تم تسجيل <b>{inserted_count}</b> جولة بنجاح!\n\n"
        f"القيم المضافة: <code>{valid_multipliers[:10]}{'...' if len(valid_multipliers) > 10 else ''}</code>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

async def main():
    logger.info("Initializing SQLite Database...")
    await db_manager.init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(RateLimitMiddleware(limit_sec=RATE_LIMIT_PER_SEC))
    dp.include_router(router)

    logger.info("Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
