# handlers/valid_regular_expressions.py

import re
import logging

# Используем тот же логгер, что и в основном приложении
logger = logging.getLogger(__name__)

def valid_regular_expressions(validation_string: str, regex_pattern: str) -> bool:
    """
    Проверяет строку на соответствие регулярному выражению
    
    Args:
        validation_string: Строка для валидации
        regex_pattern: Регулярное выражение для проверки
    
    Returns:
        bool: True если строка соответствует регулярному выражению, False в противном случае
    """
    # Логируем полученные параметры
    logger.debug(f"Получено для валидации '{validation_string}' по выражению '{regex_pattern}'")
    
    try:
        # Компилируем регулярное выражение
        pattern = re.compile(regex_pattern)
        
        # Выполняем проверку
        if pattern.fullmatch(validation_string):
            logger.debug(f"Валидация '{validation_string}' по выражению '{regex_pattern}' - успешна")
            return True
        else:
            logger.warning(f"Валидация '{validation_string}' по выражению '{regex_pattern}' - завершена с ошибкой (несоответствие шаблону)")
            return False
            
    except re.error as e:
        # В случае ошибки в регулярном выражении логируем ошибку и возвращаем False
        logger.error(f"Ошибка в регулярном выражении '{regex_pattern}': {e}")
        return False
    except Exception as e:
        # Обработка других непредвиденных ошибок
        logger.error(f"Непредвиденная ошибка при валидации строки '{validation_string}' по выражению '{regex_pattern}': {e}")
        return False