"""
Phase 2 Translation System - Enhanced Architecture Package

This package implements the Phase 2 enhanced translation system with three-tier memory
architecture, smart context building, and advanced LLM provider support.

Key Features:
- 98% token reduction through smart context generation
- Session-based document processing with Valkey caching
- Advanced model support (GPT-5 family, o3 constraints)
- Full backward compatibility with Phase 1 system
- Production-ready error handling and monitoring

Main Components:
- enhanced_translation_service: Core enhanced translation service
- context_builder: Smart context assembly pipeline
- memory: Valkey-based caching and session management
- model_adapters: LLM provider-specific adapters
- token_optimizer: Token counting and optimization
"""

# Core translation components
from .enhanced_translation_service import (
    EnhancedTranslationService,
    EnhancedTranslationRequest,
    EnhancedTranslationResult,
    OperationMode
)

from .context_builder import (
    ContextBuilder,
    ContextRequest,
    ContextBuildResult
)

from .token_optimizer import (
    TokenOptimizer,
    ContextComponent,
    ContextPriority,
    TokenOptimizationResult
)

# Memory layer
from .memory import (
    ValkeyManager,
    SessionManager,
    CachedGlossarySearch
)

# Model adapters
from .model_adapters import (
    BaseModelAdapter,
    OpenAIAdapter
)

# Data processing
from .data_loader_enhanced import EnhancedDataLoader
from .glossary_search import GlossarySearchEngine

__all__ = [
    # Core translation
    'EnhancedTranslationService',
    'EnhancedTranslationRequest', 
    'EnhancedTranslationResult',
    'OperationMode',
    
    # Context building
    'ContextBuilder',
    'ContextRequest',
    'ContextBuildResult',
    
    # Token optimization
    'TokenOptimizer',
    'ContextComponent',
    'ContextPriority',
    'TokenOptimizationResult',
    
    # Memory layer
    'ValkeyManager',
    'SessionManager',
    'CachedGlossarySearch',
    
    # Model adapters
    'BaseModelAdapter',
    'OpenAIAdapter',
    
    # Data processing
    'EnhancedDataLoader',
    'GlossarySearchEngine'
]

# Version info
__version__ = "2.0.0"
__author__ = "Phase 2 MVP Team"
__description__ = "Enhanced translation system with three-tier memory architecture"