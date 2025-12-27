#!/usr/bin/env python3
"""
Tag Preservation Handler for CAT Tool Integration
Handles XML-style tags and metadata brackets in clinical translation
"""

import re
import openai
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class TagType(Enum):
    """Types of tags found in CAT tool exports"""
    SELF_CLOSING = "self_closing"  # <123/>
    OPENING = "opening"            # <123>
    CLOSING = "closing"            # </123>
    METADATA = "metadata"          # [IN_ECN_301]


class ValidationSeverity(Enum):
    """Severity levels for tag validation issues"""
    CRITICAL = "critical"    # Tag count mismatch, missing tags
    HIGH = "high"           # Tag ID changes, format changes
    MEDIUM = "medium"       # Positioning concerns
    LOW = "low"            # Minor issues


@dataclass
class TagInfo:
    """Information about a single tag"""
    tag_type: TagType
    tag_id: Optional[str]  # The numeric ID or metadata content
    position: int          # Character position in text
    full_text: str        # Complete tag text (e.g., "<123>", "</123>", "<123/>")
    inner_text: Optional[str] = None  # Text between opening and closing tags


@dataclass
class TagValidationResult:
    """Result of tag validation"""
    is_valid: bool
    severity: Optional[ValidationSeverity]
    issues: List[str]
    source_tag_count: int
    target_tag_count: int
    missing_tags: List[str]
    extra_tags: List[str]
    changed_tags: List[Dict]


