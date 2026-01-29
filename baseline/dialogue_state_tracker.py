"""
Dialogue State Tracker - 对话状态追踪器

Implementation based on ACL 2023 paper:
"ChatGPT for Zero-shot Dialogue State Tracking: A Solution or an Opportunity?"

This module implements a complete zero-shot dialogue state tracking system that:
1. Uses no fine-tuning (pure zero-shot approach)
2. Relies on prompt engineering with slot ontology definitions
3. Maintains full dialogue history for context management
4. Performs cumulative state updates: DS_t = update(DS_{t-1}, updates)
5. Handles special values (?, dontcare) as per paper specification
6. Filters hallucinations (non-ontology slots)
7. Normalizes values for consistency
8. Parses JSON responses robustly from LLM outputs

Paper Reference:
    Hu, Y., Lee, H., Xing, B., Yao, W., Xiong, Y., Radev, D., & Ren, X. (2023).
    ChatGPT for Zero-shot Dialogue State Tracking: A Solution or an Opportunity?
    In Proceedings of ACL 2023.

Key Components:
    - PromptManager: Manages ontology, constraints, and prompt generation
    - ResponseParser: Robust JSON extraction and hallucination filtering
    - DialogueStateTracker: Main orchestrator for multi-turn DST

Author: ContextMind Project
License: MIT
"""

import json
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpecialValue(Enum):
    """
    Special slot values as defined in the ACL 2023 paper.
    
    Attributes:
        UNKNOWN: "?" - User is asking about this slot (no value provided)
        DONTCARE: "dontcare" - User doesn't care about this slot's value
    """
    UNKNOWN = "?"
    DONTCARE = "dontcare"


@dataclass
class DialogueTurn:
    """
    Represents a single dialogue turn with system and user utterances.
    
    Attributes:
        system_utterance: The system/assistant's response
        user_utterance: The user's input
        predicted_state: The cumulative dialogue state after this turn
        turn_updates: Slot updates extracted from this turn only
        raw_llm_response: Original LLM response before parsing (optional)
    """
    system_utterance: str
    user_utterance: str
    predicted_state: Dict[str, str] = field(default_factory=dict)
    turn_updates: Dict[str, str] = field(default_factory=dict)
    raw_llm_response: Optional[str] = None


