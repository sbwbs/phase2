#!/usr/bin/env python3
"""
Style Guide Configuration for A/B Testing
Configurable variants to test quality vs. token efficiency
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
import json
import os
from datetime import datetime


class StyleGuideVariant(Enum):
    """Available style guide variants for A/B testing"""
    NONE = "none"                    # No style guide (baseline)
    MINIMAL = "minimal"              # Essential only (~100 tokens)
    COMPACT = "compact"              # Condensed version (~200 tokens)
    STANDARD = "standard"            # Full style guide (~400 tokens)
    COMPREHENSIVE = "comprehensive"  # Extended with examples (~600 tokens)
    CLINICAL_PROTOCOL = "clinical_protocol"  # EN-KO Clinical Protocol specialized (~300 tokens)
    CLINICAL_PROTOCOL_STRICT = "clinical_protocol_strict"  # EN-KO Strict literal translation (~250 tokens)
    CLINICAL_PROTOCOL_DATA_DRIVEN = "clinical_protocol_data_driven"  # EN-KO with data-driven rules from actual TMX (~1200 tokens) NEW!
    REGULATORY_COMPLIANCE = "regulatory_compliance"  # KO-EN Regulatory compliance (~300 tokens)
    REGULATORY_COMPLIANCE_ENHANCED = "regulatory_compliance_enhanced"  # KO-EN with examples (~900 tokens)
    CLINICAL_PROTOCOL_STRICT_ENHANCED = "clinical_protocol_strict_enhanced"  # EN-KO with examples (~900 tokens)
    # SKBS ICF (Informed Consent Form) variants - NEW
    ICF_FORMAL = "icf_formal"        # KO-EN Adult consent - formal regulatory (~400 tokens)
    ICF_CHILD_FRIENDLY = "icf_child_friendly"  # KO-EN Children's assent 7-12 - simplified (~800 tokens)
    CUSTOM = "custom"                # User-defined configuration


@dataclass
class StyleGuideConfig:
    """Configuration for style guide variants"""
    variant: StyleGuideVariant
    name: str
    description: str
    estimated_tokens: int
    quality_score: float  # Expected quality improvement (0.0-1.0)
    token_efficiency: float  # Token reduction maintained (0.0-1.0)
    enabled: bool = True
    custom_rules: Optional[Dict] = None


class StyleGuideManager:
    """Manages different style guide variants for A/B testing"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "style_guide_config.json"
        self.variants = self._load_variants()
        self.current_variant = StyleGuideVariant.STANDARD
        self.experiment_mode = False
        self.experiment_results = {}
        
    def _load_variants(self) -> Dict[StyleGuideVariant, StyleGuideConfig]:
        """Load style guide variants from configuration"""
        variants = {
            StyleGuideVariant.NONE: StyleGuideConfig(
                variant=StyleGuideVariant.NONE,
                name="No Style Guide",
                description="Baseline translation without style instructions",
                estimated_tokens=0,
                quality_score=0.0,
                token_efficiency=1.0,
                enabled=True
            ),
            
            StyleGuideVariant.MINIMAL: StyleGuideConfig(
                variant=StyleGuideVariant.MINIMAL,
                name="Minimal Style Guide",
                description="Essential ICH-GCP requirements only",
                estimated_tokens=100,
                quality_score=0.3,
                token_efficiency=0.95,
                enabled=True
            ),
            
            StyleGuideVariant.COMPACT: StyleGuideConfig(
                variant=StyleGuideVariant.COMPACT,
                name="Compact Style Guide",
                description="Condensed version with key rules",
                estimated_tokens=200,
                quality_score=0.6,
                token_efficiency=0.90,
                enabled=True
            ),
            
            StyleGuideVariant.STANDARD: StyleGuideConfig(
                variant=StyleGuideVariant.STANDARD,
                name="Standard Style Guide",
                description="Full clinical protocol style guide",
                estimated_tokens=400,
                quality_score=0.8,
                token_efficiency=0.85,
                enabled=True
            ),
            
            StyleGuideVariant.COMPREHENSIVE: StyleGuideConfig(
                variant=StyleGuideVariant.COMPREHENSIVE,
                name="Comprehensive Style Guide",
                description="Extended with examples and detailed rules",
                estimated_tokens=600,
                quality_score=0.9,
                token_efficiency=0.80,
                enabled=True
            ),
            
            StyleGuideVariant.CLINICAL_PROTOCOL: StyleGuideConfig(
                variant=StyleGuideVariant.CLINICAL_PROTOCOL,
                name="EN-KO Clinical Protocol",
                description="Specialized for EN→KO clinical protocol translation",
                estimated_tokens=300,
                quality_score=0.85,
                token_efficiency=0.88,
                enabled=True
            ),
            
            StyleGuideVariant.CLINICAL_PROTOCOL_STRICT: StyleGuideConfig(
                variant=StyleGuideVariant.CLINICAL_PROTOCOL_STRICT,
                name="EN-KO Strict Literal",
                description="Strict literal translation for regulatory review",
                estimated_tokens=250,
                quality_score=0.92,
                token_efficiency=0.90,
                enabled=True
            ),
            
            StyleGuideVariant.REGULATORY_COMPLIANCE: StyleGuideConfig(
                variant=StyleGuideVariant.REGULATORY_COMPLIANCE,
                name="KO-EN Regulatory",
                description="KO→EN with hallucination prevention and conciseness",
                estimated_tokens=300,
                quality_score=0.88,
                token_efficiency=0.85,
                enabled=True
            ),

            StyleGuideVariant.REGULATORY_COMPLIANCE_ENHANCED: StyleGuideConfig(
                variant=StyleGuideVariant.REGULATORY_COMPLIANCE_ENHANCED,
                name="KO-EN Enhanced with Examples",
                description="KO→EN with style guide + few-shot examples",
                estimated_tokens=900,
                quality_score=0.93,
                token_efficiency=0.75,
                enabled=True
            ),

            StyleGuideVariant.CLINICAL_PROTOCOL_STRICT_ENHANCED: StyleGuideConfig(
                variant=StyleGuideVariant.CLINICAL_PROTOCOL_STRICT_ENHANCED,
                name="EN-KO Enhanced with Examples",
                description="EN→KO with style guide + few-shot examples",
                estimated_tokens=900,
                quality_score=0.95,
                token_efficiency=0.75,
                enabled=True
            ),

            StyleGuideVariant.CLINICAL_PROTOCOL_DATA_DRIVEN: StyleGuideConfig(
                variant=StyleGuideVariant.CLINICAL_PROTOCOL_DATA_DRIVEN,
                name="EN-KO Data-Driven Rules",
                description="EN→KO with 27 rules extracted from 4,902 professional translation pairs",
                estimated_tokens=1200,
                quality_score=0.96,
                token_efficiency=0.72,
                enabled=True
            ),

            # SKBS ICF (Informed Consent Form) variants - NEW
            StyleGuideVariant.ICF_FORMAL: StyleGuideConfig(
                variant=StyleGuideVariant.ICF_FORMAL,
                name="KO-EN Adult ICF Formal",
                description="KO→EN formal regulatory register for adult consent forms",
                estimated_tokens=400,
                quality_score=0.90,
                token_efficiency=0.85,
                enabled=True
            ),

            StyleGuideVariant.ICF_CHILD_FRIENDLY: StyleGuideConfig(
                variant=StyleGuideVariant.ICF_CHILD_FRIENDLY,
                name="KO-EN Children's Assent (7-12)",
                description="KO→EN child-friendly language for pediatric assent forms, based on GSK/Moderna reference",
                estimated_tokens=800,
                quality_score=0.92,
                token_efficiency=0.80,
                enabled=True
            )
        }
        
        # Load custom variants if config file exists
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    custom_config = json.load(f)
                    for variant_name, config_data in custom_config.get('custom_variants', {}).items():
                        if variant_name not in [v.value for v in StyleGuideVariant]:
                            custom_variant = StyleGuideVariant(variant_name)
                            variants[custom_variant] = StyleGuideConfig(
                                variant=custom_variant,
                                **config_data
                            )
            except Exception as e:
                print(f"Warning: Could not load custom style guide config: {e}")
        
        return variants
    
    def get_style_guide(self, variant: StyleGuideVariant) -> str:
        """Get the style guide content for the specified variant"""
        if variant == StyleGuideVariant.NONE:
            return ""
        
        elif variant == StyleGuideVariant.MINIMAL:
            return self._get_minimal_style_guide()
        
        elif variant == StyleGuideVariant.COMPACT:
            return self._get_compact_style_guide()
        
        elif variant == StyleGuideVariant.STANDARD:
            return self._get_standard_style_guide()
        
        elif variant == StyleGuideVariant.COMPREHENSIVE:
            return self._get_comprehensive_style_guide()
        
        elif variant == StyleGuideVariant.CLINICAL_PROTOCOL:
            return self._get_en_ko_clinical_protocol_style_guide()
        
        elif variant == StyleGuideVariant.CLINICAL_PROTOCOL_STRICT:
            return self._get_en_ko_clinical_protocol_strict_style_guide()

        elif variant == StyleGuideVariant.CLINICAL_PROTOCOL_DATA_DRIVEN:
            return self._get_en_ko_data_driven_style_guide()

        elif variant == StyleGuideVariant.REGULATORY_COMPLIANCE:
            return self._get_ko_en_regulatory_compliance_style_guide()

        elif variant == StyleGuideVariant.REGULATORY_COMPLIANCE_ENHANCED:
            return self._get_ko_en_enhanced_with_examples()

        elif variant == StyleGuideVariant.CLINICAL_PROTOCOL_STRICT_ENHANCED:
            return self._get_en_ko_enhanced_with_examples()

        elif variant == StyleGuideVariant.ICF_FORMAL:
            return self._get_icf_formal_style_guide()

        elif variant == StyleGuideVariant.ICF_CHILD_FRIENDLY:
            return self._get_icf_child_friendly_style_guide()

        elif variant == StyleGuideVariant.CUSTOM:
            return self._get_custom_style_guide()

        else:
            return self._get_standard_style_guide()
    
    def _get_minimal_style_guide(self) -> str:
        """Minimal essential style guide (~100 tokens)"""
        return """\n## Style: ICH-GCP Clinical Protocol
- Use formal professional register
- 임상시험→Clinical Study, 시험대상자→Study Subject
- Follow ICH-GCP terminology standards
- Maintain regulatory compliance"""
    
    def _get_compact_style_guide(self) -> str:
        """Compact style guide (~200 tokens)"""
        return """\n## Style: ICH-GCP Clinical Protocol

**REGISTER & FORMALITY:**
- Formal professional register (합니다→will/shall)
- Neutral tone, declarative statements

**TERMINOLOGY:**
- 임상시험→Clinical Study (protocol context)
- 시험대상자→Study Subject (trial context)
- 이상반응→Adverse Event (not side effect)
- 임상시험용 의약품→Investigational Product

**COMPLIANCE:**
- Follow ICH-GCP E6(R2) standards
- Subject safety priority
- Written informed consent required"""
    
    def _get_standard_style_guide(self) -> str:
        """Standard style guide (~400 tokens)"""
        return """\n## Clinical Protocol Style Guide (ICH-GCP E6(R2))

**REGISTER & FORMALITY:**
- Use formal professional register throughout
- Transform Korean honorifics (합니다/습니다) → neutral professional (will/shall)
- Use declarative statements for procedures, conditional for contingencies
- Maintain neutral, objective tone without cultural hierarchical markers

**SENTENCE STRUCTURE:**
- Break long Korean sentences (>20 words) into 2-3 shorter English sentences
- Maximum 25 words per English sentence for regulatory clarity
- Use active voice for procedures ("The investigator will assess...")
- Use passive voice for results ("Efficacy will be evaluated...")

**TERMINOLOGY CONSISTENCY:**
- 임상시험 → Clinical Study (NOT Clinical Trial in protocol context)
- 임상시험용 의약품 → Investigational Product (NOT test drug)
- 시험대상자 → Study Subject (NOT patient in trial context)
- 이상반응 → Adverse Event (NOT side effect)
- 중대한 이상반응 → Serious Adverse Event

**REGULATORY COMPLIANCE:**
- Include: "This study will be conducted in accordance with Declaration of Helsinki, ICH-GCP"
- Priority: "The safety and well-being of study subjects is the highest priority"
- Consent: "All study subjects must provide written informed consent"
- Risk: "The risk-benefit ratio has been assessed and documented" """
    
    def _get_comprehensive_style_guide(self) -> str:
        """Comprehensive style guide with examples (~600 tokens)"""
        return """\n## Comprehensive Clinical Protocol Style Guide (ICH-GCP E6(R2))

**REGISTER & FORMALITY:**
- Use formal professional register throughout all sections
- Transform Korean honorifics (합니다/습니다) → neutral professional (will/shall)
- Use declarative statements for procedures, conditional for contingencies
- Maintain neutral, objective tone without cultural hierarchical markers
- Authority: Use declarative statements for procedures, conditional for contingencies

**SENTENCE STRUCTURE TRANSFORMATION:**
- Break long Korean sentences (>20 words) into 2-3 shorter English sentences
- Maximum 25 words per English sentence for regulatory clarity
- Maintain logical flow and causal relationships
- Use active voice for procedures ("The investigator will assess...")
- Use passive voice for results ("Efficacy will be evaluated...")
- Requirements: Use modal verbs ("Subjects must provide...")

**TERMINOLOGY CONSISTENCY STANDARDS:**
- 임상시험 → Clinical Study (NOT Clinical Trial in protocol context)
- 임상시험용 의약품 → Investigational Product (NOT test drug)
- 시험대상자 → Study Subject (NOT patient in trial context)
- 이상반응 → Adverse Event (NOT side effect)
- 중대한 이상반응 → Serious Adverse Event
- 동의서 → Informed Consent (NOT consent form)

**CONTEXT-DEPENDENT TERMINOLOGY:**
- 환자 → Study Subject (trial context), Patient (medical context)
- 치료 → Intervention (trial context), Treatment (medical context)
- 효과 → Efficacy/Effectiveness (trial context), Effect (general context)

**REGULATORY COMPLIANCE LANGUAGE:**
- Framework: "This study will be conducted in accordance with the Declaration of Helsinki, ICH-GCP, and all applicable national regulations"
- Safety Priority: "The safety and well-being of study subjects is the highest priority"
- Informed Consent: "All study subjects must provide written informed consent before participation"
- Risk Assessment: "The risk-benefit ratio has been assessed and documented in the protocol"
- Monitoring: "Continuous safety monitoring will ensure subject protection throughout the study"

**CULTURAL ADAPTATION PATTERNS:**
- Neutralize Korean hierarchical language patterns (습니다 → will/shall)
- Maintain professional authority without cultural markers
- Use direct requirement statements (must/shall) for obligations
- Transform indirect obligation expressions to direct requirements

**ABBREVIATION STANDARDS:**
- First Use: Always spell out with abbreviation in parentheses
- Subsequent Use: Abbreviation only within the same section
- Cross-References: Spell out when referring across major sections
- Example: "The Investigational Product (IP) will be administered... Later, the IP dosing schedule..." """
    
    def _get_custom_style_guide(self) -> str:
        """Custom style guide based on user configuration"""
        if self.variants.get(StyleGuideVariant.CUSTOM) and self.variants[StyleGuideVariant.CUSTOM].custom_rules:
            return self._build_custom_style_guide(self.variants[StyleGuideVariant.CUSTOM].custom_rules)
        return self._get_standard_style_guide()
    
    def _get_en_ko_clinical_protocol_style_guide(self) -> str:
        """EN-KO Clinical Protocol style guide (~250 tokens)"""
        return """\n## EN→KO Clinical Protocol Style Guide

**TERMINOLOGY CONSISTENCY:**
- Clinical Study Protocol → 임상시험계획서
- Phase 1/2/3 → 제1상/제2상/제3상
- Open-label → 공개 라벨  
- Dose Escalation → 용량 증량
- Multicenter → 다기관
- Safety → 안전성
- Pharmacokinetics → 약동학
- Acute Myeloid Leukemia → 급성 골수성 백혈병

**BILINGUAL FORMAT:**
- Medical conditions: Korean(English, ABBREV) → 급성 골수성 백혈병(Acute Myeloid Leukemia, AML)
- Technical terms: Korean(English) → 최대 내약 용량(maximum tolerated dose)
- Drug/protocol codes: Keep unchanged

**FORMAL REGISTER (Natural Korean Flow):**
- Statements: ~다/~된다 endings
- Procedures: ~실시된다/~수행된다  
- Requirements: ~해야 한다
- Definitions: ~으로 정의된다

**SENTENCE STRUCTURE:**
- Adapt English SVO to Korean SOV naturally
- Break long compound sentences for Korean flow
- Use passive voice for procedural language
- Move time expressions to sentence beginning"""
    
    def _build_custom_style_guide(self, custom_rules: Dict) -> str:
        """Build custom style guide from user rules"""
        style_guide = "\n## Custom Clinical Protocol Style Guide\n"
        
        for section, rules in custom_rules.items():
            style_guide += f"\n**{section.upper()}:**\n"
            if isinstance(rules, list):
                for rule in rules:
                    style_guide += f"- {rule}\n"
            elif isinstance(rules, dict):
                for key, value in rules.items():
                    style_guide += f"- {key}: {value}\n"
            else:
                style_guide += f"- {rules}\n"
        
        return style_guide
    
    def _get_en_ko_clinical_protocol_strict_style_guide(self) -> str:
        """EN-KO Strict Literal Translation style guide (~250 tokens)"""
        return """\n## 🔒 EN→KO Strict Literal Translation Guide

**CORE PRINCIPLE: DIRECT TRANSLATION ONLY**
- 직역 최우선: 원문의 의미만 정확히 전달
- 정보 추가 절대 금지: 원문에 없는 내용 추가 불허
- 주관적 해석 금지: 평가나 판단 표현 사용 불가

**MANDATORY REGULATORY TERMS:**
- Title Page → 제목페이지 (NOT 표지)
- Sponsor Representative → 의뢰자 대표자 (NOT 의뢰자)
- Clinical Study Protocol → 임상시험계획서
- Informed Consent → 동의서
- Adverse Event → 이상반응
- Investigational Product → 임상시험용 의약품

**TRANSLATION APPROACH:**
- 보수적 번역: 영문본과 한글본 대조 심사 고려
- 표준화된 용어: 식약처 임상시험 용어집 기준
- 격식있는 문체: 합니다체 사용
- 객관적 표현: "적정함", "우수함" 등 주관적 표현 금지

**STRUCTURE:**
- 어순 조정: 영어 SVO → 한국어 SOV
- 문법적 조정만 허용: 조사, 어미 등
- 문장 분할: 긴 문장은 자연스럽게 분리"""
    
    def _get_ko_en_regulatory_compliance_style_guide(self) -> str:
        """KO-EN Regulatory Compliance with Customer Feedback Rules (~500 tokens)"""
        return """\n## KO→EN Clinical Protocol Translation Guide

**MODAL VERB HIERARCHY (MANDATORY - must > shall > should > will):**
- **must**: Legal/regulatory requirements (IRB approval, consent documentation, legal compliance)
  Example: "반드시 문서로 기록되어야 한다" → "must be documented"
- **shall**: Protocol-defined procedures (investigator obligations, data handling)
  Example: "제3자에게 공개될 수 없습니다" → "shall not be disclosed to any third party"
- **should**: Recommendations, cautionary guidance (MFDS/ICH guidelines)
  Example: "병용투여를 주의한다" → "should be administered with caution"
- **will**: Factual statements, analysis descriptions, scheduling
  Example: "Safety Set으로 분석한다" → "will be conducted using the Safety Set"

**SUBJECT TERMINOLOGY (MANDATORY):**
- 대상자/시험대상자 → "Subjects" (consistent throughout, NOT "study subjects", "individual", "person")
- Use "Subjects who..." for eligibility criteria (NOT "Participation in..." or "Any person...")

**CRITICAL TERMINOLOGY CORRECTIONS:**
- 비율 (achievement/response context) → "rate" (NOT "ratio")
  Example: 혈압 정상화 비율 → "Blood pressure normalization rate"
- 신장 (body measurement) → "height" (NOT "renal function")
- 대체 날짜 (statistics/imputation) → "Imputed date" (NOT "Alternate date")
- 임상시험 → "clinical study" (NOT "clinical trial" in protocol context)
- 이상반응 → "adverse event" (NOT "side effect")
- 교수 → "Professor" ONLY (NEVER add MD/PhD unless stated)

**FORMATTING RULES (MANDATORY):**
- Korean names: "Last, First" format with comma and space (조현지 → "Jo, Hyun Ji")
- Symbols to words: ≥ → "or greater", ≤ → "or less", > → "greater than", < → "less than"
- Capitalization: Capitalize specific timepoints (Week 4, Visit 1, Screening, Randomization)
- Treatment designations: Study Group, Control Group (capitalize)
- Generic drug names: lowercase first letter

**SENTENCE STRUCTURE RULES:**
- Revision history: Use past tense consistently ("Added", "Changed", "Clarified")
- Procedures: Use passive/descriptive form ("will be collected", "will be measured")
  ❌ "Collect demographic data..."
  ✅ "Demographic characteristics will be collected."
- Prepositions: Use "from baseline at Week X" consistently

**SPLIT SEGMENT HANDLING:**
- When Korean sentence spans multiple segments, maintain grammatical continuity
- Each segment translation must connect naturally with adjacent segments
- Preserve sentence structure even when segments break mid-sentence

**CONTENT INTEGRITY (CRITICAL):**
- NO content addition: Never add information not in Korean source
- NO content omission: Preserve all source content
- Verify English terms in source text match output exactly (check for typos)

**ANTI-HALLUCINATION RULES:**
- Translate ONLY what exists in Korean source
- Every English sentence must have Korean equivalent
- NO elaboration or interpretation"""

    def _get_ko_en_enhanced_with_examples(self) -> str:
        """KO-EN Enhanced with Customer Feedback Rules + Examples (~1100 tokens)"""
        return """\n## KO→EN Clinical Protocol Translation Guide (Enhanced)

### PART 1: MANDATORY RULES FROM CUSTOMER FEEDBACK

**MODAL VERB HIERARCHY (must > shall > should > will):**
| Modal | Usage | Korean Indicator |
|-------|-------|------------------|
| must | Legal/regulatory requirements | 반드시, 필수, 법적 의무 |
| shall | Protocol-defined procedures | 규정됨, 절차, ~수 없다 |
| should | Recommendations | 권고, 주의, 가능하면 |
| will | Factual statements, analysis | ~한다 (descriptive), 예정 |

**SUBJECT TERMINOLOGY (MANDATORY):**
- Always use "Subjects" (NOT "study subjects", "individual", "person")
- Eligibility criteria: "Subjects who..." (NOT "Participation in..." / "Any person...")

**CRITICAL TERM CORRECTIONS:**
- 비율 (achievement context) → "rate" (NOT "ratio")
- 신장 (body measurement) → "height" (NOT "renal function")
- 대체 날짜 (statistics) → "Imputed date" (NOT "Alternate date")
- 임상시험 → "clinical study" (NOT "clinical trial" in protocol)
- 이상반응 → "adverse event" (NOT "side effect")
- 교수 → "Professor" ONLY (NEVER add MD/PhD)

**FORMATTING (MANDATORY):**
- Korean names: "Last, First" format (조현지 → "Jo, Hyun Ji")
- Symbols: ≥ → "or greater", ≤ → "or less", > → "greater than", < → "less than"
- Capitalization: Week, Visit, Screening, Randomization, Study Group, Control Group
- Generic drug names: lowercase first letter

**SENTENCE STRUCTURE:**
- Revision history: Past tense ("Added", "Changed", "Clarified")
- Procedures: Passive form ("will be collected", "will be measured")
- Prepositions: "from baseline at Week X" consistently

**SPLIT SEGMENT HANDLING:**
- Maintain grammatical continuity across segments
- Each segment must connect naturally with adjacent segments

**CONTENT INTEGRITY:**
- NO additions beyond source text
- NO omissions from source text
- Verify English in source matches output (typo check)

---

### PART 2: CUSTOMER-APPROVED EXAMPLES

**Example 1 - Modal Verb (must):**
KO: 대상자가 동의한 내용은 반드시 문서로 기록되어야 한다.
EN: Subjects' informed consent must be documented.
✓ "must" for legal requirement (반드시)

**Example 2 - Modal Verb (shall):**
KO: 본 임상시험 계획서에 포함된 모든 정보는...의뢰자의 사전 서면 동의 없이 제3자에게 공개될 수 없습니다
EN: All information contained in this protocol...shall not be disclosed to any third party without prior written informed consent of the sponsor.
✓ "shall" for protocol-defined prohibition

**Example 3 - Modal Verb (should):**
KO: 아래의 약물 요법은 스크리닝(방문 1) 시점부터 임상시험 종료 시까지 병용투여를 주의한다.
EN: The following drug therapies should be administered with caution in combination from Screening (Visit 1) until the end of the study.
✓ "should" for recommendation (주의한다)

**Example 4 - Modal Verb (will):**
KO: 안전성 분석은 Safety Set(이하 'SS')으로 분석한다.
EN: Safety analysis will be conducted using the Safety Set (hereinafter "SS").
✓ "will" for factual analysis statement

**Example 5 - Subject Consistency:**
KO: 스크리닝(방문 1) 시점으로부터 4주 이내에 다른 임상시험에 참여하여 IP를 투여받은 자
EN: Subjects who participated in another study involving the administration of an IP within 4 weeks prior to Screening (Visit 1)
✓ "Subjects who..." format, NOT "Participation in..."

**Example 6 - Rate vs Ratio:**
KO: 4주, 8주 시점의 혈압 정상화 비율
EN: Blood pressure normalization rate at Weeks 4 and 8
✓ "rate" for achievement metrics (NOT "ratio")

**Example 7 - Height vs Renal:**
KO: 스크리닝(방문 1) 시 신장 및 체중을 측정하며
EN: During Screening (Visit 1), height and body weight will be measured.
✓ "height" for 신장 (body measurement context, NOT "renal function")

**Example 8 - Name Formatting:**
KO: 조현지 / BSR
EN: Jo, Hyun Ji / BSR
✓ "Last, First" format with comma and space

**Example 9 - Symbol Conversion:**
KO: MSSBP 20 mmHg 이상 감소
EN: decrease in MSSBP of 20 mmHg or greater
✓ Symbols written as words (NOT "≥20 mmHg")

**Example 10 - Passive Procedure:**
KO: 인구학적 정보를 조사한다.
EN: Demographic characteristics will be collected.
✓ Passive descriptive form, NOT imperative "Collect demographic data"

**Example 11 - No Content Addition:**
KO: "어린이의 손이 닿지 않는 곳에 보관한다."
EN: "Keep out of reach of children."
✓ No added content (removed "and store in a secure location for retention")

---

**CRITICAL ANTI-HALLUCINATION:**
- 교수 = "Professor" ONLY (never MD/PhD)
- Translate ONLY source content - every English word must have Korean equivalent"""

    def _get_en_ko_enhanced_with_examples(self) -> str:
        """EN-KO Enhanced with Generalizable Style Guide + Few-Shot Examples (~900 tokens)"""
        return """\n## 🔒 EN→KO Strict Literal Clinical Protocol Translation Guide (Enhanced)

### PART 1: GENERALIZABLE STYLE & TERMINOLOGY

**TONE & REGISTER (extracted from professional translations):**
- 격식있는 합니다체 (formal -합니다 style)
- 객관적 서술: 주관적 평가 표현 금지 (적정함, 우수함 등)
- 자연스러운 한국어 어순 (SOV)
- 의학/규제 전문 용어 사용

**SENTENCE TRANSFORMATION PATTERNS:**
- English SVO → Korean SOV 자연스럽게 전환
- 시간 표현: 문장 앞으로 이동
- 긴 영어 복합문: 한국어 2-3문장으로 자연스럽게 분할
- 수동태 선호: 절차적 언어에서 (~실시된다, ~수행된다)
- 문장 종결: 진술문(~다/~된다), 절차(~실시된다), 요구사항(~해야 한다)

**MANDATORY REGULATORY TERMS (필수 규제 용어):**
- Title Page → 제목페이지 (NOT 표지)
- Sponsor Representative → 의뢰자 대리인 (NOT 의뢰자 대표자)
- Clinical Study Protocol → 임상시험계획서
- Informed Consent → 동의서
- Adverse Event → 이상반응
- Investigational Product → 임상시험용 의약품
- Phase 1/2/3 → 제1상/제2상/제3상

**BILINGUAL TERMINOLOGY FORMAT:**
- Medical conditions: Korean(English, ABBREV)
  Example: 급성 골수성 백혈병(Acute Myeloid Leukemia, AML)
- Technical terms: Korean(English)
  Example: 최대 내약 용량(maximum tolerated dose)
- Drug/protocol codes: KEEP UNCHANGED
  Example: ZE46-0134 → ZE46-0134

**TRANSLATION APPROACH:**
- 직역 최우선: 원문 의미만 정확히 전달
- 정보 추가 절대 금지: 원문에 없는 내용 불허
- 보수적 번역: 영문본-한글본 대조 심사 고려
- 식약처 임상시험 용어집 기준

---

### PART 2: FEW-SHOT LEARNING EXAMPLES

**Example 1 - Phase 1 Protocol Title with Bilingual Format:**
EN: A Phase 1, Open-label, Dose Escalation and Dose Expansion, Multicenter Clinical Trial to Evaluate the Safety, Pharmacokinetics, Pharmacodynamics, and Preliminary Efficacy of ZE46-0134 in Adults with FLT3 mutated Relapsed or Refractory Acute Myeloid Leukemia (AML)
KO: FLT3 돌연변이 재발성 또는 불응성 급성 골수성 백혈병(Acute Myeloid Leukemia, AML) 성인 환자를 대상으로 ZE46-0134의 안전성, 약동학, 약력학 및 예비 유효성을 평가하기 위한 제1상, 공개 라벨, 용량 증량 및 용량 확장, 다기관 임상시험
✓ Bilingual medical term format, natural SOV order, technical accuracy, drug code unchanged

**Example 2 - Sponsor Information:**
EN: Lomond Therapeutics AU Pty Ltd (A subsidiary of Lomond Therapeutics, LLC)
KO: Lomond Therapeutics AU Pty Ltd (Lomond Therapeutics, LLC의 자회사)
✓ Company names unchanged, natural Korean possessive structure

**Example 3 - Signature Block (Mandatory Term):**
EN: Signature of Sponsor Representative
KO: 의뢰자 대리인의 서명
✓ MUST use 대리인 (NOT 대표자), natural possessive form

**Example 4 - Formal Attestation:**
EN: By my signature, I confirm that I have reviewed this protocol and find its content to be acceptable.
KO: 본인은 서명을 통해 본 임상시험계획서를 검토했으며 그 내용이 수용 가능함을 확인합니다.
✓ Formal 합니다체, time expression to beginning, natural flow

**Example 5 - Printed Name Format:**
EN: Printed Name of Sponsor Representative
KO: 의뢰자 대리인 이름(정자체)
✓ Mandatory term + bilingual clarification format

---

**CRITICAL RULES:**
- 원문에 없는 정보 추가 절대 금지
- 태그 보존: 모든 <태그>와 [메타데이터] 정확히 유지
- 의뢰자 대리인 (NOT 대표자) - 필수 용어"""

    def _get_en_ko_data_driven_style_guide(self) -> str:
        """EN-KO Data-Driven Style Guide with Rules Extracted from 4,902 Professional Translation Pairs (~1200 tokens)"""
        return """\n## 📊 EN→KO PROTOCOL TRANSLATION RULES
**Extracted from 4,902 professional translation pairs from actual clinical protocol documents**

### PART 1: CRITICAL TERMINOLOGY RULES

**Core Protocol Terms (MUST-FOLLOW):**
- Clinical Study Protocol → 임상시험계획서 (NEVER "연구 계획서")
- Protocol Number → 임상시험계획서 번호 (NOT "프로토콜 번호")
- Sponsor → 의뢰자 / Investigator → 시험책임자 / Participant → 시험대상자
- Adverse Event → 이상사례 (NOT "부작용")
- Serious Adverse Event → 중대한 이상사례
- Good Clinical Practice → 임상시험관리기준(GCP)

**Study Design Terms (MUST-FOLLOW):**
- Multicenter → 다기관 (NOT "다중센터")
- Open-Label → 공개 / Randomized → 무작위 배정
- Phase 2a → 제2a상 / Double-blind → 이중맹검

### PART 2: MODAL VERB PATTERNS (CRITICAL)

**"Will" Pattern (Procedural - Remove Modal):**
EN: Interested participants will sign the ICF.
KO: 희망 시험대상자는 적절한 시험대상자 동의서에 서명해야 한다.
✓ Use direct verb + obligation marker

**"Must" Pattern (Strong Obligation):**
EN: Study documentation must indicate if a visit was conducted...
KO: 임상시험 문서에는 방문 수행 여부가 명시되어야 한다.
✓ Always use "~해야 한다" or "~하여야 한다"

**"Shall" Pattern (Procedural Guidance):**
EN: The participant shall be asked a nonleading question.
KO: 시험대상자에게 다음과 같은 비유도적 질문을 할 수 있다.
✓ Context-dependent: ~할 수 있다 vs ~해야 한다

**"May" Pattern (Permission/Possibility):**
EN: Information may not be disclosed unless required...
KO: 공개가 요구되지 않는 한 공개될 수 없다.
✓ Use "~될 수 없다" or "~할 수 있다"

### PART 3: PASSIVE VOICE PATTERNS

**Pattern 1: Passive → Active (Agent Implied):**
EN: Participants will be assessed for eligibility.
KO: 시험대상자에 대해 적격성을 평가한다.
✓ Active voice with implied agent

**Pattern 2: Passive → Korean Passive (~되다):**
EN: All remote visits must be conducted in compliance with GCP.
KO: 모든 원격 방문이 GCP를 준수하여 수행되어야 한다.
✓ Use passive when emphasizing the action

### PART 4: STRUCTURAL PATTERNS

**Long Sentences → Break Into Clauses:**
EN: Participants who meet the selection criteria will be assessed for eligibility for randomization.
KO: 선정 기준에 부합하는 시험대상자에 대해 무작위 배정에 대한 적격성을 평가한다.

**Title Case → Sentence Case:**
EN: PRINCIPAL INVESTIGATOR SIGNATURE PAGE → KO: 시험책임자 서명 페이지
✓ No ALL CAPS in Korean

**Formal Statements:**
EN: By my signature, I confirm that I have reviewed this protocol...
KO: 본인은 서명을 통해, 본 임상시험계획서를 검토하고 그 내용이 허용 가능함을 확인하였습니다.

### PART 5: AVOID PATTERNS (Common Mistakes)

❌ AVOID: 그 시험자는 그 증상들을 검토할 것이다 (Over-literal articles)
✅ CORRECT: 시험자는 증상을 검토한다 (Natural Korean)

❌ AVOID: 임상 연구 계획서 (Wrong study term)
✅ CORRECT: 임상시험계획서 ("시험" for regulatory)

❌ AVOID: 환자 in regulatory context (Patient ≠ Participant)
✅ CORRECT: 시험대상자 (Regulatory participant)

❌ AVOID: Literal "will" translation (미래형)
✅ CORRECT: Direct verb + obligation (~해야 한다, ~한다)

### PART 6: QUALITY CHECKLIST

✓ Terminology: All regulatory terms match approved Korean equivalents
✓ Modal Verbs: Must > Shall > Should > Will hierarchy respected
✓ Passive Voice: English passive converted to natural Korean (active or passive)
✓ Structure: Long sentences broken into natural Korean flow
✓ No Information Addition: Every English word has Korean equivalent in source
✓ Tag Preservation: All <tags> and [metadata] preserved exactly

**Expected Quality with These Rules: 0.95+ (from actual TM analysis)**
**Token Efficiency: Maintained at 98% reduction vs naive approach**"""

    def _get_icf_formal_style_guide(self) -> str:
        """ICF Formal - Adult Consent Form KO→EN (~400 tokens)"""
        return """\n## KO→EN Clinical Trial Informed Consent Form Translation Guide

**REQUIREMENTS:**
- Formal regulatory register appropriate for adult/guardian consent forms
- Follow ICH GCP terminology standards
- Preserve all CAT tool tags exactly: <123>, </123>, <456/>

**MANDATORY TERMINOLOGY:**
- 임상시험 → "clinical trial"
- 시험대상자 → "study participant" / "subject"
- 이상반응 → "adverse event"
- 동의서 → "informed consent form"
- 설명서 → "information sheet"
- 의뢰자 → "sponsor"
- 시험약 → "investigational product"
- 위약 → "placebo"
- 무작위 배정 → "randomization"
- 보호자 → "guardian" / "legally acceptable representative"

**STYLE GUIDELINES:**
- Maintain legal precision for regulatory submission
- Use passive voice for procedures ("will be conducted")
- Include parenthetical clarifications for technical terms
- Preserve Korean name format if present

**EXAMPLES (Varicella Vaccine Clinical Trial):**
KO: 귀하의 자녀는 본 임상시험에 참여하도록 제안 받았습니다.
EN: Your child has been proposed to participate in this clinical trial.

KO: 시험대상자 설명서 및 서면 동의서
EN: Participant Information Sheet and Written Informed Consent Form

KO: 건강한 생후 12개월 ~ 12세 소아를 대상으로
EN: In healthy children aged 12 months to 12 years

KO: 무작위 배정, 관찰자 눈가림, 활성 대조, 제3상 임상시험
EN: Randomized, observer-blind, active-controlled, Phase 3 clinical trial

**CONTENT INTEGRITY:**
- NO additions beyond source text
- NO omissions from source text
- Preserve all CAT tags exactly as they appear"""

    def _get_icf_child_friendly_style_guide(self) -> str:
        """ICF Child-Friendly - Children's Assent Form KO→EN ages 7-12 (~800 tokens)
        Based on GSK/Moderna pediatric assent form reference documents"""
        return """\n## KO→EN Pediatric Research Assent Form Translation Guide

**TARGET AUDIENCE:** Children ages 7-12 years old
Based on GSK/Moderna pediatric assent form standards

**CORE PRINCIPLES:**
1. **AUTONOMY** - Emphasize child's right to choose
2. **EMOTIONAL SAFETY** - Reassure no punishment for declining
3. **ACCURACY** - Maintain medical accuracy with simplified language
4. **CLARITY** - Short sentences, concrete examples
5. **COMPLIANCE** - Age-appropriate ICH-GCP language

**CHILD-FRIENDLY TERMINOLOGY:**
- 임상시험/조사 → "research study" (NOT "clinical trial")
- 예방주사/백신 → "vaccine shot" / "injection"
- 이상반응/부작용 → "side effects"
- 위약 → "placebo" + explain: "a shot that looks real but has no medicine"
- 무작위 배정 → "decided by chance, like flipping a coin"
- 피를 뽑다 → "take a small amount of blood"
- 의사 선생님 → "doctor" / "the study doctor"
- 부모님/보호자 → "your parent(s)" / "your guardian"

**REASSURANCE PATTERNS (from GSK reference):**
- "No one will be angry or upset if you decide not to take part"
- "You can stop at any time without giving a reason"
- "Even if your parents say yes, you can still say no"

**SENTENCE STRUCTURE:**
- Keep sentences short (12-18 words average)
- Use direct address ("you", "your")
- Avoid complex medical jargon
- Use concrete examples over abstract concepts

**GOLDEN EXAMPLES (Based on GSK Pediatric Assent):**

Example 1 - Introduction:
KO: 이 설명서는 여러분이 이 조사에 참여할 것인지를 결정하는 데 도움을 주기 위해 작성되었습니다.
EN: This information sheet has been prepared to help you decide whether to take part in this study.

Example 2 - Reassurance:
KO: 연구에 참여하지 않겠다고 하더라도 화를 내거나 속상해하는 사람은 아무도 없습니다.
EN: No one will be angry or upset with you if you decide not to take part in the study.

Example 3 - Autonomy despite parental consent:
KO: 부모님께서 연구 참여에 동의하셨더라도 여러분이 참여하고 싶지 않으면 참여하지 않아도 됩니다.
EN: Even if your parents have agreed to your participation, you do not have to take part if you do not want to.

Example 4 - Placebo explanation:
KO: 위약(속임약)은 진짜 약처럼 보이지만 실제로는 약 성분이 들어 있지 않습니다.
EN: A placebo (trick medicine) looks like real medicine but does not actually contain any active ingredients.

Example 5 - Blood draw:
KO: 팔에서 소량의 피를 뽑게 됩니다. 약간 따끔할 수 있습니다.
EN: A small amount of blood will be taken from your arm. It may sting a little.

Example 6 - Right to withdraw:
KO: 언제든지 이유를 밝히지 않고 연구 참여를 그만둘 수 있습니다.
EN: You can stop taking part at any time without giving a reason.

Example 7 - Vaccine explanation (SK Bioscience context):
KO: 이 연구는 수두가 어린이들을 아프게 만들기 전에 막을 수 있는 예방주사(백신)를 만들기 위한 연구입니다.
EN: This study is about making a vaccine shot that can stop chickenpox from making children sick.

**PRESERVE ALL CAT TAGS:** <123>, </123>, <456/>

**CONTENT INTEGRITY:**
- Keep medical accuracy while simplifying language
- NO scary or overly clinical language
- Use reassuring tone throughout
- Preserve child's sense of control and choice"""

    def set_variant(self, variant: StyleGuideVariant) -> None:
        """Set the current style guide variant"""
        if variant in self.variants and self.variants[variant].enabled:
            self.current_variant = variant
            print(f"✅ Style guide variant set to: {self.variants[variant].name}")
        else:
            print(f"❌ Style guide variant '{variant.value}' not available or disabled")
    
    def enable_experiment_mode(self, variants: List[StyleGuideVariant]) -> None:
        """Enable A/B testing mode with specified variants"""
        self.experiment_mode = True
        self.experiment_variants = [v for v in variants if v in self.variants and self.variants[v].enabled]
        print(f"🧪 Experiment mode enabled with variants: {[v.value for v in self.experiment_variants]}")
    
    def get_experiment_variant(self, segment_id: int) -> StyleGuideVariant:
        """Get style guide variant for A/B testing (round-robin)"""
        if not self.experiment_mode:
            return self.current_variant
        
        variant_index = segment_id % len(self.experiment_variants)
        return self.experiment_variants[variant_index]
    
    def record_experiment_result(self, variant: StyleGuideVariant, segment_id: int, 
                               quality_score: float, token_count: int, processing_time: float) -> None:
        """Record experiment results for analysis"""
        if variant not in self.experiment_results:
            self.experiment_results[variant] = []
        
        self.experiment_results[variant].append({
            'segment_id': segment_id,
            'quality_score': quality_score,
            'token_count': token_count,
            'processing_time': processing_time,
            'timestamp': datetime.now().isoformat()
        })
    
    def get_experiment_summary(self) -> Dict:
        """Get summary of experiment results"""
        if not self.experiment_mode:
            return {}
        
        summary = {}
        for variant, results in self.experiment_results.items():
            if results:
                avg_quality = sum(r['quality_score'] for r in results) / len(results)
                avg_tokens = sum(r['token_count'] for r in results) / len(results)
                avg_time = sum(r['processing_time'] for r in results) / len(results)
                
                summary[variant.value] = {
                    'name': self.variants[variant].name,
                    'segments_translated': len(results),
                    'average_quality_score': avg_quality,
                    'average_token_count': avg_tokens,
                    'average_processing_time': avg_time,
                    'token_efficiency': self.variants[variant].token_efficiency
                }
        
        return summary
    
    def save_experiment_results(self, filename: str = None) -> None:
        """Save experiment results to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"style_guide_experiment_{timestamp}.json"
        
        results = {
            'experiment_config': {
                'variants_tested': [v.value for v in self.experiment_variants],
                'total_segments': sum(len(r) for r in self.experiment_results.values())
            },
            'variant_results': self.get_experiment_summary(),
            'detailed_results': self.experiment_results
        }
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"💾 Experiment results saved to: {filename}")
    
    def get_available_variants(self) -> List[StyleGuideVariant]:
        """Get list of available and enabled variants"""
        return [v for v, config in self.variants.items() if config.enabled]
    
    def print_variant_info(self) -> None:
        """Print information about available variants"""
        print("\n🎨 Available Style Guide Variants:")
        print("-" * 80)
        for variant, config in self.variants.items():
            if config.enabled:
                status = "✓" if variant == self.current_variant else " "
                print(f"{status} {variant.value:15} | {config.name:25} | "
                      f"Tokens: {config.estimated_tokens:4} | "
                      f"Quality: {config.quality_score:.1f} | "
                      f"Efficiency: {config.token_efficiency:.2f}")
        print("-" * 80)


# Example usage and testing
if __name__ == "__main__":
    # Initialize style guide manager
    manager = StyleGuideManager()
    
    # Show available variants
    manager.print_variant_info()
    
    # Test different variants
    print("\n🧪 Testing Style Guide Variants:")
    for variant in [StyleGuideVariant.NONE, StyleGuideVariant.MINIMAL, StyleGuideVariant.STANDARD, StyleGuideVariant.CLINICAL_PROTOCOL]:
        style_guide = manager.get_style_guide(variant)
        token_count = len(style_guide) // 4
        print(f"\n{variant.value.upper()} ({token_count} tokens):")
        print(style_guide[:200] + "..." if len(style_guide) > 200 else style_guide)
    
    # Enable experiment mode
    manager.enable_experiment_mode([StyleGuideVariant.NONE, StyleGuideVariant.STANDARD])
    
    # Simulate experiment
    for i in range(5):
        variant = manager.get_experiment_variant(i)
        style_guide = manager.get_style_guide(variant)
        token_count = len(style_guide) // 4
        quality_score = 0.5 + (0.5 if variant != StyleGuideVariant.NONE else 0.0)
        
        manager.record_experiment_result(variant, i, quality_score, token_count, 1.0)
        print(f"Segment {i}: {variant.value} → Quality: {quality_score:.2f}, Tokens: {token_count}")
    
    # Show results
    print("\n📊 Experiment Summary:")
    summary = manager.get_experiment_summary()
    for variant, data in summary.items():
        print(f"{variant}: {data['segments_translated']} segments, "
              f"Avg Quality: {data['average_quality_score']:.2f}, "
              f"Avg Tokens: {data['average_token_count']}")
    
    # Save results
    manager.save_experiment_results()
