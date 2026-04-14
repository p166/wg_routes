#!/usr/bin/env python3
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID
from dns_resolver import resolve_domain, format_resolution_result
from ssh_handler import SSHHandler

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States for FSM
class ResolutionState(StatesGroup):
    waiting_for_domain = State()

# Initialize bot and dispatcher
bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Store pending IPs for batch operations
user_pending_ips = {}


def check_admin(user_id: int) -> bool:
    """Check if user is admin."""
    if ADMIN_USER_ID is None:
        return True  # No admin restriction if not configured
    return user_id == ADMIN_USER_ID


async def start_handler(message: types.Message):
    """Handle /start command."""
    if not check_admin(message.from_user.id):
        await message.reply("❌ У вас нет доступа к этому боту")
        return
    
    await message.reply(
        "🤖 <b>WireGuard Routes Manager Bot</b>\n\n"
        "Команды:\n"
        "• <code>/add domain.com</code> или просто напишите домен - резолвить домен\n"
        "• <code>/restart-wg</code> - перезапустить туннель (применить изменения)\n"
        "• <code>/status</code> - показать текущий список IP\n"
        "• <code>/help</code> - справка\n\n"
        "📝 <b>Как использовать:</b>\n"
        "1. Отправьте домены которые нужно добавить\n"
        "2. Бот резолвит домены и покажет найденные IP\n"
        "3. IP автоматически добавляются в wg_destinations.txt\n"
        "4. Когда все домены добавлены, выполните /restart-wg",
        parse_mode="HTML"
    )


async def help_handler(message: types.Message):
    """Handle /help command."""
    if not check_admin(message.from_user.id):
        return
    
    await message.reply(
        "📚 <b>Справка по командам:</b>\n\n"
        "<b>/add domain.com</b> или просто текст\n"
        "  Резолвит домен и добавляет IP в wg_destinations.txt\n\n"
        "<b>/restart-wg</b>\n"
        "  Применяет AllowedIPs и перезапускает туннель\n"
        "  (выполняет update_allowedips_awg.sh на S1)\n\n"
        "<b>/status</b>\n"
        "  Показывает текущий список IP из wg_destinations.txt\n\n"
        "<b>/clear</b>\n"
        "  Отменяет все незаиерованные домены этой сессии\n\n"
        "⚠️ <b>Важно:</b>\n"
        "• Домены резолвятся локально (на S2)\n"
        "• IP добавляются через SSH на S1\n"
        "• Изменения не применяются до /restart-wg\n"
        "• Дедупликация IP выполняется на S1",
        parse_mode="HTML"
    )


async def add_domain_handler(message: types.Message, state: FSMContext):
    """Handle /add command or plain text."""
    if not check_admin(message.from_user.id):
        return
    
    # Extract domain from command or plain text
    if message.text.startswith("/add"):
        domain = message.text[4:].strip()
    else:
        domain = message.text.strip()
    
    if not domain:
        await message.reply("❌ Укажите домен")
        return
    
    # Send "typing" indicator
    await bot.send_chat_action(message.chat.id, "typing")
    
    # Resolve domain
    try:
        ipv4_list, ipv6_list, errors = await resolve_domain(domain)
        
        if not ipv4_list and not ipv6_list:
            error_msg = errors[0] if errors else "домен не зарезолвлен"
            await message.reply(f"❌ <b>{domain}</b>\n{error_msg}", parse_mode="HTML")
            return
        
        # Format and send result
        result_msg = format_resolution_result(domain, ipv4_list, ipv6_list)
        await message.reply(result_msg, parse_mode="HTML")
        
        # Add IPs to S1
        await bot.send_chat_action(message.chat.id, "typing")
        ssh = SSHHandler()
        success, ssh_msg = await asyncio.to_thread(ssh.add_ips, ipv4_list, ipv6_list)
        await message.reply(ssh_msg, parse_mode="HTML")
        
    except Exception as e:
        await message.reply(f"❌ Ошибка резолва: {str(e)}", parse_mode="HTML")
        logger.error(f"Resolution error: {e}")


async def restart_handler(message: types.Message):
    """Handle /restart command."""
    if not check_admin(message.from_user.id):
        return
    
    # Confirmation
    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Да, перезапустить", callback_data="restart_confirm"),
            types.InlineKeyboardButton(text="❌ Отмена", callback_data="restart_cancel")
        ]
    ])
    
    await message.reply(
        "⚠️ <b>Перезапуск туннеля</b>\n"
        "Это разорвет текущие соединения через WG.\n"
        "Вы уверены?",
        reply_markup=markup,
        parse_mode="HTML"
    )


async def restart_confirm_callback(callback_query: types.CallbackQuery):
    """Confirm restart."""
    await callback_query.answer()
    
    await callback_query.message.edit_text("⏳ Перезапуск туннеля...")
    
    try:
        ssh = SSHHandler()
        success, msg = await asyncio.to_thread(ssh.restart_tunnel)
        
        if success:
            await callback_query.message.edit_text(msg, parse_mode="HTML")
        else:
            await callback_query.message.edit_text(msg, parse_mode="HTML")
    
    except Exception as e:
        await callback_query.message.edit_text(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        logger.error(f"Restart error: {e}")


async def restart_cancel_callback(callback_query: types.CallbackQuery):
    """Cancel restart."""
    await callback_query.answer()
    await callback_query.message.edit_text("❌ Перезапуск отменен")


async def status_handler(message: types.Message):
    """Handle /status command."""
    if not check_admin(message.from_user.id):
        return
    
    await bot.send_chat_action(message.chat.id, "typing")
    
    try:
        ssh = SSHHandler()
        success, msg = await asyncio.to_thread(ssh.get_destinations)
        await message.reply(msg, parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        logger.error(f"Status error: {e}")


async def clear_handler(message: types.Message):
    """Handle /clear command."""
    if not check_admin(message.from_user.id):
        return
    
    if message.from_user.id in user_pending_ips:
        del user_pending_ips[message.from_user.id]
    
    await message.reply("✅ Кэш очищен")


# Register handlers
async def main():
    """Main bot function."""
    
    # Register commands
    dp.message.register(start_handler, Command("start"))
    dp.message.register(help_handler, Command("help"))
    dp.message.register(status_handler, Command("status"))
    dp.message.register(clear_handler, Command("clear"))
    dp.message.register(restart_handler, Command("restart-wg"))
    dp.message.register(add_domain_handler, ~Command("restart-wg"))
    
    # Register callback queries
    dp.callback_query.register(restart_confirm_callback, F.data == "restart_confirm")
    dp.callback_query.register(restart_cancel_callback, F.data == "restart_cancel")
    
    # Start polling
    try:
        logger.info("Bot started")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
