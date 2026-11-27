"""Explicit, documented text rules shared by the Data Insights page and notebooks/eda.ipynb.

Every rule here is a case-insensitive PostgreSQL regular expression that is passed
to SQL as a bound parameter, so the same definitions drive the notebook and the
dashboard. The rules only classify metadata text in read-only queries; the raw
values stored in PostgreSQL are never changed.
"""

# ---------------------------------------------------------------------------
# Insight 1: the five missions examined in the 2013 vs. 2014 KSC Earth subset.
# A record counts for a mission when its title or keywords mention the mission.
# ---------------------------------------------------------------------------
PEAK_MISSIONS = {
    "Orion / EFT-1": r"\morion\M|\meft-1\M|exploration flight test",
    "Morpheus / ALHAT": r"\mmorpheus\M|\malhat\M",
    "OCO-2": r"\moco-2\M|orbiting carbon observatory",
    "TDRS": r"\mtdrs|tracking and data relay",
    "SMAP": r"\msmap\M|soil moisture active passive",
}

# The subset studied in Insight 1 (passed to SQL as parameters).
PEAK_CENTER = "KSC"
PEAK_TOPIC = "earth"
PEAK_YEARS = (2013, 2014)

# ---------------------------------------------------------------------------
# Insight 2: what kind of record a title describes.
# ---------------------------------------------------------------------------

# A title made only of an archive ID (for example "KSC-2011-7368" or
# "iss068e054895") tells us nothing about the image content.
ID_ONLY_TITLE = r"^[A-Za-z]{0,6}[-_]?[0-9][-_A-Za-z0-9]*$"

# Earth photography taken by station or shuttle crews, e.g. "Earth Observations
# taken by the Expedition 38 crew". These titles mention "crew" but show Earth,
# so they are checked before the operations rule.
EARTH_OBSERVATION_TITLE = r"earth observ"

# The first keyword list from our earlier experiment (word-start matching).
OPERATIONS_WORDS_V1 = [
    "launch", "briefing", "ceremony", "crew", "astronaut", "processing", "testing",
    "integration", "splashdown", "recovery", "operations", "encapsulation", "assembly",
    "preflight", "construction", "payload", "deployment", "inspection", "installation",
]

# Words added after reading a fixed sample of titles that the first list missed
# (see Section 2 of the notebook). Whole-word matching.
OPERATIONS_WORDS_ADDED = [
    "liftoff", "lift-off", "rollout", "roll-out", "rollback", "stacking", "fairing", "booster",
    "mate", "mating", "offload", "arrival", "hoist", "transport", "installed", "installing",
    "test", "tests", "cleanroom", "clean room", "technicians?", "engineers?", "training",
    "spacewalk", "eva", "dock", "docks", "docking", "undock", "undocks", "undocked",
    "rendezvous", "countdown", "walkout", "suit-?up", "readiness review", "press conference",
    "news conference", "media day", "visits?", "tour", "award", "celebration", "anniversary",
    "parade", "mockup",
]


def _whole_words(words):
    """Build one whole-word regex, trying longer phrases first."""
    return r"\m(" + "|".join(sorted(words, key=len, reverse=True)) + r")\M"


OPERATIONS_TITLE_V1 = r"\m(" + "|".join(OPERATIONS_WORDS_V1) + r")"
OPERATIONS_TITLE = _whole_words(OPERATIONS_WORDS_V1 + OPERATIONS_WORDS_ADDED)

# Content groups shown in the Insight 2 chart, in display order.
CONTENT_GROUPS = [
    "Operations, people & engineering",
    "Earth photography by crews",
    "Other descriptive title",
    "ID-only title",
]

# ---------------------------------------------------------------------------
# Insight 3: mission and program aliases, matched in titles and keywords.
# Broad words such as "Earth", "NASA", or "Mission" are deliberately not missions.
# ---------------------------------------------------------------------------
MISSION_ALIASES = {
    "Artemis program (incl. EM-1)": r"\martemis\M|\mem-1\M|exploration mission[- ]1\M",
    "2001 Mars Odyssey": r"mars odyssey",
    "Orion spacecraft (incl. EFT-1)": r"\morion\M(?!\s+nebula)|\meft-1\M|exploration flight test",
    "Space Shuttle": r"space shuttle|\msts-?[0-9]{1,3}\M",
    "Space Launch System (SLS)": r"\msls\M|space launch system",
    "International Space Station": r"international space station|\miss\M",
    "Mars Exploration Rovers": r"mars exploration rover",
    "Mars Global Surveyor": r"mars global surveyor",
    "Cassini-Huygens": r"\mcassini\M|\mhuygens\M",
    "Mars Reconnaissance Orbiter": r"mars reconnaissance orbiter|\mmro\M|\mhirise\M",
    "Perseverance / Mars 2020": r"mars 2020|\mperseverance\M",
    "MESSENGER": r"\mmessenger\M",
    "Curiosity / Mars Science Laboratory": r"mars science laboratory|\mcuriosity\M",
    "Juno": r"\mjuno\M",
    "Commercial Crew Program": r"commercial crew",
}

# Location values grouped by what they describe. Checked in order; first match wins.
LOCATION_GROUPS = {
    "Launch sites & launch processing": (
        r"kennedy|\mksc|cape canaveral|ccafs|vandenberg|vafb|baikonur|wallops|"
        r"mid-atlantic regional spaceport|\mvab\M|vehicle assembly|\mo&c\M|operations and checkout|"
        r"\mphsf\M|\msspf\M|astrotech|launch (complex|pad|control)|\mslc-|\mlc[- ]?39|pad 39|shuttle landing|\mslf\M|"
        r"\mlcc\M|firing room|processing facilit|payload hazardous|mobile launcher|\mipf\M|\mvsfb\M|\mrpsf\M|"
        r"\mmppf\M|guiana|kourou|turn basin|cosmonaut hotel|saturn v building"
    ),
    "Landing & recovery areas": r"zhezkazgan|dzhezkazgan|kazakhstan|pacific ocean|atlantic ocean|san diego|splashdown",
    "NASA centers & offices": (
        r"headquarter|\mhq\M|greenbelt|goddard|michoud|jet propulsion|\mjpl\M|pasadena|glenn|plum brook|"
        r"\mafrc\M|armstrong|edwards|johnson|houston|marshall|huntsville|ames|moffett|langley|hampton|"
        r"stennis|white sands|washington|new orleans|\mmsfc\M|mission control"
    ),
    "In orbit": r"\miss\M|international space station|\morbit",
}
OTHER_LOCATION = "Other places"
