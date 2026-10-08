"""The epidemiology pack (S4, P3): four reporting checklists.

STROBE (observational studies), CONSORT (randomised trials), PRISMA
(systematic reviews) and EPIFORGE (epidemic forecasting and prediction,
the owner's own field). Each item is Researchly's paraphrase of a theme
of the published guideline, phrased as a question about the text; the
guidelines are cited by name and never quoted. The selection of items is
the ones a reader can find in prose: items about a title page, a flow
diagram's drawing or a registry form are left out or folded together.

Checks reporting, never the science (P3).
"""

from __future__ import annotations

from . import Checklist, Item, Pack

_INTRO = ("introduction", "abstract")
_METHODS = ("methods",)
_RESULTS = ("results",)
_DISC = ("discussion", "limitations", "conclusion")
_FRONT = ("abstract", "front", "unknown", "other")

_DATES = (r"\b(19|20)\d\d\b",)
_AIM = (r"\b(we|this study|this paper|this analysis)\b[^.]{0,40}\b(aim|aimed|"
        r"set out|sought|seek|hypothesi[sz]ed?|investigat|examin|estimat|"
        r"assess|evaluat|quantif|test)",
        r"\b(objective|aim|purpose|hypothesis)\b")
_LIMITS = (r"\blimitations?\b", r"\bcaveat", r"\bwe (could|can) ?not\b",
           r"\bshould be interpreted (with|in light)\b")
_FUNDING = (r"\bfund(ed|ing|er)\b", r"\bgrant\b", r"\bsupported by\b",
            r"\bfinancial support\b")
_SAMPLE = (r"\bsample size\b", r"\bpower (calculation|analysis)\b",
           r"\bstudy size\b", r"\b\d+% power\b", r"\bpowered to\b")
_ELIGIBILITY = (r"\beligib", r"\binclusion criteria\b",
                r"\bexclusion criteria\b",
                r"\bwere (included|excluded) (if|when|because)\b",
                r"\b(aged|age) (\d+|between)\b")
_CI = (r"\b9[059]\s?%\s?(ci|cri|confidence|credible|uncertainty|prediction)",
       r"\b(confidence|credible|prediction|uncertainty) intervals?\b")

