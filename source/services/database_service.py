import sqlite3
from handlers.datetime_handler import current_formatted_time, current_time
from handlers.logging_handler import setup_logger, logging

class DatabaseService:
    conn: sqlite3.Connection = None
    logger: logging.Logger = None


    def __init__(self, db_path: str = "database.db"):
        # Setup logger
        cur_time: str = current_formatted_time()
        log_filename: str = f"Database_Log_{cur_time}.log"
        self.logger = setup_logger("Database", "Logs", log_filename)

        self.logger.info("Initializing...")

        try:
            self.conn = sqlite3.connect(db_path)
            self.logger.debug("DB Connection is ready")
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {str(e)}")
            raise

        # Creating tables when initializing
        self.create_regions_table()
        self.create_organizations_table()

        self.logger.info("Initialized")


    def create_regions_table(self) -> None:
        self.logger.info("Creating Regions table...")

        try:
            with self.conn:
                query = """CREATE TABLE IF NOT EXISTS regions (
                    Id INTEGER PRIMARY KEY,
                    Name TEXT,
                    Status INTEGER
                )"""
                self.conn.execute(query)
        except Exception as e:
            self.logger.error(f"Failed to create regions table: {str(e)}")
            raise

        self.logger.info("Regions table created!")


    def create_organizations_table(self) -> None:
        self.logger.info("Creating Organizations table...")

        try:
            with self.conn:
                query = """CREATE TABLE IF NOT EXISTS organizations (
                    inn TEXT PRIMARY KEY,
                    status INTEGER,
                    url TEXT,
                    region_id INTEGER,
                    created_at DATETIME,
                    FOREIGN KEY (region_id) REFERENCES regions(Id)
                )"""
                self.conn.execute(query)
        except Exception as e:
            self.logger.error(f"Failed to create organizations table: {str(e)}")
            raise

        self.logger.info("Organizations table created!")


    def insert_organization(self, inn: str, status: int, url: str, region_id: int) -> None:
        self.logger.debug(f"Inserting organization: INN={inn}, Region={region_id}")

        try:
            with self.conn:
                query = """INSERT OR REPLACE INTO organizations (inn, status, url, region_id, created_at)
                           VALUES (?, ?, ?, ?, ?)"""
                self.conn.execute(query, (inn, status, url, region_id, current_time()))
        except Exception as e:
            self.logger.error(f"Failed to insert organization {inn}: {str(e)}")
            raise


    def get_organizations_by_region(self, region_id: int) -> list:
        self.logger.debug(f"Fetching organizations for region {region_id}")

        try:
            with self.conn:
                cursor = self.conn.execute("SELECT inn, status, url FROM organizations WHERE region_id = ?", (region_id,))
                return cursor.fetchall()
        except Exception as e:
            self.logger.error(f"Failed to fetch organizations: {str(e)}")
            return []