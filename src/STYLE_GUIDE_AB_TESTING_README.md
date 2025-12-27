# Style Guide A/B Testing System

A configurable system for testing different clinical protocol style guide variants to optimize translation quality vs. token efficiency.

## 🎯 Overview

This system allows you to **A/B test different style guide approaches** to find the optimal balance between:
- **Translation Quality** (regulatory compliance, terminology accuracy)
- **Token Efficiency** (cost optimization, performance)

## 🚀 Quick Start

### 1. Basic Usage

```python
from production_pipeline_with_style_guide import EnhancedPhase2Pipeline

# Initialize with A/B testing enabled
pipeline = EnhancedPhase2Pipeline(
    model_name="Owl",
    enable_experiments=True  # Enable A/B testing
)

# Run experiment on your data
results = pipeline.run_style_guide_experiment(test_data, save_results=True)
```

### 2. Single Variant Testing

```python
from style_guide_config import StyleGuideManager, StyleGuideVariant

# Initialize style guide manager
manager = StyleGuideManager()

# Set specific variant
manager.set_variant(StyleGuideVariant.STANDARD)

# Get style guide content
style_guide = manager.get_style_guide(StyleGuideVariant.STANDARD)
```

### 3. Run Demo

```bash
cd phase2/src
python style_guide_demo.py
```

## 🎨 Available Style Guide Variants

| Variant | Tokens | Quality | Efficiency | Description |
|---------|--------|---------|------------|-------------|
| `none` | 0 | 0.0 | 1.00 | No style guide (baseline) |
| `minimal` | ~100 | 0.3 | 0.95 | Essential ICH-GCP requirements only |
| `compact` | ~200 | 0.6 | 0.90 | Condensed version with key rules |
| `standard` | ~400 | 0.8 | 0.85 | Full clinical protocol style guide |
| `comprehensive` | ~600 | 0.9 | 0.80 | Extended with examples and detailed rules |
| `custom` | Variable | Variable | Variable | User-defined configuration |

## ⚙️ Configuration

### Configuration File (`style_guide_config.json`)

```json
{
  "experiment_settings": {
    "default_variant": "standard",
    "experiment_mode": true,
    "auto_save_results": true
  },
  "a_b_testing": {
    "enabled": true,
    "variants": ["none", "minimal", "standard"],
    "distribution": "round_robin",
    "min_segments_per_variant": 10
  }
}
```

### Environment Variables

```bash
# Set default style guide variant
export STYLE_GUIDE_VARIANT=standard

# Enable A/B testing
export ENABLE_EXPERIMENTS=true

# Specify variants to test
export EXPERIMENT_VARIANTS=none,minimal,standard
```

## 🧪 A/B Testing Workflow

### 1. Setup Experiment Mode

```python
# Enable A/B testing with specific variants
pipeline = EnhancedPhase2Pipeline(
    enable_experiments=True,
    style_guide_config="style_guide_config.json"
)
```

### 2. Run Experiment

```python
# Your test data (pandas DataFrame)
test_data = pd.DataFrame({
    'source_text': ['Korean text 1', 'Korean text 2', ...],
    'reference_en': ['English reference 1', 'English reference 2', ...]
})

# Run experiment
results = pipeline.run_style_guide_experiment(test_data, save_results=True)
```

### 3. Analyze Results

```python
# Get experiment summary
summary = pipeline.get_experiment_summary()

for variant, data in summary.items():
    print(f"{variant}: {data['segments_translated']} segments, "
          f"Avg Quality: {data['average_quality_score']:.2f}, "
          f"Avg Tokens: {data['average_token_count']}")
```

## 📊 Quality Assessment Metrics

The system automatically assesses translation quality based on:

- **Terminology Accuracy** (40% weight)
  - Correct medical term translations
  - Regulatory compliance terms
  
- **Regulatory Compliance** (30% weight)
  - ICH-GCP standard adherence
  - Required regulatory language
  
- **Cultural Adaptation** (20% weight)
  - Korean → English transformation
  - Professional register maintenance
  
- **Sentence Structure** (10% weight)
  - Appropriate sentence length
  - Clear regulatory language

## 🔧 Custom Style Guides

### Create Custom Variant

```json
{
  "custom_variants": {
    "medical_device": {
      "name": "Medical Device Protocol Style Guide",
      "description": "Specialized for medical device clinical trials",
      "estimated_tokens": 350,
      "quality_score": 0.85,
      "token_efficiency": 0.87,
      "enabled": true,
      "custom_rules": {
        "device_specific_terminology": [
          "의료기기 → Medical Device",
          "임상평가 → Clinical Evaluation"
        ],
        "regulatory_framework": [
          "Follow ISO 14155 for medical device clinical investigations",
          "Comply with Medical Device Regulation (MDR) requirements"
        ]
      }
    }
  }
}
```

