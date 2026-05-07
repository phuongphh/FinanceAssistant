# Issue #245

[Story] P3.8.5-S2: Backend auto-classification via DeepSeek

**Parent Epic:** #241 (Epic 1: Feedback System)

## User Story
As a product team analyzing feedback, I need backend to auto-classify each feedback (category, sentiment, priority) so I don't manually categorize hundreds of submissions.

## Acceptance Criteria

### FeedbackClassifier Service
- [ ] File `app/feedback/services/classifier.py`
- [ ] `classify(content)` → dict: category, sentiment, priority, confidence, classifier_version
- [ ] DeepSeek API (existing infrastructure)
- [ ] Categories: bug | suggestion | praise | question | complaint | other
- [ ] Sentiment: positive | neutral | negative
- [ ] Priority: high | medium | low
- [ ] Fallback on JSON parse error → category="other", confidence=0

### Background Worker
- [ ] Picks up unclassified feedbacks (category IS NULL)
- [ ] Calls classifier, updates record
- [ ] Logs errors, retries max 3 times

### Cost Discipline
- [ ] Verify ≤$0.0001 per classification
- [ ] 1000 feedbacks/month <$0.10

### Accuracy
- [ ] Manual test 20 samples (5 bug, 5 suggestion, 5 praise, 5 mixed)
- [ ] Accuracy ≥80%

## Test Plan
```python
async def test_classify_bug():
    result = await classifier.classify("Bot không trả lời khi tôi gửi /menu")
    assert result["category"] == "bug"
    assert result["confidence"] > 0.5

async def test_classify_fallback_on_error():
    with mock_deepseek_returning_invalid_json():
        result = await classifier.classify("test")
        assert result["category"] == "other"
        assert result["confidence"] == 0.0
```

## Estimate: ~0.5 day
## Depends on: P3.8.5-S1
