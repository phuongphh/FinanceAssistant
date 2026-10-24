# Phase 3.5 — Intent Understanding Layer (Chi Tiết Triển Khai)

> **Đây là phase mới được add giữa 3A và 3B sau khi phát hiện gap critical về free-form text handling.**
> Phase này biến Bé Tiền từ "menu app có chat skin" thành "trợ lý hiểu user thật sự".

> **Thời gian ước tính:** 2-3 tuần  
> **Mục tiêu cuối Phase:** Bé Tiền hiểu được 80%+ free-form text queries của user, response chính xác hoặc clarify thông minh khi không chắc, **không bao giờ "không hiểu, mở menu"**.  
> **Điều kiện "Done":** User test gửi 20 queries thực tế → Bé Tiền respond đúng ≥17 queries (85%). Còn lại phải có clarifying question hoặc polite decline (không silent fail).

> **Prerequisites:** Phase 3A đã ship + có data thực (assets, transactions). Phase 3.5 không tự create data, chỉ query.

---

## 🎯 Triết Lý Thiết Kế Phase 3.5

Đây là 4 nguyên lý quan trọng nhất, đọc kỹ trước khi code:

### 1. "Tier C — Cheapest Compute First"
- 75% queries match được rule-based (không cần LLM)
- 20% queries cần LLM classifier rẻ (~150 tokens)
- 5% queries cần LLM reasoning (advisory)
- **Mục tiêu:** Cost <$5/month cho 1000 queries/ngày

### 2. "Ask, Don't Guess"
- Confidence <0.5 → ask clarifying question
- Confidence 0.5-0.8 → confirm before execute
- Confidence >0.8 → execute
- **Trong finance, sai = nguy hiểm.** Better to ask twice than execute wrong.

### 3. "Out of Scope Polite Decline"
- Nếu query thực sự out of scope → say so warmly
- Không cố pretend hiểu
- Suggest alternative nếu có
- Example: *"Mình chưa biết về chứng khoán Mỹ, nhưng có thể giúp anh với chứng khoán VN. Anh muốn xem portfolio không?"*

### 4. "Personality Preserved"
- Bé Tiền tone (xưng "mình", warm, không robotic)
- Wealth-level adaptive responses (Starter vs HNW khác nhau)
- Memory-aware (gọi tên, reference history)

---

## 📅 Phân Bổ Thời Gian 3 Tuần

| Tuần | Nội dung | Deliverable |
|------|----------|-------------|
| **Tuần 1** | Pattern matching + Action handlers (Read queries) | Bé Tiền trả lời được 6 read intents bằng rule-based |
| **Tuần 2** | LLM classifier + Clarification flow | Cover ambiguous queries, ask khi không chắc |
| **Tuần 3** | Personality polish + Advisory queries + Testing | Wealth-aware responses, edge cases, user testing |

---

## 🗂️ Cấu Trúc Thư Mục Mở Rộng

```
finance_assistant/
├── app/
│   ├── intent/                          # ⭐ NEW - Core của Phase 3.5
│   │   ├── __init__.py
│   │   ├── classifier/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                  # IntentClassifier interface
│   │   │   ├── rule_based.py            # Layer 1 — pattern matching
│   │   │   ├── llm_based.py             # Layer 2 — LLM fallback
│   │   │   └── pipeline.py              # Combine both
│   │   ├── extractors/
│   │   │   ├── __init__.py
│   │   │   ├── time_range.py            # "tháng này", "tuần trước"
│   │   │   ├── category.py              # "ăn uống", "sức khỏe"
│   │   │   ├── ticker.py                # "VNM", "VIC"
│   │   │   ├── amount.py                # Reuse từ Phase 3A
│   │   │   └── goal_name.py             # "mua xe", "mua nhà"
│   │   ├── handlers/                    # Layer 4 — action handlers
│   │   │   ├── __init__.py
│   │   │   ├── base.py                  # IntentHandler interface
│   │   │   ├── query_assets.py
│   │   │   ├── query_expenses.py
│   │   │   ├── query_income.py
│   │   │   ├── query_market.py
│   │   │   ├── query_goals.py
│   │   │   ├── advisory.py              # Layer 4 special
│   │   │   └── out_of_scope.py
│   │   ├── dispatcher.py                # Layer 3 — confidence routing
│   │   └── intents.py                   # IntentType enum
│   │
│   ├── bot/
│   │   ├── handlers/
│   │   │   └── free_form_text.py        # ⭐ NEW - main entry point
│   │   ├── formatters/
│   │   │   └── query_response.py        # ⭐ NEW - Layer 5 composer
│   │   └── personality/
│   │       └── query_voice.py           # ⭐ NEW - Bé Tiền tone for queries
│   │
│   └── ...
│
├── content/
│   ├── intent_patterns.yaml             # ⭐ NEW - Layer 1 patterns
│   ├── clarification_messages.yaml      # ⭐ NEW
│   └── out_of_scope_responses.yaml      # ⭐ NEW
│
└── tests/
    ├── test_intent/
    │   ├── test_rule_based.py
    │   ├── test_extractors.py
    │   ├── test_dispatcher.py
    │   └── fixtures/
    │       └── query_examples.yaml      # Test cases tiếng Việt
    └── ...
```

---

# 🎯 TUẦN 1: Pattern Matching + Read Query Handlers

## 1.1 — Định Nghĩa Intent Types

### File: `app/intent/intents.py`

```python
"""
Định nghĩa các intents Bé Tiền có thể handle.
Phase 3.5 covers READ + simple ACTION intents.
Phase 4+ sẽ add advisory + complex intents.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class IntentType(str, Enum):
    # ===== Read intents (Phase 3.5 core) =====
    QUERY_ASSETS = "query_assets"              # "tài sản của tôi có gì"
    QUERY_NET_WORTH = "query_net_worth"        # "tổng tài sản tôi bao nhiêu"
    QUERY_PORTFOLIO = "query_portfolio"        # "portfolios chứng khoán có gì"
    
    QUERY_EXPENSES = "query_expenses"          # "chi tiêu tháng này"
    QUERY_EXPENSES_BY_CATEGORY = "query_expenses_by_category"  # "chi sức khỏe tháng này"
    QUERY_INCOME = "query_income"              # "thu nhập của tôi"
    QUERY_CASHFLOW = "query_cashflow"          # "tháng này dư bao nhiêu"
    
    QUERY_MARKET = "query_market"              # "VNM giá bao nhiêu"
    QUERY_GOALS = "query_goals"                # "mục tiêu của tôi có gì"
    QUERY_GOAL_PROGRESS = "query_goal_progress"  # "mua xe cần bao nhiêu nữa"
    
    # ===== Action intents (Phase 3.5 simple) =====
    ACTION_RECORD_SAVING = "action_record_saving"  # "tiết kiệm 1tr"
    ACTION_QUICK_TRANSACTION = "action_quick_transaction"  # "vừa chi 200k ăn"
    
    # ===== Advanced intents (Phase 3.5 routes to LLM) =====
    ADVISORY = "advisory"                      # "nên đầu tư gì"
    PLANNING = "planning"                      # "muốn mua xe cần làm gì"
    
    # ===== Meta intents =====
    GREETING = "greeting"                      # "chào", "hi"
    HELP = "help"                              # "giúp tôi", "/help"
    UNCLEAR = "unclear"                        # Không classify được
    OUT_OF_SCOPE = "out_of_scope"             # Ngoài khả năng


@dataclass
class IntentResult:
    """Kết quả của intent classification."""
    intent: IntentType
    confidence: float  # 0.0 - 1.0
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    classifier_used: str = ""  # "rule" | "llm"
    needs_clarification: bool = False
    clarification_question: str | None = None
```

