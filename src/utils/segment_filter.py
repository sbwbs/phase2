#!/usr/bin/env python3
"""
Intelligent Segment Filtering for Translation Pipelines
Provides auto-copy functionality for trivial content that doesn't need LLM processing
"""

import re
from typing import Tuple, Dict, Any

class SegmentFilter:
    """Filter to identify segments that should be auto-copied without LLM processing"""
    
    def __init__(self):
        """Initialize segment filter with conservative rules"""
        self.auto_copy_count = 0
        self.total_segments = 0
        
    def should_auto_copy(self, text: str) -> Tuple[bool, str]:
        """
        Determine if segment should be auto-copied without LLM processing
        
        Args:
            text: Source text segment
            
        Returns:
            Tuple of (should_copy, reason)
        """
        if not text:
            return True, "empty_segment"
            
        text_clean = text.strip()
        
        # Empty or whitespace-only
        if not text_clean:
            return True, "whitespace_only"
            
        # Single characters/numbers (most conservative)
        if len(text_clean) == 1:
            return True, "single_character"
            
        # Pure punctuation (very conservative)
        if len(text_clean) <= 3 and all(c in ".,;:()/[]{}*-+=" for c in text_clean):
            return True, "pure_punctuation"
            
        return False, "needs_translation"
    
    def process_segment(self, segment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single segment, applying auto-copy if appropriate
        
        Args:
            segment_data: Dictionary containing segment information
            
        Returns:
            Updated segment data with auto-copy applied if appropriate
        """
        self.total_segments += 1
        
        source_text = segment_data.get('source_en', segment_data.get('source_ko', ''))
        should_copy, reason = self.should_auto_copy(source_text)
        
        if should_copy:
            self.auto_copy_count += 1
            
            # Create auto-copy result
            segment_data['auto_copied'] = True
            segment_data['auto_copy_reason'] = reason
            segment_data['translated_text'] = source_text  # Direct copy
            segment_data['processing_time'] = 0.0
            segment_data['api_cost'] = 0.0
            segment_data['quality_score'] = 1.0  # Perfect for exact copy
            
        else:
            segment_data['auto_copied'] = False
            
        return segment_data
    
    def filter_batch_for_llm(self, batch_data: list) -> Tuple[list, list]:
        """
        Filter batch to separate auto-copy segments from LLM-required segments
        
        Args:
            batch_data: List of segment dictionaries
            
        Returns:
            Tuple of (llm_segments, auto_copy_segments)
        """
        llm_segments = []
        auto_copy_segments = []
        
        for segment in batch_data:
            processed_segment = self.process_segment(segment.copy())
            
            if processed_segment['auto_copied']:
                auto_copy_segments.append(processed_segment)
            else:
                llm_segments.append(segment)  # Original segment for LLM
                
        return llm_segments, auto_copy_segments
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get filtering statistics"""
        if self.total_segments == 0:
            return {"no_segments_processed": True}
            
        auto_copy_rate = (self.auto_copy_count / self.total_segments) * 100
        
        return {
            "total_segments": self.total_segments,
            "auto_copied": self.auto_copy_count,
            "llm_processed": self.total_segments - self.auto_copy_count,
            "auto_copy_rate": auto_copy_rate,
            "estimated_cost_savings": f"{auto_copy_rate:.1f}% API cost reduction"
        }
    
    def reset_statistics(self):
        """Reset internal counters"""
        self.auto_copy_count = 0
        self.total_segments = 0


def demo_segment_filter():
    """Demonstrate segment filter functionality"""
    print("🔍 Segment Filter Demo")
    print("=" * 40)
    
    # Test segments (common patterns from real data)
    test_segments = [
        "1",
        "2", 
        "/",
        "-",
        ".",
        "Protocol No.",  # This will need LLM (>3 chars)
        "A",
        "CONFIDENTIAL",  # This will need LLM  
        "The sponsor representative will monitor adverse events.",  # Needs LLM
        "",
        "   ",
        "*",
        "()",
        "[]"
    ]
    
    filter = SegmentFilter()
    
    print("Testing segments:")
    for i, text in enumerate(test_segments, 1):
        should_copy, reason = filter.should_auto_copy(text)
        status = "✅ AUTO-COPY" if should_copy else "🔄 LLM NEEDED"
        print(f"{i:2d}. '{text}' → {status} ({reason})")
    
    print(f"\nResults: {filter.get_statistics()}")


if __name__ == "__main__":
    demo_segment_filter()