# User Guide 101: Starting a New Translation Project

A step-by-step guide to set up and run a new clinical protocol translation project.

---

## Quick Start Checklist

- [ ] Project ID decided (e.g., `greencross`, `protocol_abc`)
- [ ] Source Excel file prepared
- [ ] Glossary Excel file(s) ready
- [ ] TMX translation memory file (optional)
- [ ] API credentials configured in `.env`
- [ ] Valkey running (Tier 1 cache)
- [ ] Qdrant credentials (optional, Tier 2 semantic search)

---

## 1. Prepare Your Data Files

### 1.1 Source Document (Required)

**Location**: Place in a working directory (e.g., `~/Downloads/Bilingual files/`)

**Format**: Excel (.xlsx) with these columns:

| Column Name | Required | Description |
|-------------|----------|-------------|
| Segment ID | Yes | Unique identifier (UUID or sequential) |
| Segment status | No | Status flag (e.g., "Not Translated", "Translated") |
| Source segment | Yes | Text in source language |
| Target segment | No | Pre-existing translation (can be empty) |

**Example**:
```
| Segment ID                           | Segment status   | Source segment          | Target segment |
|--------------------------------------|------------------|-------------------------|----------------|
| 550e8400-e29b-41d4-a716-446655440000 | Not Translated   | 본 임상시험의 목적은... | (empty)        |
| 550e8400-e29b-41d4-a716-446655440001 | Translated       | 시험대상자 선정기준    | Inclusion criteria |
```

**Notes**:
- Column names are auto-detected (Korean/English patterns)
- CAT tool tags are preserved: `<123/>`, `<123>text</123>`, `[IN_ECN_301]`
- Maximum recommended: 10,000 segments per file

---

### 1.2 Glossary File (Required)

**Location**: `phase2/data/` directory

**Format**: Excel (.xlsx) with these columns:

| Column Name | Required | Description |
|-------------|----------|-------------|
| Korean | Yes | Korean term |
| English | Yes | English translation |
| Priority | No | 1 (mandatory) or 2 (preferred), default: 2 |
| Source | No | Origin of term (e.g., "client_glossary") |
| Mandatory | No | TRUE/FALSE for strict enforcement |
| Alternatives | No | Comma-separated alternative translations |

**Example**:
```
| Korean     | English        | Priority | Source          | Mandatory |
|------------|----------------|----------|-----------------|-----------|
| 임상시험   | clinical study | 1        | client_glossary | TRUE      |
| 시험대상자 | subject        | 1        | ICH_GCP         | TRUE      |
| 이상반응   | adverse event  | 1        | regulatory      | TRUE      |
| 교수       | Professor      | 1        | client          | TRUE      |
| 부작용     | side effect    | 2        | general         | FALSE     |
```

**Priority Levels**:
- **Priority 1**: Must be used exactly (mandatory terms)
- **Priority 2**: Preferred but flexible

**Naming Convention**: `{ProjectName}_{Year}_terms.xlsx`
- Example: `GreenCross_2025_terms.xlsx`

---

### 1.3 Translation Memory - TMX (Optional but Recommended)

**Location**: `phase2/data/` directory

**Format**: TMX 1.4 XML

**Structure**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE tmx SYSTEM "tmx14.dtd">
<tmx version="1.4">
  <header
    creationtool="YourTool"
    creationtoolversion="1.0"
    datatype="plaintext"
    segtype="sentence"
    adminlang="en-US"
    srclang="ko-KR"
    o-tmf="TradosXML"/>
  <body>
    <tu>
      <tuv xml:lang="ko-KR">
        <seg>본 임상시험에 참여하기로 동의한 환자</seg>
      </tuv>
      <tuv xml:lang="en-US">
        <seg>Patients who agreed to participate in this clinical study</seg>
      </tuv>
    </tu>
    <!-- More translation units... -->
  </body>
</tmx>
```

**Language Codes**:
- Korean: `ko-KR` or `ko`
- English: `en-US` or `en`

**Naming Convention**: `{ProjectName}_{SourceLang}-{TargetLang}.tmx`
- Example: `GreenCross_KOKR-ENUS.tmx`

---

## 2. Configure Environment

### 2.1 Create/Update `.env` File

**Location**: `phase2/.env`

```bash
# ===========================================
# REQUIRED: OpenAI API (for GPT-5 translation)
# ===========================================
OPENAI_API_KEY=sk-your-openai-api-key-here