STROBE = Checklist(
    "strobe", "STROBE", "observational studies (cohort, case-control, "
    "cross-sectional)", "STROBE",
    r"\b(cohort|case-control|cross-sectional|observational) (study|design|"
    r"analysis|survey)\b",
    (
        Item("design", "Study design",
             "Does the abstract or the start of the paper name the study "
             "design?",
             "Readers judge everything else by the design: say early "
             "whether it is a cohort, case-control or cross-sectional study.",
             (r"\b(cohort|case-control|cross-sectional|ecological|"
              r"observational) (study|design|analysis|survey)\b",),
             _FRONT + _INTRO),
        Item("objectives", "Objectives",
             "Are the objectives or hypotheses stated?",
             "Say what the study set out to find, so readers can tell a "
             "pre-specified question from a later one.", _AIM, _INTRO),
        Item("setting", "Setting and dates",
             "Do the Methods give the setting, the places and the dates "
             "(recruitment, exposure, follow-up, data collection)?",
             "Where and when the data come from decides who the results "
             "apply to.", _DATES, _METHODS),
        Item("participants", "Participants",
             "Are the eligibility criteria and how participants were "
             "selected described?",
             "Readers need to know who could be in the study, and how they "
             "came to be in it.", _ELIGIBILITY + (r"\brecruit", r"\bselected\b",
                                                  r"\benrolled\b"),
             _METHODS),
        Item("variables", "Variables",
             "Are the outcomes, exposures and potential confounders defined?",
             "Each variable needs a definition a reader could apply.",
             (r"\b(outcome|exposure|confounder|covariate|effect modifier)s?\b",
              r"\bdefined as\b"), _METHODS),
        Item("measurement", "Data sources and measurement",
             "Do the Methods say where each variable came from and how it "
             "was measured?",
             "The source and the measurement decide how much error the "
             "data carry.",
             (r"\bmeasured\b", r"\bquestionnaire\b", r"\bregist(er|ry)\b",
              r"\b(medical|health|clinical) records\b", r"\bsurveillance\b",
              r"\bdata (were|was) (obtained|collected|extracted|drawn)\b"),
             _METHODS),
        Item("bias", "Bias",
             "Is anything said about possible sources of bias and how they "
             "were addressed?",
             "Every observational study has some; naming them shows the "
             "reader you looked.", (r"\bbias(es|ed)?\b",), _METHODS + _DISC),
        Item("study-size", "Study size",
             "Is it explained how the study size was arrived at?",
             "A reader cannot judge a null result without knowing what the "
             "study could have detected.", _SAMPLE, _METHODS),
        Item("statistics", "Statistical methods",
             "Are the statistical methods described, including how "
             "confounding was handled?",
             "The analysis is part of the result: say what was adjusted for "
             "and how.",
             (r"\bregression\b", r"\badjust(ed|ing|ment) for\b",
              r"\bstratif", r"\bpropensity\b", r"\bstatistical analys"),
             _METHODS),
        Item("missing-data", "Missing data",
             "Is it said how missing data were handled?",
             "Missing data can bias any estimate; readers need to know "
             "whether cases were dropped or imputed.",
             (r"\bmissing (data|values|information|observations)\b",
              r"\bimput", r"\bcomplete[- ]case\b"), _METHODS + _RESULTS),
        Item("flow", "Participant numbers",
             "Do the Results give the numbers at each stage (eligible, "
             "included, analysed) and why people dropped out?",
             "Losses along the way can change who the results describe.",
             (r"\b\d[\d,]*\s+(participants|patients|individuals|people|"
              r"children|adults|cases|households)\b[^.]{0,60}\b(were )?"
              r"(included|excluded|eligible|enrolled|analysed|analyzed|"
              r"followed)\b",
              r"\blost to follow[- ]up\b", r"\bflow (diagram|chart)\b"),
             _RESULTS),
        Item("descriptive", "Characteristics",
             "Are the participants' characteristics described?",
             "Readers compare your population with theirs before using your "
             "results.",
             (r"\bcharacteristics\b", r"\b(median|mean) age\b",
              r"\bbaseline\b"), _RESULTS),
        Item("estimates", "Main results with precision",
             "Are the main estimates given with their precision, adjusted "
             "and unadjusted where relevant?",
             "An estimate without its interval cannot be weighed.",
             _CI + (r"\b(odds|hazard|risk|rate) ratio\b",), _RESULTS),
        Item("limitations", "Limitations",
             "Does the Discussion state the limitations, including bias and "
             "imprecision?",
             "A limitation you state is a boundary; one a reviewer finds is "
             "a rebuttal.", _LIMITS, _DISC),
        Item("generalisability", "Generalisability",
             "Does the Discussion say to whom the results apply?",
             "Readers need to know whether your setting is like theirs.",
             (r"\bgenerali[sz]", r"\bexternal validity\b",
              r"\b(apply|applicable|transferable) to\b",
              r"\bother (settings|populations|countries|regions)\b"), _DISC),
        Item("funding", "Funding", "Is the source of funding stated?",
             "Readers weigh results knowing who paid for them.", _FUNDING),
    ))

