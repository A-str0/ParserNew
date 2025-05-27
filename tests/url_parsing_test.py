import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import logging
import time

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s (%(filename)s:%(lineno)d): %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("card_clicker.log")]
)
logger = logging.getLogger("CardClicker")

async def start_browser(headless: bool = True):
    """Запускает браузер и возвращает объект Browser."""
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=headless)
        logger.debug("Browser launched")
        return browser
    except Exception as e:
        logger.error(f"Failed to start browser: {e}")
        raise

async def open_page(browser, url: str, retries: int = 3, timeout: int = 30000):
    """Открывает новую страницу и переходит по указанному URL с повторными попытками."""
    for attempt in range(retries):
        try:
            context = await browser.new_context()
            page = await context.new_page()
            logger.debug(f"Attempt {attempt + 1}: Navigating to {url}")
            await page.goto(url, wait_until="networkidle", timeout=timeout)
            # Проверяем наличие карточек или контейнера
            await page.wait_for_selector("app-bankrupt-result-card-company, .u-card-result", timeout=timeout)
            logger.debug(f"Page loaded: {url}")
            return page
        except PlaywrightTimeoutError:
            logger.warning(f"Attempt {attempt + 1}: Timeout loading {url}")
            if attempt < retries - 1:
                await asyncio.sleep(2)  # Пауза перед повторной попыткой
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: Failed to load {url}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2)
        finally:
            if 'page' in locals():
                await page.screenshot(path=f"load_error_attempt_{attempt + 1}.png")
    logger.error(f"Failed to load {url} after {retries} attempts")
    raise PlaywrightTimeoutError(f"Could not load {url}")

async def ensure_all_cards_loaded(page, max_scrolls: int = 10):
    """Прокручивает страницу, чтобы загрузить все карточки."""
    try:
        last_count = 0
        for _ in range(max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)  # Увеличено для медленных страниц
            cards = page.locator("app-bankrupt-result-card-company")
            current_count = await cards.count()
            logger.debug(f"Loaded {current_count} cards")
            if current_count == last_count and current_count > 0:
                break  # Прокрутка не добавила новых карточек
            last_count = current_count
        if last_count == 0:
            logger.warning("No cards loaded after scrolling")
    except Exception as e:
        logger.error(f"Failed to load all cards: {e}")
        await page.screenshot(path="scroll_error.png")

async def get_card_data(card, index: int) -> dict:
    """Извлекает данные карточки."""
    try:
        title = card.find("h2").text.strip() if card.find("h2") else f"No title {index}"
        status = card.find(class_="u-card-result__value u-card-result__value_cursor-def u-card-result__value_item-property u-card-result__value_width-item").text.strip() if card.find(class_="u-card-result__value") else "No status"
        return {"index": index, "title": title, "status": status}
    except Exception as e:
        logger.error(f"Failed to extract data for card {index}: {e}")
        return {"index": index, "title": f"Error {index}", "status": "Error"}

async def emulate_click_and_get_url(page, card_locator, index: int, retries: int = 3) -> dict:
    """Эмулирует клик на карточке по индексу и возвращает URL и данные карточки."""
    try:
        logger.debug(f"Trying to emulate")

        # Проверяем, существует ли карточка
        if await card_locator.nth(index).count() == 0:
            logger.warning(f"No card found at index {index}")
            return None

        logger.debug(f"Card exists")

        # Прокручиваем до карточки
        await card_locator.nth(index).scroll_into_view_if_needed()
        await page.wait_for_timeout(500)

        logger.debug(f"Scroll to card")

        logger.debug(f"Getting data")

        # Извлекаем данные карточки перед кликом
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("app-bankrupt-result-card-company")
        if index >= len(cards):
            logger.warning(f"Card index {index} out of range")
            return None
        card_data = await get_card_data(cards[index], index)

        logger.debug(f"Data was gotten")

        # Эмулируем клик и перехватываем навигацию
        url = None
        for attempt in range(retries):
            try:
                async with page.expect_navigation(timeout=15000) as navigation_info:
                    logger.debug(f"Clicking {card_locator}...")

                    await card_locator.nth(index).click()

                    logger.debug(f"Clicked")

                navigation = await navigation_info.value
                url = navigation.url if navigation else page.url
                logger.debug(f"Card {index}: Navigated to {url}")
                break
            except PlaywrightTimeoutError:
                logger.warning(f"Attempt {attempt + 1} timeout for card {index}")
                await asyncio.sleep(1)
                if attempt == retries - 1:
                    logger.error(f"Failed navigation for card {index} after {retries} attempts")
                    await page.screenshot(path=f"nav_error_card_{index}.png")
                    return None

        # Возвращаемся на исходную страницу
        await page.go_back(wait_until="networkidle")
        await page.wait_for_selector("app-bankrupt-result-card-company, .u-card-result", timeout=10000)
        logger.debug(f"Card {index}: Returned to original page")

        return {**card_data, "url": url}
    except Exception as e:
        logger.error(f"Failed to emulate click for card {index}: {e}")
        await page.screenshot(path=f"error_card_{index}.png")
        return None

async def process_cards(page) -> list:
    """Обрабатывает все карточки на странице и собирает URL перенаправлений."""
    try:
        # Убедимся, что все карточки загружены
        await ensure_all_cards_loaded(page)
        
        # Находим все карточки
        card_locator = page.locator("app-bankrupt-result-card-company")
        card_count = await card_locator.count()
        logger.debug(f"Found {card_count} cards")

        results = []
        for index in range(card_count):
            # Фильтрация по статусу "Конкурсное производство"
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.find_all("app-bankrupt-result-card-company")
            logger.debug(f"Analyzing card {index} of {card_count}")
            if index >= len(cards):
                continue
            card = cards[index]
            status = card.find(class_="u-card-result__value u-card-result__value_cursor-def u-card-result__value_item-property u-card-result__value_width-item")
            logger.debug(f"Status is {status}")
            if status and "Конкурсное производство" not in status.text.strip():
                logger.debug(f"Card {index} skipped (status not 'Конкурсное производство')")
                continue

            result = await emulate_click_and_get_url(page, card_locator, index)
            if result:
                results.append(result)
        return results
    except Exception as e:
        logger.error(f"Failed to process cards: {e}")
        await page.screenshot(path="process_error.png")
        return []

async def test(url: str):
    """Основная функция для тестирования."""
    logger.info("Starting test")
    browser = await start_browser(headless=False)  # Включите видимый режим для отладки
    try:
        page = await open_page(browser, url)
        results = await process_cards(page)
        return results
    finally:
        await browser.close()
        logger.debug("Browser closed")

def run():
    """Запускает тест."""
    url = "https://bankrot.fedresurs.ru/bankrupts?regionId=1&isActiveLegalCase=true&offset=0&limit=15"
    try:
        results = asyncio.run(test(url))
        for result in results:
            print(f"Card {result['index']}: Title={result['title']}, Status={result['status']}, URL={result['url']}")
    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    run()