# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

from flask import Blueprint, jsonify
import logging

# Импорт для проверки конфигурации
from maintenance.configurations.get_env_config import check_env_file_exists
from maintenance.configurations.get_local_config import check_local_config_exists
from maintenance.configurations.get_global_config import check_global_config_available

logger = logging.getLogger(__name__)

healthz_bp = Blueprint('healthz', __name__)


def _check_critical_components():
    """
    Проверка критических компонентов для liveness пробы:
    - .env файл
    - global.conf файл
    - глобальный сервис конфигураций

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

    return len(issues) == 0, issues


@healthz_bp.route('/healthz', methods=['GET'])
def healthz():
    """
    Liveness проба для Kubernetes.
    Проверяет, что сервис жив и может функционировать.

    Returns:
        200 OK: если все критические компоненты доступны
        503 Service Unavailable: если хотя бы один компонент недоступен
    """
    logger.debug("Проверка liveness (живости) сервиса")

    all_ok, issues = _check_critical_components()

    response_data = {
        "status": all_ok,
        "message": "Service is alive" if all_ok else "Service is not alive",
        "checks": {
            "env_file": check_env_file_exists(),
            "local_config": check_local_config_exists(),
            "global_config": check_global_config_available()
        }
    }

    if not all_ok:
        response_data["issues"] = issues
        logger.warning(f"Liveness проверка не пройдена: {', '.join(issues)}")
        return jsonify(response_data), 503

    logger.debug("Liveness проверка успешна")
    return jsonify(response_data), 200