"""Curated word lists. Deliberately conservative: precision over recall.

Sources: the project's writing-craft guide (§4, §6, §9), the AJE 2022
causal-language word lists (Am J Epidemiol), and standard plain-language
style references. Every list is easy to audit and extend — auditable rules
are a trust feature (research/04).
"""

# --- W201: single grand words → plain alternatives -------------------------
# (employ/leverage/elucidate added from the lecture's avoid-list, which treats
#  them as needlessly grand where plain 'use' or 'clarify' would do)
GRAND_WORDS = {
    "utilize": "use", "utilizes": "uses", "utilized": "used",
    "utilizing": "using", "utilization": "use", "utilisation": "use",
    "utilise": "use", "utilises": "uses", "utilised": "used",
    "commence": "begin", "commences": "begins", "commenced": "began",
    "endeavor": "try", "endeavour": "try",
    "ascertain": "determine",
    "necessitates": "requires", "necessitate": "require",
    "leverage": "use", "leverages": "uses", "leveraged": "used",
    "elucidate": "clarify", "elucidates": "clarifies",
    "elucidated": "clarified",
}
# Grand only as verbs: "financial leverage" and "this endeavour" are nouns,
# and "use"/"try" would make nonsense of them (P33).
GRAND_ONLY_AS_VERB = frozenset({
    "leverage", "leverages", "leveraged", "endeavor", "endeavour"})

# --- S001: Latin phrases of academic and legal English -----------------------
# "ad valorem" was read as the lone word "valorem" and corrected to "galore"
# (owner's assignment, 2026-10-08). A word is skipped when it and a
# neighbour form one of these.
LATIN_PHRASES = frozenset({
    "ad valorem", "ad hoc", "ad libitum", "ad infinitum", "a priori",
    "a posteriori", "a fortiori", "per capita", "per se", "per annum",
    "per diem", "pro rata", "pro forma", "pro bono", "de facto", "de jure",
    "de novo", "ex ante", "ex post", "ex vivo", "ex officio", "in situ",
    "in vitro", "in vivo", "in silico", "in utero", "in toto", "in extremis",
    "inter alia", "intra vitam", "prima facie", "bona fide", "mutatis mutandis",
    "ceteris paribus", "status quo", "vice versa", "sine qua non", "sui generis",
    "post hoc", "post mortem", "ante mortem", "ipso facto", "modus operandi",
    "non sequitur", "quid pro quo", "et cetera", "et al", "sensu lato",
    "sensu stricto", "viva voce", "nota bene", "sic passim", "circa",
})
_LATIN_WORDS = frozenset(w for ph in LATIN_PHRASES for w in ph.split())

# --- W202: wordy phrases → tighter alternatives ----------------------------
WORDY_PHRASES = {
    "due to the fact that": "because",
    "owing to the fact that": "because",
    "despite the fact that": "although",
    "in spite of the fact that": "although",
    "in order to": "to",
    "prior to": "before",
    "subsequent to": "after",
    "at this point in time": "now",
    "in the event that": "if",
    "in close proximity to": "near",
    "by means of": "by",
    "has the ability to": "can",
    "have the ability to": "can",
    "whether or not": "whether",
    "in excess of": "more than",
    "a majority of": "most",
    "the majority of": "most",
    "a large number of": "many",
    "it is possible that": "possibly / may",
    "in the absence of": "without",
    "period of time": "period",
}

# --- W203: hype / buzzwords -------------------------------------------------
HYPE_WORDS = (
    "novel", "cutting-edge", "state-of-the-art", "groundbreaking",
    "ground-breaking", "paradigm-shifting", "revolutionary", "unprecedented",
    "game-changing",
)
# "novel coronavirus/pathogen/variant..." is technical usage, not hype.
HYPE_TECHNICAL_FOLLOWERS = (
    "coronavirus", "virus", "pathogen", "variant", "strain", "influenza",
    "serotype", "antigen", "compound", "species", "host",
)

