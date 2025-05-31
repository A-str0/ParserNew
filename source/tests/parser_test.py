import sys
sys.path.insert(0, "E:\\Projects\\ParserNew\\source")
# sys.path.append("../")

import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from services.bankrupt_parser_service import BankruptParserService
from handlers.datetime_handler import current_formatted_time
from datetime import *


def current_formatted_time() -> str:
    return datetime.now().strftime("%d%m%Y%H%M%S")


async def test_parse_card():
    # Инициализация сервиса
    parser = BankruptParserService(proxy_config=None)  # Укажи прокси, если нужно
    try:
        # Загрузка страницы
        url = "https://bankrot.fedresurs.ru/bankrupts?regionId=1&isActiveLegalCase=true&offset=0&limit=100"
        page = await parser.load_page(url)

        # Ожидание карточек
        await page.wait_for_selector("app-bankrupt-result-card-company")
        cards = await page.locator("app-bankrupt-result-card-company").all()

        # Тестирование первой карточки
        card = cards[0]
        card_soup = BeautifulSoup(await card.inner_html(), "html.parser")
        result = await parser.parse_card(page, card_soup, card)

        # Вывод результата
        if result:
            parser.logger.info(f"Результат: INN={result['inn']}, Status={result['status']}, URL={result['url']}")
        else:
            parser.logger.error("Парсинг не вернул результат")

        # Сохранение HTML главной страницы для отладки
        with open(f"main_page_{current_formatted_time()}.html", "w", encoding="utf-8") as f:
            f.write(await page.content())

    except Exception as e:
        parser.logger.error(f"Ошибка тестирования: {e}")
    finally:
        if parser.browser:
            await parser.browser.close()

asyncio.run(test_parse_card())