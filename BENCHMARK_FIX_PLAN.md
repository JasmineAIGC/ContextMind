# Complete Benchmark Fix Plan

## Executive Summary
The refactoring from `tests/` to `benchmark/` broke DST evaluation completely. This document outlines the comprehensive fix needed to restore functionality.

## Root Cause Analysis

### What Worked (tests/)
1. **Actual DST Execution**: Used `DialogueStateTracker.process_turn()` 
2. **Cumulative State Tracking**: Properly maintained state across turns
3. **Complete Adapter**: Had `get_domain_schema()` for initialization
4. **Correct Metrics**: Calculated Joint Accuracy and other metrics properly
5. **Intent Integration**: Properly integrated intent evaluation

### What's Broken (benchmark/)
1. **No DST Execution**: "Ground Truth" mode doesn't run DST, just simulates
2. **Missing Methods**: Adapter lacks `get_domain_schema()`
3. **Oversimplified Logic**: Lost cumulative state tracking
4. **Wrong Metrics**: Simplified metrics don't match methodology
5. **Disconnected Intent**: Intent evaluation not properly integrated

## Fix Strategy

### Option A: Minimal Patches (NOT RECOMMENDED)
- Try to fix each issue individually
- High risk of missing interactions
- Difficult to verify correctness

### Option B: Complete Port (RECOMMENDED)
- Copy working logic from tests/
- Keep new features from benchmark/
- Easier to verify against known-working code
- Lower risk

## Implementation Plan

### Step 1: Fix Adapter
**File**: `benchmark/datasets/transfertod/adapter.py`

**Add Missing Methods:**
```python
def get_domain_schema(self, domain: str) -> Dict[str, Any]:
    """Extract schema from dialogues"""
    # Copy from tests/adapters/transfertod_adapter.py lines 241-289
    
def get_dialogues_by_domain(self, domain: str = None, data_type: str = None) -> List[str]:
    """Get dialogue IDs by domain and type"""
    # Copy from tests/adapters/transfertod_adapter.py lines 291-324
```

### Step 2: Rewrite Runner
**File**: `benchmark/run_dst_transfertod.py`

**Port Core Logic:**
1. Create `DSTTransferTODEvaluator` class (like tests)
2. Implement `initialize()` method
3. Implement `test_dialogue()` method with actual DST
4. Implement metric calculation methods
5. Keep new display/saving features

**Key Components to Port:**
- Lines 32-90 from tests: Initialization logic
- Lines 92-283 from tests: Dialogue testing logic
- Lines 284-334 from tests: Metric calculation
- Lines 336-441 from tests: Main evaluation loop

**Keep from Current Benchmark:**
- `print_metrics_table()`: Nice display
- `save_results()`: File saving
- `--verbose` control: Good UX
- `--save-plots`: Visualization

### Step 3: Verification
1. Test with small dataset (--limit 2)
2. Compare metrics with tests/ output
3. Verify intent evaluation works
4. Check all error cases

## Expected Results

### Before Fix
```
找到 10 个对话
⚠️  Multiple errors
Total Turns: 7 (wrong)
指标异常
```

### After Fix
```
找到 10 个对话
[1/10] 评测对话: ... ✓
[10/10] 评测对话: ... ✓
Total Turns: 10 (correct)
Slot Accuracy: 0.85 (real)
评测完成！
```

## Implementation Notes

### Critical Points
1. **Don't oversimplify** - Keep full evaluation logic
2. **Test incrementally** - Verify each component
3. **Compare outputs** - Must match tests/
4. **Preserve features** - Don't lose new capabilities

### Dependencies
- Both adapters must match interface
- Intent evaluator must work with both
- Metrics must be calculated consistently

## Success Criteria
- [ ] DST actually runs (not simulated)
- [ ] All dialogues evaluate without errors
- [ ] Metrics match tests/ output
- [ ] Intent evaluation works
- [ ] New features (display, saving) work
- [ ] Documentation updated

## Timeline
- Step 1 (Adapter): 30 min
- Step 2 (Runner): 2-3 hours
- Step 3 (Testing): 1 hour
- **Total**: ~4 hours

## Risk Assessment
- **Low Risk**: Copying proven working code
- **Medium Risk**: Integration with new features
- **Mitigation**: Incremental testing, keep backup

## Conclusion
The fix requires systematic porting of working logic from tests/ while preserving benchmark/ improvements. This is lower risk than trying to patch the broken code.
