import logging
import os
import time

import requests
import telegram
from dotenv import load_dotenv
from http import HTTPStatus

import exceptions
import settings

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


logging.basicConfig(
    handlers=[logging.StreamHandler()],
    level=logging.INFO,
    format='%(asctime)s, %(levelname)s, %(message)s'
)
logger = logging.getLogger(__name__)


def send_message(bot, message):
    """Отправляет сообщение в чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info('Сообщение в чат отправлено')
    except exceptions.SendMessageFailure:
        logger.error('Возникла ошибка при отправке сообщения')


def get_api_answer(current_timestamp):
    """Делает запрос к конечной точке."""
    timestamp = current_timestamp
    params = {'from_date': timestamp}
    try:
        response = requests.get(
            settings.ENDPOINT, headers=HEADERS, params=params)
    except exceptions.APIResponseStatusCodeException:
        logger.error('Сбой при запросе к endpoint')
    if response.status_code != HTTPStatus.OK:
        message = 'Сбой при запросе к endpoint'
        logger.error(message)
        raise exceptions.APIResponseStatusCodeException(message)
    return response.json()


def check_response(response):
    """Проверяет ответ API."""

    if not isinstance(response, dict):
        message = 'Ответ API не словарь'
        raise TypeError(message)
    if response.get('homeworks')[0] is None:
        message = 'Ошибка доступа по ключу "homeworks"'
        raise KeyError(message)
    if not isinstance(response.get('homeworks'), list):
        message = 'Ответ API не является списком'
        raise TypeError(message)
    if ['homeworks'][0] not in response:
        message = 'В ответе API нет домашней работы'
        raise IndexError(message)
    homework = response.get('homeworks')
    return homework


def parse_status(homework):
    """Извлекает из информации о домашке ее статус."""
    keys = ['status', 'homework_name']
    for key in keys:
        if key not in homework:
            message = f'Ключа {key} нет в ответе API'
            raise KeyError(message)
    homework_status = homework['status']
    if homework_status not in settings.HOMEWORK_STATUSES:
        message = 'Неизвестный статус домашней работы'
        raise KeyError(message)
    homework_name = homework['homework_name']
    verdict = settings.HOMEWORK_STATUSES[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет наличие переменных окружения."""
    return all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, PRACTICUM_TOKEN])


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        message = 'Отсутствует необходимая переменная среды'
        logger.critical(message)
        raise exceptions.MissingRequiredTokenException(message)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time() - settings.WEEK)
    previous_status = None
    previous_error = None

    while True:
        try:
            response = get_api_answer(current_timestamp)
        except exceptions.IncorrectAPIResponseException as e:
            if str(e) != previous_error:
                previous_error = str(e)
                send_message(bot, e)
            logger.error(e)
            time.sleep(settings.RETRY_TIME)
            continue
        try:
            homeworks = check_response(response)
            hw_status = homeworks[0].get('status')
            if hw_status != previous_status:
                previous_status = hw_status
                message = parse_status(homeworks[0])
                send_message(bot, message)
            else:
                logger.debug('Обновления статуса нет')

            time.sleep(settings.RETRY_TIME)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if previous_error != str(error):
                previous_error = str(error)
                send_message(bot, message)
            logger.error(message)
        finally:
            time.sleep(settings.RETRY_TIME)


if __name__ == '__main__':
    main()
