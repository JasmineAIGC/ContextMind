# RiSAWOZ Documentation Index

This directory contains all documentation related to RiSAWOZ dataset evaluation and DST (Dialogue State Tracking) functionality.

## 📚 Essential Documentation (Start Here)

### Getting Started
- [README](readme.md) - **Main overview** of RiSAWOZ integration and usage
- [RiSAWOZ Test Complete Fix](risawoz-test-complete-fix.md) - Complete fix guide for risawoz_test.json

### Core Guides
- [Semantic Matching Guide](SEMANTIC_MATCHING_GUIDE.md) - **Recommended**: Using embeddings for better slot value matching
- [Log Format Improvement](LOG_FORMAT_IMPROVEMENT.md) - Output format aligned with TransferTOD
- [Dataset Isolation](DATASET_ISOLATION.md) - How RiSAWOZ and TransferTOD are kept separate

## 🔧 Technical Reports (Reference)

### Major Fixes
- [Critical Fix: Zero Metrics](CRITICAL_FIX_ZERO_METRICS.md) - Fix for 0% metrics issue (slot comparison bug)
- [Complete Fix Report](COMPLETE_FIX_REPORT.md) - Comprehensive zero metrics fix
- [RiSAWOZ Test JSON Fix](RISAWOZ_TEST_JSON_FIX.md) - Adapter fixes for risawoz_test.json format

### Feature Implementation
- [Intent Extraction Fix](INTENT_EXTRACTION_FIX.md) - Turn-level intent extraction from user_acts
- [Semantic Embedding Summary](SEMANTIC_EMBEDDING_SUMMARY.md) - Summary of embedding integration
- [Metrics Fix Summary](METRICS_FIX_SUMMARY.md) - Quick reference for metrics fixes

### Historical Reports
- [DST Fix Report](dst-fix-report.md) - Original DST evaluation fixes
- [DST Refactor Report](dst-refactor-report.md) - Refactoring details
- [Intent Labels Fix Report](intent-labels-fix-report.md) - Using RiSAWOZ-specific intent labels

## 🔍 Summaries and Quick References

- [Fixes Summary](FIXES_SUMMARY.md) - Quick overview of all fixes
- [Isolation and Intent Summary](ISOLATION_AND_INTENT_SUMMARY.md) - Dataset isolation + intent usage
- [Intent Fix Summary](INTENT_FIX_SUMMARY.md) - Intent extraction summary
- [DST Improvements](dst-improvements.md) - Summary of improvements

## ℹ️ Format and Data Information

- [NLU vs DST Format](nlu-vs-dst-format.md) - Format comparison and why NLU can't be used for DST
- [NLU Format DST Guide](nlu-format-dst-guide.md) - Alternative: Using NLU format for DST (deprecated)
- [User Issue Solution](user-issue-solution.md) - Answers to common user questions

## 🛠️ Troubleshooting

- [Fix RiSAWOZ Error](fix-risawoz-error.md) - File path and error handling
- [Solution Summary](solution-summary.md) - Complete solutions to issues

## 📁 Related Files

### Dataset Implementation
- `benchmark/datasets/risawoz/` - Dataset adapter code
- `benchmark/run_dst_risawoz.py` - Main evaluation script
- `resources/data/RISAWOZ_TEST_README.md` - Test data documentation
- `resources/data/risawoz_test.json` - Test dataset (600 dialogues)

### Configuration
- `benchmark/shared/configs/intent_labels_risawoz.json` - RiSAWOZ intent labels (13 domains)

## 🎯 Quick Start

1. **Setup**: Read [README](readme.md)
2. **Run Evaluation**: 
   ```bash
   python benchmark/run_dst_risawoz.py \
       --data-root resources/data \
       --val-file risawoz_test.json \
       --limit 10 --verbose \
       --use-semantic-match
   ```
3. **Understand Results**: See [Log Format Improvement](LOG_FORMAT_IMPROVEMENT.md)
4. **Improve Accuracy**: Enable semantic matching via [Semantic Matching Guide](SEMANTIC_MATCHING_GUIDE.md)

## 📊 Key Features

- ✅ **Turn-level intent evaluation** (each turn has intent)
- ✅ **Semantic embedding matching** (handles synonyms like 偏贵/贵点)
- ✅ **TransferTOD-aligned metrics** (Slot Acc, Joint Acc, P/R/F1)
- ✅ **Clean log format** (--verbose for details, summary always shown)
- ✅ **Dataset isolation** (RiSAWOZ changes don't affect TransferTOD)
