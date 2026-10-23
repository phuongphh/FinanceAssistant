# Issue #367

fix(dashboard): asset name text overflow in wealth dashboard

## Description
Asset names that are too long overflow/break the dashboard card layout.

## Suggested fix
In backend/miniapp/static/css/wealth.css, add to .asset-name:
- overflow: hidden
- text-overflow: ellipsis
- white-space: nowrap

Or try clear Telegram cache first (Settings > Data and Storage > Clear Cache).
