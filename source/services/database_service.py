import sqlite3
from handlers.datetime_handler import current_time
from handlers.logging_handler import setup_logger, logging


class DatabaseService:
    conn: sqlite3.Connection = None
    logger: logging.Logger = None


    def __init__(self, db_path: str):
        # Setup logger
        cur_time: str = current_time()
        log_filename: str = f"Database_Log_{cur_time}.log"
        self.logger = setup_logger("Logs", log_filename)

        self.logger.info("Initializing...")

        try:
            conn = sqlite3.connect(db_path)

            self.logger.debug("DB Connection is ready")
        except Exception as e:
            self.logger.error(str(e))

        self.logger.info("Initialized")


    def create_organiztions_table(self) -> None:
        raise NotImplementedError()


    def create_regions_table(self) -> None:
        self.logger.info("Creating Regions table...")

        try:
            with self.conn:
                query = """ CREATE TABLE IF NOT EXISTS regions ( Id INTEGER, Name TEXT, Status INTEGER )"""
                self.conn.execute(query)
        except Exception as e:
            self.logger.error(str(e))

        self.logger.info("Regions table created!")
        
