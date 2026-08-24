import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ConversationHandler

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

# НАСТРОЙКИ
ADMIN_IDS = [1032384251]


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ЗАГРУЗКА ДАННЫХ 
def load_analogies():
    if os.path.exists("analogies.json"):
        with open("analogies.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            return {k.strip(): [{inner_k.strip(): str(inner_v).strip() for inner_k, inner_v in item.items()} for item in v] for k, v in raw_data.items()}
    return {"Ручки": [], "Ножки": []}

def load_favorites():
    if os.path.exists("favorites.json"):
        with open("favorites.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_favorites(favorites):
    with open("favorites.json", "w", encoding="utf-8") as f:
        json.dump(favorites, f, ensure_ascii=False, indent=2)

def save_analogies(data):
    with open("analogies.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def backup_analogies():
    """Создание бэкапа перед изменениями"""
    if os.path.exists("analogies.json"):
        backup_name = f"analogies_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        import shutil
        shutil.copy2("analogies.json", backup_name)
        # Оставляем последние 5 бэкапов
        backups = sorted([f for f in os.listdir() if f.startswith("analogies_backup_")])
        for old_backup in backups[:-5]:
            os.remove(old_backup)
        logger.info(f"Создан бэкап: {backup_name}")

ANALOGIES_DB = load_analogies()
CATEGORIES = list(ANALOGIES_DB.keys())
FAVORITES_DB = load_favorites()

#  СОСТОЯНИЯ 
MAIN_MENU, CATEGORY, SEARCH, ADMIN_MENU, ADD_ANALOG, DELETE_ANALOG, EDIT_ANALOG = range(7)

# КЛАВИАТУРЫ 
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск аналога", callback_data="main_search")],
        [InlineKeyboardButton("📂 Категории", callback_data="main_categories")],
        [InlineKeyboardButton("⭐ Избранное", callback_data="main_favorites")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="main_about")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton("📝 Добавить аналог", callback_data="admin_add")],
        [InlineKeyboardButton("🗑️ Удалить аналог", callback_data="admin_delete")],
        [InlineKeyboardButton("✏️ Редактировать аналог", callback_data="admin_edit")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_category_keyboard():
    keyboard = [[InlineKeyboardButton(f"📁 {cat}", callback_data=f"cat_{cat}")] for cat in CATEGORIES]
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_after_search_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ В избранное", callback_data="add_favorite")],
        [InlineKeyboardButton("🔍 Новый поиск", callback_data="main_search")],
        [InlineKeyboardButton("📂 Другая категория", callback_data="main_categories")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
    ])

def get_favorites_keyboard(user_id):
    favorites = FAVORITES_DB.get(str(user_id), [])
    keyboard = []
    for i, item in enumerate(favorites[:10], 1):
        keyboard.append([InlineKeyboardButton(
            f"{i}. {item['les_name']} → {item['stavros_name']}",
            callback_data=f"fav_{i-1}"
        )])
    if favorites:
        keyboard.append([InlineKeyboardButton("🗑️ Очистить избранное", callback_data="clear_favorites")])
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]])

#  ФУНКЦИИ ПОИСКА 
def search_analogies(category, query):
    query = query.lower().strip()
    results = []
    for item in ANALOGIES_DB.get(category, []):
        if query in item['les_name'].lower() or query in item['stavros_name'].lower():
            results.append(item)
    return results

def search_all(query):
    query = query.lower().strip()
    all_results = []
    for category in CATEGORIES:
        for item in ANALOGIES_DB.get(category, []):
            if query in item['les_name'].lower() or query in item['stavros_name'].lower():
                all_results.append((category, item))
    return all_results

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

