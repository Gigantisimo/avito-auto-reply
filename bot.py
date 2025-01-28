from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    ConversationHandler, 
    MessageHandler, 
    filters
)
import aiohttp
import sqlite3
import asyncio
from datetime import datetime
import base64
import os
import re
import io
# from PIL import Image
from dotenv import load_dotenv
import logging
import json
import sys
import firebase_admin
from firebase_admin import credentials, firestore

# В начале файла
load_dotenv()  # Загружаем переменные окружения

# Состояния для разговора
(
    WAITING_CLIENT_ID,
    WAITING_CLIENT_SECRET,
    WAITING_USER_ID,
    WAITING_TEMPLATE,
    WAITING_IMAGE,  # Новое состояние
) = range(5)

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Логируем в stdout вместо файла
)

class AvitoBot:
    def __init__(self):
        # Инициализация Firebase
        if not firebase_admin._apps:
            if os.getenv('FIREBASE_CREDENTIALS'):
                # Декодируем credentials из переменной окружения
                cred_json = base64.b64decode(os.getenv('FIREBASE_CREDENTIALS')).decode('utf-8')
                cred_dict = json.loads(cred_json)
                cred = credentials.Certificate(cred_dict)
            else:
                # Используем локальный файл
                cred = credentials.Certificate('firebase-credentials.json')
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()
        self.temp_credentials = {}

    def get_user(self, user_id: str):
        doc_ref = self.db.collection('users').document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def save_user(self, user_id: str, data: dict):
        doc_ref = self.db.collection('users').document(user_id)
        doc_ref.set(data, merge=True)

    async def manage_accounts_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            user_id = str(update.callback_query.from_user.id)
            message = update.callback_query.message
        else:
            user_id = str(update.message.from_user.id)
            message = update.message

        user_data = self.get_user(user_id)
        accounts = []
        if user_data:
            if user_data.get('client_id'):
                accounts.append(('1', 'Основной аккаунт', True))
            if user_data.get('client_id_2'):
                accounts.append(('2', 'Второй аккаунт', True))

        keyboard = []
        
        # Добавляем кнопки для каждого аккаунта
        for acc_id, name, enabled in accounts:
            status = "✅" if enabled else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{name} {status}",
                callback_data=f'account_{acc_id}'
            )])
        
        # Если есть свободный слот, показываем кнопку добавления
        if len(accounts) < 2:
            keyboard.append([InlineKeyboardButton("➕ Добавить аккаунт", callback_data='add_account')])
        
        keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data='main_menu')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            f"🗂 Управление аккаунтами:\n\n"
            f"Активно: {len(accounts)} из {len(accounts)}\n"
            f"Доступно всего: 2 аккаунта\n"
            f"Осталось слотов: {max(0, 2 - len(accounts))}"
        )
        
        if update.callback_query:
            await message.edit_text(text=message_text, reply_markup=reply_markup)
        else:
            await message.reply_text(text=message_text, reply_markup=reply_markup)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("➕ Добавить Client ID", callback_data='add_client_id')],
            [InlineKeyboardButton("🔑 Добавить Client Secret", callback_data='add_client_secret')],
            [InlineKeyboardButton("👤 Добавить User ID", callback_data='add_user_id')],
            [InlineKeyboardButton("📝 Установить шаблон ответа", callback_data='set_template')],
            [InlineKeyboardButton("🖼 Загрузить изображение", callback_data='upload_image')],
            [InlineKeyboardButton("🔄 Включить/выключить автоответ", callback_data='toggle_auto_reply')],
            [InlineKeyboardButton("💰 Проверить баланс", callback_data='check_balance')],
            [InlineKeyboardButton("👥 Управление аккаунтами", callback_data='manage_accounts')],
            [InlineKeyboardButton("⚙️ Настройки", callback_data='view_settings')],
            [InlineKeyboardButton("📨 Бот для рассылки", url="t.me/avsender_bot")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Добро пожаловать в бота автоответов Авито!\nВыберите действие:",
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)
        user_data = self.get_user(user_id)
        
        if query.data == 'add_client_id':
            await query.message.reply_text("Пожалуйста, введите ваш Client ID:")
            return WAITING_CLIENT_ID
            
        elif query.data == 'add_client_secret':
            if user_id not in self.temp_credentials or 'client_id' not in self.temp_credentials[user_id]:
                await query.message.reply_text("Сначала добавьте Client ID!")
                return ConversationHandler.END
            await query.message.reply_text("Пожалуйста, введите ваш Client Secret:")
            return WAITING_CLIENT_SECRET
            
        elif query.data == 'add_user_id':
            if user_id not in self.temp_credentials or 'client_secret' not in self.temp_credentials[user_id]:
                await query.message.reply_text("Сначала добавьте Client ID и Client Secret!")
                return ConversationHandler.END
            await query.message.reply_text("Пожалуйста, введите ваш User ID:")
            return WAITING_USER_ID
            
        elif query.data == 'set_template':
            if not user_data:
                await query.message.reply_text("❌ Сначала настройте учетные данные!")
                return
            await query.message.reply_text(
                "📝 Отправьте текст шаблона для автоответа.\n"
                "Например: Здравствуйте! Спасибо за ваше сообщение. Я отвечу вам позже."
            )
            return WAITING_TEMPLATE
            
        elif query.data == 'toggle_auto_reply':
            if not user_data:
                await query.message.reply_text("Сначала настройте учетные данные!")
                return
            new_status = not user_data['auto_reply_enabled']
            user_data['auto_reply_enabled'] = new_status
            self.save_user(user_id, user_data)
            await query.message.reply_text(
                f"Автоответ {'включен' if new_status else 'выключен'}"
            )
        elif query.data == 'view_settings':
            if not user_data:
                keyboard = [
                    [InlineKeyboardButton("➕ Добавить Client ID", callback_data='add_client_id')],
                    [InlineKeyboardButton("📨 Бот для рассылки", url="t.me/avsender_bot")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.edit_text(
                    "❌ Настройки не найдены\n"
                    "Необходимо добавить учетные данные.",
                    reply_markup=reply_markup
                )
                return

            settings_text = (
                "⚙️ Текущие настройки:\n\n"
                f"🔑 Client ID: {user_data['client_id'][:10]}...{user_data['client_id'][-5:] if user_data['client_id'] else 'Не установлен'}\n"
                f"🔐 Client Secret: {'Установлен ✅' if user_data['client_secret'] else 'Не установлен ❌'}\n"
                f"👤 User ID: {user_data['avito_user_id'] or 'Не установлен'}\n"
                f"📝 Шаблон: {user_data['template'] or 'Не установлен'}\n"
                f"🔄 Автоответ: {'Включен ✅' if user_data['auto_reply_enabled'] else 'Выключен ❌'}\n\n"
                "Что хотите изменить?"
            )
            
            keyboard = [
                [InlineKeyboardButton("➕ Добавить Client ID", callback_data='add_client_id')],
                [InlineKeyboardButton("🔑 Добавить Client Secret", callback_data='add_client_secret')],
                [InlineKeyboardButton("👤 Добавить User ID", callback_data='add_user_id')],
                [InlineKeyboardButton("📝 Установить шаблон ответа", callback_data='set_template')],
                [InlineKeyboardButton("🔄 Включить/выключить автоответ", callback_data='toggle_auto_reply')],
                [InlineKeyboardButton("📨 Бот для рассылки", url="t.me/avsender_bot")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.edit_text(settings_text, reply_markup=reply_markup)
        elif query.data == 'upload_image':
            if not user_data:
                await query.message.reply_text("❌ Сначала настройте учетные данные!")
                return ConversationHandler.END
            await query.message.reply_text(
                "🖼 Отправьте изображение, которое будет использоваться в автоответах.\n"
                "Поддерживаются форматы: JPEG, PNG"
            )
            return WAITING_IMAGE
        elif query.data == 'check_balance':
            if not user_data:
                await query.message.reply_text("❌ Сначала настройте учетные данные!")
                return
            
            balances = await self.check_balance_and_advance(user_data)
            if balances:
                main_balance = balances['main_balance']
                advance_balance = balances['advance']
                
                message = "💰 Информация о балансах:\n\n"
                
                if main_balance:
                    message += (
                        f"Основной баланс: {main_balance.get('real', 0)} ₽\n"
                        f"Бонусы: {main_balance.get('bonus', 0)} ₽\n"
                    )
                
                if advance_balance is not None:
                    message += f"\nБаланс аванса: {advance_balance:.2f} ₽"
                
                await query.message.reply_text(message)
            else:
                await query.message.reply_text("❌ Не удалось получить информацию о балансах")
        elif query.data == 'manage_accounts':
            await self.manage_accounts_handler(update, context)
        
        elif query.data == 'buy_accounts':
            await self.buy_accounts_menu(update, context)
        
        elif query.data.startswith('buy_') and query.data != 'buy_accounts':  # Добавляем проверку
            try:
                accounts_count = int(query.data.split('_')[1])
                amount = accounts_count * 200  # 200 рублей за аккаунт
                
                payment_service = PaymentService(os.getenv('TOCHKA_JWT_TOKEN'))
                qr_data = await payment_service.create_payment_qr(amount, accounts_count, user_id)
                
                if qr_data:
                    # Создаем QR-код как изображение
                    qr = Image.open(io.BytesIO(base64.b64decode(qr_data['image'])))
                    bio = io.BytesIO()
                    qr.save(bio, 'PNG')
                    bio.seek(0)
                    
                    # Отправляем QR-код и инструкции
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=bio,
                        caption=(
                            f"💳 Оплата {accounts_count} дополнительных аккаунтов\n\n"
                            f"Сумма к оплате: {qr_data['amount']}₽\n\n"
                            "1️⃣ Отсканируйте QR-код через приложение банка\n"
                            "2️⃣ Оплатите точную сумму\n"
                            "3️⃣ Нажмите кнопку проверки после оплаты"
                        ),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("✅ Проверить оплату", 
                                               callback_data=f'check_payment_{qr_data["qrc_id"]}')
                        ]])
                    )
                else:
                    await query.answer("❌ Ошибка создания платежа. Попробуйте позже.")
            except ValueError:
                await query.answer("❌ Неверный формат данных")
            except Exception as e:
                print(f"Error processing payment: {e}")
                await query.answer("❌ Произошла ошибка. Попробуйте позже.")
        elif query.data.startswith('check_payment_'):
            qrc_id = query.data.split('_')[2]
            payment_service = PaymentService(os.getenv('TOCHKA_JWT_TOKEN'))
            status = await payment_service.check_payment_status(qrc_id)
            
            if status == 'SUCCESS':
                if await self.process_successful_payment(user_id, qrc_id):
                    await query.message.edit_caption(
                        caption="✅ Оплата прошла успешно!\n\nДополнительные аккаунты активированы.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Вернуться в меню", callback_data='start')
                        ]])
                    )
                else:
                    await query.answer("❌ Ошибка активации аккаунтов. Обратитесь в поддержку.")
            else:
                await query.answer("⏳ Оплата еще не поступила. Попробуйте через минуту.")

    async def handle_client_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.message.from_user.id)
        client_id = update.message.text.strip()
        
        if user_id not in self.temp_credentials:
            self.temp_credentials[user_id] = {}
        
        self.temp_credentials[user_id]['client_id'] = client_id
        await update.message.reply_text("✅ Client ID сохранен! Теперь добавьте Client Secret.")
        return ConversationHandler.END

    async def handle_client_secret(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.message.from_user.id)
        client_secret = update.message.text.strip()
        
        self.temp_credentials[user_id]['client_secret'] = client_secret
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить Client ID", callback_data='add_client_id')],
            [InlineKeyboardButton("🔑 Добавить Client Secret", callback_data='add_client_secret')],
            [InlineKeyboardButton("👤 Добавить User ID", callback_data='add_user_id')],
            [InlineKeyboardButton("📝 Установить шаблон ответа", callback_data='set_template')],
            [InlineKeyboardButton("🔄 Включить/выключить автоответ", callback_data='toggle_auto_reply')],
            [InlineKeyboardButton("⚙️ Настройки", callback_data='view_settings')],
            [InlineKeyboardButton("📨 Бот для рассылки", url="t.me/avsender_bot")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ Client Secret сохранен! Теперь добавьте User ID.", 
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    async def handle_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.message.from_user.id)
        avito_user_id = update.message.text.strip()
        
        self.temp_credentials[user_id]['avito_user_id'] = avito_user_id
        
        # Сохраняем все данные в БД
        self.save_user(user_id, {
            'client_id': self.temp_credentials[user_id]['client_id'],
            'client_secret': self.temp_credentials[user_id]['client_secret'],
            'avito_user_id': avito_user_id,
            'template': '',
            'auto_reply_enabled': False,
            'auto_reply_start_time': 0,
            'image_file_id': None
        })
        
        # Очищаем временные данные
        del self.temp_credentials[user_id]
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить Client ID", callback_data='add_client_id')],
            [InlineKeyboardButton("🔑 Добавить Client Secret", callback_data='add_client_secret')],
            [InlineKeyboardButton("👤 Добавить User ID", callback_data='add_user_id')],
            [InlineKeyboardButton("📝 Установить шаблон ответа", callback_data='set_template')],
            [InlineKeyboardButton("🔄 Включить/выключить автоответ", callback_data='toggle_auto_reply')],
            [InlineKeyboardButton("⚙️ Настройки", callback_data='view_settings')],
            [InlineKeyboardButton("📨 Бот для рассылки", url="t.me/avsender_bot")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ Все учетные данные успешно сохранены!\n"
            "Теперь вы можете:\n"
            "1. Установить шаблон ответа\n"
            "2. Включить автоответ\n"
            "3. Проверить настройки",
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    async def handle_template(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.message.from_user.id)
        template = update.message.text.strip()
        
        if not template:
            await update.message.reply_text("❌ Шаблон не может быть пустым!")
            return ConversationHandler.END
            
        user_data = self.get_user(user_id)
        if not user_data:
            await update.message.reply_text("❌ Сначала настройте учетные данные!")
            return ConversationHandler.END
            
        user_data['template'] = template
        self.save_user(user_id, user_data)
        
        await update.message.reply_text(
            "✅ Шаблон сообщения успешно сохранен!\n"
            f"Текст шаблона:\n{template}"
        )
        return ConversationHandler.END

    async def get_token(self, client_id: str, client_secret: str) -> str:
        async with aiohttp.ClientSession() as session:
            data = {
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': client_secret
            }
            async with session.post('https://api.avito.ru/token', data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('access_token')
                return None

    def save_replied_chat(self, user_id: str, chat_id: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO replied_chats (user_id, chat_id, replied_at)
            VALUES (?, ?, ?)
        ''', (user_id, chat_id, int(datetime.now().timestamp())))
        conn.commit()
        conn.close()

    def has_replied_to_chat(self, user_id: str, chat_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT 1 FROM replied_chats WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
        result = c.fetchone() is not None
        conn.close()
        return result

    async def check_messages(self, context: ContextTypes.DEFAULT_TYPE):
        users = self.get_active_users()
        for user_data in users:
            token = await self.get_token(user_data['client_id'], user_data['client_secret'])
            if not token:
                print(f"Failed to get token for user {user_data['user_id']}")
                continue

            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {token}'}
                params = {'unread_only': 'true', 'limit': '100'}
                url = f"https://api.avito.ru/messenger/v2/accounts/{user_data['avito_user_id']}/chats"
                
                try:
                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status != 200:
                            print(f"Failed to get chats: {response.status}")
                            continue
                        
                        chats = await response.json()
                        for chat in chats.get('chats', []):
                            chat_id = chat.get('id')
                            if not chat_id:
                                continue

                            if self.has_replied_to_chat(user_data['user_id'], chat_id):
                                print(f"Already replied to chat {chat_id}")
                                continue

                            last_message_time = chat.get('last_message', {}).get('created', 0)
                            if last_message_time < user_data.get('auto_reply_start_time', 0):
                                print(f"Message in chat {chat_id} is too old")
                                continue

                            if not user_data.get('template'):
                                print(f"No template set for user {user_data['user_id']}")
                                continue

                            # Отправляем изображение, если оно есть
                            if user_data.get('image_file_id'):
                                try:
                                    upload_url = f"https://api.avito.ru/messenger/v1/accounts/{user_data['avito_user_id']}/uploadImages"
                                    form_data = aiohttp.FormData()
                                    form_data.add_field('uploadfile[]', 
                                                      user_data['image_file_id'],
                                                      filename='image.jpg',
                                                      content_type='image/jpeg')
                                    
                                    async with session.post(upload_url, headers=headers, data=form_data) as upload_response:
                                        if upload_response.status == 200:
                                            upload_data = await upload_response.json()
                                            image_id = list(upload_data.keys())[0]
                                            
                                            # Отправляем изображение
                                            image_data = {
                                                'image_id': image_id
                                            }
                                            image_url = f"https://api.avito.ru/messenger/v1/accounts/{user_data['avito_user_id']}/chats/{chat_id}/messages/image"
                                            await session.post(image_url, headers=headers, json=image_data)
                                            print(f"Successfully sent image to chat {chat_id}")
                                            await asyncio.sleep(2)
                                except Exception as e:
                                    print(f"Error sending image: {e}")

                            # Отправляем текст
                            message_data = {
                                'message': {'text': user_data['template']},
                                'type': 'text'
                            }
                            
                            msg_url = f"https://api.avito.ru/messenger/v1/accounts/{user_data['avito_user_id']}/chats/{chat_id}/messages"
                            async with session.post(msg_url, headers=headers, json=message_data) as msg_response:
                                if msg_response.status == 200:
                                    print(f"Successfully sent message to chat {chat_id}")
                                    self.save_replied_chat(user_data['user_id'], chat_id)
                                else:
                                    print(f"Failed to send message: {msg_response.status}")
                except Exception as e:
                    print(f"Error checking messages for user {user_data['user_id']}: {e}")
                    continue

    async def handle_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Временно отключаем обработку изображений
        await update.message.reply_text("Функция загрузки изображений временно недоступна")
        return ConversationHandler.END

    async def check_balance_and_advance(self, user_data):
        token = await self.get_token(user_data['client_id'], user_data['client_secret'])
        if not token:
            return None
        
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'X-Source': 'telegram_bot'
            }
            
            # Проверяем основной баланс
            balance_url = f"https://api.avito.ru/core/v1/accounts/{user_data['avito_user_id']}/balance/"
            balance_data = None
            try:
                async with session.get(balance_url, headers=headers) as response:
                    if response.status == 200:
                        balance_data = await response.json()
            except Exception as e:
                print(f"Error checking main balance: {e}")

            # Проверяем аванс
            advance_url = "https://api.avito.ru/cpa/v3/balanceInfo"
            advance_data = None
            try:
                async with session.post(advance_url, headers=headers, json={}) as response:
                    if response.status == 200:
                        advance_data = await response.json()
            except Exception as e:
                print(f"Error checking advance balance: {e}")

            return {
                'main_balance': balance_data,
                'advance': advance_data.get('balance', 0) / 100 if advance_data else None
            }

    async def check_balance_periodically(self, context: ContextTypes.DEFAULT_TYPE):
        print("\n💰 Запущена проверка балансов")
        users = self.get_active_users()
        print(f"📊 Проверяем баланс для {len(users)} пользователей")
        
        for user_data in users:
            try:
                balances = await self.check_balance_and_advance(user_data)
                
                if balances:
                    main_balance = balances['main_balance']
                    advance_balance = balances['advance']
                    warning_msg = []
                    
                    # Проверка основного баланса (один раз при < 200)
                    if (main_balance and main_balance.get('real', 0) < 200 and 
                        not user_data.get('notified_main_balance_200')):
                        warning_msg.append(
                            f"⚠️ Основной баланс меньше 200 рублей!\n"
                            f"Текущий баланс: {main_balance.get('real', 0)} ₽"
                        )
                        user_data['notified_main_balance_200'] = 1
                        self.save_user(user_data['user_id'], user_data)
                    
                    # Проверка аванса (при < 200 и < 100)
                    if advance_balance is not None:
                        if advance_balance < 200 and not user_data.get('notified_advance_200'):
                            warning_msg.append(
                                f"⚠️ Баланс аванса меньше 200 рублей!\n"
                                f"Текущий аванс: {advance_balance:.2f} ₽"
                            )
                            user_data['notified_advance_200'] = 1
                            self.save_user(user_data['user_id'], user_data)
                        
                        if advance_balance < 100 and not user_data.get('notified_advance_100'):
                            warning_msg.append(
                                f"❗️ Баланс аванса меньше 100 рублей!\n"
                                f"Текущий аванс: {advance_balance:.2f} ₽"
                            )
                            user_data['notified_advance_100'] = 1
                            self.save_user(user_data['user_id'], user_data)
                    
                    if warning_msg:
                        await context.bot.send_message(
                            user_data['user_id'],
                            "❗️ ВНИМАНИЕ! Низкий баланс!\n\n" + "\n\n".join(warning_msg) +
                            "\n\nПожалуйста, пополните баланс для продолжения работы с сервисом!"
                        )
                        print(f"⚠️ Отправлено предупреждение о низком балансе пользователю {user_data['user_id']}")
                    
            except Exception as e:
                print(f"❌ Ошибка при проверке баланса пользователя {user_data['user_id']}: {e}")
        
        print("✅ Проверка балансов завершена\n")

    async def process_successful_payment(self, user_id: str, qrc_id: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            c.execute('BEGIN')
            
            # Получаем информацию о платеже
            c.execute('''
                UPDATE qr_payments 
                SET status = 'succeeded', paid_at = strftime('%s','now')
                WHERE qrc_id = ? AND user_id = ? AND status = 'pending'
                RETURNING accounts_count
            ''', (qrc_id, user_id))
            
            result = c.fetchone()
            if result:
                accounts_count = result[0]
                
                # Обновляем количество доступных аккаунтов
                c.execute('''
                    UPDATE users 
                    SET paid_accounts = paid_accounts + ?
                    WHERE user_id = ?
                ''', (accounts_count, user_id))
                
                c.execute('COMMIT')
                return True
            
            c.execute('ROLLBACK')
            return False
            
        except Exception as e:
            c.execute('ROLLBACK')
            print(f"Error processing payment: {e}")
            return False
        finally:
            conn.close()

    async def get_available_accounts(self, user_id: str) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            # Получаем количество оплаченных аккаунтов
            c.execute('SELECT paid_accounts FROM users WHERE user_id = ?', (user_id,))
            result = c.fetchone()
            paid_accounts = result[0] if result else 0
            
            # Возвращаем сумму бесплатных (3) и оплаченных аккаунтов
            return 3 + paid_accounts
        finally:
            conn.close()

    async def buy_accounts_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("1 аккаунт - 200₽", callback_data='buy_1')],
            [InlineKeyboardButton("3 аккаунта - 500₽", callback_data='buy_3')],
            [InlineKeyboardButton("5 аккаунтов - 800₽", callback_data='buy_5')],
            [InlineKeyboardButton("🔙 Назад", callback_data='manage_accounts')]
        ]
        
        await update.callback_query.edit_message_text(
            "💎 Покупка дополнительных аккаунтов\n\n"
            "Выберите количество аккаунтов:\n\n"
            "• Каждый аккаунт позволяет настроить отдельный автоответ\n"
            "• Оплата разовая (не подписка)\n"
            "• Активация моментальная после оплаты",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def test_token_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.message.from_user.id) != os.getenv('ADMIN_TELEGRAM_ID'):
            await update.message.reply_text("❌ У вас нет прав для этой команды")
            return
        
        try:
            payment_service = PaymentService(os.getenv('TOCHKA_JWT_TOKEN'))
            await payment_service.test_token()
            await update.message.reply_text("✅ Токен работает корректно!")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка проверки токена:\n{str(e)}")

class PaymentService:
    def __init__(self, jwt_token):
        self.jwt_token = jwt_token.strip()
        if not self.jwt_token.startswith('Bearer '):
            self.jwt_token = f'Bearer {self.jwt_token}'
        
        self.base_url = 'https://enter.tochka.com'
        self._merchant_info = None

    async def test_token(self):
        """Тестирует валидность токена через получение списка клиентов"""
        try:
            headers = {
                'Authorization': self.jwt_token,
                'Content-Type': 'application/json'
            }
            
            test_url = f'{self.base_url}/open/v2/customers'
            
            async with aiohttp.ClientSession() as session:
                async with session.get(test_url, headers=headers) as response:
                    response_text = await response.text()
                    logging.info(f"Test token response status: {response.status}")
                    logging.debug(f"Test token response: {response_text}")
                    
                    if response.status != 200:
                        raise Exception(f"{response.status}: {response_text}")
                    return True
        except Exception as e:
            logging.error(f"Token test failed: {str(e)}")
            raise

    async def _get_customer_info(self):
        """Получает информацию о клиенте"""
        if self._merchant_info is not None:
            return self._merchant_info

        headers = {
            'Authorization': self.jwt_token,
            'Content-Type': 'application/json'
        }

        async with aiohttp.ClientSession() as session:
            # Получаем список клиентов
            customers_url = f'{self.base_url}/open/v2/customers'
            async with session.get(customers_url, headers=headers) as response:
                response_text = await response.text()
                logging.debug(f"Customers response: {response_text}")
                
                if response.status != 200:
                    raise Exception(f"Error getting customers: {response_text}")
                
                data = await response.json()
                business_customer = next(
                    (c for c in data.get('customers', []) if c.get('customerType') == 'Business'),
                    None
                )
                
                if not business_customer:
                    raise Exception("No business customer found")
                
                customer_code = business_customer['customerCode']
                
                # Получаем детальную информацию о клиенте
                customer_url = f'{self.base_url}/open/v2/customers/{customer_code}'
                async with session.get(
                    customer_url,
                    params={'bankCode': '044525104'},
                    headers=headers
                ) as response:
                    response_text = await response.text()
                    logging.debug(f"Customer details response: {response_text}")
                    
                    if response.status != 200:
                        raise Exception(f"Error getting customer info: {response_text}")
                    
                    customer_info = await response.json()
                    self._merchant_info = {
                        'merchantId': customer_info.get('merchantId'),
                        'accountId': customer_info.get('accountId')
                    }
                    
                    if not all(self._merchant_info.values()):
                        raise Exception("Invalid merchant info received")
                    
                    return self._merchant_info

    async def create_payment_qr(self, amount, accounts_count, user_id):
        """Создает QR-код для оплаты"""
        try:
            merchant_info = await self._get_customer_info()
            
            headers = {
                'Authorization': self.jwt_token,
                'Content-Type': 'application/json'
            }
            
            # Создаем кассовый QR-код
            qr_url = f"{self.base_url}/sbp/v2/cashbox_qr_code"
            register_payload = {
                "accountId": merchant_info['accountId'],
                "merchantId": merchant_info['merchantId'],
                "redirectUrl": os.getenv("PAYMENT_SUCCESS_URL")
            }
            
            async with aiohttp.ClientSession() as session:
                # Регистрируем QR-код
                async with session.post(qr_url, json=register_payload, headers=headers) as response:
                    response_text = await response.text()
                    logging.info(f"QR registration status: {response.status}")
                    logging.debug(f"QR registration response: {response_text}")
                    
                    if response.status != 200:
                        raise Exception(f"QR registration failed: {response_text}")
                    
                    qr_data = await response.json()
                    qrc_id = qr_data.get('qrcId')
                    
                    if not qrc_id:
                        raise Exception("No QR code ID received")
                    
                    # Активируем QR-код с суммой
                    activate_url = f"{self.base_url}/sbp/v2/cashbox_qr_code/{qrc_id}/activate"
                    activate_payload = {
                        "amount": int(amount * 100)  # в копейках
                    }
                    
                    async with session.post(activate_url, json=activate_payload, headers=headers) as response:
                        response_text = await response.text()
                        logging.info(f"QR activation status: {response.status}")
                        logging.debug(f"QR activation response: {response_text}")
                        
                        if response.status != 200:
                            raise Exception(f"QR activation failed: {response_text}")
                    
                    # Сохраняем информацию о платеже
                    conn = sqlite3.connect('avito_bot.db')
                    c = conn.cursor()
                    c.execute('''
                        INSERT INTO qr_payments 
                        (user_id, qrc_id, amount, accounts_count, status)
                        VALUES (?, ?, ?, ?, 'pending')
                    ''', (user_id, qrc_id, amount, accounts_count))
                    conn.commit()
                    conn.close()
                    
                    return {
                        'qrc_id': qrc_id,
                        'image': qr_data.get('image'),
                        'amount': amount
                    }
        except Exception as e:
            logging.error(f"Error creating QR payment: {e}")
            return None

    async def check_payment_status(self, qrc_id):
        """Проверяет статус платежа"""
        try:
            headers = {
                'Authorization': self.jwt_token,
                'Content-Type': 'application/json'
            }
            
            status_url = f"{self.base_url}/sbp/v2/cashbox_qr_code/{qrc_id}/payment-status"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(status_url, headers=headers) as response:
                    response_text = await response.text()
                    logging.info(f"Payment status check: {response.status}")
                    logging.debug(f"Payment status response: {response_text}")
                    
                    if response.status != 200:
                        raise Exception(f"{response.status}: {response_text}")
                        
                    data = await response.json()
                    return data.get('status', 'PENDING')
        except Exception as e:
            logging.error(f"Error checking payment status: {e}")
            return 'ERROR'

bot = AvitoBot()  # Создаем глобальный экземпляр бота

def main():
    if __name__ == '__main__':
        # Проверка переменных окружения
        required_vars = {
            "TOCHKA_JWT_TOKEN": os.getenv("TOCHKA_JWT_TOKEN"),
            "TOCHKA_CLIENT_ID": os.getenv("TOCHKA_CLIENT_ID"),
            "PAYMENT_SUCCESS_URL": os.getenv("PAYMENT_SUCCESS_URL"),
            "ADMIN_TELEGRAM_ID": os.getenv("ADMIN_TELEGRAM_ID")
        }
        
        missing_vars = [var for var, value in required_vars.items() if not value]
        
        if missing_vars:
            print("❌ Ошибка: Отсутствуют обязательные переменные окружения:")
            for var in missing_vars:
                print(f"  - {var}")
            return
        
        try:
            # Проверяем токен при запуске
            payment_service = PaymentService(os.getenv('TOCHKA_JWT_TOKEN'))
            
            bot = AvitoBot()
            print("✅ Бот инициализирован")
            
            application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()
            
            # Добавляем обработчик команды проверки токена
            application.add_handler(CommandHandler('test_token', bot.test_token_handler))
            
            # Добавляем логи в check_messages
            async def check_messages_with_logs(context):
                print("\n🔄 Запущена проверка сообщений")
                users = bot.get_active_users()
                print(f"📊 Найдено активных пользователей: {len(users)}")
                await bot.check_messages(context)
                print("✅ Проверка сообщений завершена\n")

            # Добавляем логи в send_reminder
            async def send_reminder(context):
                print("\n📢 Запущена отправка напоминаний")
                conn = sqlite3.connect(bot.db_path)
                c = conn.cursor()
                c.execute('SELECT user_id FROM users')
                users = c.fetchall()
                print(f"👥 Всего пользователей для напоминания: {len(users)}")
                conn.close()

                for user in users:
                    try:
                        await context.bot.send_message(
                            user[0],
                            "Напоминаю! У нас есть бот для рассылки по чатам Avito!\n\n"
                            "🚀 С помощью @avsender_bot вы можете:\n"
                            "• Отправлять сообщения по своим чатам\n"
                            "• Настраивать фильтры по датам\n"
                            "• Добавлять изображения\n\n"
                            "👉 Переходите прямо сейчас!",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("Перейти к боту рассылки", url="t.me/avsender_bot")]
                            ])
                        )
                        print(f"✅ Напоминание отправлено пользователю {user[0]}")
                    except Exception as e:
                        print(f"❌ Ошибка отправки напоминания пользователю {user[0]}: {e}")
                        continue
                print("✅ Отправка напоминаний завершена\n")

            conv_handler = ConversationHandler(
                entry_points=[
                    CommandHandler('start', bot.start),
                    CallbackQueryHandler(bot.button_handler)
                ],
                states={
                    WAITING_CLIENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_client_id)],
                    WAITING_CLIENT_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_client_secret)],
                    WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_user_id)],
                    WAITING_TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_template)],
                    WAITING_IMAGE: [MessageHandler(filters.PHOTO, bot.handle_image)],  # Новый обработчик
                },
                fallbacks=[CommandHandler('start', bot.start)],
            )
            
            application.add_handler(conv_handler)
            print("✅ Обработчики добавлены")
            
            job_queue = application.job_queue
            job_queue.run_repeating(check_messages_with_logs, interval=60, first=10)
            job_queue.run_repeating(send_reminder, interval=3*24*60*60, first=24*60*60)
            job_queue.run_repeating(bot.check_balance_periodically, interval=60*60, first=10)  # Проверка каждый час
            print("✅ Задачи планировщика добавлены")
            
            print("\n🚀 Бот запущен и готов к работе!")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logging.error(f"Startup error: {e}")
            print(f"❌ Ошибка запуска: {e}")
            sys.exit(1)

if __name__ == '__main__':
    main()