CONSORT = Checklist(
    "consort", "CONSORT", "randomised controlled trials", "CONSORT",
    r"\brandomi[sz]ed (controlled |clinical )?trial\b|\brandomly "
    r"(assigned|allocated)\b",
    (
        Item("design", "Identified as randomised",
             "Does the abstract or the start of the paper say the trial was "
             "randomised?",
             "Randomisation is what lets a trial support a causal claim; "
             "say it at once.", (r"\brandomi[sz]ed\b", r"\brandomly\b"),
             _FRONT + _INTRO),
        Item("objectives", "Objectives",
             "Are the specific objectives or hypotheses stated?",
             "The trial's question decides its primary outcome.", _AIM,
             _INTRO),
        Item("trial-design", "Trial design",
             "Is the design described (parallel, crossover, cluster, "
             "factorial) with the allocation ratio?",
             "The design decides how the results must be analysed.",
             (r"\b(parallel|crossover|cross-over|cluster|factorial|"
              r"stepped[- ]wedge)\b", r"\ballocation ratio\b",
              r"\b\d:\d\b"), _METHODS),
        Item("participants", "Participants and setting",
             "Are the eligibility criteria and the settings where data were "
             "collected given?",
             "Readers need to know whom the trial could enrol, and where.",
             _ELIGIBILITY, _METHODS),
        Item("interventions", "Interventions",
             "Is each group's intervention described well enough to repeat?",
             "An intervention a reader cannot reproduce cannot be adopted.",
             (r"\binterventions?\b", r"\bcontrol (group|arm)\b",
              r"\bplacebo\b", r"\b(usual|standard) care\b",
              r"\b(received|were given|was given)\b"), _METHODS),
        Item("outcomes", "Outcomes",
             "Are the primary and secondary outcomes defined, with when "
             "they were measured?",
             "A pre-specified primary outcome protects against choosing the "
             "result after seeing the data.",
             (r"\bprimary (outcome|end ?point)\b",
              r"\bsecondary (outcome|end ?point)s?\b"), _METHODS),
        Item("sample-size", "Sample size",
             "Is it explained how the sample size was determined?",
             "A reader cannot judge a null result without the power.",
             _SAMPLE, _METHODS),
        Item("sequence", "Random sequence",
             "Is the method used to generate the random allocation sequence "
             "described?",
             "How the sequence was made is what makes the allocation random.",
             (r"\b(random|randomisation|randomization) (number|sequence|"
              r"list|schedule)\b", r"\bcomputer[- ]generated\b",
              r"\b(block|stratified|permuted) randomi"), _METHODS),
        Item("concealment", "Allocation concealment",
             "Is it said how the allocation was concealed until assignment?",
             "Without concealment, whoever enrols participants can steer "
             "the groups.",
             (r"\bconceal", r"\bsealed\b[^.]{0,30}\benvelopes?\b",
              r"\bcentral(ly|ised|ized)? randomi"), _METHODS),
        Item("blinding", "Blinding",
             "Is it said who was blinded after assignment, and how?",
             "Knowing the group can change how outcomes are reported and "
             "assessed.",
             (r"\bblind(ed|ing)?\b", r"\bmasked\b", r"\bopen[- ]label\b"),
             _METHODS),
        Item("statistics", "Statistical methods",
             "Are the methods for comparing groups described?",
             "Readers need the analysis that produced the effect estimate.",
             (r"\bintention[- ]to[- ]treat\b", r"\bper[- ]protocol\b",
              r"\bregression\b", r"\bstatistical analys", r"\bcompared\b"),
             _METHODS),
        Item("flow", "Participant flow",
             "Do the Results give the numbers randomised, treated and "
             "analysed in each group, with losses and reasons?",
             "Unequal losses between groups can undo randomisation.",
             (r"\b\d[\d,]*\s+(participants|patients|people|children|adults)"
              r"\b[^.]{0,60}\b(were )?(randomi[sz]ed|allocated|assigned|"
              r"analysed|analyzed)\b",
              r"\blost to follow[- ]up\b", r"\bdiscontinued\b",
              r"\bflow (diagram|chart)\b"), _RESULTS),
        Item("recruitment", "Recruitment dates",
             "Are the dates of recruitment and follow-up given?",
             "When the trial ran affects how far its results carry.", _DATES,
             _METHODS + _RESULTS),
        Item("estimates", "Effect size and precision",
             "Is each outcome's effect given with its precision?",
             "An effect without its interval cannot be weighed.",
             _CI + (r"\b(relative|absolute) risk\b", r"\brisk difference\b",
                    r"\bdifference (between|in)\b"), _RESULTS),
        Item("harms", "Harms",
             "Are harms or unintended effects reported?",
             "A treatment's benefits mean little without its harms.",
             (r"\badverse (event|effect|reaction)s?\b", r"\bharms?\b",
              r"\bside[- ]effects?\b", r"\bsafety\b")),
        Item("limitations", "Limitations",
             "Does the Discussion address the trial's limitations?",
             "State the sources of bias and imprecision yourself.", _LIMITS,
             _DISC),
        Item("registration", "Registration and protocol",
             "Are the trial registration and where to find the protocol "
             "given?",
             "Registration lets a reader check that the reported outcomes "
             "are the planned ones.",
             (r"\bregist(ered|ration|ry)\b", r"\bNCT\d{6,}\b",
              r"\bISRCTN\d+\b", r"\bprotocol\b")),
        Item("funding", "Funding", "Are the sources of funding stated?",
             "Readers weigh results knowing who paid for them.", _FUNDING),
    ))

