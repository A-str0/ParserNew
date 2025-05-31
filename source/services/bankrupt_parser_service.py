import requests as rq
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Browser, Page, Locator
from handlers.datetime_handler import current_formatted_time
from handlers.logging_handler import setup_logger, logging
from handlers.decorators import with_interval
from handlers.format_handler import format_url


class BankruptParserService:
    logger: logging.Logger = None
    browser: Browser = None


    def __init__(self, proxy_config=None) -> None:
        # Setup logger
        cur_time: str = current_formatted_time()
        log_filename: str = f"BankruptParser_Log_{cur_time}.log"
        self.logger = setup_logger("Parser", "Logs", log_filename)
        self.proxy_config = proxy_config


    async def open_browser(self) -> Browser:
        self.logger.debug("Launching browser...")

        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=False)  # TODO: change to True for production
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
                ignore_https_errors=True,
                proxy=self.proxy_config if self.proxy_config else None,
                # Trun off the WebRTC
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Connection": "keep-alive"
                },
                # Emulate real browser metadata
                permissions=["geolocation"],
                geolocation={"latitude": 55.7558, "longitude": 37.6173},  # Москва
                locale="en-US",
                timezone_id="Europe/Moscow"
            )
            page = await context.new_page()

            # Net responses logging
            async def log_response(response):
                self.logger.debug(f"Response: {response.url} - Status: {response.status}")
            page.on("response", log_response)

            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(2000)  # Waiting for JavaScript
        except PlaywrightTimeoutError:
            self.logger.error(f"Timeout waiting for selector on {url}")
            raise
        except Exception as e:
            self.logger.error(f"Error while loading the page: {str(e)}")
            raise

        self.logger.debug(f"Page loaded! ({url})")
        return page


    async def expect_popup(self, page: Page, locator: Locator) -> Page:
        async with page.expect_popup() as popup_info:
            await locator.locator("a").hover()  # Emulate hover
            await page.wait_for_timeout(500)  # Pause for "humanity" effect
            await locator.locator("a").click() # Click on the link
        popup_page = await popup_info.value
        await popup_page.wait_for_timeout(3000)  # Waiting for JavaScript

        return popup_page

    @with_interval(5)
    async def make_request(self, url: str, params=None) -> rq.Response:
        self.logger.info(f"Sending request for {url} ({params})...")

        try:
            response = rq.get(
                url,
                params=params,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "application/json, text/plain, */*"
                },
                proxies=self.proxy_config if self.proxy_config else None
            )
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


    async def parse_card(self, page: Page, card_soup: BeautifulSoup, card_locator: Locator) -> dict:
        try:
            # Parcing INN   
            inn = card_soup.find("div", class_="u-card-result__item-id").find("span", class_="u-card-result__value u-card-result__value_fw").text.strip()
            self.logger.debug(f"Organization INN: {inn}")

            # Open Popup page
            popup_page = await self.expect_popup(page, card_locator)

            # Net responses logging
            async def log_response(response):
                self.logger.debug(f"Response: {response.url} - Status: {response.status}")
            popup_page.on("response", log_response)

            information_soup = BeautifulSoup(await popup_page.content(), "html.parser").find("body")
            last_publications = information_soup.find_all("div", class_="info-item")

            publication_url = None

            # Checking LastPublications on AllInformation page
            for publication in last_publications:
                link = publication.find("div", class_="info-item-value")
                if link and "субсидиарной ответственности" in link.text.strip():
                    self.logger.debug(f"Matching publication found: {link}")

                    anchor = publication.find("a", class_="underlined")
                    if anchor:
                        publication_url = anchor.get("href")

                        self.logger.debug(f"Organization URL ({inn}): {publication_url}")
                        break

            # If matching publication is not found, checking the AllInformation page
            if publication_url is None:
                self.logger.debug("Matching publication not found on AllInformation page")

                all_info_link = information_soup.find("a", class_="d-flex justify-content-end all-info-link")
                # If cannot find the AllPublications page url, return Null dictionary
                if not all_info_link:
                    self.logger.warning(f"Url for all publications is not found")

                    await popup_page.close()
                    return {"inn": inn, "status": 1, "url": None}

                # Formatting the AllPublications page URL
                all_publications_url = all_info_link.get("href")
                all_publications_url = format_url(all_info_link.get("href"), "https://fedresurs.ru")
                self.logger.debug(f"AllPublications page URL: {all_publications_url}")

                # Getting all the publications
                all_publications_page = await self.load_page(all_publications_url)
                await all_publications_page.wait_for_selector("entity-card-publications-search-result-card", timeout=30000)
                all_publications_soup = BeautifulSoup(await all_publications_page.content(), "html.parser")
                all_publications = all_publications_soup.find_all("entity-card-publications-search-result-card")

                # Iterating through all the publications
                # TODO: Add page offset changing
                for publication in all_publications:
                    title = publication.find("div", class_="item item-1").find("div", class_="fw-light cursor-auto")

                    if title and "субсидиарной ответственности" in title.text.strip():
                        link = publication.find("a", class_="underlined")
                        self.logger.debug(f"Matching publication found: {link}")

                        if link:
                            publication_url = format_url(link.get("href"), "https://bankrot.fedresurs.ru")
                            self.logger.debug(f"Organization ({inn}) URL: {publication_url}")
                            break

                await all_publications_page.close()

            await popup_page.close()

            status = 1 if publication_url is None else 0
            self.logger.debug(f"Organization ({inn}) status: {status}")

            return {"inn": inn, "status": status, "url": publication_url}
        except Exception as e:
            self.logger.error(f"Error while extracting card data: {e}")
            return None