### Use Custom Variant

```python
# Set custom variant
pipeline.style_guide_manager.set_variant(StyleGuideVariant.CUSTOM)

# The system will automatically use your custom rules
style_guide = pipeline.style_guide_manager.get_style_guide(StyleGuideVariant.CUSTOM)
```

## 📈 Performance Monitoring

### Token Efficiency Tracking

```python
# Get current token reduction
baseline_tokens = 20473  # Phase 1 baseline
current_tokens = result.total_tokens
token_reduction = ((baseline_tokens - current_tokens) / baseline_tokens) * 100

print(f"Token reduction: {token_reduction:.1f}%")
```

### Quality vs. Token Trade-off

```python
# Analyze quality vs. token efficiency
for variant, data in summary.items():
    quality = data['average_quality_score']
    tokens = data['average_token_count']
    efficiency = data['token_efficiency']
    
    print(f"{variant}: Quality={quality:.2f}, Tokens={tokens}, Efficiency={efficiency:.2f}")
```

## 🎯 Best Practices

### 1. Experiment Design

- **Minimum Segments**: Use at least 10 segments per variant for statistical significance
- **Balanced Distribution**: Use round-robin distribution for fair comparison
- **Reference Translations**: Include reference translations for quality assessment

### 2. Variant Selection

- **Start Simple**: Begin with `none` vs `standard` comparison
- **Gradual Enhancement**: Add more complex variants based on results
- **Domain Specific**: Use custom variants for specialized content

### 3. Result Analysis

- **Quality Threshold**: Set minimum quality threshold (e.g., 0.7)
- **Token Budget**: Consider your token budget constraints
- **Production Ready**: Test winning variant in production before full deployment

## 🔍 Example Results Analysis

### Sample Output

```
🧪 Experiment Results:
Total Segments: 30
Duration: 45.23s
Overall Quality: 0.78
Total Tokens: 12500

🎯 Variant Results:
none: 10 segments, Avg Quality: 0.52, Avg Tokens: 2800
minimal: 10 segments, Avg Quality: 0.68, Avg Tokens: 2900
standard: 10 segments, Avg Quality: 0.78, Avg Tokens: 3200
```

### Interpretation

- **`none`**: Lowest quality (0.52) but most token efficient
- **`minimal`**: Good balance (0.68 quality, 95% efficiency)
- **`standard`**: Best quality (0.78) but 85% efficiency

**Recommendation**: Use `minimal` variant for production (good quality, high efficiency)

## 🚨 Troubleshooting

### Common Issues

1. **Experiment Mode Not Enabled**
   ```python
   # Check configuration
   print(f"Experiment Mode: {pipeline.enable_experiments}")
   print(f"Variants: {pipeline.current_experiment_variants}")
   ```

2. **Style Guide Not Loading**
   ```python
   # Check config file
   import os
   print(f"Config exists: {os.path.exists('style_guide_config.json')}")
   ```

3. **Quality Assessment Failing**
   ```python
   # Check quality assessment method
   quality = pipeline.assess_translation_quality(source, translation, reference, variant)
   print(f"Quality score: {quality}")
   ```

### Debug Mode

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Run with verbose output
pipeline.logger.setLevel(logging.DEBUG)
```

## 📚 Integration with Existing Pipeline

### Replace Working Pipeline

```python
# Old way
from production_pipeline_working import WorkingPhase2Pipeline
pipeline = WorkingPhase2Pipeline()

# New way with style guides
from production_pipeline_with_style_guide import EnhancedPhase2Pipeline
pipeline = EnhancedPhase2Pipeline(enable_experiments=True)
```

### Backward Compatibility

The enhanced pipeline maintains all existing functionality:
- ✅ Real glossary integration (2906 terms)
- ✅ Valkey memory management
- ✅ GPT-5 OWL integration
- ✅ Session management
- ✅ Cost tracking

**Plus** the new style guide features:
- 🎨 Configurable style guides
- 🧪 A/B testing capabilities
- 📊 Quality assessment
- 🔧 Custom variant support

## 🎉 Getting Started Checklist

- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Set OpenAI API key
- [ ] Configure `style_guide_config.json`
- [ ] Run demo: `python style_guide_demo.py`
- [ ] Test with your data
- [ ] Analyze results
- [ ] Deploy winning variant to production

## 🤝 Contributing

To add new style guide variants or improve quality assessment:

1. **Add New Variant**: Extend `StyleGuideVariant` enum
2. **Implement Content**: Add method in `StyleGuideManager`
3. **Update Config**: Add to configuration file
4. **Test**: Run experiments to validate
5. **Document**: Update this README

## 📞 Support

For questions or issues:

1. Check the demo script for examples
2. Review configuration options
3. Check logs for error details
4. Verify API access and credentials

---

**Happy A/B Testing! 🎨🧪📊**
