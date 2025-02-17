import httpx
import logging
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

    # Заголовки запроса
    headers = {
        'Authorization': f'Bearer {PARTNER_TOKEN}, {USER_TOKEN}',
        'Accept': 'application/vnd.api.v2+json',
        'Content-Type': 'application/json'
    }

    page = 1
    page_size = 200
    numbers_list = []
    
    async with httpx.AsyncClient() as client:
        while True:            
            # Тело запроса
            body = {    
                "page": page,
                "page_size": page_size,
                "fields": [
                    "id",
                    "name",
                    "phone"            
                ]    
            }
            
            try: 
                # Отправка запроса
                response = await client.post(url, headers=headers, json=body)
                
                # Проверка статуса ответа
                if response.status_code != 200:
                    logging.error(f"Ошибка на странице {page}: {response.status_code}, {response.text}")
                    break
                
                clients_data_list = response.json()
                    
                # Если нет результатов, прекращаем цикл
                if not clients_data_list['data']:
                    break
                                    
                phone_numbers = [client['phone'] for client in clients_data_list['data']] 
                # phone_numbers = phone_numbers = [{'phone': client['phone'], 'record_date': client['record_date']} # Для словаря{'Номер_телефона':'Дата_записи'}
                #                                  for client in clients_data_list['data']]
                numbers_list.extend(phone_numbers)
                
                # Переходим к следующей странице
                page += 1 

            except Exception as e:
                logging.error(f"Ошибка при запросе страницы {page}: {str(e)}")
                break
                            
    return numbers_list   
        