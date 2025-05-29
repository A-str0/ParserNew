import requests as rq
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Browser, Page, Locator
from playwright_stealth import stealth_async
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
        self.logger = setup_logger("Parser", "Logs", log_filename)

        # Setup browser
        # asyncio.run(self.open_browser())


    async def open_browser(self) -> Browser:
        self.logger.debug("Launching browser...")

        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=False) ## TODO: change to True
        except Exception as e:
            self.logger.error(f"Failed to launch browser: {e}")
            raise

        self.logger.debug("Browser launched")
        return self.browser


    async def load_page(self, url: str) -> Page:
        self.logger.debug(f"Loading page ({url})...")

        try:
            if self.browser is None or not self.browser.is_connected():
                self.logger.debug("Browser not initialized or disconnected, opening new browser")
                await self.open_browser()

            self.logger.debug(f"Browser is: {self.browser}")

            context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                java_script_enabled=True,
                ignore_https_errors=True
            )
            page = await context.new_page()
                
            await page.goto(url, wait_until="networkidle")
        except PlaywrightTimeoutError:
            self.logger.error(f"Timeout waiting for selector on {url}")
            raise
        except Exception as e:
            self.logger.error(f"Error while loading the page: {str(e)}")
            raise

        self.logger.debug(f"Page loaded! ({url})")

        return page

    @with_interval(5)
    async def make_request(self, url: str, params = None) -> rq.Response:
        self.logger.info(f"Sending request for {url} ({params})...")

        try:
            response = rq.get(url, params=params, timeout=10, headers={'User-Agent': 'Chromium'})
            response.raise_for_status()

            return response
        except rq.exceptions.HTTPError as e:
            self.logger.error(f"HTTP Error: {e}")
            raise
        except rq.Timeout as e:
            self.logger.error(f"Timeout Error: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error while making request: {str(e)}")
            raise

    # Looks like a mess. TODO: Remade this
    async def parse_card(self, page: Page, card_soup: BeautifulSoup, card_locator: Locator) -> dict:
        try:
            # Parcing INN   
            inn = card_soup.find("div", class_="u-card-result__item-id").find("span", class_="u-card-result__value u-card-result__value_fw").text.strip()
            self.logger.debug(f"Organization INN: {inn}")

            # TODO: check if should open all information page
            async with page.expect_popup() as popup_information_info:
                await card_locator.locator("a").click()
            popup_information_page: Page = await popup_information_info.value
            await stealth_async(popup_information_page)
            await popup_information_page.wait_for_load_state("networkidle")

            async def log_response(response):
                self.logger.debug(f"Response: {response.url} - Status: {response.status}")
            popup_information_page.on("response", log_response)

            async def capture_api(response):
                if "api" in response.url:
                    self.logger.debug(f"API: {response.url} - {await response.json()}")
            popup_information_page.on("response", capture_api)

            self.logger.debug(await popup_information_page.content())
            
            information_soup: BeautifulSoup = BeautifulSoup(await popup_information_page.content(), "html.parser")
            last_publications = information_soup.find_all("div", class_="info-item")

            publication_url: str = None

            await popup_information_page.close()

            # Iterate through all the last publications
            for publication in last_publications:
                # If publication is matching the required format
                if "субсидиарной ответственности" in publication.find("a", class_="info-item-value").text.strip():
                    self.logger.debug("Found matched publicaton")

                    publication_url = publication.find("a").get("href")

                    self.logger.debug(f"URL for organization ({inn}): {publication_url}")
                    break
        
                popup_information_page.close()

            # Not found any matching publication in last publications
            if publication_url == None:
                self.logger.debug("No publication with matching format on the information page")

                # Making request for All publications page
                all_publications_url: str = information_soup.find("a", class_="d-flex justify-content-end all-info-link").get("href")
                self.logger.debug(f"All publications page URL: {all_publications_url}")

                all_publications_page: Page = await self.load_page(all_publications_url)
                all_publications_soup: BeautifulSoup = BeautifulSoup(all_publications_page.content)
                all_publications: list = all_publications_soup.find_all("entity-card-publications-search-result-card")
                for publication in all_publications:
                    if "субсидиарной ответственности" in publication.find("div", class_="item item-1").find("div", class_="fw-light cursor-auto").text.strip():
                        self.logger.debug("Found matched publicaton")

                        async with page.expect_popup() as popup_publication_info:
                            await card_locator.locator("a").click()
                        popup_publication_page: Page = popup_publication_info.value
                        popup_publication_page.wait_for_url()
                        publication_url = popup_publication_page.url
                        await popup_publication_page.close()

                        self.logger.debug(f"URL for organization ({inn}): {publication_url}")
                        break

                pass

            status: int = 1 if publication_url == None else 0
            self.logger.debug(f"Status for organization ({inn}): {status}")

            return {"inn" : inn, "status" : status, "url" : publication_url}
        except Exception as e:
            self.logger.error(f"Error extracting card data: {e}")
            return None


