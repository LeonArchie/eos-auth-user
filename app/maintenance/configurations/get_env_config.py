# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import sys
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def check_env_file_exists() -> bool:
    """
    Проверка существования .env файла в корне приложения

    Returns:
        bool: True если файл существует, иначе False
    """
    root_dir = Path(__file__).parent.parent.parent
    env_path = root_dir / '.env'

    if env_path.exists():
        logger.debug("Файл .env найден")
        return True
    else:
        logger.error("Файл .env не найден")
        return False


def get_env_config(param_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Получение значения параметра из .env файла

    Args:
        param_name (str): Имя параметра для поиска в .env файле
        default (str, optional): Значение по умолчанию, если параметр не найден

    Returns:
        str or None: Значение параметра или значение по умолчанию
    """
    logger.debug(f"Поиск параметра {param_name}")

    try:
        root_dir = Path(__file__).parent.parent.parent
        env_path = root_dir / '.env'

        if not env_path.exists():
            logger.warning(f"Файл .env не найден, возвращаю значение по умолчанию: {default}")
            return default

        with open(env_path, 'r', encoding='utf-8') as env_file:
            for line in env_file:
                line = line.strip()

                if not line or line.startswith('#'):
                    continue

                if '=' in line:
                    name, value = line.split('=', 1)
                    name = name.strip()

                    if name == param_name:
                        value = value.strip().strip('\'"')
                        logger.debug(f"Найден параметр {param_name}: {value[:10] if value else ''}...")
                        return value

        logger.debug(f"Параметр {param_name} не найден в .env файле, возвращаю значение по умолчанию: {default}")
        return default

    except Exception as e:
        logger.error(f"Ошибка при чтении .env файла: {e}")
        return default


def init_env_check() -> bool:
    """
    Инициализация проверки .env файла при запуске приложения

    Returns:
        bool: True если файл существует, иначе False
    """
    return check_env_file_exists()