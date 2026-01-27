# Canton Network Documentation Style Guide

This document defines the visual styling for docs.canton.network, aligned with the canton.network brand.

## Color Palette

### Primary Brand Colors (from canton.network)
| Color | Hex | RGB | Usage |
|-------|-----|-----|-------|
| Purple Accent | #875CFF | rgb(135, 92, 255) | Hover states, links |
| Cyan/Teal | #96E4FD | rgb(150, 228, 253) | Accent backgrounds |
| Dark Text | #1B1B1B | rgb(27, 27, 27) | Primary text |
| Dark Gray | #434343 | rgb(67, 67, 67) | Active states, secondary text |

### Designer-Specified Colors (for docs)

#### Light Mode
| Color | Value | Usage |
|-------|-------|-------|
| Highlight/Primary | #734BE2 | rgb(115, 75, 226) | Links, buttons, accents |
| Selected Background | rgba(115, 75, 226, 0.10) | Hover states, selections |

#### Dark Mode
| Color | Value | Usage |
|-------|-------|-------|
| Highlight/Primary | #A985FF | rgb(169, 133, 255) | Links, buttons, accents |
| Selected Background | rgba(169, 133, 255, 0.10) | Hover states, selections |

### Background Colors
| Mode | Background | Usage |
|------|------------|-------|
| Light | #FFFFFF | Page background |
| Dark | #0F0F0F | Page background (near black) |
| Light Card | #F8F9FA | Card/panel backgrounds |
| Dark Card | #1A1A1A | Card/panel backgrounds |

## Typography

### Font Families
- **Primary**: Inter (Google Font)
- **Fallback**: system-ui, -apple-system, sans-serif

### Font Weights
- Regular: 400
- Bold: 700

### Usage
| Element | Weight | Size (base) |
|---------|--------|-------------|
| Body text | 400 | 16px |
| Headings | 700 | varies |
| Navigation | 500 | 14px |
| Code | 400 | 14px (monospace) |

## Mintlify Theme Settings

Based on the above, use these settings in docs.json:

```json
{
  "colors": {
    "primary": "#734BE2",
    "light": "#A985FF",
    "dark": "#5C3DB8"
  }
}
```

**Note:** Mintlify's `colors` object only supports `primary`, `light`, and `dark` keys. Background colors and selection states must be handled via custom CSS (see `styles.css`).

## Custom CSS (styles.css)

For additional styling beyond Mintlify's built-in options, use CSS custom properties:

```css
:root {
  --canton-highlight: #734BE2;
  --canton-selected-bg: rgba(115, 75, 226, 0.10);
  --canton-hover-bg: rgba(115, 75, 226, 0.05);
}

[data-theme="dark"] {
  --canton-highlight: #A985FF;
  --canton-selected-bg: rgba(169, 133, 255, 0.10);
  --canton-hover-bg: rgba(169, 133, 255, 0.05);
}
```

## Code Block Themes
- Light mode: github-light or similar clean theme
- Dark mode: github-dark or dracula for better contrast

## Logo Requirements
- Light mode: Dark/black Canton logo
- Dark mode: White Canton logo
- Formats: SVG preferred, PNG fallback
- Horizontal layout for navbar

## Reference
- Canton Network: https://www.canton.network/
- Brand Kit: https://www.canton.network/brand-kit-trademark-use
- Mintlify Settings: https://www.mintlify.com/docs/organize/settings
