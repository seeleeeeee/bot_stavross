import os
import json
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ConversationHandler

# === ЗАГРУЖАЕМ ПЕРЕМЕННЫЕ ИЗ .env ===
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

# === ТВОЙ ID (ТЫ АДМИН) ===
ADMIN_IDS = [1032384251]

# === СОСТОЯНИЯ ДЛЯ РАЗГОВОРА ===
CATEGORY, SEARCH, ADMIN_ACTION, ADD_NAME, ADD_SIZE, ADD_MATERIAL, ADD_FINISH, ADD_STAVROS_PRICE, ADD_OUR_PRICE, ADD_LINK = range(10)

DB_FILE = "products_db.json"

# === ЗАГРУЗКА БАЗЫ ===
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"Ручки": [], "Ножки": [], "Столики": [], "Аксессуары": []}

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

PRODUCTS_DB = load_db()
CATEGORIES = list(PRODUCTS_DB.keys())

# === КЛАВИАТУРЫ ===
def get_category_keyboard():
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat_{cat}")] for cat in CATEGORIES]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить товар", callback_data="admin_add")],
        [InlineKeyboardButton("📋 Список товаров", callback_data="admin_list")],
        [InlineKeyboardButton("❌ Удалить товар", callback_data="admin_delete")],
        [InlineKeyboardButton("🚪 Выйти из админки", callback_data="admin_exit")]
    ])

def is_admin(user_id):
    return user_id in ADMIN_IDS

def search_in_category(category, query):
    query = query.lower().strip()
    results = []
    for product in PRODUCTS_DB.get(category, []):
        if query in product["name"].lower() or query in product["material"].lower():
            results.append(product)
    return results

def format_results(results, category, query):
    if not results:
        return f"❌ В категории «{category}» ничего не найдено по запросу «{query}»."
    text = f"🔍 Найдено <b>{len(results)}</b> аналогов:\n\n"
    for i, p in enumerate(results[:15], 1):
        diff = p["our_price"] - p["price"]
        emoji = "📈" if diff > 0 else "📉" if diff < 0 else "⚖️"
        text += f"{i}. <b>{p['name']}</b>\n"
        text += f"   📐 {p['size']} | 🌳 {p['material']} | 🎨 {p['finish']}\n"
        text += f"   💰 Stavros: {p['price']:,} ₽ | 🏷️ Наша: {p['our_price']:,} ₽ | {emoji} {abs(diff):,} ₽\n"
        text += f"   🔗 <a href='{p['link']}'>Ссылка</a>\n\n"
    return text

# === /START ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_category_keyboard()
    await update.message.reply_text(
        "🔍 <b>Поиск аналогов товаров (Stavros)</b>\n\n"
        "Выберите категорию:\n"
        "🔹 Ручки\n"
        "🔹 Ножки\n"
        "🔹 Столики\n"
        "🔹 Аксессуары",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    return CATEGORY

# === ВЫБОР КАТЕГОРИИ ===
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

# === ПОИСК ===
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    category = context.user_data.get("category")
    if not category:
        keyboard = get_category_keyboard()
        await update.message.reply_text("⚠️ Сначала выберите категорию:", reply_markup=keyboard)
        return CATEGORY
    results = search_in_category(category, query)
    reply = format_results(results, category, query)
    await update.message.reply_text(reply, parse_mode="HTML", disable_web_page_preview=True)
    return SEARCH

# === /ADMIN ===
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔐 <b>Админ-панель</b>\n\n"
        "Выберите действие:",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )
    return ADMIN_ACTION

