# ContextMind Debug Log Analysis Guide

## Overview

This guide helps you understand and analyze ContextMind debug logs to troubleshoot issues and optimize your context engineering pipeline.

---

## Debug Mode

Enable debug mode to see detailed context optimization and prompt construction:

```bash
python interactive_demo.py --debug
```

---

## Understanding Debug Output Sections

### Section 1: Context Optimization Result

```
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                    【上下文优化结果】Context Optimization Result                              ║
║  说明：这是 ContextMind 从历史对话、长期记忆等源收集并优化后的上下文信息                      ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
```

**What it shows**: The result of ContextMind's context collection and optimization process.

**Key metrics**:
- **近期对话 (Recent History)**: Number of conversation messages retrieved
- **长期记忆 (Long-term Memory)**: Number of relevant memories retrieved
- **外部知识 (External Knowledge)**: Number of external knowledge items

**What to look for**:
- ✅ History count matches expected conversation length
- ✅ Memory items have high relevance scores (> 0.7)
- ⚠️ If history = 0 and conversation happened, check session settings

### Section 2: Recent Conversation Content

```
【近期对话内容】（最近 10 轮，按时间倒序）
  1. assistant: 最近的回复...
  2. user: 最近的问题...
  3. assistant: 之前的回复...
  ...
```

**What it shows**: The actual conversation messages being provided as context (most recent first).

**Important**: Messages are shown in **reverse chronological order** (newest first). This is intentional:
- LLMs pay more attention to information earlier in the prompt
- Putting recent messages first ensures they get priority
- This is a feature, not a bug

**What to look for**:
- ✅ Recent conversations are present
- ✅ Messages are coherent and relevant
- ⚠️ If messages seem out of order, remember they're reversed

### Section 3: Long-term Memory Content

```
【长期记忆内容】（按相关性排序）
  1. 用户偏好: ... (相关性: 0.95)
  2. 用户背景: ... (相关性: 0.88)
```

**What it shows**: Relevant long-term memories retrieved for this query.

**Relevance scores**:
- 0.9-1.0: Highly relevant
- 0.7-0.9: Moderately relevant
- < 0.7: May not be very useful

**What to look for**:
- ✅ Memories are actually relevant to current query
- ✅ Relevance scores are reasonable
- ⚠️ If too many irrelevant memories, consider tuning retrieval threshold

### Section 4: Complete Prompt

```
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                    【完整Prompt】Complete Prompt Sent to LLM                                  ║
║  说明：这是发送给大语言模型的完整提示词，包含系统指令、上下文和当前用户输入                    ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
```

**What it shows**: The exact prompt sent to the LLM.

**Structure**:
1. **System instructions**: How the LLM should behave
2. **Business information**: Domain-specific context
3. **Conversation history**: Recent messages
4. **Long-term memory**: Relevant user information
5. **Current user input**: The question being answered

**What to look for**:
- ✅ All expected sections are present
- ✅ Conversation history is included
- ✅ Formatting is clean and readable
- ⚠️ Check for any unexpected or malformed content

### Section 5: Prompt Composition Analysis

```
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                    【Prompt构成分析】Prompt Composition Analysis                               ║
║  说明：这是对上述Prompt的统计分析，帮助了解各部分内容的占比                                     ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝

  - 总字符数: 2341
  - 包含对话历史: 是 (10 轮)
  - 包含长期记忆: 是 (3 项)
  - 包含业务信息: 是
```

**What it shows**: Statistics about the prompt structure.

**What to look for**:
- ✅ Character count is reasonable for your LLM's context window
- ✅ All expected components are included
- ⚠️ If character count is very high, consider enabling compression strategies

---

## Common Issues and Solutions

### Issue: LLM Doesn't Reference Previous Conversation

**Symptoms**:
- User mentions something from round 5
- LLM at round 15 doesn't reference it
- User gets frustrated

**Diagnosis**:
1. Check debug log - is conversation history included in prompt?
2. If YES → This is an LLM quality issue, not ContextMind
3. If NO → Check session configuration

**Solutions**:
- If LLM quality issue: Use a better LLM model
- If session issue: Ensure `--no-session` flag is NOT set
- Consider strengthening system prompt with explicit citation examples

### Issue: Context Seems Cut Off

**Symptoms**:
- Only last few messages appear
- Earlier conversation missing

**Diagnosis**:
Check `max_recent_events` setting

**Solutions**:
```bash
# Default is 9999 (unlimited)
python interactive_demo.py --max-events 9999

# Or set to specific value
python interactive_demo.py --max-events 50
```

### Issue: No Long-term Memory

**Symptoms**:
- 长期记忆: 0 项
- Expected memories not appearing

