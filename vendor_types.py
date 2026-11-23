"""vendor_types.py — what kind of payee a vendor is.

The vendor graph is only worth reading if a link means two committees share an
OPERATIVE: a consultant, pollster, mail house, media buyer, fundraiser. The
document-frequency cap in build_vendor_factions.py drops vendors almost every
committee pays (Office Depot, USPS), but anything paid by fewer than ~100
committees slipped through it: Ruth's Chris, the IRS, the Board of Ethics,
Total Wine, the hotels. Those are errands, not alliances. And TV and radio
stations, cable reps and newspapers tie committees together only because they
bought airtime in the same market; Louisiana Airwaves and Louisiana Dial cover
that money. So every payee gets one of five types, and only `operative` and
`field` payees can make an edge:

    operative  consultants, pollsters, mail and print, media buyers, fundraisers,
               compliance, lawyers: the signal
    field      a private individual paid for canvassing, election-day or other
               campaign labour. Counted (a shared field operation is real
               signal) but never named on the page: they are not public figures
    media      TV and radio stations, cable ad sellers, newspapers, billboards
    commodity  restaurants, hotels, travel, retail, software and platforms,
               banks and payment processors
    civic      government, taxes and fees, schools, churches, chambers, clubs,
               charities, party and caucus dues

Classification uses the payee's name first and, for names that don't decide it,
how committees described what they paid it for (summed by dollars across every
filing). It is deliberately conservative toward `operative`: a payee is dropped
only when its name or its paid-for descriptions say it is something else.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, 'media_calls.json'), encoding='utf-8') as f:
    CALLS = set(json.load(f)['calls'])

def _rx(words):
    return re.compile(r'\b(' + '|'.join(words) + r')\b')

# ── name rules ────────────────────────────────────────────────────────────────
_MEDIA_NAME = _rx([
    r'[KW][A-Z]{2,3} ?-? ?(TV|AM|FM|LD|CD|DT|AM FM|RADIO|TELEVISION)',
    'AMPERSAND', 'COMCAST', 'SPECTRUM REACH', 'SPECTRUM', 'CHARTER COMMUNICATIONS',
    'VIAMEDIA', 'VIA MEDIA', 'ALTICE', 'DIRECTV', 'DISH NETWORK', 'EATEL',
    r'COX (CABLE|MEDIA|COMMUNICATIONS?|REACH)', 'CLEAR CHANNEL', 'IHEART ?MEDIA',
    'IHEART', 'CUMULUS', 'TOWNSQUARE', 'AUDACY', 'ENTERCOM', r'[A-Z ]*BROADCASTING',
    'LOUISIANA RADIO NETWORK', 'GRAY (TELEVISION|MEDIA)', 'NEXSTAR', 'TEGNA',
    'HEARST', 'LAMAR', 'OUTFRONT', r'[A-Z ]*OUTDOOR', 'BILLBOARDS?',
    'NEWS', 'NEWSPAPERS?', 'HERALD', 'GAZETTE', 'TIMES', 'TRIBUNE', 'JOURNAL',
    'WEEKLY', 'DEMOCRAT', 'INDEPENDENT', 'ADVOCATE', 'PICAYUNE', 'ADVERTISER',
    'ENTERPRISE', 'INDEX', 'COMET', 'GAMBIT', 'POST SOUTH', 'DAILY WORLD',
    'ILLUMINATOR', 'INQUISITOR', 'MAGAZINE', 'STAR', 'NEWSWATCH', 'JAMBALAYA NEWS',
    'LA CALLE', 'GANNETT', 'GEORGES MEDIA', 'NEWSPAPER',
])
_CIVIC_NAME = _rx([
    'IRS', 'INTERNAL REVENUE', 'TREASURY', 'DEPARTMENT OF REVENUE', r'DEPT OF [A-Z ]+',
    'DEPARTMENT OF', 'BOARD OF ETHICS', 'ETHICS ADMINISTRATION', 'SECRETARY OF STATE',
    r'CLERK OF [A-Z ]*COURT', 'CLERK OF COURT', 'SHERIFF S OFFICE', 'SHERIFF',
    r'[A-Z ]*PARISH', 'CITY OF', 'TOWN OF', 'VILLAGE OF', 'STATE OF LOUISIANA',
    r'LOUISIANA (SENATE|HOUSE)', r'LA (SENATE|HOUSE)', 'HOUSE OF REPRESENTATIVES',
    'STATE TREASURER', 'WORKFORCE COMMISSION', 'POST ?MASTER', 'POSTAL', 'USPS',
    'POST OFFICE', 'UNITED STATES', 'US TREASURY', 'AIRPORT', 'RECREATION DISTRICT',
    r'HIGH SCHOOL', 'SCHOOL', 'ACADEMY', 'UNIVERSITY', 'COLLEGE', 'CHURCH',
    'BAPTIST', 'CATHOLIC', 'METHODIST', 'MINISTRIES', 'MINISTRY', 'TEMPLE',
    'FIRE DEPARTMENT', 'VOLUNTEER FIRE', 'POLICE', 'AMERICAN CANCER', 'RED CROSS',
    'NAACP', 'BOOSTER', 'ATHLETIC ASSOCIATION', 'CIVIC ASSOC', 'CIVIC ASSOCIATION',
    'HOMEOWNERS', 'FOUNDATION', 'CHAMBER OF COMMERCE', 'CHAMBER', 'LIONS CLUB',
    'ROTARY', 'JAYCEES', 'KIWANIS', 'OPTIMIST', 'KREWE', 'MARDI GRAS', 'FESTIVAL',
    'FAIR', 'FAIR DAY', 'BAR ASSOCIATION', 'REPUBLICAN WOMEN', 'DEMOCRATIC WOMEN',
    r'FEDERATION OF [A-Z ]*WOMEN', 'CAUCUS', 'LLBC', 'DELTA SIGMA THETA',
    'ALPHA KAPPA ALPHA', 'OMEGA PSI PHI', 'KAPPA ALPHA PSI', 'SORORITY', 'FRATERNITY',
    'AMERICAN LEGION', 'VFW', r'MEMORIAL POST', 'GRANT A WISH', 'CASA OF',
    'YOUTH CENTER', 'CIVIC CENTER', 'BUSINESS ASSOCIATION', 'CIVIC', 'NEIGHBORHOOD', '^ALEC$', 'AMERICAN LEGISLATIVE EXCHANGE',
    'NATIONAL CONFERENCE', 'MAIN STREET', 'LEGISLATIVE DELEGATION', 'LA DEMOCRATS',
    r'(DEMOCRATIC|REPUBLICAN) PARTY', 'RURAL CAUCUS', 'NICHOLLS STATE',
])
_COMMODITY_NAME = _rx([
    # money movement
    'BANK', 'BANCORP', 'BANCSHARES', 'CREDIT UNION', 'HANCOCK WHITNEY', 'WHITNEY',
    'CAPITAL ONE', 'CHASE BANK', 'CHASE CARD', 'REGIONS', 'AMERICAN EXPRESS', 'AMEX', 'CITI CARDS',
    'CITIBANK', 'CARDMEMBER', 'DISCOVER', 'PAYPAL', 'STRIPE', 'SQUARE', 'VANTIV',
    'LITLE', 'ACTBLUE', 'ACTBLUE TECHNICAL SERVICES', 'WINRED', 'ANEDOT', 'BB&T',
    'BB T', 'TRUIST', 'SYNCHRONY', 'WELLS FARGO', 'ELECTRONIC BUSINESS SYSTEMS',
    'DELUXE', 'PITNEY BOWES', 'PURCHASE POWER', 'OFFICE DEPOT', 'OFFICEMAX',
    'STAPLES', 'INSURANCE', 'STATE FARM', 'LIBERTY BANK', 'FIRST GUARANTY',
    'COMMUNITY FIRST', 'HUCKABY', 'IBERIABANK', 'JPMORGAN', 'BUSEY',
    # platforms, software, phones
    'FACEBOOK', 'META', 'GOOGLE', 'YOUTUBE', 'TWITTER', 'MICROSOFT', 'APPLE',
    'ADOBE', 'DROPBOX', 'ZOOM', 'MAILCHIMP', 'CONSTANT CONTACT', 'GODADDY',
    'SQUARESPACE', 'WIX', 'CANVA', 'VERIZON', 'AT&T', 'AT T', 'T-MOBILE',
    'SPRINT', 'AMAZON', 'STAMPS COM', 'INTUIT', 'QUICKBOOKS', 'SLACK', 'HOTELS COM',
    'EXPEDIA', 'AIRBNB', 'VRBO', 'UBER', 'UBER TECHNOLOGIES', 'LYFT', 'DOORDASH',
    'GRUBHUB', 'SOUTHWEST', 'DELTA AIR', 'AMERICAN AIRLINES', 'UNITED AIRLINES',
    'AIRLINES?', 'CAR RENTAL', 'HERTZ', 'AVIS', 'NATIONAL CAR', 'ENTERPRISE RENT',
    'PARKING', 'PARKMOBILE', 'NEW SOUTH PARKING', 'MICROSOFT STORE',
    # retail and fuel
    'WALMART', 'SAM S', 'COSTCO', 'HOME DEPOT', 'LOWES', 'LOWE S',
    'HARDWARE', 'KOHL S', 'DICK S SPORTING', 'BASS PRO', 'CABELA S', 'CABELAS',
    'ACADEMY SPORTS', 'KUIU', 'ULINE', 'SHELL', 'EXXON', 'CHEVRON', 'RACETRACK',
    'CIRCLE K', 'MURPHY USA', 'TOBACCO', 'TWO MEN', 'U-HAUL', 'HOBBY LOBBY',
    'MICHAELS', 'PARTY CITY', 'PARTY RENTALS', 'PARTY EXPRESS', 'DOLLAR',
    'FLORIST', 'FLOWERS', 'BEADS', 'FRAME SHOPPE', 'BOUTIQUE', 'TRUMP INTERNATIONAL',
    'FURNITURE', 'STICKER MULE', 'STICKERGIANT', 'DECORATING', 'DECOR', 'BALLOONS?',
    'ARTISTRY', 'SALON', 'SPA', 'TUXEDO', 'JEWELERS?',
    # food, drink, lodging, venues
    'RESTAURANTS?', 'RESTAURANT GROUP', 'CAFE', 'GRILL', 'GRILLE', 'BISTRO',
    'BISTREAUX', 'STEAK', 'STEAKHOUSE', 'STEAK HOUSE', 'PIZZA', 'BURRITO',
    'CATERING', 'CATERER', 'CATERS', 'EATERY', 'EAT PLACE', 'KITCHEN', 'BBQ',
    'BAR', 'PUB', 'BREW', 'BREW PUB', 'BREWING', 'DONUTS?', 'BAKERY', 'CAKES?',
    'SMOKEHOUSE', 'DINER', 'SEAFOOD', 'SUSHI', 'SAKE', 'SHACK', 'MARKET',
    'SUPERMARKET', 'GROCERY', 'FOOD STORE', 'FOODS', 'MEAT MARKET', 'BUTCHER',
    'LIQUOR', 'WINE', 'WINES', 'SPIRITS', 'HOTEL', 'HOTELS', 'INN', 'SUITES',
    'MARRIOTT', 'COURTYARD', 'HILTON', 'HAMPTON INN', 'HYATT', 'SHERATON', 'WESTIN',
    'RENAISSANCE', 'FOUR SEASONS', 'CASINO', 'RESORT', 'COUNTRY CLUB', 'GOLF',
    'HUNTING CLUB', 'CITY CLUB', 'LAKEHOUSE', 'CUISINE', 'ROADHOUSE', 'TAVERN',
    'BENTLEY ROOM', 'RUTH S CHRIS', 'COMMANDER S PALACE', 'BRENNAN S', 'MANSURS',
    'GINO S', 'RUFFINO S', 'BYBLOS', 'ZOES', 'MELLOW MUSHROOM', 'NEWK S',
    'LOUIE S', 'MIDDENDORF S', 'CHIMES', 'WALK-ON S', 'COPELAND S', 'MATTINA BELLA',
    'FAT BOY S', 'FAT DADDY S', 'SUREWAY', 'MATHERNE S', 'ROUSE S', 'SAVE A LOT',
    'BIN Q', 'BOULEVARD BISTRO', 'SCHLITTZ', 'RICCOBONO S', 'HEROMAN S',
    'LE PETIT', 'FREMIN S', 'CASHIO S', 'SUGAH RUSH', 'BENOIT S', 'PAT S DOWNTOWN',
    'STAB S', 'DRAKES', 'HEIRLOOM', 'CITY PORK', 'SHAKE SHACK',
    'MESSINA S', 'DESIGNS IN CATERING', 'GIACONA', 'DIAMOND GRILL', 'JACMEL',
    'PARAGON CASINO', 'EDGE OF THE LAKE', 'THE CROSSING', 'TCHEFUNCTA',
    'CHATEAU', 'SQUIRE CREEK', 'OAK GROVE', 'SUGARLAND', 'ARTIE S', 'CHAMPION RANCH',
    'LONELY LANE', 'GATR', 'IZZO S', 'SOUTHERN HOTEL',
    'RACELAND', 'CUISINE LOUISIANE', 'KALURAH', 'BOSTON RESTAURANT', 'ESYNCS',
])

# ── description rules (summed by dollars) ─────────────────────────────────────
_DESC_COMMODITY = _rx([
    'FOOD', 'MEALS?', 'DINNER', 'LUNCH', 'BREAKFAST', 'CATER(ING)?', 'REFRESHMENTS?',
    'DRINKS', 'BEVERAGES?', 'RECEPTION', 'HOTEL', 'LODGING', 'ROOM', 'TRAVEL',
    'AIRFARE', 'FLIGHT', 'PARKING', 'GAS', 'FUEL', 'MILEAGE', 'RENTAL CAR',
    'OFFICE SUPPLIES', 'SUPPLIES', 'POSTAGE', 'SHIPPING', 'BANK', 'FEES?', 'TAX(ES)?',
    'DUES', 'MEMBERSHIP', 'TICKETS?', 'SPONSOR(SHIP)?', 'AD IN PROGRAM', 'PROGRAM AD',
    'FILING', 'QUALIFYING', 'PHONE', 'CELL', 'INTERNET', 'SOFTWARE', 'SUBSCRIPTION',
    'RENT', 'UTILITIES', 'EQUIPMENT', 'FURNITURE', 'DONATION', 'GIFTS?', 'FLOWERS',
    'ENTERTAINMENT', 'GOLF', 'TOURNAMENT', 'FUNDRAISER EVENT', 'VENUE', 'BAR TAB',
    'LIQUOR', 'WINE', 'ICE',
])
_DESC_OPERATIVE = _rx([
    'CONSULT(ING|ANT|ANTS)?', 'MAIL(ERS?|ING|OUTS?)?', 'DIRECT MAIL', 'PRINT(ING)?',
    'POLL(ING)?', 'SURVEY', 'MEDIA', 'MEDIA BUY', 'ADVERTIS(ING|EMENT)', 'ADS?',
    'PRODUCTION', 'DIGITAL', 'FUNDRAIS(ING|ER FEES?)', 'COMMISSION', 'STRATEG(Y|IC)',
    'MANAGEMENT', 'MANAGER', 'DESIGN', 'SIGNS?', 'YARD SIGNS', 'PUSH CARDS?',
    'PHOTO(GRAPHY)?', 'VIDEO', 'WEB(SITE)?', 'RESEARCH', 'COMPLIANCE', 'ACCOUNTING',
    'LEGAL', 'PUBLIC RELATIONS', 'PR', 'COMMUNICATIONS', 'TEXT(ING)?', 'ROBO ?CALLS?',
    'PHONE BANK', 'DATA', 'LIST', 'VOTER FILE', 'TARGETING', 'SPEECH', 'PRESS',
])
FIELD_DESC = _rx([
    'CANVASS(ING|ER|ERS)?', 'ELECTION DAY', 'POLL ?WATCH(ER|ING)?', 'POLL WORKERS?',
    'WORKERS?', 'GOTV', 'GET OUT THE VOTE', 'SLATE CARDS?', 'DOOR ?(TO ?DOOR|KNOCK)',
    'BLOCK WALK', 'WALKERS?', 'DRIVERS?', 'TRANSPORT(ATION)?', 'LABOR', 'STIPEND',
    'VOLUNTEERS?', 'SIGN (PLACEMENT|CREW|INSTALL)', 'PUT(TING)? UP SIGNS',
    'HANDBILLS?', 'DISTRIBUT(E|ION|ING)', 'POLLING PLACE', 'RIDES TO POLLS',
    'STAFF', 'CAMPAIGN WORKER', 'HELPER', 'FIELD',
])

# Money given to a candidate or committee that the gift filter in the build
# missed: blank-coded rows naming a district or election, or a stray
# "contribution" on a person.
_DESC_POLITICAL = _rx([
    'CONTRIBUTIONS?', 'DONATIONS?', r'DIST', 'DISTRICT[0-9]*', 'PRIMARY',
    'ELECTION', 'RUNOFF', 'REIMBURSE(MENT)?', 'IN-KIND', 'LOAN', 'REFUND',
])

# A business-looking word anywhere in the name means it is not a private person.
_BUSINESS = _rx([
    'CONSULT[A-Z]*', 'MEDIA', 'GROUP', 'STRATEG[A-Z]*', 'PRINT[A-Z]*', 'PRESS',
    'SIGNS?', 'COMMUNICATIONS?', 'PHOTO[A-Z]*', 'DESIGNS?', 'SOLUTIONS', 'SERVICES?',
    'ENTERPRISES?', 'ASSOCIATES', 'PARTNERS', 'PRODUCTIONS?', 'RESEARCH', 'POLLING',
    'MARKETING', 'ADVERTISING', 'CREATIVE', 'DIGITAL', 'AGENCY', 'FIRM', 'LAW',
    'ATTORNEYS?', 'CPA', 'CPAS', 'STUDIOS?', 'GRAPHICS?', 'SPECIALTIES', 'SYSTEMS',
    'HOLDINGS', 'VENTURES', 'NETWORK', 'STRATEGIES', 'PUBLIC', 'AFFAIRS', 'DATA',
    'INTELLIGENCE', 'GLOBAL', 'IMPACT', 'CAMPAIGNS', 'POLITICAL', 'WORKS', 'SHOP',
    'SOUND', 'AUDIO', 'VISION', 'IDEAS', 'NATIONAL', 'AMERICAN', 'SOUTHERN',
    'LOUISIANA', 'BAYOU', 'CAPITOL', 'CAPITAL', 'COMPANY', 'TECHNOLOGIES', 'LABS',
    'INDUSTRIES', 'TRUCK', 'CENTER', 'CLUB', 'OF', 'THE', 'AND', '&', 'STAFFING',
    'SCREENPRINTING', 'EMBROIDERY', 'APPAREL', 'PROMOS?', 'PROMOTIONS', 'OUTFITTERS',
])
_PERSON = re.compile(r'^[A-Z]{1,15}( [A-Z]{1,15}){1,3}$')

def name_type(key):
    """Type decided by the name alone, or None when the name doesn't decide it."""
    first = key.split()[0] if key else ''
    if first in CALLS or first.split('-')[0] in CALLS or _MEDIA_NAME.search(key):
        return 'media'
    if _CIVIC_NAME.search(key):
        return 'civic'
    if _COMMODITY_NAME.search(key):
        return 'commodity'
    return None

