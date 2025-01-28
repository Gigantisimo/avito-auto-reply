from http.server import BaseHTTPRequestHandler
from bot import AvitoBot
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import json
import os

class handler(BaseHTTPRequestHandler):
    async def handle_webhook(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            bot = AvitoBot()
            app = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()
            
            # Регистрируем обработчики
            app.add_handler(CommandHandler('start', bot.start))
            app.add_handler(CallbackQueryHandler(bot.button_handler))
            
            # Обрабатываем update
            update = Update.de_json(json.loads(post_data), app.bot)
            await app.process_update(update)
            
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