"""
Food pairing service for wines.

Tier 1: Varietal lookup table (zero latency, covers ~80% of 191K wines).
Tier 2: LLM generation (deferred — add when users report missing pairings).
"""

from typing import Optional

VARIETAL_PAIRINGS: dict[str, str] = {
    "cabernet sauvignon": "Steak, lamb, aged cheese",
    "merlot": "Roast chicken, mushroom dishes, pasta",
    "pinot noir": "Salmon, duck, grilled vegetables",
    "chardonnay": "Lobster, creamy pasta, roast chicken",
    "sauvignon blanc": "Goat cheese, seafood, salads",
    "pinot grigio": "Light fish, sushi, antipasto",
    "pinot gris": "Light fish, sushi, antipasto",
    "riesling": "Thai food, spicy dishes, pork",
    "syrah": "BBQ ribs, stew, smoked meats",
    "shiraz": "BBQ ribs, stew, smoked meats",
    "malbec": "Grilled steak, empanadas, blue cheese",
    "tempranillo": "Tapas, chorizo, manchego",
    "zinfandel": "Pizza, burgers, BBQ",
    "sangiovese": "Pasta with red sauce, pizza, salami",
    "grenache": "Mediterranean dishes, roasted vegetables",
    "viognier": "Rich fish, apricot dishes, mild curry",
    "gewürztraminer": "Asian cuisine, foie gras, spicy food",
    "gewurztraminer": "Asian cuisine, foie gras, spicy food",
    "nebbiolo": "Truffle dishes, braised meat, risotto",
    "gamay": "Charcuterie, light chicken, picnic food",
    "chenin blanc": "Sushi, Thai food, fruit desserts",
    "muscadet": "Oysters, mussels, light seafood",
    "albariño": "Ceviche, grilled shrimp, paella",
    "albarino": "Ceviche, grilled shrimp, paella",
    "mourvèdre": "Grilled meats, stew, hard cheese",
    "mourvedre": "Grilled meats, stew, hard cheese",
    "cabernet franc": "Roasted vegetables, pork, goat cheese",
    "petit verdot": "Grilled lamb, dark chocolate, game",
    "carmenere": "Grilled meats, roasted peppers, beans",
    "torrontés": "Ceviche, sushi, light salads",
    "torrontes": "Ceviche, sushi, light salads",
    "verdejo": "Tapas, seafood, fresh salads",
    "grüner veltliner": "Schnitzel, Asian food, white fish",
    "gruner veltliner": "Schnitzel, Asian food, white fish",
    "marsanne": "Roast chicken, creamy sauces, nuts",
    "roussanne": "Rich seafood, poultry, soft cheese",
    "sémillon": "Roast chicken, rich seafood, foie gras",
    "semillon": "Roast chicken, rich seafood, foie gras",
    "barbera": "Tomato-based pasta, pizza, grilled meats",
    "primitivo": "Pizza, burgers, BBQ",
    "montepulciano": "Lamb, pasta, aged cheese",
    "corvina": "Risotto, braised meats, hard cheese",
    "aglianico": "Braised lamb, aged cheese, rich stews",
    "nero d'avola": "Grilled meats, eggplant, rich pasta",
    "vermentino": "Seafood, pesto, light salads",
    "prosecco": "Appetizers, light seafood, brunch",
    "moscato": "Fruit desserts, spicy food, brunch",
    "port": "Blue cheese, dark chocolate, nuts",
    "sherry": "Tapas, nuts, cured meats",
    # Wine type fallbacks
    "red": "Red meat, aged cheese, hearty dishes",
    "white": "Seafood, poultry, light dishes",
    "rosé": "Salads, light appetizers, grilled fish",
    "rose": "Salads, light appetizers, grilled fish",
    "sparkling": "Appetizers, oysters, celebration food",
    "dessert": "Fruit tarts, blue cheese, dark chocolate",
    "fortified": "Nuts, aged cheese, dark chocolate",
}


class PairingService:
    """Food pairing lookup. Varietal first, wine_type fallback."""

    def get_pairing(self, varietal: Optional[str], wine_type: Optional[str]) -> Optional[str]:
        """Return food pairing string, or None if no match."""
        if varietal:
            result = VARIETAL_PAIRINGS.get(varietal.lower())
            if result:
                return result

        if wine_type:
            result = VARIETAL_PAIRINGS.get(wine_type.lower())
            if result:
                return result

        return None
