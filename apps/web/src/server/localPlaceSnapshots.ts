import type { PlaceMenu } from "../lib/types.ts";
import type { GooglePlaceReview } from "./googlePlaces.ts";

interface LocalPlaceSnapshot {
  names: string[];
  menu?: PlaceMenu;
  reviews?: GooglePlaceReview[];
}

function normalizeName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

const SNAPSHOTS: LocalPlaceSnapshot[] = [
  {
    names: ["PrimeTime College Park", "Primetime College Park"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Popular Picks",
          items: [
            {
              name: "French Onion Soup",
              description: "Rich onion broth with melted cheese.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy", "wheat_gluten"],
            },
            {
              name: "Lobster Mac and Cheese",
              description: "Creamy pasta with lobster and cheese sauce.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy", "shellfish", "wheat_gluten"],
            },
            {
              name: "Chili Pop Shrimp",
              description: "Popcorn shrimp in a sweet-spicy chili sauce.",
              price: "$16",
              likely_safe_for: [],
              likely_risky_for: ["shellfish", "wheat_gluten", "egg"],
            },
            {
              name: "Steak",
              description: "Grilled steak entree.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Grilled Chicken",
              description: "Simply prepared grilled chicken.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
          ],
        },
      ],
    },
    reviews: [
      {
        review_id: "snapshot-primetime-1",
        author_name: "Local demo snapshot",
        rating: 5,
        text: "Others at our table had burgers, steak, and chicken, all perfectly cooked.",
        publish_time: null,
        relative_publish_time: null,
      },
      {
        review_id: "snapshot-primetime-2",
        author_name: "Local demo snapshot",
        rating: 1,
        text: "The soup and the ribs are just so salty that my wife can't even finish her food.",
        publish_time: null,
        relative_publish_time: null,
      },
    ],
  },
  {
    names: ["Honey Pig BBQ", "Honey Pig"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Korean BBQ",
          items: [
            {
              name: "Beef Bulgogi",
              description: "Thinly sliced marinated beef for tabletop grilling.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["soy", "sesame"],
            },
            {
              name: "Spicy Pork Bulgogi",
              description: "Marinated pork with a spicy sauce.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["soy", "sesame"],
            },
            {
              name: "Pork Belly",
              description: "Unmarinated pork belly for shared-grill barbecue.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Kimchi Fried Rice",
              description: "Rice stir-fried with kimchi and seasoning.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["egg", "soy", "sesame"],
            },
            {
              name: "Seafood Tofu Soup",
              description: "Soft tofu soup with seafood broth.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["shellfish", "soy", "egg"],
            },
          ],
        },
      ],
    },
    reviews: [
      {
        review_id: "snapshot-honeypig-1",
        author_name: "Local demo snapshot",
        rating: 3,
        text: "Good for groups, but the tabletop grill means sauces and marinades can end up everywhere.",
        publish_time: null,
        relative_publish_time: null,
      },
    ],
  },
  {
    names: ["The Board and Brew", "Board and Brew"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Cafe Favorites",
          items: [
            {
              name: "Turkey Avocado Sandwich",
              description: "Turkey, avocado, tomato, and greens on toasted bread.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["wheat_gluten"],
            },
            {
              name: "Breakfast Burrito",
              description: "Eggs, cheese, potatoes, and salsa wrapped in a tortilla.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["egg", "dairy", "wheat_gluten"],
            },
            {
              name: "House Salad",
              description: "Mixed greens with tomato, cucumber, and vinaigrette.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Cold Brew",
              description: "Slow-steeped iced coffee.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Bagel with Cream Cheese",
              description: "Toasted bagel served with cream cheese.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy", "wheat_gluten"],
            },
          ],
        },
      ],
    },
  },
  {
    names: ["Ledo Pizza", "Ledo Pizza College Park"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Popular Orders",
          items: [
            {
              name: "Cheese Pizza",
              description: "Square-cut pizza with house sauce and mozzarella.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy", "wheat_gluten"],
            },
            {
              name: "Vegetable Pizza",
              description: "Pizza topped with peppers, mushrooms, and onions.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy", "wheat_gluten"],
            },
            {
              name: "Buffalo Wings",
              description: "Chicken wings tossed in buffalo sauce.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Garden Salad",
              description: "Lettuce, tomato, cucumber, and house dressing.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
          ],
        },
      ],
    },
  },
  {
    names: ["Raising Cane's Chicken Fingers", "Raising Cane's"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Cane's Staples",
          items: [
            {
              name: "Chicken Fingers",
              description: "Breaded chicken tenders with Cane's sauce.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["wheat_gluten", "egg"],
            },
            {
              name: "Crinkle-Cut Fries",
              description: "Salted crinkle fries.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Coleslaw",
              description: "Shredded cabbage slaw with creamy dressing.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["egg"],
            },
            {
              name: "Texas Toast",
              description: "Buttered toasted bread.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy", "wheat_gluten"],
            },
            {
              name: "Lemonade",
              description: "Fresh lemonade.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
          ],
        },
      ],
    },
  },
  {
    names: ["Dunkin'", "Dunkin"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Quick Picks",
          items: [
            {
              name: "Cold Brew",
              description: "Black cold brew coffee.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Hash Browns",
              description: "Seasoned bite-sized potatoes.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Wake-Up Wrap",
              description: "Egg, cheese, and meat in a tortilla wrap.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["egg", "dairy", "wheat_gluten"],
            },
            {
              name: "Multigrain Bagel",
              description: "Bagel served plain or toasted.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["wheat_gluten"],
            },
          ],
        },
      ],
    },
  },
  {
    names: ["Chipotle Mexican Grill", "Chipotle"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Burritos and Bowls",
          items: [
            {
              name: "Chicken Salad Bowl",
              description: "Romaine, chicken, rice, beans, and tomato salsa.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Steak Burrito",
              description: "Steak, rice, beans, salsa, and cheese in a tortilla.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy", "wheat_gluten"],
            },
            {
              name: "Chips and Guacamole",
              description: "Corn tortilla chips with guacamole.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Quesadilla",
              description: "Flour tortilla with melted cheese and filling.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy", "wheat_gluten"],
            },
          ],
        },
      ],
    },
  },
  {
    names: ["CAVA", "Cava"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Bowls and Salads",
          items: [
            {
              name: "Greens and Grains Bowl",
              description: "Greens, grains, chicken, tomato, cucumber, and lemon herb dressing.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Falafel Bowl",
              description: "Falafel, hummus, grains, vegetables, and tahini.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["sesame"],
            },
            {
              name: "Greek Salad",
              description: "Greens, vegetables, olives, and feta.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy"],
            },
            {
              name: "Pita Chips",
              description: "Seasoned pita chips.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["wheat_gluten"],
            },
          ],
        },
      ],
    },
  },
  {
    names: ["sweetgreen", "Sweetgreen"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Salads and Bowls",
          items: [
            {
              name: "Chicken Harvest Bowl",
              description: "Chicken, greens, rice, carrots, and apples.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Garden Cobb",
              description: "Greens, chicken, egg, blue cheese, and ranch.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["egg", "dairy"],
            },
            {
              name: "Shroomami",
              description: "Warm grains, mushrooms, tofu, and sesame seeds.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["soy", "sesame"],
            },
            {
              name: "Crispy Rice Bowl",
              description: "Rice, vegetables, and crispy toppings.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
          ],
        },
      ],
    },
  },
  {
    names: ["Subway", "Subway College Park"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Sandwiches and Salads",
          items: [
            {
              name: "Oven-Roasted Turkey Salad",
              description: "Turkey with lettuce, tomato, cucumber, and onion.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Veggie Delite Salad",
              description: "Lettuce, tomato, cucumber, peppers, and onion.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Turkey Footlong",
              description: "Turkey sandwich on bread with toppings.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["wheat_gluten"],
            },
            {
              name: "Cookie",
              description: "Fresh-baked dessert cookie.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["egg", "dairy", "wheat_gluten"],
            },
          ],
        },
      ],
    },
  },
  {
    names: ["Busboys and Poets", "Busboys & Poets"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Popular Plates",
          items: [
            {
              name: "Grilled Chicken Plate",
              description: "Grilled chicken with vegetables and rice.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Vegan Bowl",
              description: "Rice, beans, greens, and roasted vegetables.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Mac and Cheese",
              description: "Creamy macaroni and cheese.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy", "wheat_gluten"],
            },
            {
              name: "Fried Cauliflower",
              description: "Crispy cauliflower with dipping sauce.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["wheat_gluten"],
            },
          ],
        },
      ],
    },
  },
  {
    names: ["College Park Diner", "The College Park Diner"],
    menu: {
      source_url: null,
      sections: [
        {
          title: "Diner Staples",
          items: [
            {
              name: "Greek Salad",
              description: "Lettuce, tomato, cucumber, olives, and feta.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy"],
            },
            {
              name: "Grilled Chicken Platter",
              description: "Chicken breast with vegetables and rice.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
            {
              name: "Pancake Stack",
              description: "Buttermilk pancakes with butter.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: ["dairy", "egg", "wheat_gluten"],
            },
            {
              name: "French Fries",
              description: "Crispy fries from the fryer.",
              price: null,
              likely_safe_for: [],
              likely_risky_for: [],
            },
          ],
        },
      ],
    },
  },
];

export function getLocalPlaceSnapshot(placeName: string): LocalPlaceSnapshot | null {
  const normalized = normalizeName(placeName);
  return SNAPSHOTS.find((entry) => entry.names.some((name) => normalizeName(name) === normalized)) ?? null;
}