---

## 1.2 — Pattern Matching Engine

### File: `content/intent_patterns.yaml`

**Đây là file QUAN TRỌNG NHẤT của tuần 1.** Bao phủ 70-75% queries.

```yaml
# Vietnamese intent patterns
# Format: each intent has 'patterns' (regex) and 'parameter_extractors'
# Patterns are checked top-to-bottom; first match wins.

query_assets:
  description: "User asks about their assets"
  patterns:
    # "tài sản của tôi có gì"
    - pattern: "tài sản.*(?:của (?:tôi|mình)|tôi có).*?(?:gì|nào|những)"
      confidence: 0.95
    # "tôi có tài sản gì"
    - pattern: "(?:tôi|mình)\\s+có.*tài sản.*(?:gì|nào)"
      confidence: 0.95
    # "asset của tôi"
    - pattern: "asset.*?(?:của (?:tôi|mình)|tôi có)"
      confidence: 0.9
    # "tôi đang có những gì"
    - pattern: "(?:tôi|mình).*đang có.*(?:gì|nào|những)"
      confidence: 0.7  # Lower - có thể ambiguous
  parameter_extractors:
    asset_type:
      patterns:
        - { match: "bất động sản|bds|nhà|đất", value: "real_estate" }
        - { match: "chứng khoán|cổ phiếu|stock", value: "stock" }
        - { match: "crypto|tiền số|btc|bitcoin", value: "crypto" }
        - { match: "vàng|gold", value: "gold" }
        - { match: "tiền mặt|tiền|cash", value: "cash" }

query_net_worth:
  description: "User asks total net worth"
  patterns:
    - pattern: "tổng (?:tài sản|asset|net worth)"
      confidence: 0.95
    - pattern: "(?:tài sản|asset).*?tổng"
      confidence: 0.9
    - pattern: "(?:tôi|mình).*có\\s+(?:tổng cộng|tất cả).*bao nhiêu"
      confidence: 0.85
    - pattern: "net worth"
      confidence: 0.95

query_portfolio:
  description: "User asks about stock portfolio"
  patterns:
    - pattern: "portfolios?.*chứng khoán"
      confidence: 0.95
    - pattern: "danh mục.*(?:chứng khoán|cổ phiếu|đầu tư)"
      confidence: 0.95
    - pattern: "(?:chứng khoán|cổ phiếu|stocks?).*(?:của (?:tôi|mình)|tôi (?:có|đang))"
      confidence: 0.9
    - pattern: "(?:những|các) mã.*(?:nào|gì)"
      confidence: 0.85

query_expenses:
  description: "User asks about expenses (general)"
  patterns:
    - pattern: "chi (?:tiêu|phí).*(?:tháng|tuần|năm)"
      confidence: 0.9
    - pattern: "(?:tôi|mình).*(?:đã )?(?:chi|tiêu).*(?:tháng|tuần)"
      confidence: 0.9
    - pattern: "tiêu bao nhiêu"
      confidence: 0.85
  parameter_extractors:
    time_range:
      use_extractor: "time_range"  # Sẽ implement riêng

query_expenses_by_category:
  description: "User asks about expenses in specific category"
  patterns:
    # "chi tiêu cho sức khỏe tháng này"
    - pattern: "chi (?:tiêu|phí).*(?:cho|về).*?(?P<category>\\w+).*(?:tháng|tuần|năm)"
      confidence: 0.95
    # "liệt kê chi phí ăn uống tháng này"
    - pattern: "(?:liệt kê|list|xem).*chi (?:phí|tiêu).*?(?P<category>\\w+)"
      confidence: 0.95
    # "tháng này tôi tiêu cho ăn uống bao nhiêu"
    - pattern: "(?:tháng|tuần) (?:này|trước|qua).*(?:tiêu|chi).*?(?P<category>\\w+)"
      confidence: 0.9
  parameter_extractors:
    category:
      use_extractor: "category"
    time_range:
      use_extractor: "time_range"

query_income:
  description: "User asks about income"
  patterns:
    - pattern: "thu nhập.*(?:của (?:tôi|mình)|tôi)"
      confidence: 0.95
    - pattern: "(?:tôi|mình).*kiếm được.*bao nhiêu"
      confidence: 0.85
    - pattern: "lương.*(?:tôi|mình)"
      confidence: 0.9

query_cashflow:
  description: "User asks net cashflow"
  patterns:
    - pattern: "(?:tháng|tuần) (?:này|trước|qua).*(?:dư|còn lại|tiết kiệm được)"
      confidence: 0.9
    - pattern: "dòng tiền"
      confidence: 0.95
    - pattern: "tiết kiệm.*(?:tháng|tuần) (?:này|trước|qua)"
      confidence: 0.85

query_market:
  description: "User asks about market price"
  patterns:
    # "VNM giá bao nhiêu" 
    - pattern: "(?P<ticker>[A-Z]{2,5})\\s*(?:giá|hôm nay|hiện tại)"
      confidence: 0.95
    # "giá VNM"
    - pattern: "giá\\s+(?P<ticker>[A-Z]{2,5})"
      confidence: 0.95
    # "VN-Index hôm nay"
    - pattern: "vn[\\s-]?index"
      confidence: 0.95
    # "BTC giá"
    - pattern: "(?:btc|bitcoin|eth|ethereum).*giá"
      confidence: 0.9
  parameter_extractors:
    ticker:
      use_extractor: "ticker"

query_goals:
  description: "User asks about their goals"
  patterns:
    - pattern: "mục tiêu.*(?:của (?:tôi|mình)|tôi)"
      confidence: 0.95
    - pattern: "(?:tôi|mình).*đặt.*mục tiêu"
      confidence: 0.9
    - pattern: "goals?.*(?:của (?:tôi|mình)|tôi)"
      confidence: 0.95

query_goal_progress:
  description: "User asks about progress toward specific goal"
  patterns:
    # "muốn đạt được X cần làm gì"
    - pattern: "(?:muốn|để) (?:đạt được|có được|mua được|làm được).*?(?P<goal>.+?).*(?:cần|phải).*(?:làm gì|làm sao|như thế nào)"
      confidence: 0.95
    # "X cần bao nhiêu nữa"
    - pattern: "(?:còn|cần).*(?:bao nhiêu|bao lâu).*?(?P<goal>.+)"
      confidence: 0.7  # Lower - dễ ambiguous
  parameter_extractors:
    goal_name:
      use_extractor: "goal_name"

action_record_saving:
  description: "User wants to record a saving"
  patterns:
    # "tiết kiệm 1tr" — note: cần distinguish với report ("đã tiết kiệm")
    - pattern: "^tiết kiệm\\s+(?P<amount>\\d+(?:tr|k|triệu|nghìn|ngàn)?)\\s*$"
      confidence: 0.85  # Slightly lower vì ambiguous
    - pattern: "(?:gửi|chuyển|để dành|cất).*(?:tiết kiệm|saving).*?(?P<amount>\\d+(?:tr|k|triệu)?)"
      confidence: 0.9
  parameter_extractors:
    amount:
      use_extractor: "amount"

advisory:
  description: "User asks for investment/financial advice"
  patterns:
    - pattern: "nên (?:đầu tư|mua) (?:gì|cái nào|cổ phiếu nào)"
      confidence: 0.9
    - pattern: "làm thế nào để (?:đầu tư|tiết kiệm|kiếm thêm)"
      confidence: 0.9
    - pattern: "có thể mua gì"
      confidence: 0.8
    - pattern: "đầu tư.*(?:tiếp|thêm|nữa)"
      confidence: 0.85

greeting:
  patterns:
    - pattern: "^(?:chào|hi|hello|xin chào|hey)\\b"
      confidence: 0.95

help:
  patterns:
    - pattern: "(?:giúp|help|hướng dẫn).*(?:tôi|mình)"
      confidence: 0.9
    - pattern: "^/help$"
      confidence: 1.0
    - pattern: "không biết.*(?:làm sao|như thế nào|gì)"
      confidence: 0.7
```