def format_all_results(results, query):
    if not results:
        return f"❌ Ничего не найдено по запросу «{query}»."
    
    categories_found = set(cat for cat, _ in results)
    text = f"🔍 Найдено в <b>{len(categories_found)}</b> категориях:\n\n"
    for category, item in results[:20]:
        text += f"📁 {category}: <b>{item['les_name']}</b> → <b>{item['stavros_name']}</b>\n"
        if item.get('les_link'):
            text += f"   🔗 Les-WM: <a href='{item['les_link']}'>Ссылка</a>\n"
        if item.get('stavros_link'):
            text += f"   🔗 Stavros: <a href='{item['stavros_link']}'>Ссылка</a>\n"
        text += "\n"
    if len(results) > 20:
        text += f"\n... и ещё {len(results) - 20} результатов"
    return text

# ОБРАБОТЧИКИ
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
    user_id = query.from_user.id
    
    if action == "main_menu":
        await query.edit_message_text("🏠 <b>Главное меню</b>", reply_markup=get_main_menu(), parse_mode="HTML")
        return MAIN_MENU
    
    elif action == "main_search":
        # Сохраняем флаг, что ищем без категории
        context.user_data["global_search"] = True
        context.user_data["category"] = None
        await query.edit_message_text(
            "🔍 <b>Глобальный поиск</b>\n\n"
            "Введите название товара (поиск по всем категориям):",
            parse_mode="HTML"
        )
        return SEARCH
    
    elif action == "main_categories":
        context.user_data["global_search"] = False
        await query.edit_message_text("📂 <b>Категории</b>", reply_markup=get_category_keyboard(), parse_mode="HTML")
        return CATEGORY
    
    elif action == "main_favorites":
        await show_favorites(update, context)
        return MAIN_MENU
    
    elif action == "main_about":
        total_analogs = sum(len(items) for items in ANALOGIES_DB.values())
        total_users = len(FAVORITES_DB)
        about_text = (
            f"ℹ️ <b>О боте</b>\n\n"
            f"🤖 Поиск аналогов STAVROS и Les-WM.\n"
            f"📦 В базе: {total_analogs} аналогов.\n"
            f"👥 Пользователей: {total_users}\n"
            f"📁 Категорий: {len(CATEGORIES)}"
        )
        keyboard = [[InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]]
        if user_id in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="main_admin")])
        await query.edit_message_text(about_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return MAIN_MENU
    
    elif action == "main_admin":
        if user_id not in ADMIN_IDS:
            await query.answer("⛔ Доступ запрещен", show_alert=True)
            return MAIN_MENU
        await query.edit_message_text("⚙️ <b>Админ-панель</b>", reply_markup=get_admin_menu(), parse_mode="HTML")
        return ADMIN_MENU
    
    return MAIN_MENU

async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    favorites = FAVORITES_DB.get(user_id, [])
    
    if not favorites:
        await query.edit_message_text(
            "📭 <b>Избранное пусто</b>\n\n"
            "Добавляйте аналоги в избранное после поиска кнопкой «⭐ В избранное»",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]]),
            parse_mode="HTML"
        )
        return
    
    text = "⭐ <b>Избранное</b>\n\n"
    for i, item in enumerate(favorites, 1):
        text += f"{i}. <b>{item['les_name']}</b> → <b>{item['stavros_name']}\n"
        if item.get('les_link'):
            text += f"   🔗 Les-WM: <a href='{item['les_link']}'>Ссылка</a>\n"
        if item.get('stavros_link'):
            text += f"   🔗 Stavros: <a href='{item['stavros_link']}'>Ссылка</a>\n"
        text += "\n"
    
    await query.edit_message_text(
        text,
        reply_markup=get_favorites_keyboard(query.from_user.id),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

async def favorite_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if query.data == "clear_favorites":
        FAVORITES_DB[user_id] = []
        save_favorites(FAVORITES_DB)
        await query.edit_message_text(
            "🗑️ Избранное очищено",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]])
        )
        return MAIN_MENU
    
    if query.data.startswith("fav_"):
        try:
            index = int(query.data.replace("fav_", ""))
            favorites = FAVORITES_DB.get(user_id, [])
            if 0 <= index < len(favorites):
                item = favorites[index]
                text = f"📌 <b>{item['les_name']}</b> → <b>{item['stavros_name']}</b>\n\n"
                if item.get('les_link'):
                    text += f"🔗 Les-WM: <a href='{item['les_link']}'>Ссылка</a>\n"
                if item.get('stavros_link'):
                    text += f"🔗 Stavros: <a href='{item['stavros_link']}'>Ссылка</a>\n"
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⭐ Вернуться в избранное", callback_data="main_favorites")],
                        [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
                    ]),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
        except:
            pass
    return MAIN_MENU

