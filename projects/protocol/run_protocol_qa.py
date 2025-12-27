#!/usr/bin/env python3
"""
Protocol QA System - Master Orchestrator
Runs 2-step process:
1. Processor 1: Extract EN-KO rules from reference documents
2. Processor 2: Validate merged translations using extracted rules
"""

import sys
import os
import logging
import argparse
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

sys.path.insert(0, os.path.dirname(__file__))

from protocol_qa_rule_extractor import ProtocolQARuleExtractor
from protocol_qa_validator import ProtocolQAValidator


class ProtocolQASystem:
    """Master orchestrator for 2-step QA process"""

    def __init__(self):
        """Initialize"""
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

    def setup_logging(self):
        """Setup logging"""
        logging.basicConfig(level=logging.INFO)

    def run_full_process(self, test_mode: bool = False, test_segments: int = 50):
        """
        Run full 2-step QA process

        Args:
            test_mode: If True, validate only subset of segments
            test_segments: Number of segments for test mode
        """
        self.logger.info("")
        self.logger.info("=" * 100)
        self.logger.info("🚀 PROTOCOL QA SYSTEM - 2-STEP PROCESS")
        self.logger.info("=" * 100)
        self.logger.info("")

        try:
            # PROCESSOR 1: Extract rules from reference documents
            self.logger.info("┌" + "─" * 98 + "┐")
            self.logger.info("│ PROCESSOR 1: Extract EN-KO Rules from Reference Documents" + " " * 40 + "│")
            self.logger.info("└" + "─" * 98 + "┘")

            extractor = ProtocolQARuleExtractor()
            rules_file = extractor.run()

            # PROCESSOR 2: Validate translations using extracted rules
            self.logger.info("")
            self.logger.info("┌" + "─" * 98 + "┐")
            self.logger.info("│ PROCESSOR 2: Validate Translations Using Extracted Rules" + " " * 41 + "│")
            self.logger.info("└" + "─" * 98 + "┘")

            validator = ProtocolQAValidator(rules_file)
            merged_file = "/Users/won.suh/Downloads/83-0060-0002_Protocol_FINAL_MERGED_20251212_151821.xlsx"

            report_file = validator.run(merged_file, test_mode=test_mode, test_segments=test_segments)

            self.logger.info("")
            self.logger.info("=" * 100)
            self.logger.info("✅ PROTOCOL QA SYSTEM COMPLETE")
            self.logger.info("=" * 100)
            self.logger.info("")
            self.logger.info(f"📖 Rules file: {rules_file}")
            self.logger.info(f"📋 Validation report: {report_file}")
            self.logger.info("")

            return rules_file, report_file

        except Exception as e:
            self.logger.error(f"❌ QA process failed: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Protocol QA System - 2-Step Validation")
    parser.add_argument(
        "--mode",
        choices=["test", "production"],
        default="test",
        help="Run mode: test (50 segments) or production (all segments)"
    )
    parser.add_argument(
        "--segments",
        type=int,
        default=50,
        help="Number of segments for test mode (default: 50)"
    )

    args = parser.parse_args()

    qa_system = ProtocolQASystem()
    qa_system.run_full_process(
        test_mode=(args.mode == "test"),
        test_segments=args.segments
    )


if __name__ == '__main__':
    main()