# === АДМИН-ДЕЙСТВИЯ ===
async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "admin_exit":
        await query.edit_message_text("🚪 Выход из админки. Используйте /start для поиска.")
        return ConversationHandler.END

    if action == "admin_add":
        context.user_data["admin_action"] = "add"
        keyboard = get_category_keyboard()
        await query.edit_message_text(
            "➕ <b>Добавление товара</b>\n\n"
            "Выберите категорию, в которую хотите добавить товар:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return CATEGORY

    if action == "admin_list":
        text = "📋 <b>Все товары в базе:</b>\n\n"
        total = 0
        for cat, products in PRODUCTS_DB.items():
            text += f"<b>{cat}</b>: {len(products)} шт.\n"
            total += len(products)
        text += f"\n<b>Всего товаров:</b> {total}"
        await query.edit_message_text(text, parse_mode="HTML")
        await query.message.reply_text("Выберите действие:", reply_markup=get_admin_keyboard())
        return ADMIN_ACTION

    if action == "admin_delete":
        context.user_data["admin_action"] = "delete"
        keyboard = get_category_keyboard()
        await query.edit_message_text(
            "🗑️ <b>Удаление товара</b>\n\n"
            "Выберите категорию:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return CATEGORY

# === ДОБАВЛЕНИЕ ТОВАРА ===
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data["new_product"] = {"category": category}
    await query.edit_message_text(
        f"➕ <b>Новый товар</b>\n"
        f"Категория: {category}\n\n"
        f"Введите <b>название</b> товара:",
        parse_mode="HTML"
    )
    return ADD_NAME

async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_product"]["name"] = update.message.text
    await update.message.reply_text("Введите <b>размер</b> (например: 253×54×37):", parse_mode="HTML")
    return ADD_SIZE

async def add_product_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_product"]["size"] = update.message.text
    await update.message.reply_text("Введите <b>материал</b> (Дуб / Бук):", parse_mode="HTML")
    return ADD_MATERIAL

async def add_product_material(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_product"]["material"] = update.message.text
    await update.message.reply_text("Введите <b>отделку</b> (например: Под эмаль):", parse_mode="HTML")
    return ADD_FINISH

async def add_product_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_product"]["finish"] = update.message.text
    await update.message.reply_text("Введите <b>цену Stavros</b> (только цифры):", parse_mode="HTML")
    return ADD_STAVROS_PRICE

async def add_product_stavros_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_product"]["price"] = int(update.message.text.replace(" ", ""))
        await update.message.reply_text("Введите <b>нашу цену</b> (только цифры):", parse_mode="HTML")
        return ADD_OUR_PRICE
    except ValueError:
        await update.message.reply_text("❌ Ошибка! Введите число (например: 2670):")
        return ADD_STAVROS_PRICE

async def add_product_our_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_product"]["our_price"] = int(update.message.text.replace(" ", ""))
        await update.message.reply_text("Введите <b>ссылку</b> на товар Stavros:", parse_mode="HTML")
        return ADD_LINK
    except ValueError:
        await update.message.reply_text("❌ Ошибка! Введите число (например: 2750):")
        return ADD_OUR_PRICE

async def add_product_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = context.user_data["new_product"]
    product["link"] = update.message.text
    category = product["category"]
    
    # Добавляем в базу
    PRODUCTS_DB[category].append({
        "name": product["name"],
        "size": product["size"],
        "material": product["material"],
        "finish": product["finish"],
        "price": product["price"],
        "our_price": product["our_price"],
        "link": product["link"]
    })
    save_db(PRODUCTS_DB)
    
    await update.message.reply_text(
        f"✅ <b>Товар добавлен!</b>\n\n"
        f"📌 {product['name']}\n"
        f"📐 {product['size']} | 🌳 {product['material']} | 🎨 {product['finish']}\n"
        f"💰 Stavros: {product['price']:,} ₽ | 🏷️ Наша: {product['our_price']:,} ₽\n"
        f"🔗 {product['link']}",
        parse_mode="HTML"
    )
    await update.message.reply_text("Выберите действие:", reply_markup=get_admin_keyboard())
    return ADMIN_ACTION

# === УДАЛЕНИЕ ТОВАРА ===
async def delete_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data["delete_category"] = category
    products = PRODUCTS_DB.get(category, [])
    
    if not products:
        await query.edit_message_text(f"❌ В категории «{category}» нет товаров.")
        await query.message.reply_text("Выберите действие:", reply_markup=get_admin_keyboard())
        return ADMIN_ACTION
    
    keyboard = []
    for i, p in enumerate(products):
        keyboard.append([InlineKeyboardButton(
            f"{i+1}. {p['name']} | {p['size']}",
            callback_data=f"del_{i}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
    
    await query.edit_message_text(
        f"🗑️ <b>Удаление товара</b>\n"
        f"Категория: {category}\n\n"
        f"Выберите товар для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return ADMIN_ACTION

async def delete_product_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_back":
        await query.edit_message_text("Выберите действие:", reply_markup=get_admin_keyboard())
        return ADMIN_ACTION
    
    idx = int(query.data.replace("del_", ""))
    category = context.user_data.get("delete_category")
    product = PRODUCTS_DB[category].pop(idx)
    save_db(PRODUCTS_DB)
    
    await query.edit_message_text(
        f"✅ <b>Товар удалён</b>\n\n"
        f"📌 {product['name']} | {product['size']}",
        parse_mode="HTML"
    )
    await query.message.reply_text("Выберите действие:", reply_markup=get_admin_keyboard())
    return ADMIN_ACTION

# === КОМАНДА /ID ===
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 Твой ID: <code>{update.effective_user.id}</code>",
        parse_mode="HTML"
    )

# === ОТМЕНА ===
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Действие отменено. Используйте /start для поиска.")
    return ConversationHandler.END

# === ЗАПУСК БОТА ===
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Команда /id
    app.add_handler(CommandHandler("id", get_id))
    
    # Основной разговор
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("admin", admin)],
        states={
            CATEGORY: [
                CallbackQueryHandler(category_selected, pattern="^cat_"),
                CallbackQueryHandler(add_product_start, pattern="^cat_"),
                CallbackQueryHandler(delete_product_start, pattern="^cat_"),
                CallbackQueryHandler(admin_action, pattern="^admin_"),
                CallbackQueryHandler(delete_product_confirm, pattern="^del_|^admin_back"),
            ],
            SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search),
                CallbackQueryHandler(category_selected, pattern="^cat_"),
            ],
            ADMIN_ACTION: [
                CallbackQueryHandler(admin_action, pattern="^admin_"),
                CallbackQueryHandler(delete_product_confirm, pattern="^del_|^admin_back"),
            ],
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            ADD_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_size)],
            ADD_MATERIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_material)],
            ADD_FINISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_finish)],
            ADD_STAVROS_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_stavros_price)],
            ADD_OUR_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_our_price)],
            ADD_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_link)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(conv_handler)
    
    print("✅ Бот запущен! Напиши ему /start")
    app.run_polling()

if __name__ == "__main__":
    main()
