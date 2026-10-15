---
name: design
description: Comprehensive UI/UX, Design System, and Frontend Polish Framework. Use this skill whenever building or refining web applications, dashboards, component systems, or styling. Focuses on eliminating amateur patterns (like raw emojis in UI, generic layouts, unstyled buttons) in favor of crisp SVG iconography, cohesive design tokens, refined micro-interactions, and professional FinTech/SaaS aesthetics.
---

# Design & Frontend Polish System

A professional design-engineering framework to ensure interfaces look deliberate, crafted, and enterprise-grade.

## 1. Iconography Standards
- **Zero Raw Emojis in UI**: Never use OS emojis (e.g., `📊`, `💰`, `💳`, `💾`, `✏️`, `👤`) for navigation, buttons, titles, or actions. Different operating systems render emojis inconsistently and create a toy-like impression.
- **Consistent SVG Micro-Icons**: Use inline SVGs or SVG sprite definitions styled with:
  - `viewBox="0 0 24 24"` (or `0 0 20 20` for compact badges).
  - `fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"`.
  - Scaled via CSS using relative or explicit units (`width: 18px; height: 18px;`).
  - Alignment: vertically centered with text (`display: inline-flex; align-items: center; gap: 8px;`).

## 2. Typography & Numerical Precision
- **Geometric / Humanist Primary Font**: Pairs such as *Plus Jakarta Sans*, *Inter*, *Geist*, or *Outfit*.
- **Tracking & Weight Hierarchy**:
  - Main section titles: `font-weight: 700` or `800`, `letter-spacing: -0.025em`.
  - Section subtitles & labels: `font-weight: 500` or `600`, `font-size: 0.85rem`.
  - Metadata & timestamps: `color: var(--text-muted); font-size: 0.78rem;`.
- **Financial & Data Tabular Figures**:
  - Always enforce `font-variant-numeric: tabular-nums;` on balances, currencies, percentages, and table cells so numbers align precisely without jittering during live updates.

## 3. Surface & Elevation Architecture
- **Layered Surfaces**:
  - Base canvas (`--bg-color`): Soft slate tint in light mode (`#f8fafc`), deep midnight obsidian in dark mode (`#090d16`).
  - Panel / Card surface (`--panel-bg`): `#ffffff` (light), `#111827` (dark).
  - Subtle borders: `1px solid var(--border-color)` (`#e2e8f0` light, `#1f2937` dark). Avoid harsh black borders.
- **Elevation**:
  - Soft diffuse shadows: `box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.05)`.
  - Modals & Floating Menus: Backdrop blur (`backdrop-filter: blur(8px);`) with deep elevation (`0 20px 40px -8px rgba(0, 0, 0, 0.4)`).

## 4. Buttons, Forms & Interactive Feedback
- **Primary Buttons**: Gradient or solid primary accent, white text, subtle glow shadow, tactile active state (`transform: scale(0.98)`).
- **Secondary & Ghost Buttons**: Transparent or subtle tint, border matching container, color reacting on hover.
- **Inputs & Selects**: Crisp border, background matching panel, focus ring with 3px subtle brand glow (`outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-subtle);`).
- **Transitions**: Standardized micro-interaction speed (`transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);`).

## 5. Visual Consistency Checklist
- [x] All emoji characters replaced with vector SVG icons.
- [x] Currency values have tabular figures and localized currency symbols.
- [x] Status dots have subtle animated glow or clean border rings.
- [x] Badges use muted semantic background with higher-contrast text.
- [x] Modals have clear exit triggers and accessible focus targets.
