# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest
import requests
import uuid
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.unit


class TestModuleIDInjector:
    """Тесты для ModuleIDInjector"""
    def test_module_id_injection(self, temp_project_dir, monkeypatch):
        """Тест инъекции MODULE-ID в заголовки"""
        import requests
        monkeypatch.chdir(temp_project_dir)
        
        from handlers.module_id_injector import ModuleIDInjector
        
        original_request = requests.Session.request
        
        try:
            injector = ModuleIDInjector()
            injector._module_id = 'TEST-MODULE'
            injector._injected = False
            result = injector.inject()
            
            assert result is True
            assert injector._injected is True
        finally:
            requests.Session.request = original_request
    
    def test_module_id_injection_idempotent(self, temp_project_dir, monkeypatch):
        """Тест что повторная инъекция не вызывает ошибок"""
        import requests
        monkeypatch.chdir(temp_project_dir)
        
        from handlers.module_id_injector import ModuleIDInjector
        
        original_request = requests.Session.request
        
        try:
            injector = ModuleIDInjector()
            injector._module_id = 'TEST-MODULE'
            injector._injected = False
            
            result1 = injector.inject()
            result2 = injector.inject()
            
            assert result1 is True
            assert result2 is True
        finally:
            requests.Session.request = original_request
    
    def test_module_id_masking(self, temp_project_dir, monkeypatch):
        """Тест маскирования MODULE_ID для логов"""
        monkeypatch.chdir(temp_project_dir)
        
        from handlers.module_id_injector import ModuleIDInjector
        
        injector = ModuleIDInjector()
        
        masked_long = injector._mask_id('TEST-MODULE-123456')
        assert '...' in masked_long
        assert len(masked_long) < len('TEST-MODULE-123456')
        
        masked_short = injector._mask_id('SHORT')
        assert masked_short == 'SHORT'
    
    def test_inject_module_id_to_requests_function(self, temp_project_dir, monkeypatch):
        """Тест функции inject_module_id_to_requests"""
        import requests
        monkeypatch.chdir(temp_project_dir)
        
        from handlers.module_id_injector import inject_module_id_to_requests
        
        original_request = requests.Session.request
        
        try:
            # Сбрасываем состояние
            from handlers.module_id_injector import _default_injector
            _default_injector.reset()
            _default_injector._module_id = 'TEST-MODULE'
            
            inject_module_id_to_requests()
        finally:
            requests.Session.request = original_request
    
    def test_reset_injector(self, temp_project_dir, monkeypatch):
        """Тест сброса состояния инъектора"""
        monkeypatch.chdir(temp_project_dir)
        
        from handlers.module_id_injector import ModuleIDInjector
        
        injector = ModuleIDInjector()
        injector._injected = True
        injector._module_id = 'TEST'
        
        assert injector._injected is True
        assert injector._module_id is not None
        
        injector.reset()
        
        assert injector._injected is False
        assert injector._module_id is None


class TestRQIDInjector:
    """Тесты для RQIDInjector"""
    
    def test_rqid_generation(self):
        """Тест генерации UUID для rqid"""
        from handlers.rqid_injector import RQIDInjector
        
        injector = RQIDInjector()
        rqid1 = injector._generate_rqid()
        rqid2 = injector._generate_rqid()
        
        uuid.UUID(rqid1)
        uuid.UUID(rqid2)
        
        assert rqid1 != rqid2
        assert len(rqid1) == 36
        assert rqid1.count('-') == 4
    
    def test_rqid_injection(self):
        """Тест инъекции rqid в заголовки"""
        import requests
        from handlers.rqid_injector import RQIDInjector
        
        original_request = requests.Session.request
        
        try:
            injector = RQIDInjector()
            injector._injected = False
            result = injector.inject()
            
            assert result is True
            assert injector._injected is True
        finally:
            requests.Session.request = original_request
    
    def test_rqid_injection_idempotent(self):
        """Тест что повторная инъекция не вызывает ошибок"""
        import requests
        from handlers.rqid_injector import RQIDInjector
        
        original_request = requests.Session.request
        
        try:
            injector = RQIDInjector()
            injector._injected = False
            
            result1 = injector.inject()
            result2 = injector.inject()
            
            assert result1 is True
            assert result2 is True
        finally:
            requests.Session.request = original_request
    
    def test_inject_rqid_function(self):
        """Тест функции inject_rqid для удобства"""
        import requests
        from handlers.rqid_injector import inject_rqid, _default_injector
        
        original_request = requests.Session.request
        
        try:
            _default_injector.reset()
            result = inject_rqid()
            assert result is True
        finally:
            requests.Session.request = original_request
    
    def test_reset_injector(self):
        """Тест сброса состояния инъектора"""
        from handlers.rqid_injector import RQIDInjector
        
        injector = RQIDInjector()
        injector._injected = True
        
        assert injector._injected is True
        
        injector.reset()
        
        assert injector._injected is False