**Diagnosis**:
1. Is memory enabled? Check `--use-memory` flag
2. Have enough conversations happened to extract memories?

**Solutions**:
```bash
# Enable memory
python interactive_demo.py --use-memory

# Give it a few rounds to extract patterns
```

### Issue: LLM Gives Wrong/Off-topic Answers

**Diagnosis**:
1. Check the prompt in debug log
2. Is the right context provided? → If YES, this is LLM issue
3. Is context missing? → This is ContextMind configuration issue

**Distinguishing ContextMind vs LLM Issues**:

| Symptom | ContextMind Issue | LLM Issue |
|---------|-------------------|-----------|
| Context missing from prompt | ✅ YES | ❌ NO |
| Context present but LLM ignores it | ❌ NO | ✅ YES |
| Wrong information retrieved | ✅ YES | ❌ NO |
| Right info retrieved, wrong response | ❌ NO | ✅ YES |

---

## Best Practices

### 1. Enable Debug Mode During Development

Always test with `--debug` flag to understand what's happening:

```bash
python interactive_demo.py --debug
```

### 2. Check Logs After Issues

When you encounter odd behavior:
1. Enable debug mode
2. Reproduce the issue
3. Check the log file in `logs/` directory
4. Look at the prompt that was sent

### 3. Monitor Context Size

For very long conversations:
- Check total character count
- Compare against your LLM's context window
- Consider enabling compression if approaching limits

### 4. Validate Context Quality

Periodically review:
- Are retrieved memories actually relevant?
- Is conversation history in the right order?
- Are all expected sections included in prompt?

### 5. Understand Reverse Order

Remember: Conversation history is shown newest-first in debug output. This is intentional for LLM attention.

---

## Quick Reference

### Debug Sections

1. **上下文优化结果**: What context was collected
2. **近期对话内容**: Conversation messages (newest first)
3. **长期记忆内容**: Relevant memories with scores
4. **完整Prompt**: Exact prompt sent to LLM
5. **Prompt构成分析**: Statistics about the prompt

### Key Flags

```bash
--debug              # Enable debug output
--use-memory         # Enable long-term memory
--max-events N       # Set history window size
--no-session         # Disable session history
```

### Log Files

- Location: `logs/`
- Format: `contextmind_YYYYMMDD_HHMMSS.log`
- Content: Full session with timestamps

---

## Advanced Troubleshooting

### Tracing a Specific Issue

1. **Reproduce with debug mode**:
   ```bash
   python interactive_demo.py --debug > session.log 2>&1
   ```

2. **Find the problematic turn**:
   Search for the user input where issue occurred

3. **Check context sections**:
   - Was the right context available?
   - Was it included in the prompt?
   - How did the LLM respond?

4. **Identify the layer**:
   - Collection issue → Check ContextCollector
   - Optimization issue → Check ContextOptimizer
   - Retrieval issue → Check retrieval strategies
   - LLM issue → Consider different model or prompt tuning

### Performance Analysis

Check logs for:
- Context collection time
- Memory retrieval time
- LLM response time
- Total time per turn

Optimize the slowest component.

---

## Example Log Analysis

### Good Log Example

```
【统计信息】
  - 近期对话: 10 条消息       ✅ History present
  - 长期记忆: 3 项             ✅ Memories retrieved
  - 外部知识: 0 项             ✅ Expected for this app

【长期记忆内容】（按相关性排序）
  1. 用户偏好简洁回答 (相关性: 0.95)   ✅ High relevance
  2. 用户是工程师 (相关性: 0.88)       ✅ High relevance

【Prompt构成分析】
  - 总字符数: 1523             ✅ Reasonable size
  - 包含对话历史: 是 (10 轮)   ✅ History included
  - 包含长期记忆: 是 (3 项)    ✅ Memory included
```

**Result**: Everything working as expected!

### Problem Log Example

```
【统计信息】
  - 近期对话: 0 条消息         ⚠️ NO HISTORY!
  - 长期记忆: 0 项             ⚠️ NO MEMORY!

【Prompt构成分析】
  - 包含对话历史: 否            ⚠️ Missing context
```

**Diagnosis**: Session not enabled or configuration issue.

**Solution**: Check `--no-session` flag, verify session service initialization.

---

## Summary

- ✅ Debug mode provides complete visibility into context engineering
- ✅ Each section shows a specific part of the pipeline
- ✅ Most issues can be identified by checking which section fails
- ✅ Distinguish between ContextMind and LLM issues
- ✅ Use logs to optimize and troubleshoot your system

For more help, see:
- `docs/ARCHITECTURE.md` - System architecture
- `docs/API_REFERENCE.md` - API documentation
- `docs/BEST_PRACTICES.md` - Usage best practices
