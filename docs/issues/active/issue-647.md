# Issue #647

improve: Change land asset icon from house to tree in rental real estate

## Summary
Change the icon for "Đất" (Land) type real estate from the house icon to the tree icon in the rental real estate card.

## Motivation
In the "BĐS cho thuê" card under Asset menu, all real estate items currently use the same house icon (🏠). For "Đất" type properties, a tree icon (🌳) is more appropriate, matching the icon already used in the Add Asset → Real Estate form.

## Requirements
- [ ] Identify all "Đất" (Land) type assets in the "BĐS cho thuê" card
- [ ] Change their icon from house (🏠) to tree (🌳)
- [ ] Keep house icon for other property types (apartment, house, etc.)
- [ ] Match the tree icon style already used in Add Asset → Real Estate form

## Technical Notes
- Affected file(s): Rental real estate card component in Asset menu
- Reference the existing icon mapping in Add Asset → Real Estate form

## Acceptance Criteria
- [ ] All "Đất" type properties show tree icon
- [ ] Other property types keep house icon
- [ ] Icons match the existing style in the app

## Out of Scope
- Changing icons for other asset types
- Adding new asset types

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

In the "BĐS cho thuê" card under Asset menu:
1. Map "Đất" (Land) type properties to tree icon (🌳)
2. Keep house icon (🏠) for all other property types
3. Use the same tree icon style as in Add Asset → Real Estate form

Guidelines:
- Branch: improve/land-icon-tree
- Conventional commits
- Create draft PR linking to issue #[ISSUE_NUMBER]
```

