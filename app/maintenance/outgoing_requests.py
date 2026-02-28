# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import logging
from pathlib import Path
from typing import Optional
from functools import wraps
import requests

# Настройка логгера
logger = logging.getLogger(__name__)

# Глобальная переменная для хранения MODULE_ID
_module_id: Optional[str] = None

def _load_module_id_from_config() -> str:
    """
    Загружает MODULE_ID из файла global.conf
    """
    # Определяем путь к global.conf
    current_dir = Path(__file__).parent.parent
    config_file_path = current_dir / 'global.conf'
    
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('MODULE_ID='):
                    module_id = line.split('=', 1)[1].strip()
                    if module_id:
                        logger.info(f"MODULE_ID загружен: {module_id}")
                        return module_id
        
        logger.warning("MODULE_ID не найден в global.conf")
        return ""
        
    except Exception as e:
        logger.error(f"Ошибка загрузки MODULE_ID: {e}")
        return ""

def get_module_id() -> str:
    """
    Получение MODULE_ID с ленивой загрузкой
    """
    global _module_id
    
    if _module_id is None:
        _module_id = _load_module_id_from_config()
    
    return _module_id

def inject_module_id_to_requests():
    """
    Модифицирует стандартные функции requests для автоматического добавления MODULE-ID
    """
    module_id = get_module_id()
    
    if not module_id:
        logger.warning("MODULE-ID не найден, инъекция не выполнена")
        return
    
    original_request = requests.Session.request
    
    @wraps(original_request)
    def wrapped_request(session, method, url, **kwargs):
        # Добавляем MODULE-ID к заголовкам
        headers = kwargs.get('headers', {})
        headers['MODULE-ID'] = module_id
        kwargs['headers'] = headers
        logger.debug(f"Добавлен заголовок MODULE-ID к {method} {url}")
        return original_request(session, method, url, **kwargs)
    
    # Заменяем метод request в Session
    requests.Session.request = wrapped_request
    logger.debug(f"Глобальная инъекция MODULE-ID выполнена: {module_id}")

# Автоматически выполняем инъекцию при импорте модуля
inject_module_id_to_requests()