class PromptManager:
    """
    Prompt Manager for Zero-shot Dialogue State Tracking.
    
    Manages the ontology (slot definitions), categorical constraints, and prompt
    generation according to ACL 2023 paper Figure 2 specifications.
    
    The prompt structure follows the paper's design:
    1. Slot ontology definitions (describing what each slot represents)
    2. Categorical constraints (predefined value lists for certain slots)
    3. Dialogue formatting instructions
    4. Special value handling rules (?, dontcare)
    5. JSON output format specification
    
    Attributes:
        domain: The dialogue domain (e.g., "general", "hotel", "restaurant")
        ontology_slots: Dictionary mapping slot names to their descriptions
        categorical_constraints: Dictionary mapping slot names to allowed values
        value_normalization: Dictionary for normalizing different value representations
        
    Example:
        >>> pm = PromptManager(domain="restaurant")
        >>> pm.add_slot("food_type", "Type of cuisine", ["Chinese", "Italian", "Japanese"])
        >>> instruction = pm.get_system_instruction()
    """
    
    def __init__(self, domain: str = "general"):
        """
        Initialize the Prompt Manager.
        
        Args:
            domain: Dialogue domain for context-specific slot definitions.
                   Supported domains: "general", "hotel", "restaurant", "taxi", "train"
        """
        self.domain = domain
        
        # Slot ontology - maps slot names to their semantic descriptions
        # This corresponds to "slots" in paper Figure 2
        self.ontology_slots: Dict[str, str] = {
            # General intent and topic slots
            "intent": "用户的主要意图 (User's primary intent)",
            "topic": "当前讨论的话题 (Current discussion topic)",
            "entity": "提到的实体或对象 (Mentioned entity or object)",
            
            # Temporal slots
            "time": "时间信息 (Time information)",
            "date": "日期信息 (Date information)",
            "duration": "持续时间 (Duration)",
            
            # Location slots
            "location": "地点或位置 (Location or place)",
            "departure": "出发地 (Departure location)",
            "destination": "目的地 (Destination)",
            
            # Preference slots
            "preference": "用户偏好 (User preference)",
            "requirement": "特殊要求 (Special requirements)",
            
            # Numeric slots
            "price": "价格或费用 (Price or cost)",
            "quantity": "数量 (Quantity)",
            "rating": "评分或等级 (Rating or level)",
        }
        
        # Categorical constraints - slots with predefined value sets
        # This corresponds to "categorical" in paper Figure 2
        self.categorical_constraints: Dict[str, List[str]] = {
            "intent": ["询问", "预订", "修改", "取消", "确认", "投诉", "其他"],
            "rating": ["1星", "2星", "3星", "4星", "5星"],
            "price": ["便宜", "中等", "昂贵"],
        }
        
        # Value normalization mapping for consistent representation
        # Addresses the paper's discussion on value normalization (Section 4.2)
        self.value_normalization: Dict[str, str] = {
            "便宜的": "便宜",
            "贵的": "昂贵",
            "很贵": "昂贵",
            "不贵": "中等",
            "一般": "中等",
            "普通": "中等",
        }
    
    def add_slot(self, slot_name: str, description: str, 
                 categorical_values: Optional[List[str]] = None) -> None:
        """
        Add a custom slot to the ontology.
        
        Allows domain-specific customization of the slot schema.
        
        Args:
            slot_name: Name of the slot (e.g., "food_type", "hotel_stars")
            description: Semantic description of what this slot represents
            categorical_values: Optional list of allowed values if this is a
                              categorical slot. If provided, only these values
                              will be considered valid.
                              
        Example:
            >>> pm = PromptManager()
            >>> pm.add_slot("food_type", "Type of cuisine", 
            ...            ["Chinese", "Italian", "Japanese"])
        """
        self.ontology_slots[slot_name] = description
        if categorical_values:
            self.categorical_constraints[slot_name] = categorical_values
            logger.debug(f"Added categorical slot '{slot_name}' with {len(categorical_values)} values")
        else:
            logger.debug(f"Added free-form slot '{slot_name}'")
    
    def remove_slot(self, slot_name: str) -> bool:
        """
        Remove a slot from the ontology.
        
        Args:
            slot_name: Name of the slot to remove
            
        Returns:
            True if slot was removed, False if it didn't exist
        """
        removed = False
        if slot_name in self.ontology_slots:
            del self.ontology_slots[slot_name]
            removed = True
        if slot_name in self.categorical_constraints:
            del self.categorical_constraints[slot_name]
            removed = True
        return removed
    
    def get_slot_names(self) -> Set[str]:
        """
        Get all defined slot names.
        
        Returns:
            Set of slot names in the ontology
        """
        return set(self.ontology_slots.keys())
    
    def get_system_instruction(self) -> str:
        """
        Build the system instruction prompt according to ACL 2023 paper Figure 2.
        
        The prompt structure includes:
        1. Slot ontology definitions with descriptions
        2. Categorical constraints for applicable slots
        3. Dialogue format specification (system/user)
        4. Update extraction instructions
        5. Special value handling rules (?, dontcare)
        6. Output format requirements (JSON)
        
        Returns:
            Complete system instruction string ready for LLM input
            
        Note:
            This is the core prompt engineering component. The quality of
            DST predictions heavily depends on this prompt design.
        """
        instruction = f"""请考虑以下槽位（"slots"）列表，以 JSON 格式提供：

"slots": {json.dumps(self.ontology_slots, indent=2, ensure_ascii=False)}

某些槽位只能从预定义列表中取值（"categorical"约束）：

"categorical": {json.dumps(self.categorical_constraints, indent=2, ensure_ascii=False)}

现在考虑以下系统（"system"）和用户（"user"）之间的对话。

请告诉我用户在最新回复中更新了哪些槽位？
以 JSON 格式呈现更新内容。如果没有槽位被更新，返回空的 JSON 对象 {{}}.

特殊规则（Special Value Handling）：
1. 如果用户请求某个槽位信息（但未提供具体值），用 "?" 填充
   示例：用户："酒店价格多少？" → {{"price": "?"}}
   
2. 如果用户表示不关心某个槽位，用 "dontcare" 填充
   示例：用户："什么价格都行" → {{"price": "dontcare"}}
   
3. 只更新明确提到或可从上下文推断的槽位
   - 不要臆测未提及的信息
   - 利用对话历史进行共指消解
   
4. 保持与之前对话的一致性
   - 注意代词指代（"它"、"那里"、"也一样"等）
   - 从完整对话历史中推断含义

5. 对于categorical槽位，只能从预定义列表中选择值

输出要求：
- 直接返回 JSON 格式的槽位更新
- 不要包含任何额外的解释或文本
- 格式：{{"slot_name": "value", ...}}
- 如果无更新，返回：{{}}
"""
        
        return instruction
    
    def normalize_value(self, value: str) -> str:
        """
        Normalize slot values for consistency.
        
        Addresses value variation issues discussed in paper Section 4.2.
        Different surface forms are mapped to canonical representations.
        
        Args:
            value: Original value string from LLM output
            
        Returns:
            Normalized value string
            
        Example:
            >>> pm = PromptManager()
            >>> pm.normalize_value("便宜的")
            "便宜"
            >>> pm.normalize_value("很贵")
            "昂贵"
        """
        # Strip whitespace
        value = value.strip()
        
        # Apply normalization mapping
        if value in self.value_normalization:
            normalized = self.value_normalization[value]
            logger.debug(f"Normalized '{value}' to '{normalized}'")
            return normalized
        
        # Additional normalization could be added here:
        # - Lowercase conversion for English
        # - Removing punctuation
        # - Standardizing date/time formats
        
        return value
    
    def validate_categorical_value(self, slot: str, value: str) -> bool:
        """
        Validate if a value is allowed for a categorical slot.
        
        Args:
            slot: Slot name
            value: Proposed value
            
        Returns:
            True if value is valid for this slot, False otherwise
        """
        if slot not in self.categorical_constraints:
            return True  # Non-categorical slots accept any value
        
        allowed_values = self.categorical_constraints[slot]
        is_valid = value in allowed_values
        
        if not is_valid:
            logger.warning(
                f"Invalid categorical value '{value}' for slot '{slot}'. "
                f"Allowed values: {allowed_values}"
            )
        
        return is_valid


