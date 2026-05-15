# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import requests
import logging
from typing import Dict, Any

from maintenance.configurations.get_local_config import get_local_config

# Константы для возвращаемых значений
DATA_ERROR = "DATA_ERROR"
FORMAT_ERROR = "FORMAT_ERROR"
SERVER_ERROR = "SERVER_ERROR"
VALID_ERROR = "VALID_ERROR"

# Кэш для хранения полученных значений
_CONFIG_CACHE: Dict[str, str] = {}

logger = logging.getLogger(__name__)


def check_global_config_available() -> bool:
    """Проверяет доступность глобального сервиса конфигураций через /readyz endpoint"""
    config_service_url = get_local_config("URL_CONFIG_MODULES")
    if not config_service_url:
        logger.error("URL_CONFIG_MODULES не найден в локальной конфигурации")
        return False

    try:
        response = requests.get(
            f"{config_service_url}/readyz",
            timeout=3
        )
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"Сервис конфигураций недоступен: {e}")
        return False


def get_global_config(parameter_path: str) -> str:
    """
    Получение конфигурационного параметра из удаленного сервиса конфигураций

    Args:
        parameter_path (str): Путь к параметру в формате "db/name/add/port"

    Returns:
        str: Значение параметра или код ошибки
    """
    # Проверяем наличие значения в кэше
    if parameter_path in _CONFIG_CACHE:
        cached_value = _CONFIG_CACHE[parameter_path]
        logger.debug(f"Параметр из кэша {parameter_path}: {cached_value}")
        return cached_value

    # Получаем URL сервиса конфигураций из локального конфига
    config_service_url = get_local_config("URL_CONFIG_MODULES")
    if not config_service_url:
        logger.error("URL_CONFIG_MODULES не найден в локальной конфигурации")
        return SERVER_ERROR

    # Выполняем запрос к сервису конфигураций
    try:
        response = requests.get(
            f"{config_service_url}/v1/read/{parameter_path}",
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()

            if "value" in data:
                value = data["value"]
                logger.info(f"Параметр из сервиса конфигураций {parameter_path}: {value}")

                # Сохраняем в кэш
                _CONFIG_CACHE[parameter_path] = value

                return value
            else:
                logger.error(f"Невозможно получить {parameter_path} - значения нет в ответе")
                return DATA_ERROR

        elif response.status_code == 400:
            logger.error(f"Невозможно получить {parameter_path} - не соответствует формату")
            return FORMAT_ERROR

        elif response.status_code == 404:
            logger.error(f"Невозможно получить {parameter_path} - параметр не существует")
            return DATA_ERROR

        elif response.status_code >= 500:
            logger.error(f"Ошибка при подключении к сервису конфигураций (код {response.status_code})")
            return SERVER_ERROR

        else:
            logger.error(f"Неожиданный код ответа от сервиса конфигураций: {response.status_code}")
            return SERVER_ERROR

    except requests.exceptions.ConnectionError:
        logger.error("Ошибка подключения к сервису конфигураций")
        return SERVER_ERROR
    except requests.exceptions.Timeout:
        logger.error("Таймаут при подключении к сервису конфигураций")
        return SERVER_ERROR
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при запросе к сервису конфигураций: {e}")
        return SERVER_ERROR


def init_global_config_check() -> bool:
    """
    Инициализация проверки доступности глобального сервиса конфигураций

    Returns:
        bool: True если сервис доступен, False если нет
    """
    return check_global_config_available()


def get_config_cache_stats() -> Dict[str, Any]:
    """Получение статистики кэша конфигураций (для отладки)"""
    return {
        'cache_size': len(_CONFIG_CACHE),
        'cache_keys': list(_CONFIG_CACHE.keys())
    }


def clear_config_cache():
    """Очистка кэша конфигураций (для тестирования)"""
    global _CONFIG_CACHE
    _CONFIG_CACHE = {}
    logger.debug("Кэш глобальных конфигураций очищен")