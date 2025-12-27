"""
Phase 2 MVP Memory Layer - Tier 1 Valkey Integration

This module provides the foundation memory layer for the enhanced translation system,
implementing session-based caching, term consistency tracking, and high-performance
glossary search with intelligent caching.

Key Components:
- ValkeyManager: Core Valkey/Redis integration with connection pooling
- SessionManager: High-level document session management
- ConsistencyTracker: Term consistency tracking with conflict resolution
- CachedGlossarySearch: Cached glossary search with performance optimization

Performance Targets:
- Sub-millisecond cache operations
- Handle concurrent document sessions
- 95%+ cache hit rate for repeated terms
- Memory-efficient storage
"""

from .valkey_manager import (
    ValkeyManager,
    SessionMetadata,
    TermMapping,
    CacheEntry
)

from .session_manager import (
    SessionManager,
    SessionStatus,
    SessionProgress,
    SegmentResult
)

from .consistency_tracker import (
    ConsistencyTracker,
    ConflictResolutionStrategy,
    TermConflict,
    TermAnalytics
)

from .cached_glossary_search import (
    CachedGlossarySearch,
    CacheMetrics
)

__all__ = [
    # Core Valkey Integration
    'ValkeyManager',
    'SessionMetadata',
    'TermMapping',
    'CacheEntry',
    
    # Session Management
    'SessionManager',
    'SessionStatus',
    'SessionProgress',
    'SegmentResult',
    
    # Consistency Tracking
    'ConsistencyTracker',
    'ConflictResolutionStrategy',
    'TermConflict',
    'TermAnalytics',
    
    # Cached Search
    'CachedGlossarySearch',
    'CacheMetrics'
]

# Version info
__version__ = "2.0.0"
__author__ = "Phase 2 MVP Team"
__description__ = "Valkey-based memory layer for translation system"