### File: `app/intent/classifier/rule_based.py`

```python
"""
Rule-based classifier — Layer 1.
Match patterns YAML, NO LLM CALL.
"""

import re
import yaml
from pathlib import Path
from app.intent.intents import IntentType, IntentResult
from app.intent.extractors import time_range, category, ticker, amount


class RuleBasedClassifier:
    def __init__(self, patterns_file: str = "content/intent_patterns.yaml"):
        self._patterns = self._load_patterns(patterns_file)
    
    def _load_patterns(self, path: str) -> dict:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def classify(self, text: str) -> IntentResult | None:
        """
        Try to match text against all patterns.
        Return first match (highest confidence per intent).
        Return None if no match — caller should escalate to LLM.
        """
        text_lower = text.lower().strip()
        
        best_match = None
        best_confidence = 0.0
        
        for intent_name, intent_config in self._patterns.items():
            patterns = intent_config.get("patterns", [])
            
            for pattern_def in patterns:
                regex = pattern_def["pattern"]
                confidence = pattern_def["confidence"]
                
                match = re.search(regex, text_lower, re.IGNORECASE)
                if match and confidence > best_confidence:
                    # Extract parameters
                    params = self._extract_parameters(
                        text_lower,
                        match,
                        intent_config.get("parameter_extractors", {}),
                    )
                    
                    best_match = IntentResult(
                        intent=IntentType(intent_name),
                        confidence=confidence,
                        parameters=params,
                        raw_text=text,
                        classifier_used="rule",
                    )
                    best_confidence = confidence
        
        return best_match
    
    def _extract_parameters(
        self,
        text: str,
        match: re.Match,
        extractor_config: dict,
    ) -> dict:
        """Extract structured parameters from matched text."""
        params = {}
        
        # First: get named groups from regex
        params.update({k: v for k, v in match.groupdict().items() if v})
        
        # Second: run extractors
        for param_name, config in extractor_config.items():
            if "use_extractor" in config:
                extractor_name = config["use_extractor"]
                value = self._run_extractor(extractor_name, text)
                if value is not None:
                    params[param_name] = value
            elif "patterns" in config:
                # Inline pattern matching
                for p in config["patterns"]:
                    if re.search(p["match"], text, re.IGNORECASE):
                        params[param_name] = p["value"]
                        break
        
        return params
    
    def _run_extractor(self, extractor_name: str, text: str):
        extractors = {
            "time_range": time_range.extract,
            "category": category.extract,
            "ticker": ticker.extract,
            "amount": amount.extract,
        }
        if extractor_name in extractors:
            return extractors[extractor_name](text)
        return None
```

---

## 1.3 — Parameter Extractors

### File: `app/intent/extractors/time_range.py`

```python
"""
Extract time range from Vietnamese text.
"""

from datetime import date, timedelta
from dataclasses import dataclass


@dataclass
class TimeRange:
    start: date
    end: date
    label: str  # Human-readable


def extract(text: str) -> TimeRange | None:
    text = text.lower()
    today = date.today()
    
    # "hôm nay"
    if "hôm nay" in text:
        return TimeRange(today, today, "hôm nay")
    
    # "hôm qua"
    if "hôm qua" in text:
        d = today - timedelta(days=1)
        return TimeRange(d, d, "hôm qua")
    
    # "tuần này"
    if "tuần này" in text:
        start = today - timedelta(days=today.weekday())
        return TimeRange(start, today, "tuần này")
    
    # "tuần trước" / "tuần qua"
    if "tuần trước" in text or "tuần qua" in text:
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        return TimeRange(start, end, "tuần trước")
    
    # "tháng này"
    if "tháng này" in text:
        start = today.replace(day=1)
        return TimeRange(start, today, "tháng này")
    
    # "tháng trước" / "tháng qua"
    if "tháng trước" in text or "tháng qua" in text:
        if today.month == 1:
            start = date(today.year - 1, 12, 1)
            end = date(today.year - 1, 12, 31)
        else:
            start = date(today.year, today.month - 1, 1)
            # Last day of previous month
            end = today.replace(day=1) - timedelta(days=1)
        return TimeRange(start, end, "tháng trước")
    
    # "năm nay"
    if "năm nay" in text:
        start = date(today.year, 1, 1)
        return TimeRange(start, today, "năm nay")
    
    # Default: tháng này
    if any(kw in text for kw in ["chi tiêu", "chi phí", "tiêu"]):
        start = today.replace(day=1)
        return TimeRange(start, today, "tháng này")
    
    return None
```

### File: `app/intent/extractors/category.py`

```python
"""
Extract spending category from Vietnamese text.
"""

# Keyword → category mapping (Vietnamese-first)
CATEGORY_KEYWORDS = {
    "food": [
        "ăn uống", "ăn", "uống", "đồ ăn", "thức ăn", "nhà hàng",
        "cafe", "café", "cà phê", "phở", "cơm", "trà sữa",
        "ẩm thực", "food",
    ],
    "transport": [
        "di chuyển", "đi lại", "xăng", "grab", "taxi", "xe",
        "xe ôm", "transport", "transportation",
    ],
    "housing": [
        "nhà cửa", "nhà ở", "tiền nhà", "thuê nhà", "điện",
        "nước", "wifi", "internet", "housing",
    ],
    "shopping": [
        "mua sắm", "mua đồ", "quần áo", "shopping", "đồ dùng",
    ],
    "health": [
        "sức khỏe", "y tế", "bác sĩ", "bệnh viện", "thuốc",
        "khám bệnh", "health", "medical",
    ],
    "education": [
        "giáo dục", "học", "học phí", "sách", "khóa học",
        "education", "course",
    ],
    "entertainment": [
        "giải trí", "phim", "game", "du lịch", "vui chơi",
        "entertainment",
    ],
    "utility": [
        "tiện ích", "điện thoại", "subscription", "netflix",
        "spotify", "utility",
    ],
    "gift": [
        "quà", "tặng", "biếu", "lì xì", "mừng", "gift",
    ],
    "investment": [
        "đầu tư", "investment", "investing",
    ],
}


def extract(text: str) -> str | None:
    """
    Find category keyword in text. Return category code or None.
    Returns first match found.
    """
    text_lower = text.lower()
    
    for category_code, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category_code
    
    return None
```

