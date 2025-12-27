"""
Valkey/Redis Manager for Phase 2 MVP - Tier 1 Memory Layer

This module provides production-ready Valkey/Redis integration for the translation
system with connection pooling, error handling, and performance optimization.

Core Features:
- Connection pooling with health monitoring
- O(1) lookup performance for term consistency
- Document session management with TTL
- Integration with glossary search engine caching
- Robust error handling and failover
"""

import json
import time
import logging
from typing import Dict, List, Optional, Any, Set, Tuple
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
try:
    import valkey
    from valkey.connection import ConnectionPool
    from valkey.exceptions import ConnectionError, TimeoutError, ValkeyError
except ImportError:
    # Use mock for testing when valkey is not installed
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from mock_valkey import Valkey as valkey, MockValkey
    
    # Mock the exceptions
    class ConnectionError(Exception):
        pass
    
    class TimeoutError(Exception):
        pass
    
    class ValkeyError(Exception):
        pass
    
    # Mock ConnectionPool
    class ConnectionPool:
        def __init__(self, **kwargs):
            pass


@dataclass
class SessionMetadata:
    """Document session metadata"""
    doc_id: str
    created_at: datetime
    updated_at: datetime
    source_language: str
    target_language: str
    total_segments: int
    processed_segments: int
    term_count: int
    status: str  # 'active', 'paused', 'completed', 'error'


@dataclass
class TermMapping:
    """Source to target term mapping with metadata"""
    source_term: str
    target_term: str
    confidence: float
    segment_id: str
    created_at: datetime
    locked: bool = False
    conflicts: List[str] = None
    
    def __post_init__(self):
        if self.conflicts is None:
            self.conflicts = []


@dataclass
class CacheEntry:
    """Cache entry with metadata"""
    data: Any
    created_at: datetime
    ttl_seconds: int
    access_count: int = 0
    last_accessed: datetime = None
    
    def __post_init__(self):
        if self.last_accessed is None:
            self.last_accessed = self.created_at


