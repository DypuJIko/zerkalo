import os
import logging
import asyncio
import aiohttp
import hashlib
from watchdog.observers import Observer
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import FSInputFile
from datetime import datetime, timedelta
from aiogram.utils.keyboard import InlineKeyboardBuilder
from handlers import router
from database import init_db, add_or_update_user, get_user_folder, add_file_id, get_file_id
from utils import (API_TOKEN,
                   PhotoHandler,                    
                   upload_file, 
                   convert_photo,
                   create_and_publish_folder,
                   retry_on_failure                                    
                )


bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Инициализация базы данных
init_db()


# Задаем глобальные переменные
timeout = 600 # таймаут для завершения сессии
user_in_session = None
general_folder = 'C:\photo'
clients_folder = 'C:\clients'



# Обработчик нажатия кнопок
@dp.callback_query(F.data.startswith('start_session_'))
async def callback_start_session(query: types.CallbackQuery):
    global user_in_session
    user_id = query.from_user.id
    phone_number = query.data.split('_')[2]
    folder = os.path.join(clients_folder, phone_number)

    if user_in_session is None:
        user_in_session = user_id
        add_or_update_user(user_id, phone_number, folder)
        os.makedirs(folder, exist_ok=True)
        asyncio.create_task(start_watchdog(phone_number, general_folder, clients_folder))       

        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Получить фото в чате", callback_data=f'get_photos_{phone_number}')
        keyboard.button(text="Загрузить фото в облако", callback_data=f'upload_to_cloud_{phone_number}')
        keyboard.adjust(1)        
        await query.message.edit_text(
            "Пожалуйста, фотографируйтесь",
            reply_markup=keyboard.as_markup()
        )                
    else:
        await query.message.edit_text("Бот занят, попробуйте позже.")



# Обработчик фотографий в Ч/Б
@dp.callback_query(F.data.startswith('get_bw_'))
async def callback_get_bw_photo(query: types.CallbackQuery):
    data = query.data.split('_')    
    message_id = query.message.message_id
    file_id = get_file_id(data[2])
    origin_name = query.message.document.file_name.split('.')        

    # Обновляем сообщение, удаляя кнопку
    await bot.edit_message_reply_markup(chat_id=query.message.chat.id, 
                                        message_id=message_id, 
                                        reply_markup=None
                                    )
    # Получаем файл по id
    file = await retry_on_failure(bot.get_file, file_id)
    file_path = file.file_path

    # Загружаем файл
    downloaded_file = await retry_on_failure(bot.download_file, file_path)

    bw_image_path = convert_photo(downloaded_file, origin_name[0])

    # Отправляем черно-белое изображение
    bw_file = FSInputFile(bw_image_path)
    await retry_on_failure(bot.send_document, chat_id=query.message.chat.id, document=bw_file)

    # Удаляем временный файл
    os.remove(bw_image_path)
    
    await query.answer()



# Обработчик отправки фотографий в чат
@dp.callback_query(F.data.startswith('get_photos_'))
async def callback_get_photos(query: types.CallbackQuery,
                              check_interval: int = 10, 
                              max_wait_time: int = timeout):
    
    user_id = query.from_user.id
    user_data = get_user_folder(user_id)
    folder = user_data[1] if user_data else ''

    logging.info(f"User ID: {user_id}, Folder: {folder}")
    
    if not folder:        
        await query.message.edit_text("На данный момент ваших фотографий нет.")
        return
   
    # Обновление сообщения для удаления клавиатуры
    await query.message.edit_text("После загрузки всех фотографий вам придет сообщение")

    elapsed_time = 0  # Время, прошедшее с последней проверки, когда были файлы

    while elapsed_time <= max_wait_time:
        try:
            files = os.listdir(folder)
            logging.info(f"Files found чат: {files}") 
            if files:
                for filename in files:
                    file_path = os.path.join(folder, filename)
                    if os.path.isfile(file_path):
                        input_file = FSInputFile(file_path)

                        message = await retry_on_failure(bot.send_document, chat_id=query.message.chat.id, document=input_file)
                        
                        # Использование хеширования для создания callback_data
                        file_id_hash = hashlib.md5(message.document.file_id.encode()).hexdigest()

                        # Сохранение связи хеш -> file_id
                        add_file_id(file_id_hash, message.document.file_id)

                        keyboard = InlineKeyboardBuilder()
                        keyboard.button(text="Получить Ч/Б фото", callback_data=f'get_bw_{file_id_hash}')                    
                        keyboard.adjust(1)

                        # Добавляем клавиатуру к сообщению
                        await bot.edit_message_reply_markup(chat_id=query.message.chat.id, 
                                                            message_id=message.message_id, 
                                                            reply_markup=keyboard.as_markup()
                                                        )
                        os.remove(file_path)  # Удаляем отправленный файл
                        elapsed_time = 0  # Сбрасываем счетчик времени
            else:
                await asyncio.sleep(check_interval)
                elapsed_time += check_interval
                logging.info(f"Elapsed time чат: {elapsed_time}")
                if elapsed_time >= max_wait_time:
                    await query.message.answer("Все фотографии отправлены.")
                    await asyncio.sleep(1)
                    await query.message.answer("Мы будем рады, если вы поделитесь с нами вашими фотографиями для публикации их в группе. Для этого можно отправить фото в этот чат")               
                    break     
        except Exception as e:
            logging.error(f"Ошибка при отправке фото в чат: {e}")
            break 