### File: `app/intent/extractors/ticker.py`

```python
"""
Extract stock ticker from Vietnamese text.
"""

import re

# Common VN tickers (whitelist để tránh false positive với english words)
VN_TICKERS = {
    # VN30 popular
    "VNM", "VIC", "VHM", "VRE", "VCB", "TCB", "MBB", "ACB", "VPB",
    "BID", "CTG", "STB", "HPG", "HSG", "MWG", "MSN", "FPT", "PNJ",
    "REE", "GAS", "PLX", "POW", "SAB", "BVH", "PDR", "NVL", "DGC",
    # ETFs
    "E1VFVN30", "FUEVFVND", "FUESSV30", "FUESSVFL",
}

# Crypto tickers
CRYPTO_TICKERS = {
    "BTC", "ETH", "BNB", "USDT", "USDC", "SOL", "ADA",
    "DOT", "DOGE", "MATIC", "AVAX", "LINK",
}


def extract(text: str) -> str | None:
    """
    Find ticker in text. Match whitelist to avoid false positives.
    """
    text_upper = text.upper()
    
    # Look for 2-5 uppercase letters
    candidates = re.findall(r"\b[A-Z]{2,5}\b", text_upper)
    
    for candidate in candidates:
        if candidate in VN_TICKERS or candidate in CRYPTO_TICKERS:
            return candidate
    
    # Special handling: VN-Index variations
    if re.search(r"vn[\s-]?index", text, re.IGNORECASE):
        return "VNINDEX"
    
    # Bitcoin Vietnamese
    if "bitcoin" in text.lower():
        return "BTC"
    if "ethereum" in text.lower():
        return "ETH"
    
    return None
```

### File: `app/intent/extractors/amount.py`

Reuse từ Phase 3A (`parse_transaction_text` đã có), wrap thành function dedicated:

```python
"""Extract amount in VND from text."""
import re


def extract(text: str) -> int | None:
    """
    Parse Vietnamese amount expressions.
    "1tr" → 1000000, "500k" → 500000, "2 triệu" → 2000000
    """
    # Patterns ordered by specificity
    patterns = [
        (r"(\d+(?:\.\d+)?)\s*(?:tr|triệu|trieu)\b", 1_000_000),
        (r"(\d+(?:\.\d+)?)\s*(?:k|nghìn|nghin|ngàn|ngan)\b", 1_000),
        (r"(\d+(?:\.\d+)?)\s*tỷ\b", 1_000_000_000),
        (r"\b(\d{4,})\b", 1),  # Plain number ≥ 1000
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            return int(value * multiplier)
    
    return None
```

---

## 1.4 — Action Handlers (Layer 4)

### File: `app/intent/handlers/base.py`

```python
"""Base interface cho intent handlers."""

from abc import ABC, abstractmethod
from app.intent.intents import IntentResult


class IntentHandler(ABC):
    @abstractmethod
    async def handle(self, intent: IntentResult, user) -> str:
        """
        Execute handler logic.
        Return formatted response string ready to send Telegram.
        """
        pass
```

### File: `app/intent/handlers/query_assets.py`

```python
"""Handle 'query_assets' intent."""

from app.intent.handlers.base import IntentHandler
from app.intent.intents import IntentResult
from app.wealth.services.asset_service import AssetService
from app.bot.formatters.money import format_money_short, format_money_full


class QueryAssetsHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user) -> str:
        asset_service = AssetService()
        
        # Filter by type if specified
        asset_type_filter = intent.parameters.get("asset_type")
        
        all_assets = await asset_service.get_user_assets(user.id)
        
        if not all_assets:
            return self._empty_state(user)
        
        if asset_type_filter:
            filtered = [a for a in all_assets if a.asset_type == asset_type_filter]
            if not filtered:
                return self._no_match_for_type(asset_type_filter, user)
            return self._format_filtered(filtered, asset_type_filter, user)
        
        return self._format_all(all_assets, user)
    
    def _empty_state(self, user) -> str:
        name = user.display_name or "bạn"
        return (
            f"💎 {name} chưa thêm tài sản nào cả!\n\n"
            "Mình giúp bạn track tài sản — tiền mặt, chứng khoán, BĐS, vàng...\n"
            "Tap vào /add_asset để bắt đầu nhé 🚀"
        )
    
    def _format_all(self, assets, user) -> str:
        from app.wealth.services.net_worth_calculator import NetWorthCalculator
        from app.wealth.models.asset_types import ASSET_CATEGORIES
        
        # Group by type
        by_type = {}
        total = 0
        for asset in assets:
            by_type.setdefault(asset.asset_type, []).append(asset)
            total += float(asset.current_value)
        
        name = user.display_name or "bạn"
        lines = [
            f"💎 Tài sản hiện tại của {name}:",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"Tổng: **{format_money_full(total)}**",
            "",
        ]
        
        for asset_type, items in sorted(
            by_type.items(),
            key=lambda x: sum(float(a.current_value) for a in x[1]),
            reverse=True,
        ):
            config = ASSET_CATEGORIES["asset_types"].get(asset_type, {})
            icon = config.get("icon", "📌")
            label = config.get("label_vi", asset_type)
            
            type_total = sum(float(a.current_value) for a in items)
            lines.append(f"{icon} **{label}** — {format_money_short(type_total)}")
            
            for asset in items[:3]:  # Top 3 per category
                lines.append(f"   • {asset.name}: {format_money_short(asset.current_value)}")
            
            if len(items) > 3:
                lines.append(f"   _...và {len(items) - 3} mục nữa_")
            lines.append("")
        
        # Add suggestion (Bé Tiền personality)
        lines.append("Muốn xem chi tiết phần nào? Hỏi mình nhé 😊")
        
        return "\n".join(lines)
    
    def _format_filtered(self, assets, asset_type: str, user) -> str:
        # Similar logic but only one type
        # ... implementation
        pass
    
    def _no_match_for_type(self, asset_type: str, user) -> str:
        from app.wealth.models.asset_types import ASSET_CATEGORIES
        config = ASSET_CATEGORIES["asset_types"].get(asset_type, {})
        label = config.get("label_vi", asset_type)
        
        name = user.display_name or "bạn"
        return (
            f"{name} chưa có {label} nào cả 🤔\n\n"
            "Mình có thể giúp bạn thêm vào không? Tap /add_asset"
        )
```

### File: `app/intent/handlers/query_expenses.py`