PRISMA = Checklist(
    "prisma", "PRISMA", "systematic reviews and meta-analyses", "PRISMA",
    r"\bsystematic (literature )?review\b|\bmeta-analys[ie]s\b",
    (
        Item("design", "Identified as a systematic review",
             "Does the abstract or the start of the paper say this is a "
             "systematic review or meta-analysis?",
             "Readers expect different things from a systematic review than "
             "from a narrative one.",
             (r"\bsystematic (literature )?review\b", r"\bmeta-analys"),
             _FRONT + _INTRO),
        Item("objectives", "Objectives",
             "Is the review's question stated?",
             "The question decides what the review searched for.", _AIM,
             _INTRO),
        Item("eligibility", "Eligibility criteria",
             "Are the inclusion and exclusion criteria given?",
             "Readers need to know which studies could have been included.",
             _ELIGIBILITY + (r"\bstudies were (eligible|included)\b",),
             _METHODS),
        Item("sources", "Information sources",
             "Are the databases and other sources searched named, with the "
             "date of the last search?",
             "The sources decide what the review could have found.",
             (r"\b(pubmed|medline|embase|scopus|web of science|cochrane|"
              r"cinahl|psycinfo|google scholar|lilacs)\b",
              r"\bdatabases?\b[^.]{0,40}\bsearched\b"), _METHODS),
        Item("search", "Search strategy",
             "Is the search strategy given, or where to find it?",
             "A search a reader cannot repeat cannot be checked.",
             (r"\bsearch (strategy|terms|string|strings)\b",
              r"\bboolean\b", r"\bmesh\b", r"\bkeywords?\b"), _METHODS),
        Item("selection", "Selection process",
             "Is it said how studies were selected, and by how many "
             "reviewers working independently?",
             "Independent screening guards against one reader's bias.",
             (r"\bindependently\b", r"\btwo (reviewers|authors|"
              r"investigators)\b", r"\bscreened\b",
              r"\btitles? and abstracts?\b"), _METHODS),
        Item("extraction", "Data collection",
             "Is the data extraction process described?",
             "Readers need to know how numbers moved from papers into the "
             "review.", (r"\bextract(ed|ion)\b", r"\bdata collection\b"),
             _METHODS),
        Item("risk-of-bias", "Risk of bias",
             "Is it said how the risk of bias of each study was assessed?",
             "A pooled estimate is only as sound as the studies in it.",
             (r"\brisk of bias\b", r"\bquality assessment\b",
              r"\bnewcastle[- ]ottawa\b", r"\brob ?2\b",
              r"\bcritical appraisal\b"), _METHODS),
        Item("synthesis", "Synthesis methods",
             "Are the methods of synthesis described (pooling model, "
             "heterogeneity)?",
             "How results were combined decides what the summary means.",
             (r"\brandom[- ]effects?\b", r"\bfixed[- ]effects?\b",
              r"\bpooled\b", r"\bnarrative synthesis\b",
              r"\bheterogeneity\b"), _METHODS),
        Item("certainty", "Certainty of evidence",
             "Is it said how the certainty of the body of evidence was "
             "judged?",
             "Readers need to know how much weight the conclusion bears.",
             (r"\bgrade\b", r"\bcertainty of (the )?evidence\b",
              r"\bquality of (the )?evidence\b")),
        Item("flow", "Study selection",
             "Do the Results give the numbers of records identified, "
             "screened and included?",
             "The flow from search to inclusion shows what was left out.",
             (r"\brecords?\b[^.]{0,40}\b(identified|screened|retrieved)\b",
              r"\bfull[- ]text\b", r"\bflow (diagram|chart)\b",
              r"\b\d[\d,]*\s+(studies|articles|records|trials)\b"),
             _RESULTS),
        Item("results", "Synthesis results",
             "Are the summary estimates given with their precision and "
             "heterogeneity?",
             "A pooled estimate without its interval and heterogeneity "
             "cannot be weighed.", _CI + (r"\bi\s?(\^)?2\b",
                                           r"\bheterogeneity\b"), _RESULTS),
        Item("limitations", "Limitations",
             "Does the Discussion address the limitations of the evidence "
             "and of the review?", "Say what the review could not do.",
             _LIMITS, _DISC),
        Item("registration", "Registration",
             "Is the review's registration or protocol given?",
             "Registration shows the methods were set before the results.",
             (r"\bprospero\b", r"\bregist(ered|ration)\b", r"\bprotocol\b")),
        Item("funding", "Funding", "Are the sources of funding stated?",
             "Readers weigh results knowing who paid for them.", _FUNDING),
    ))

