from aiogram import Router, types, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from yclients_conn import get_client_phone_numbers
from utils import normalize_phone_number 
                   

router = Router()
FORWARD_TO_USER_ID = 7375092623


# Обработчик команды /info
@router.message(Command("info"))
async def cmd_info(message: Message):
    user = message.from_user
    chat_id = message.chat.id  # Получаем chat_id из сообщения
    user_info = (
        f"Имя: {user.first_name}\n"
        f"Фамилия: {user.last_name}\n"
        f"Юзернейм: @{user.username}\n"
        f"ID: {user.id}\n"
        f"Chat_id: {chat_id}\n"
        f"Язык: {user.language_code}"
    )
    await message.answer(user_info)



# Обработчик команды /start
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Необходима авторизация. Введите номер телефона, по которому производилась запись на сайте."
    )



# Обработчик отправки номера телефона
@router.message(F.text)
async def handle_phone_number(message: types.Message):    
    phone_number = normalize_phone_number(message.text)
    if not phone_number:
        await message.answer("Неверный формат номера. Попробуйте еще раз.")
        return
    
    clients = await get_client_phone_numbers()

    if phone_number in clients:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Начать фотосессию", callback_data=f'start_session_{phone_number}')
        keyboard.adjust(1)
        await message.answer(
            "Авторизация пройдена, можно начать фотосессию",
            reply_markup=keyboard.as_markup()
        )
    else:
        await message.answer("Авторизация не пройдена, попробуйте еще раз. Или зарегистрируйтесь по ссылке: https://n1148308.yclients.com")    



# Обработчик отправки документов
@router.message(F.document)
async def handle_document(message: Message):    
    await message.bot.send_document(chat_id=FORWARD_TO_USER_ID, 
                                    document=message.document.file_id, 
                                    caption=message.caption
                                )


# Обработчик отправки фотографий
@router.message(F.photo)
async def handle_photo(message: Message):    
    await message.bot.send_photo(chat_id=FORWARD_TO_USER_ID, 
                                 photo=message.photo[-1].file_id, 
                                 caption=message.caption
                            )
    