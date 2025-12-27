#!/usr/bin/env python3
"""
Reference Document Loader
Extracts and aligns EN-KO paragraphs from Word documents
For consistency rule extraction from professional reference translations
"""

import logging
import os
import re
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
import pandas as pd

try:
    from docx import Document
    from docx.text.paragraph import Paragraph
    from docx.table import Table
except ImportError:
    raise ImportError("python-docx required: pip install python-docx")


@dataclass
class AlignedSegment:
    """Represents an aligned EN-KO segment pair"""
    segment_num: int
    en_text: str
    ko_text: str
    section_header: str
    alignment_confidence: float  # 0.0-1.0
    source: str  # "paragraph", "table", "list"
    en_paragraph_index: int
    ko_paragraph_index: int


class ReferenceDocLoader:
    """Load and align EN-KO reference documents"""

    def __init__(self, en_doc_path: str, ko_doc_path: str):
        """
        Initialize reference document loader

        Args:
            en_doc_path: Path to English reference document (.docx)
            ko_doc_path: Path to Korean reference document (.docx)
        """
        self.setup_logging()
        self.en_doc_path = en_doc_path
        self.ko_doc_path = ko_doc_path
        self.aligned_segments = []
        self.en_doc = None
        self.ko_doc = None
        self.en_paragraphs = []
        self.ko_paragraphs = []
        self.current_section = ""

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_documents(self):
        """Load both Word documents"""
        self.logger.info("📂 Loading reference documents...")

        if not os.path.exists(self.en_doc_path):
            raise FileNotFoundError(f"English doc not found: {self.en_doc_path}")
        if not os.path.exists(self.ko_doc_path):
            raise FileNotFoundError(f"Korean doc not found: {self.ko_doc_path}")

        try:
            self.en_doc = Document(self.en_doc_path)
            self.logger.info(f"  ✓ English doc loaded: {len(self.en_doc.paragraphs)} paragraphs")

            self.ko_doc = Document(self.ko_doc_path)
            self.logger.info(f"  ✓ Korean doc loaded: {len(self.ko_doc.paragraphs)} paragraphs")
        except Exception as e:
            self.logger.error(f"❌ Error loading documents: {e}")
            raise

    def extract_paragraphs(self):
        """
        Extract paragraphs from both documents
        Filter out empty paragraphs, headers, footers
        """
        self.logger.info("📄 Extracting paragraphs...")

        # Extract English paragraphs
        self.en_paragraphs = self._extract_doc_paragraphs(self.en_doc)
        self.logger.info(f"  English: {len(self.en_paragraphs)} content paragraphs")

        # Extract Korean paragraphs
        self.ko_paragraphs = self._extract_doc_paragraphs(self.ko_doc)
        self.logger.info(f"  Korean: {len(self.ko_paragraphs)} content paragraphs")

    def _extract_doc_paragraphs(self, doc) -> List[Dict]:
        """
        Extract content paragraphs from document

        Returns:
            List of dicts: {text, is_heading, section, index, char_count}
        """
        paragraphs = []
        current_section = ""

        for idx, para in enumerate(doc.paragraphs):
            text = para.text.strip()

            # Skip empty paragraphs
            if not text:
                continue

            # Detect section headers (usually bold, underlined, or specific style)
            is_heading = para.style.name.startswith('Heading')
            if is_heading:
                current_section = text

            # Skip very short fragments (likely page numbers, etc.)
            if len(text) < 20 and not is_heading:
                continue

            paragraphs.append({
                'text': text,
                'is_heading': is_heading,
                'section': current_section,
                'index': idx,
                'char_count': len(text)
            })

        return paragraphs

    def align_paragraphs(self, max_length_ratio: float = 0.3) -> List[AlignedSegment]:
        """
        Align EN and KO paragraphs by position and content similarity

        Args:
            max_length_ratio: Max ratio difference for alignment (0.3 = 30%)

        Returns:
            List of aligned segment pairs
        """
        self.logger.info("🔗 Aligning paragraphs...")

        # Filter out headings for alignment (align separately)
        en_content = [p for p in self.en_paragraphs if not p['is_heading']]
        ko_content = [p for p in self.ko_paragraphs if not p['is_heading']]

        self.logger.info(f"  Aligning {len(en_content)} EN × {len(ko_content)} KO paragraphs...")

        # Use greedy alignment: match by position with length similarity validation
        aligned = []
        segment_num = 1

        min_len = min(len(en_content), len(ko_content))

        for i in range(min_len):
            en_para = en_content[i]
            ko_para = ko_content[i]

            # Calculate alignment confidence based on length similarity
            en_len = en_para['char_count']
            ko_len = ko_para['char_count']

            # Korean typically 60% of English length
            expected_ko_len = en_len * 0.6
            length_ratio = abs(ko_len - expected_ko_len) / expected_ko_len if expected_ko_len > 0 else 1.0

            # Confidence: 1.0 if ratio perfect, decreases with divergence
            confidence = max(0.0, 1.0 - (length_ratio / 0.5))  # 0.5 = 50% divergence threshold
            confidence = min(1.0, confidence)

            # Only include if reasonable confidence
            if confidence > 0.3:  # 30% minimum confidence
                segment = AlignedSegment(
                    segment_num=segment_num,
                    en_text=en_para['text'],
                    ko_text=ko_para['text'],
                    section_header=en_para['section'],
                    alignment_confidence=confidence,
                    source='paragraph',
                    en_paragraph_index=i,
                    ko_paragraph_index=i
                )
                aligned.append(segment)
                segment_num += 1

        self.logger.info(f"  ✅ Aligned {len(aligned)} segment pairs")
        self.aligned_segments = aligned
        return aligned

    def extract_tables(self) -> List[AlignedSegment]:
        """
        Extract and align table content from both documents

        Returns:
            Additional aligned segments from tables
        """
        self.logger.info("📊 Extracting table content...")

        en_tables = self._extract_doc_tables(self.en_doc)
        ko_tables = self._extract_doc_tables(self.ko_doc)

        self.logger.info(f"  Found {len(en_tables)} EN tables, {len(ko_tables)} KO tables")

        # Simple alignment: match by position
        table_segments = []
        segment_num = len(self.aligned_segments) + 1

        for i, (en_table, ko_table) in enumerate(zip(en_tables, ko_tables)):
            segment = AlignedSegment(
                segment_num=segment_num,
                en_text=en_table,
                ko_text=ko_table,
                section_header=self.current_section,
                alignment_confidence=0.7,  # Lower confidence for tables
                source='table',
                en_paragraph_index=-1,
                ko_paragraph_index=-1
            )
            table_segments.append(segment)
            segment_num += 1

        self.aligned_segments.extend(table_segments)
        return table_segments

    def _extract_doc_tables(self, doc) -> List[str]:
        """Extract table content as text"""
        tables = []
        for table in doc.tables:
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                row_text = " | ".join(cells)
                if row_text.strip():
                    rows.append(row_text)
            if rows:
                tables.append("\n".join(rows))
        return tables

    def save_aligned_pairs(self, output_path: str):
        """
        Save aligned segments to Excel

        Args:
            output_path: Path to output Excel file
        """
        self.logger.info(f"💾 Saving aligned pairs to: {output_path}")

        # Convert to DataFrame
        data = [asdict(seg) for seg in self.aligned_segments]
        df = pd.DataFrame(data)

        # Reorder columns for readability
        column_order = [
            'segment_num',
            'en_text',
            'ko_text',
            'section_header',
            'alignment_confidence',
            'source',
            'en_paragraph_index',
            'ko_paragraph_index'
        ]
        df = df[column_order]

        # Save to Excel
        df.to_excel(output_path, index=False, engine='openpyxl')

        self.logger.info(f"  ✓ Saved {len(df)} aligned pairs")
        self.logger.info(f"  Average confidence: {df['alignment_confidence'].mean():.2%}")

        return output_path

    def run(self) -> str:
        """
        Execute full reference document alignment workflow

        Returns:
            Path to output Excel file with aligned pairs
        """
        self.logger.info("=" * 100)
        self.logger.info("🚀 REFERENCE DOCUMENT LOADER & ALIGNMENT")
        self.logger.info("=" * 100)

        # Step 1: Load documents
        self.load_documents()

        # Step 2: Extract paragraphs
        self.extract_paragraphs()

        # Step 3: Align paragraphs
        self.align_paragraphs()

        # Step 4: Extract tables (optional)
        self.extract_tables()

        # Step 5: Save aligned pairs
        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"/Users/won.suh/Project/translate-ai/phase2/data/reference_pairs_protocol_v1.2_{timestamp}.xlsx"

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        self.save_aligned_pairs(output_file)

        self.logger.info("")
        self.logger.info("=" * 100)
        self.logger.info("✅ REFERENCE DOCUMENT ALIGNMENT COMPLETE")
        self.logger.info("=" * 100)
        self.logger.info(f"\n📁 Output: {output_file}\n")

        return output_file


def main():
    """Main execution"""
    en_doc = "/Users/won.suh/Downloads/pair/83-0060-02_Protocol 1.2-18Jul2025_EN.docx"
    ko_doc = "/Users/won.suh/Downloads/pair/83-0060-02_Protocol 1.2-18Jul2025_Korean_final.docx"

    loader = ReferenceDocLoader(en_doc, ko_doc)
    output_file = loader.run()
    print(f"\n✅ Successfully generated: {output_file}")


if __name__ == '__main__':
    main()
