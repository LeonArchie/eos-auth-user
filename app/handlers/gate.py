# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

"""
Сервис-шлюз для валидации всех входящих запросов.
Проверяет метод запроса, заголовки и структуру тела по схемам из schemas.yaml.
Все пути должны быть описаны в schemas.yaml (регулярными выражениями), иначе запрос блокируется.
"""

import re
import yaml
import json
import logging
import time
import uuid
from typing import Dict, Any, Optional, List, Pattern, Union
from pathlib import Path
from flask import request, current_app, g

logger = logging.getLogger(__name__)

# Кэш для загруженных схем
_schemas_cache: Optional[List[Dict[str, Any]]] = None
_compiled_patterns_cache: Dict[str, Pattern] = {}

# Флаг состояния шлюза
_gate_healthy: bool = True
_gate_init_error: Optional[str] = None


class GateValidationError(Exception):
    """Кастомное исключение для ошибок валидации"""
    pass


def load_schemas() -> List[Dict[str, Any]]:
    """
    Загружает схемы валидации из schemas.yaml с кэшированием.

    :return: Список правил валидации
    :raises: GateValidationError если файл не найден или некорректен
    """
    global _schemas_cache, _gate_healthy, _gate_init_error

    if _schemas_cache is not None:
        logger.debug(f"Использование кэшированных схем ({len(_schemas_cache)} правил)")
        return _schemas_cache

    start_time = time.time()
    logger.info("Начало загрузки схем валидации из schemas.yaml")

    try:
        current_dir = Path(__file__).parent.parent
        schema_path = current_dir / 'schemas.yaml'

        if not schema_path.exists():
            error_msg = f"Файл схем не найден: {schema_path}"
            logger.error(error_msg)
            _gate_healthy = False
            _gate_init_error = error_msg
            raise GateValidationError(error_msg)

        with open(schema_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        if not isinstance(config, dict) or 'gate' not in config:
            error_msg = "Файл схем должен содержать корневой ключ 'gate'"
            logger.error(error_msg)
            _gate_healthy = False
            _gate_init_error = error_msg
            raise GateValidationError(error_msg)

        api_rules = config.get('gate', {}).get('api', [])

        if not isinstance(api_rules, list):
            error_msg = "Поле 'gate.api' должно быть списком"
            logger.error(error_msg)
            _gate_healthy = False
            _gate_init_error = error_msg
            raise GateValidationError(error_msg)

        normalized_rules = []
        skipped_rules = 0

        for idx, rule in enumerate(api_rules):
            if isinstance(rule, dict) and 'rule' in rule:
                try:
                    normalized_rule = normalize_rule(rule['rule'])
                    rule_name = rule.get('name', f'unnamed_{idx}')
                    normalized_rule['name'] = rule_name
                    normalized_rule['rqid'] = rule.get('rule', {}).get('rqid', False)
                    normalized_rules.append(normalized_rule)
                except Exception as e:
                    logger.warning(f"Ошибка нормализации правила #{idx}: {e}")
                    skipped_rules += 1
            else:
                logger.warning(f"Пропущено некорректное правило #{idx}: отсутствует ключ 'rule'")
                skipped_rules += 1

        _schemas_cache = normalized_rules
        _gate_healthy = True
        _gate_init_error = None

        load_time = time.time() - start_time
        logger.info(f"Загружено {len(normalized_rules)} правил валидации (пропущено: {skipped_rules}) за {load_time:.3f}с")

        return normalized_rules

    except yaml.YAMLError as e:
        error_msg = f"Ошибка парсинга YAML: {str(e)}"
        logger.error(error_msg)
        _gate_healthy = False
        _gate_init_error = error_msg
        raise GateValidationError(error_msg)
    except Exception as e:
        error_msg = f"Неожиданная ошибка при загрузке схем: {str(e)}"
        logger.error(error_msg, exc_info=True)
        _gate_healthy = False
        _gate_init_error = error_msg
        raise GateValidationError(error_msg)


def normalize_rule(rule: Any) -> Dict:
    """Нормализует правило к единому формату."""
    normalized = {
        'path': rule.get('path', ''),
        'method': rule.get('method', '').upper() if rule.get('method') else None,
        'headers': rule.get('headers', []) or [],
        'body': rule.get('body', []) or []
    }

    headers = []
    for header in normalized['headers']:
        if isinstance(header, dict):
            headers.append({
                'name': header.get('name', '').lower(),
                'value': header.get('value', '')
            })
    normalized['headers'] = headers

    body = normalized['body']

    if isinstance(body, str) and body == '*':
        normalized['body'] = '*'

    elif not body or (isinstance(body, list) and len(body) == 0):
        normalized['body'] = {}

    elif isinstance(body, list):
        body_fields = {}
        for field in body:
            if isinstance(field, dict):
                for field_name, pattern in field.items():
                    body_fields[field_name] = pattern
            elif isinstance(field, str):
                body_fields[field] = '.*'
        normalized['body'] = body_fields

    else:
        logger.warning(f"Неизвестный формат тела запроса: {type(body)}")
        normalized['body'] = body

    return normalized


def compile_path_pattern(pattern: str) -> Pattern:
    """Компилирует регулярное выражение для пути с кэшированием."""
    if pattern in _compiled_patterns_cache:
        return _compiled_patterns_cache[pattern]

    try:
        compiled = re.compile(pattern)
        _compiled_patterns_cache[pattern] = compiled
        return compiled
    except re.error as e:
        logger.error(f"Ошибка компиляции regex '{pattern}': {e}")
        raise GateValidationError(f"Некорректное регулярное выражение: {pattern}")


def find_matching_rule(request_path: str) -> Optional[Dict]:
    """Находит правило, соответствующее пути запроса."""
    rules = load_schemas()

    for rule in rules:
        path_pattern = rule.get('path', '')
        if not path_pattern:
            continue

        compiled_pattern = compile_path_pattern(path_pattern)
        if compiled_pattern.match(request_path):
            return rule

    logger.warning(f"Правило не найдено для пути: {request_path}")
    return None


def validate_method(allowed_method: Optional[str], request_method: str) -> bool:
    """Проверяет разрешен ли метод запроса."""
    if allowed_method is None:
        return False
    return request_method.upper() == allowed_method.upper()


def validate_rqid(expected_rqid: bool, request_headers) -> bool:
    """Проверяет наличие и корректность заголовка Rqid."""
    if not expected_rqid:
        return True

    rqid_header = None
    for header_name in request_headers.keys():
        if header_name.lower() == 'rqid':
            rqid_header = header_name
            break

    if not rqid_header:
        logger.warning("Отсутствует обязательный заголовок Rqid")
        return False

    rqid_value = request_headers.get(rqid_header, '')

    try:
        uuid.UUID(rqid_value)
        return True
    except (ValueError, AttributeError, TypeError) as e:
        logger.warning(f"Rqid имеет некорректный формат UUID: {rqid_value}, ошибка: {e}")
        return False


def validate_headers_exact(expected_headers: List[Dict], request_headers) -> bool:
    """Строгая проверка заголовков запроса."""
    if not expected_headers:
        return True

    expected_pairs = {}
    for header in expected_headers:
        name = header.get('name', '').lower()
        value = header.get('value', '')

        if not name or not value:
            logger.warning(f"Некорректное правило заголовка: name='{name}', value='{value}'")
            return False

        if name not in expected_pairs:
            expected_pairs[name] = []
        expected_pairs[name].append(value)

    found_match = False

    for header_name in request_headers.keys():
        header_name_lower = header_name.lower()

        if header_name_lower in expected_pairs:
            actual_value = request_headers.get(header_name)
            expected_values = expected_pairs[header_name_lower]

            if actual_value in expected_values:
                if found_match:
                    logger.warning(f"Найдено второе совпадение для заголовка {header_name}={actual_value}")
                    return False
                found_match = True
            else:
                logger.warning(f"Заголовок {header_name} имеет неверное значение: '{actual_value}'")
                return False

    if not found_match:
        logger.warning(f"Не найдено ни одного подходящего заголовка из ожидаемых: {expected_pairs}")
        return False

    return True


def validate_field(value: Any, pattern: str) -> bool:
    """Проверяет значение поля по regex-паттерну."""
    try:
        str_value = str(value) if value is not None else ""
        return bool(re.match(pattern, str_value))
    except (TypeError, re.error):
        return False


def validate_body_structure(expected_body: Union[Dict, str], actual_body: Dict) -> bool:
    """Проверяет структуру тела запроса."""
    if expected_body == '*':
        return True

    if expected_body == {}:
        if actual_body:
            logger.warning(f"Тело не ожидается, но получены данные: {list(actual_body.keys())}")
            return False
        return True

    if isinstance(expected_body, dict):
        expected_fields = set(expected_body.keys())
        actual_fields = set(actual_body.keys())

        if expected_fields != actual_fields:
            missing = expected_fields - actual_fields
            extra = actual_fields - expected_fields
            if missing:
                logger.warning(f"Отсутствуют поля: {missing}")
            if extra:
                logger.warning(f"Лишние поля: {extra}")
            return False

        for field_name, pattern in expected_body.items():
            if field_name not in actual_body:
                return False
            if not validate_field(actual_body[field_name], pattern):
                logger.warning(f"Поле {field_name} не соответствует паттерну {pattern}")
                return False

        return True

    logger.error(f"Неизвестный формат expected_body: {type(expected_body)}")
    return False


def extract_request_body() -> Dict:
    """Извлекает тело запроса в зависимости от Content-Type."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    elif request.form:
        return request.form.to_dict()
    elif request.data:
        try:
            return json.loads(request.data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug(f"Не удалось распарсить сырые данные как JSON: {e}")
            return {}
    else:
        return {}


def gate_middleware(app):
    """Middleware для Flask, выполняющий валидацию всех запросов."""

    @app.before_request
    def validate_request():
        global _gate_healthy, _gate_init_error

        g.start_time = time.time()
        logger.info(f"→ {request.method} {request.path} (IP: {request.remote_addr})")

        if not _gate_healthy:
            logger.error(f"Шлюз нездоров: {_gate_init_error}")
            return "Gateway initialization failed", 504

        try:
            request_path = request.path
            rule = find_matching_rule(request_path)

            if rule is None:
                logger.warning(f"Запрос отклонен: путь {request_path} не описан в schemas.yaml")
                return "", 403

            if not validate_method(rule.get('method'), request.method):
                logger.warning(f"Запрос отклонен: неверный метод {request.method} для {request_path}")
                return "", 403

            if not validate_headers_exact(rule.get('headers', []), request.headers):
                logger.warning(f"Запрос отклонен: ошибка проверки заголовков для {request_path}")
                return "", 403

            if not validate_rqid(rule.get('rqid', False), request.headers):
                logger.warning(f"Запрос отклонен: неверный или отсутствующий Rqid для {request_path}")
                return "", 403

            expected_body = rule.get('body', {})
            actual_body = extract_request_body()

            if not validate_body_structure(expected_body, actual_body):
                logger.warning(f"Запрос отклонен: неверная структура тела для {request_path}")
                return "", 403

            if not hasattr(current_app, 'gate_context'):
                current_app.gate_context = {}

            current_app.gate_context['validated'] = True
            current_app.gate_context['rule'] = rule.get('name')

            process_time = time.time() - g.start_time
            logger.info(f"Запрос {request.path} успешно прошел валидацию по правилу '{rule.get('name')}' (обработка: {process_time:.3f}с)")
            return None

        except GateValidationError as e:
            logger.error(f"Ошибка валидации: {e}")
            return "Gateway validation error", 504
        except Exception as e:
            logger.error(f"Неожиданная ошибка при валидации запроса: {str(e)}", exc_info=True)
            return "Internal gateway error", 504

    @app.after_request
    def log_response(response):
        if hasattr(g, 'start_time'):
            process_time = time.time() - g.start_time
            logger.info(f"← {response.status_code} ({process_time:.3f}с)")
        else:
            logger.info(f"← {response.status_code}")
        return response

    return app


def init_gate(app):
    """Инициализирует шлюз для приложения."""
    global _gate_healthy, _gate_init_error

    logger.info("Инициализация сервиса-шлюза (gate)")

    try:
        start_time = time.time()
        rules = load_schemas()
        load_time = time.time() - start_time

        logger.info(f"Успешно загружено {len(rules)} правил валидации за {load_time:.3f}с")

        gate_middleware(app)
        logger.info("Сервис-шлюз успешно инициализирован")

    except GateValidationError as e:
        logger.error(f"Критическая ошибка инициализации шлюза: {e}")
        _gate_healthy = False
        _gate_init_error = str(e)
        gate_middleware(app)
        logger.warning("Шлюз инициализирован в аварийном режиме - все запросы будут отклоняться с кодом 504")

    except Exception as e:
        logger.error(f"Неожиданная ошибка инициализации шлюза: {str(e)}", exc_info=True)
        _gate_healthy = False
        _gate_init_error = str(e)
        gate_middleware(app)
        logger.warning("Шлюз инициализирован в аварийном режиме - все запросы будут отклоняться с кодом 504")

    return app


def get_gate_status() -> Dict[str, Any]:
    """Возвращает статус шлюза для мониторинга."""
    return {
        'healthy': _gate_healthy,
        'error': _gate_init_error,
        'rules_loaded': len(_schemas_cache) if _schemas_cache else 0
    }