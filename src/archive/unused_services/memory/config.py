"""
Configuration Management for Valkey Memory Layer

This module provides centralized configuration for the Valkey/Redis integration
with environment-based configuration and validation.
"""

import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class ValkeyConfig:
    """Valkey/Redis connection configuration"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 20
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    health_check_interval: int = 30


@dataclass
class CacheConfig:
    """Cache behavior configuration"""
    default_ttl_seconds: int = 7200  # 2 hours
    session_ttl_seconds: int = 3600  # 1 hour
    max_cache_size: int = 10000
    enable_preloading: bool = True
    auto_extend_threshold: int = 300  # 5 minutes


@dataclass
class ConsistencyConfig:
    """Term consistency tracking configuration"""
    confidence_threshold: float = 0.8
    consistency_threshold: float = 0.7
    default_resolution_strategy: str = "glossary_preferred"


@dataclass
class PerformanceConfig:
    """Performance optimization configuration"""
    batch_size: int = 100
    concurrent_sessions_limit: int = 50
    operation_timeout_ms: int = 5000
    memory_limit_mb: int = 512


class MemoryLayerConfig:
    """Centralized configuration for memory layer"""
    
    def __init__(self):
        self.valkey = self._load_valkey_config()
        self.cache = self._load_cache_config()
        self.consistency = self._load_consistency_config()
        self.performance = self._load_performance_config()
    
    def _load_valkey_config(self) -> ValkeyConfig:
        """Load Valkey configuration from environment variables"""
        return ValkeyConfig(
            host=os.getenv("VALKEY_HOST", "localhost"),
            port=int(os.getenv("VALKEY_PORT", "6379")),
            db=int(os.getenv("VALKEY_DB", "0")),
            password=os.getenv("VALKEY_PASSWORD"),
            max_connections=int(os.getenv("VALKEY_MAX_CONNECTIONS", "20")),
            socket_timeout=float(os.getenv("VALKEY_SOCKET_TIMEOUT", "5.0")),
            socket_connect_timeout=float(os.getenv("VALKEY_CONNECT_TIMEOUT", "5.0")),
            retry_on_timeout=os.getenv("VALKEY_RETRY_ON_TIMEOUT", "true").lower() == "true",
            health_check_interval=int(os.getenv("VALKEY_HEALTH_CHECK_INTERVAL", "30"))
        )
    
    def _load_cache_config(self) -> CacheConfig:
        """Load cache configuration from environment variables"""
        return CacheConfig(
            default_ttl_seconds=int(os.getenv("CACHE_DEFAULT_TTL", "7200")),
            session_ttl_seconds=int(os.getenv("CACHE_SESSION_TTL", "3600")),
            max_cache_size=int(os.getenv("CACHE_MAX_SIZE", "10000")),
            enable_preloading=os.getenv("CACHE_ENABLE_PRELOADING", "true").lower() == "true",
            auto_extend_threshold=int(os.getenv("CACHE_AUTO_EXTEND_THRESHOLD", "300"))
        )
    
    def _load_consistency_config(self) -> ConsistencyConfig:
        """Load consistency configuration from environment variables"""
        return ConsistencyConfig(
            confidence_threshold=float(os.getenv("CONSISTENCY_CONFIDENCE_THRESHOLD", "0.8")),
            consistency_threshold=float(os.getenv("CONSISTENCY_THRESHOLD", "0.7")),
            default_resolution_strategy=os.getenv("CONSISTENCY_RESOLUTION_STRATEGY", "glossary_preferred")
        )
    
    def _load_performance_config(self) -> PerformanceConfig:
        """Load performance configuration from environment variables"""
        return PerformanceConfig(
            batch_size=int(os.getenv("PERFORMANCE_BATCH_SIZE", "100")),
            concurrent_sessions_limit=int(os.getenv("PERFORMANCE_CONCURRENT_LIMIT", "50")),
            operation_timeout_ms=int(os.getenv("PERFORMANCE_TIMEOUT_MS", "5000")),
            memory_limit_mb=int(os.getenv("PERFORMANCE_MEMORY_LIMIT_MB", "512"))
        )
    
    def validate(self) -> bool:
        """Validate configuration values"""
        errors = []
        
        # Validate Valkey config
        if self.valkey.port < 1 or self.valkey.port > 65535:
            errors.append(f"Invalid Valkey port: {self.valkey.port}")
        
        if self.valkey.max_connections < 1:
            errors.append(f"Invalid max_connections: {self.valkey.max_connections}")
        
        # Validate cache config
        if self.cache.default_ttl_seconds < 1:
            errors.append(f"Invalid default TTL: {self.cache.default_ttl_seconds}")
        
        if self.cache.max_cache_size < 1:
            errors.append(f"Invalid max_cache_size: {self.cache.max_cache_size}")
        
        # Validate consistency config
        if not 0.0 <= self.consistency.confidence_threshold <= 1.0:
            errors.append(f"Invalid confidence_threshold: {self.consistency.confidence_threshold}")
        
        if not 0.0 <= self.consistency.consistency_threshold <= 1.0:
            errors.append(f"Invalid consistency_threshold: {self.consistency.consistency_threshold}")
        
        # Validate performance config
        if self.performance.batch_size < 1:
            errors.append(f"Invalid batch_size: {self.performance.batch_size}")
        
        if self.performance.memory_limit_mb < 1:
            errors.append(f"Invalid memory_limit_mb: {self.performance.memory_limit_mb}")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
        
        return True
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary"""
        return {
            "valkey": {
                "host": self.valkey.host,
                "port": self.valkey.port,
                "db": self.valkey.db,
                "max_connections": self.valkey.max_connections,
                "socket_timeout": self.valkey.socket_timeout,
                "retry_on_timeout": self.valkey.retry_on_timeout
            },
            "cache": {
                "default_ttl_seconds": self.cache.default_ttl_seconds,
                "session_ttl_seconds": self.cache.session_ttl_seconds,
                "max_cache_size": self.cache.max_cache_size,
                "enable_preloading": self.cache.enable_preloading
            },
            "consistency": {
                "confidence_threshold": self.consistency.confidence_threshold,
                "consistency_threshold": self.consistency.consistency_threshold,
                "default_resolution_strategy": self.consistency.default_resolution_strategy
            },
            "performance": {
                "batch_size": self.performance.batch_size,
                "concurrent_sessions_limit": self.performance.concurrent_sessions_limit,
                "operation_timeout_ms": self.performance.operation_timeout_ms,
                "memory_limit_mb": self.performance.memory_limit_mb
            }
        }


# Global configuration instance
memory_config = MemoryLayerConfig()