import logging, time

def with_interval(cooldown_time: float, logger: logging.Logger = None):
    """ Декоратор для простоя между вызовами функции
    :param cooldown_time: время в секундах между вызовами функции
    """

    def decorator(func):
        last_called = [None]  # Используем список, чтобы сохранить состояние между вызовами

        def wrapped(*args, **kwargs):
            # Если функция была вызвана ранее, то проверяем, не прошел ли cooldown
            if last_called[0] is not None:
                elapsed_time = float(time.time() - last_called[0])
                if elapsed_time < float(cooldown_time):
                    wait_time = float(cooldown_time) - elapsed_time
                    logger.info(f"Cooldown. Waiting for {wait_time:.2f} seconds")
                    time.sleep(wait_time)

            # Обновляем время последнего вызова
            last_called[0] = time.time()
            return func(*args, **kwargs)

        return wrapped
    return decorator