```python
"""Handle expense queries."""

from app.intent.handlers.base import IntentHandler
from app.intent.intents import IntentResult
from app.services.transaction_service import TransactionService
from app.bot.formatters.money import format_money_short, format_money_full


class QueryExpensesHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user) -> str:
        tx_service = TransactionService()
        
        time_range = intent.parameters.get("time_range")
        category = intent.parameters.get("category")
        
        if not time_range:
            # Default to current month
            from app.intent.extractors.time_range import extract
            time_range = extract("tháng này")
        
        # Query
        if category:
            transactions = await tx_service.get_by_category_and_date_range(
                user_id=user.id,
                category=category,
                start_date=time_range.start,
                end_date=time_range.end,
            )
        else:
            transactions = await tx_service.get_by_date_range(
                user_id=user.id,
                start_date=time_range.start,
                end_date=time_range.end,
            )
        
        if not transactions:
            return self._empty(time_range, category, user)
        
        return self._format(transactions, time_range, category, user)
    
    def _format(self, transactions, time_range, category, user):
        total = sum(float(tx.amount) for tx in transactions)
        count = len(transactions)
        
        from app.config.categories import get_category
        
        if category:
            cat_obj = get_category(category)
            header = f"💸 Chi {cat_obj.emoji} **{cat_obj.name_vi}** {time_range.label}:"
        else:
            header = f"💸 Chi tiêu {time_range.label}:"
        
        lines = [
            header,
            f"━━━━━━━━━━━━━━━━━━━━",
            f"Tổng: **{format_money_full(total)}** ({count} giao dịch)",
            "",
        ]
        
        # Show top 10 transactions
        for tx in sorted(transactions, key=lambda x: x.amount, reverse=True)[:10]:
            cat_obj = get_category(tx.category)
            lines.append(
                f"{cat_obj.emoji} {tx.merchant or 'N/A'} — {format_money_short(tx.amount)}"
            )
        
        if count > 10:
            lines.append(f"\n_...và {count - 10} giao dịch nhỏ hơn_")
        
        return "\n".join(lines)
    
    def _empty(self, time_range, category, user):
        name = user.display_name or "bạn"
        if category:
            from app.config.categories import get_category
            cat_obj = get_category(category)
            return f"{name} không có chi tiêu cho {cat_obj.emoji} {cat_obj.name_vi} {time_range.label} 🌱"
        return f"{name} không có chi tiêu nào {time_range.label}!"
```

### File: `app/intent/handlers/query_market.py`

```python
"""Handle market price queries."""

from app.intent.handlers.base import IntentHandler
from app.intent.intents import IntentResult
from app.services.market_service import MarketService


class QueryMarketHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user) -> str:
        ticker = intent.parameters.get("ticker")
        
        if not ticker:
            return "Bạn muốn xem giá mã nào? Ví dụ: VNM, VIC, BTC..."
        
        market_service = MarketService()
        
        try:
            price_info = await market_service.get_current_price(ticker)
        except Exception as e:
            return (
                f"Mình không lấy được giá {ticker} lúc này 😔\n"
                "Có thể thử lại sau vài phút nhé!"
            )
        
        if not price_info:
            return (
                f"Mình chưa biết về mã **{ticker}** 🤔\n"
                "Bạn check lại tên mã xem? Hoặc gõ /help xem các mã mình hỗ trợ."
            )
        
        # Format response based on ticker type
        change_emoji = "📈" if price_info.change_pct >= 0 else "📉"
        change_sign = "+" if price_info.change_pct >= 0 else ""
        
        lines = [
            f"📊 **{ticker}** hôm nay:",
            f"Giá: {price_info.price:,.0f}đ",
            f"{change_emoji} {change_sign}{price_info.change_pct:.2f}% so với hôm qua",
        ]
        
        # Check if user owns this — add personal context
        from app.wealth.services.asset_service import AssetService
        asset_service = AssetService()
        owned = await asset_service.find_by_ticker(user.id, ticker)
        
        if owned:
            quantity = owned.metadata.get("quantity", 0)
            current_value = price_info.price * quantity
            lines.extend([
                "",
                f"_Bạn đang sở hữu **{quantity:,} {ticker}**_",
                f"_Giá trị hiện tại: {current_value:,.0f}đ_",
            ])
        
        return "\n".join(lines)
```

### Other handlers (skeletons)

- `query_income.py` — query IncomeStreams, sum, format
- `query_net_worth.py` — call NetWorthCalculator
- `query_portfolio.py` — filter assets by type=stock
- `query_goals.py` — list goals
- `query_cashflow.py` — net cashflow của period

---

## 1.5 — Pipeline & Free-Form Handler

### File: `app/intent/classifier/pipeline.py`

```python
"""
Intent classification pipeline.
Layer 1 (rule) first, Layer 2 (LLM) fallback.
"""

from app.intent.classifier.rule_based import RuleBasedClassifier
from app.intent.intents import IntentResult, IntentType


class IntentPipeline:
    def __init__(self):
        self.rule_classifier = RuleBasedClassifier()
        # Layer 2 (LLM) sẽ implement ở Tuần 2
        self.llm_classifier = None
    
    async def classify(self, text: str) -> IntentResult:
        """
        Main entry. Try rule-based first.
        If no match (or low confidence), escalate to LLM (Tuần 2).
        """
        # Layer 1
        rule_result = self.rule_classifier.classify(text)
        
        if rule_result and rule_result.confidence >= 0.85:
            return rule_result
        
        # Layer 2 — LLM fallback (Tuần 2)
        if self.llm_classifier:
            llm_result = await self.llm_classifier.classify(text)
            if llm_result:
                return llm_result
        
        # Fallback: lower-confidence rule match if exists, else UNCLEAR
        if rule_result:
            return rule_result
        
        return IntentResult(
            intent=IntentType.UNCLEAR,
            confidence=0.0,
            raw_text=text,
            classifier_used="none",
        )
```

### File: `app/bot/handlers/free_form_text.py`

```python
"""
Main entry point cho free-form text từ user.
Routes to intent classification → handler → response.
"""

from telegram import Update
from telegram.ext import ContextTypes

from app.intent.classifier.pipeline import IntentPipeline
from app.intent.dispatcher import IntentDispatcher
from app.services.user_service import UserService


# Singleton (load once)
_pipeline = IntentPipeline()
_dispatcher = IntentDispatcher()


async def handle_free_form_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Called when user sends text NOT in:
    - Active wizard
    - Storytelling mode
    - Command (/...)
    """
    text = update.message.text
    user_id = update.effective_user.id
    
    user_service = UserService()
    user = await user_service.get_by_telegram_id(user_id)
    
    # Step 1: Classify intent
    intent_result = await _pipeline.classify(text)
    
    # Step 2: Dispatch to handler
    response = await _dispatcher.dispatch(intent_result, user)
    
    # Step 3: Send response
    await update.message.reply_text(response, parse_mode="Markdown")
    
    # Step 4: Track for analytics
    from app.analytics import track, Event
    from datetime import datetime
    await track(Event(
        user_id=user.id,
        event_type="intent_handled",
        properties={
            "intent": intent_result.intent.value,
            "confidence": intent_result.confidence,
            "classifier": intent_result.classifier_used,
        },
        timestamp=datetime.utcnow(),
    ))
```

### File: `app/intent/dispatcher.py`