EPIFORGE = Checklist(
    "epiforge", "EPIFORGE", "epidemic forecasts, projections and "
    "predictions", "EPIFORGE",
    r"\b(forecast(s|ed|ing)?|nowcast(s|ed|ing)?|projections?)\b[^.]{0,50}"
    r"\b(epidemic|outbreak|cases|incidence|hospitali[sz]ations|admissions|"
    r"deaths|peak|transmission)\b|\bscenario model",
    (
        Item("design", "Identified as a forecast",
             "Does the abstract or the start of the paper say the study "
             "makes a forecast, projection or prediction?",
             "Forecasts are judged differently from explanatory models; say "
             "which this is.",
             (r"\bforecast", r"\bnowcast", r"\bprojection", r"\bpredict"),
             _FRONT + _INTRO),
        Item("purpose", "Purpose and user",
             "Is it said what the forecast is for and who will use it?",
             "A forecast is made for a decision; naming it lets readers "
             "judge whether the targets fit.",
             (r"\binform(ing|s)? (the )?(response|decisions?|planning|policy|"
              r"public health)", r"\bdecision[- ]makers?\b",
              r"\bpolicymakers\b", r"\bpublic health (response|planning|"
              r"authorities)\b"), _INTRO + _METHODS),
        Item("target", "Forecast target",
             "Is the target defined: which quantity, in which population, "
             "at what resolution?",
             "'Cases' can mean reported, confirmed or estimated; say which, "
             "where, and per week or per day.",
             (r"\b(forecast|predict|project)(ed|s|ing)?\b[^.]{0,60}\b("
              r"cases|incidence|peak|deaths|hospitali[sz]ations|admissions|"
              r"attack rate)\b", r"\btarget\b"), _INTRO + _METHODS),
        Item("horizon", "Horizon",
             "Is the forecast horizon given (how far ahead)?",
             "Accuracy falls with the horizon; readers need it to weigh any "
             "number.",
             (r"\bhorizons?\b", r"\b(weeks?|days?|months?) ahead\b",
              r"\b\d+-(week|day|month)[- ]ahead\b"), _INTRO + _METHODS),
        Item("data", "Data sources",
             "Are the data sources described, with whether they are "
             "available to others?",
             "A forecast is only as good as its inputs, and reusable only "
             "if they are.",
             (r"\bsurveillance\b", r"\bdata (were|was) (obtained|collected|"
              r"drawn|downloaded)\b", r"\bpublicly available\b",
              r"\bregist(er|ry)\b"), _METHODS),
        Item("data-issues", "Data quality and delays",
             "Is it said how reporting delays, under-reporting or revisions "
             "of the data were handled?",
             "Real-time data are incomplete; a forecast that ignores it "
             "inherits the bias.",
             (r"\breporting (delay|fraction|rate|probability)\b",
              r"\bunder-?report", r"\bbackfill", r"\bright[- ]truncat",
              r"\bnowcast", r"\bascertainment\b"), _METHODS),
        Item("model", "Model description",
             "Is the model described well enough to reproduce: its "
             "structure and type?",
             "Readers need to know what produced the numbers.",
             (r"\b(seir|sir|seirs|compartmental|renewal|branching process|"
              r"agent-based|arima|regression|ensemble|machine learning|"
              r"mechanistic|statistical) (model|approach|equation)",),
             _METHODS),
        Item("assumptions", "Assumptions",
             "Are the model's key assumptions stated?",
             "Assumptions are where forecasts go wrong; readers need them "
             "to judge the output.", (r"\bassum(e|ed|es|ing|ption)",),
             _METHODS),
        Item("parameters", "Parameters",
             "Are the parameters given with how each was estimated or where "
             "it came from?",
             "Fixed values need a source; fitted ones need the method.",
             (r"\bparameters?\b", r"\bpriors?\b", r"\bfixed at\b",
              r"\bcalibrat", r"\bestimated (from|by|using)\b"), _METHODS),
        Item("uncertainty", "Uncertainty",
             "Are forecasts given with their uncertainty (intervals or "
             "quantiles)?",
             "A point forecast without its range invites false confidence.",
             _CI + (r"\bquantiles?\b", r"\bposterior predictive\b",
                    r"\buncertainty\b"), _RESULTS + _METHODS),
        Item("evaluation", "Evaluation",
             "Is the forecasts' performance evaluated with a stated method "
             "or score?",
             "Readers need to know how well past forecasts matched what "
             "happened.",
             (r"\b(mean )?absolute error\b", r"\brmse\b", r"\bmae\b",
              r"\blog(arithmic)? score\b", r"\bcrps\b",
              r"\binterval score\b", r"\bcoverage\b", r"\bout-of-sample\b",
              r"\bheld-out\b", r"\bskill\b", r"\bcalibration of the "
              r"forecasts?\b"), _METHODS + _RESULTS),
        Item("baseline", "Comparison",
             "Are the forecasts compared with a baseline or with other "
             "models?",
             "Accuracy means little until it beats something simple.",
             (r"\bbaseline\b", r"\bnull model\b", r"\bnaive\b",
              r"\bpersistence\b", r"\bcompared with (other|an?) "
              r"(models?|forecasts?)\b"), _METHODS + _RESULTS),
        Item("code", "Code and data availability",
             "Is it said where the code and the data can be found?",
             "Forecasts are reused and rerun; others need the code.",
             (r"\bcode\b[^.]{0,40}\bavailable\b", r"\bgithub\b",
              r"\bzenodo\b", r"\brepository\b", r"\bopen[- ]source\b")),
        Item("limitations", "Limitations",
             "Does the Discussion state the forecast's limitations?",
             "Say where and why the forecast may fail.", _LIMITS, _DISC),
        Item("funding", "Funding", "Are the sources of funding stated?",
             "Readers weigh results knowing who paid for them.", _FUNDING),
    ))

PACK = Pack("epidemiology", "Epidemiology", (STROBE, CONSORT, PRISMA, EPIFORGE))
