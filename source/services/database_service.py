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
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
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


    def organization_exists(self, inn: int) -> bool:
        # Check if an organization with the given INN exists in the database
        try:
            with self.conn:
                cursor = self.conn.execute("SELECT 1 FROM organizations WHERE inn = ?", (inn,))
                result = cursor.fetchone()
                exists = result is not None
                self.logger.debug(f"Checked INN {inn}: {'exists' if exists else 'does not exist'}")
                return exists
        except Exception as e:
            self.logger.error(f"Error checking INN {inn}: {e}")
            return False


    def get_organization(self, inn: str) -> list:
        try:
            self.cursor.execute(
                "SELECT inn, status, url, region_id FROM Organizations WHERE inn = ?",
                (inn,)
            )
            result = self.cursor.fetchone()
            if result:
                self.logger.debug(f"Retrieved organization: INN {inn}")
                return list(result)
            else:
                self.logger.debug(f"No organization found for INN {inn}")
                return []
        except Exception as e:
            self.logger.error(f"Error retrieving organization INN {inn}: {e}")
            return []


    def clear_regions(self) -> None:
        self.logger.debug("Clearing regions table")
        try:
            with self.conn:
                self.conn.execute("DELETE FROM regions")
            self.logger.info("Regions table cleared")
        except Exception as e:
            self.logger.error(f"Failed to clear regions table: {str(e)}")
            raise


    def insert_region(self, region_id: int, name: str) -> None:
        self.logger.debug(f"Inserting region: ID={region_id}, Name={name}")
        try:
            with self.conn:
                query = """INSERT OR REPLACE INTO regions (Id, Name, Status)
                           VALUES (?, ?, ?)"""
                self.conn.execute(query, (region_id, name, 1))  # Default Status=1
        except Exception as e:
            self.logger.error(f"Failed to insert region {region_id}: {str(e)}")
            raise


    def get_regions(self) -> list:
        self.logger.debug("Fetching all regions")
        try:
            with self.conn:
                cursor = self.conn.execute("SELECT Id, Name FROM regions ORDER BY Id")
                return [(row[0], row[1]) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Failed to fetch regions: {str(e)}")
            return []


    def __del__(self):
        """Close the database connection when the object is destroyed."""
        if self.conn:
            self.conn.close()
            self.logger.debug("Database connection closed")