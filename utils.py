import os
import time
import logging
import shutil
import aiofiles
import asyncio
import aiohttp
import numpy as np
from PIL import Image, ExifTags
from watchdog.events import FileSystemEventHandler
from datetime import datetime
from dotenv import load_dotenv


load_dotenv()


API_TOKEN = os.getenv('BOT_TOKEN')
TOKEN = os.getenv("YANDEX")


# Функция для обнаружения темных фотографий
def check_photo(image_path: str, threshold: int=0) -> bool:
    image = Image.open(image_path).convert('L')  # Преобразование в оттенки серого
    pixels = np.array(image)
    brightness = np.mean(pixels)    
    return brightness > threshold



# Функция для повторной попытки выполнения
async def retry_on_failure(func, *args, **kwargs):
    retries = 5
    delay = 2
    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except (aiohttp.ClientOSError, asyncio.CancelledError, ConnectionResetError) as e:
            logging.error(f"Ошибка сети: {e}. новая попытка {delay} секунд...")
            await asyncio.sleep(delay)
            delay *= 2  # Увеличиваем задержку экспоненциально
    logging.error("Максимальное количество попыток.")
    raise Exception("Максимальное количество попыток")



def convert_photo(file, file_id):
    # Преобразуем изображение в черно-белое
    image = Image.open(file)

    # Исправляем ориентацию изображения
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        exif = image._getexif()
        if exif is not None:
            orientation = exif.get(orientation)
            if orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        # Если нет EXIF данных или что-то пошло не так, продолжаем без изменения ориентации
        pass

    bw_image = image.convert('L')
    
    # Сохраняем черно-белое изображение во временный файл с высоким качеством
    bw_image_path = f"bw_{file_id}.jpg"
    bw_image.save(bw_image_path, quality=95)

    return bw_image_path



# Преобразование номера телефона
def normalize_phone_number(phone_number):
    if phone_number.startswith('8'):
        return '+7' + phone_number[1:]
    elif phone_number.startswith('+7'):
        return phone_number
    return None



class PhotoHandler(FileSystemEventHandler):
    def __init__(self,  phone_number, clients_folder):
        self.folder = os.path.join(clients_folder, phone_number)
        self.last_modified = datetime.now()
        
   
    def on_created(self, event):        
        if not event.is_directory:                             
            if event.src_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                time.sleep(1)
                if check_photo(event.src_path):
                    self.move_file_with_retry(event.src_path, self.folder)
                    self.last_modified = datetime.now()           
                else:
                    os.remove(event.src_path)    


    def on_moved(self, event):        
        if not event.is_directory:            
            if event.dest_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                if check_photo(event.dest_path):           
                    self.move_file_with_retry(event.dest_path, self.folder)
                    self.last_modified = datetime.now()
                else:
                    os.remove(event.dest_path)    
                    

    def move_file_with_retry(self, src, dst_folder, retries=5, delay=1):
        dst = os.path.join(dst_folder, os.path.basename(src))
        for _ in range(retries):
            try:
                shutil.move(src, dst)
                break
            except PermissionError:
                time.sleep(delay)
        else:
            logging.error(f"Не удалось переместить файл {src} в {dst} после {retries} попыток")


# Функция для создания папки и получения ссылки на яндекс диске
async def create_and_publish_folder(session, disk_path):
    encoded_disk_path = disk_path.replace("+", "%2B")
    url = f"https://cloud-api.yandex.net/v1/disk/resources?path={encoded_disk_path}"
    headers = {"Authorization": f"OAuth {TOKEN}"}
    public_url = None

    # Создание папки
    async with session.put(url, headers=headers) as resp:                  
        if resp.status == 201:
            logging.info(f"Папка {disk_path} создана.")
        elif resp.status == 409:
            logging.info(f"Папка {disk_path} уже существует.")
        else:
            error = await resp.json()
            logging.error(f"Ошибка при создании папки на Яндекс.Диске: {error}")
            return public_url
    
    # Сделать папку публичной
    url = f"https://cloud-api.yandex.net/v1/disk/resources/publish?path={encoded_disk_path}"
    async with session.put(url, headers=headers) as resp:
        if resp.status == 200:
            logging.info(f"Папка {encoded_disk_path} теперь публичная.")

            # Получение публичной ссылки
            url = f"https://cloud-api.yandex.net/v1/disk/resources?path={encoded_disk_path}"
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    public_url = data.get('public_url')            
                else:
                    error = await resp.json()
                    logging.error(f"Ошибка при получении информации о ресурсе на Яндекс.Диске: {error}")
        else:
            error = await resp.json()
            logging.error(f"Ошибка при открытии доступа к папке на Яндекс.Диске: {error}")

    return public_url 


# Функция для загрузки файлов на яндекс диск
async def upload_file(session, file_path, yandex_disk_path):
    encoded_yandex_disk_path = yandex_disk_path.replace("+", "%2B")
    url = f"https://cloud-api.yandex.net/v1/disk/resources/upload?path={encoded_yandex_disk_path}"
    headers = {"Authorization": f"OAuth {TOKEN}"}
    async with session.get(url, headers=headers) as resp:
        if resp.status == 200:
            upload_url = (await resp.json())['href']
            async with aiofiles.open(file_path, 'rb') as f:
                async with session.put(upload_url, data=await f.read()) as upload_resp:
                    if upload_resp.status == 201:
                        logging.info(f"Файл {file_path} успешно загружен на Яндекс.Диск.")
                    else:
                        error = await upload_resp.json()
                        logging.error(f"Ошибка при загрузке файла на Яндекс.Диск: {error}")
        else:
            error = await resp.json()
            logging.error(f"Ошибка при получении ссылки загрузки на Яндекс.Диск: {error}")