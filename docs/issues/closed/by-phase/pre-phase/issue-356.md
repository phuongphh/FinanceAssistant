# Issue #356

[Story] P3.9.5-S18: Helper utility render animation emoji

**Parent Epic:** #338 (Epic 5: Telegram Animation Emojis)

## Description
Helper utility convert string với emoji → tuple (text, MessageEntity[]) để Telegram render animation.

## Acceptance Criteria
- [ ] Function render_with_animation(text, mapping) → tuple[str, list[MessageEntity]]
- [ ] Emoji trong mapping → entity type=custom_emoji, custom_emoji_id=...
- [ ] Emoji không mapping → giữ static (no entity)
- [ ] Telegram adapter accept entities param
- [ ] Unit test: all mapped, partial, none
- [ ] Layer contract: utility lives in backend/bot/utils/, adapter handles transport

## Estimate: ~0.3 day
## Dependencies: S17 (mapping file)

Close #338