class TagHandler:
    """Comprehensive tag extraction, validation, and preservation handler"""

    def __init__(self):
        """Initialize tag handler with pattern definitions"""
        self.patterns = {
            TagType.SELF_CLOSING: r'<(\d+)/>',
            TagType.OPENING: r'<(\d+)>',
            TagType.CLOSING: r'</(\d+)>',
            TagType.METADATA: r'\[([^\]]+)\]'
        }

    def extract_tags(self, text: str) -> List[TagInfo]:
        """
        Extract all tags from text with position information

        Args:
            text: Source or target text

        Returns:
            List of TagInfo objects
        """
        tags = []

        for tag_type, pattern in self.patterns.items():
            for match in re.finditer(pattern, text):
                tag_info = TagInfo(
                    tag_type=tag_type,
                    tag_id=match.group(1),
                    position=match.start(),
                    full_text=match.group(0)
                )
                tags.append(tag_info)

        # Sort by position
        tags.sort(key=lambda x: x.position)

        return tags

    def count_tags_by_type(self, tags: List[TagInfo]) -> Dict[TagType, int]:
        """Count tags by type"""
        counts = {tag_type: 0 for tag_type in TagType}
        for tag in tags:
            counts[tag.tag_type] += 1
        return counts

    def extract_paired_tags(self, text: str) -> List[Dict]:
        """
        Extract paired tags with their content

        Returns:
            List of dicts with opening_tag, closing_tag, content, positions
        """
        paired_tags = []

        # Find all paired patterns: <123>content</123>
        paired_pattern = r'<(\d+)>(.*?)</\1>'

        for match in re.finditer(paired_pattern, text, re.DOTALL):
            paired_tags.append({
                'tag_id': match.group(1),
                'opening_tag': f'<{match.group(1)}>',
                'closing_tag': f'</{match.group(1)}>',
                'content': match.group(2),
                'full_match': match.group(0),
                'start_pos': match.start(),
                'end_pos': match.end()
            })

        return paired_tags

    def validate_tags(self, source_text: str, target_text: str) -> TagValidationResult:
        """
        Comprehensive tag validation between source and target

        Args:
            source_text: Original text with tags
            target_text: Translated text with tags

        Returns:
            TagValidationResult with detailed validation information
        """
        source_tags = self.extract_tags(source_text)
        target_tags = self.extract_tags(target_text)

        source_counts = self.count_tags_by_type(source_tags)
        target_counts = self.count_tags_by_type(target_tags)

        issues = []
        severity = None
        missing_tags = []
        extra_tags = []
        changed_tags = []

        # Get tag IDs
        source_tag_ids = {tag.full_text for tag in source_tags}
        target_tag_ids = {tag.full_text for tag in target_tags}

        # Check for missing tags
        missing = source_tag_ids - target_tag_ids
        if missing:
            missing_tags = list(missing)
            issues.append(f"Missing tags in target: {missing_tags}")
            severity = ValidationSeverity.CRITICAL

        # Check for extra tags
        extra = target_tag_ids - source_tag_ids
        if extra:
            extra_tags = list(extra)
            issues.append(f"Extra tags in target: {extra_tags}")
            if not severity:
                severity = ValidationSeverity.CRITICAL

        # Check tag counts by type
        for tag_type in TagType:
            if source_counts[tag_type] != target_counts[tag_type]:
                issues.append(
                    f"{tag_type.value} count mismatch: "
                    f"source={source_counts[tag_type]}, target={target_counts[tag_type]}"
                )
                if not severity:
                    severity = ValidationSeverity.CRITICAL

        # Validate paired tags structure
        source_paired = self.extract_paired_tags(source_text)
        target_paired = self.extract_paired_tags(target_text)

        if len(source_paired) != len(target_paired):
            issues.append(
                f"Paired tag count mismatch: source={len(source_paired)}, target={len(target_paired)}"
            )
            if not severity:
                severity = ValidationSeverity.HIGH

        # Check that paired tags have same IDs
        source_paired_ids = {p['tag_id'] for p in source_paired}
        target_paired_ids = {p['tag_id'] for p in target_paired}

        if source_paired_ids != target_paired_ids:
            changed_tags.append({
                'type': 'paired_tags',
                'source_ids': list(source_paired_ids),
                'target_ids': list(target_paired_ids)
            })
            issues.append(f"Paired tag IDs changed: {source_paired_ids} → {target_paired_ids}")
            if not severity:
                severity = ValidationSeverity.HIGH

        # Determine overall validity
        is_valid = len(issues) == 0

        return TagValidationResult(
            is_valid=is_valid,
            severity=severity,
            issues=issues,
            source_tag_count=len(source_tags),
            target_tag_count=len(target_tags),
            missing_tags=missing_tags,
            extra_tags=extra_tags,
            changed_tags=changed_tags
        )

    def create_tag_preservation_prompt_section(self) -> str:
        """
        Create prompt section for tag preservation instructions

        Returns:
            Formatted prompt text for inclusion in translation prompts
        """
        return """
🏷️ TAG PRESERVATION RULES (CRITICAL - MUST FOLLOW):

Your input contains XML-style tags and metadata brackets that MUST be preserved exactly.

**Tag Types You Will Encounter:**
1. Self-closing tags: `<123/>` - Copy exactly as-is
2. Opening tags: `<123>` - Preserve the exact number
3. Closing tags: `</123>` - Must match opening tag number
4. Paired tags: `<123>text</123>` - Translate ONLY the text, keep tags unchanged
5. Metadata brackets: `[IN_ECN_301]` - Copy exactly, DO NOT translate

**CRITICAL RULES:**
✅ DO: Preserve ALL tags with exact same numbers/IDs
✅ DO: Maintain tag positions relative to translated text
✅ DO: Translate text BETWEEN or AROUND tags only
✅ DO: Keep nested tag structures intact
✅ DO: Preserve spacing inside tags (e.g., `<129> 부 록</129>` → `<129> Appendix</129>`)

❌ DON'T: Change tag numbers (e.g., <123> to <124>)
❌ DON'T: Remove or add tags
❌ DON'T: Change tag format (self-closing vs paired)
❌ DON'T: Translate metadata in brackets

**Examples:**

Example 1 - Superscript notation:
Source: BMI ≥ 30 kg/m<660>2</660> 인 자
Target: Subjects with BMI ≥ 30 kg/m<660>2</660>
✅ Tag <660>2</660> preserved for superscript formatting

Example 2 - Nested tags:
Source: <182><180>시험제</180></182><185>목</185>
Target: <182><180>Study Title</180></182><185>Objectives</185>
✅ All tags preserved, only Korean text translated

Example 3 - Mixed tags:
Source: <109/><112>/</112><117/>
Target: <109/><112>/</112><117/>
✅ Self-closing and paired tags both preserved exactly

Example 4 - Text with tags:
Source: <129> 부 록</129>
Target: <129> Appendix</129>
✅ Space after opening tag preserved

Example 5 - Metadata:
Source: [IN_ECN_301] Protocol ver.1.0_2024.09.30
Target: [IN_ECN_301] Protocol ver.1.0_2024.09.30
✅ Metadata bracket unchanged

⚠️ TAG VALIDATION: Your output will be automatically validated for tag preservation. Any tag errors will require re-translation.
"""

    def create_enhanced_prompt_with_tags(self,
                                        base_prompt: str,
                                        insert_after: str = "## Source Text") -> str:
        """
        Insert tag preservation instructions into existing prompt

        Args:
            base_prompt: Existing translation prompt
            insert_after: Text marker to insert after

        Returns:
            Enhanced prompt with tag instructions
        """
        tag_section = self.create_tag_preservation_prompt_section()

        # Insert tag section after specified marker
        if insert_after in base_prompt:
            parts = base_prompt.split(insert_after, 1)
            enhanced = parts[0] + tag_section + "\n" + insert_after + parts[1]
        else:
            # If marker not found, prepend to prompt
            enhanced = tag_section + "\n" + base_prompt

        return enhanced

    def validate_with_llm(self,
                         source_text: str,
                         target_text: str,
                         openai_client: openai.OpenAI) -> Dict:
        """
        Use LLM to validate semantic positioning of tags

        This checks if tags are in reasonable positions given the translation,
        particularly for formatting tags like superscripts.

        Args:
            source_text: Original text with tags
            target_text: Translated text with tags
            openai_client: Initialized OpenAI client

        Returns:
            Dict with validation results
        """
        validation_prompt = f"""You are a tag positioning validator for CAT tool translations.

Source text: {source_text}
Target text: {target_text}

Analyze whether the tags in the target are positioned correctly given the translation.

Focus on:
1. Formatting tags (like superscripts) should be around the same semantic elements
2. Document structure tags should maintain logical flow
3. Tags shouldn't break words or create nonsensical formatting

Respond with JSON:
{{
    "positioning_valid": true/false,
    "issues": ["list of any positioning problems"],
    "severity": "critical/high/medium/low/none",
    "recommendation": "specific fix if needed"
}}"""

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": validation_prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )

            import json
            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            return {
                "positioning_valid": None,
                "issues": [f"LLM validation failed: {str(e)}"],
                "severity": "none",
                "recommendation": "Manual review recommended"
            }

    def has_tags(self, text: str) -> bool:
        """Check if text contains any tags"""
        return bool(re.search(r'<\d+[/>]|</\d+>|\[[^\]]+\]', text))

    def get_tag_statistics(self, text: str) -> Dict:
        """Get comprehensive tag statistics for reporting"""
        tags = self.extract_tags(text)
        counts = self.count_tags_by_type(tags)
        paired = self.extract_paired_tags(text)

        return {
            'total_tags': len(tags),
            'has_tags': len(tags) > 0,
            'self_closing_count': counts[TagType.SELF_CLOSING],
            'opening_count': counts[TagType.OPENING],
            'closing_count': counts[TagType.CLOSING],
            'metadata_count': counts[TagType.METADATA],
            'paired_structures': len(paired),
            'tag_details': [
                {
                    'type': tag.tag_type.value,
                    'id': tag.tag_id,
                    'position': tag.position,
                    'text': tag.full_text
                }
                for tag in tags
            ]
        }


