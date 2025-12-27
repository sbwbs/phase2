"""
GPT-5 OWL Production Monitoring and Error Handling

This module provides comprehensive monitoring, error handling, and observability
for GPT-5 OWL medical translation workflows with 1400+ segment processing.

Key Features:
- Real-time error classification and recovery strategies
- Session-aware progress tracking and health monitoring
- Cost and performance alerting with thresholds
- Medical translation quality metrics and compliance tracking
- Production-grade logging and telemetry
"""

import logging
import asyncio
import time
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

from memory.valkey_manager import ValkeyManager
from gpt5_cost_optimizer import GPT5CostOptimizer, CostMetrics


class ErrorSeverity(Enum):
    """Error severity levels for GPT-5 OWL operations"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categories of errors in medical translation pipeline"""
    API_ERROR = "api_error"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    CONTEXT_BUILD = "context_build"
    TRANSLATION_QUALITY = "translation_quality"
    SESSION_MANAGEMENT = "session_management"
    COST_THRESHOLD = "cost_threshold"
    SYSTEM_RESOURCE = "system_resource"


@dataclass
class ErrorEvent:
    """Structured error event for GPT-5 OWL operations"""
    timestamp: datetime
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    doc_id: Optional[str]
    segment_id: Optional[str]
    model_used: str
    context: Dict[str, Any]
    resolution_attempted: Optional[str] = None
    resolution_successful: bool = False
    cost_impact_usd: float = 0.0
    retry_count: int = 0


@dataclass
class SessionHealth:
    """Health metrics for a document translation session"""
    doc_id: str
    total_segments: int
    completed_segments: int
    failed_segments: int
    success_rate: float
    average_processing_time_ms: float
    total_cost_usd: float
    average_cost_per_segment: float
    context_optimization_rate: float
    cache_hit_rate: float
    last_activity: datetime
    estimated_completion_time: Optional[datetime]
    quality_score: float
    error_count: int
    warning_count: int


@dataclass
class SystemHealth:
    """Overall system health metrics"""
    active_sessions: int
    total_requests_last_hour: int
    success_rate_last_hour: float
    average_response_time_ms: float
    total_cost_last_hour_usd: float
    cache_hit_rate: float
    error_rate: float
    api_quota_remaining: Optional[float]
    system_load: float
    memory_usage_percent: float


