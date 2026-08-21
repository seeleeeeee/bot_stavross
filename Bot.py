import os
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ConversationHandler

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

# === ЗАГРУЗКА АНАЛОГОВ ===
def load_analogies():
    if os.path.exists("analogies.json"):
        with open("analogies.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            return {k.strip(): [{inner_k.strip(): str(inner_v).strip() for inner_k, inner_v in item.items()} for item in v] for k, v in raw_data.items()}
    return {"Ручки": [], "Ножки": []}

ANALOGIES_DB = load_analogies()
CATEGORIES = list(ANALOGIES_DB.keys())
MAIN_MENU, CATEGORY, SEARCH = range(3)

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
        if item.get('les_link'):
            text += f"   🔗 Les-WM: <a href='{item['les_link']}'>Ссылка</a>\n"
        if item.get('stavros_link'):
            text += f"   🔗 Stavros: <a href='{item['stavros_link']}'>Ссылка</a>\n"
        text += "\n"
    return text

# === ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    total_analogs = sum(len(items) for items in ANALOGIES_DB.values())
    welcome_text = (
        f"👋 Привет, <b>{user_name}</b>!\n\n"
        f"🤖 Бот для поиска аналогов STAVROS и Les-WM.\n"
        f"📦 В базе <b>{total_analogs}</b> аналогов.\n\n"
        f"👇 <b>Выбери действие:</b>"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu(), parse_mode="HTML")
    return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    
    if action == "main_menu":
        await query.edit_message_text("🏠 <b>Главное меню</b>", reply_markup=get_main_menu(), parse_mode="HTML")
        return MAIN_MENU
    elif action == "main_search":
        await query.edit_message_text("🔍 <b>Поиск аналога</b>\n\nВведите название товара:", parse_mode="HTML")
        return SEARCH
    elif action == "main_categories":
        await query.edit_message_text("📂 <b>Категории</b>", reply_markup=get_category_keyboard(), parse_mode="HTML")
        return CATEGORY
    elif action == "main_about":
        total_analogs = sum(len(items) for items in ANALOGIES_DB.values())
        about_text = f"ℹ️ <b>О боте</b>\n\n🤖 Поиск аналогов STAVROS и Les-WM.\n📦 В базе: {total_analogs} аналогов."
        await query.edit_message_text(about_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]]), parse_mode="HTML")
        return MAIN_MENU

async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data["category"] = category
    await query.edit_message_text(f"📂 Категория: <b>{category}</b>\n\nВведите название:", parse_mode="HTML")
    return SEARCH

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text
    category = context.user_data.get("category")
    
    if not category:
        await update.message.reply_text("⚠️ Сначала выберите категорию:", reply_markup=get_category_keyboard())
        return CATEGORY
        
    results = search_analogies(category, query_text)
    reply = format_analogies(results, category, query_text)
    
    await update.message.reply_text(reply, parse_mode="HTML", disable_web_page_preview=True, reply_markup=get_after_search_keyboard())
    return SEARCH

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Отменено.", reply_markup=get_main_menu())
    return MAIN_MENU

# === СОЗДАНИЕ И ЗАПУСК ПРИЛОЖЕНИЯ ===
def main():
    application = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [CallbackQueryHandler(main_menu_handler, pattern="^main_")],
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
    application.add_handler(conv_handler)

    port = int(os.environ.get('PORT', 10000))
    webhook_url = f"https://bot-stavross.onrender.com/{TOKEN}"
    
    print("🚀 Запуск бота с использованием встроенного вебхука...")
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,
        webhook_url=webhook_url
    )

if __name__ == '__main__':
    main()