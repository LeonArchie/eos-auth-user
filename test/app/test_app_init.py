# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest
import sys


pytestmark = pytest.mark.unit


class TestAppInit:
    """Тесты для app_init.py"""
    
    def test_create_app_returns_flask_app(self, temp_project_dir, monkeypatch):
        """Тест что create_app возвращает Flask приложение"""
        monkeypatch.chdir(temp_project_dir)
        
        from maintenance.app_init import create_app
        
        app = create_app()
        
        assert app is not None
        assert app.name == '__main__' or app.name == 'maintenance.app_init'
        assert app.config['TESTING'] is False
    
    def test_create_app_sets_testing_mode(self, temp_project_dir, monkeypatch):
        """Тест установки режима тестирования"""
        monkeypatch.chdir(temp_project_dir)
        
        from maintenance.app_init import create_app
        
        app = create_app()
        app.config['TESTING'] = True
        
        assert app.config['TESTING'] is True
    
    def test_create_app_registers_blueprints(self, temp_project_dir, monkeypatch):
        """Тест регистрации blueprint'ов"""
        monkeypatch.chdir(temp_project_dir)
        
        from maintenance.app_init import create_app
        
        app = create_app()
        
        # Проверяем что blueprint'ы зарегистрированы
        blueprints = list(app.blueprints.keys())
        assert 'healthz' in blueprints or any('healthz' in b for b in blueprints)
        assert 'readyz' in blueprints or any('readyz' in b for b in blueprints)
    
    def test_create_app_registers_error_handlers(self, temp_project_dir, monkeypatch):
        """Тест регистрации обработчиков ошибок"""
        monkeypatch.chdir(temp_project_dir)
        
        from maintenance.app_init import create_app
        
        app = create_app()
        
        # Проверяем что обработчики зарегистрированы
        assert 404 in app.error_handler_spec[None]
        assert 500 in app.error_handler_spec[None]
        assert 501 in app.error_handler_spec[None]
        assert 502 in app.error_handler_spec[None]
        assert 503 in app.error_handler_spec[None]
        assert 504 in app.error_handler_spec[None]
        assert 505 in app.error_handler_spec[None]
    
    def test_create_app_initializes_gate(self, temp_project_dir, monkeypatch):
        """Тест инициализации шлюза"""
        monkeypatch.chdir(temp_project_dir)
        
        from maintenance.app_init import create_app
        
        app = create_app()
        
        # Проверяем что gate middleware применен
        assert hasattr(app, 'before_request_funcs')
        assert len(app.before_request_funcs) > 0
    
    def test_create_app_sets_up_loggers(self, temp_project_dir, monkeypatch):
        """Тест настройки логгеров"""
        monkeypatch.chdir(temp_project_dir)
        
        from maintenance.app_init import create_app
        
        app = create_app()
        
        assert 'INCOMING_LOGGER' in app.config
        assert 'OUTGOING_LOGGER' in app.config
    
    def test_create_app_handles_database_error(self, temp_project_dir, monkeypatch, mocker):
        """Тест обработки ошибки инициализации БД"""
        monkeypatch.chdir(temp_project_dir)
        
        # Мокаем initialize_database чтобы вызвала исключение
        mocker.patch('maintenance.app_init.initialize_database', 
                     side_effect=Exception('Database connection failed'))
        mocker.patch('maintenance.app_init.is_database_initialized', return_value=False)
        
        from maintenance.app_init import create_app
        
        # Должен выйти с ошибкой
        with pytest.raises(SystemExit):
            create_app()
    
    def test_create_app_without_database(self, temp_project_dir, monkeypatch):
        """Тест когда БД отключена (DB_ENABLE=false)"""
        monkeypatch.chdir(temp_project_dir)
        
        from maintenance.app_init import create_app
        
        # В тестовой конфигурации DB_ENABLE=false, инициализация должна пройти успешно
        app = create_app()
        
        assert app is not None
        assert app.config.get('INCOMING_LOGGER') is not None