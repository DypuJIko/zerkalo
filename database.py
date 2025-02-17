import sqlite3
from contextlib import contextmanager


# Контекстный менеджер для управления подключением к базе данных
@contextmanager
def connect_db(db_name='database.db'):
    conn = sqlite3.connect(db_name)
    try:
        yield conn
    finally:
        conn.close()


# Инициализация базы данных: создание таблиц
def init_db():
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users_folders (
            user_id INTEGER PRIMARY KEY,
            phone_number TEXT,
            folder TEXT
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS file_id_map (
            file_id_hash TEXT PRIMARY KEY,
            file_id TEXT
        )''')
        conn.commit()


# Функция для добавления или обновления данных о пользователе
def add_or_update_user(user_id, phone_number, folder):
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''REPLACE INTO users_folders (user_id, phone_number, folder) VALUES (?, ?, ?)''',
                       (user_id, phone_number, folder))
        conn.commit()


# Функция для получения данных о пользователе
def get_user_folder(user_id):
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT phone_number, folder FROM users_folders WHERE user_id = ?', (user_id,))
        return cursor.fetchone()


# Функция для добавления file_id
def add_file_id(file_id_hash, file_id):
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''REPLACE INTO file_id_map (file_id_hash, file_id) VALUES (?, ?)''', (file_id_hash, file_id))
        conn.commit()


# Функция для получения file_id по хешу
def get_file_id(file_id_hash):
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT file_id FROM file_id_map WHERE file_id_hash = ?', (file_id_hash,))
        result = cursor.fetchone()
        return result[0] if result else None
    