import requests as rq
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Browser, Page, Locator
from handlers.datetime_handler import current_formatted_time
from handlers.logging_handler import setup_logger, logging
from handlers.decorators import with_interval
from handlers.format_handler import format_url
from services.database_service import DatabaseService


class BankruptParserService:
    logger: logging.Logger = None
    browser: Browser = None
    db_service: DatabaseService = None


    def __init__(self, db_service: DatabaseService, proxy_config=None, parse_full_info=True) -> None:
        # Setup logger
        cur_time: str = current_formatted_time()
        log_filename: str = f"BankruptParser_Log_{cur_time}.log"
        self.logger = setup_logger("Parser", "Logs", log_filename)
        self.proxy_config = proxy_config

        # Set DatabaseService
        self.db_service = db_service

        # Flag to control whether to parse the full information page
        self.parse_full_info = parse_full_info


    async def organization_exists(self, inn: str) -> bool:
        if not self.db_service:
            self.logger.error("Database service not initialized")
            return False
        
        try:
            return self.db_service.organization_exists(inn)
        except Exception as e:
            self.logger.error(f"Error checking INN {inn} in database: {e}")
            return False


    async def open_browser(self) -> Browser:
        # Launch the browser
        self.logger.debug("Launching browser...")
        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=False)  # TODO: Change to True for production
        except Exception as e:
            self.logger.error(f"Failed to launch browser: {e}")
            raise
        self.logger.debug("Browser launched")
        return self.browser


    async def load_page(self, url: str, wait_time: int = 3000) -> Page:
        self.logger.debug(f"Loading page ({url})...")
        try:
            if self.browser is None or not self.browser.is_connected():
                self.logger.debug("Browser not initialized or disconnected, opening new browser")
                await self.open_browser()

            context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                java_script_enabled=True,
                ignore_https_errors=True,
                proxy=self.proxy_config if self.proxy_config else None,
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Connection": "keep-alive"
                },
                # Emulate real browser metadata
                permissions=["geolocation"],
                geolocation={"latitude": 55.7558, "longitude": 37.6173},
                locale="en-US",
                timezone_id="Europe/Moscow"
            )
            page = await context.new_page()

            async def log_response(response):
                self.logger.debug(f"Response: {response.url} - Status: {response.status}")
            page.on("response", log_response)

            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(wait_time)
        except PlaywrightTimeoutError:
            self.logger.error(f"Timeout waiting for selector on {url}")
            raise
        except Exception as e:
            self.logger.error(f"Error while loading the page: {str(e)}")
            raise
        self.logger.debug(f"Page loaded! ({url})")
        return page


    async def expect_popup(self, page: Page, locator: Locator, wait_time: int = 3000) -> Page:
        # Wait for a popup to appear after clicking a link
        async with page.expect_popup() as popup_info:
            await locator.locator("a").hover()
            await page.wait_for_timeout(500)
            await locator.locator("a").click()
        popup_page = await popup_info.value
        await popup_page.wait_for_timeout(wait_time)
        return popup_page


    @with_interval(5)
    async def make_request(self, url: str, params=None) -> rq.Response:
        # Make an HTTP request with retries
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


    async def parse_card(self, page: Page, card_soup: BeautifulSoup, card_locator: Locator, wait_time: int = 3000) -> dict:
        # Parse a single organization card
        try:
            # Check procedure status
            procedure_status: str = card_soup.find("div", class_="u-card-result__value u-card-result__value_cursor-def u-card-result__value_item-property u-card-result__value_width-item").text.strip()
            if procedure_status == "Конкурсное производство":
                return None

            # Parse INN
            inn: str = card_soup.find("div", class_="u-card-result__item-id").find("span", class_="u-card-result__value u-card-result__value_fw").text.strip()
            self.logger.debug(f"Processing INN: {inn}")
            
            # Check DB status for organization
            organization: list = self.db_service.get_organization(int(inn))
            if organization[1] == 0:
                self.logger.debug(f"Organization with INN {inn} has status '0' in DB, skipping")
                return None

            # Check if full information parsing is disabled
            if not self.parse_full_info:
                self.logger.debug(f"Full info parsing disabled for INN: {inn}")
                return {"inn": inn, "status": 1, "url": None}

            # Open popup page
            popup_page: Page = await self.expect_popup(page, card_locator, wait_time)

            # Net responses logging
            async def log_response(response):
                self.logger.debug(f"Response: {response.url} - Status: {response.status}")
            popup_page.on("response", log_response)

            information_soup: BeautifulSoup = BeautifulSoup(await popup_page.content(), "html.parser").find("body")
            last_publications = information_soup.find_all("div", class_="info-item")

            publication_url = None

            # Check publications on the full information page
            for publication in last_publications:
                link = publication.find("div", class_="info-item-value")
                if link and "субсидиарной ответственности" in link.text.strip():
                    self.logger.debug(f"Matching publication found: {link}")
                    anchor = publication.find("a", class_="underlined")
                    if anchor:
                        publication_url: str = anchor.get("href")
                        self.logger.debug(f"Publication URL for INN {inn}: {publication_url}")
                        break

            # If no matching publication, check the all publications page
            if publication_url is None:
                self.logger.debug("Matching publication not found on full information page")
                all_info_link = information_soup.find("a", class_="d-flex justify-content-end all-info-link")
                if not all_info_link:
                    self.logger.warning(f"No URL found for all publications")
                    await popup_page.close()
                    return {"inn": inn, "status": 1, "url": None}

                # Format the all publications page URL
                all_publications_url: str = format_url(all_info_link.get("href"), "https://fedresurs.ru")
                self.logger.debug(f"All publications page URL: {all_publications_url}")

                # Load all publications page
                all_publications_page: Page = await self.load_page(all_publications_url, wait_time)
                await all_publications_page.wait_for_selector("entity-card-publications-search-result-card", timeout=30000)

                # Process all publications with pagination
                while True:
                    all_publications_soup = BeautifulSoup(await all_publications_page.content(), "html.parser")
                    all_publications = all_publications_soup.find_all("entity-card-publications-search-result-card")

                    # Iterate through publications
                    for publication in all_publications:
                        title = publication.find("div", class_="item item-1").find("div", class_="fw-light cursor-auto")
                        if title and "субсидиарной ответственности" in title.text.strip():
                            link = publication.find("a", class_="underlined")
                            self.logger.debug(f"Matching publication found: {link}")
                            if link:
                                publication_url: str = format_url(link.get("href"), "https://bankrot.fedresurs.ru")
                                self.logger.debug(f"Publication URL for INN {inn}: {publication_url}")
                                break

                    if publication_url:
                        break

                    # Check for "Load More" button
                    load_more_button = all_publications_page.locator("div.more_btn_wrapper")
                    if await load_more_button.is_visible() and await load_more_button.is_enabled():
                        previous_count = len(all_publications)
                        self.logger.debug("Clicking 'Load More' button on all publications page")
                        await load_more_button.click()
                        await all_publications_page.wait_for_timeout(wait_time)
                        new_soup = BeautifulSoup(await all_publications_page.content(), "html.parser")
                        new_publications = new_soup.find_all("entity-card-publications-search-result-card")
                        if len(new_publications) <= previous_count:
                            self.logger.debug("No new publications loaded, stopping pagination")
                            break
                    else:
                        self.logger.debug("No 'Load More' button found or disabled")
                        break

                await all_publications_page.close()

            await popup_page.close()

            status: int = 1 if publication_url is None else 0
            self.logger.debug(f"Organization status for INN {inn}: {status}")

            return {"inn": inn, "status": status, "url": publication_url}
        except Exception as e:
            self.logger.error(f"Error while extracting card data: {e}")
            return None