# Обработчик отправки фотографий в облако
@dp.callback_query(F.data.startswith('upload_to_cloud_'))
async def callback_upload_to_cloud(query: types.CallbackQuery,
                                   check_interval: int = 10, 
                                   max_wait_time: int = timeout):
    
    user_id = query.from_user.id
    user_data = get_user_folder(user_id)
    phone_number = user_data[0] if user_data else ''
    folder = user_data[1] if user_data else ''

    logging.info(f"User ID: {user_id}, Phone_nimber: {phone_number}, Folder: {folder}")
  
    if not folder:
        await query.message.edit_text("На данный момент ваших фотографий нет.")
        return

    disk_path = f"disk:/{phone_number}"

    # Обновление сообщения для удаления клавиатуры
    await query.message.edit_text("После загрузки фотографий вам придет ссылка")

    async with aiohttp.ClientSession() as session:
        public_link = await retry_on_failure(create_and_publish_folder, session, disk_path)

        elapsed_time = 0  # Время, прошедшее с последней проверки, когда были файлы
        while True:
            try:
                files = os.listdir(folder)
                logging.info(f"Files found облако: {files}")
                if files:
                    for filename in files:
                        file_path = os.path.join(folder, filename)
                        if os.path.isfile(file_path):                        
                            await retry_on_failure(upload_file, session, file_path, f"{disk_path}/{filename}")
                            os.remove(file_path)
                            elapsed_time = 0  # Сбрасываем счетчик времени
                else:
                    await asyncio.sleep(check_interval)
                    elapsed_time += check_interval
                    logging.info(f"Elapsed time облако: {elapsed_time}")
                    if elapsed_time >= max_wait_time:               
                        await query.message.edit_text(f"Фотографии загружены в облако. Ссылка для скачивания: {public_link}")
                        await asyncio.sleep(1)
                        await query.message.answer("Мы будем рады, если вы поделитесь с нами вашими фотографиями для публикации их в группе. Для этого можно отправить фото в этот чат")
                        break
            except Exception as e:
                logging.error(f"Ошибка при загрузке в облако: {e}")
                break        
       


# Запуск мониторинга основной папки с фотографиями
async def start_watchdog(phone_number, photo_folder, clients_folder):
    global user_in_session    
    event_handler = PhotoHandler(phone_number, clients_folder)
    observer = Observer()
    observer.schedule(event_handler, path=photo_folder, recursive=False)
    observer.start()

    try:
        while user_in_session:
            await asyncio.sleep(10)           
            if datetime.now() - event_handler.last_modified > timedelta(seconds=timeout):
                user_in_session = None
                logging.info("Нет изменений в течение 10 минут. Остановка мониторинга.")
                break
    finally:
        observer.stop()
        observer.join()



async def main():
    dp.include_router(router)
    await dp.start_polling(bot)



if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename='app.log',
        filemode='w'
    )
    try:
        asyncio.run(main())
    except Exception as err:
        logging.error(f"Ошибка: {err}")