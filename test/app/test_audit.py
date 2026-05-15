# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest
from freezegun import freeze_time


pytestmark = pytest.mark.unit


class TestAudit:
    """Тесты для модуля аудита"""
    
    def test_audit_success(self, temp_project_dir, monkeypatch, mocker, reset_audit_module):
        """Тест успешной отправки аудит события"""
        monkeypatch.chdir(temp_project_dir)
        
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_post = mocker.patch('requests.post', return_value=mock_response)
        
        from handlers.audit import audit
        
        with freeze_time("2024-01-01 12:00:00"):
            audit('object-123', 'user-456', 'Test audit message')
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Проверяем URL
        assert '/v1/create' in call_args[0][0]
        
        # Проверяем данные
        json_data = call_args[1]['json']
        assert json_data['object_id'] == 'object-123'
        assert json_data['initiator_id'] == 'user-456'
        assert json_data['message'] == 'Test audit message'
        assert json_data['module_name'] == 'Test-App'
        assert 'time' in json_data
    
    def test_audit_network_error(self, temp_project_dir, monkeypatch, mocker, 
                                  capture_logs, reset_audit_module):
        """Тест сетевой ошибки при отправке аудит события"""
        monkeypatch.chdir(temp_project_dir)
        
        mocker.patch('requests.post', side_effect=Exception('Network error'))
        
        from handlers.audit import audit
        
        audit('object-123', 'user-456', 'Test message')
        
        assert 'Сетевая ошибка' in capture_logs.text or 'Неожиданная ошибка' in capture_logs.text
    
    def test_audit_http_error_response(self, temp_project_dir, monkeypatch, mocker,
                                        capture_logs, reset_audit_module):
        """Тест HTTP ошибки при отправке аудит события"""
        monkeypatch.chdir(temp_project_dir)
        
        mock_response = mocker.Mock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_post = mocker.patch('requests.post', return_value=mock_response)
        
        from handlers.audit import audit
        
        audit('object-123', 'user-456', 'Test message')
        
        mock_post.assert_called_once()
        assert 'Ошибка отправки события аудита' in capture_logs.text
    
    def test_audit_timeout(self, temp_project_dir, monkeypatch, mocker,
                           capture_logs, reset_audit_module):
        """Тест таймаута при отправке аудит события"""
        monkeypatch.chdir(temp_project_dir)
        
        from requests.exceptions import Timeout
        mocker.patch('requests.post', side_effect=Timeout())
        
        from handlers.audit import audit
        
        audit('object-123', 'user-456', 'Test message')
        
        assert 'Сетевая ошибка' in capture_logs.text
    
    def test_audit_config_loading(self, temp_project_dir, monkeypatch, reset_audit_module):
        """Тест загрузки конфигурации аудита"""
        monkeypatch.chdir(temp_project_dir)
        
        import handlers.audit as audit_module
        
        # Сбрасываем состояние
        audit_module._module_name = None
        audit_module._audit_url = None
        
        # Вызываем функцию для загрузки конфига
        audit_module._ensure_initialized()
        
        assert audit_module._module_name == 'Test-App'
        assert audit_module._audit_url == 'http://test-audit-service:9443'
    
    def test_audit_missing_config_file(self, tmp_path, monkeypatch, reset_audit_module, capture_logs):
        """Тест когда файл конфигурации отсутствует"""
        monkeypatch.chdir(tmp_path)
        
        import handlers.audit as audit_module
        
        audit_module._module_name = None
        audit_module._audit_url = None
        
        with pytest.raises(FileNotFoundError):
            audit_module._ensure_initialized()
    
    def test_audit_invalid_json_response(self, temp_project_dir, monkeypatch, mocker,
                                          reset_audit_module):
        """Тест невалидного JSON ответа от сервиса аудита"""
        monkeypatch.chdir(temp_project_dir)
        
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = Exception('Invalid JSON')
        mocker.patch('requests.post', return_value=mock_response)
        
        from handlers.audit import audit
        
        # Не должно вызвать исключение
        audit('object-123', 'user-456', 'Test message')
    
    def test_audit_custom_timeout(self, temp_project_dir, monkeypatch, mocker, reset_audit_module):
        """Тест что используется правильный таймаут"""
        monkeypatch.chdir(temp_project_dir)
        
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_post = mocker.patch('requests.post', return_value=mock_response)
        
        from handlers.audit import audit
        
        audit('object-123', 'user-456', 'Test message')
        
        # Проверяем что timeout передан в запрос
        call_kwargs = mock_post.call_args[1]
        assert 'timeout' in call_kwargs
        assert call_kwargs['timeout'] == 10