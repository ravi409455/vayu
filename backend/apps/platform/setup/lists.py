"""Master lists the setup fills. Cities are Clappia's (BookingCreation 3.0 "Car Inspection City").
Clappia types the car freely, so car make/model is ours: Clappia's car companies, each with the
models commonly inspected in India. Items are only added, never removed or relabelled (an admin's
later edits stay)."""
from django.core.management import call_command

from apps.forms.models import MasterList, MasterListItem

from .clappia import slug

CITIES = ["Delhi", "Faridabad", "Ghaziabad", "Greater Noida", "Gurgaon", "Hyderabad", "Manesar",
          "Meerut", "Noida", "Pune", "Gandhinagar", "Ahmedabad", "Bangalore"]

CARS = {
    "Audi": ["A4", "A6", "Q3", "Q5", "Q7"],
    "BMW": ["3 Series", "5 Series", "X1", "X3", "X5"],
    "Chevrolet": ["Beat", "Cruze", "Enjoy"],
    "Citroën": ["C3", "C3 Aircross", "eC3", "Basalt"],
    "Datsun": ["Go", "Redi-Go"],
    "Fiat": ["Punto", "Linea"],
    "Ford": ["EcoSport", "Endeavour", "Figo", "Aspire"],
    "Force": ["Gurkha"],
    "Honda": ["Amaze", "City", "Elevate", "WR-V", "Jazz"],
    "Hyundai": ["Creta", "Venue", "i20", "Grand i10 Nios", "Verna", "Exter", "Alcazar", "Tucson",
                "Aura", "Ioniq 5"],
    "Jaguar": ["XE", "XF", "F-Pace"],
    "Jeep": ["Compass", "Meridian", "Wrangler"],
    "Kia": ["Seltos", "Sonet", "Carens", "Syros", "EV6"],
    "Mahindra": ["XUV 3XO", "XUV700", "Scorpio-N", "Scorpio Classic", "Thar", "Thar Roxx",
                 "Bolero", "XUV400", "BE 6", "XEV 9e"],
    "Maruti Suzuki": ["Swift", "Dzire", "Baleno", "Brezza", "Ertiga", "Fronx", "Grand Vitara",
                      "WagonR", "Alto K10", "Celerio", "XL6", "Invicto", "Jimny", "Victoris",
                      "Ignis", "S-Presso", "Ciaz"],
    "Mercedes": ["A-Class", "C-Class", "E-Class", "GLA", "GLC", "GLE"],
    "MG": ["Hector", "Astor", "Comet EV", "Windsor EV", "ZS EV", "Gloster"],
    "Mitsubishi": ["Pajero Sport", "Outlander"],
    "Nissan": ["Magnite", "Kicks", "Micra"],
    "Renault": ["Kiger", "Triber", "Kwid", "Duster"],
    "Skoda": ["Kushaq", "Slavia", "Kylaq", "Octavia", "Superb", "Kodiaq"],
    "Tata": ["Nexon", "Nexon EV", "Punch", "Punch EV", "Tiago", "Tiago EV", "Tigor", "Altroz",
             "Harrier", "Safari", "Curvv", "Curvv EV"],
    "Toyota": ["Innova Crysta", "Innova Hycross", "Fortuner", "Urban Cruiser Hyryder", "Glanza",
               "Rumion", "Camry", "Hilux"],
    "Volkswagen": ["Virtus", "Taigun", "Tiguan", "Polo"],
}


def car_items() -> list[tuple[str, str]]:
    return [(slug(f"{make} {model}"), f"{make} {model}") for make, models in CARS.items()
            for model in models]


def apply() -> dict[str, int]:
    """Create the lists (the launch ones too) and add any missing items. Returns items added."""
    call_command("seed_master_lists", verbosity=0)
    added = {}
    for key, items in (("city", [(slug(c), c) for c in CITIES]), ("car_make_model", car_items())):
        lst = MasterList.objects.get(key=key)
        n = 0
        start = lst.items.count()
        for order, (item_key, label) in enumerate(items):
            _, made = MasterListItem.objects.get_or_create(
                list=lst, key=item_key, defaults={"label": label, "order": start + order})
            n += made
        added[key] = n
    return added