def demo_tag_handler():
    """Demonstrate tag handler functionality with test cases"""
    print("=" * 80)
    print("TAG HANDLER DEMONSTRATION")
    print("=" * 80)

    handler = TagHandler()

    # Test cases from actual data
    test_cases = [
        {
            "name": "Superscript notation",
            "source": "BMI ≥ 30 kg/m<660>2</660> 인 자",
            "target_good": "Subjects with BMI ≥ 30 kg/m<660>2</660>",
            "target_bad": "Subjects with BMI ≥ 30 kg/m2"
        },
        {
            "name": "Nested tags",
            "source": "<182><180>시험제</180></182><185>목</185>",
            "target_good": "<182><180>Study Title</180></182><185>Objectives</185>",
            "target_bad": "<182>Study Title and Objectives</182>"
        },
        {
            "name": "Mixed tags",
            "source": "<109/><112>/</112><117/>",
            "target_good": "<109/><112>/</112><117/>",
            "target_bad": "<109/> / <117/>"
        },
        {
            "name": "Text with tags",
            "source": "<129> 부 록</129>",
            "target_good": "<129> Appendix</129>",
            "target_bad": "<129>Appendix</129>"
        }
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"\n{'=' * 80}")
        print(f"Test Case {i}: {test['name']}")
        print(f"{'=' * 80}")

        print(f"\nSource: {test['source']}")
        source_stats = handler.get_tag_statistics(test['source'])
        print(f"Source tags: {source_stats['total_tags']}")

        # Validate good target
        print(f"\n✅ GOOD Target: {test['target_good']}")
        validation_good = handler.validate_tags(test['source'], test['target_good'])
        print(f"   Valid: {validation_good.is_valid}")
        if not validation_good.is_valid:
            print(f"   Issues: {validation_good.issues}")

        # Validate bad target
        print(f"\n❌ BAD Target: {test['target_bad']}")
        validation_bad = handler.validate_tags(test['source'], test['target_bad'])
        print(f"   Valid: {validation_bad.is_valid}")
        if not validation_bad.is_valid:
            print(f"   Severity: {validation_bad.severity.value if validation_bad.severity else 'N/A'}")
            print(f"   Issues: {validation_bad.issues}")

    # Demonstrate prompt generation
    print(f"\n{'=' * 80}")
    print("PROMPT SECTION GENERATION")
    print(f"{'=' * 80}")
    print(handler.create_tag_preservation_prompt_section())


if __name__ == "__main__":
    demo_tag_handler()