async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data["category"] = category
    context.user_data["global_search"] = False
    await query.edit_message_text(
        f"📂 Категория: <b>{category}</b>\n\n"
        f"Введите название товара для поиска:",
        parse_mode="HTML"
    )
    return SEARCH

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text
    category = context.user_data.get("category")
    global_search = context.user_data.get("global_search", False)
    
    # Если глобальный поиск
    if global_search or not category:
        results = search_all(query_text)
        reply = format_all_results(results, query_text)
        
        # Сохраняем результаты для избранного
        if results:
            context.user_data["last_results"] = [item for _, item in results]
        
        await update.message.reply_text(
            reply,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_after_search_keyboard()
        )
        return SEARCH
    
    # Поиск в категории
    results = search_analogies(category, query_text)
    reply = format_analogies(results, category, query_text)
    
    # Сохраняем результаты для избранного
    if results:
        context.user_data["last_results"] = results
    
    await update.message.reply_text(
        reply,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_after_search_keyboard()
    )
    return SEARCH

async def add_to_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    last_results = context.user_data.get("last_results", [])
    
    if not last_results:
        await query.edit_message_text(
            "⚠️ Сначала найдите аналог",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]])
        )
        return MAIN_MENU
    
    if user_id not in FAVORITES_DB:
        FAVORITES_DB[user_id] = []
    
    # Добавляем первый найденный аналог
    item = last_results[0]
    # Проверяем, есть ли уже
    existing = False
    for fav in FAVORITES_DB[user_id]:
        if fav['les_name'] == item['les_name'] and fav['stavros_name'] == item['stavros_name']:
            existing = True
            break
    
    if not existing:
        FAVORITES_DB[user_id].append(item)
        save_favorites(FAVORITES_DB)
        await query.edit_message_text(
            f"⭐ Добавлено в избранное:\n<b>{item['les_name']}</b> → <b>{item['stavros_name']}</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Моё избранное", callback_data="main_favorites")],
                [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
            ]),
            parse_mode="HTML"
        )
    else:
        await query.edit_message_text(
            "ℹ️ Уже есть в избранном",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Моё избранное", callback_data="main_favorites")],
                [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
            ])
        )
    return MAIN_MENU

#  АДМИН ФУНКЦИИ
async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    user_id = query.from_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("⛔ Доступ запрещен", show_alert=True)
        return MAIN_MENU
    
    if action == "main_menu":
        await query.edit_message_text("🏠 <b>Главное меню</b>", reply_markup=get_main_menu(), parse_mode="HTML")
        return MAIN_MENU
    
    elif action == "admin_add":
        await query.edit_message_text(
            "📝 <b>Добавление нового аналога</b>\n\n"
            "Введите данные в формате:\n"
            "<code>Категория | Название Les-WM | Ссылка Les-WM | Название Stavros | Ссылка Stavros</code>\n\n"
            "Пример:\n"
            "<code>Ручки | Новая ручка | https://les-wm.ru/... | Stavros-001 | https://stavros.ru/...</code>\n\n"
            "Для отмены нажмите кнопку ниже:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="HTML"
        )
        return ADD_ANALOG
    
    elif action == "admin_delete":
        await show_delete_menu(update, context)
        return DELETE_ANALOG
    
    elif action == "admin_edit":
        await show_edit_menu(update, context)
        return EDIT_ANALOG
    
    elif action == "admin_stats":
        await show_stats(update, context)
        return ADMIN_MENU
    
    return ADMIN_MENU

