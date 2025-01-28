from bot import AvitoBot
from telegram import Update
from telegram.ext import Application
import json
import os

async def handle_webhook(request):
    try:
        bot = AvitoBot()
        app = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()
        
        # Регистрируем обработчики
        app.add_handler(CommandHandler('start', bot.start))
        app.add_handler(CallbackQueryHandler(bot.button_handler))
        # ... другие обработчики
        
        # Обрабатываем update
        update = Update.de_json(json.loads(request.body), app.bot)
        await app.process_update(update)
        
        return {'statusCode': 200}
    except Exception as e:
        print(f"Error processing update: {e}")
        return {'statusCode': 500} 