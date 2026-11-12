"""Builds reels/topics.json: validated Wikipedia article titles, interleaved across pillars.
Run once (or again after adding seeds). Existing used topics are tracked in history.json, not here."""
import json
import time
from pathlib import Path

import requests

HERE = Path(__file__).parent
UA = {"User-Agent": "DoodloreBot/1.0 (https://github.com/shamal8862; automated art reels) python-requests/2.32"}

SEEDS = {
    "myth": [
        "Prometheus", "Medusa", "Trojan Horse", "Achilles", "Midas", "Narcissus (mythology)", "Icarus", "Orpheus",
        "Sisyphus", "Tantalus", "Arachne", "Echo (mythology)", "Persephone", "Cerberus", "Minotaur", "Labours of Hercules",
        "Odysseus", "Polyphemus", "Siren (mythology)", "Scylla", "Atlas (mythology)", "Pegasus", "Golden Fleece", "Cassandra",
        "Pythia", "Lernaean Hydra", "Phoenix (mythology)", "Daedalus", "Theseus", "Perseus", "Bellerophon", "Chimera (mythology)",
        "Charon", "Styx", "Elysium", "Nemesis", "Romulus and Remus", "Aeneas", "Cupid and Psyche", "Pyramus and Thisbe",
        "Baucis and Philemon", "Pygmalion (mythology)", "Actaeon", "Niobe", "Tithonus", "Endymion (mythology)", "Hyacinth (mythology)",
        "Atalanta", "Calypso (mythology)", "Circe", "Penelope", "Argus Panoptes", "Damocles", "Gordian Knot", "Janus",
        "Ragnarok", "Yggdrasil", "Fenrir", "Thor", "Loki", "Odin", "Valhalla", "Valkyrie", "Mjolnir", "Sleipnir",
        "Jormungandr", "Baldr", "Idun", "Bifrost", "Freyja", "Draugr", "Kraken",
        "Osiris myth", "Ra", "Anubis", "Bastet", "Thoth", "Great Sphinx of Giza", "Curse of the pharaohs",
        "King Arthur", "Excalibur", "Merlin", "Holy Grail", "Lady of the Lake", "Banshee", "Selkie", "Loch Ness Monster",
        "Robin Hood", "Will-o'-the-wisp", "Tir na nOg", "Changeling", "Leprechaun", "Fairy ring", "Wild Hunt",
        "Golem", "Baba Yaga", "Pied Piper of Hamelin", "Flying Dutchman", "El Dorado", "Atlantis", "Kitsune", "Tengu",
        "Kappa (folklore)", "Yuki-onna", "Epic of Gilgamesh", "Tower of Babel", "Krampus", "La Llorona", "Anansi",
        "Jinn", "Aladdin", "Sinbad the Sailor", "Roc (mythology)", "Garuda", "Sun Wukong", "Chang'e", "Moon rabbit",
        "Fountain of Youth", "Prester John", "Wandering Jew", "Vampire", "Werewolf", "Mermaid", "Unicorn", "Basilisk",
        "Griffin", "Manticore", "Sea serpent", "Nidhogg", "Hel (mythology)", "Beowulf", "Grendel", "Tristan and Iseult",
    ],
    "history": [
        "Great Emu War", "Great Molasses Flood", "Defenestrations of Prague", "War of the Bucket", "Anglo-Zanzibar War",
        "Great Stink", "Tulip mania", "Cadaver Synod", "Pig War (1859)", "Great Moon Hoax", "Mary Toft", "Cottingley Fairies",
        "Year Without a Summer", "Tunguska event", "Great Fire of London", "Mary Celeste", "Roanoke Colony",
        "Voynich manuscript", "Antikythera mechanism", "Phaistos Disc", "Library of Alexandria", "Colossus of Rhodes",
        "Hanging Gardens of Babylon", "Terracotta Army", "Pompeii", "Tollund Man", "Sutton Hoo", "Rosetta Stone",
        "Nazca Lines", "Moai", "Stonehenge", "Carnac stones", "Ravens of the Tower of London", "Tarrare", "Phineas Gage",
        "Tanganyika laughter epidemic", "London Beer Flood", "Halifax Explosion", "Darien scheme", "South Sea Company",
        "Animal trial", "Children's Crusade", "Pope Joan", "Man in the Iron Mask", "Kaspar Hauser", "Lady Godiva",
        "Incitatus", "Great Fire of Rome", "Diogenes", "Hypatia", "Eureka (word)", "Galileo affair", "Tycho Brahe",
        "Isaac Newton's apple tree", "Kite experiment", "War of the currents", "The Great Exhibition", "The Crystal Palace",
        "Vasa (ship)", "Mary Rose", "Great Chicago Fire", "Johnstown Flood", "1883 eruption of Krakatoa", "Black Death",
        "Plague doctor costume", "Mary Mallon", "Body snatching", "Gin Craze", "Post-mortem photography",
        "Tower of London", "Hatshepsut", "Cleopatra", "Mechanical Turk", "Piltdown Man", "Cardiff Giant", "Fiji mermaid",
        "Great Wall of China", "Lighthouse of Alexandria", "Statue of Zeus at Olympia", "Mausoleum at Halicarnassus",
        "Temple of Artemis", "Great Pyramid of Giza", "Easter Island", "Lost Colony", "Franklin's lost expedition",
        "Dancing plague", "Benjamin Franklin", "Leonardo da Vinci's robot", "Ada Lovelace", "Rasputin",
        "Bayeux Tapestry", "Magna Carta", "Domesday Book", "Gunpowder Plot", "Salem witch trials",
        "Trial by ordeal", "Duel", "Bread and circuses", "Roman roads", "Greek fire", "Trebuchet", "Viking ship",
        "Lindisfarne", "Ship burial", "Bog body", "Mummy", "Egyptian pyramid construction techniques",
    ],
    "origin": [
        "OK", "Knocking on wood", "Friday the 13th", "Black cat", "Wedding ring", "Birthday cake", "Halloween",
        "Jack-o'-lantern", "Christmas tree", "Santa Claus", "Easter Bunny", "Valentine's Day", "April Fools' Day",
        "Groundhog Day", "Tooth fairy", "Mistletoe", "Pinata", "Sandwich", "Necktie", "High-heeled shoe", "Handshake",
        "Toast (honor)", "Salute", "Charles Boycott", "Ambrose Burnside", "Guillotine", "Etienne de Silhouette",
        "Pheidippides", "Laconic phrase", "Pan (god)", "Mentor (Odysseus)", "Ceres (mythology)", "Vulcan (mythology)",
        "Names of the days of the week", "Hygieia", "Horseshoe", "Four-leaf clover", "Wishbone", "Breaking a mirror",
        "Umbrella", "Fork", "Playing card", "Chess", "Tarot", "Board game", "Calendar", "Leap year", "Month",
        "Zodiac", "Constellation", "Astrolabe", "Hourglass", "Sundial", "Mechanical clock", "Spectacles",
        "Printing press", "Paper money", "Coin", "Postage stamp", "Penny Black", "Teddy bear", "Rubber duck",
        "Kaleidoscope", "Magic lantern", "Zoetrope", "Christmas card", "Advent calendar", "Easter egg",
        "May Day", "Maypole", "Morris dance", "Carnival", "Masquerade ball", "Fireworks", "Bonfire Night",
        "Gargoyle", "Green Man", "Labyrinth", "Ouroboros", "Caduceus", "Rod of Asclepius", "Evil eye",
        "Rabbit's foot", "Dreamcatcher", "Totem pole", "Scarecrow", "Weather vane", "Lighthouse",
    ],
}


