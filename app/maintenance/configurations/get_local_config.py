# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import logging
from pathlib import Path
from typing import Optional, Dict, Any

# Кэш для хранения параметров из global.conf
_CONFIG_CACHE: Dict[str, str] = {}

logger = logging.getLogger(__name__)


def check_local_config_exists() -> bool:
    """
    Проверка существования global.conf файла в корне приложения
    и загрузка его в кэш

    Returns:
        bool: True если файл существует, иначе False
    """
    global _CONFIG_CACHE

    root_dir = Path(__file__).parent.parent.parent
    config_path = root_dir / 'global.conf'

    if config_path.exists():
        logger.debug("Файл global.conf найден, загрузка в кэш")

        try:
            with open(config_path, 'r', encoding='utf-8') as config_file:
                for line in config_file:
                    line = line.strip()

                    if not line or line.startswith('#'):
                        continue

                    if '=' in line:
                        name, value = line.split('=', 1)
                        name = name.strip()
                        value = value.strip().strip('\'"')
                        _CONFIG_CACHE[name] = value

            logger.debug(f"Загружено {len(_CONFIG_CACHE)} параметров в кэш из global.conf")
            return True

        except Exception as e:
            logger.error(f"Ошибка при загрузке global.conf в кэш: {e}")
            return False
    else:
        logger.error("Файл global.conf не найден")
        return False


def get_local_config(param_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Получение значения параметра из global.conf файла

    Args:
        param_name (str): Имя параметра для поиска в global.conf
        default (str, optional): Значение по умолчанию

    Returns:
        str or None: Значение параметра или значение по умолчанию
    """
    global _CONFIG_CACHE

    # Проверяем наличие параметра в кэше
    if param_name in _CONFIG_CACHE:
        value = _CONFIG_CACHE[param_name]
        logger.debug(f"Параметр {param_name}: {value[:20] if value else ''}... (из кэша)")
        return value

    try:
        root_dir = Path(__file__).parent.parent.parent
        config_path = root_dir / 'global.conf'

        if not config_path.exists():
            logger.warning(f"Файл global.conf не найден, возвращаю значение по умолчанию: {default}")
            return default

        with open(config_path, 'r', encoding='utf-8') as config_file:
            for line in config_file:
                line = line.strip()

                if not line or line.startswith('#'):
                    continue

                if '=' in line:
                    name, value = line.split('=', 1)
                    name = name.strip()

                    if name == param_name:
                        value = value.strip().strip('\'"')

                        # Добавляем в кэш
                        _CONFIG_CACHE[param_name] = value

                        logger.debug(f"Параметр {param_name}: {value[:20] if value else ''}... (из файла)")
                        return value

        logger.debug(f"Параметр {param_name} не найден, возвращаю значение по умолчанию: {default}")
        return default

    except Exception as e:
        logger.error(f"Ошибка при чтении global.conf файла: {e}")
        return default


def init_local_config_check() -> bool:
    """
    Инициализация проверки global.conf файла при запуске приложения

    Returns:
        bool: True если файл существует, иначе False
    """
    return check_local_config_exists()


def get_cache_stats() -> Dict[str, Any]:
    """Получение статистики кэша (для отладки)"""
    return {
        'cache_size': len(_CONFIG_CACHE),
        'cache_keys': list(_CONFIG_CACHE.keys())
    }


def clear_cache():
    """Очистка кэша (для тестирования)"""
    global _CONFIG_CACHE
    _CONFIG_CACHE = {}
    logger.debug("Кэш global.conf очищен")