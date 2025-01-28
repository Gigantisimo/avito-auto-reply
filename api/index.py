from http.server import BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import json
import os
from bot import bot  # Импортируем экземпляр бота из bot.py

class handler(BaseHTTPRequestHandler):
    async def handle_webhook(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            update_data = json.loads(post_data)
            
            # Создаем объект Update из данных
            telegram_update = Update.de_json(update_data, None)
            
            # Создаем приложение
            application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()
            
            # Регистрируем обработчики
            application.add_handler(CommandHandler('start', bot.start))
            application.add_handler(CallbackQueryHandler(bot.button_handler))
            
            # Обрабатываем update
            await application.process_update(telegram_update)
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write('OK'.encode())
            
        except Exception as e:
            print(f"Error processing update: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def do_POST(self):
        import asyncio
        asyncio.run(self.handle_webhook()) 