# --- W204: intensifiers (Preference) ---------------------------------------
INTENSIFIERS = ("very", "extremely", "really", "incredibly", "hugely",
                "tremendously", "massively")

# --- W205: filler / throat-clearing ----------------------------------------
FILLER_PHRASES = (
    "it should be noted that",
    "it is important to note that",
    "it is worth noting that",
    "it is interesting to note that",
    "it must be mentioned that",
    "needless to say",
    "as a matter of fact",
    "it goes without saying that",
)

# --- W206: redundant pairs --------------------------------------------------
REDUNDANT_PAIRS = {
    "each and every": "every",
    "first and foremost": "first",
    "full and complete": "complete",
    "basic fundamentals": "fundamentals",
    "end result": "result",
    "final outcome": "outcome",
    "past history": "history",
    "advance planning": "planning",
    "completely eliminate": "eliminate",
    "close proximity": "proximity",
    "exactly identical": "identical",
    "general consensus": "consensus",
    "mutual cooperation": "cooperation",
    "small in size": "small",
    "brief in duration": "brief",
    "future prospects": "prospects",
}

# --- W208: contractions -----------------------------------------------------
CONTRACTIONS = (
    "don't", "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't",
    "can't", "couldn't", "won't", "wouldn't", "shouldn't", "hasn't",
    "haven't", "hadn't", "it's", "we're", "we've", "we'll", "they're",
    "there's", "that's", "let's", "i'm", "you're", "what's", "who's",
)

# --- C301: hedges -----------------------------------------------------------
HEDGE_TOKENS = {
    "may", "might", "could", "possibly", "potentially", "perhaps",
    "presumably", "apparently", "seemingly", "arguably", "somewhat",
    "likely", "suggest", "suggests", "suggested", "appear", "appears",
    "appeared", "seem", "seems", "seemed", "tentatively", "conceivably",
}

# --- C302: overclaiming -----------------------------------------------------
OVERCLAIM_PATTERNS = (
    r"\bproves?\b", r"\bproved\b", r"\bproven\b",
    r"\bconclusively\b", r"\bdefinitively\b", r"\bunambiguously\b",
    r"\bbeyond (?:any )?doubt\b", r"\bundoubtedly\b",
    r"\bestablishes that\b",
)

# --- C303: causal verbs (AJE 2022-style list) ------------------------------
CAUSAL_VERB_LEMMAS = {
    "cause", "reduce", "increase", "decrease", "improve", "prevent",
    "protect", "drive", "affect", "impact", "lower", "raise", "worsen",
    "mitigate", "avert",
}
CAUSAL_PHRASES = (r"\bleads? to\b", r"\bled to\b", r"\bresults? in\b",
                  r"\bresulted in\b")
# Verbs describing the *authors'* actions are fine ("we increased the
# sample size"); only claims about the world are flagged.
AUTHOR_SUBJECTS = {"we", "i", "author", "authors", "study", "analysis",
                   "model", "simulation", "paper"}

# --- C305: assertive adverbs ------------------------------------------------
ASSERTIVE_PATTERNS = (
    r"\bclearly\b", r"\bobviously\b", r"\bof course\b", r"\bevidently\b",
    r"\bit is clear that\b", r"\bit is obvious that\b",
)

# --- G102: light verbs + nominalization → verb ------------------------------
LIGHT_VERBS = {"perform", "conduct", "make", "carry", "undertake", "execute",
               "do", "provide", "achieve", "accomplish"}
NOMINAL_TO_VERB = {
    "estimation": "estimate", "comparison": "compare", "analysis": "analyse",
    "analyses": "analyse", "investigation": "investigate",
    "assessment": "assess", "evaluation": "evaluate",
    "examination": "examine", "measurement": "measure",
    "calculation": "calculate", "computation": "compute",
    "implementation": "implement", "identification": "identify",
    "validation": "validate", "simulation": "simulate",
    "estimations": "estimate", "comparisons": "compare",
    "calibration": "calibrate", "optimization": "optimise",
    "optimisation": "optimise", "adjustment": "adjust",
    "determination": "determine", "prediction": "predict",
    "description": "describe", "collection": "collect",
    "selection": "select", "derivation": "derive",
}

