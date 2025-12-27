"""
Analyze Protocol TMX files to extract EN-KO translation patterns
"""
import xml.etree.ElementTree as ET
from collections import defaultdict
import re

def parse_tmx(file_path):
    """Parse TMX file and extract EN-KO translation pairs"""
    # Register XML namespace
    ET.register_namespace('xml', 'http://www.w3.org/XML/1998/namespace')

    tree = ET.parse(file_path)
    root = tree.getroot()

    pairs = []
    for tu in root.findall('.//tu'):
        # Find tuv elements without namespace prefix
        en_seg = None
        ko_seg = None

        for tuv in tu.findall('.//tuv'):
            # Get lang attribute (try both with and without namespace)
            lang = tuv.get('{http://www.w3.org/XML/1998/namespace}lang')
            if not lang:
                lang = tuv.get('lang')

            if lang == 'en-US':
                seg = tuv.find('seg')
                if seg is not None:
                    en_seg = seg
            elif lang == 'ko-KR':
                seg = tuv.find('seg')
                if seg is not None:
                    ko_seg = seg

        if en_seg is not None and ko_seg is not None:
            en_text = ''.join(en_seg.itertext()).strip()
            ko_text = ''.join(ko_seg.itertext()).strip()

            # Remove empty pairs or pairs with only tags
            if en_text and ko_text and en_text != ko_text:
                pairs.append((en_text, ko_text))

    return pairs

def analyze_terminology_patterns(pairs):
    """Extract consistent terminology translations"""
    term_map = defaultdict(set)

    # Key clinical protocol terms to track
    key_terms = [
        "protocol", "study", "participant", "investigator", "sponsor",
        "adverse event", "safety", "efficacy", "randomization", "treatment",
        "consent", "screening", "eligibility", "criteria", "arm",
        "phase", "multicenter", "open-label", "blind", "placebo",
        "primary outcome", "secondary outcome", "endpoint", "visit",
        "dose", "administration", "withdrawal", "exclusion", "inclusion"
    ]

    for en, ko in pairs:
        en_lower = en.lower()
        for term in key_terms:
            if term in en_lower:
                term_map[term].add(f"EN: {en} → KO: {ko}")

    return term_map

def analyze_modal_verbs(pairs):
    """Extract how modal verbs are translated"""
    modals = ["will", "shall", "must", "should", "may", "can"]
    modal_patterns = defaultdict(list)

    for en, ko in pairs:
        en_lower = en.lower()
        for modal in modals:
            if f" {modal} " in f" {en_lower} ":
                modal_patterns[modal].append((en, ko))

    return modal_patterns

def analyze_passive_voice(pairs):
    """Extract passive voice translation patterns"""
    passive_patterns = []

    # Common passive voice indicators
    passive_indicators = [" will be ", " is ", " are ", " was ", " were ", " been "]

    for en, ko in pairs:
        en_lower = en.lower()
        if any(ind in en_lower for ind in passive_indicators):
            if any(past_participle in en_lower for past_participle in [
                " conducted", " performed", " assessed", " evaluated", " collected",
                " administered", " monitored", " reviewed", " recorded", " measured"
            ]):
                passive_patterns.append((en, ko))

    return passive_patterns

def analyze_regulatory_phrases(pairs):
    """Extract regulatory compliance phrases"""
    regulatory_patterns = []

    regulatory_keywords = [
        "good clinical practice", "gcp", "ich", "declaration of helsinki",
        "ethics committee", "irb", "institutional review board",
        "confidential", "informed consent", "sign", "approval",
        "compliance", "regulation", "guideline"
    ]

    for en, ko in pairs:
        en_lower = en.lower()
        if any(keyword in en_lower for keyword in regulatory_keywords):
            regulatory_patterns.append((en, ko))

    return regulatory_patterns

def main():
    # Analyze both TMX files
    tmx_files = [
        "/Users/won.suh/Downloads/linguistic asset/AVK_83-0060-002_Protocol v1.2_EN-KO.tmx",
        "/Users/won.suh/Downloads/linguistic asset/Avance Clinical CRO_ENUS-KOKR.tmx"
    ]

    all_pairs = []
    for tmx_file in tmx_files:
        try:
            pairs = parse_tmx(tmx_file)
            all_pairs.extend(pairs)
            print(f"✓ Parsed {len(pairs)} pairs from {tmx_file.split('/')[-1]}")
        except Exception as e:
            print(f"✗ Error parsing {tmx_file}: {e}")

    print(f"\n{'='*80}")
    print(f"TOTAL TRANSLATION PAIRS: {len(all_pairs)}")
    print(f"{'='*80}\n")

    # 1. Terminology patterns
    print("="*80)
    print("1. KEY TERMINOLOGY PATTERNS")
    print("="*80)
    term_map = analyze_terminology_patterns(all_pairs)
    for term, examples in sorted(term_map.items()):
        if examples:
            print(f"\n### {term.upper()}:")
            for ex in list(examples)[:3]:  # Show first 3 examples
                print(f"  {ex}")

    # 2. Modal verb patterns
    print("\n" + "="*80)
    print("2. MODAL VERB PATTERNS")
    print("="*80)
    modal_patterns = analyze_modal_verbs(all_pairs)
    for modal, examples in sorted(modal_patterns.items()):
        if examples:
            print(f"\n### {modal.upper()}:")
            for en, ko in examples[:3]:  # Show first 3
                print(f"  EN: {en}")
                print(f"  KO: {ko}")
                print()

    # 3. Passive voice patterns
    print("\n" + "="*80)
    print("3. PASSIVE VOICE PATTERNS")
    print("="*80)
    for en, ko in analyze_passive_voice(all_pairs)[:10]:  # Show first 10
        print(f"EN: {en}")
        print(f"KO: {ko}")
        print()

    # 4. Regulatory phrases
    print("\n" + "="*80)
    print("4. REGULATORY COMPLIANCE PHRASES")
    print("="*80)
    for en, ko in analyze_regulatory_phrases(all_pairs)[:15]:  # Show first 15
        print(f"EN: {en}")
        print(f"KO: {ko}")
        print()

    # 5. Show some complete high-quality pairs for context
    print("\n" + "="*80)
    print("5. SAMPLE HIGH-QUALITY TRANSLATION PAIRS")
    print("="*80)
    for en, ko in all_pairs[50:80]:  # Show middle section
        if 20 < len(en) < 200:  # Filter for meaningful length
            print(f"EN: {en}")
            print(f"KO: {ko}")
            print()

if __name__ == "__main__":
    main()
