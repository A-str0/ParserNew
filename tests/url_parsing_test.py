import logging
from playwright.sync_api import sync_playwright
import requests as rq

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def test_url(url):
    r = rq.get(url)

    r.raise_for_status()

    print(r.text)

    pass

def extract_bankrupt_urls():
    """Извлекает URL страниц с подробной информацией о банкротах."""
    with sync_playwright() as p:
        # Запускаем браузер с видимым интерфейсом
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Переходим на страницу и ждем полной загрузки
        logger.info("Загружаем страницу банкротов...")
        page.goto("https://bankrot.fedresurs.ru/bankrupts?regionId=1", wait_until="networkidle")

        # Находим все карточки компаний
        cards = page.locator("app-bankrupt-result-card-company").all()
        logger.info(f"Найдено карточек: {len(cards)}")

        # Список для хранения результатов
        results = []
        
        # Обрабатываем каждую карточку
        for i, card in enumerate(cards):
            try:
                # Извлекаем текст карточки для логирования или фильтрации
                card_text = card.text_content()
                logger.info(f"Обрабатываем карточку {i}: {card_text[:50]}...")

                # Кликаем на ссылку и перехватываем попап
                with page.expect_popup() as popup_info:
                    card.locator("a").click()
                popup = popup_info.value
                
                

                # Сохраняем URL новой страницы
                redirect_url = popup.url
                results.append({"index": i, "company": card_text.strip(), "url": redirect_url})
                logger.info(f"URL для карточки {i}: {redirect_url}")

                # Закрываем попап, чтобы не перегружать память
                popup.close()

            except Exception as e:
                logger.error(f"Ошибка при обработке карточки {i}: {e}")
                continue

        # Закрываем браузер
        browser.close()
        return results

if __name__ == "__main__":
    # Запускаем функцию и выводим результаты
    test_url("https://fedresurs.ru/companies/c75fcea8-2989-4f47-b317-428adc68b9d1")

    # bankrupt_data = extract_bankrupt_urls()
    # for data in bankrupt_data:
    #     print(f"Карточка {data['index']}: {data['company'][:50]}... -> {data['url']}")