class GPT5Monitor:
    """Production monitoring system for GPT-5 OWL medical translation"""
    
    def __init__(self,
                 valkey_manager: ValkeyManager,
                 cost_optimizer: GPT5CostOptimizer,
                 log_file_path: Optional[str] = None,
                 enable_alerting: bool = True,
                 cost_alert_threshold: float = 50.0,
                 error_rate_threshold: float = 0.1):
        """
        Initialize GPT-5 monitoring system
        
        Args:
            valkey_manager: Valkey cache manager
            cost_optimizer: GPT-5 cost optimizer
            log_file_path: Path for detailed logging
            enable_alerting: Enable alerting system
            cost_alert_threshold: Cost threshold for alerts (USD)
            error_rate_threshold: Error rate threshold for alerts
        """
        self.valkey_manager = valkey_manager
        self.cost_optimizer = cost_optimizer
        self.enable_alerting = enable_alerting
        self.cost_alert_threshold = cost_alert_threshold
        self.error_rate_threshold = error_rate_threshold
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self._setup_detailed_logging(log_file_path)
        
        # Monitoring state
        self.session_health = {}  # doc_id -> SessionHealth
        self.error_events = []    # Recent error events
        self.performance_metrics = {}
        self.alert_callbacks = []  # Alert notification callbacks
        
        # Monitoring intervals
        self.health_check_interval = 60  # seconds
        self.metrics_collection_interval = 30  # seconds
        
        # Error tracking
        self.max_error_history = 1000
        self.max_retry_attempts = 3
        self.retry_delays = [1, 3, 7]  # seconds
        
        # Quality thresholds
        self.min_quality_score = 0.7
        self.max_processing_time_ms = 30000  # 30 seconds
        
        self.logger.info("GPT-5 Monitor initialized")
    
    def add_alert_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Add callback for alert notifications"""
        self.alert_callbacks.append(callback)
    
    async def start_monitoring(self):
        """Start background monitoring tasks"""
        self.logger.info("Starting GPT-5 monitoring tasks")
        
        # Start background tasks
        asyncio.create_task(self._periodic_health_check())
        asyncio.create_task(self._periodic_metrics_collection())
        asyncio.create_task(self._error_cleanup_task())
    
    async def log_translation_start(self,
                                  doc_id: str,
                                  segment_id: str,
                                  korean_text: str,
                                  model_name: str,
                                  context_tokens: int) -> str:
        """
        Log translation request start
        
        Returns:
            Request ID for tracking
        """
        request_id = f"{doc_id}_{segment_id}_{int(time.time())}"
        
        # Initialize session health if new
        if doc_id not in self.session_health:
            await self._initialize_session_health(doc_id)
        
        # Log request details
        request_context = {
            'request_id': request_id,
            'doc_id': doc_id,
            'segment_id': segment_id,
            'model_name': model_name,
            'korean_text_length': len(korean_text),
            'context_tokens': context_tokens,
            'timestamp': datetime.now().isoformat()
        }
        
        self._log_structured_event("translation_start", request_context)
        
        return request_id
    
    async def log_translation_success(self,
                                    request_id: str,
                                    doc_id: str,
                                    segment_id: str,
                                    english_translation: str,
                                    processing_time_ms: float,
                                    tokens_used: int,
                                    cost_usd: float,
                                    quality_score: float = 0.9):
        """Log successful translation"""
        
        # Update session health
        session_health = self.session_health.get(doc_id)
        if session_health:
            session_health.completed_segments += 1
            session_health.total_cost_usd += cost_usd
            session_health.average_processing_time_ms = (
                (session_health.average_processing_time_ms * (session_health.completed_segments - 1) + 
                 processing_time_ms) / session_health.completed_segments
            )
            session_health.average_cost_per_segment = (
                session_health.total_cost_usd / session_health.completed_segments
            )
            session_health.last_activity = datetime.now()
            
            # Update success rate
            total_processed = session_health.completed_segments + session_health.failed_segments
            session_health.success_rate = session_health.completed_segments / max(total_processed, 1)
            
            # Check for quality issues
            if quality_score < self.min_quality_score:
                await self._log_quality_warning(doc_id, segment_id, quality_score)
            
            # Check for performance issues
            if processing_time_ms > self.max_processing_time_ms:
                await self._log_performance_warning(doc_id, segment_id, processing_time_ms)
        
        # Log success details
        success_context = {
            'request_id': request_id,
            'doc_id': doc_id,
            'segment_id': segment_id,
            'translation_length': len(english_translation),
            'processing_time_ms': processing_time_ms,
            'tokens_used': tokens_used,
            'cost_usd': cost_usd,
            'quality_score': quality_score,
            'timestamp': datetime.now().isoformat()
        }
        
        self._log_structured_event("translation_success", success_context)
        
        # Check cost alerts
        if cost_usd > self.cost_alert_threshold / 100:  # Alert for high single-request costs
            await self._trigger_cost_alert(doc_id, cost_usd, "single_request")
    
    async def log_translation_error(self,
                                  request_id: str,
                                  doc_id: str,
                                  segment_id: str,
                                  error: Exception,
                                  model_name: str,
                                  context: Dict[str, Any] = None,
                                  retry_attempt: int = 0) -> ErrorEvent:
        """Log translation error and determine recovery strategy"""
        
        # Classify error
        error_category = self._classify_error(error)
        error_severity = self._determine_error_severity(error_category, retry_attempt)
        
        # Create error event
        error_event = ErrorEvent(
            timestamp=datetime.now(),
            severity=error_severity,
            category=error_category,
            message=str(error),
            doc_id=doc_id,
            segment_id=segment_id,
            model_used=model_name,
            context=context or {},
            retry_count=retry_attempt
        )
        
        # Add to error history
        self.error_events.append(error_event)
        if len(self.error_events) > self.max_error_history:
            self.error_events.pop(0)
        
        # Update session health
        session_health = self.session_health.get(doc_id)
        if session_health:
            session_health.failed_segments += 1
            session_health.error_count += 1
            
            # Update success rate
            total_processed = session_health.completed_segments + session_health.failed_segments
            session_health.success_rate = session_health.completed_segments / max(total_processed, 1)
        
        # Log error details
        error_context = {
            'request_id': request_id,
            'error_category': error_category.value,
            'error_severity': error_severity.value,
            'error_message': str(error),
            'retry_attempt': retry_attempt,
            'doc_id': doc_id,
            'segment_id': segment_id,
            'model_name': model_name,
            'timestamp': datetime.now().isoformat()
        }
        
        self._log_structured_event("translation_error", error_context)
        
        # Trigger alerts for critical errors
        if error_severity == ErrorSeverity.CRITICAL:
            await self._trigger_error_alert(error_event)
        
        return error_event
    
    async def should_retry(self, error_event: ErrorEvent) -> Tuple[bool, int]:
        """
        Determine if request should be retried and with what delay
        
        Returns:
            Tuple of (should_retry, delay_seconds)
        """
        if error_event.retry_count >= self.max_retry_attempts:
            return False, 0
        
        # Category-specific retry logic
        if error_event.category == ErrorCategory.RATE_LIMIT:
            # Always retry rate limits with exponential backoff
            delay = min(self.retry_delays[error_event.retry_count] * 2, 60)
            return True, delay
        
        elif error_event.category == ErrorCategory.TIMEOUT:
            # Retry timeouts with moderate delay
            delay = self.retry_delays[min(error_event.retry_count, len(self.retry_delays) - 1)]
            return True, delay
        
        elif error_event.category == ErrorCategory.API_ERROR:
            # Retry API errors cautiously
            if error_event.retry_count < 2:
                delay = self.retry_delays[error_event.retry_count] * 3
                return True, delay
        
        elif error_event.category == ErrorCategory.CONTEXT_BUILD:
            # Don't retry context build errors - likely data issue
            return False, 0
        
        # Default: conservative retry
        delay = self.retry_delays[min(error_event.retry_count, len(self.retry_delays) - 1)]
        return error_event.retry_count < 2, delay
    
    async def get_session_health(self, doc_id: str) -> Optional[SessionHealth]:
        """Get health metrics for a session"""
        return self.session_health.get(doc_id)
    
    async def get_system_health(self) -> SystemHealth:
        """Get overall system health metrics"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        # Calculate metrics from recent data
        recent_errors = [e for e in self.error_events if e.timestamp > hour_ago]
        recent_requests = len([e for e in self.error_events if e.timestamp > hour_ago])
        
        # Active sessions
        active_sessions = len([s for s in self.session_health.values() 
                             if s.last_activity > now - timedelta(minutes=30)])
        
        # Cost metrics
        cost_summary = self.cost_optimizer.get_global_cost_summary()
        
        return SystemHealth(
            active_sessions=active_sessions,
            total_requests_last_hour=recent_requests,
            success_rate_last_hour=self._calculate_success_rate(hour_ago),
            average_response_time_ms=self._calculate_average_response_time(),
            total_cost_last_hour_usd=cost_summary['total_cost_usd'],
            cache_hit_rate=cost_summary.get('cache_hit_rates', {}).get('TRANSLATION_CACHE', 0.0),
            error_rate=len(recent_errors) / max(recent_requests, 1),
            api_quota_remaining=None,  # Would be fetched from OpenAI API
            system_load=0.5,  # Placeholder - would use psutil in production
            memory_usage_percent=60.0  # Placeholder - would use psutil in production
        )
    
    # Internal methods
    
    async def _initialize_session_health(self, doc_id: str):
        """Initialize health tracking for a new session"""
        session_data = self.valkey_manager.get_session(doc_id)
        total_segments = session_data.total_segments if session_data else 0
        
        self.session_health[doc_id] = SessionHealth(
            doc_id=doc_id,
            total_segments=total_segments,
            completed_segments=0,
            failed_segments=0,
            success_rate=1.0,
            average_processing_time_ms=0.0,
            total_cost_usd=0.0,
            average_cost_per_segment=0.0,
            context_optimization_rate=0.0,
            cache_hit_rate=0.0,
            last_activity=datetime.now(),
            estimated_completion_time=None,
            quality_score=1.0,
            error_count=0,
            warning_count=0
        )
    
    def _classify_error(self, error: Exception) -> ErrorCategory:
        """Classify error type for appropriate handling"""
        error_str = str(error).lower()
        
        if "rate limit" in error_str or "quota" in error_str:
            return ErrorCategory.RATE_LIMIT
        elif "timeout" in error_str or "time out" in error_str:
            return ErrorCategory.TIMEOUT
        elif "auth" in error_str or "api key" in error_str:
            return ErrorCategory.AUTHENTICATION
        elif "context" in error_str or "build" in error_str:
            return ErrorCategory.CONTEXT_BUILD
        elif "session" in error_str:
            return ErrorCategory.SESSION_MANAGEMENT
        else:
            return ErrorCategory.API_ERROR
    
    def _determine_error_severity(self, category: ErrorCategory, retry_count: int) -> ErrorSeverity:
        """Determine error severity based on category and retry count"""
        if retry_count >= self.max_retry_attempts:
            return ErrorSeverity.CRITICAL
        
        severity_map = {
            ErrorCategory.RATE_LIMIT: ErrorSeverity.WARNING,
            ErrorCategory.TIMEOUT: ErrorSeverity.WARNING,
            ErrorCategory.AUTHENTICATION: ErrorSeverity.CRITICAL,
            ErrorCategory.CONTEXT_BUILD: ErrorSeverity.ERROR,
            ErrorCategory.TRANSLATION_QUALITY: ErrorSeverity.WARNING,
            ErrorCategory.SESSION_MANAGEMENT: ErrorSeverity.ERROR,
            ErrorCategory.COST_THRESHOLD: ErrorSeverity.WARNING,
            ErrorCategory.API_ERROR: ErrorSeverity.ERROR
        }
        
        return severity_map.get(category, ErrorSeverity.ERROR)
    
    async def _log_quality_warning(self, doc_id: str, segment_id: str, quality_score: float):
        """Log quality warning"""
        warning_context = {
            'doc_id': doc_id,
            'segment_id': segment_id,
            'quality_score': quality_score,
            'threshold': self.min_quality_score
        }
        
        self._log_structured_event("quality_warning", warning_context)
        
        session_health = self.session_health.get(doc_id)
        if session_health:
            session_health.warning_count += 1
    
    async def _log_performance_warning(self, doc_id: str, segment_id: str, processing_time: float):
        """Log performance warning"""
        warning_context = {
            'doc_id': doc_id,
            'segment_id': segment_id,
            'processing_time_ms': processing_time,
            'threshold_ms': self.max_processing_time_ms
        }
        
        self._log_structured_event("performance_warning", warning_context)
    
    def _setup_detailed_logging(self, log_file_path: Optional[str]):
        """Setup detailed logging for monitoring"""
        if log_file_path:
            handler = logging.FileHandler(log_file_path)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def _log_structured_event(self, event_type: str, context: Dict[str, Any]):
        """Log structured event for analysis"""
        log_entry = {
            'event_type': event_type,
            'timestamp': datetime.now().isoformat(),
            **context
        }
        
        self.logger.info(f"GPT5_EVENT: {json.dumps(log_entry)}")
    
    async def _trigger_cost_alert(self, doc_id: str, cost: float, alert_type: str):
        """Trigger cost-related alert"""
        alert_data = {
            'alert_type': 'cost_threshold',
            'doc_id': doc_id,
            'cost_usd': cost,
            'threshold': self.cost_alert_threshold,
            'timestamp': datetime.now().isoformat()
        }
        
        for callback in self.alert_callbacks:
            try:
                callback(alert_data)
            except Exception as e:
                self.logger.error(f"Alert callback failed: {e}")
    
    async def _trigger_error_alert(self, error_event: ErrorEvent):
        """Trigger error-related alert"""
        alert_data = {
            'alert_type': 'critical_error',
            'error_event': asdict(error_event),
            'timestamp': datetime.now().isoformat()
        }
        
        for callback in self.alert_callbacks:
            try:
                callback(alert_data)
            except Exception as e:
                self.logger.error(f"Alert callback failed: {e}")
    
    def _calculate_success_rate(self, since: datetime) -> float:
        """Calculate success rate since given time"""
        # This would be implemented based on your success tracking
        return 0.95  # Placeholder
    
    def _calculate_average_response_time(self) -> float:
        """Calculate average response time"""
        # This would be implemented based on your timing tracking
        return 2500.0  # Placeholder
    
    async def _periodic_health_check(self):
        """Periodic health check task"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._perform_health_checks()
            except Exception as e:
                self.logger.error(f"Health check failed: {e}")
    
    async def _periodic_metrics_collection(self):
        """Periodic metrics collection task"""
        while True:
            try:
                await asyncio.sleep(self.metrics_collection_interval)
                await self._collect_metrics()
            except Exception as e:
                self.logger.error(f"Metrics collection failed: {e}")
    
    async def _error_cleanup_task(self):
        """Clean up old error events"""
        while True:
            try:
                await asyncio.sleep(3600)  # Every hour
                cutoff = datetime.now() - timedelta(hours=24)
                self.error_events = [e for e in self.error_events if e.timestamp > cutoff]
            except Exception as e:
                self.logger.error(f"Error cleanup failed: {e}")
    
    async def _perform_health_checks(self):
        """Perform comprehensive health checks"""
        # Check session health
        for doc_id, health in self.session_health.items():
            if health.success_rate < 0.8:
                await self._trigger_session_health_alert(doc_id, health)
    
    async def _collect_metrics(self):
        """Collect and update metrics"""
        # Update system-level metrics
        system_health = await self.get_system_health()
        
        metrics_context = {
            'active_sessions': system_health.active_sessions,
            'error_rate': system_health.error_rate,
            'average_response_time': system_health.average_response_time_ms,
            'total_cost_last_hour': system_health.total_cost_last_hour_usd
        }
        
        self._log_structured_event("system_metrics", metrics_context)
    
    async def _trigger_session_health_alert(self, doc_id: str, health: SessionHealth):
        """Trigger session health alert"""
        alert_data = {
            'alert_type': 'session_health',
            'doc_id': doc_id,
            'success_rate': health.success_rate,
            'error_count': health.error_count,
            'timestamp': datetime.now().isoformat()
        }
        
        for callback in self.alert_callbacks:
            try:
                callback(alert_data)
            except Exception as e:
                self.logger.error(f"Alert callback failed: {e}")


# Utility functions for monitoring setup

def setup_production_monitoring(valkey_manager: ValkeyManager,
                               cost_optimizer: GPT5CostOptimizer,
                               log_dir: str = "/tmp/gpt5_logs") -> GPT5Monitor:
    """Setup production monitoring with default configuration"""
    
    # Ensure log directory exists
    Path(log_dir).mkdir(exist_ok=True)
    log_file = Path(log_dir) / f"gpt5_monitor_{datetime.now().strftime('%Y%m%d')}.log"
    
    monitor = GPT5Monitor(
        valkey_manager=valkey_manager,
        cost_optimizer=cost_optimizer,
        log_file_path=str(log_file),
        enable_alerting=True,
        cost_alert_threshold=100.0,  # $100 USD
        error_rate_threshold=0.1      # 10% error rate
    )
    
    # Add default alert callback for logging
    def log_alert(alert_data: Dict[str, Any]):
        logging.getLogger("gpt5_alerts").critical(f"ALERT: {json.dumps(alert_data)}")
    
    monitor.add_alert_callback(log_alert)
    
    return monitor