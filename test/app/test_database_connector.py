# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest
from unittest.mock import MagicMock, patch


pytestmark = pytest.mark.unit


class TestDatabaseConnector:
    """Тесты для DatabaseConnector"""
    
    def test_is_db_enabled_false(self, temp_project_dir, monkeypatch):
        """Тест проверки что БД отключена в тестовой конфигурации"""
        monkeypatch.chdir(temp_project_dir)
        
        from maintenance.database_connector import is_db_enabled
        
        assert is_db_enabled() is False
    
    def test_get_db_connector_singleton(self):
        """Тест что get_db_connector возвращает синглтон"""
        from maintenance.database_connector import get_db_connector
        
        connector1 = get_db_connector()
        connector2 = get_db_connector()
        
        assert connector1 is connector2
    
    def test_connector_initialized_false_by_default(self):
        """Тест что коннектор не инициализирован по умолчанию"""
        from maintenance.database_connector import DatabaseConnector
        
        connector = DatabaseConnector()
        assert connector.is_initialized() is False
    
    def test_connector_enabled_false_by_default(self):
        """Тест что БД отключена по умолчанию в тестах"""
        from maintenance.database_connector import get_db_connector
        
        connector = get_db_connector()
        assert connector.is_enabled() is False
    
    def test_is_database_healthy_when_disabled(self, temp_project_dir, monkeypatch):
        """Тест проверки здоровья когда БД отключена"""
        monkeypatch.chdir(temp_project_dir)
        
        from maintenance.database_connector import is_database_healthy
        
        # Когда БД отключена, is_database_healthy должна вернуть True
        assert is_database_healthy() is True
    
    def test_is_database_initialized_when_disabled(self, temp_project_dir, monkeypatch):
        """Тест проверки инициализации когда БД отключена"""
        monkeypatch.chdir(temp_project_dir)
        
        from maintenance.database_connector import is_database_initialized
        
        # Коннектор отмечен как инициализированный даже при отключенной БД
        assert is_database_initialized() is True


class TestDatabaseConnectorWithMocks:
    """Тесты DatabaseConnector с моками"""
    
    def test_connector_initialize_with_db_enabled(self, mocker):
        """Тест инициализации коннектора когда БД включена"""
        from maintenance.database_connector import DatabaseConnector
        
        # Мокаем is_db_enabled чтобы вернула True
        mocker.patch('maintenance.database_connector.is_db_enabled', return_value=True)
        mocker.patch('maintenance.database_connector._load_db_configuration', return_value={
            'user': 'test_user',
            'password': 'test_pass',
            'master_host': 'localhost',
            'master_port': '5432',
            'database': 'test_db',
            'pool_size': '5',
            'max_overflow': '10',
            'pool_timeout': '60',
            'pool_recycle': '3600',
            'pool_pre_ping': 'true',
            'max_retries': '5',
            'retry_delay': '5'
        })
        
        mock_app = MagicMock()
        mock_app.config = {}
        
        connector = DatabaseConnector()
        
        # Должен вызвать исключение из-за отсутствия реальной БД
        with pytest.raises(Exception):
            connector.initialize(mock_app)
    
    def test_get_session_when_disabled_raises_error(self):
        """Тест получения сессии когда БД отключена"""
        from maintenance.database_connector import DatabaseConnector
        
        connector = DatabaseConnector()
        connector._enabled = False
        connector._initialized = True
        
        with pytest.raises(RuntimeError, match="Попытка создать сессию при отключенной БД"):
            with connector.get_session():
                pass
    
    def test_close_when_disabled_does_nothing(self):
        """Тест закрытия когда БД отключена"""
        from maintenance.database_connector import DatabaseConnector
        
        connector = DatabaseConnector()
        connector._enabled = False
        connector._initialized = True
        
        # Не должно вызывать исключений
        connector.close()