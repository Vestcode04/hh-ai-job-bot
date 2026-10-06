from dotenv import load_dotenv
from os import getenv
import asyncio
import logging
from aiogram import Bot, Dispatcher
from handlers import handler_router
from database import initialize_database

logging.basicConfig(level=logging.INFO)
load_dotenv()
open_api= getenv("OPEN_API")
bot = Bot(token=getenv("TG_API"))
dispatcher = Dispatcher()

async def main():
    await initialize_database()
    await bot.delete_webhook(drop_pending_updates=True)
    dispatcher.include_router(handler_router)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
