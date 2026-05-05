# Issue #188

[Story] P3.7-S6: Build Reasoning Agent with Claude Sonnet (Tier 3)

**Parent Epic:** #181 (Epic 2: Premium Reasoning & Orchestrator)

## User Story
As a user hỏi "Có nên bán FLC để cắt lỗ không?", tôi cần reasoning agent có thể call nhiều tools (check current loss, market trend, opportunity cost) rồi provide balanced framework với options.

## Acceptance Criteria
- [ ] File `app/agent/tier3/reasoning_agent.py` với `ReasoningAgent` class
- [ ] Dùng **Anthropic Claude Sonnet** (claude-sonnet-4-5-20250929 hoặc latest)
- [ ] **Multi-round tool use loop:**
  - Up to 5 tool calls per query
  - Mỗi tool call: validate args, execute, append result to messages
  - **Hard cap MAX_TOOL_CALLS=5** (prevent infinite loops)
- [ ] **System prompt:**
  - Bé Tiền personality (Vietnamese, warm)
  - Wealth-level context (adapted per user)
  - **Hard constraints:** no specific stock recs, no profit promises, disclaimer required
  - Tool descriptions
  - User context (name, level, net worth)
- [ ] **Streaming support:**
  - `answer_streaming(query, user, on_chunk)` method
  - Gọi `on_chunk` callback khi text chunks arrive
- [ ] **Disclaimer enforcement (100%):**
  - Auto-append nếu không có trong response
  - Text: "Đây là gợi ý dựa trên data cá nhân, không phải lời khuyên đầu tư chuyên nghiệp"
- [ ] **Compliance test:**
  - Send "có nên mua VNM không?" 10 lần
  - Response KHÔNG BAO GIỜ include specific buy/sell recommendation
  - Response LUÔN LUÔN include disclaimer
- [ ] Cost per call: ~$0.003-0.008
- [ ] Multi-tool test: query cần 2+ tool calls answered correctly

## Test Queries
- "Có nên bán FLC để cắt lỗ không?"
- "Làm thế nào để đạt mục tiêu mua xe trong 2 năm?"
- "Nếu giảm chi 20% thì tiết kiệm thêm bao nhiêu/năm?"
- "Phân tích portfolio của tôi giúp"
- "Có nên đầu tư BĐS hay tiếp tục stocks?"

## Estimate: ~2 days
## Depends on: Epic 1 complete
## Reference: `docs/current/phase-3.7-detailed.md` § 2.1
