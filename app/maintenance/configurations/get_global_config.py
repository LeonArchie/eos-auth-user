# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import requests
import threading
import logging
from typing import Dict, Any, Optional

from maintenance.configurations.get_local_config import get_local_config

# Константы для возвращаемых значений
DATA_ERROR = "DATA_ERROR"
FORMAT_ERROR = "FORMAT_ERROR"
SERVER_ERROR = "SERVER_ERROR"
VALID_ERROR = "VALID_ERROR"

# Кэш для хранения полученных значений
_CONFIG_CACHE: Dict[str, str] = {}

# Флаг доступности сервиса
_global_service_available: bool = False

# Таймер для фоновой проверки доступности сервиса
_health_check_timer = None
_health_check_interval = 10  # секунд
_health_check_lock = threading.Lock()

logger = logging.getLogger(__name__)


def check_global_config_available() -> bool:
    """Проверяет доступность глобального сервиса конфигураций"""
    return _global_service_available


def _check_service_health() -> bool:
    """Проверка доступности сервиса конфигураций через /readyz endpoint"""
    global _global_service_available

    config_service_url = get_local_config("URL_CONFIG_MODULES")
    if not config_service_url:
        logger.error("URL_CONFIG_MODULES не найден в локальной конфигурации")
        return False

    try:
        response = requests.get(
            f"{config_service_url}/readyz",
            timeout=3
        )

        if response.status_code == 200:
            if not _global_service_available:
                logger.info("Сервис конфигураций стал доступен")
                _global_service_available = True
                _stop_health_check()
            return True
        else:
            logger.error(f"Ошибка при подключении к сервису конфигураций (код {response.status_code})")
            _global_service_available = False
            return False

    except Exception as e:
        logger.error(f"Ошибка при проверке доступности сервиса конфигураций: {e}")
        _global_service_available = False
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
            _global_service_available = False
            _start_health_check()
            return SERVER_ERROR

        else:
            logger.error(f"Неожиданный код ответа от сервиса конфигураций: {response.status_code}")
            return SERVER_ERROR

    except requests.exceptions.ConnectionError:
        logger.error("Ошибка подключения к сервису конфигураций")
        _global_service_available = False
        _start_health_check()
        return SERVER_ERROR
    except requests.exceptions.Timeout:
        logger.error("Таймаут при подключении к сервису конфигураций")
        _global_service_available = False
        _start_health_check()
        return SERVER_ERROR
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при запросе к сервису конфигураций: {e}")
        _global_service_available = False
        _start_health_check()
        return SERVER_ERROR


def _health_check_worker():
    """Фоновая задача для периодической проверки доступности сервиса"""
    if _check_service_health():
        # Сервис стал доступен, останавливаем проверки
        _stop_health_check()
    else:
        # Сервис все еще недоступен, планируем следующую проверку
        _start_health_check()


def _start_health_check():
    """Запуск фоновой проверки доступности сервиса"""
    global _health_check_timer

    with _health_check_lock:
        if _health_check_timer is None or not _health_check_timer.is_alive():
            _health_check_timer = threading.Timer(_health_check_interval, _health_check_worker)
            _health_check_timer.daemon = True
            _health_check_timer.start()
            logger.debug("Запущена фоновая проверка доступности сервиса конфигураций")


def _stop_health_check():
    """Остановка фоновой проверки доступности сервиса"""
    global _health_check_timer

    with _health_check_lock:
        if _health_check_timer:
            _health_check_timer.cancel()
            _health_check_timer = None
            logger.debug("Фоновая проверка доступности сервиса конфигураций остановлена")


def init_global_config_check() -> bool:
    """
    Инициализация проверки доступности глобального сервиса конфигураций

    Returns:
        bool: True если сервис доступен, False если нет
    """
    if _check_service_health():
        return True
    else:
        _start_health_check()
        return False


def get_config_cache_stats() -> Dict[str, Any]:
    """Получение статистики кэша конфигураций (для отладки)"""
    return {
        'cache_size': len(_CONFIG_CACHE),
        'cache_keys': list(_CONFIG_CACHE.keys()),
        'global_service_available': _global_service_available
    }


def clear_config_cache():
    """Очистка кэша конфигураций (для тестирования)"""
    global _CONFIG_CACHE
    _CONFIG_CACHE = {}
    logger.debug("Кэш глобальных конфигураций очищен")