# --- G103: nominalization suffixes -----------------------------------------
NOMINAL_SUFFIXES = ("tion", "sion", "ment", "ance", "ence", "ency", "ancy")
NOMINAL_MIN_LEN = 7
# Common words that end in these suffixes but read fine / aren't derived
NOMINAL_ALLOWLIST = {
    "attention", "information", "population", "distribution", "proportion",
    "question", "section", "equation", "function", "position", "condition",
    "government", "environment", "moment", "element", "document",
    "experiment", "department", "instrument", "treatment", "science",
    "evidence", "confidence", "difference", "prevalence", "incidence",
    "influence", "absence", "presence", "sentence", "reference",
    "transmission", "emission", "session", "profession", "dimension",
    "infection", "intervention", "vaccination", "surveillance", "variance",
    "importance", "significance", "frequency", "tendency", "emergency",
    "agency", "region", "religion", "version", "mention",
}

# --- G108: weak stress-position trailers ------------------------------------
TRAILING_QUALIFIERS = (
    r", according to [^,.;]+$",
    r", as (?:shown|seen|reported|illustrated|demonstrated) (?:in|by) [^,.;]+$",
    r", in (?:our|this) (?:study|analysis|simulations?|model)$",
)

# --- E7xx: rules mined from the owner's lecture notes on scientific writing -

# E701: low-information phrases that sound substantive but say nothing
# (the lecture, 'Information density')
EMPTY_PHRASES = (
    "holistic understanding",
    "comprehensive understanding of the complex",
    "sheds light on", "shed light on", "shedding light on",
    "paves the way for", "pave the way for",
    "provides valuable insights into", "provide valuable insights into",
    "provides important insights into",
    "helps to inform", "help to inform",
    "a wide range of applications",
)

# E703: verbs after a naked sentence-initial "This"
NAKED_THIS_VERBS = {
    "is", "was", "has", "can", "could", "may", "might", "will", "would",
    "suggests", "indicates", "means", "implies", "shows", "demonstrates",
    "allows", "highlights", "raises", "reflects", "leads", "led",
    "results", "resulted", "supports", "confirms", "underscores",
}

# E704: consensus claims that need an owner or a citation
CONSENSUS_RX = (r"\b(?:is|are)\s+(?:widely\s+|generally\s+|commonly\s+)?"
                r"(?:known|considered|believed|thought|recognized|"
                r"recognised|regarded|assumed)\s+to\b")

# E705: absolute novelty claims (risky without "to our knowledge")
NOVELTY_RX = (
    r"\b(?:has|have)\s+(?:never\s+|not\s+)(?:yet\s+)?been\s+"
    r"(?:studied|investigated|explored|examined|reported|done|addressed|"
    r"quantified|characteri[sz]ed|assessed)\b"
    r"|\bno\s+(?:prior\s+|previous\s+)?(?:study|studies|work|research)\s+"
    r"(?:has|have|exists?)\b",
)
KNOWLEDGE_SOFTENERS = ("to our knowledge", "to the best of our knowledge",
                       "as far as we are aware", "we are not aware")

# E707: display-first openers in Results (lead with the finding instead)
FIGURE_OPENER_RX = (r"^\s*(?:Figure|Fig\.?|Table|Supplementary\s+"
                    r"(?:Figure|Table))\s+\S+\s+"
                    r"(?:shows?|presents?|displays?|illustrates?|depicts?|"
                    r"summari[sz]es?|provides?|gives?|lists?)\b")

# --- AB801: vague forward references in abstracts (Belcher/Schultz) ---------
ABSTRACT_VAGUE_RX = (r"\b(?:results?|findings?|implications?|data|outcomes?)"
                     r"\s+(?:will|shall)\s+be\s+"
                     r"(?:discussed|presented|explored|described|reported|"
                     r"examined)\b")

