import logging

def setup_logger(self, log_path: str, log_filename) -> logging.Logger:
    logger = logging.getLogger(__name__)

    # Formatter
    formatter: logging.Formatter = logging.Formatter("%(asctime)s %(levelname)s (%(filename)s:%(lineno)d): %(message)s")

    # Console handler
    ch: logging.Handler = logging.StreamHandler()
    ch.formatter = formatter
    logger.addHandler(ch)

    # File handler
    handler = logging.FileHandler(log_filename, encoding="utf-8")    
    handler.formatter = formatter    

    logger.addHandler(handler)
    logger.setLevel(logging.CRITICAL)

    logger.info("Logger is ready")

    return logger