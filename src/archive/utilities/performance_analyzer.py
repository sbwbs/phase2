"""
Performance Analyzer for Context Builder & Token Optimizer (CE-002)

This module provides comprehensive performance analysis and token usage measurement
for the context building system. Validates the 90%+ token reduction target and
provides detailed metrics for optimization strategies.

Key Features:
- Token usage analysis and optimization measurement
- Performance benchmarking across different scenarios
- Real-time monitoring of context building efficiency
- Integration with Phase 2 test data analysis
- Cost savings calculation and projection
"""

import logging
import asyncio
import time
import json
import statistics
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict

from token_optimizer import TokenOptimizer, ContextPriority
from context_builder import ContextBuilder, ContextRequest, create_context_request
from prompt_formatter import PromptFormatter, create_gpt5_config, create_gpt4_config


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for context building"""
    timestamp: datetime
    segment_id: str
    doc_id: str
    source_text_length: int
    baseline_tokens: int
    optimized_tokens: int
    token_reduction_absolute: int
    token_reduction_percent: float
    glossary_terms_found: int
    glossary_terms_included: int
    locked_terms_included: int
    previous_segments_included: int
    build_time_ms: float
    optimization_strategy: str
    meets_target: bool
    target_tokens: int
    cache_hit: bool
    component_breakdown: Dict[str, int]


@dataclass
class AggregatedMetrics:
    """Aggregated performance metrics across multiple segments"""
    total_segments: int
    avg_token_reduction_percent: float
    median_token_reduction_percent: float
    min_token_reduction_percent: float
    max_token_reduction_percent: float
    avg_build_time_ms: float
    target_achievement_rate: float
    cache_hit_rate: float
    total_tokens_saved: int
    estimated_cost_savings_usd: float
    performance_grade: str


@dataclass
class BenchmarkScenario:
    """Benchmark scenario configuration"""
    name: str
    description: str
    target_tokens: int
    segment_count: int
    include_glossary: bool
    include_previous_context: bool
    model_type: str


class PerformanceAnalyzer:
    """Advanced performance analysis engine for context building system"""
    
    # Cost estimates (USD per 1K tokens) for different models
    MODEL_COSTS = {
        'gpt-4o': {'input': 0.005, 'output': 0.015},
        'gpt-5': {'input': 0.003, 'output': 0.012},  # Estimated
        'gpt-4.1': {'input': 0.01, 'output': 0.03},
        'o3': {'input': 0.015, 'output': 0.06}  # Estimated higher cost
    }
    
    def __init__(self, 
                 context_builder: ContextBuilder,
                 enable_detailed_logging: bool = True,
                 save_results: bool = True,
                 results_directory: Optional[Path] = None):
        """
        Initialize performance analyzer
        
        Args:
            context_builder: Context builder instance to analyze
            enable_detailed_logging: Enable detailed metric logging
            save_results: Save analysis results to files
            results_directory: Directory to save results
        """
        self.context_builder = context_builder
        self.enable_logging = enable_detailed_logging
        self.save_results = save_results
        
        if results_directory:
            self.results_dir = Path(results_directory)
        else:
            self.results_dir = Path("performance_results")
        
        self.results_dir.mkdir(exist_ok=True)
        
        # Performance tracking
        self.metrics_history: List[PerformanceMetrics] = []
        self.benchmark_results: Dict[str, AggregatedMetrics] = {}
        
        self.logger = logging.getLogger(__name__)
        
        # Initialize token optimizer for baseline calculations
        self.token_optimizer = TokenOptimizer()
        
        self.logger.info(f"PerformanceAnalyzer initialized, results saved to: {self.results_dir}")
    
    async def analyze_segment(self, 
                            korean_text: str,
                            segment_id: str,
                            doc_id: str,
                            target_tokens: int = 500,
                            baseline_context: Optional[str] = None) -> PerformanceMetrics:
        """
        Analyze performance for a single segment
        
        Args:
            korean_text: Source Korean text
            segment_id: Segment identifier
            doc_id: Document identifier
            target_tokens: Target token limit
            baseline_context: Optional baseline context for comparison
            
        Returns:
            PerformanceMetrics for the segment
        """
        start_time = time.time()
        
        # Create context request
        request = create_context_request(
            korean_text=korean_text,
            segment_id=segment_id,
            doc_id=doc_id,
            optimization_target=target_tokens
        )
        
        # Build optimized context
        result = await self.context_builder.build_context(request)
        
        build_time = (time.time() - start_time) * 1000  # Convert to ms
        
        # Calculate baseline tokens if not provided
        if baseline_context:
            baseline_tokens = self.token_optimizer.count_tokens(baseline_context)
        else:
            baseline_tokens = result.performance_metrics.get('baseline_tokens', 0)
        
        # Create performance metrics
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            segment_id=segment_id,
            doc_id=doc_id,
            source_text_length=len(korean_text),
            baseline_tokens=baseline_tokens,
            optimized_tokens=result.token_count,
            token_reduction_absolute=baseline_tokens - result.token_count,
            token_reduction_percent=result.performance_metrics.get('token_reduction_percent', 0),
            glossary_terms_found=len(result.performance_metrics.get('glossary_results', [])),
            glossary_terms_included=result.glossary_terms_included,
            locked_terms_included=result.locked_terms_included,
            previous_segments_included=result.previous_segments_included,
            build_time_ms=build_time,
            optimization_strategy=result.optimization_result.optimization_strategy,
            meets_target=result.token_count <= target_tokens,
            target_tokens=target_tokens,
            cache_hit=result.cache_hit_rate > 0,
            component_breakdown=result.performance_metrics.get('component_breakdown', {})
        )
        
        # Store metrics
        self.metrics_history.append(metrics)
        
        if self.enable_logging:
            self.logger.info(f"Analyzed {segment_id}: {metrics.token_reduction_percent:.1f}% reduction, "
                           f"{metrics.optimized_tokens} tokens, {build_time:.1f}ms")
        
        return metrics
    
    async def run_benchmark(self, 
                          scenario: BenchmarkScenario,
                          test_segments: List[Tuple[str, str]]) -> AggregatedMetrics:
        """
        Run performance benchmark for a specific scenario
        
        Args:
            scenario: Benchmark scenario configuration
            test_segments: List of (korean_text, segment_id) tuples
            
        Returns:
            AggregatedMetrics for the benchmark
        """
        self.logger.info(f"Running benchmark: {scenario.name}")
        self.logger.info(f"Description: {scenario.description}")
        self.logger.info(f"Segments: {len(test_segments)}, Target: {scenario.target_tokens} tokens")
        
        metrics_list = []
        total_start_time = time.time()
        
        # Process segments
        for i, (korean_text, segment_id) in enumerate(test_segments):
            if i >= scenario.segment_count:
                break
            
            try:
                metrics = await self.analyze_segment(
                    korean_text=korean_text,
                    segment_id=segment_id,
                    doc_id=f"{scenario.name}_doc",
                    target_tokens=scenario.target_tokens
                )
                metrics_list.append(metrics)
                
            except Exception as e:
                self.logger.error(f"Failed to analyze segment {segment_id}: {e}")
                continue
        
        total_time = time.time() - total_start_time
        
        # Calculate aggregated metrics
        if metrics_list:
            aggregated = self._calculate_aggregated_metrics(metrics_list, scenario.name)
        else:
            # Create empty metrics if no segments processed
            aggregated = AggregatedMetrics(
                total_segments=0,
                avg_token_reduction_percent=0,
                median_token_reduction_percent=0,
                min_token_reduction_percent=0,
                max_token_reduction_percent=0,
                avg_build_time_ms=0,
                target_achievement_rate=0,
                cache_hit_rate=0,
                total_tokens_saved=0,
                estimated_cost_savings_usd=0,
                performance_grade="F"
            )
        
        # Store benchmark results
        self.benchmark_results[scenario.name] = aggregated
        
        self.logger.info(f"Benchmark completed: {aggregated.avg_token_reduction_percent:.1f}% "
                        f"avg reduction, {aggregated.target_achievement_rate:.1f}% target achievement")
        
        if self.save_results:
            await self._save_benchmark_results(scenario, aggregated, metrics_list)
        
        return aggregated
    
    def _calculate_aggregated_metrics(self, 
                                    metrics_list: List[PerformanceMetrics], 
                                    scenario_name: str) -> AggregatedMetrics:
        """Calculate aggregated metrics from individual measurements"""
        
        # Basic statistics
        reductions = [m.token_reduction_percent for m in metrics_list]
        build_times = [m.build_time_ms for m in metrics_list]
        target_achievements = [m.meets_target for m in metrics_list]
        cache_hits = [m.cache_hit for m in metrics_list]
        
        # Calculate cost savings
        total_tokens_saved = sum(m.token_reduction_absolute for m in metrics_list)
        estimated_cost_savings = self._calculate_cost_savings(metrics_list)
        
        # Performance grading
        avg_reduction = statistics.mean(reductions)
        target_rate = statistics.mean(target_achievements) * 100
        performance_grade = self._calculate_performance_grade(avg_reduction, target_rate)
        
        return AggregatedMetrics(
            total_segments=len(metrics_list),
            avg_token_reduction_percent=avg_reduction,
            median_token_reduction_percent=statistics.median(reductions),
            min_token_reduction_percent=min(reductions),
            max_token_reduction_percent=max(reductions),
            avg_build_time_ms=statistics.mean(build_times),
            target_achievement_rate=target_rate,
            cache_hit_rate=statistics.mean(cache_hits) * 100,
            total_tokens_saved=total_tokens_saved,
            estimated_cost_savings_usd=estimated_cost_savings,
            performance_grade=performance_grade
        )
    
    def _calculate_cost_savings(self, metrics_list: List[PerformanceMetrics]) -> float:
        """Calculate estimated cost savings in USD"""
        total_savings = 0.0
        
        for metrics in metrics_list:
            tokens_saved = metrics.token_reduction_absolute
            
            # Use GPT-4o costs as default for estimation
            cost_per_1k = self.MODEL_COSTS['gpt-4o']['input']
            savings = (tokens_saved / 1000) * cost_per_1k
            total_savings += savings
        
        return total_savings
    
    def _calculate_performance_grade(self, avg_reduction: float, target_rate: float) -> str:
        """Calculate performance grade based on key metrics"""
        # Scoring criteria
        if avg_reduction >= 90 and target_rate >= 95:
            return "A+"
        elif avg_reduction >= 85 and target_rate >= 90:
            return "A"
        elif avg_reduction >= 80 and target_rate >= 85:
            return "B+"
        elif avg_reduction >= 70 and target_rate >= 80:
            return "B"
        elif avg_reduction >= 60 and target_rate >= 70:
            return "C+"
        elif avg_reduction >= 50 and target_rate >= 60:
            return "C"
        else:
            return "D"
    
    async def run_comprehensive_analysis(self, 
                                       test_segments: List[Tuple[str, str]]) -> Dict[str, AggregatedMetrics]:
        """
        Run comprehensive analysis across multiple scenarios
        
        Args:
            test_segments: List of (korean_text, segment_id) tuples
            
        Returns:
            Dictionary of scenario results
        """
        self.logger.info("Starting comprehensive performance analysis")
        
        # Define benchmark scenarios
        scenarios = [
            BenchmarkScenario(
                name="standard_500_tokens",
                description="Standard scenario with 500 token target",
                target_tokens=500,
                segment_count=50,
                include_glossary=True,
                include_previous_context=True,
                model_type="gpt-4o"
            ),
            BenchmarkScenario(
                name="aggressive_300_tokens",
                description="Aggressive optimization with 300 token target",
                target_tokens=300,
                segment_count=30,
                include_glossary=True,
                include_previous_context=False,
                model_type="gpt-4o"
            ),
            BenchmarkScenario(
                name="minimal_200_tokens",
                description="Minimal context with 200 token target",
                target_tokens=200,
                segment_count=20,
                include_glossary=False,
                include_previous_context=False,
                model_type="gpt-4o"
            ),
            BenchmarkScenario(
                name="gpt5_optimized",
                description="GPT-5 optimized with reasoning",
                target_tokens=500,
                segment_count=25,
                include_glossary=True,
                include_previous_context=True,
                model_type="gpt-5"
            )
        ]
        
        results = {}
        
        # Run each scenario
        for scenario in scenarios:
            try:
                result = await self.run_benchmark(scenario, test_segments)
                results[scenario.name] = result
            except Exception as e:
                self.logger.error(f"Benchmark failed for {scenario.name}: {e}")
                continue
        
        # Generate comprehensive report
        if self.save_results:
            await self._generate_comprehensive_report(results)
        
        return results
    
    async def _save_benchmark_results(self,
                                    scenario: BenchmarkScenario,
                                    aggregated: AggregatedMetrics,
                                    metrics_list: List[PerformanceMetrics]):
        """Save benchmark results to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save detailed metrics as JSON
        detailed_file = self.results_dir / f"{scenario.name}_detailed_{timestamp}.json"
        detailed_data = {
            "scenario": asdict(scenario),
            "aggregated_metrics": asdict(aggregated),
            "individual_metrics": [asdict(m) for m in metrics_list]
        }
        
        with open(detailed_file, 'w') as f:
            json.dump(detailed_data, f, indent=2, default=str)
        
        # Save summary as CSV for easy analysis
        summary_file = self.results_dir / f"{scenario.name}_summary_{timestamp}.csv"
        metrics_df = pd.DataFrame([asdict(m) for m in metrics_list])
        metrics_df.to_csv(summary_file, index=False)
        
        self.logger.info(f"Saved results: {detailed_file.name}, {summary_file.name}")
    
    async def _generate_comprehensive_report(self, results: Dict[str, AggregatedMetrics]):
        """Generate comprehensive analysis report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.results_dir / f"comprehensive_analysis_{timestamp}.md"
        
        report_content = self._build_markdown_report(results)
        
        with open(report_file, 'w') as f:
            f.write(report_content)
        
        # Generate performance charts if matplotlib available
        try:
            await self._generate_performance_charts(results, timestamp)
        except ImportError:
            self.logger.warning("Matplotlib not available, skipping chart generation")
        
        self.logger.info(f"Comprehensive report saved: {report_file.name}")
    
    def _build_markdown_report(self, results: Dict[str, AggregatedMetrics]) -> str:
        """Build markdown report from analysis results"""
        report = [
            "# Context Builder Performance Analysis Report",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
            "## Executive Summary",
            ""
        ]
        
        # Calculate overall performance
        if results:
            avg_reductions = [r.avg_token_reduction_percent for r in results.values()]
            overall_reduction = statistics.mean(avg_reductions)
            
            target_rates = [r.target_achievement_rate for r in results.values()]
            overall_target_rate = statistics.mean(target_rates)
            
            total_savings = sum(r.estimated_cost_savings_usd for r in results.values())
            
            report.extend([
                f"- **Overall Token Reduction**: {overall_reduction:.1f}% average",
                f"- **Target Achievement Rate**: {overall_target_rate:.1f}%",
                f"- **Estimated Cost Savings**: ${total_savings:.4f} USD",
                f"- **CE-002 Target Status**: {'✅ ACHIEVED' if overall_reduction >= 90 else '❌ NOT ACHIEVED'} (Target: 90%+)",
                ""
            ])
        
        # Detailed scenario results
        report.extend([
            "## Scenario Results",
            "",
            "| Scenario | Segments | Avg Reduction | Target Rate | Grade | Cost Savings |",
            "|----------|----------|---------------|-------------|-------|--------------|"
        ])
        
        for name, metrics in results.items():
            report.append(
                f"| {name} | {metrics.total_segments} | "
                f"{metrics.avg_token_reduction_percent:.1f}% | "
                f"{metrics.target_achievement_rate:.1f}% | "
                f"{metrics.performance_grade} | "
                f"${metrics.estimated_cost_savings_usd:.4f} |"
            )
        
        report.extend([
            "",
            "## Key Findings",
            ""
        ])
        
        # Add findings based on results
        if results:
            best_scenario = max(results.items(), key=lambda x: x[1].avg_token_reduction_percent)
            worst_scenario = min(results.items(), key=lambda x: x[1].avg_token_reduction_percent)
            
            report.extend([
                f"- **Best Performance**: {best_scenario[0]} with {best_scenario[1].avg_token_reduction_percent:.1f}% reduction",
                f"- **Lowest Performance**: {worst_scenario[0]} with {worst_scenario[1].avg_token_reduction_percent:.1f}% reduction",
                ""
            ])
        
        # Recommendations
        report.extend([
            "## Recommendations",
            "",
            "### Token Optimization",
            "- Target achieved scenarios demonstrate effective context pruning",
            "- Glossary integration provides significant context value",
            "- Previous context inclusion shows diminishing returns in tight token budgets",
            "",
            "### Performance Optimization",
            "- Cache hit rates above 80% indicate effective caching strategy",
            "- Build times under 100ms per segment meet performance targets",
            "- Batch processing can further improve throughput",
            ""
        ])
        
        return "\n".join(report)
    
    async def _generate_performance_charts(self, results: Dict[str, AggregatedMetrics], timestamp: str):
        """Generate performance visualization charts"""
        # Token reduction comparison
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        
        scenarios = list(results.keys())
        reductions = [results[s].avg_token_reduction_percent for s in scenarios]
        target_rates = [results[s].target_achievement_rate for s in scenarios]
        build_times = [results[s].avg_build_time_ms for s in scenarios]
        grades = [results[s].performance_grade for s in scenarios]
        
        # Token reduction chart
        bars1 = ax1.bar(scenarios, reductions, color='skyblue')
        ax1.axhline(y=90, color='red', linestyle='--', label='90% Target')
        ax1.set_ylabel('Token Reduction %')
        ax1.set_title('Average Token Reduction by Scenario')
        ax1.legend()
        ax1.tick_params(axis='x', rotation=45)
        
        # Target achievement rate
        bars2 = ax2.bar(scenarios, target_rates, color='lightgreen')
        ax2.axhline(y=95, color='red', linestyle='--', label='95% Target')
        ax2.set_ylabel('Target Achievement Rate %')
        ax2.set_title('Target Achievement Rate by Scenario')
        ax2.legend()
        ax2.tick_params(axis='x', rotation=45)
        
        # Build time performance
        bars3 = ax3.bar(scenarios, build_times, color='orange')
        ax3.axhline(y=100, color='red', linestyle='--', label='100ms Target')
        ax3.set_ylabel('Build Time (ms)')
        ax3.set_title('Average Build Time by Scenario')
        ax3.legend()
        ax3.tick_params(axis='x', rotation=45)
        
        # Performance grades
        grade_colors = {'A+': 'darkgreen', 'A': 'green', 'B+': 'lightgreen', 
                       'B': 'yellow', 'C+': 'orange', 'C': 'red', 'D': 'darkred'}
        colors = [grade_colors.get(g, 'gray') for g in grades]
        ax4.bar(scenarios, [1] * len(scenarios), color=colors)
        ax4.set_ylabel('Performance Grade')
        ax4.set_title('Performance Grades by Scenario')
        ax4.set_yticks([])
        
        # Add grade labels
        for i, grade in enumerate(grades):
            ax4.text(i, 0.5, grade, ha='center', va='center', fontweight='bold', fontsize=12)
        
        ax4.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        chart_file = self.results_dir / f"performance_analysis_{timestamp}.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"Performance charts saved: {chart_file.name}")
    
    def get_real_time_metrics(self) -> Dict[str, Any]:
        """Get real-time performance metrics"""
        if not self.metrics_history:
            return {"status": "no_data", "metrics": {}}
        
        recent_metrics = self.metrics_history[-10:]  # Last 10 measurements
        
        return {
            "status": "active",
            "total_segments_analyzed": len(self.metrics_history),
            "recent_avg_reduction": statistics.mean([m.token_reduction_percent for m in recent_metrics]),
            "recent_avg_build_time": statistics.mean([m.build_time_ms for m in recent_metrics]),
            "recent_target_achievement": statistics.mean([m.meets_target for m in recent_metrics]) * 100,
            "cache_hit_rate": statistics.mean([m.cache_hit for m in recent_metrics]) * 100,
            "benchmark_results": {name: asdict(metrics) for name, metrics in self.benchmark_results.items()}
        }
    
    def export_metrics(self, format: str = "csv") -> str:
        """Export metrics in specified format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format.lower() == "csv":
            export_file = self.results_dir / f"metrics_export_{timestamp}.csv"
            metrics_df = pd.DataFrame([asdict(m) for m in self.metrics_history])
            metrics_df.to_csv(export_file, index=False)
        
        elif format.lower() == "json":
            export_file = self.results_dir / f"metrics_export_{timestamp}.json"
            export_data = {
                "export_timestamp": timestamp,
                "total_metrics": len(self.metrics_history),
                "metrics": [asdict(m) for m in self.metrics_history]
            }
            with open(export_file, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
        
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        self.logger.info(f"Metrics exported: {export_file.name}")
        return str(export_file)


# Test data generator for performance testing
def generate_test_segments() -> List[Tuple[str, str]]:
    """Generate test segments for performance analysis"""
    clinical_segments = [
        ("임상시험계획서에 따라 피험자를 선별하고 등록한다.", "clinical_001"),
        ("이상반응이 발생한 경우 즉시 보고하여야 한다.", "clinical_002"),
        ("치료 효과의 안전성과 유효성을 평가한다.", "clinical_003"),
        ("무작위배정을 통해 대조군과 시험군을 구성한다.", "clinical_004"),
        ("임상시험 대상자의 동의서를 확보해야 한다.", "clinical_005"),
        ("시험약물의 투여 방법과 용량을 결정한다.", "clinical_006"),
        ("피험자의 의학적 병력을 상세히 검토한다.", "clinical_007"),
        ("임상시험의 주요 평가변수를 설정한다.", "clinical_008"),
        ("안전성 모니터링을 위한 계획을 수립한다.", "clinical_009"),
        ("데이터 수집 및 관리 절차를 정의한다.", "clinical_010")
    ]
    
    return clinical_segments


# Main execution for standalone testing
if __name__ == "__main__":
    """Run performance analysis when executed directly"""
    import sys
    from test_context_builder_integration import TestRealDataProcessing
    
    async def main():
        print("Context Builder Performance Analysis")
        print("=" * 40)
        
        # Setup test environment
        test_setup = TestRealDataProcessing()
        test_setup.setup_method()
        
        # Initialize performance analyzer
        analyzer = PerformanceAnalyzer(
            context_builder=test_setup.context_builder,
            enable_detailed_logging=True,
            save_results=True
        )
        
        # Generate test data
        test_segments = generate_test_segments()
        
        print(f"Running analysis on {len(test_segments)} test segments...")
        
        # Run comprehensive analysis
        results = await analyzer.run_comprehensive_analysis(test_segments)
        
        # Print summary
        print("\n" + "=" * 40)
        print("ANALYSIS SUMMARY")
        print("=" * 40)
        
        for scenario_name, metrics in results.items():
            print(f"\n{scenario_name.upper()}:")
            print(f"  Token Reduction: {metrics.avg_token_reduction_percent:.1f}%")
            print(f"  Target Achievement: {metrics.target_achievement_rate:.1f}%")
            print(f"  Performance Grade: {metrics.performance_grade}")
            print(f"  Cost Savings: ${metrics.estimated_cost_savings_usd:.4f}")
        
        # Validate CE-002 target
        overall_reduction = statistics.mean([m.avg_token_reduction_percent for m in results.values()])
        print(f"\n{'='*40}")
        print("CE-002 TARGET VALIDATION")
        print(f"{'='*40}")
        print(f"Overall Token Reduction: {overall_reduction:.1f}%")
        print(f"Target Achievement: {'✅ PASSED' if overall_reduction >= 90 else '❌ FAILED'} (Target: 90%+)")
        
        # Export metrics
        export_file = analyzer.export_metrics("csv")
        print(f"\nDetailed metrics exported to: {export_file}")
    
    # Run the analysis
    asyncio.run(main())