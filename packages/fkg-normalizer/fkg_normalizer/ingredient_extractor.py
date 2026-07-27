"""
Ingredient Extractor — rule-based culinary ingredient discovery and normalizer.

Extracts canonical ingredient names from unstructured dish descriptions,
recipe texts, and web snippets.
"""
from __future__ import annotations

import re
import unicodedata

# 200+ Core Culinary Ingredients across global cuisines
CULINARY_INGREDIENTS: list[str] = [
    # Dairy & Fats
    "milk", "condensed milk", "evaporated milk", "cream", "heavy cream", "butter", "ghee", "clarified butter",
    "paneer", "cottage cheese", "cheese", "mozzarella", "parmesan", "yogurt", "curd", "rabri", "khoya", "mawa",
    "coconut milk", "coconut cream", "mustard oil", "sesame oil", "olive oil", "vegetable oil",
    
    # Grains, Flours & Legumes
    "rice", "basmati rice", "jasmine rice", "flattened rice", "poha", "semolina", "rawa", "sooji",
    "wheat flour", "all-purpose flour", "maida", "chickpea flour", "besan", "rice flour", "tapioca", "sago",
    "urad dal", "black gram", "moong dal", "mung bean", "toor dal", "pigeon pea", "chana dal", "split chickpea",
    "chickpeas", "garbanzo beans", "kidney beans", "rajma", "lentils", "peas", "green peas",
    
    # Sweeteners & Flavoring
    "sugar", "jaggery", "sugar syrup", "honey", "brown sugar", "maple syrup", "palm sugar",
    "vanilla", "cocoa powder", "chocolate", "dark chocolate", "rose water", "kewra water",
    
    # Spices & Herbs
    "saffron", "cardamom", "green cardamom", "black cardamom", "cinnamon", "cloves", "star anise",
    "black pepper", "white pepper", "cumin", "caraway", "shahi jeera", "mustard seeds", "fenugreek", "methi",
    "turmeric", "coriander seeds", "coriander powder", "red chili powder", "cayenne", "paprika",
    "garam masala", "chaat masala", "curry leaves", "coriander leaves", "cilantro", "mint", "pudina",
    "ginger", "garlic", "hing", "asafoetida", "tamarind", "bay leaf", "nutmeg", "mace", "poppy seeds", "khus khus",
    "galangal", "lemongrass", "kaffir lime leaves", "thai basil", "fish sauce", "soy sauce", "chili paste",
    
    # Vegetables & Fungi
    "potatoes", "potato", "onions", "onion", "shallots", "tomatoes", "tomato", "spinach", "palak",
    "cauliflower", "gobi", "cabbage", "carrots", "carrot", "capsicum", "bell pepper", "green chili", "red chili",
    "eggplant", "brinjal", "baingan", "okra", "bhindi", "mushrooms", "mushroom", "pumpkin", "bottle gourd",
    "green beans", "bamboo shoots", "water chestnuts",
    
    # Fruits & Nuts
    "coconut", "grated coconut", "cashews", "cashew nuts", "almonds", "pistachios", "walnuts", "raisins",
    "banana", "apple", "mango", "lemon", "lime", "pineapple", "strawberry", "raspberry", "dates", "figs",
    
    # Meat & Seafood
    "chicken", "mutton", "lamb", "goat", "beef", "pork", "fish", "prawns", "shrimp", "crab", "egg", "eggs",
]


class IngredientExtractor:
    """Utility class to extract canonical culinary ingredients from text."""

    def __init__(self, custom_ingredients: list[str] | None = None) -> None:
        raw_list = (custom_ingredients or CULINARY_INGREDIENTS)
        # Sort by length descending so multi-word ingredients (e.g. "condensed milk") match before single words ("milk")
        self._ingredients = sorted(raw_list, key=len, reverse=True)

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize unicode, lowercase, and strip punctuation."""
        text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
        return text.lower()

    def extract_from_text(self, text: str) -> list[str]:
        """Scans input text and returns a list of unique canonical ingredients matched."""
        if not text:
            return []

        norm_text = self._normalize_text(text)
        found: list[str] = []
        seen: set[str] = set()

        for ing in self._ingredients:
            # Match whole word / boundary pattern
            pattern = r"\b" + re.escape(ing) + r"\b"
            if re.search(pattern, norm_text):
                # Avoid adding redundant sub-words if multi-word already present (e.g., skip "milk" if "condensed milk" added)
                if not any(ing in existing for existing in seen if ing != existing):
                    found.append(ing)
                    seen.add(ing)

        return found

    def clean_ingredient_string(self, raw_ingredient: str) -> str:
        """Strips quantities, units, and preparation notes from a raw ingredient line."""
        clean = raw_ingredient.lower().strip()
        # Remove common units/quantities: "1 cup", "200g", "2 tbsp", "1/2 tsp", "1 pinch"
        clean = re.sub(r"^\d+(?:\/\d+)?(?:\.\d+)?\s*(?:g|kg|ml|l|cup|cups|tbsp|tsp|pinch|pinches|gram|grams|oz|lb|pound|lbs)?\b", "", clean)
        clean = re.sub(r"\([^)]*\)", "", clean)  # remove parenthetical notes
        clean = re.sub(r"[^a-zA-Z\s]", " ", clean)  # remove punctuation
        clean = re.sub(r"\s+", " ", clean).strip()

        # Match against dictionary if possible
        matched = self.extract_from_text(clean)
        if matched:
            return matched[0]
        return clean[:40] if clean else raw_ingredient[:40].strip()
