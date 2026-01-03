import os
import random
import logging
import threading
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler
from supabase import create_client, Client
from flask import Flask

# Загрузка переменных окружения
load_dotenv()

TG_TOKEN = os.getenv("TG_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# --- DUMMY SERVER START ---
# Создаем простейший веб-сервер, чтобы Render видел, что процесс активен
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is alive!"

def run_server():
    # Render (и другие) предоставляют порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()
# --- DUMMY SERVER END ---

# Инициализация Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Состояния для разговора
ASK_NAME = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем, есть ли уже такой пользователь
    response = supabase.table('secret_santa').select("*").eq('user_id', user_id).execute()
    
    if len(response.data) > 0:
        await update.message.reply_text(f"Ты зарегистрирован как {response.data[0]['name']}. Жди начала игры!")
        return ConversationHandler.END
    
    await update.message.reply_text("🎅 Хо-хо-хо! 🎅\nПривет! Это Тайный Санта от BestQuest. "
          "С Новым 2026 годом тебя! 🎉\n\n📝 Придумай себе псевдоним и напиши его мне. Не "
          "указывай настоящее имя! А то интрига, кто кому дарит подарок, раскроется слишком "
          "рано 😉\n💡 Можно, например, придумать себе какое-нибудь новогоднее имя или "
          "использовать название своей команды, если вы в ней одни. Ну или что-нибудь в "
          "таком духе.\n\n(Только этого, того... давай цензурно, ладно? Пожалуйста 🙏)")
    await update.message.reply_text("🎁 О подарке: 🎁\nВо-первых, не надо покупать слишком "
          "дорогой подарок, чтобы никому не было неловко. Давайте договоримся, что лимит - "
          "500 рублей. 💸\nВо-вторых - купи что-нибудь прикольное. Что-нибудь, что, может быть, "
          "ты бы сам хотел получить. Давайте все сделам свои подарки яркими и веселыми, "
          "чтобы это мероприятие надолго осталось тёплым воспоминанием для всех нас! 🔮❤️")
    return ASK_NAME

async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    user_id = update.effective_user.id

    if len(name) == 0:
        await update.message.reply_text("Ты, кажется, не ввёл ни символа. Попробуй ещё раз!")
        return ASK_NAME

    try:
        data = {"user_id": user_id, "name": name}
        supabase.table('secret_santa').insert(data).execute()
        await update.message.reply_text(f"Отлично, {name}! Ты в игре. Немного подождём остальных - и начнём... ⏳")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("Ой! Кажется, произошла ошибка при записи в базу данных. "
                                        "Пожалуйста, перезапусти бота командой /start и введи свой псевдоним еще раз.")
    
    return ConversationHandler.END

async def activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверка на админа
    if user_id != ADMIN_ID:
      return

    # Получаем всех участников
    response = supabase.table('secret_santa').select("*").execute()
    participants = response.data
    count = len(participants)

    if count < 2:
        await update.message.reply_text(f"Слишком мало участников ({count}). Нужно минимум 2.")
        return

    await update.message.reply_text(f"Участников: {count}. Начинаю распределение...")

    # Генерация сдвига
    # j от 1 до count-1
    shift = random.randint(1, count - 1)
    
    # Рассылка
    for i in range(count):
        santa = participants[i]
        # Вычисляем индекс получателя со сдвигом по кругу
        receiver_index = (i + shift) % count
        receiver = participants[receiver_index]

        santa_tg_id = santa['user_id']
        receiver_name = receiver['name']

        try:
            await context.bot.send_message(
                chat_id=santa_tg_id,
                text=f"🎅 Хо-хо-хо! 🎅\nЖребий брошен.\nТы даришь подарок игроку: 🎁 {receiver_name} 🎁"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение пользователю {santa_tg_id}: {e}")
            await update.message.reply_text(f"Ошибка отправки для {santa['name']} (ID: {santa_tg_id})")

    await update.message.reply_text("Распределение завершено! Все сообщения отправлены.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Регистрация отменена.")
    return ConversationHandler.END

if __name__ == '__main__':
    # Запускаем dummy-сервер в отдельном потоке
    keep_alive()

    application = ApplicationBuilder().token(TG_TOKEN).build()

    # Обработчик регистрации
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    
    # Команда админа
    application.add_handler(CommandHandler('activate', activate))

    print("Бот запущен...")
    application.run_polling()
