---
name: sichuan-cooking
description: Use this skill when the user asks how to cook Sichuan food, wants a Sichuan recipe, asks for spicy/numbing flavor adjustment, needs ingredient substitutions for Sichuan dishes, or wants a home-cooking workflow for dishes such as mapo tofu, twice-cooked pork, kung pao chicken, boiled fish, fish-fragrant eggplant, or dan dan noodles.
---

# Sichuan Cooking

## Overview

Give practical Sichuan cooking guidance for home kitchens. Focus on flavor balance, ingredient preparation, heat control, and substitutions rather than restaurant-style complexity.

## Response Workflow

1. Clarify constraints only when needed: dish name, servings, spice tolerance, available ingredients, dietary limits, and cooking equipment.
2. If the user names a dish, provide a direct recipe. If the user only asks for "四川菜", recommend 2-4 suitable dishes first.
3. Structure recipes with:
   - Dish profile: flavor, difficulty, time.
   - Ingredients: main ingredients, aromatics, seasonings.
   - Prep: cutting, marinating, sauce mix.
   - Cooking steps: ordered, short, heat-level aware.
   - Key points: what can go wrong and how to fix it.
   - Adjustments: less spicy, more numbing, vegetarian, no doubanjiang, etc.
4. Keep quantities realistic for home cooking and use metric units where possible.

## Sichuan Flavor Principles

- Core flavors often come from doubanjiang, dried chili, Sichuan peppercorn, ginger, garlic, scallion, soy sauce, vinegar, sugar, and stock or water.
- "麻" comes from Sichuan peppercorn; add it carefully and adjust at the end.
- "辣" comes from chili oil, dried chili, fresh chili, and doubanjiang; reduce chili before reducing aromatics.
- Many dishes need balance: salty, spicy, numbing, slightly sweet, aromatic, and sometimes sour.
- Toast or bloom chili and peppercorn gently; burnt spices turn bitter quickly.

## Default Recipe Format

```text
菜名：
适合：
时间：
难度：

食材：
- ...

步骤：
1. ...
2. ...

关键点：
- ...

口味调整：
- 少辣：
- 更麻：
- 无某食材替代：
```

## Safety And Practicality

- For pork, chicken, fish, and seafood, remind the user to cook thoroughly.
- Warn about hot oil when making chili oil or blooming spices.
- Do not claim one recipe is the only authentic version; Sichuan dishes vary by region and household.
- If the user has allergies or dietary restrictions, adapt the recipe instead of ignoring them.