class ResponseParser:
    """
    Response Parser for robust JSON extraction from LLM outputs.
    
    Handles the instability issue mentioned in the ACL 2023 paper where
    ChatGPT doesn't always return pure JSON. Implements multiple parsing
    strategies with fallback mechanisms.
    
    Key Features:
    1. Multiple JSON extraction strategies (direct parse, regex, key-value pairs)
    2. Hallucination filtering (only keeps ontology-defined slots)
    3. Value normalization
    4. Categorical constraint validation
    
    The paper reports ~90.4% valid predictions and ~9.6% hallucinations,
    which this parser aims to filter.
    
    Attributes:
        prompt_manager: PromptManager instance for ontology access
        strict_categorical: If True, reject invalid categorical values
    """
    
    def __init__(self, prompt_manager: PromptManager, strict_categorical: bool = False):
        """
        Initialize the Response Parser.
        
        Args:
            prompt_manager: PromptManager instance containing slot ontology
            strict_categorical: Whether to strictly enforce categorical constraints
                              (default: False, will log warnings but accept values)
        """
        self.prompt_manager = prompt_manager
        self.strict_categorical = strict_categorical
    
    def extract_json(self, text: str) -> Dict[str, str]:
        """
        Extract JSON from LLM response text using robust multi-strategy approach.
        
        Addresses the parsing instability issue discussed in the paper (Section 4).
        Tries multiple extraction methods in order of preference:
        1. Direct JSON parsing (if response is pure JSON)
        2. Regex-based JSON block extraction (handles embedded JSON)
        3. Key-value pair extraction (fallback for malformed JSON)
        
        Args:
            text: Raw LLM response text (may contain JSON embedded in prose)
            
        Returns:
            Dictionary of extracted slot updates. Returns empty dict on failure.
            
        Example:
            >>> parser = ResponseParser(pm)
            >>> parser.extract_json('{"intent": "book", "location": "Beijing"}')
            {"intent": "book", "location": "Beijing"}
            >>> parser.extract_json('The updates are: {"intent": "book"}')
            {"intent": "book"}
        """
        if not text or not text.strip():
            return {}
        
        try:
            # Strategy 1: Direct JSON parsing (fastest, works for clean outputs)
            try:
                result = json.loads(text.strip())
                if isinstance(result, dict):
                    logger.debug("JSON extracted via direct parsing")
                    return result
                elif isinstance(result, list):
                    # Handle list of dicts: merge them
                    return self._merge_dict_list(result)
            except json.JSONDecodeError:
                pass
            
            # Strategy 2: Regex-based JSON extraction (handles embedded JSON)
            json_result = self._extract_json_with_regex(text)
            if json_result:
                logger.debug("JSON extracted via regex")
                return json_result
            
            # Strategy 3: Key-value pair extraction (fallback for malformed JSON)
            kv_result = self._extract_key_value_pairs(text)
            if kv_result:
                logger.debug("JSON extracted via key-value pattern matching")
                return kv_result
            
            # All strategies failed
            logger.warning(f"Failed to extract JSON from response: {text[:100]}...")
            return {}
            
        except Exception as e:
            logger.error(f"Exception during JSON extraction: {e}")
            return {}
    
    def _extract_json_with_regex(self, text: str) -> Optional[Dict[str, str]]:
        """
        Extract JSON using regex patterns.
        
        Tries multiple regex patterns to handle various JSON embedding styles.
        """
        # Patterns ordered by specificity
        json_patterns = [
            # Nested braces (handles complex nested structures)
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
            # Simple braces (single-level objects)
            r'\{.*?\}',
            # Square brackets (array format)
            r'\[.*?\]',
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                json_str = match.group(0)
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict):
                        return parsed
                    elif isinstance(parsed, list):
                        return self._merge_dict_list(parsed)
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _extract_key_value_pairs(self, text: str) -> Dict[str, str]:
        """
        Extract key-value pairs using regex (fallback strategy).
        
        Matches patterns like: "key": "value" or 'key': 'value'
        """
        # Pattern: "key": "value" or 'key': 'value'
        kv_pattern = r'["\']([^"\']+)["\']\s*:\s*["\']([^"\']*)["\']'
        matches = re.findall(kv_pattern, text)
        
        if matches:
            return dict(matches)
        return {}
    
    def _merge_dict_list(self, dict_list: List) -> Dict[str, str]:
        """
        Merge a list of dictionaries into a single dictionary.
        
        Used when LLM returns an array of slot updates.
        """
        result = {}
        for item in dict_list:
            if isinstance(item, dict):
                result.update(item)
        return result
    
    def filter_hallucinations(self, updates: Dict[str, str]) -> Dict[str, str]:
        """
        Filter hallucinated slots that are not in the ontology.
        
        Implements hallucination filtering as discussed in the paper.
        The paper reports ~9.6% hallucination rate where ChatGPT predicts
        slots not defined in the ontology.
        
        Also applies:
        - Value normalization
        - Categorical constraint validation (if strict mode enabled)
        
        Args:
            updates: Raw slot updates extracted from LLM response
            
        Returns:
            Filtered dictionary containing only valid ontology slots with
            normalized values
            
        Example:
            >>> updates = {"intent": "book", "fake_slot": "value", "price": "便宜的"}
            >>> filtered = parser.filter_hallucinations(updates)
            >>> filtered
            {"intent": "book", "price": "便宜"}  # fake_slot removed, price normalized
        """
        filtered = {}
        valid_slots = self.prompt_manager.get_slot_names()
        
        for slot, value in updates.items():
            # Filter 1: Only keep slots defined in ontology
            if slot not in valid_slots:
                logger.warning(
                    f"Hallucinated slot '{slot}' not in ontology. "
                    f"This is likely a prediction error."
                )
                continue
            
            # Filter 2: Apply value normalization
            normalized_value = self.prompt_manager.normalize_value(value)
            
            # Filter 3: Validate categorical constraints (if strict mode)
            if self.strict_categorical:
                if not self.prompt_manager.validate_categorical_value(slot, normalized_value):
                    logger.warning(
                        f"Skipping invalid categorical value '{normalized_value}' "
                        f"for slot '{slot}'"
                    )
                    continue
            
            filtered[slot] = normalized_value
        
        # Log statistics
        if len(updates) > len(filtered):
            logger.info(
                f"Filtered {len(updates) - len(filtered)} hallucinated/invalid slots "
                f"out of {len(updates)} predictions"
            )
        
        return filtered
    
    def parse_and_filter(self, text: str) -> Dict[str, str]:
        """
        Complete parsing pipeline: extract JSON and filter hallucinations.
        
        Convenience method that combines extraction and filtering.
        
        Args:
            text: Raw LLM response
            
        Returns:
            Filtered, validated slot updates
        """
        raw_updates = self.extract_json(text)
        filtered_updates = self.filter_hallucinations(raw_updates)
        return filtered_updates