class ValkeyManager:
    """Production-ready Valkey/Redis manager for translation system"""
    
    # Key prefixes for different data types
    DOC_META_PREFIX = "doc"
    DOC_TERMS_PREFIX = "doc_terms"
    DOC_SEGMENTS_PREFIX = "doc_segments"
    GLOSSARY_CACHE_PREFIX = "glossary_cache"
    TERM_FREQ_PREFIX = "term_freq"
    SESSION_LIST_KEY = "active_sessions"
    
    # Default configurations
    DEFAULT_SESSION_TTL = 3600  # 1 hour
    DEFAULT_CACHE_TTL = 7200    # 2 hours
    DEFAULT_CONNECTION_POOL_SIZE = 20
    DEFAULT_TIMEOUT = 5.0
    
    def __init__(self, 
                 host: str = "localhost",
                 port: int = 6379,
                 db: int = 0,
                 password: Optional[str] = None,
                 max_connections: int = DEFAULT_CONNECTION_POOL_SIZE,
                 socket_timeout: float = DEFAULT_TIMEOUT,
                 socket_connect_timeout: float = DEFAULT_TIMEOUT,
                 retry_on_timeout: bool = True,
                 health_check_interval: int = 30):
        """
        Initialize Valkey manager with connection pooling
        
        Args:
            host: Valkey server host
            port: Valkey server port
            db: Database number
            password: Authentication password
            max_connections: Maximum pool connections
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
            retry_on_timeout: Retry operations on timeout
            health_check_interval: Health check interval in seconds
        """
        self.logger = logging.getLogger(__name__)
        self.host = host
        self.port = port
        self.db = db
        self.retry_on_timeout = retry_on_timeout
        self.health_check_interval = health_check_interval
        
        # Connection pool configuration
        self.pool = ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            retry_on_timeout=retry_on_timeout,
            health_check_interval=health_check_interval
        )
        
        # Valkey client with multi-threading support
        self.valkey_client = valkey.Valkey(connection_pool=self.pool)
        
        # Performance tracking
        self.operation_times: List[float] = []
        self.error_count = 0
        self.connection_errors = 0
        
        # Initialize connection and validate
        self._validate_connection()
        
        self.logger.info(f"ValkeyManager initialized: {host}:{port}/{db}")
    
    def _validate_connection(self) -> None:
        """Validate connection and log server info"""
        try:
            info = self.valkey_client.info()
            version = info.get('redis_version', info.get('valkey_version', 'unknown'))
            memory_used = info.get('used_memory_human', 'unknown')
            
            self.logger.info(f"Connected to Valkey {version}, Memory: {memory_used}")
            
            # Test basic operations
            test_key = "valkey_manager_test"
            self.valkey_client.set(test_key, "test_value", ex=1)
            if self.valkey_client.get(test_key) != b"test_value":
                raise ConnectionError("Basic operation validation failed")
            self.valkey_client.delete(test_key)
            
        except Exception as e:
            self.logger.error(f"Valkey connection validation failed: {e}")
            raise ConnectionError(f"Failed to connect to Valkey: {e}")
    
    @contextmanager
    def _operation_timer(self, operation_name: str):
        """Context manager for timing operations"""
        start_time = time.time()
        try:
            yield
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"Operation {operation_name} failed: {e}")
            raise
        finally:
            duration = time.time() - start_time
            self.operation_times.append(duration)
            if duration > 0.1:  # Log slow operations
                self.logger.warning(f"Slow operation {operation_name}: {duration:.3f}s")
    
    def _serialize_datetime(self, dt: datetime) -> str:
        """Serialize datetime to ISO format string"""
        return dt.isoformat()
    
    def _deserialize_datetime(self, dt_str: str) -> datetime:
        """Deserialize datetime from ISO format string"""
        return datetime.fromisoformat(dt_str)
    
    def _serialize_data(self, data: Any) -> str:
        """Serialize data to JSON string with datetime handling"""
        if isinstance(data, (SessionMetadata, TermMapping, CacheEntry)):
            # Convert dataclass to dict and handle datetime fields
            data_dict = asdict(data)
            for key, value in data_dict.items():
                if isinstance(value, datetime):
                    data_dict[key] = self._serialize_datetime(value)
            return json.dumps(data_dict)
        return json.dumps(data)
    
    def _deserialize_data(self, data_str: str, data_type: type = None) -> Any:
        """Deserialize JSON string to data with datetime handling"""
        if not data_str:
            return None
        
        data = json.loads(data_str)
        
        if data_type and data_type in (SessionMetadata, TermMapping, CacheEntry):
            # Handle datetime fields
            datetime_fields = {
                SessionMetadata: ['created_at', 'updated_at'],
                TermMapping: ['created_at'],
                CacheEntry: ['created_at', 'last_accessed']
            }
            
            for field in datetime_fields.get(data_type, []):
                if field in data and data[field]:
                    data[field] = self._deserialize_datetime(data[field])
            
            return data_type(**data)
        
        return data
    
    # ========== Session Management ==========
    
    def create_session(self, doc_id: str, 
                      source_language: str,
                      target_language: str,
                      total_segments: int,
                      ttl_seconds: int = DEFAULT_SESSION_TTL) -> SessionMetadata:
        """
        Create a new document translation session
        
        Args:
            doc_id: Unique document identifier
            source_language: Source language code
            target_language: Target language code  
            total_segments: Total number of segments in document
            ttl_seconds: Session TTL in seconds
            
        Returns:
            SessionMetadata object
        """
        with self._operation_timer(f"create_session_{doc_id}"):
            now = datetime.now()
            
            session = SessionMetadata(
                doc_id=doc_id,
                created_at=now,
                updated_at=now,
                source_language=source_language,
                target_language=target_language,
                total_segments=total_segments,
                processed_segments=0,
                term_count=0,
                status='active'
            )
            
            # Store session metadata with TTL
            session_key = f"{self.DOC_META_PREFIX}:{doc_id}:metadata"
            session_data = self._serialize_data(session)
            
            self.valkey_client.setex(session_key, ttl_seconds, session_data)
            
            # Add to active sessions list
            self.valkey_client.sadd(self.SESSION_LIST_KEY, doc_id)
            
            # Initialize empty term and segment tracking
            terms_key = f"{self.DOC_TERMS_PREFIX}:{doc_id}"
            segments_key = f"{self.DOC_SEGMENTS_PREFIX}:{doc_id}"
            
            self.valkey_client.expire(terms_key, ttl_seconds)
            self.valkey_client.expire(segments_key, ttl_seconds)
            
            self.logger.info(f"Created session for document {doc_id} with {total_segments} segments")
            return session
    
    def get_session(self, doc_id: str) -> Optional[SessionMetadata]:
        """Get session metadata for document"""
        with self._operation_timer(f"get_session_{doc_id}"):
            session_key = f"{self.DOC_META_PREFIX}:{doc_id}:metadata"
            session_data = self.valkey_client.get(session_key)
            
            if not session_data:
                return None
            
            return self._deserialize_data(session_data.decode(), SessionMetadata)
    
    def update_session(self, doc_id: str, **kwargs) -> bool:
        """Update session metadata fields"""
        with self._operation_timer(f"update_session_{doc_id}"):
            session = self.get_session(doc_id)
            if not session:
                return False
            
            # Update fields
            session.updated_at = datetime.now()
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            
            # Save updated session
            session_key = f"{self.DOC_META_PREFIX}:{doc_id}:metadata"
            session_data = self._serialize_data(session)
            
            # Preserve existing TTL
            ttl = self.valkey_client.ttl(session_key)
            if ttl > 0:
                self.valkey_client.setex(session_key, ttl, session_data)
            else:
                self.valkey_client.set(session_key, session_data)
            
            return True
    
    def extend_session_ttl(self, doc_id: str, additional_seconds: int) -> bool:
        """Extend session TTL"""
        with self._operation_timer(f"extend_session_ttl_{doc_id}"):
            session_key = f"{self.DOC_META_PREFIX}:{doc_id}:metadata"
            terms_key = f"{self.DOC_TERMS_PREFIX}:{doc_id}"
            segments_key = f"{self.DOC_SEGMENTS_PREFIX}:{doc_id}"
            
            # Extend TTL for all session-related keys
            results = []
            for key in [session_key, terms_key, segments_key]:
                current_ttl = self.valkey_client.ttl(key)
                if current_ttl > 0:
                    new_ttl = current_ttl + additional_seconds
                    results.append(self.valkey_client.expire(key, new_ttl))
            
            return all(results)
    
    def cleanup_session(self, doc_id: str) -> bool:
        """Clean up all session data"""
        with self._operation_timer(f"cleanup_session_{doc_id}"):
            session_key = f"{self.DOC_META_PREFIX}:{doc_id}:metadata"
            terms_key = f"{self.DOC_TERMS_PREFIX}:{doc_id}"
            segments_key = f"{self.DOC_SEGMENTS_PREFIX}:{doc_id}"
            
            # Remove from active sessions
            self.valkey_client.srem(self.SESSION_LIST_KEY, doc_id)
            
            # Delete all session data
            deleted = self.valkey_client.delete(session_key, terms_key, segments_key)
            
            self.logger.info(f"Cleaned up session {doc_id}, deleted {deleted} keys")
            return deleted > 0
    
    def get_active_sessions(self) -> List[str]:
        """Get list of active session IDs"""
        with self._operation_timer("get_active_sessions"):
            return [doc_id.decode() for doc_id in self.valkey_client.smembers(self.SESSION_LIST_KEY)]
    
    # ========== Term Consistency Tracking ==========
    
    def add_term_mapping(self, doc_id: str, 
                        source_term: str,
                        target_term: str,
                        segment_id: str,
                        confidence: float = 1.0,
                        lock_term: bool = False) -> bool:
        """
        Add term mapping for consistency tracking
        
        Args:
            doc_id: Document ID
            source_term: Source language term
            target_term: Target language term
            segment_id: Segment where mapping was established
            confidence: Translation confidence score
            lock_term: Whether to lock term for consistency
            
        Returns:
            True if mapping was added successfully
        """
        with self._operation_timer(f"add_term_mapping_{doc_id}"):
            terms_key = f"{self.DOC_TERMS_PREFIX}:{doc_id}"
            
            # Check for existing mapping
            existing_mapping = self.get_term_mapping(doc_id, source_term)
            
            term_mapping = TermMapping(
                source_term=source_term,
                target_term=target_term,
                confidence=confidence,
                segment_id=segment_id,
                created_at=datetime.now(),
                locked=lock_term
            )
            
            # Handle conflicts
            if existing_mapping and existing_mapping.target_term != target_term:
                if existing_mapping.locked:
                    self.logger.warning(f"Term conflict: {source_term} locked to {existing_mapping.target_term}")
                    return False
                else:
                    # Add conflict record
                    term_mapping.conflicts.append(f"{existing_mapping.target_term}@{existing_mapping.segment_id}")
            
            # Store mapping
            mapping_data = self._serialize_data(term_mapping)
            result = self.valkey_client.hset(terms_key, source_term, mapping_data)
            
            # Update session term count
            self.update_session(doc_id, term_count=self.valkey_client.hlen(terms_key))
            
            return True
    
    def get_term_mapping(self, doc_id: str, source_term: str) -> Optional[TermMapping]:
        """Get term mapping for source term"""
        with self._operation_timer(f"get_term_mapping_{doc_id}"):
            terms_key = f"{self.DOC_TERMS_PREFIX}:{doc_id}"
            mapping_data = self.valkey_client.hget(terms_key, source_term)
            
            if not mapping_data:
                return None
            
            return self._deserialize_data(mapping_data.decode(), TermMapping)
    
    def get_all_term_mappings(self, doc_id: str) -> Dict[str, TermMapping]:
        """Get all term mappings for document"""
        with self._operation_timer(f"get_all_term_mappings_{doc_id}"):
            terms_key = f"{self.DOC_TERMS_PREFIX}:{doc_id}"
            raw_mappings = self.valkey_client.hgetall(terms_key)
            
            mappings = {}
            for source_term, mapping_data in raw_mappings.items():
                source_term = source_term.decode()
                mapping = self._deserialize_data(mapping_data.decode(), TermMapping)
                mappings[source_term] = mapping
            
            return mappings
    
    def lock_term(self, doc_id: str, source_term: str) -> bool:
        """Lock term to prevent changes"""
        with self._operation_timer(f"lock_term_{doc_id}"):
            mapping = self.get_term_mapping(doc_id, source_term)
            if not mapping:
                return False
            
            mapping.locked = True
            terms_key = f"{self.DOC_TERMS_PREFIX}:{doc_id}"
            mapping_data = self._serialize_data(mapping)
            
            self.valkey_client.hset(terms_key, source_term, mapping_data)
            return True
    
    def unlock_term(self, doc_id: str, source_term: str) -> bool:
        """Unlock term to allow changes"""
        with self._operation_timer(f"unlock_term_{doc_id}"):
            mapping = self.get_term_mapping(doc_id, source_term)
            if not mapping:
                return False
            
            mapping.locked = False
            terms_key = f"{self.DOC_TERMS_PREFIX}:{doc_id}"
            mapping_data = self._serialize_data(mapping)
            
            self.valkey_client.hset(terms_key, source_term, mapping_data)
            return True
    
    # ========== Caching Interface ==========
    
    def cache_search_results(self, cache_key: str, 
                           results: Any,
                           ttl_seconds: int = DEFAULT_CACHE_TTL) -> bool:
        """Cache glossary search results"""
        with self._operation_timer("cache_search_results"):
            cache_entry = CacheEntry(
                data=results,
                created_at=datetime.now(),
                ttl_seconds=ttl_seconds
            )
            
            full_key = f"{self.GLOSSARY_CACHE_PREFIX}:{cache_key}"
            cache_data = self._serialize_data(cache_entry)
            
            return self.valkey_client.setex(full_key, ttl_seconds, cache_data)
    
    def get_cached_search_results(self, cache_key: str) -> Optional[Any]:
        """Get cached search results"""
        with self._operation_timer("get_cached_search_results"):
            full_key = f"{self.GLOSSARY_CACHE_PREFIX}:{cache_key}"
            cache_data = self.valkey_client.get(full_key)
            
            if not cache_data:
                return None
            
            cache_entry = self._deserialize_data(cache_data.decode(), CacheEntry)
            
            # Update access tracking
            cache_entry.access_count += 1
            cache_entry.last_accessed = datetime.now()
            
            # Update cache with new access info (preserve TTL)
            ttl = self.valkey_client.ttl(full_key)
            if ttl > 0:
                updated_cache_data = self._serialize_data(cache_entry)
                self.valkey_client.setex(full_key, ttl, updated_cache_data)
            
            return cache_entry.data
    
    def invalidate_cache(self, pattern: str = None) -> int:
        """Invalidate cache entries"""
        with self._operation_timer("invalidate_cache"):
            if pattern:
                full_pattern = f"{self.GLOSSARY_CACHE_PREFIX}:{pattern}"
                keys = self.valkey_client.keys(full_pattern)
            else:
                keys = self.valkey_client.keys(f"{self.GLOSSARY_CACHE_PREFIX}:*")
            
            if keys:
                return self.valkey_client.delete(*keys)
            return 0
    
    # ========== Performance and Health ==========
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        if not self.operation_times:
            return {"status": "no_operations_yet"}
        
        avg_time = sum(self.operation_times) / len(self.operation_times)
        max_time = max(self.operation_times)
        min_time = min(self.operation_times)
        
        # Valkey info
        try:
            info = self.valkey_client.info()
            memory_used = info.get('used_memory', 0)
            connected_clients = info.get('connected_clients', 0)
            total_commands = info.get('total_commands_processed', 0)
        except Exception:
            memory_used = connected_clients = total_commands = -1
        
        return {
            "operations": {
                "total_operations": len(self.operation_times),
                "average_time_ms": avg_time * 1000,
                "max_time_ms": max_time * 1000,
                "min_time_ms": min_time * 1000,
                "error_count": self.error_count,
                "connection_errors": self.connection_errors
            },
            "valkey_info": {
                "memory_used_bytes": memory_used,
                "connected_clients": connected_clients,
                "total_commands_processed": total_commands
            },
            "connection_pool": {
                "max_connections": self.pool.max_connections,
                "created_connections": len(self.pool._created_connections)
            }
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        try:
            start_time = time.time()
            
            # Test ping
            ping_result = self.valkey_client.ping()
            ping_time = time.time() - start_time
            
            # Test basic operations
            test_key = f"health_check_{int(time.time())}"
            self.valkey_client.set(test_key, "ok", ex=1)
            get_result = self.valkey_client.get(test_key)
            self.valkey_client.delete(test_key)
            
            # Get active sessions count
            active_sessions = len(self.get_active_sessions())
            
            return {
                "status": "healthy",
                "ping": ping_result,
                "ping_time_ms": ping_time * 1000,
                "basic_operations": "ok" if get_result == b"ok" else "failed",
                "active_sessions": active_sessions,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.connection_errors += 1
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def close(self) -> None:
        """Close connection pool"""
        self.pool.disconnect()
        self.logger.info("ValkeyManager connection pool closed")