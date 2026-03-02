# maintenance/configurations/get_env_config.py
# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import sys
import logging
from typing import Optional
from pathlib import Path
from maintenance.flag_state import get_env_flag, set_env_flag

logger = logging.getLogger(__name__)


def check_env_file_exists() -> int:
    """
    Проверка существования .env файла в корне приложения
    
    Returns:
        int: 1 если файл существует, иначе завершает программу с кодом 2
    """
    root_dir = Path(__file__).parent.parent.parent
    env_path = root_dir / '.env'
    
    if env_path.exists():
        set_env_flag(1)
        logger.debug("Файл .env найден")
        return 1
    else:
        set_env_flag(0)
        print("Файл .env не найден")
        sys.exit(2)


def get_env_config(param_name: str) -> Optional[str]:
    """
    Получение значения параметра из .env файла
    
    Args:
        param_name (str): Имя параметра для поиска в .env файле
        
    Returns:
        str or None: Значение параметра или None если параметр не найден
    """
    logger.debug(f"Передан параметр {param_name}")
    
    # Проверяем существование .env файла если флаг еще не установлен
    if get_env_flag() == 0:
        check_env_file_exists()
    
    # Если .env файл не существует, возвращаем None
    if get_env_flag() == 0:
        return None
    
    try:
        root_dir = Path(__file__).parent.parent.parent
        env_path = root_dir / '.env'
        
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
                        return value
        
        logger.debug(f"Параметр {param_name} не найден в .env файле")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка при чтении .env файла: {e}")
        return None


def init_env_check() -> int:
    """
    Инициализация проверки .env файла при запуске приложения
    
    Returns:
        int: 1 если файл существует, иначе завершает программу с кодом 2
    """
    return check_env_file_exists()