async def show_delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = []
    for category in CATEGORIES:
        count = len(ANALOGIES_DB.get(category, []))
        keyboard.append([InlineKeyboardButton(
            f"📁 {category} ({count})",
            callback_data=f"del_cat_{category}"
        )])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_admin")])
    await query.edit_message_text(
        "🗑️ <b>Выберите категорию для удаления аналога</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def show_delete_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    category = query.data.replace("del_cat_", "")
    context.user_data["delete_category"] = category
    
    items = ANALOGIES_DB.get(category, [])
    keyboard = []
    for i, item in enumerate(items[:20]):
        keyboard.append([InlineKeyboardButton(
            f"{i+1}. {item['les_name']} → {item['stavros_name']}",
            callback_data=f"del_item_{i}"
        )])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_delete")])
    await query.edit_message_text(
        f"🗑️ <b>Выберите аналог для удаления</b>\nКатегория: {category}\n\n"
        f"Всего: {len(items)} аналогов",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def delete_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        index = int(query.data.replace("del_item_", ""))
        category = context.user_data.get("delete_category")
        
        if category not in ANALOGIES_DB:
            await query.edit_message_text("❌ Категория не найдена")
            return ADMIN_MENU
        
        items = ANALOGIES_DB[category]
        if 0 <= index < len(items):
            deleted_item = items.pop(index)
            backup_analogies()
            save_analogies(ANALOGIES_DB)
            
            await query.edit_message_text(
                f"✅ Аналог удален:\n"
                f"<b>{deleted_item['les_name']}</b> → <b>{deleted_item['stavros_name']}</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗑️ Удалить ещё", callback_data="admin_delete")],
                    [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
                ]),
                parse_mode="HTML"
            )
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")
    return MAIN_MENU

