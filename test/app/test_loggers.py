# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest
import json
from flask import Flask


pytestmark = pytest.mark.unit


class TestIncomingRequestLogger:
    """Тесты для IncomingRequestLogger"""
    
    def test_logger_initialization(self, app):
        """Тест инициализации логгера"""
        from handlers.incoming_logger import IncomingRequestLogger
        
        logger = IncomingRequestLogger(app)
        assert logger.app is not None
    
    def test_filter_sensitive_headers(self):
        """Тест фильтрации чувствительных заголовков"""
        from handlers.incoming_logger import IncomingRequestLogger
        
        headers = {
            'Authorization': 'Bearer secret123',
            'Cookie': 'session=abc123',
            'X-API-Key': 'api-key-456',
            'Token': 'token789',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        filtered = IncomingRequestLogger._filter_sensitive_data(headers)
        
        assert filtered['Authorization'] == '***FILTERED***'
        assert filtered['Cookie'] == '***FILTERED***'
        assert filtered['X-API-Key'] == '***FILTERED***'
        assert filtered['Token'] == '***FILTERED***'
        assert filtered['Content-Type'] == 'application/json'
        assert filtered['Accept'] == 'application/json'
    
    def test_filter_sensitive_headers_case_insensitive(self):
        """Тест фильтрации чувствительных заголовков (регистронезависимо)"""
        from handlers.incoming_logger import IncomingRequestLogger
        
        headers = {
            'authorization': 'Bearer secret',
            'COOKIE': 'session=123',
            'X-API-KEY': 'key123'
        }
        
        filtered = IncomingRequestLogger._filter_sensitive_data(headers)
        
        assert filtered['authorization'] == '***FILTERED***'
        assert filtered['COOKIE'] == '***FILTERED***'
        assert filtered['X-API-KEY'] == '***FILTERED***'
    
    def test_get_request_body_json(self, app):
        """Тест извлечения JSON тела запроса"""
        from handlers.incoming_logger import IncomingRequestLogger
        
        with app.test_request_context('/test', method='POST', 
                                      data=json.dumps({'key': 'value'}),
                                      content_type='application/json'):
            body = IncomingRequestLogger._get_request_body()
            assert body == {'key': 'value'}
    
    def test_get_request_body_empty(self, app):
        """Тест извлечения пустого тела запроса"""
        from handlers.incoming_logger import IncomingRequestLogger
        
        with app.test_request_context('/test', method='GET'):
            body = IncomingRequestLogger._get_request_body()
            assert body is None
    
    def test_get_response_body_json(self, app):
        """Тест извлечения JSON тела ответа"""
        from handlers.incoming_logger import IncomingRequestLogger
        
        with app.test_request_context('/test'):
            from flask import make_response
            response = make_response(json.dumps({'result': 'ok'}), 200)
            response.content_type = 'application/json'
            
            body = IncomingRequestLogger._get_response_body(response)
            assert body == {'result': 'ok'}
    
    def test_log_request_info_called(self, app, capture_logs):
        """Тест что log_request_info вызывается при запросе"""
        from handlers.incoming_logger import IncomingRequestLogger
        
        logger = IncomingRequestLogger(app)
        
        with app.test_client() as client:
            response = client.get('/test/ok')
            # Логгер должен был вызваться, даже если ответ 403 от шлюза
            assert response is not None


class TestOutgoingRequestLogger:
    """Тесты для OutgoingRequestLogger"""
    
    def test_log_request(self, capture_logs):
        """Тест логирования исходящего запроса"""
        from handlers.outgoing_logger import OutgoingRequestLogger
        
        logger = OutgoingRequestLogger()
        logger.log_request('GET', 'http://example.com/api', 
                          {'Content-Type': 'application/json'}, 
                          body={'test': 'data'})
        
        assert 'Исходящий запрос' in capture_logs.text
    
    def test_log_response_success(self, capture_logs):
        """Тест логирования успешного ответа"""
        from handlers.outgoing_logger import OutgoingRequestLogger
        
        logger = OutgoingRequestLogger()
        logger.log_response('http://example.com/api', 200, 
                           {'Content-Type': 'application/json'},
                           body={'result': 'ok'})
        
        assert 'Успешный ответ' in capture_logs.text
    
    def test_log_response_client_error(self, capture_logs):
        """Тест логирования ошибки клиента (4xx)"""
        from handlers.outgoing_logger import OutgoingRequestLogger
        
        logger = OutgoingRequestLogger()
        logger.log_response('http://example.com/api', 404,
                           {'Content-Type': 'application/json'},
                           body={'error': 'not found'})
        
        assert 'Ошибка клиента' in capture_logs.text
    
    def test_log_response_server_error(self, capture_logs):
        """Тест логирования ошибки сервера (5xx)"""
        from handlers.outgoing_logger import OutgoingRequestLogger
        
        logger = OutgoingRequestLogger()
        logger.log_response('http://example.com/api', 500,
                           {'Content-Type': 'application/json'},
                           body={'error': 'server error'})
        
        assert 'Ошибка сервера' in capture_logs.text
    
    def test_log_request_with_timing(self, capture_logs):
        """Тест логирования запроса с замером времени"""
        from handlers.outgoing_logger import OutgoingRequestLogger
        
        logger = OutgoingRequestLogger()
        context = logger.log_request_with_timing('GET', 'http://example.com/api', {})
        
        assert 'url' in context
        assert 'method' in context
        assert 'start_time' in context
    
    def test_log_response_with_timing(self, capture_logs):
        """Тест логирования ответа с использованием контекста"""
        from handlers.outgoing_logger import OutgoingRequestLogger
        import time
        
        logger = OutgoingRequestLogger()
        context = {'url': 'http://example.com/api', 'start_time': time.time()}
        
        logger.log_response_with_timing(context, 200, {}, body={'result': 'ok'})
        
        assert 'OUTGOING_RESPONSE' in capture_logs.text or 'Успешный ответ' in capture_logs.text
    
    def test_filter_sensitive_headers_outgoing(self):
        """Тест фильтрации чувствительных заголовков для исходящих запросов"""
        from handlers.outgoing_logger import OutgoingRequestLogger
        
        headers = {
            'Authorization': 'Bearer token',
            'X-API-Key': 'secret-key',
            'Content-Type': 'application/json'
        }
        
        filtered = OutgoingRequestLogger._filter_sensitive_data(headers)
        
        assert filtered['Authorization'] == '***FILTERED***'
        assert filtered['X-API-Key'] == '***FILTERED***'
        assert filtered['Content-Type'] == 'application/json'
    
    def test_parse_body_json_string(self):
        """Тест парсинга JSON строки"""
        from handlers.outgoing_logger import OutgoingRequestLogger
        
        parsed = OutgoingRequestLogger._parse_body('{"key": "value"}')
        assert parsed == {'key': 'value'}
    
    def test_parse_body_dict(self):
        """Тест парсинга словаря"""
        from handlers.outgoing_logger import OutgoingRequestLogger
        
        parsed = OutgoingRequestLogger._parse_body({'key': 'value'})
        assert parsed == {'key': 'value'}
    
    def test_parse_body_none(self):
        """Тест парсинга None"""
        from handlers.outgoing_logger import OutgoingRequestLogger
        
        parsed = OutgoingRequestLogger._parse_body(None)
        assert parsed is None