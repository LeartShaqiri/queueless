"""Restaurants, stores and billers.

Restaurant menus and prices are taken from each brand's Prishtina listing on Wolt (Nov 2026).
Store product lists are illustrative samples, not live catalogues.
"""

B = "/static/brands/"


def items(section, rows):
    out = []
    for name, price, *desc in rows:
        slug = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
        out.append({"id": slug, "name": name, "price": price, "section": section, "desc": desc[0] if desc else ""})
    return out


RESTAURANTS = {
    "Heb's": {
        "logo": B + "hebs.jpg",
        "sub": "Chicken & burgers",
        "menu": [
            *items("Burgers", [
                ("Hebs Chicken Burger", "2.99"), ("Hebs Beef Burger", "2.99"), ("Golden Burger", "3.70"),
                ("Crispy Onion Burger", "3.30"), ("Jalapeno Burger", "3.30"), ("Mega Cheese Burger", "4.00"),
            ]),
            *items("Meals", [
                ("Hebs Chicken Burger Menu", "5.10", "Burger, fries and a drink"),
                ("Mega Cheese Burger Menu", "6.80", "Burger, fries and a drink"),
                ("Kids Box", "4.29", "Hamburger, drink, fries and a toy"),
            ]),
            *items("Chicken", [
                ("Hebs Chicken Spinner", "2.99"), ("Spicy Wings · 5 pcs", "3.99"), ("Chicken Tenders · 5 pcs", "5.19"),
            ]),
            *items("Sides & drinks", [
                ("Fries M", "1.39"), ("Curly Fries", "1.49"), ("Onion Rings", "1.90"),
                ("Mozzarella Sticks · 5 pcs", "3.19"), ("Garlic Sauce", "0.50"), ("Coca Cola", "1.50"), ("Water", "1.20"),
            ]),
        ],
    },
    "KFC": {
        "logo": B + "kfc.png",
        "sub": "Fried chicken",
        "menu": [
            *items("Burgers & wraps", [
                ("Original Burger", "4.59"), ("Zinger Original Burger", "4.59", "Spicy"), ("Tower Burger", "5.39"),
                ("Double Fillet Burger", "6.99"), ("Twister Wrap", "4.59"), ("Cheeseburger", "2.69"),
            ]),
            *items("Meals", [
                ("Original Combo", "6.99", "Original Burger, Crispy Strips, medium fries, drink and dip"),
                ("Original Burger Menu", "7.09", "Burger, fries and a drink"),
                ("Zinger Tower Burger Menu", "7.89", "Burger, fries and a drink"),
            ]),
            *items("Buckets & pieces", [
                ("Hot Wings", "2.39"), ("Crispy Strips", "4.19"), ("Chili Cheese Nuggets", "1.99"),
                ("Duo Bucket", "10.99", "5 Hot Wings, 5 Crispy Strips, 2 medium fries"),
            ]),
            *items("Sides & dips", [
                ("CrissCuts", "1.89"), ("Corn", "1.20"), ("Don Garlic Dip", "0.59"), ("Sweet Chilli Dip", "0.59"),
            ]),
        ],
    },
    "Pano Pizza": {
        "logo": B + "pano.jpg",
        "sub": "Pizza, pasta & sandwiches",
        "menu": [
            *items("Pizza", [
                ("Pizza Margarita", "3.30", "Tomato sauce, kashkaval, oregano"),
                ("Pizza Funghi", "3.50", "Tomato sauce, kashkaval, mushrooms"),
                ("Pizza Proshutë", "4.00", "Tomato sauce, ham, kashkaval"),
                ("Pizza Pepperoni", "4.00", "Tomato sauce, Bosnian sujuk, peppers"),
                ("Pizza Chicken", "4.00", "Pano sauce, smoked chicken, corn"),
                ("Pizza Pano", "4.90", "Ham, minced meat, spring onion"),
                ("Pizza Calzone", "7.00"),
            ]),
            *items("Sandwiches & pasta", [
                ("Sandwich Mix", "4.40", "Smoked chicken, sujuk, cheese, Pano sauce"),
                ("Chicken Cheddar Burger", "4.40"),
                ("Pasta Bologneze", "4.60"), ("Pesto Pasta", "4.60"),
            ]),
            *items("Sides & drinks", [
                ("Garlic Bread", "2.50"), ("Fries", "1.20"), ("Sos Pano", "0.50"), ("Coca Cola", "1.50"),
            ]),
        ],
    },
}

