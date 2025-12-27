#!/usr/bin/env python3
"""
Reference-Based Translation Evaluation System
Compares generated translations against expected reference translations using structured LLM evaluation
"""

import os
import sys
import json
import pandas as pd
import logging
import time
import openai
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv("/Users/won.suh/Project/translate-ai/.env")

@dataclass
class EvaluationResult:
    """Structured evaluation result from LLM"""
    segment_id: int
    source_text: str
    expected_translation: str
    generated_translation: str
    match_rating: int
    terminology_accuracy: int
    meaning_preservation: int
    regulatory_compliance: int
    gap_analysis: str
    specific_issues: List[str]
    improvement_suggestions: List[str]
    overall_grade: str
    pass_fail: str
    evaluation_cost: float
    evaluation_time: float

class ReferenceEvaluationSystem:
    """System for evaluating generated translations against reference translations"""
    
    def __init__(self, model_name: str = "gpt-4o"):
        """Initialize evaluation system"""
        self.model_name = model_name
        self.client = openai.OpenAI()
        self.setup_logging()
        
        # Evaluation statistics
        self.total_evaluations = 0
        self.total_cost = 0.0
        self.total_time = 0.0
        
    def setup_logging(self):
        """Setup logging for evaluation system"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('reference_evaluation_system')
        
    def create_evaluation_prompt(self, source: str, expected: str, generated: str, direction: str) -> str:
        """Create structured evaluation prompt for LLM"""
        
        direction_context = {
            'ko-en': {
                'source_lang': 'Korean',
                'target_lang': 'English',
                'focus': 'regulatory compliance and clinical terminology accuracy',
                'standards': 'ICH-GCP guidelines for clinical trial documentation'
            },
            'en-ko': {
                'source_lang': 'English', 
                'target_lang': 'Korean',
                'focus': 'natural Korean expression and clinical terminology consistency',
                'standards': 'Korean medical documentation standards'
            }
        }
        
        ctx = direction_context.get(direction, direction_context['ko-en'])
        
        prompt = f"""You are a medical translation quality expert evaluating {ctx['source_lang']} to {ctx['target_lang']} translations for clinical trial documentation.

EVALUATION TASK:
The EXPECTED translation is the professional reference standard. Evaluate how well the GENERATED translation matches the EXPECTED translation.

SOURCE ({ctx['source_lang']}): {source}
EXPECTED (Reference): {expected}
GENERATED (Our Output): {generated}

EVALUATION CRITERIA:
Focus on {ctx['focus']} following {ctx['standards']}.

Provide your evaluation in this EXACT JSON format:
{{
  "match_rating": <0-100 integer>,
  "terminology_accuracy": <0-100 integer>,
  "meaning_preservation": <0-100 integer>,
  "regulatory_compliance": <0-100 integer>,
  "gap_analysis": "<detailed description of differences vs expected>",
  "specific_issues": ["<issue 1>", "<issue 2>"],
  "improvement_suggestions": ["<suggestion 1>", "<suggestion 2>"],
  "overall_grade": "<A+/A/A-/B+/B/B-/C+/C/C-/D+/D/F>",
  "pass_fail": "<PASS/FAIL>"
}}

SCORING GUIDELINES:
- match_rating: Overall similarity to expected (90-100=excellent, 80-89=good, 70-79=acceptable, <70=needs work)
- terminology_accuracy: Correctness of medical/clinical terms (100=perfect match, 90+=minor variants, <80=errors)
- meaning_preservation: Semantic accuracy vs expected (100=identical meaning, 90+=equivalent, <80=meaning loss)
- regulatory_compliance: Adherence to clinical standards (100=fully compliant, <90=compliance issues)
- pass_fail: PASS if match_rating ≥ 70 AND no critical regulatory issues

