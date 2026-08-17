import os
import json
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ConversationHandler

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле!")

ADMIN_IDS = [1032384251]

# === СОСТОЯНИЯ ДЛЯ РАЗГОВОРА ===
MAIN_MENU, CATEGORY, SEARCH = range(3)

# === ЗАГРУЗКА АНАЛОГОВ ИЗ JSON ===
def load_analogies():
    if os.path.exists("analogies.json"):
        with open("analogies.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {"Ручки": [], "Ножки": []}

ANALOGIES_DB = load_analogies()
CATEGORIES = list(ANALOGIES_DB.keys())

# === КЛАВИАТУРЫ ===
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск аналога", callback_data="main_search")],
        [InlineKeyboardButton("📂 Категории", callback_data="main_categories")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="main_about")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_category_keyboard():
    keyboard = [[InlineKeyboardButton(f"📁 {cat}", callback_data=f"cat_{cat}")] for cat in CATEGORIES]
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_after_search_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Новый поиск", callback_data="main_search")],
        [InlineKeyboardButton("📂 Другая категория", callback_data="main_categories")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
    ])

# === ФУНКЦИИ ПОИСКА ===
def search_analogies(category, query):
    query = query.lower().strip()
    results = []
    
    for item in ANALOGIES_DB.get(category, []):
        if query in item['les_name'].lower() or query in item['stavros_name'].lower():
            results.append(item)
    
    return results

def format_analogies(results, category, query):
    if not results:
        return f"❌ В категории «{category}» ничего не найдено по запросу «{query}»."
    
    text = f"🔍 Найдено <b>{len(results)}</b> аналогов:\n\n"
    for i, item in enumerate(results[:15], 1):
        text += f"{i}. <b>{item['les_name']}</b> → <b>{item['stavros_name']}</b>\n"
        if item['les_link']:
            text += f"   🔗 Les-WM: <a href='{item['les_link']}'>Ссылка</a>\n"
        if item['stavros_link']:
            text += f"   🔗 Stavros: <a href='{item['stavros_link']}'>Ссылка</a>\n"
        text += "\n"
    
    return text

# === ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    total_analogs = sum(len(items) for items in ANALOGIES_DB.values())
    
    welcome_text = (
        f"👋 Привет, <b>{user_name}</b>!\n\n"
        f"🤖 Я бот для поиска аналогов товаров <b>STAVROS</b> и <b>Les-WM</b>.\n"
        f"📦 В моей базе <b>{total_analogs}</b> аналогов.\n\n"
        f"🔹 <b>Как я работаю:</b>\n"
        f"   Выбери категорию или воспользуйся поиском\n"
        f"   Я покажу пары аналогов с ссылками\n\n"
        f"👇 <b>Выбери действие:</b>"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )
    return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "main_menu":
        await query.edit_message_text(
            "🏠 <b>Главное меню</b>\n\nВыберите действие:",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
        return MAIN_MENU
    
    elif action == "main_search":
        await query.edit_message_text(
            "🔍 <b>Поиск аналога</b>\n\n"
            "Введите название товара (например: «Карпаты», «Целлер»):",
            parse_mode="HTML"
        )
        return SEARCH
    
    elif action == "main_categories":
        await query.edit_message_text(
            "📂 <b>Категории</b>\n\nВыберите категорию:",
            reply_markup=get_category_keyboard(),
            parse_mode="HTML"
        )
        return CATEGORY
    
    elif action == "main_about":
        total_analogs = sum(len(items) for items in ANALOGIES_DB.values())
        about_text = (
            "ℹ️ <b>О боте</b>\n\n"
            "🤖 Бот для поиска аналогов товаров STAVROS и Les-WM\n\n"
            "🔹 <b>Что умеет:</b>\n"
            "   - Искать аналоги по названиям\n"
            "   - Показывать пары товаров\n"
            "   - Давать ссылки на оба сайта\n\n"
            f"📦 <b>В базе:</b> {total_analogs} аналогов\n\n"
            "👨‍💻 <b>Разработчик:</b> @seeleeeeee"
        )
        await query.edit_message_text(
            about_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
            ]),
            parse_mode="HTML"
        )
        return MAIN_MENU

async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data["category"] = category
    
    await query.edit_message_text(
        f"📂 Категория: <b>{category}</b>\n\n"
        f"Введите название товара (например: «Карпаты», «Целлер»):",
        parse_mode="HTML"
    )
    return SEARCH

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    category = context.user_data.get("category")
    
    if not category:
        await update.message.reply_text(
            "⚠️ Сначала выберите категорию:",
            reply_markup=get_category_keyboard()
        )
        return CATEGORY
    
    results = search_analogies(category, query)
    reply = format_analogies(results, category, query)
    
    await update.message.reply_text(
        reply,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_after_search_keyboard()
    )
    return SEARCH

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Действие отменено.",
        reply_markup=get_main_menu()
    )
    return MAIN_MENU

# === ЗАПУСК БОТА ===
def main():
    # ПРИНУДИТЕЛЬНО УДАЛЯЕМ ВЕБХУК
    try:
        response = requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
        print(f"✅ Вебхук удалён: {response.json()}")
    except Exception as e:
        print(f"⚠️ Ошибка удаления вебхука: {e}")
    
    # ПРИНУДИТЕЛЬНО СБРАСЫВАЕМ ВЕБХУК
    try:
        response = requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url=")
        print(f"✅ Вебхук сброшен: {response.json()}")
    except Exception as e:
        print(f"⚠️ Ошибка сброса вебхука: {e}")
    
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_handler, pattern="^main_"),
            ],
            CATEGORY: [
                CallbackQueryHandler(category_selected, pattern="^cat_"),
                CallbackQueryHandler(main_menu_handler, pattern="^main_"),
            ],
            SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search),
                CallbackQueryHandler(main_menu_handler, pattern="^main_"),
                CallbackQueryHandler(category_selected, pattern="^cat_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(conv_handler)
    
    print("🚀 Бот запущен! Жду команду /start...")
    app.run_polling()

if __name__ == "__main__":
    main()