#!/usr/bin/env python3
"""
Test script to validate that imports work correctly after reorganization
"""

import sys
from pathlib import Path

# Add the current directory to Python path for testing
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test all major imports to ensure they work correctly"""
    
    print("Testing Phase 2 package imports...")
    
    try:
        print("✓ Testing token_optimizer import...")
        from token_optimizer import TokenOptimizer, ContextComponent, ContextPriority
        print("✓ token_optimizer imports successful")
    except ImportError as e:
        print(f"✗ token_optimizer import failed: {e}")
    
    try:
        print("✓ Testing glossary_search import...")
        from glossary_search import GlossarySearchEngine
        print("✓ glossary_search imports successful")
    except ImportError as e:
        print(f"✗ glossary_search import failed: {e}")
    
    try:
        print("✓ Testing memory.valkey_manager import...")
        from memory.valkey_manager import ValkeyManager
        print("✓ memory.valkey_manager imports successful")
    except ImportError as e:
        print(f"✗ memory.valkey_manager import failed: {e}")
    
    try:
        print("✓ Testing memory.session_manager import...")
        from memory.session_manager import SessionManager
        print("✓ memory.session_manager imports successful")
    except ImportError as e:
        print(f"✗ memory.session_manager import failed: {e}")
    
    try:
        print("✓ Testing memory.cached_glossary_search import...")
        from memory.cached_glossary_search import CachedGlossarySearch
        print("✓ memory.cached_glossary_search imports successful")
    except ImportError as e:
        print(f"✗ memory.cached_glossary_search import failed: {e}")
    
    try:
        print("✓ Testing context_builder import...")
        from context_builder import ContextBuilder, ContextRequest
        print("✓ context_builder imports successful")
    except ImportError as e:
        print(f"✗ context_builder import failed: {e}")
    
    try:
        print("✓ Testing enhanced_translation_service import...")
        from enhanced_translation_service import (
            EnhancedTranslationService, 
            EnhancedTranslationRequest,
            OperationMode
        )
        print("✓ enhanced_translation_service imports successful")
    except ImportError as e:
        print(f"✗ enhanced_translation_service import failed: {e}")
    
    try:
        print("✓ Testing model_adapters import...")
        from model_adapters import BaseModelAdapter, OpenAIAdapter
        print("✓ model_adapters imports successful")
    except ImportError as e:
        print(f"✗ model_adapters import failed: {e}")
    
    print("\nImport testing completed!")

if __name__ == "__main__":
    test_imports()