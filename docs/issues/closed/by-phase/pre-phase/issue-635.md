# Issue #635

bug: KeyError 'vip' in menu_formatter.format_main_menu when wealth_level is 'vip'

## Bug
Clicking /menu produces no response. Backend returns 200 but bot sends nothing.

## Log
```
File ".../menu_formatter.py", line 58, in format_main_menu
    title = config["title"][band].format(name=name)
KeyError: 'vip'
```

## Root cause
`content/menu_copy.yaml` has no `title.vip` key, but some users have `wealth_level=vip`. The formatter tries to look up `config["title"]["vip"]` and crashes with KeyError.

## Files
- `backend/bot/formatters/menu_formatter.py:58`
- `content/menu_copy.yaml` (missing `vip` section)