```python
"""
Layer 3: Confidence-based dispatcher.
"""

from app.intent.intents import IntentType, IntentResult


class IntentDispatcher:
    def __init__(self):
        from app.intent.handlers.query_assets import QueryAssetsHandler
        from app.intent.handlers.query_expenses import QueryExpensesHandler
        from app.intent.handlers.query_market import QueryMarketHandler
        # ... import all handlers
        
        self.handlers = {
            IntentType.QUERY_ASSETS: QueryAssetsHandler(),
            IntentType.QUERY_EXPENSES: QueryExpensesHandler(),
            IntentType.QUERY_EXPENSES_BY_CATEGORY: QueryExpensesHandler(),
            IntentType.QUERY_MARKET: QueryMarketHandler(),
            # ... map all
        }
    
    async def dispatch(self, intent_result: IntentResult, user) -> str:
        # Confidence-based routing
        if intent_result.intent == IntentType.UNCLEAR:
            return self._unclear_response(user)
        
        if intent_result.intent == IntentType.OUT_OF_SCOPE:
            return self._out_of_scope_response(intent_result.raw_text, user)
        
        if intent_result.confidence < 0.5:
            return await self._ask_clarification(intent_result, user)
        
        if 0.5 <= intent_result.confidence < 0.8:
            return await self._confirm_then_execute(intent_result, user)
        
        # confidence >= 0.8: execute
        handler = self.handlers.get(intent_result.intent)
        if not handler:
            return self._not_implemented_response(intent_result, user)
        
        try:
            return await handler.handle(intent_result, user)
        except Exception as e:
            print(f"Handler error: {e}")
            return self._error_response(user)
    
    def _unclear_response(self, user) -> str:
        name = user.display_name or "bạn"
        return (
            f"Mình chưa hiểu lắm {name} ơi 🤔\n\n"
            "Bạn có thể hỏi:\n"
            "• 'Tài sản của tôi có gì?'\n"
            "• 'Chi tiêu tháng này?'\n"
            "• 'VNM giá bao nhiêu?'\n\n"
            "Hoặc gõ /help để xem đầy đủ"
        )
    
    def _out_of_scope_response(self, text, user) -> str:
        name = user.display_name or "bạn"
        return (
            f"Mình chưa biết trả lời câu này {name} ạ 😅\n\n"
            "Mình giúp được về: tài sản, chi tiêu, thu nhập, đầu tư VN, mục tiêu.\n"
            "Bạn thử hỏi cách khác xem?"
        )
    
    async def _ask_clarification(self, intent_result, user):
        # Tuần 2 sẽ implement đầy đủ
        return self._unclear_response(user)
    
    async def _confirm_then_execute(self, intent_result, user):
        # Tuần 2 sẽ implement
        # For now, just execute
        handler = self.handlers.get(intent_result.intent)
        if handler:
            return await handler.handle(intent_result, user)
        return self._not_implemented_response(intent_result, user)
    
    def _not_implemented_response(self, intent_result, user):
        return f"Mình hiểu bạn muốn {intent_result.intent.value}, nhưng tính năng này chưa sẵn sàng. Coming soon!"
    
    def _error_response(self, user):
        return "Có lỗi xảy ra. Bạn thử lại sau nhé!"
```

---

## 1.6 — Integration với Existing Bot Router

Update `app/bot/router.py` (or wherever main message handler lives):

```python
async def handle_text_message(update, context):
    user_id = update.effective_user.id
    user = await user_service.get_by_telegram_id(user_id)
    
    # Pre-filter: skip if in active flow
    if user.onboarding_step != OnboardingStep.COMPLETED:
        return await handle_onboarding_input(update, context)
    
    if context.user_data.get("storytelling_mode"):
        return await handle_storytelling_input(update, context)
    
    if context.user_data.get("asset_draft_step"):
        return await handle_asset_wizard_input(update, context)
    
    # ⭐ NEW: route free-form text qua intent pipeline
    from app.bot.handlers.free_form_text import handle_free_form_text
    return await handle_free_form_text(update, context)
```

---

## ✅ Checklist Cuối Tuần 1

- [ ] `app/intent/intents.py` với enum đầy đủ
- [ ] `content/intent_patterns.yaml` với ≥30 patterns
- [ ] `RuleBasedClassifier` hoạt động — test với 11 query examples của bạn
- [ ] 4 extractors: time_range, category, ticker, amount
- [ ] 6 handlers: query_assets, query_expenses, query_income, query_market, query_portfolio, query_net_worth
- [ ] `IntentPipeline` + `IntentDispatcher` skeleton
- [ ] Integration với existing bot router
- [ ] Test: 11 query examples → đúng intent ≥9/11 (82%+)
- [ ] No LLM calls in this week — pure rule-based

---

# 🤖 TUẦN 2: LLM Classifier + Clarification Flow

## 2.1 — LLM Classifier Setup

### File: `app/intent/classifier/llm_based.py`

```python
"""
LLM-based classifier — fallback khi rule-based fail.
Uses DeepSeek (cheapest option).
"""

import json
from openai import AsyncOpenAI
from app.config import settings
from app.intent.intents import IntentType, IntentResult


LLM_CLASSIFIER_PROMPT = """Bạn là intent classifier cho Bé Tiền — finance assistant.

Phân loại câu hỏi của user vào MỘT trong các intents sau:

INTENTS:
- query_assets: Hỏi về tài sản (BĐS, CK, crypto, vàng, tiền)
- query_net_worth: Hỏi tổng tài sản
- query_portfolio: Hỏi về danh mục chứng khoán
- query_expenses: Hỏi về chi tiêu
- query_expenses_by_category: Hỏi chi tiêu theo loại
- query_income: Hỏi về thu nhập
- query_cashflow: Hỏi dòng tiền
- query_market: Hỏi giá thị trường (VNM, BTC, etc.)
- query_goals: Hỏi mục tiêu của user
- query_goal_progress: Hỏi tiến độ mục tiêu cụ thể
- action_record_saving: Muốn ghi tiết kiệm
- action_quick_transaction: Muốn ghi giao dịch
- advisory: Hỏi lời khuyên đầu tư
- planning: Hỏi cách lập kế hoạch
- greeting: Chào hỏi
- help: Cần hướng dẫn
- out_of_scope: Hoàn toàn ngoài phạm vi (ví dụ: hỏi về thời tiết)

PARAMETERS (extract nếu có):
- time_range: "today" | "this_week" | "last_week" | "this_month" | "last_month" | "this_year"
- category: "food" | "transport" | "housing" | "shopping" | "health" | "education" | "entertainment" | "utility" | "gift" | "investment"
- asset_type: "cash" | "stock" | "real_estate" | "crypto" | "gold"
- ticker: e.g. "VNM", "BTC"
- amount: integer in VND
- goal_name: text

OUTPUT JSON ONLY:
{
  "intent": "intent_name",
  "confidence": 0.0-1.0,
  "parameters": {...}
}

USER QUERY: {query}

JSON:"""


class LLMClassifier:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1",
        )
    
    async def classify(self, text: str) -> IntentResult | None:
        prompt = LLM_CLASSIFIER_PROMPT.format(query=text)
        
        try:
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=200,
                temperature=0.0,  # Deterministic
            )
            
            result = json.loads(response.choices[0].message.content)
            
            intent_str = result.get("intent", "unclear")
            confidence = float(result.get("confidence", 0.0))
            parameters = result.get("parameters", {})
            
            try:
                intent = IntentType(intent_str)
            except ValueError:
                intent = IntentType.UNCLEAR
            
            return IntentResult(
                intent=intent,
                confidence=confidence,
                parameters=parameters,
                raw_text=text,
                classifier_used="llm",
            )
        except Exception as e:
            print(f"LLM classifier error: {e}")
            return None
```

---

## 2.2 — Clarification System

### File: `content/clarification_messages.yaml`

