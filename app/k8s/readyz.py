# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

from flask import Blueprint, jsonify
import logging

from maintenance.database_connector import is_database_healthy, is_database_initialized, is_database_enabled
from maintenance.configurations.get_env_config import check_env_file_exists
from maintenance.configurations.get_local_config import check_local_config_exists
from maintenance.configurations.get_global_config import check_global_config_available

logger = logging.getLogger(__name__)

readyz_bp = Blueprint('readyz', __name__)


def _check_all_components():
    """
    Проверка всех компонентов для readiness пробы:
    - .env файл
    - global.conf файл
    - глобальный сервис конфигураций
    - база данных (только если она включена)

    Returns:
        tuple: (успех, список проблем)
    """
    issues = []

    # Проверяем .env файл
    env_exists = check_env_file_exists()
    if not env_exists:
        issues.append(".env файл отсутствует")

    # Проверяем global.conf файл
    local_exists = check_local_config_exists()
    if not local_exists:
        issues.append("global.conf файл отсутствует")

    # Проверяем доступность глобального сервиса конфигураций
    global_available = check_global_config_available()
    if not global_available:
        issues.append("Глобальный сервис конфигураций недоступен")

    # Проверяем базу данных только если она включена
    db_enabled = is_database_enabled()
    
    if db_enabled:
        db_initialized = is_database_initialized()
        db_healthy = is_database_healthy()

        if not db_initialized:
            issues.append("База данных не инициализирована")
        elif not db_healthy:
            issues.append("База данных нездорова")
    else:
        logger.info("Проверка БД пропущена - база данных отключена в конфигурации")

    return len(issues) == 0, issues


@readyz_bp.route('/readyz', methods=['GET'])
def readyz():
    """
    Readiness проба для Kubernetes.
    Проверяет, что сервис готов принимать трафик.

    Returns:
        200 OK: если все необходимые компоненты доступны
        503 Service Unavailable: если хотя бы один компонент недоступен
    """
    logger.debug("Проверка readiness (готовности) сервиса")

    all_ok, issues = _check_all_components()
    
    db_enabled = is_database_enabled()

    response_data = {
        "status": all_ok,
        "message": "Service is ready to accept traffic" if all_ok else "Service is not ready",
        "checks": {
            "env_file": check_env_file_exists(),
            "local_config": check_local_config_exists(),
            "global_config": check_global_config_available(),
            "database_enabled": db_enabled,
            "database_initialized": is_database_initialized() if db_enabled else None,
            "database_healthy": is_database_healthy() if db_enabled else None
        }
    }

    if not all_ok:
        response_data["issues"] = issues
        logger.warning(f"Readiness проверка не пройдена: {', '.join(issues)}")
        return jsonify(response_data), 503

    logger.debug("Readiness проверка успешна")
    return jsonify(response_data), 200