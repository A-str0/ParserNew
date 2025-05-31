from datetime import *


def current_formatted_time() -> str:
    return datetime.now().strftime("%d%m%Y%H%M%S")


def current_time() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")