class DialogueStateTracker:
    """
    Zero-shot Dialogue State Tracker (DST) based on ACL 2023 paper.
    
    Implements the complete DST pipeline:
    1. Maintains full dialogue history for context (addresses "中间丢失" issue)
    2. Constructs prompts with ontology and constraints
    3. Calls LLM to predict slot updates
    4. Parses JSON responses robustly
    5. Filters hallucinations
    6. Performs cumulative state updates: DS_t = update(DS_{t-1}, updates_t)
    7. Handles special values (?, dontcare)
    
    The tracker is completely zero-shot - no fine-tuning required.
    All intelligence comes from prompt engineering and LLM capabilities.
    
    Attributes:
        llm_client: Optional LLM client for inference (if None, uses rule-based fallback)
        prompt_manager: Manages ontology and prompt generation
        response_parser: Parses and validates LLM outputs
        messages: Full dialogue history in chat format
        current_state: Cumulative dialogue state (DS_t)
        turns: History of all dialogue turns with predictions
        
    Example:
        >>> tracker = DialogueStateTracker(llm_client=my_llm)
        >>> tracker.reset_dialogue()
        >>> state = await tracker.process_turn(
        ...     system_utterance="你好，需要帮助吗？",
        ...     user_utterance="我想订酒店"
        ... )
        >>> print(state)  # {"intent": "预订"}
    """
    
    def __init__(self, 
                 llm_client: Optional[Any] = None,
                 prompt_manager: Optional[PromptManager] = None,
                 domain: str = "general",
                 strict_categorical: bool = False,
                 temperature: float = 0.0):
        """
        Initialize the Dialogue State Tracker.
        
        Args:
            llm_client: LLM client for inference. Can be any object with a chat
                       method. If None, falls back to rule-based extraction.
            prompt_manager: Custom PromptManager. If None, creates default one.
            domain: Dialogue domain for default prompt manager
            strict_categorical: Whether to strictly enforce categorical constraints
            temperature: LLM temperature (default 0.0 for deterministic outputs)
        """
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager or PromptManager(domain)
        self.response_parser = ResponseParser(
            self.prompt_manager, 
            strict_categorical=strict_categorical
        )
        self.temperature = temperature
        
        # Dialogue history for LLM context (crucial for coreference resolution)
        self.messages: List[Dict[str, str]] = []
        
        # Current cumulative dialogue state (DS_t in paper notation)
        self.current_state: Dict[str, str] = {}
        
        # Turn-by-turn history with predictions
        self.turns: List[DialogueTurn] = []
        
        logger.info(
            f"Initialized DialogueStateTracker with {len(self.prompt_manager.ontology_slots)} "
            f"slots in domain '{domain}'"
        )
    
    def reset_dialogue(self) -> None:
        """
        Reset state for a new dialogue.
        
        Clears:
        - Message history
        - Current dialogue state  
        - Turn history
        
        Initializes message history with system instruction prompt.
        Call this before starting each new conversation.
        """
        self.messages = [
            {
                "role": "system",
                "content": self.prompt_manager.get_system_instruction()
            }
        ]
        self.current_state = {}
        self.turns = []
        logger.info("Dialogue reset - ready for new conversation")
    
    async def process_turn(self, 
                          system_utterance: str, 
                          user_utterance: str) -> Dict[str, str]:
        """
        Process a single dialogue turn and update cumulative state.
        
        This is the core DST pipeline implementing the paper's approach:
        1. Format current turn as "system: ... \\n user: ..."
        2. Add to message history (for context and coreference)
        3. Call LLM to predict slot updates
        4. Parse LLM response to extract JSON
        5. Filter hallucinations
        6. Update cumulative state: DS_t = update(DS_{t-1}, updates_t)
        7. Record turn in history
        
        Args:
            system_utterance: What the system/assistant said
            user_utterance: What the user said
            
        Returns:
            Current cumulative dialogue state (DS_t) after processing this turn
            
        Example:
            >>> # Turn 1
            >>> state = await tracker.process_turn("你好", "我想订酒店")
            >>> # state: {"intent": "预订"}
            >>> 
            >>> # Turn 2 - context is maintained for coreference
            >>> state = await tracker.process_turn("去哪里？", "北京")
            >>> # state: {"intent": "预订", "destination": "北京"}
        """
        # Step 1: Format turn according to paper's convention
        turn_prompt = f'system: "{system_utterance}"\nuser: "{user_utterance}"'
        logger.debug(f"Processing turn: {turn_prompt}")
        
        # Step 2: Add to message history for context (crucial for coreference resolution)
        self.messages.append({
            "role": "user",
            "content": turn_prompt
        })
        
        # Step 3: Get LLM prediction or use fallback
        turn_update = {}
        raw_output = ""
        
        if self.llm_client:
            try:
                # Call LLM to predict slot updates
                raw_output = await self._call_llm()
                
                # Step 4: Add LLM response to history for continuity
                # This enables multi-turn reasoning and coreference resolution
                self.messages.append({
                    "role": "assistant",
                    "content": raw_output
                })
                
                # Step 5: Parse and filter response
                turn_update = self.response_parser.parse_and_filter(raw_output)
                
            except Exception as e:
                logger.error(f"Error during LLM call or parsing: {e}")
                turn_update = {}
        else:
            # Fallback to rule-based extraction (for demo/testing without LLM)
            turn_update = self._extract_with_rules(user_utterance)
            raw_output = json.dumps(turn_update, ensure_ascii=False)
        
        # Step 6: Cumulative state update (DS_t = update(DS_{t-1}, updates_t))
        self._update_state(turn_update)
        
        # Step 7: Record this turn in history
        turn = DialogueTurn(
            system_utterance=system_utterance,
            user_utterance=user_utterance,
            predicted_state=self.current_state.copy(),
            turn_updates=turn_update.copy(),
            raw_llm_response=raw_output
        )
        self.turns.append(turn)
        
        logger.info(
            f"Turn {len(self.turns)}: extracted {len(turn_update)} updates, "
            f"total state has {len(self.current_state)} slots"
        )
        
        return self.current_state.copy()
    
    async def _call_llm(self) -> str:
        """
        Call LLM API with current message history.
        
        Handles different LLM client interfaces:
        - chat_async/chat methods
        - Direct callable
        - Various response formats (string, object with content, choices, etc.)
        
        Returns:
            Raw LLM response text
            
        Raises:
            Exception: If LLM call fails (caught and logged by caller)
        """
        try:
            # Try different common LLM client interfaces
            if hasattr(self.llm_client, 'chat_async'):
                response = await self.llm_client.chat_async(
                    messages=self.messages,
                    temperature=self.temperature
                )
            elif hasattr(self.llm_client, 'chat'):
                response = self.llm_client.chat(
                    messages=self.messages,
                    temperature=self.temperature
                )
            else:
                # Try direct call
                response = await self.llm_client(
                    messages=self.messages,
                    temperature=self.temperature
                )
            
            # Extract text from various response formats
            if isinstance(response, str):
                return response
            elif hasattr(response, 'content'):
                return response.content
            elif hasattr(response, 'choices') and len(response.choices) > 0:
                return response.choices[0].message.content
            else:
                return str(response)
                
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def _extract_with_rules(self, user_utterance: str) -> Dict[str, str]:
        """
        Rule-based slot extraction fallback (when no LLM available).
        
        This is a simple keyword-based extractor for demo/testing purposes.
        Not as powerful as LLM-based extraction, but allows the system to
        function without an API key.
        
        Args:
            user_utterance: User's input text
            
        Returns:
            Extracted slot updates based on simple rules
            
        Note:
            This is NOT part of the paper's approach. It's just a fallback
            for running demos without LLM access.
        """
        updates = {}
        
        # Intent detection via keywords
        intent_keywords = {
            "预订": ["想要", "需要", "预订", "订", "预定"],
            "询问": ["什么", "哪", "怎么", "如何", "是否", "吗", "多少"],
            "取消": ["取消", "不要", "退订"],
            "修改": ["修改", "改", "换"],
        }
        
        for intent, keywords in intent_keywords.items():
            if any(kw in user_utterance for kw in keywords):
                updates["intent"] = intent
                break
        
        # Location extraction
        location_indicators = {
            "destination": ["去", "到"],
            "departure": ["从"],
            "location": ["在"],
        }
        
        for slot, indicators in location_indicators.items():
            for indicator in indicators:
                if indicator in user_utterance:
                    # Simple extraction: get text after indicator
                    parts = user_utterance.split(indicator)
                    if len(parts) > 1:
                        # Extract until punctuation
                        location = parts[1].split("，")[0].split("。")[0].split("、")[0].strip()[:20]
                        if len(location) > 0:
                            updates[slot] = location
                            break
        
        # Price preference detection
        price_keywords = {
            "便宜": ["便宜", "实惠", "不贵"],
            "昂贵": ["贵", "高档", "豪华"],
        }
        
        for price_level, keywords in price_keywords.items():
            if any(kw in user_utterance for kw in keywords):
                updates["price"] = price_level
                break
        
        logger.debug(f"Rule-based extraction: {updates}")
        return updates
    
    def _update_state(self, updates: Dict[str, str]) -> None:
        """
        Update cumulative dialogue state with new slot values.
        
        Implements the cumulative update formula from the paper:
        DS_t = update(DS_{t-1}, predicted_updates)
        
        Handles special values according to paper specification:
        - "?": User is asking about this slot (don't update state)
        - "dontcare": User doesn't care about this slot (record this preference)
        - Normal values: Update the slot
        
        Args:
            updates: Slot updates from current turn
            
        Note:
            This implements slot-filling semantics: newer values overwrite
            older ones for the same slot. Some DST systems use more complex
            update strategies, but this aligns with the paper's approach.
        """
        for slot, value in updates.items():
            # Handle special values as per paper specification
            if value == SpecialValue.UNKNOWN.value:
                # User is asking about this slot - don't update state
                # Example: "What's the price?" -> {"price": "?"}
                logger.debug(f"User asking about slot '{slot}', not updating state")
                continue
                
            elif value == SpecialValue.DONTCARE.value:
                # User doesn't care about this slot - record this preference
                # Example: "Any price is fine" -> {"price": "dontcare"}
                logger.debug(f"User doesn't care about slot '{slot}'")
                self.current_state[slot] = SpecialValue.DONTCARE.value
                
            elif value and value.strip():
                # Normal value - update the slot
                self.current_state[slot] = value
                logger.debug(f"Updated slot '{slot}' = '{value}'")
            else:
                # Empty value - ignore
                logger.debug(f"Ignoring empty value for slot '{slot}'")
    
    def get_current_state(self) -> Dict[str, str]:
        """
        Get the current cumulative dialogue state.
        
        Returns:
            Copy of current state dictionary (DS_t)
        """
        return self.current_state.copy()
    
    def get_turn_history(self) -> List[DialogueTurn]:
        """
        Get complete turn-by-turn dialogue history.
        
        Returns:
            Copy of turn history list
        """
        return self.turns.copy()
    
    def get_slot_value(self, slot_name: str) -> Optional[str]:
        """
        Get value of a specific slot in current state.
        
        Args:
            slot_name: Name of the slot to retrieve
            
        Returns:
            Slot value if present, None otherwise
        """
        return self.current_state.get(slot_name)
    
    def has_slot(self, slot_name: str) -> bool:
        """
        Check if a slot has been filled in current state.
        
        Args:
            slot_name: Name of the slot to check
            
        Returns:
            True if slot is present in state, False otherwise
        """
        return slot_name in self.current_state
    
    def clear_slot(self, slot_name: str) -> bool:
        """
        Clear a specific slot from current state.
        
        Useful for handling user corrections or resets.
        
        Args:
            slot_name: Name of the slot to clear
            
        Returns:
            True if slot was removed, False if it didn't exist
        """
        if slot_name in self.current_state:
            del self.current_state[slot_name]
            logger.info(f"Cleared slot '{slot_name}'")
            return True
        return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get tracking statistics for analysis.
        
        Returns:
            Dictionary with statistics:
            - num_turns: Number of dialogue turns processed
            - num_slots_filled: Number of slots in current state
            - num_messages: Total messages in history
            - filled_slots: List of currently filled slot names
        """
        return {
            "num_turns": len(self.turns),
            "num_slots_filled": len(self.current_state),
            "num_messages": len(self.messages),
            "filled_slots": list(self.current_state.keys()),
            "domain": self.prompt_manager.domain,
        }
