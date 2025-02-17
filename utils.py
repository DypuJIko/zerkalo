import os
import time
import logging
import shutil
import aiofiles
import asyncio
import random
from PIL import Image, ImageOps
from PIL.ExifTags import TAGS
from watchdog.events import FileSystemEventHandler
from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip, vfx
from datetime import datetime
from dotenv import load_dotenv


load_dotenv()


API_TOKEN = os.getenv('BOT_TOKEN')
TOKEN = os.getenv("YANDEX")


def create_videos(photo_dir: str, audio_dir: str):
    try:    
        # Создаем список треков и выбираем случайный
        audios = [f for f in os.listdir(audio_dir) if f.lower().endswith('.mp3')]
        audio_file = os.path.join(audio_dir, random.choice(audios))  
        logging.info(audios)
        logging.info(audio_file)
    except Exception as er:
        logging.error(f"Ошибка получения аудио для клипа: {er}")

    try:
        # Создаем список фотографий
        photos = [f for f in os.listdir(photo_dir) if f.lower().endswith('.jpg')]          

        # Создаем ImageClip после корректировки ориентации и размера 
        clips = [ImageClip(os.path.join(photo_dir, filename)).set_duration(0.5) for filename in photos]
    except Exception as err:
        logging.error(f"Ошибка получения фото для клипа: {err}")

    # Проверяем, что есть хотя бы один клип
    if clips:
        try:                
            # Объединяем клипы в одно слайд-шоу
            final_clip = concatenate_videoclips(clips, method='compose')

            # Загрузка и наложение аудиофайла
            audio = AudioFileClip(audio_file)
            
            # Зацикливание аудио, если оно короче финального клипа
            audio = audio.fx(vfx.loop, duration=final_clip.duration)
            final_clip = final_clip.set_audio(audio)

            # Сохранение итогового видео
            final_clip.write_videofile('C:\slideshow\slideshow.mp4', fps=30, codec='libx264', audio_codec='aac')
            final_clip.close()

            # Проверка размера файла
            file_size = os.path.getsize('C:\slideshow\slideshow.mp4') / (1024 * 1024)  # Размер в МБ
            logging.info(f"Размер видеофайла: {file_size:.2f} МБ")

            # Если размер больше 50 МБ, уменьшаем качество и сохраняем снова
            if file_size > 50:
                logging.info("Файл больше 50 МБ, понижаем качество...")
                output_path_compressed = 'C:\\slideshow\\slideshow_compressed.mp4'
                final_clip.write_videofile(output_path_compressed, fps=30, codec='libx264', audio_codec='aac', bitrate="500k")
                logging.info(f"Видео сохранено с пониженным качеством: {os.path.getsize(output_path_compressed) / (1024 * 1024)}")    
                os.remove('C:\slideshow\slideshow.mp4')   

            # Удаление всех фотографий после создания слайдшоу
            for photo in photos:
                os.remove(os.path.join(photo_dir, photo))
        except Exception as e:
            logging.error(f"Ошибка при создании финального клипа: {e}")
    else:
        logging.error("Нет доступных клипов для создания видео.")
   
    return 'C:\slideshow\slideshow.mp4'



def resize_photo(image_path: str, save_dir: str, max_width=1920, max_height=1080):    
    try:
        # Открываем изображение и корректируем его ориентацию
        with Image.open(image_path) as img:
            image = ImageOps.exif_transpose(img)  # Автоматическая корректировка ориентации
           
            # Изменяем размер изображения, если оно превышает максимальное разрешение
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            # Сохраняем исправленное изображение
            save_path = os.path.join(save_dir, image_path.split('\\')[-1])                       
            image.save(save_path, format='JPEG')  

    except Exception as e:
        logging.error(f"Ошибка при обработке resize_photo {image_path}: {e}")



# Функция для обнаружения темных фотографий
def check_photo(image_path: str) -> bool:
    try:
        img = Image.open(image_path)
        exif_data = img._getexif()
        
        if not exif_data:            
            logging.warning(f"Нет метаданных у фото {image_path}")
            # return True  # Нет EXIF-данных

        for tag, value in exif_data.items():            
            tag_name = TAGS.get(tag, tag)            
            if tag_name == "Flash":
                logging.info(f"Параметры вспышки {tag_name} - {value}")
                if value == 9:
                    return True # Означает, что вспышка была 
                else:
                    return False 
            
    except Exception as e:
        logging.error(f"Ошибка обработки в check_photo {image_path}: {e}")



# Функция для повторной попытки выполнения
async def retry_on_failure(func, *args, **kwargs):
    retries = 5
    delay = 2
    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logging.error(f"Ошибка: {e}. новая попытка {delay} секунд...")
            await asyncio.sleep(delay)
            delay *= 2  # Увеличиваем задержку экспоненциально
    logging.error(f"Максимальное количество попыток {func}.")
    raise Exception("Максимальное количество попыток")



def convert_photo(file, file_id):
    # Открываем изображение и автоматически исправляем ориентацию
    image = ImageOps.exif_transpose(Image.open(file))

    # Преобразуем изображение в черно-белое
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
            