def validate(titles):
    """Resolves redirects, drops missing pages and disambiguation pages."""
    ok = {}
    for i in range(0, len(titles), 40):
        batch = titles[i:i + 40]
        r = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
            "action": "query", "format": "json", "redirects": 1, "prop": "pageprops", "ppprop": "disambiguation",
            "titles": "|".join(batch)}).json()
        q = r.get("query", {})
        mapping = {t: t for t in batch}
        for n in q.get("normalized", []):
            mapping = {k: (n["to"] if v == n["from"] else v) for k, v in mapping.items()}
        for rd in q.get("redirects", []):
            mapping = {k: (rd["to"] if v == rd["from"] else v) for k, v in mapping.items()}
        pages = {p["title"]: p for p in q.get("pages", {}).values()}
        for seed, final in mapping.items():
            p = pages.get(final)
            if not p or "missing" in p or "disambiguation" in (p.get("pageprops") or {}):
                print("  dropped:", seed)
                continue
            ok[seed] = final
        time.sleep(1)
    return ok


def main():
    resolved = {}
    for pillar, titles in SEEDS.items():
        v = validate(titles)
        resolved[pillar] = list(dict.fromkeys(v.values()))
        print(f"{pillar}: {len(resolved[pillar])} valid of {len(titles)}")
    # round-robin interleave: myth, history, origin, myth, ...
    order, seen = [], set()
    for i in range(max(len(x) for x in resolved.values())):
        for pillar in ("myth", "history", "origin"):
            if i < len(resolved[pillar]) and resolved[pillar][i] not in seen:
                seen.add(resolved[pillar][i])
                order.append({"title": resolved[pillar][i], "pillar": pillar})
    (HERE / "topics.json").write_text(json.dumps(order, indent=1, ensure_ascii=False), encoding="utf-8")
    print("topics.json:", len(order), "topics")


if __name__ == "__main__":
    main()
