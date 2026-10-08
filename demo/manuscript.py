"""The demo manuscript: ONE source of truth for the Word, Overleaf and
Markdown versions (demo/build_demo.py renders all three from it).

Everything here is invented: the country, the districts, the authors, the
numbers and every reference. No sentence is taken from any paper, thesis,
course or guide. The prose is meant to be good scientific writing apart
from the deliberate errors listed in demo/README.md, so that Researchly's
precision shows: every flag on this manuscript should be a planted one.

Inline markup inside paragraph text (rendered per format by build_demo.py):

    {ref:fig:KEY} {ref:tab:KEY} {ref:eq:KEY}   a cross-reference
                                               ("Figure 1" / \\ref{fig:KEY})
    {citep:KEY,KEY}                            parenthetical citation
    {citet:KEY}                                textual citation "Lim et al. (2021)"
    {citeyearpar:KEY}                          just "(2021)" (after a name in prose)
    {m:LATEX|UNICODE}                          inline maths

Blocks: P (paragraph), H (heading, level 1 or 2), Eq (displayed equation),
Fig (figure), Tab (table). Floats carry the number their caption shows; the
LaTeX build emits floats in that order so LaTeX numbers them the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TITLE = ("A compartmental model of one dengue season in three districts "
         "of Velmora")
AUTHORS = ["Ingrid Varden", "Teodor Kalnis"]
AFFILIATION = "Centre for Outbreak Analytics, University of Velmora"
KEYWORDS = ["dengue", "SEIR model", "transmission", "Bayesian inference"]


@dataclass
class P:
    text: str


@dataclass
class H:
    text: str
    level: int = 1


@dataclass
class Eq:
    key: str
    latex: str
    unicode: str
    number: int


@dataclass
class Fig:
    key: str
    number: int
    file: str
    caption: str


@dataclass
class Tab:
    key: str
    number: int
    caption: str
    header: list
    rows: list = field(default_factory=list)


# Cross-reference targets that exist nowhere: the number the Word and
# Markdown text prints for them (the LaTeX text uses \ref{KEY} instead).
MISSING_REFS = {"fig:missing": 3}

# --- made-up references (author-year) ----------------------------------------
# key -> (short form for the text, year, BibTeX fields)
REFERENCES = {
    "haraldsen2017": dict(
        short="Haraldsen and Okonkwo", year=2017,
        author="Haraldsen, Mira and Okonkwo, Dele",
        title="Three decades of dengue surveillance in Velmora",
        journal="Velmoran Journal of Public Health", volume="41",
        pages="112--121"),
    "oyelaran2019": dict(
        short="Oyelaran and Mbeki", year=2019,
        author="Oyelaran, Femi and Mbeki, Lindiwe",
        title="Rainfall, temperature and the timing of dengue seasons in "
              "lowland districts",
        journal="Tropical Vector Reports", volume="8", pages="45--58"),
    "lim2021": dict(
        short="Lim et al.", year=2021,
        author="Lim, Wei Ting and Castellano, Paula and Adeyemi, Bola",
        title="Reproduction numbers of dengue from weekly case counts: a "
              "renewal approach",
        journal="Annals of Transmission Modelling", volume="14",
        pages="201--219"),
    "quintero2020": dict(
        short="Quintero", year=2020,
        author="Quintero, Alma",
        title="Estimating the reproduction number of arboviruses with "
              "renewal equations",
        journal="Bulletin of Computational Epidemics", volume="5",
        pages="77--90"),
    "nakamura2022": dict(
        short="Nakamura and Petrov", year=2022,
        author="Nakamura, Sora and Petrov, Ilya",
        title="Incubation and infectious periods of dengue: a synthesis of "
              "cohort estimates",
        journal="Proceedings of the Society for Outbreak Analysis",
        volume="19", pages="330--341"),
}

# --- the figures' made-up data (weekly reported cases, 26 weeks) -------------
WEEKS = list(range(1, 27))
DISTRICTS = ["Marrowick", "Tessvale", "Oldmere"]
CASES = {
    "Marrowick": [6, 9, 14, 21, 33, 48, 70, 96, 128, 160, 184, 196, 190, 171,
                  146, 118, 92, 70, 52, 38, 27, 19, 14, 10, 7, 5],
    "Tessvale": [3, 4, 5, 7, 10, 14, 19, 26, 35, 47, 61, 76, 90, 101, 108,
                 106, 96, 82, 66, 51, 38, 28, 20, 14, 10, 7],
    "Oldmere": [2, 2, 3, 4, 5, 7, 9, 12, 16, 21, 27, 33, 40, 46, 51, 54, 56,
                53, 47, 40, 32, 25, 18, 13, 9, 6],
}
POPULATION = {"Marrowick": 45_800, "Tessvale": 37_500, "Oldmere": 33_200}


def _district_rows():
    rows = []
    for d in DISTRICTS:
        n = sum(CASES[d])
        rows.append([d, f"{POPULATION[d]:,}", f"{n:,}",
                     f"{100 * n / POPULATION[d]:.1f}"])
    return rows


TOTAL_CASES = sum(sum(v) for v in CASES.values())
# The model's fitted median and interval are drawn as a smoothed version
# of the counts (build_demo.py); the numbers below are what the tables say.
TABLE_DISTRICTS = Tab(
    key="tab:districts", number=1,
    caption=("Study districts: population, reported dengue cases from "
             "April to September 2022, and attack rate."),
    header=["District", "Population", "Reported cases", "Attack rate (%)"],
    rows=_district_rows(),
)
TABLE_PARAMS = Tab(
    key="tab:params", number=2,
    caption=("Posterior medians and 95% credible intervals of the "
             "district-specific parameters."),
    header=["District", "Basic reproduction number", "Reporting fraction",
            "Peak of seasonal term (week)"],
    rows=[["Marrowick", "2.1 (1.8 to 2.4)", "0.26 (0.21 to 0.31)",
           "12 (11 to 13)"],
          ["Tessvale", "1.7 (1.5 to 1.9)", "0.23 (0.19 to 0.28)",
           "13 (12 to 14)"],
          ["Oldmere", "1.4 (1.2 to 1.6)", "0.21 (0.17 to 0.26)",
           "13 (12 to 15)"]],
)

FIG_CASES = Fig(key="fig:cases", number=1, file="fig1_weekly_cases.png",
                caption="Weekly reported dengue cases.")
FIG_FIT = Fig(key="fig:fit", number=2, file="fig2_model_fit.png",
              caption=("Model fit to the weekly case reports in each "
                       "district. Points are reported cases; the line is "
                       "the posterior median of the fitted model and the "
                       "shaded band its 95% posterior predictive "
                       "interval. Week 1 is the first week of April "
                       "2022."))

EQ_FOI = Eq(key="eq:foi", number=1,
            latex=r"\lambda_i(t) = \beta_i(t)\,\frac{I_i(t)}{N_i}",
            unicode="λᵢ(t) = βᵢ(t) Iᵢ(t) / Nᵢ")
EQ_R0 = Eq(key="eq:r0", number=2,
           latex=r"R_{0,i} = \frac{\beta_i(0)}{\gamma}",
           unicode="R₀,ᵢ = βᵢ(0) / γ")

# --- the manuscript ------------------------------------------------------------

ABSTRACT = [
    P("Dengue returns to the lowland districts of Velmora every year, and "
      "the size of each season varies widely between districts. However, "
      "the drivers of this variation remain unclear, because routine "
      "surveillance reports cases without the timing of the transmission "
      "behind them. We aimed to estimate district-specific transmission "
      "intensity for the 2022 season. We fitted a deterministic "
      "susceptible, exposed, infectious, recovered (SEIR) model with a "
      "seasonal transmission rate to weekly case reports from three "
      "districts, using Hamiltonian Monte Carlo. The model reproduced the "
      "timing of the peak in every district. We found that the basic "
      "reproduction number was highest in Marrowick (2.1, 95% credible "
      "interval 1.8 to 2.4) "
      "and lowest in Oldmere (1.4, 1.2 to 1.6), and the attack rate ranged "
      "from 1.9% to 4.2%."),
]

BODY = [
    H("Introduction"),
    P("Dengue is the most widespread mosquito-borne viral infection of "
      "people, and its incidence in Velmora has risen in each of the past "
      "three decades {citep:haraldsen2017}. Transmission is known to be "
      "sensitive to temperature, because the extrinsic incubation period "
      "(EIP) of the virus in the mosquito shortens as the air warms. In "
      "the lowland districts the season starts after the first rains, "
      "peaks within two to three months and then fades as the mosquito "
      "population declines {citep:oyelaran2019}. Each season is seeded by "
      "infections that persist through the dry months at low levels, and "
      "its size depends on how quickly transmission builds once the "
      "mosquito population recovers."),
    P("Routine surveillance records when cases are reported, not when "
      "people were infected, so the weekly counts lag transmission by the "
      "incubation period in the person and by the reporting delay. Several "
      "studies have estimated the reproduction number of dengue from case "
      "counts, most of them with an renewal model "
      "{citep:lim2021,quintero2020}. A renewal model describes how one "
      "generation of cases produces the next, but it does not separate "
      "the people who are infectious from the people who are still "
      "incubating, and it says nothing about how many people remain "
      "susceptible at the end of a season. A compartmental model can "
      "separate these groups, and fitting it to several districts at once "
      "shows whether the districts differ in transmission or only in "
      "reporting. However, no compartmental model has been fitted to "
      "district-level case reports from Velmora, and the shorter EIP of "
      "the warmest districts has not been linked to their earlier "
      "seasons."),
    P("We therefore aimed to estimate district-specific transmission rates "
      "for the 2022 season, and to ask whether the differences between "
      "districts could be explained by the size of the susceptible "
      "population alone."),

    H("Methods"),
    H("Study setting and data", 2),
    P("Velmora reports dengue cases weekly from every public clinic to a "
      "national register. We used the counts from three districts, "
      "Marrowick, Tessvale and Oldmere, for the 26 weeks from the first "
      "week of April to the last week of September 2022. The three "
      "districts differ in population size and in the density of housing, "
      "and together they reported {total_cases} cases over the season "
      "({ref:tab:districts}). A case was any person with fever and a "
      "positive rapid antigen test. We did not have the dates of symptom "
      "onset, so we treated the the week of the clinic visit as the week "
      "of onset."),
    H("Transmission model", 2),
    P("We modelled each district with a deterministic SEIR model in which "
      "people move from the susceptible compartment to the exposed, "
      "infectious and recovered compartments in turn. The mosquito was not "
      "modelled explicitly; instead the transmission rate carried a "
      "seasonal term that stands for the effect of temperature on the "
      "extrinsic incubation period (EIP) and on mosquito abundance. The "
      "force of infection in district {m:i|i} is the rate at which a "
      "susceptible person becomes infected; it is given by"),
    EQ_FOI,
    P("where {m:\\beta_i(t)|βᵢ(t)} is the seasonal transmission rate, "
      "{m:I_i(t)|Iᵢ(t)} the number of infectious people and "
      "{m:N_i|Nᵢ} the population of the district. The seasonal term in "
      "{ref:eq:foi} was a cosine with a period of one year, so that each "
      "district had its own baseline rate, amplitude and phase. People "
      "left the exposed compartment at rate {m:\\sigma|σ}, the inverse of "
      "the intrinsic incubation period, and the infectious compartment at "
      "rate {m:\\gamma|γ}. The basic reproduction number at the start of "
      "the season follows from the ratio of these rates."),
    EQ_R0,
    P("We fixed the mean intrinsic incubation period at 5.9 days and the "
      "mean infectious period at 5 days, following {citet:nakamura2022}, "
      "and estimated the baseline rate, the amplitude and the phase of the "
      "seasonal term, and the reporting fraction for each district. The "
      "initial number of infectious people in each district was estimated "
      "as a free parameter."),
    H("Statistical inference", 2),
    P("We assumed that the reported count in each week followed a negative "
      "binomial distribution around the model's incidence multiplied by "
      "the reporting fraction. We fitted the model to the three districts "
      "jointly, with a hierarchical prior on the baseline transmission "
      "rate, using Hamiltonian Monte Carlo in four chains of 2,000 "
      "iterations. The baseline transmission rate had a log-normal prior "
      "centred on a basic reproduction number of 2, with a between-district "
      "standard deviation estimated from the data. The amplitude of the "
      "seasonal term had a uniform prior between 0 and 1, the phase a "
      "uniform prior over the year, and the reporting fraction a beta "
      "prior with mean 0.25, the national estimate of the fraction of "
      "infections that lead to a clinic visit {citep:haraldsen2017}. "
      "Convergence was judged by the split R-hat statistic and "
      "the effective sample size. We report posterior medians with 95% "
      "credible intervals (CrI). We checked the fit by comparing the "
      "posterior predictive distribution of the weekly counts with the "
      "data, and we ran a seperate fit for each district to confirm that "
      "the hierarchical prior had not pulled the estimates together."),

    H("Results"),
    P("The model reproduced the rise, peak and decline of reported cases "
      "in all three districts, and the posterior predictive interval "
      "covered 74 of the 78 weekly counts ({ref:fig:fit}). The four weeks "
      "outside the interval were all in the first month of the season, "
      "when counts were small and the initial conditions dominated. The "
      "peak came "
      "in week 12 in Marrowick, three weeks earlier than in "
      "Tessvale and five weeks earlier than in Oldmere ({ref:fig:cases}). "
      "Figure 1 shows that all three districts were close to their "
      "seasonal minimum by the end of September."),
    P("Reported incidence varied more than twofold between districts. The "
      "attack rate was 4.8% in Marrowick, compared with 1.9% in Oldmere "
      "({ref:tab:districts}). The basic reproduction number from "
      "{ref:eq:r0} was highest in Marrowick, at 2.1 (95% CrI 1.8 to 2.4), "
      "and lowest in Oldmere, at 1.4 (95% CrI 1.2 to 1.6). The estimated "
      "reporting fraction was similar in all three districts, between "
      "0.21 and 0.26, so the differences in reported incidence reflected "
      "differences in transmision rather than in reporting."),
    FIG_CASES,
    FIG_FIT,
    TABLE_DISTRICTS,
    TABLE_PARAMS,
    P("The seasonal term peaked between week 12 and week 13 in every "
      "district, about two weeks after the mean weekly temperature peaked. "
      "The fraction of the population still susceptible at the end of the "
      "season was above 0.9 everywhere, so the season ended because "
      "transmission fell with the weather, not because the susceptible "
      "pool was exhausted. The separate fits gave estimates within the "
      "credible intervals of the joint fit."),

    H("Discussion"),
    P("We fitted an SEIR model to one dengue season in three districts and "
      "found that transmission, not reporting, explained the differences "
      "between them. The earlier and larger season in Marrowick was "
      "consistent with its higher housing density, which brings people "
      "and mosquitoes closer together. A similar lead of the densest "
      "district was shown by Lim and colleagues {citeyearpar:lim2021} in "
      "a neighbouring region. This proves that housing density explains "
      "the difference between districts. Our estimates of the basic "
      "reproduction number lie within the range that {citet:quintero2020} "
      "reported for lowland settings with a renewal model, which suggests "
      "that the choice of model matters less for the reproduction number "
      "than for the susceptible fraction, which a renewal model cannot "
      "report."),
    P("The seasonal term peaked about two weeks after the temperature "
      "did, which matches the delay expected from the EIP: a warm week "
      "shortens the EIP, and the extra infectious mosquitoes appear one "
      "to two weeks later. The same delay was found in the lowland "
      "districts of the neighbouring region {citep:oyelaran2019}, where "
      "the seasons start about a month earlier than in Velmora."),
    P("The lag between the peaks in the three districts ({ref:fig:missing}) "
      "may possibly suggest that the virus moved outward from Marrowick "
      "along the main road, but weekly counts cannot show the direction of "
      "spread. A model with movement between districts would need case "
      "data with finer timing than the week of the clinic visit."),
    P("Our study has three limitations. First, we had no onset dates, so "
      "the week of the clinic visit stood in for the week of infection, "
      "which blurs the timing by about one week. Second, the model treats "
      "each district as well mixed and ignores movement between them. "
      "Third, the seasonal term absorbs every driver that varies with the "
      "calendar, so we cannot separate temperature from rainfall or from "
      "school holidays, and the EIP enters only through that term."),
    P("The estimates have one practical use. Because most residents were "
      "still susceptible at the end of the season, the next season will "
      "not be limited by immunity, and vector control before the first "
      "rains would have the most effect in Marrowick, where transmission "
      "starts first."),

    H("Conclusion"),
    P("An SEIR model fitted jointly to three districts reproduced one "
      "dengue season and showed that the districts differed in "
      "transmission intensity rather than in reporting. The approach needs "
      "only routine weekly counts, and it could be run at the end of each "
      "season to rank districts for vector control in the next one."),
]

FLOATS = {f.key: f for f in BODY if isinstance(f, (Fig, Tab))}
EQUATIONS = {e.key: e for e in BODY if isinstance(e, Eq)}
