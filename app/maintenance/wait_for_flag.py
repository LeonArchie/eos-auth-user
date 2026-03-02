# maintenance/wait_for_flag.py
# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

"""
Модуль для ожидания установки флагов с повторными попытками.
"""

import time
import logging
from typing import Callable, Optional, Any

from maintenance.flag_state import get_global_flag

logger = logging.getLogger(__name__)


def wait_for_flag(
    flag_getter: Callable[[], int],
    flag_name: str,
    target_value: int = 1,
    max_attempts: int = 10,
    delay: float = 10.0,
    description: Optional[str] = None
) -> bool:
    """
    Универсальная функция для ожидания установки флага в определенное значение.
    
    Args:
        flag_getter: Функция для получения текущего значения флага
        flag_name: Имя флага для логирования
        target_value: Целевое значение флага (по умолчанию 1)
        max_attempts: Максимальное количество попыток
        delay: Задержка между попытками в секундах
        description: Дополнительное описание для логирования
    
    Returns:
        bool: True если флаг достиг целевого значения, False если все попытки исчерпаны
    """
    desc_text = f" ({description})" if description else ""
    logger.info(f"Ожидание установки флага {flag_name}{desc_text} в {target_value} "
                f"(макс. попыток: {max_attempts}, задержка: {delay} сек)")
    
    for attempt in range(1, max_attempts + 1):
        try:
            current_value = flag_getter()
            
            if current_value == target_value:
                logger.info(f"Флаг {flag_name} установлен в {target_value} (попытка {attempt})")
                return True
            else:
                logger.warning(f"Флаг {flag_name} = {current_value} (ожидалось {target_value}, "
                              f"попытка {attempt}/{max_attempts})")
        except Exception as e:
            logger.error(f"Ошибка при получении значения флага {flag_name} (попытка {attempt}): {e}")
        
        if attempt < max_attempts:
            logger.info(f"Ожидание {delay} секунд перед следующей попыткой...")
            time.sleep(delay)
    
    logger.error(f"Флаг {flag_name} не достиг значения {target_value} после {max_attempts} попыток")
    return False


def wait_for_global_flag(
    max_attempts: int = 10,
    delay: float = 10.0,
    target_value: int = 1
) -> bool:
    """
    Специализированная функция для ожидания установки флага FLAG_GET_GLOBAL.
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Задержка между попытками в секундах
        target_value: Целевое значение флага (по умолчанию 1)
    
    Returns:
        bool: True если флаг достиг целевого значения, False если все попытки исчерпаны
    """
    return wait_for_flag(
        flag_getter=get_global_flag,
        flag_name="FLAG_GET_GLOBAL",
        target_value=target_value,
        max_attempts=max_attempts,
        delay=delay,
        description="глобальный сервис конфигураций"
    )


def wait_for_db_flag(
    max_attempts: int = 10,
    delay: float = 5.0,
    target_value: int = 1
) -> bool:
    """
    Функция для ожидания установки флага FLAG_DB_ACTIVE.
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Задержка между попытками в секундах
        target_value: Целевое значение флага (по умолчанию 1)
    
    Returns:
        bool: True если флаг достиг целевого значения, False если все попытки исчерпаны
    """
    from maintenance.flag_state import get_db_flag
    
    return wait_for_flag(
        flag_getter=get_db_flag,
        flag_name="FLAG_DB_ACTIVE",
        target_value=target_value,
        max_attempts=max_attempts,
        delay=delay,
        description="активность базы данных"
    )


def wait_for_custom_flag(
    flag_getter: Callable[[], Any],
    flag_name: str,
    condition: Callable[[Any], bool],
    max_attempts: int = 10,
    delay: float = 10.0,
    description: Optional[str] = None
) -> bool:
    """
    Универсальная функция для ожидания выполнения условия на значении флага.
    
    Args:
        flag_getter: Функция для получения текущего значения флага
        flag_name: Имя флага для логирования
        condition: Функция-условие, которая принимает значение флага и возвращает bool
        max_attempts: Максимальное количество попыток
        delay: Задержка между попытками в секундах
        description: Дополнительное описание для логирования
    
    Returns:
        bool: True если условие выполнилось, False если все попытки исчерпаны
    """
    desc_text = f" ({description})" if description else ""
    logger.info(f"Ожидание выполнения условия для флага {flag_name}{desc_text} "
                f"(макс. попыток: {max_attempts}, задержка: {delay} сек)")
    
    for attempt in range(1, max_attempts + 1):
        try:
            current_value = flag_getter()
            
            if condition(current_value):
                logger.info(f"Условие для флага {flag_name} выполнено (попытка {attempt})")
                return True
            else:
                logger.warning(f"Флаг {flag_name} = {current_value} (условие не выполнено, "
                              f"попытка {attempt}/{max_attempts})")
        except Exception as e:
            logger.error(f"Ошибка при проверке флага {flag_name} (попытка {attempt}): {e}")
        
        if attempt < max_attempts:
            logger.info(f"Ожидание {delay} секунд перед следующей попыткой...")
            time.sleep(delay)
    
    logger.error(f"Условие для флага {flag_name} не выполнено после {max_attempts} попыток")
    return False