Respond ONLY with the JSON object, no additional text."""

        return prompt
    
    def evaluate_single_comparison(self, 
                                   source: str, 
                                   expected: str, 
                                   generated: str, 
                                   direction: str = "ko-en",
                                   segment_id: int = 0) -> EvaluationResult:
        """Evaluate a single translation against reference"""
        
        start_time = time.time()
        
        # Create evaluation prompt
        prompt = self.create_evaluation_prompt(source, expected, generated, direction)
        
        try:
            # Call LLM for evaluation
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a medical translation quality expert. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.1  # Low temperature for consistent evaluation
            )
            
            # Extract and parse JSON response
            evaluation_text = response.choices[0].message.content.strip()
            
            # Clean up JSON response (remove any markdown formatting)
            if evaluation_text.startswith("```json"):
                evaluation_text = evaluation_text.replace("```json", "").replace("```", "").strip()
            
            evaluation_data = json.loads(evaluation_text)
            
            # Calculate cost
            evaluation_cost = (response.usage.prompt_tokens * 0.15 + response.usage.completion_tokens * 0.60) / 1000
            evaluation_time = time.time() - start_time
            
            # Update statistics
            self.total_evaluations += 1
            self.total_cost += evaluation_cost
            self.total_time += evaluation_time
            
            # Create structured result
            result = EvaluationResult(
                segment_id=segment_id,
                source_text=source,
                expected_translation=expected,
                generated_translation=generated,
                match_rating=evaluation_data.get('match_rating', 0),
                terminology_accuracy=evaluation_data.get('terminology_accuracy', 0),
                meaning_preservation=evaluation_data.get('meaning_preservation', 0),
                regulatory_compliance=evaluation_data.get('regulatory_compliance', 0),
                gap_analysis=evaluation_data.get('gap_analysis', ''),
                specific_issues=evaluation_data.get('specific_issues', []),
                improvement_suggestions=evaluation_data.get('improvement_suggestions', []),
                overall_grade=evaluation_data.get('overall_grade', 'F'),
                pass_fail=evaluation_data.get('pass_fail', 'FAIL'),
                evaluation_cost=evaluation_cost,
                evaluation_time=evaluation_time
            )
            
            self.logger.info(f"✅ Evaluated segment {segment_id}: Grade {result.overall_grade}, Match {result.match_rating}%")
            return result
            
        except json.JSONDecodeError as e:
            self.logger.error(f"❌ JSON parsing error for segment {segment_id}: {e}")
            self.logger.error(f"Raw response: {evaluation_text}")
            return self._create_error_result(segment_id, source, expected, generated, f"JSON parsing error: {e}")
            
        except Exception as e:
            self.logger.error(f"❌ Evaluation error for segment {segment_id}: {e}")
            return self._create_error_result(segment_id, source, expected, generated, f"Evaluation error: {e}")
    
    def evaluate_batch_comparisons(self, 
                                   comparisons: List[Tuple[str, str, str]], 
                                   direction: str = "ko-en",
                                   batch_size: int = 5) -> List[EvaluationResult]:
        """Evaluate multiple translation comparisons in batches"""
        
        all_results = []
        total_comparisons = len(comparisons)
        
        self.logger.info(f"🔍 Starting batch evaluation of {total_comparisons} comparisons")
        
        # Process in batches to manage cost and time
        for i in range(0, total_comparisons, batch_size):
            batch = comparisons[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_comparisons + batch_size - 1) // batch_size
            
            self.logger.info(f"⚙️ Evaluating batch {batch_num}/{total_batches} ({len(batch)} comparisons)...")
            
            # Evaluate each comparison in the batch
            batch_results = []
            for j, (source, expected, generated) in enumerate(batch):
                segment_id = i + j + 1
                result = self.evaluate_single_comparison(source, expected, generated, direction, segment_id)
                batch_results.append(result)
                
                # Small delay to avoid rate limiting
                time.sleep(0.1)
            
            all_results.extend(batch_results)
            
            # Progress update
            if batch_num % 3 == 0 or batch_num == total_batches:
                avg_time = self.total_time / self.total_evaluations
                remaining = (total_comparisons - len(all_results)) * avg_time
                self.logger.info(f"   Progress: {len(all_results)}/{total_comparisons} | Avg: {avg_time:.2f}s/eval | ETA: {remaining/60:.1f}min | Cost: ${self.total_cost:.3f}")
        
        self.logger.info(f"✅ Batch evaluation complete: {len(all_results)} evaluations")
        return all_results
    
    def _create_error_result(self, segment_id: int, source: str, expected: str, generated: str, error_msg: str) -> EvaluationResult:
        """Create error result for failed evaluations"""
        return EvaluationResult(
            segment_id=segment_id,
            source_text=source,
            expected_translation=expected,
            generated_translation=generated,
            match_rating=0,
            terminology_accuracy=0,
            meaning_preservation=0,
            regulatory_compliance=0,
            gap_analysis=f"Evaluation failed: {error_msg}",
            specific_issues=[f"System error: {error_msg}"],
            improvement_suggestions=["Retry evaluation"],
            overall_grade="ERROR",
            pass_fail="FAIL",
            evaluation_cost=0.0,
            evaluation_time=0.0
        )
    
    def generate_evaluation_report(self, results: List[EvaluationResult]) -> Dict:
        """Generate comprehensive evaluation report"""
        
        if not results:
            return {"error": "No evaluation results provided"}
        
        # Calculate aggregate statistics
        valid_results = [r for r in results if r.overall_grade != "ERROR"]
        
        if not valid_results:
            return {"error": "No valid evaluation results"}
        
        avg_match_rating = sum(r.match_rating for r in valid_results) / len(valid_results)
        avg_terminology = sum(r.terminology_accuracy for r in valid_results) / len(valid_results)
        avg_meaning = sum(r.meaning_preservation for r in valid_results) / len(valid_results)
        avg_compliance = sum(r.regulatory_compliance for r in valid_results) / len(valid_results)
        
        # Grade distribution
        grade_counts = {}
        for result in valid_results:
            grade = result.overall_grade
            grade_counts[grade] = grade_counts.get(grade, 0) + 1
        
        # Pass/fail statistics
        pass_count = sum(1 for r in valid_results if r.pass_fail == "PASS")
        pass_rate = (pass_count / len(valid_results)) * 100
        
        # Most common issues
        all_issues = []
        for result in valid_results:
            all_issues.extend(result.specific_issues)
        
        issue_counts = {}
        for issue in all_issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
        
        top_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        report = {
            "evaluation_summary": {
                "total_evaluations": len(results),
                "valid_evaluations": len(valid_results),
                "error_evaluations": len(results) - len(valid_results),
                "total_cost": f"${self.total_cost:.3f}",
                "total_time": f"{self.total_time/60:.2f} minutes",
                "cost_per_evaluation": f"${self.total_cost/len(valid_results):.4f}" if valid_results else "$0.0000"
            },
            "quality_metrics": {
                "average_match_rating": f"{avg_match_rating:.1f}%",
                "average_terminology_accuracy": f"{avg_terminology:.1f}%",
                "average_meaning_preservation": f"{avg_meaning:.1f}%",
                "average_regulatory_compliance": f"{avg_compliance:.1f}%",
                "pass_rate": f"{pass_rate:.1f}%"
            },
            "grade_distribution": grade_counts,
            "top_issues": top_issues,
            "pass_fail_summary": {
                "passed": pass_count,
                "failed": len(valid_results) - pass_count,
                "pass_rate_percent": f"{pass_rate:.1f}%"
            }
        }
        
        return report
    
    def export_results_to_excel(self, results: List[EvaluationResult], filename: str = None) -> str:
        """Export evaluation results to Excel file"""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"evaluation_results_{timestamp}.xlsx"
        
        # Convert results to DataFrame
        data = []
        for result in results:
            data.append({
                'Segment_ID': result.segment_id,
                'Source_Text': result.source_text,
                'Expected_Translation': result.expected_translation,
                'Generated_Translation': result.generated_translation,
                'Match_Rating': result.match_rating,
                'Terminology_Accuracy': result.terminology_accuracy,
                'Meaning_Preservation': result.meaning_preservation,
                'Regulatory_Compliance': result.regulatory_compliance,
                'Gap_Analysis': result.gap_analysis,
                'Specific_Issues': '; '.join(result.specific_issues),
                'Improvement_Suggestions': '; '.join(result.improvement_suggestions),
                'Overall_Grade': result.overall_grade,
                'Pass_Fail': result.pass_fail,
                'Evaluation_Cost': result.evaluation_cost,
                'Evaluation_Time': result.evaluation_time
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file with multiple sheets
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # Main results
            df.to_excel(writer, sheet_name='Evaluation_Results', index=False)
            
            # Summary statistics
            report = self.generate_evaluation_report(results)
            summary_data = []
            
            # Flatten report for Excel
            for category, metrics in report.items():
                if isinstance(metrics, dict):
                    for key, value in metrics.items():
                        summary_data.append({
                            'Category': category,
                            'Metric': key,
                            'Value': value
                        })
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary_Statistics', index=False)
            
            # Grade distribution
            if 'grade_distribution' in report:
                grade_data = []
                for grade, count in report['grade_distribution'].items():
                    grade_data.append({'Grade': grade, 'Count': count})
                
                grade_df = pd.DataFrame(grade_data)
                grade_df.to_excel(writer, sheet_name='Grade_Distribution', index=False)
        
        self.logger.info(f"📊 Evaluation results exported to: {filename}")
        return filename

def demo_evaluation_system():
    """Demonstrate the evaluation system with sample data"""
    print("🔍 Reference-Based Evaluation System Demo")
    print("=" * 60)
    
    # Initialize evaluation system
    evaluator = ReferenceEvaluationSystem()
    
    # Sample comparison data (Korean to English)
    sample_comparisons = [
        (
            "원광대학교병원 소화기내과 최석채 교수",
            "Professor Choi Seok-chae, Division of Gastroenterology, Wonkwang University Hospital", 
            "Professor Choi Seokchae, Division of Gastroenterology, Wonkwang University Hospital"
        ),
        (
            "임상시험계획서에 따라 연구를 수행한다",
            "The study will be conducted according to the clinical trial protocol",
            "Research will be performed according to the clinical study protocol"
        ),
        (
            "이상반응 보고서를 작성해야 한다",
            "Adverse event reports must be prepared",
            "Side effect reports should be created"
        )
    ]
    
    print(f"🧪 Evaluating {len(sample_comparisons)} sample translations...")
    
    # Evaluate comparisons
    results = evaluator.evaluate_batch_comparisons(sample_comparisons, direction="ko-en")
    
    # Generate report
    report = evaluator.generate_evaluation_report(results)
    
    # Display results
    print(f"\n📊 EVALUATION RESULTS:")
    print(f"Average Match Rating: {report['quality_metrics']['average_match_rating']}")
    print(f"Pass Rate: {report['quality_metrics']['pass_rate']}")
    print(f"Total Cost: {report['evaluation_summary']['total_cost']}")
    
    # Export results
    filename = evaluator.export_results_to_excel(results, "demo_evaluation_results.xlsx")
    print(f"Results exported to: {filename}")

if __name__ == "__main__":
    demo_evaluation_system()