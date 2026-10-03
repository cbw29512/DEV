# Grocery List

## Definition of Done

- Mobile-first grocery checklist that works well from an iPhone Home Screen.
- The current grocery list is stored in GitHub as data, not hard-coded into the UI.
- Checking an item hides it from the active shopping list.
- Checked items can be shown again and unchecked.
- Check state persists on the same device/browser.
- Future list additions/removals can be made by updating `items.json` without rebuilding app logic.
- A failed network fetch falls back to the last successfully cached grocery list.
- The app is deployable as a static Netlify site.

## Data Schema

Server list: `items.json`

```json
{
  "id": "stable-string-id",
  "category": "Meat",
  "text": "2 rotisserie chickens"
}
```

Rules:
- `id` is stable and unique. Never reuse an ID for a different grocery item.
- `category` controls grouping.
- `text` is the user-visible quantity/name.

Local device state:
- `groceryCheckedV1`: object mapping item IDs to booleans.
- `groceryItemsCacheV1`: last successfully loaded copy of `items.json`.

The server list and local checked state are intentionally separate so list changes do not erase checkmarks for unchanged items.