# ===========================================
# REQUIRED: Valkey (Tier 1 - Session Cache)
# ===========================================
VALKEY_HOST=localhost
VALKEY_PORT=6379

# ===========================================
# OPTIONAL: Qdrant (Tier 2 - Semantic Search)
# ===========================================
QDRANT_URL=https://your-cluster.cloud.qdrant.io:6333
QDRANT_API_KEY=your-qdrant-api-key
USE_QDRANT=false
ENABLE_HYBRID_SEARCH=true

# Project-specific (creates isolated collections)
QDRANT_PROJECT_ID=your_project_name

# ===========================================
# OPTIONAL: Additional LLM Providers
# ===========================================
ANTHROPIC_API_KEY=your-anthropic-key
GEMINI_API_KEY=your-gemini-key
```

### 2.2 Start Valkey Server

```bash
# Option 1: Homebrew (macOS)
brew services start valkey

# Option 2: Docker
docker run -d -p 6379:6379 valkey/valkey

# Verify it's running
valkey-cli ping
# Expected: PONG
```

---

## 3. Set Up Project-Scoped Collections (Qdrant)

If using Qdrant for semantic search, set up project-scoped collections:

### 3.1 Configure Project ID

In your `.env`:
```bash
QDRANT_PROJECT_ID=myproject
USE_QDRANT=true
```

This creates isolated collections:
- `myproject_glossary` - Glossary terms
- `myproject_tm_ko_en` - Korean→English TM
- `myproject_tm_en_ko` - English→Korean TM

### 3.2 Load Data to Qdrant

```python
from memory.qdrant_config import QdrantConfig
from memory.qdrant_manager import QdrantManager
from loaders.qdrant_data_loader import QdrantDataLoader

# Initialize with project scope
config = QdrantConfig.from_env(project_id="myproject")
manager = QdrantManager.from_config(config)
loader = QdrantDataLoader(manager, config=config)

# Load glossary (one-time, skips if populated)
glossary_data = [...]  # Your glossary list
loader.load_glossary(glossary_data)

# Load TM
tm_data = [...]  # Your TM pairs
loader.load_tm_ko_en(tm_data)

# Verify
stats = loader.get_collection_stats()
print(stats)
# {'myproject_glossary': 1107, 'myproject_tm_ko_en': 72568, 'myproject_tm_en_ko': 0}
```

---

## 4. Create Project Pipeline Script

### 4.1 Copy and Customize Template

```bash
# Copy existing pipeline as template
cp src/greencross_translation_pipeline.py src/myproject_translation_pipeline.py
```

### 4.2 Update Configuration in Script

Edit `src/myproject_translation_pipeline.py`:

```python
# ============================================
# PROJECT CONFIGURATION - Update these values
# ============================================

PROJECT_ID = "myproject"

# Input file
INPUT_FILE = "/path/to/your/source_document.xlsx"

# Glossary files (Priority 1 first, then Priority 2)
GLOSSARY_FILES = [
    ("data/MyProject_2025_terms.xlsx", 1),      # Priority 1 (mandatory)
    ("data/combined_en_ko_glossary.xlsx", 2),   # Priority 2 (preferred)
]

# TMX file (optional)
TMX_FILE = "data/MyProject_KOKR-ENUS.tmx"

# Translation direction
DIRECTION = "ko_en"  # or "en_ko"

# Output directory
OUTPUT_DIR = "/path/to/output/"

# Model configuration
MODEL_NAME = "Owl"  # GPT-5 OWL recommended
BATCH_SIZE = 50     # Segments per API call

# Qdrant configuration
USE_QDRANT = True   # Enable Tier 2 semantic search
```

---

## 5. Run Translation

### 5.1 Quick Test (3 segments)

```bash
cd /Users/won.suh/Project/translate-ai/phase2
source venv_new/bin/activate

