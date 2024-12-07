import httpx
import os
from dotenv import load_dotenv

load_dotenv()


# Замените эти переменные на свои реальные данные
PARTNER_TOKEN = os.getenv('PARTNER_TOKEN')
CID = os.getenv('COMPANY_ID')
PID = os.getenv('PARTNER_ID')
USER_TOKEN = os.getenv('USER_TOKEN')


async def get_client_phone_numbers():
    # Адрес запроса
    url = f'https://api.yclients.com/api/v1/company/{CID}/clients/search'

    # Тело запроса
    body = {    
        "page": 1,
        "page_size": 1000,
        "fields": [
            "id",
            "name",
            "phone"            
        ]    
    }

    # Заголовки запроса
    headers = {
        'Authorization': f'Bearer {PARTNER_TOKEN}, {USER_TOKEN}',
        'Accept': 'application/vnd.api.v2+json',
        'Content-Type': 'application/json'
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=body)
        
        # Проверка статуса ответа
        if response.status_code == 200:
            clients_data_list = response.json()
            phone_numbers = [client['phone'] for client in clients_data_list['data']] # Для списка номеров
            # phone_numbers = phone_numbers = [{'phone': client['phone'], 'record_date': client['record_date']} # Для словаря{'Номер_телефона':'Дата_записи'}
            #                                  for client in clients_data_list['data']]
            return phone_numbers
        else:
            print(f"Ошибка: {response.status_code}, {response.text}")
            return []