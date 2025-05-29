import logging

def setup_logger(name: str, log_path: str, log_filename, level=logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger(name)

    # Formatter
    formatter: logging.Formatter = logging.Formatter("%(asctime)s %(levelname)s (%(filename)s:%(lineno)d): %(message)s")

    # Console handler
    ch: logging.Handler = logging.StreamHandler()
    ch.formatter = formatter
    logger.addHandler(ch)

    # File handler
    handler = logging.FileHandler(f"{log_path}\\{log_filename}", encoding="utf-8")    
    handler.formatter = formatter    

    logger.addHandler(handler)
    logger.setLevel(level)

    logger.info("Logger is ready")

    return logger