python src/myproject_translation_pipeline.py --test 3
```

**Expected output**:
```
Loading glossary: 1,107 terms
Loading TM: 72,568 pairs
Processing 3 segments...
Segment 1/3: ✓ (glossary: 3, TM: 1)
Segment 2/3: ✓ (glossary: 2, TM: 0)
Segment 3/3: ✓ (glossary: 4, TM: 2)
Complete: 3 segments in 45.2s, cost: $0.01
Output: myproject_translated_20251227_143022.xlsx
```

### 5.2 Full Run (Sequential)

```bash
python src/myproject_translation_pipeline.py
```

### 5.3 Parallel Run (4x Faster for Large Documents)

```bash
# Split into 4 processes
python src/myproject_translation_pipeline_range.py 0 500 > /tmp/range_0.log 2>&1 &
python src/myproject_translation_pipeline_range.py 500 1000 > /tmp/range_1.log 2>&1 &
python src/myproject_translation_pipeline_range.py 1000 1500 > /tmp/range_2.log 2>&1 &
python src/myproject_translation_pipeline_range.py 1500 END > /tmp/range_3.log 2>&1 &

# Monitor all processes
python src/monitor_parallel_translation.py
```

---

## 6. Output Files

### 6.1 Translation Results

**Location**: Output directory specified in config

**Filename**: `{project}_translated_{YYYYMMDD}_{HHMMSS}.xlsx`

**Sheets**:

| Sheet | Contents |
|-------|----------|
| Translation_Results | Segment ID, Source, Target, Quality Score |
| Glossary_Terms_Used | Per-segment term usage breakdown |
| Pipeline_Details | Processing metrics per segment |
| Summary | Totals: segments, time, cost, quality stats |

### 6.2 Logs

**Location**: `/tmp/` or configured log directory

**Files**:
- `range_0_500.log` - Process 1 output
- `range_500_1000.log` - Process 2 output
- etc.

---

## 7. Directory Structure Summary

```
phase2/
├── .env                              # API keys and configuration
├── data/
│   ├── {Project}_2025_terms.xlsx     # Primary glossary
│   ├── combined_en_ko_glossary.xlsx  # Secondary glossary
│   └── {Project}_KOKR-ENUS.tmx       # Translation memory
├── src/
│   ├── {project}_translation_pipeline.py       # Main pipeline
│   ├── {project}_translation_pipeline_range.py # Parallel version
│   └── memory/
│       └── qdrant_config.py          # Project-scoped config
└── output/                           # Translation results
    └── {project}_translated_*.xlsx
```

---

## 8. Troubleshooting

### Valkey Connection Error
```bash
# Check if running
valkey-cli ping

# Start if not running
brew services start valkey
```

### Qdrant Connection Error
```bash
# Test connection
python -c "
from qdrant_client import QdrantClient
import os
client = QdrantClient(url=os.getenv('QDRANT_URL'), api_key=os.getenv('QDRANT_API_KEY'))
print(client.get_collections())
"
```

### Missing Glossary Terms
```bash
# Verify glossary loaded
python -c "
from loaders.greencross_glossary_loader import load_glossary
terms = load_glossary('data/MyProject_2025_terms.xlsx')
print(f'Loaded {len(terms)} terms')
"
```

### Out of Memory (Large Documents)
```python
# Reduce batch size in pipeline config
BATCH_SIZE = 25  # Instead of 50
```

---

## 9. Cost Estimation

| Segments | Sequential Time | Parallel Time (4x) | Estimated Cost |
|----------|-----------------|-------------------|----------------|
| 50 | 10 min | 10 min | $0.14 |
| 500 | 1.5 hr | 25 min | $1.40 |
| 2,000 | 7 hr | 2 hr | $5.60 |
| 8,000 | 28 hr | 10 hr | $22.40 |

**Formula**: ~$0.0028 per segment (GPT-5 OWL with 50-segment batching)

---

## 10. Quick Reference Commands

```bash
# Setup
source venv_new/bin/activate
brew services start valkey

# Test Qdrant integration
python src/test_qdrant_integration.py

# Quick validation (3 segments)
python src/myproject_translation_pipeline.py --test 3

# Full sequential run
python src/myproject_translation_pipeline.py

# Parallel run (4 processes)
python src/myproject_translation_pipeline_range.py 0 500 &
python src/myproject_translation_pipeline_range.py 500 1000 &
python src/myproject_translation_pipeline_range.py 1000 1500 &
python src/myproject_translation_pipeline_range.py 1500 END &
python src/monitor_parallel_translation.py

# QA validation
python src/translation_qa.py
```
