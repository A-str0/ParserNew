import requests
from bs4 import BeautifulSoup
from handlers.datetime_handler import current_time
from handlers.logging_handler import setup_logger, logging
from handlers.decorators import with_interval


class BankruptParserService:
    logger: logging.Logger = None


    def __init__(self) -> None:
        # Setup logger
        cur_time: str = current_time()
        log_filename: str = f"BankruptParser_Log_{cur_time}.log"
        self.logger = setup_logger("Logs", log_filename)


    @with_interval(5)
    def get_response_from_url(self, url: str) -> requests.Response:
        self.logger.debug(f"Getting response from url: {url}...")

        try:
            response = requests.get(url)

            response.raise_for_status()
        except Exception as e:
            self.logger.error(f"Failed to get response from {url}: {e}")
            raise

        self.logger.debug(f"Response from {url} received: {response.status_code}")

        return response


    def get_soup_from_response(self, response: requests.Response) -> BeautifulSoup:
        self.logger.debug("Getting soup from response...")

        try:
            soup: BeautifulSoup = BeautifulSoup(response.text)
        except Exception as e:
            self.logger.error(f"Failed to parse response: {e}")
            raise

        self.logger.debug("Soup was gotten!")

        return soup


    def is_valid_status(self, card) -> bool:
        try:
            card_procedure = "u-card-result__value u-card-result__value_cursor-def u-card-result__value_item-property u-card-result__value_width-item"
            return "Конкурсное производство" in card.find(class_=card_procedure).text
        except AttributeError:
            self.logger.warning("Card has no status field")
            return False


    def extract_organization_data(self, card) -> dict:
        try:
            status = card.find(class_="u-card-result__value u-card-result__value_cursor-def u-card-result__value_item-property u-card-result__value_width-item").text.strip()
            url = card.find("a")["href"] if card.find("a") else None
            return {"inn": inn, "status": status, "url": url}
        except AttributeError as e:
            self.logger.error(f"Failed to extract card data: {e}")
            return None


    def parse_cards(self, soup: BeautifulSoup) -> list:
        try:
            cards = soup.find_all("app-bankrupt-result-card-company")

            card_procedure: str = "u-card-result__value u-card-result__value_cursor-def u-card-result__value_item-property u-card-result__value_width-item"
            return list(filter(lambda card: "Конкурсное производство" in card.find(card_procedure).text, cards))
        except Exception as e:
            self.logger.error(str(e))

        self.logger.warning("List of cards is empty!")
        return []
