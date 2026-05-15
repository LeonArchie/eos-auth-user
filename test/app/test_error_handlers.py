# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest


pytestmark = pytest.mark.unit


class TestErrorHandlers:
    """Тесты обработчиков ошибок"""
    
    def test_not_found_response_structure(self, app):
        """Тест структуры ответа 404"""
        from handlers.error_handlers import not_found
        
        with app.test_request_context():
            response = not_found(Exception("Not found"))
            data = response.get_json()
            
            assert data['status'] is False
            assert data['code'] == 404
            assert data['body']['message'] == 'Not Found'
            assert response.status_code == 404
    
    def test_internal_server_error_response(self, app):
        """Тест ответа 500 Internal Server Error"""
        from handlers.error_handlers import internal_server_error
        
        with app.test_request_context():
            response = internal_server_error(Exception("Database connection failed"))
            data = response.get_json()
            
            assert data['code'] == 500
            assert data['body']['message'] == 'Internal Server Error'
            assert data['body']['detail'] == 'Database connection failed'
            assert response.status_code == 500
    
    def test_internal_server_error_without_detail(self, app):
        """Тест 500 без деталей ошибки"""
        from handlers.error_handlers import internal_server_error
        
        with app.test_request_context():
            response = internal_server_error(Exception())
            data = response.get_json()
            
            assert data['body']['detail'] == 'An unexpected error occurred'
    
    def test_not_implemented_response(self, app):
        """Тест ответа 501 Not Implemented"""
        from handlers.error_handlers import not_implemented
        
        with app.test_request_context():
            response = not_implemented(Exception())
            data = response.get_json()
            
            assert data['code'] == 501
            assert data['body']['message'] == 'Not Implemented'
            assert response.status_code == 501
    
    def test_bad_gateway_response(self, app):
        """Тест ответа 502 Bad Gateway"""
        from handlers.error_handlers import bad_gateway
        
        with app.test_request_context():
            response = bad_gateway(Exception())
            data = response.get_json()
            
            assert data['code'] == 502
            assert data['body']['message'] == 'Bad Gateway'
            assert response.status_code == 502
    
    def test_service_unavailable_response(self, app):
        """Тест ответа 503 Service Unavailable"""
        from handlers.error_handlers import service_unavailable
        
        with app.test_request_context():
            response = service_unavailable(Exception())
            data = response.get_json()
            
            assert data['code'] == 503
            assert data['body']['message'] == 'Service Unavailable'
            assert response.status_code == 503
    
    def test_gateway_timeout_response(self, app):
        """Тест ответа 504 Gateway Timeout"""
        from handlers.error_handlers import gateway_timeout
        
        with app.test_request_context():
            response = gateway_timeout(Exception())
            data = response.get_json()
            
            assert data['code'] == 504
            assert data['body']['message'] == 'Gateway Timeout'
            assert response.status_code == 504
    
    def test_http_version_not_supported_response(self, app):
        """Тест ответа 505 HTTP Version Not Supported"""
        from handlers.error_handlers import http_version_not_supported
        
        with app.test_request_context():
            response = http_version_not_supported(Exception())
            data = response.get_json()
            
            assert data['code'] == 505
            assert data['body']['message'] == 'HTTP Version Not Supported'
            assert response.status_code == 505
    
    def test_all_responses_have_required_fields(self, app):
        """Тест что все ответы имеют обязательные поля"""
        from handlers.error_handlers import (
            not_found, internal_server_error, not_implemented,
            bad_gateway, service_unavailable, gateway_timeout,
            http_version_not_supported
        )
        
        handlers = [
            not_found, internal_server_error, not_implemented,
            bad_gateway, service_unavailable, gateway_timeout,
            http_version_not_supported
        ]
        
        with app.test_request_context():
            for handler in handlers:
                response = handler(Exception("Test"))
                data = response.get_json()
                
                assert 'status' in data
                assert 'code' in data
                assert 'body' in data
                assert 'message' in data['body']
                assert data['status'] is False