async def show_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = []
    for category in CATEGORIES:
        count = len(ANALOGIES_DB.get(category, []))
        keyboard.append([InlineKeyboardButton(
            f"📁 {category} ({count})",
            callback_data=f"edit_cat_{category}"
        )])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_admin")])
    await query.edit_message_text(
        "✏️ <b>Выберите категорию для редактирования</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def show_edit_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    category = query.data.replace("edit_cat_", "")
    context.user_data["edit_category"] = category
    
    items = ANALOGIES_DB.get(category, [])
    keyboard = []
    for i, item in enumerate(items[:20]):
        keyboard.append([InlineKeyboardButton(
            f"{i+1}. {item['les_name']} → {item['stavros_name']}",
            callback_data=f"edit_item_{i}"
        )])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_edit")])
    await query.edit_message_text(
        f"✏️ <b>Выберите аналог для редактирования</b>\nКатегория: {category}\n\n"
        f"Всего: {len(items)} аналогов",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def start_edit_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        index = int(query.data.replace("edit_item_", ""))
        category = context.user_data.get("edit_category")
        
        if category not in ANALOGIES_DB:
            await query.edit_message_text("❌ Категория не найдена")
            return ADMIN_MENU
        
        items = ANALOGIES_DB[category]
        if 0 <= index < len(items):
            context.user_data["edit_index"] = index
            item = items[index]
            
            await query.edit_message_text(
                f"✏️ <b>Редактирование аналога</b>\n\n"
                f"Текущие данные:\n"
                f"📌 Les-WM: {item['les_name']}\n"
                f"🔗 Les-WM: {item['les_link']}\n"
                f"📌 Stavros: {item['stavros_name']}\n"
                f"🔗 Stavros: {item['stavros_link']}\n\n"
                f"Введите новые данные в формате:\n"
                f"<code>Название Les-WM | Ссылка Les-WM | Название Stavros | Ссылка Stavros</code>\n\n"
                f"Для отмены нажмите кнопку:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="HTML"
            )
            return EDIT_ANALOG
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")
    return ADMIN_MENU

async def add_analog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        parts = [p.strip() for p in text.split('|')]
        
        if len(parts) != 5:
            await update.message.reply_text(
                "❌ Неверный формат! Нужно 5 полей через |\n"
                "Попробуйте снова или нажмите Отмена",
                reply_markup=get_cancel_keyboard()
            )
            return ADD_ANALOG
        
        category, les_name, les_link, stavros_name, stavros_link = parts
        
        # Проверяем ссылки
        if not les_link.startswith(('http://', 'https://')):
            les_link = f"https://{les_link}"
        if not stavros_link.startswith(('http://', 'https://')):
            stavros_link = f"https://{stavros_link}"
        
        # Добавляем
        if category not in ANALOGIES_DB:
            ANALOGIES_DB[category] = []
            if category not in CATEGORIES:
                CATEGORIES.append(category)
        
        new_item = {
            "les_name": les_name,
            "les_link": les_link,
            "stavros_name": stavros_name,
            "stavros_link": stavros_link
        }
        
        ANALOGIES_DB[category].append(new_item)
        backup_analogies()
        save_analogies(ANALOGIES_DB)
        
        await update.message.reply_text(
            f"✅ Аналог успешно добавлен!\n\n"
            f"📁 Категория: {category}\n"
            f"📌 Les-WM: {les_name}\n"
            f"📌 Stavros: {stavros_name}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Добавить ещё", callback_data="admin_add")],
                [InlineKeyboardButton("⚙️ Админ-панель", callback_data="main_admin")],
                [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
            ])
        )
        return ADMIN_MENU
        
    except Exception as e:
        logger.error(f"Ошибка добавления: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {e}\nПопробуйте снова",
            reply_markup=get_cancel_keyboard()
        )
        return ADD_ANALOG

async def edit_analog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        parts = [p.strip() for p in text.split('|')]
        
        if len(parts) != 4:
            await update.message.reply_text(
                "❌ Неверный формат! Нужно 4 поля через |\n"
                "Попробуйте снова или нажмите Отмена",
                reply_markup=get_cancel_keyboard()
            )
            return EDIT_ANALOG
        
        les_name, les_link, stavros_name, stavros_link = parts
        category = context.user_data.get("edit_category")
        index = context.user_data.get("edit_index")
        
        if category not in ANALOGIES_DB:
            await update.message.reply_text("❌ Категория не найдена")
            return ADMIN_MENU
        
        items = ANALOGIES_DB[category]
        if not (0 <= index < len(items)):
            await update.message.reply_text("❌ Аналог не найден")
            return ADMIN_MENU
        
        # Обновляем
        items[index] = {
            "les_name": les_name,
            "les_link": les_link,
            "stavros_name": stavros_name,
            "stavros_link": stavros_link
        }
        
        backup_analogies()
        save_analogies(ANALOGIES_DB)
        
        await update.message.reply_text(
            f"✅ Аналог успешно обновлен!\n\n"
            f"📌 Les-WM: {les_name}\n"
            f"📌 Stavros: {stavros_name}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Админ-панель", callback_data="main_admin")],
                [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
            ])
        )
        return ADMIN_MENU
        
    except Exception as e:
        logger.error(f"Ошибка редактирования: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {e}",
            reply_markup=get_cancel_keyboard()
        )
        return EDIT_ANALOG

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    total_analogs = sum(len(items) for items in ANALOGIES_DB.values())
    total_users = len(FAVORITES_DB)
    total_favorites = sum(len(favs) for favs in FAVORITES_DB.values())
    
    stats_text = (
        f"📊 <b>Статистика</b>\n\n"
        f"📦 Всего аналогов: <b>{total_analogs}</b>\n"
        f"📁 Категорий: <b>{len(CATEGORIES)}</b>\n"
        f"👥 Пользователей: <b>{total_users}</b>\n"
        f"⭐ Всего в избранном: <b>{total_favorites}</b>\n\n"
        f"📂 <b>По категориям:</b>\n"
    )
    
    for category in CATEGORIES:
        count = len(ANALOGIES_DB.get(category, []))
        stats_text += f"  • {category}: {count}\n"
    
    await query.edit_message_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Админ-панель", callback_data="main_admin")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
        ]),
        parse_mode="HTML"
    )