```yaml
# Clarification messages khi confidence trung bình
# Bot sẽ hỏi user thay vì execute bừa

low_confidence_assets:
  - |
    Mình hiểu bạn hỏi về tài sản, nhưng chưa rõ chi tiết...
    
    Bạn muốn:
    [📊 Xem tổng tài sản]
    [🏠 Chỉ BĐS]
    [📈 Chỉ chứng khoán]
    [💵 Chỉ tiền mặt]

low_confidence_expenses:
  - |
    Bạn muốn xem chi tiêu của period nào?
    [📅 Hôm nay]
    [📅 Tuần này]
    [📅 Tháng này]
    [📅 Tháng trước]

low_confidence_action:
  - |
    Bạn muốn:
    [💰 Ghi tiết kiệm]
    [📝 Ghi giao dịch]
    [🎯 Đặt mục tiêu]
    [Khác]

ambiguous_amount:
  - |
    Số tiền là {amount}đ đúng không? Bạn xác nhận giúp mình:
    [✅ Đúng rồi]
    [✏️ Sửa]

ambiguous_category:
  - |
    Bạn muốn xem chi tiêu cho category nào?
    {category_buttons}
```

### Implement clarification trong dispatcher

Update `app/intent/dispatcher.py`:

```python
async def _ask_clarification(self, intent_result, user):
    """When confidence < 0.5, ask user to disambiguate."""
    intent = intent_result.intent
    
    # Specific clarification per intent
    if intent in (IntentType.QUERY_ASSETS, IntentType.QUERY_NET_WORTH):
        return self._clarify_assets(user)
    elif intent in (IntentType.QUERY_EXPENSES, IntentType.QUERY_EXPENSES_BY_CATEGORY):
        return self._clarify_expenses(user)
    elif intent == IntentType.ACTION_RECORD_SAVING:
        return self._clarify_action(user)
    
    return self._unclear_response(user)


def _clarify_assets(self, user) -> str:
    """Send message với inline keyboard."""
    # Note: real implementation needs to send keyboard, not just text
    # For simplicity here, return text with options
    return self._load_clarification("low_confidence_assets")


async def _confirm_then_execute(self, intent_result, user):
    """When confidence 0.5-0.8, confirm before executing."""
    intent = intent_result.intent
    params = intent_result.parameters
    
    # For read intents, just execute (read is safe)
    read_intents = {
        IntentType.QUERY_ASSETS,
        IntentType.QUERY_NET_WORTH,
        IntentType.QUERY_EXPENSES,
        IntentType.QUERY_INCOME,
        IntentType.QUERY_MARKET,
        IntentType.QUERY_GOALS,
        IntentType.QUERY_PORTFOLIO,
        IntentType.QUERY_CASHFLOW,
    }
    
    if intent in read_intents:
        # Read is safe — just execute even at medium confidence
        handler = self.handlers.get(intent)
        if handler:
            return await handler.handle(intent_result, user)
    
    # For write intents, MUST confirm
    if intent in (IntentType.ACTION_RECORD_SAVING, IntentType.ACTION_QUICK_TRANSACTION):
        return self._build_confirmation(intent_result, user)
    
    return self._unclear_response(user)


def _build_confirmation(self, intent_result, user):
    """Build confirmation message with action summary."""
    if intent_result.intent == IntentType.ACTION_RECORD_SAVING:
        amount = intent_result.parameters.get("amount", 0)
        return (
            f"Mình hiểu bạn muốn ghi tiết kiệm **{amount:,}đ**.\n"
            "Đúng không?\n\n"
            "[✅ Đúng] [❌ Không phải]"
        )
    return self._unclear_response(user)
```

---

## 2.3 — Context-Aware Intent

Một số intents cần biết context của user. Ví dụ:
- "tài sản của tôi" cho user starter → đơn giản
- "tài sản của tôi" cho user HNW → detailed breakdown

Update handlers để wealth-level aware. Example:

```python
class QueryAssetsHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user) -> str:
        # ... fetch assets ...
        
        from app.wealth.ladder import detect_level, WealthLevel
        from app.wealth.services.net_worth_calculator import NetWorthCalculator
        
        net_worth = await NetWorthCalculator().calculate(user.id)
        level = detect_level(net_worth.total)
        
        if level == WealthLevel.STARTER:
            return self._format_simple(assets, user)
        elif level == WealthLevel.YOUNG_PROFESSIONAL:
            return self._format_with_growth(assets, user)
        elif level in (WealthLevel.MASS_AFFLUENT, WealthLevel.HIGH_NET_WORTH):
            return self._format_detailed(assets, user)
```

---

## ✅ Checklist Cuối Tuần 2

- [ ] `LLMClassifier` integrated trong pipeline
- [ ] LLM cost <$0.0005/query average
- [ ] Clarification messages trong YAML
- [ ] Dispatcher có 3 paths: execute / confirm / clarify / decline
- [ ] Read intents skip confirmation (always execute)
- [ ] Write intents MUST confirm
- [ ] Wealth-level aware responses
- [ ] Test với 30+ ambiguous queries

---

# 💝 TUẦN 3: Personality + Advisory + Testing

## 3.1 — Personality Layer

### File: `app/bot/personality/query_voice.py`

Make Bé Tiền sound like Bé Tiền, không generic AI:

```python
"""
Add Bé Tiền personality to query responses.
"""

import random


def add_personality(response: str, user, intent_type) -> str:
    """
    Wrap raw response with personality elements.
    """
    # Sometimes prepend warm greeting
    if random.random() < 0.3:
        greeting = _get_greeting(user)
        response = f"{greeting} {response}"
    
    # Sometimes append next-action suggestion
    if random.random() < 0.5:
        suggestion = _get_suggestion(intent_type, user)
        if suggestion:
            response = f"{response}\n\n{suggestion}"
    
    return response


def _get_greeting(user) -> str:
    name = user.display_name or "bạn"
    greetings = [
        f"{name} ơi,",
        f"Hiểu rồi {name}!",
        f"Cho mình check liền,",
    ]
    return random.choice(greetings)


def _get_suggestion(intent_type, user) -> str | None:
    suggestions_map = {
        "query_assets": [
            "Muốn xem chi tiết phần nào? 📊",
            "Mình có thể show trend 30 ngày nếu bạn muốn 📈",
        ],
        "query_expenses": [
            "Bạn muốn so sánh với tháng trước không? 📅",
            "Có muốn mình breakdown theo loại không? 🍕",
        ],
        "query_market": [
            "Muốn xem chi tiết phân tích không?",
            "Có thể giúp bạn check thêm mã khác 📊",
        ],
    }
    
    options = suggestions_map.get(intent_type)
    if options:
        return random.choice(options)
    return None
```

---

## 3.2 — Advisory Handler

Đây là Group 6 trong analysis ban đầu — câu hỏi cần reasoning:

### File: `app/intent/handlers/advisory.py`

