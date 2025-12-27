# Complete LLM Prompt Template - Phase 2 Production Pipeline

## 🚀 Actual Prompt Sent to GPT-5 OWL

### **Template Structure:**

```
# Clinical Study Protocol Translation: Korean → English

{SMART_CONTEXT}

## Source Text (Korean)
{KOREAN_TEXT}

## Required Output
Provide only the professional English translation following ICH GCP standards for clinical trial documentation. Use regulatory-compliant terminology without explanations.
```

---

## 📋 **Real Example - Individual Segment**

**Korean Input:** "본 임상시험은 의뢰자가 주관하는 다기관, 무작위배정, 공개 임상시험입니다."

**Complete Prompt Sent to LLM:**

```
# Clinical Study Protocol Translation: Korean → English

## Key Medical Terminology
- 임상시험: clinical trial (Clinical_Trials_Sheet1)
- 다기관: multicenter (Clinical_Trials_Sheet1)
- 공개: open-label (Clinical_Trials_Sheet1)
- 의뢰자: sponsor (Clinical_Trials_Sheet1)
- 시험: study (Clinical_Trials_Sheet1)
- 임상 실험실 평가: clinical laboratory assessment (Clinical_Trials_Sheet1)
- 임상 결과 평가: clinical outcome assessment (Clinical_Trials_Sheet1)
- 임상시험 계획: clinical study plan (Clinical_Trials_Sheet1)

## Locked Terms (Maintain Consistency)
- 임상시험: clinical study
- 의뢰자: sponsor
- 시험대상자: subject

## Previous Translation Context
Previous: 시험대상자는 서면 동의서를 제공해야 합니다... → The subject must provide written informed consent...

## Translation Instructions
- **PRIORITY 1**: Always use locked terms from session memory when available (these override all other terminology)
- **PRIORITY 2**: Use exact terminology from Key Medical Terminology above for terms not in locked terms
- Maintain absolute consistency with locked terms from session memory - never deviate from these
- Translate for clinical study protocol regulatory documentation
- Follow ICH GCP guidelines for clinical trial terminology
- Maintain regulatory compliance and precision
- Use standardized clinical trial terminology (e.g., "clinical trial" not "clinical study", "investigational product" not "test drug")
- Preserve Korean regulatory terms that have established English equivalents
- Provide professional, accurate translation without explanations

## Source Text (Korean)
본 임상시험은 의뢰자가 주관하는 다기관, 무작위배정, 공개 임상시험입니다.

## Required Output
Provide only the professional English translation following ICH GCP standards for clinical trial documentation. Use regulatory-compliant terminology without explanations.
```

**Stats:** ~1,758 characters, ~359 tokens

---

## 📦 **Batch Processing Template**

For batch processing (5 segments per API call):

```
# Clinical Study Protocol Batch Translation: Korean → English

{SMART_CONTEXT_WITH_ALL_TERMS}

## Source Texts (Korean)
1. [First Korean sentence]
2. [Second Korean sentence]
3. [Third Korean sentence]
4. [Fourth Korean sentence]
5. [Fifth Korean sentence]

## Required Output
Provide professional English translations following ICH GCP standards for clinical trial documentation. Use regulatory-compliant terminology without explanations.

Format your response as:
1. [First translation]
2. [Second translation]
3. [Third translation]
4. [Fourth translation]
5. [Fifth translation]
```

---

## 🧠 **Smart Context Components (Dynamic)**

The `{SMART_CONTEXT}` is built dynamically for each segment/batch:

### **1. Key Medical Terminology** (from real glossary search)
```
## Key Medical Terminology
- {korean_term}: {english_term} ({source})
- [Only terms found in current text]
```

### **2. Locked Terms** (from Valkey persistent storage)
```
## Locked Terms (Maintain Consistency)
- {korean}: {english}
- [Terms locked from previous translations]
```

### **3. Previous Context** (from session memory)
```
## Previous Translation Context
Previous: {korean_snippet}... → {english_snippet}...
- [Last 2-3 translations for narrative flow]
```

### **4. Priority Instructions** (explicit hierarchy)
```
## Translation Instructions
- **PRIORITY 1**: Always use Key Medical Terminology from glossary when available (these are authoritative)
- **PRIORITY 2**: Use locked terms from session memory only for terms NOT in Key Medical Terminology
- If a term appears in both Key Medical Terminology and Locked Terms, ALWAYS use the Key Medical Terminology version
- [Clinical trial specific instructions]
```

---

## ⚡ **Priority System in Action**

### **Conflict Resolution Example:**

**Scenario:** Same Korean term has different translations

- **Glossary**: 임상시험 → "clinical trial" ✅ **WINS**
- **Locked**: 임상시험 → "clinical study"

**How it appears in prompt:**
```
## Key Medical Terminology
- 임상시험: clinical trial (Clinical_Trials_Sheet1)

## Locked Terms (Maintain Consistency)  
- 임상시험: clinical study

## Translation Instructions
- **PRIORITY 1**: Always use Key Medical Terminology from glossary when available (these are authoritative)
- **PRIORITY 2**: Use locked terms from session memory only for terms NOT in Key Medical Terminology
- If a term appears in both Key Medical Terminology and Locked Terms, ALWAYS use the Key Medical Terminology version
```

**Result:** LLM will use "clinical trial" because glossary terms now have explicit priority over locked terms.

---

## 🔌 **API Call Structure**

### **GPT-5 OWL (Primary):**
```python
response = client.responses.create(
    model="gpt-5",
    input=[{"role": "user", "content": final_prompt}],
    text={"verbosity": "medium"},
    reasoning={"effort": "minimal"}
)
```

### **GPT-4o (Fallback):**
```python
response = client.chat.completions.create(
    model="gpt-4o", 
    messages=[{"role": "user", "content": final_prompt}],
    max_tokens=500,
    temperature=0.3
)
```

---

## 📊 **Context Optimization**

- **Total Available Terms**: 2906 (Coding Form + Clinical Trials)
- **Terms Actually Used**: ~8-15 per segment (relevant only)
- **Token Reduction**: 98% (20,473 → 413 tokens average)
- **Locked Terms**: 5-8 most recent from Valkey
- **Previous Context**: Last 2-3 translations

---

## 🎯 **Key Features**

1. **Dynamic Context**: Only relevant terms loaded
2. **Explicit Priority**: Locked terms override glossary
3. **Session Persistence**: Terms survive via Valkey (24hr TTL)
4. **Clinical Compliance**: ICH GCP standards enforced
5. **Smart Batching**: 5 segments per API call
6. **Fallback Strategy**: GPT-5 → GPT-4o if needed
7. **Consistency Tracking**: Previous context included

This prompt template ensures maximum translation consistency while optimizing for cost and regulatory compliance.