STORES = {
    "Royal Mall": [
        {"name": "Neptun", "logo": B + "neptun.png", "sub": "Electronics", "products": items("Electronics", [
            ("Samsung Galaxy A55 128GB", "389.00"), ("Xiaomi Redmi Note 14", "229.00"), ("JBL Flip 6 speaker", "119.00"),
            ("Philips Air Fryer", "99.00"), ("Logitech wireless mouse", "24.90"),
        ])},
    ],
    "Albi Mall": [
        {"name": "Zara", "logo": B + "zara.webp", "sub": "Fashion", "products": items("Clothing", [
            ("Wool blend coat", "89.95"), ("Straight-fit jeans", "35.95"), ("Knit sweater", "29.95"), ("Leather ankle boots", "69.95"),
        ])},
        {"name": "Nike", "logo": B + "nike.webp", "sub": "Sportswear", "products": items("Sportswear", [
            ("Air Force 1 '07", "119.99"), ("Club Fleece hoodie", "59.99"), ("Dri-FIT T-shirt", "29.99"), ("Brasilia backpack", "34.99"),
        ])},
        {"name": "Mango", "logo": B + "mango.webp", "sub": "Fashion", "products": items("Clothing", [
            ("Classic trench coat", "99.99"), ("Linen shirt", "39.99"), ("Mom-fit jeans", "39.99"),
        ])},
        {"name": "Levi's", "logo": B + "levis.webp", "sub": "Denim", "products": items("Denim", [
            ("501 Original jeans", "109.95"), ("Trucker jacket", "109.95"), ("Housemark logo tee", "29.95"),
        ])},
        {"name": "Bershka", "logo": B + "bershka.webp", "sub": "Fashion", "products": items("Clothing", [
            ("Oversize hoodie", "25.99"), ("Baggy jeans", "35.99"), ("Puffer jacket", "49.99"),
        ])},
        {"name": "Tommy Hilfiger", "logo": B + "tommy-hilfiger.webp", "sub": "Fashion", "products": items("Clothing", [
            ("Slim-fit polo", "79.90"), ("Chino trousers", "99.90"), ("Crew-neck jumper", "119.90"),
        ])},
    ],
    "Prishtina Mall": [
        {"name": "H&M", "logo": B + "hm.png", "sub": "Fashion", "products": items("Clothing", [
            ("Regular-fit T-shirt", "9.99"), ("Slim jeans", "29.99"), ("Knit cardigan", "34.99"), ("Padded jacket", "59.99"),
        ])},
        {"name": "Intersport", "logo": B + "intersport.png", "sub": "Sports", "products": items("Sports", [
            ("Running shoes", "89.99"), ("Football, size 5", "24.99"), ("Yoga mat", "19.99"), ("Sports bottle", "9.99"),
        ])},
        {"name": "Hamleys", "logo": B + "hamleys.png", "sub": "Toys", "products": items("Toys", [
            ("LEGO Classic box", "39.99"), ("Hamleys teddy bear", "29.99"), ("Remote-control car", "49.99"), ("Family board game", "24.99"),
        ])},
        {"name": "Diesel", "logo": B + "diesel.png", "sub": "Denim", "products": items("Denim", [
            ("D-Strukt jeans", "160.00"), ("Logo T-shirt", "70.00"), ("Leather belt", "95.00"),
        ])},
    ],
}

BILLERS = [
    {"value": "KEDS", "type": "Electricity", "logo": B + "keds.svg", "sub": "Electricity"},
    {"value": "KRU Prishtina", "type": "Water", "logo": B + "kru.png", "sub": "Water", "bg": "#0B5EA8"},
    {"value": "IPKO", "type": "Phone & internet", "logo": B + "ipko.png", "sub": "Phone & internet"},
]