```python
"""
Handle advisory queries (need LLM reasoning).
"""

from app.intent.handlers.base import IntentHandler


ADVISORY_PROMPT = """Bạn là Bé Tiền — trợ lý tài chính cá nhân thân thiện cho người Việt.

User vừa hỏi: "{query}"

Context về user:
- Tên: {name}
- Wealth level: {level}
- Tổng tài sản: {net_worth}
- Phân bổ: {breakdown}
- Thu nhập tháng: {income}
- Mục tiêu hiện tại: {goals}

NGUYÊN TẮC TRẢ LỜI:
1. Tone: ấm áp, xưng "mình", gọi "{name}" - "bạn"
2. Cụ thể: dựa trên context user, không generic advice
3. KHÔNG khuyên cổ phiếu cụ thể (lý do pháp lý)
4. KHÔNG hứa hẹn lợi nhuận
5. Đưa ra 2-3 options, để user chọn
6. Nếu cần thông tin thêm, hỏi lại

Trả lời ngắn gọn, max 200 từ."""


class AdvisoryHandler(IntentHandler):
    async def handle(self, intent, user):
        from app.wealth.services.net_worth_calculator import NetWorthCalculator
        from app.wealth.services.asset_service import AssetService
        from app.wealth.ladder import detect_level
        
        # Build rich context
        net_worth = await NetWorthCalculator().calculate(user.id)
        assets = await AssetService().get_user_assets(user.id)
        level = detect_level(net_worth.total)
        
        # Format breakdown
        breakdown_str = ", ".join([
            f"{cat}: {val:,.0f}đ"
            for cat, val in net_worth.by_type.items()
        ])
        
        # Get income (simplified)
        income_str = "chưa rõ"  # TODO: query IncomeStreams
        
        # Get goals
        goals_str = "chưa đặt"  # TODO: query Goals
        
        prompt = ADVISORY_PROMPT.format(
            query=intent.raw_text,
            name=user.display_name or "bạn",
            level=level.value,
            net_worth=f"{net_worth.total:,.0f}đ",
            breakdown=breakdown_str,
            income=income_str,
            goals=goals_str,
        )
        
        # Call LLM
        from openai import AsyncOpenAI
        from app.config import settings
        
        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1",
        )
        
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,  # Some creativity for advice
        )
        
        return response.choices[0].message.content
```

**Note quan trọng:** Advisory handler cost cao hơn các handlers khác (~500 tokens/call). Đây là justified vì:
1. Là minority queries (~5%)
2. User get high value
3. Other handlers offset cost

---

## 3.3 — User Testing Protocol

### Test Suite: 30 Queries

Test với 5 users, mỗi user gửi 30 queries này:

**Group A — Direct queries (rule should match):**
1. tài sản của tôi có gì
2. tổng tài sản của tôi
3. portfolios chứng khoán của tôi
4. chi tiêu tháng này
5. chi tiêu cho ăn uống tháng này
6. chi phí sức khỏe tháng trước
7. thu nhập của tôi
8. VNM giá bao nhiêu
9. VN-Index hôm nay
10. mục tiêu của tôi

**Group B — Indirect queries (LLM may help):**
11. tôi đang giàu cỡ nào
12. tháng này tôi xài hoang chưa
13. cổ phiếu nào của tôi tăng nhiều nhất
14. tôi chi cho cafe nhiều không
15. tôi tiết kiệm được nhiều không

**Group C — Action queries:**
16. tiết kiệm 1tr
17. ghi 200k ăn trưa
18. tôi vừa mua 5 cổ VNM
19. xóa giao dịch hôm qua

**Group D — Advisory:**
20. nên đầu tư gì với 50tr
21. làm thế nào để mua nhà 5 tỷ
22. có nên bán VNM không
23. crypto có nên đầu tư không

**Group E — Edge cases:**
24. (gibberish: "asdkjfh")
25. "?"
26. (rất dài: "tôi muốn biết về tất cả tài sản chi tiêu mục tiêu thu nhập đầu tư của tôi")
27. "thời tiết hôm nay" (out of scope)
28. (mixed: "tài sản với chi tiêu")
29. (tiếng Anh: "show my assets")
30. (typo: "tài sảnn của tôii")

### Success Metrics

| Metric | Target |
|--------|--------|
| Group A accuracy | ≥95% (nearly all rule matches) |
| Group B accuracy | ≥80% (LLM does the work) |
| Group C accuracy | ≥85% with confirmation |
| Group D handling | ≥80% reasonable advice |
| Group E behavior | 100% graceful (no silent fail) |
| Avg response time | <2 seconds |
| LLM call rate | <30% of queries |
| Cost per query | <$0.0003 |

---

## ✅ Checklist Cuối Tuần 3

- [ ] Personality layer integrated
- [ ] Advisory handler hoạt động
- [ ] All 30 test queries pass success criteria
- [ ] User testing với 5 users completed
- [ ] Analytics dashboard show:
  - % queries handled by rule vs LLM
  - Avg confidence per intent
  - Failure rate
- [ ] Documentation updated
- [ ] Migration plan từ menu-fallback → free-form ready

---

# 📊 Metrics Phase 3.5

Track ngay từ tuần 1:

**Coverage:**
- % queries với intent classified (target: >90%)
- % queries handled successfully (target: >80%)

**Accuracy:**
- % rule-based matches confirmed correct (target: >95%)
- % LLM classifications confirmed correct (target: >85%)

**User Satisfaction:**
- Reply rate (user respond after bot's clarification?) — target: >70%
- Negative feedback rate (target: <5%)

**Cost:**
- Average LLM tokens per query (target: <50 tokens)
- Total monthly cost projected at scale

---

# 🎯 Exit Criteria Phase 3.5

Chỉ chuyển Phase 3B khi:

- [ ] 30 test queries pass với success rates trên
- [ ] Cost <$5/month for current usage
- [ ] D7 retention không giảm (hoặc tăng) so với pre-3.5
- [ ] User feedback: "Bé Tiền hiểu mình tốt hơn rồi"
- [ ] Analytics: rule-based catches >70% queries
- [ ] No regressions in existing flows (wizards, briefing, storytelling)

---

# 🚧 Bẫy Thường Gặp Phase 3.5

## 1. Over-relying on LLM
LLM đắt + chậm + có thể hallucinate. Rule-based first principle quan trọng.

## 2. Pattern explosion
30 patterns OK. 300 patterns = unmaintainable. Khi nhiều quá, refactor sang LLM.

## 3. Ignoring confidence
"Confidence 0.6" không có nghĩa "execute". Implement confirmation flow.

## 4. Forget Vietnamese variations
"tài sản" có thể viết "tai san", "tài sảnn", "TÀI SẢN". Test diacritics + typos.

## 5. Generic responses
Bé Tiền có personality. Đừng output "Here are your assets:". Output "Tài sản của bạn nè! 💎".

## 6. No analytics
Không track = không biết classifier sai ở đâu. Setup từ tuần 1.

## 7. Forgetting OOS politely
User hỏi thời tiết → đừng silent fail. Polite decline + suggest alternative.

## 8. Voice/Audio context
User có thể gửi voice với queries. Voice → Whisper → text → intent pipeline. Test.

---

# 📚 Tài Liệu Tham Khảo

- DeepSeek API: https://platform.deepseek.com
- Vietnamese NLP resources: underthesea, pyvi
- Intent classification patterns: Rasa, Dialogflow
- Dispatcher pattern: martinfowler.com/eaaCatalog

---

**Phase 3.5 transforms Bé Tiền from "menu app" to "AI assistant". Sau phase này, user sẽ cảm thấy Bé Tiền thực sự THÔNG MINH — đây là moment of truth của product.** 

**Good luck! 🚀💚**