async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id in ADMIN_IDS:
        await query.edit_message_text(
            "⚙️ <b>Админ-панель</b>",
            reply_markup=get_admin_menu(),
            parse_mode="HTML"
        )
        return ADMIN_MENU
    else:
        await query.edit_message_text(
            "🏠 <b>Главное меню</b>",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
        return MAIN_MENU

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Отменено.", reply_markup=get_main_menu())
    return MAIN_MENU

# === ОСНОВНАЯ ФУНКЦИЯ ===
def main():
    application = Application.builder().token(TOKEN).build()
    
    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_handler, pattern="^main_"),
                CallbackQueryHandler(favorite_click, pattern="^(fav_|clear_favorites)"),
                CallbackQueryHandler(add_to_favorites, pattern="^add_favorite$"),
            ],
            CATEGORY: [
                CallbackQueryHandler(category_selected, pattern="^cat_"),
                CallbackQueryHandler(main_menu_handler, pattern="^main_"),
            ],
            SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search),
                CallbackQueryHandler(main_menu_handler, pattern="^main_"),
                CallbackQueryHandler(category_selected, pattern="^cat_"),
                CallbackQueryHandler(add_to_favorites, pattern="^add_favorite$"),
            ],
            ADMIN_MENU: [
                CallbackQueryHandler(admin_menu_handler, pattern="^(admin_|main_)"),
                CallbackQueryHandler(show_delete_items, pattern="^del_cat_"),
                CallbackQueryHandler(delete_item, pattern="^del_item_"),
                CallbackQueryHandler(show_edit_items, pattern="^edit_cat_"),
                CallbackQueryHandler(start_edit_item, pattern="^edit_item_"),
                CallbackQueryHandler(cancel_action, pattern="^cancel_action$"),
            ],
            ADD_ANALOG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_analog),
                CallbackQueryHandler(cancel_action, pattern="^cancel_action$"),
                CallbackQueryHandler(admin_menu_handler, pattern="^(admin_|main_)"),
            ],
            DELETE_ANALOG: [
                CallbackQueryHandler(show_delete_items, pattern="^del_cat_"),
                CallbackQueryHandler(delete_item, pattern="^del_item_"),
                CallbackQueryHandler(admin_menu_handler, pattern="^(admin_|main_)"),
                CallbackQueryHandler(cancel_action, pattern="^cancel_action$"),
            ],
            EDIT_ANALOG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_analog),
                CallbackQueryHandler(show_edit_items, pattern="^edit_cat_"),
                CallbackQueryHandler(start_edit_item, pattern="^edit_item_"),
                CallbackQueryHandler(cancel_action, pattern="^cancel_action$"),
                CallbackQueryHandler(admin_menu_handler, pattern="^(admin_|main_)"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)]
    )
    application.add_handler(conv_handler)
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    
    # Запуск
    port = int(os.environ.get('PORT', 10000))
    webhook_url = f"https://bot-stavross.onrender.com/{TOKEN}"
    
    print("🚀 Запуск бота...")
    print(f"👤 Ваш ID: 1032384251")
    print(f"📁 Категорий: {len(CATEGORIES)}")
    print(f"📦 Аналогов: {sum(len(items) for items in ANALOGIES_DB.values())}")
    
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,
        webhook_url=webhook_url
    )

if __name__ == '__main__':
    main()