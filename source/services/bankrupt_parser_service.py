import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Browser, Page
from handlers.datetime_handler import current_time
from handlers.logging_handler import setup_logger, logging
from handlers.decorators import with_interval


class BankruptParserService:
    logger: logging.Logger = None
    browser: Browser = None


    def __init__(self) -> None:
        # Setup logger
        cur_time: str = current_time()
        log_filename: str = f"BankruptParser_Log_{cur_time}.log"
        self.logger = setup_logger("Logs", log_filename)

        # Setup browser
        self.browser = self.open_browser()


    async def open_browser(self) -> Browser:
        self.logger.debug("Launching browser...")

        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
        except Exception as e:
            self.logger.error(f"Failed to launch browser: {e}")
            raise

        self.logger.debug("Browser launched")
        return browser


    async def get_page_content(self, url: str) -> tuple[BeautifulSoup, Page]:
        self.logger.debug(f"Getting page content from {url}...")

        async with async_playwright() as p:
            page = await self.browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle")
                await page.wait_for_selector("app-bankrupt-result-card-company", timeout=10000)
                
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                self.logger.debug(f"Page content from {url} received")

                return soup, page
            except PlaywrightTimeoutError:
                self.logger.error(f"Timeout waiting for selector on {url}")

                await self.browser.close()
                raise
            except Exception as e:
                self.logger.error(f"Failed to get page content from {url}: {e}")

                await self.browser.close()
                raise


    @with_interval(5)
    async def process_page(self, page: Page, url: str) -> list:
        self.logger.debug(f"Navigating to {url}")

        try:
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_selector("app-bankrupt-result-companies", timeout=10000)
            self.logger.debug(f"Loading page {url}")
        
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.find_all("app-bankrupt-result-card-company")
        
            card_procedure: str = "u-card-result__value u-card-result__value_cursor-def u-card-result__value_item-property u-card-result__value_width-item"
            return list(filter(lambda card: "Конкурсное производство" in card.find(card_procedure).text, cards))
        except Exception as e:
            self.logger.error(f"Failed to process page {url}: {e}")
            raise


    def extract_card_data(self, card) -> dict:
        """Извлекает данные из одной карточки."""
        try:
            status = card.find(class_="status").text.strip() if card.find(class_="status") else "No status"
            self.logger.debug(f"Extracted card: {title}")
            return {"title": title, "status": status}
        except Exception as e:
            logger.error(f"Error extracting card data: {e}")
            return None


    def extract_organization_data(self, card) -> dict:
        try:
            BeautifulSoup.find

            inn = card.find("div", class_="u-card-result__item-id").find_all("span", class_)
            status = card.find(class_="u-card-result__value u-card-result__value_cursor-def u-card-result__value_item-property u-card-result__value_width-item").text.strip()
            # url = card.find("a")["href"] if card.find("a") else None

            result = {"inn": inn, "status": status, "url": url}

            self.logger.debug(f"Organization data extracted: {result}")
            return result
        except AttributeError as e:
            self.logger.error(f"Failed to extract card data: {e}")
            return None