def looks_like_person(key):
    return bool(_PERSON.match(key)) and not _BUSINESS.search(key)

def classify(key, desc_dollars, candidates=frozenset()):
    """desc_dollars: $ by desc_bucket(). candidates: normalized names of everyone
    who has run for office in Louisiana (the Secretary of State's history)."""
    t = name_type(key)
    if t:
        return t
    op, com, fld, pol = (desc_dollars.get(k, 0.0)
                         for k in ('operative', 'commodity', 'field', 'political'))
    if looks_like_person(key):
        # Paid mostly for field work: a private individual, counted but unnamed.
        if fld and fld >= op + com + pol:
            return 'field'
        # A former or current candidate paid as a person is almost always a
        # contribution coded as an expenditure (Gil Pinac, Buddy Caldwell).
        if key in candidates or (pol and pol >= op):
            return 'civic'
        # A named professional (fundraiser, consultant) is a public operative;
        # anyone else paid as a person is a private individual and stays anonymous.
        return 'operative' if op > fld + com else 'field'
    if pol > op and pol > com:
        return 'civic'
    if com > 2 * op and com > fld:
        return 'commodity'
    return 'operative'

def desc_bucket(desc):
    d = (desc or '').upper()
    if not d.strip():
        return 'blank'
    if FIELD_DESC.search(d):
        return 'field'
    if _DESC_POLITICAL.search(d):
        return 'political'
    if _DESC_OPERATIVE.search(d):
        return 'operative'
    if _DESC_COMMODITY.search(d):
        return 'commodity'
    return 'blank'
