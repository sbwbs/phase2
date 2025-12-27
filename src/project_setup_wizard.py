#!/usr/bin/env python3
"""
Interactive CLI Wizard for Setting Up New Translation Projects

Run: python src/project_setup_wizard.py

Guides you through:
1. Project configuration
2. Data file validation
3. Environment setup
4. Qdrant collection creation
5. Pipeline script generation
"""

import os
import sys
import re
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.END}\n")


def print_step(step: int, total: int, text: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}[Step {step}/{total}] {text}{Colors.END}")
    print(f"{Colors.CYAN}{'-'*50}{Colors.END}")


def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_info(text: str):
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")


def prompt(question: str, default: str = None) -> str:
    """Prompt user for input with optional default."""
    if default:
        user_input = input(f"{Colors.BOLD}{question}{Colors.END} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        return input(f"{Colors.BOLD}{question}{Colors.END}: ").strip()


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt for yes/no answer."""
    default_str = "Y/n" if default else "y/N"
    answer = input(f"{Colors.BOLD}{question}{Colors.END} [{default_str}]: ").strip().lower()
    if not answer:
        return default
    return answer in ('y', 'yes')


def prompt_choice(question: str, choices: List[str], default: int = 0) -> int:
    """Prompt user to choose from a list."""
    print(f"\n{Colors.BOLD}{question}{Colors.END}")
    for i, choice in enumerate(choices):
        marker = "→" if i == default else " "
        print(f"  {marker} [{i+1}] {choice}")

    while True:
        answer = input(f"\nEnter choice [1-{len(choices)}] (default: {default+1}): ").strip()
        if not answer:
            return default
        try:
            idx = int(answer) - 1
            if 0 <= idx < len(choices):
                return idx
        except ValueError:
            pass
        print_error(f"Please enter a number between 1 and {len(choices)}")


def sanitize_project_id(name: str) -> str:
    """Sanitize project ID for use as collection name prefix."""
    name = name.lower()
    name = re.sub(r'[^a-z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name)
    name = name.strip('_')
    return name or "default"


@dataclass
class ProjectConfig:
    """Project configuration data."""
    project_id: str = ""
    project_name: str = ""
    direction: str = "ko_en"  # or "en_ko"

    # File paths
    source_file: str = ""
    glossary_files: List[Tuple[str, int]] = field(default_factory=list)
    tmx_file: str = ""
    output_dir: str = ""

    # Qdrant settings
    use_qdrant: bool = False
    qdrant_url: str = ""
    qdrant_api_key: str = ""

    # Processing settings
    model_name: str = "Owl"
    batch_size: int = 50


class ProjectSetupWizard:
    """Interactive wizard for project setup."""

    def __init__(self):
        self.config = ProjectConfig()
        self.base_dir = Path(__file__).parent.parent
        self.data_dir = self.base_dir / "data"
        self.src_dir = self.base_dir / "src"
        self.total_steps = 7

    def run(self):
        """Run the wizard."""
        print_header("Translation Project Setup Wizard")

        print("This wizard will guide you through setting up a new")
        print("clinical protocol translation project.\n")
        print(f"Base directory: {self.base_dir}")
        print(f"Data directory: {self.data_dir}")

        if not prompt_yes_no("\nReady to begin?", True):
            print("\nSetup cancelled.")
            return

        try:
            self.step1_project_info()
            self.step2_translation_direction()
            self.step3_source_file()
            self.step4_glossary_files()
            self.step5_tmx_file()
            self.step6_qdrant_setup()
            self.step7_review_and_create()
        except KeyboardInterrupt:
            print("\n\nSetup cancelled by user.")
            return

    def step1_project_info(self):
        """Collect project identification."""
        print_step(1, self.total_steps, "Project Information")

        print("The Project ID is used to:")
        print("  • Name your pipeline script")
        print("  • Create isolated Qdrant collections")
        print("  • Organize output files\n")

        # Get project name
        project_name = prompt("Project name (e.g., 'GreenCross Protocol v5')")
        self.config.project_name = project_name

        # Suggest sanitized ID
        suggested_id = sanitize_project_id(project_name)
        self.config.project_id = prompt("Project ID (lowercase, no spaces)", suggested_id)
        self.config.project_id = sanitize_project_id(self.config.project_id)

        print_success(f"Project ID: {self.config.project_id}")
        print_info(f"Collections will be: {self.config.project_id}_glossary, {self.config.project_id}_tm_ko_en, ...")

    def step2_translation_direction(self):
        """Select translation direction."""
        print_step(2, self.total_steps, "Translation Direction")

        choices = [
            "Korean → English (KO-EN) - Clinical protocols to English",
            "English → Korean (EN-KO) - English protocols to Korean"
        ]

        choice = prompt_choice("Select translation direction:", choices, default=0)
        self.config.direction = "ko_en" if choice == 0 else "en_ko"

        print_success(f"Direction: {self.config.direction.upper()}")

    def step3_source_file(self):
        """Configure source document."""
        print_step(3, self.total_steps, "Source Document")

        print("Expected format: Excel (.xlsx) with columns:")
        print("  • Segment ID (required)")
        print("  • Source segment (required)")
        print("  • Target segment (optional)")
        print("  • Segment status (optional)\n")

        while True:
            source_file = prompt("Path to source Excel file")
            source_file = os.path.expanduser(source_file)

            if os.path.exists(source_file):
                self.config.source_file = source_file

                # Try to count segments
                try:
                    import pandas as pd
                    df = pd.read_excel(source_file)
                    print_success(f"Found: {len(df)} segments")
                    print_info(f"Columns: {', '.join(df.columns[:5])}...")
                except Exception as e:
                    print_warning(f"Could not read file: {e}")
                break
            else:
                print_error(f"File not found: {source_file}")
                if not prompt_yes_no("Try again?", True):
                    self.config.source_file = source_file  # Save anyway
                    print_warning("File will need to exist before running pipeline")
                    break

    def step4_glossary_files(self):
        """Configure glossary files."""
        print_step(4, self.total_steps, "Glossary Files")

        print("Glossary format: Excel with columns:")
        print("  • Korean (required)")
        print("  • English (required)")
        print("  • Priority: 1=mandatory, 2=preferred (optional)\n")

        glossary_files = []

        # Check for existing glossaries in data dir
        existing = list(self.data_dir.glob("*terms*.xlsx")) + list(self.data_dir.glob("*glossary*.xlsx"))
        if existing:
            print(f"Found {len(existing)} glossary file(s) in data/:")
            for f in existing[:5]:
                print(f"  • {f.name}")
            print()

        while True:
            glossary_path = prompt("Path to glossary file (or 'done' to finish)")

            if glossary_path.lower() == 'done':
                break

            glossary_path = os.path.expanduser(glossary_path)

            # Check if it's just a filename (look in data dir)
            if not os.path.exists(glossary_path):
                data_path = self.data_dir / glossary_path
                if data_path.exists():
                    glossary_path = str(data_path)

            if os.path.exists(glossary_path):
                priority = prompt_choice(
                    f"Priority for {os.path.basename(glossary_path)}:",
                    ["Priority 1 (mandatory terms)", "Priority 2 (preferred terms)"],
                    default=0
                ) + 1

                glossary_files.append((glossary_path, priority))

                try:
                    import pandas as pd
                    df = pd.read_excel(glossary_path)
                    print_success(f"Added: {len(df)} terms (Priority {priority})")
                except:
                    print_success(f"Added: {os.path.basename(glossary_path)} (Priority {priority})")
            else:
                print_error(f"File not found: {glossary_path}")

            if not prompt_yes_no("Add another glossary?", len(glossary_files) == 0):
                break

        self.config.glossary_files = glossary_files

        if not glossary_files:
            print_warning("No glossary files added. Pipeline will run without glossary.")
        else:
            print_success(f"Total: {len(glossary_files)} glossary file(s)")

    def step5_tmx_file(self):
        """Configure TMX translation memory."""
        print_step(5, self.total_steps, "Translation Memory (TMX)")

        print("TMX provides reference translations for similar segments.")
        print("Format: TMX 1.4 XML file\n")

        # Check for existing TMX
        existing_tmx = list(self.data_dir.glob("*.tmx"))
        if existing_tmx:
            print(f"Found {len(existing_tmx)} TMX file(s) in data/:")
            for f in existing_tmx[:3]:
                print(f"  • {f.name}")
            print()

        if prompt_yes_no("Do you have a TMX file?", bool(existing_tmx)):
            tmx_path = prompt("Path to TMX file")
            tmx_path = os.path.expanduser(tmx_path)

            # Check data dir
            if not os.path.exists(tmx_path):
                data_path = self.data_dir / tmx_path
                if data_path.exists():
                    tmx_path = str(data_path)

            if os.path.exists(tmx_path):
                self.config.tmx_file = tmx_path
                print_success(f"TMX: {os.path.basename(tmx_path)}")
            else:
                print_warning(f"File not found: {tmx_path}")
                self.config.tmx_file = tmx_path
        else:
            print_info("Skipping TMX. Pipeline will run without translation memory.")

    def step6_qdrant_setup(self):
        """Configure Qdrant vector search."""
        print_step(6, self.total_steps, "Qdrant Vector Search (Tier 2)")

        print("Qdrant enables semantic search for glossary and TM.")
        print("Benefits:")
        print("  • Find similar terms even with different wording")
        print("  • Hybrid search (semantic + exact matching)")
        print("  • Project-isolated collections\n")

        # Check existing .env
        env_file = self.base_dir / ".env"
        has_qdrant = False
        if env_file.exists():
            with open(env_file) as f:
                content = f.read()
                has_qdrant = "QDRANT_URL" in content and "QDRANT_API_KEY" in content

        if has_qdrant:
            print_info("Qdrant credentials found in .env")
            self.config.use_qdrant = prompt_yes_no("Enable Qdrant for this project?", True)
        else:
            print_warning("No Qdrant credentials in .env")
            if prompt_yes_no("Do you have Qdrant Cloud credentials?", False):
                self.config.qdrant_url = prompt("Qdrant URL (https://xxx.cloud.qdrant.io:6333)")
                self.config.qdrant_api_key = prompt("Qdrant API Key")
                self.config.use_qdrant = True

                # Offer to save to .env
                if prompt_yes_no("Save credentials to .env?", True):
                    self._update_env_file()
            else:
                print_info("Qdrant disabled. Using keyword-based search only.")
                self.config.use_qdrant = False

        if self.config.use_qdrant:
            print_success(f"Qdrant enabled")
            print_info(f"Collections: {self.config.project_id}_glossary, {self.config.project_id}_tm_{self.config.direction}")

    def step7_review_and_create(self):
        """Review configuration and create files."""
        print_step(7, self.total_steps, "Review & Create")

        print(f"{Colors.BOLD}Project Configuration:{Colors.END}")
        print(f"  Project ID:    {self.config.project_id}")
        print(f"  Direction:     {self.config.direction.upper()}")
        print(f"  Source file:   {self.config.source_file or '(not set)'}")
        print(f"  Glossaries:    {len(self.config.glossary_files)} file(s)")
        print(f"  TMX file:      {self.config.tmx_file or '(none)'}")
        print(f"  Qdrant:        {'Enabled' if self.config.use_qdrant else 'Disabled'}")
        print(f"  Model:         {self.config.model_name}")
        print(f"  Batch size:    {self.config.batch_size}")

        print(f"\n{Colors.BOLD}Files to create:{Colors.END}")
        pipeline_file = f"{self.config.project_id}_translation_pipeline.py"
        print(f"  • src/{pipeline_file}")

        if not prompt_yes_no("\nCreate project files?", True):
            print("\nSetup cancelled. No files created.")
            return

        # Create pipeline script
        self._create_pipeline_script()

        # Test Qdrant connection if enabled
        if self.config.use_qdrant:
            if prompt_yes_no("\nTest Qdrant connection?", True):
                self._test_qdrant_connection()

            if prompt_yes_no("Create Qdrant collections now?", True):
                self._create_qdrant_collections()

        # Print next steps
        print_header("Setup Complete!")

        print(f"{Colors.BOLD}Next steps:{Colors.END}\n")
        print(f"1. Review your pipeline script:")
        print(f"   {Colors.CYAN}code src/{pipeline_file}{Colors.END}\n")
        print(f"2. Test with 3 segments:")
        print(f"   {Colors.CYAN}python src/{pipeline_file} --test 3{Colors.END}\n")
        print(f"3. Run full translation:")
        print(f"   {Colors.CYAN}python src/{pipeline_file}{Colors.END}\n")

        if self.config.use_qdrant:
            print(f"4. Test Qdrant integration:")
            print(f"   {Colors.CYAN}python src/test_qdrant_integration.py{Colors.END}\n")

    def _update_env_file(self):
        """Update .env file with Qdrant credentials."""
        env_file = self.base_dir / ".env"

        lines_to_add = []
        if self.config.qdrant_url:
            lines_to_add.append(f"QDRANT_URL={self.config.qdrant_url}")
        if self.config.qdrant_api_key:
            lines_to_add.append(f"QDRANT_API_KEY={self.config.qdrant_api_key}")
        lines_to_add.append(f"USE_QDRANT=true")
        lines_to_add.append(f"QDRANT_PROJECT_ID={self.config.project_id}")

        if env_file.exists():
            with open(env_file, 'a') as f:
                f.write("\n# Qdrant Configuration (added by setup wizard)\n")
                for line in lines_to_add:
                    f.write(line + "\n")
        else:
            with open(env_file, 'w') as f:
                f.write("# Environment Configuration\n")
                f.write("# Created by project setup wizard\n\n")
                for line in lines_to_add:
                    f.write(line + "\n")

        print_success("Updated .env file")

    def _create_pipeline_script(self):
        """Generate customized pipeline script."""
        template = f'''#!/usr/bin/env python3
"""
{self.config.project_name} Translation Pipeline

Generated by project_setup_wizard.py
Project ID: {self.config.project_id}
Direction: {self.config.direction.upper()}

Run:
    python src/{self.config.project_id}_translation_pipeline.py --test 3  # Quick test
    python src/{self.config.project_id}_translation_pipeline.py           # Full run
"""

import os
import sys
import argparse
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# ============================================
# PROJECT CONFIGURATION
# ============================================

PROJECT_ID = "{self.config.project_id}"
PROJECT_NAME = "{self.config.project_name}"
DIRECTION = "{self.config.direction}"

# Input file
INPUT_FILE = "{self.config.source_file}"

# Glossary files: (path, priority)
GLOSSARY_FILES = {repr(self.config.glossary_files)}

# TMX file (optional)
TMX_FILE = "{self.config.tmx_file or ''}"

# Output directory
OUTPUT_DIR = os.path.dirname(INPUT_FILE) if INPUT_FILE else "."

# Model configuration
MODEL_NAME = "{self.config.model_name}"
BATCH_SIZE = {self.config.batch_size}

# Qdrant configuration
USE_QDRANT = {self.config.use_qdrant}

# ============================================
# PIPELINE IMPLEMENTATION
# ============================================

def main():
    parser = argparse.ArgumentParser(description=f"{{PROJECT_NAME}} Translation Pipeline")
    parser.add_argument("--test", type=int, help="Test with N segments")
    parser.add_argument("--start", type=int, default=0, help="Start row")
    parser.add_argument("--end", type=int, help="End row")
    args = parser.parse_args()

    print(f"\\n{'='*60}")
    print(f"{{PROJECT_NAME}} Translation Pipeline")
    print(f"Direction: {{DIRECTION.upper()}}")
    print(f"{'='*60}\\n")

    # Import appropriate pipeline based on direction
    if DIRECTION == "ko_en":
        from production_pipeline_ko_en_improved import ImprovedKOENPipeline as Pipeline
    else:
        from production_pipeline_en_ko_improved import ImprovedENKOPipeline as Pipeline

    # Load glossary
    glossary_terms = []
    for glossary_path, priority in GLOSSARY_FILES:
        if os.path.exists(glossary_path):
            try:
                from loaders.greencross_glossary_loader import load_glossary
                terms = load_glossary(glossary_path, priority=priority)
                glossary_terms.extend(terms)
                print(f"✓ Loaded glossary: {{len(terms)}} terms (Priority {{priority}})")
            except Exception as e:
                print(f"⚠ Error loading {{glossary_path}}: {{e}}")

    print(f"Total glossary terms: {{len(glossary_terms)}}")

    # Load TMX if available
    tm_loader = None
    if TMX_FILE and os.path.exists(TMX_FILE):
        try:
            from loaders.tmx_memory_loader import TMXMemoryLoader
            tm_loader = TMXMemoryLoader(TMX_FILE)
            print(f"✓ Loaded TMX: {{len(tm_loader.translation_units)}} translation units")
        except Exception as e:
            print(f"⚠ Error loading TMX: {{e}}")

    # Initialize pipeline
    pipeline_kwargs = {{
        "model_name": MODEL_NAME,
        "batch_size": BATCH_SIZE,
        "combined_glossary": glossary_terms,
        "tm_loader": tm_loader,
        "use_valkey": True,
    }}

    if USE_QDRANT:
        pipeline_kwargs.update({{
            "use_qdrant": True,
            "qdrant_url": os.getenv("QDRANT_URL"),
            "qdrant_api_key": os.getenv("QDRANT_API_KEY"),
        }})

    pipeline = Pipeline(**pipeline_kwargs)

    # Load source data
    import pandas as pd
    df = pd.read_excel(INPUT_FILE)
    print(f"✓ Loaded source: {{len(df)}} segments")

    # Determine range
    start_row = args.start
    end_row = args.end or len(df)

    if args.test:
        end_row = min(start_row + args.test, len(df))
        print(f"\\n🧪 TEST MODE: Processing {{end_row - start_row}} segments\\n")

    # Process segments
    results = []
    for idx in range(start_row, end_row):
        row = df.iloc[idx]
        # Get source text based on direction
        source_col = [c for c in df.columns if 'source' in c.lower() or 'korean' in c.lower()][0]
        source_text = row[source_col]

        if pd.isna(source_text) or not str(source_text).strip():
            continue

        result = pipeline.translate_segment(
            source_text=str(source_text),
            segment_id=str(row.get('Segment ID', idx))
        )
        results.append(result)

        print(f"[{{idx+1}}/{{end_row}}] ✓ Translated (glossary: {{result.get('glossary_count', 0)}}, TM: {{result.get('tm_count', 0)}})")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"{{PROJECT_ID}}_translated_{{timestamp}}.xlsx")

    results_df = pd.DataFrame(results)
    results_df.to_excel(output_file, index=False)

    print(f"\\n{'='*60}")
    print(f"✓ Complete: {{len(results)}} segments translated")
    print(f"✓ Output: {{output_file}}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
'''

        output_file = self.src_dir / f"{self.config.project_id}_translation_pipeline.py"
        with open(output_file, 'w') as f:
            f.write(template)

        # Make executable
        os.chmod(output_file, 0o755)

        print_success(f"Created: src/{self.config.project_id}_translation_pipeline.py")

    def _test_qdrant_connection(self):
        """Test Qdrant connection."""
        print_info("Testing Qdrant connection...")

        try:
            from memory.qdrant_manager import QdrantManager

            manager = QdrantManager(
                qdrant_url=self.config.qdrant_url or os.getenv('QDRANT_URL'),
                qdrant_api_key=self.config.qdrant_api_key or os.getenv('QDRANT_API_KEY'),
                openai_api_key=os.getenv('OPENAI_API_KEY'),
                enable_hybrid=False
            )

            if manager.health_check():
                print_success("Qdrant connection successful!")
            else:
                print_error("Qdrant connection failed")
        except Exception as e:
            print_error(f"Qdrant test failed: {e}")

    def _create_qdrant_collections(self):
        """Create Qdrant collections for the project."""
        print_info(f"Creating collections for project: {self.config.project_id}")

        try:
            from memory.qdrant_config import QdrantConfig
            from memory.qdrant_manager import QdrantManager

            config = QdrantConfig(
                project_id=self.config.project_id,
                qdrant_url=self.config.qdrant_url or os.getenv('QDRANT_URL'),
                qdrant_api_key=self.config.qdrant_api_key or os.getenv('QDRANT_API_KEY'),
                openai_api_key=os.getenv('OPENAI_API_KEY'),
                use_qdrant=True
            )

            manager = QdrantManager.from_config(config)

            # Create collections
            collections = config.get_all_collections()
            for name, collection in collections.items():
                created = manager.create_collection_if_not_exists(collection)
                if created:
                    print_success(f"Created: {collection}")
                else:
                    print_info(f"Exists: {collection}")

        except Exception as e:
            print_error(f"Failed to create collections: {e}")


def main():
    wizard = ProjectSetupWizard()
    wizard.run()


if __name__ == "__main__":
    main()