# --- L901: serial-summary literature-review openers (the course, unit 1) --------
LITREVIEW_FILLER = (
    r"\bthere\s+(?:are|have\s+been|is\s+a\s+growing\s+body\s+of)\s+"
    r"(?:many|several|numerous|various|a\s+number\s+of)?\s*"
    r"(?:studies|articles|papers|reports|researchers|works?)\b",
    r"\bmuch\s+research\s+has\s+been\s+(?:done|conducted|carried\s+out)\b",
    r"\bmany\s+(?:studies|researchers|authors|scholars)\s+have\s+"
    r"(?:studied|investigated|examined|explored|looked\s+at|reported)\b",
)

# --- F601: acronyms ---------------------------------------------------------
ACRONYM_ALLOWLIST = {
    # ubiquitous general/scientific
    "USA", "UK", "US", "EU", "UN", "PDF", "DOI", "URL", "ID", "AI", "IT",
    # ubiquitous biomedical/epi (assume audience knows)
    "DNA", "RNA", "HIV", "AIDS", "COVID", "SARS", "MERS", "PCR", "WHO",
    "CDC", "NHS", "NIH", "ICU", "BMI",
    # statistics reporting conventions
    "CI", "SD", "SE", "IQR", "OR", "RR", "HR", "AIC", "BIC", "MCMC",
    "ESS", "HMC", "NUTS", "GLM", "GAM", "ODE", "SIR", "SEIR", "SEIRD",
    # P31 (Q3): reporting conventions and names, not abbreviations to define
    "GDP", "UV", "ROC", "AUC",
    "BMJ", "BMC", "PLOS", "JAMA", "NEJM",          # journal names
    # currency codes (dogfooding: "SGD$10 (~USD8)")
    "SGD", "USD", "EUR", "GBP", "CNY", "JPY", "INR", "MYR", "IDR", "THB",
}

# --- Metadiscourse meter (Hyland's interactional resources; the course, unit 2) ------
# Boosters assert certainty; the hedge/booster balance is a calibration
# read-out ("confidence without cockiness" — Wellington et al.).
BOOSTER_TOKENS = {
    "clearly", "obviously", "certainly", "definitely", "undoubtedly",
    "always", "never", "must", "evidently", "indeed", "conclusively",
    "definitively", "unquestionably", "demonstrably", "surely",
    "established", "establishes", "proven", "proves",
}
SELF_MENTION_TOKENS = {"we", "our", "us", "i", "my"}

# --- W210: variant consistency ("one term, one meaning") --------------------
# Curated exact pairs only — algorithmic UK/US transforms create false pairs
# (four/for, filling/filing). Extend freely.
CONSISTENCY_PAIRS = (
    ("modelling", "modeling"), ("modelled", "modeled"),
    ("behaviour", "behavior"), ("behaviours", "behaviors"),
    ("analyse", "analyze"), ("analysed", "analyzed"),
    ("analysing", "analyzing"), ("analyses", "analyzes"),
    ("organisation", "organization"), ("organisations", "organizations"),
    ("optimisation", "optimization"), ("optimise", "optimize"),
    ("optimised", "optimized"),
    ("parameterisation", "parameterization"),
    ("hospitalisation", "hospitalization"),
    ("hospitalisations", "hospitalizations"),
    ("colour", "color"), ("colours", "colors"),
    ("labelled", "labeled"), ("labelling", "labeling"),
    ("centre", "center"), ("centres", "centers"),
    ("standardised", "standardized"), ("standardise", "standardize"),
    ("characterised", "characterized"), ("characterise", "characterize"),
    ("summarised", "summarized"), ("summarise", "summarize"),
    ("generalisability", "generalizability"),
    ("immunisation", "immunization"), ("randomised", "randomized"),
    ("categorised", "categorized"), ("visualisation", "visualization"),
    ("neighbourhood", "neighborhood"), ("neighbourhoods", "neighborhoods"),
    ("favourable", "favorable"), ("favour", "favor"),
)
