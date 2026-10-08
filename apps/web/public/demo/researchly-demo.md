# A compartmental model of one dengue season in three districts of Velmora

Ingrid Varden, Teodor Kalnis

Centre for Outbreak Analytics, University of Velmora

## Abstract

Dengue returns to the lowland districts of Velmora every year, and the size of each season varies widely between districts. However, the drivers of this variation remain unclear, because routine surveillance reports cases without the timing of the transmission behind them. We aimed to estimate district-specific transmission intensity for the 2022 season. We fitted a deterministic susceptible, exposed, infectious, recovered (SEIR) model with a seasonal transmission rate to weekly case reports from three districts, using Hamiltonian Monte Carlo. The model reproduced the timing of the peak in every district. We found that the basic reproduction number was highest in Marrowick (2.1, 95% credible interval 1.8 to 2.4) and lowest in Oldmere (1.4, 1.2 to 1.6), and the attack rate ranged from 1.9% to 4.2%.

Keywords: dengue; SEIR model; transmission; Bayesian inference

## Introduction

Dengue is the most widespread mosquito-borne viral infection of people, and its incidence in Velmora has risen in each of the past three decades (Haraldsen and Okonkwo, 2017). Transmission is known to be sensitive to temperature, because the extrinsic incubation period (EIP) of the virus in the mosquito shortens as the air warms. In the lowland districts the season starts after the first rains, peaks within two to three months and then fades as the mosquito population declines (Oyelaran and Mbeki, 2019). Each season is seeded by infections that persist through the dry months at low levels, and its size depends on how quickly transmission builds once the mosquito population recovers.

Routine surveillance records when cases are reported, not when people were infected, so the weekly counts lag transmission by the incubation period in the person and by the reporting delay. Several studies have estimated the reproduction number of dengue from case counts, most of them with an renewal model (Lim et al., 2021; Quintero, 2020). A renewal model describes how one generation of cases produces the next, but it does not separate the people who are infectious from the people who are still incubating, and it says nothing about how many people remain susceptible at the end of a season. A compartmental model can separate these groups, and fitting it to several districts at once shows whether the districts differ in transmission or only in reporting. However, no compartmental model has been fitted to district-level case reports from Velmora, and the shorter EIP of the warmest districts has not been linked to their earlier seasons.

We therefore aimed to estimate district-specific transmission rates for the 2022 season, and to ask whether the differences between districts could be explained by the size of the susceptible population alone.

## Methods

### Study setting and data

Velmora reports dengue cases weekly from every public clinic to a national register. We used the counts from three districts, Marrowick, Tessvale and Oldmere, for the 26 weeks from the first week of April to the last week of September 2022. The three districts differ in population size and in the density of housing, and together they reported 3,679 cases over the season (Table 1). A case was any person with fever and a positive rapid antigen test. We did not have the dates of symptom onset, so we treated the the week of the clinic visit as the week of onset.

### Transmission model

We modelled each district with a deterministic SEIR model in which people move from the susceptible compartment to the exposed, infectious and recovered compartments in turn. The mosquito was not modelled explicitly; instead the transmission rate carried a seasonal term that stands for the effect of temperature on the extrinsic incubation period (EIP) and on mosquito abundance. The force of infection in district i is the rate at which a susceptible person becomes infected; it is given by

$$ \lambda_i(t) = \beta_i(t)\,\frac{I_i(t)}{N_i} \qquad (1) $$

where βᵢ(t) is the seasonal transmission rate, Iᵢ(t) the number of infectious people and Nᵢ the population of the district. The seasonal term in Equation (1) was a cosine with a period of one year, so that each district had its own baseline rate, amplitude and phase. People left the exposed compartment at rate σ, the inverse of the intrinsic incubation period, and the infectious compartment at rate γ. The basic reproduction number at the start of the season follows from the ratio of these rates.

$$ R_{0,i} = \frac{\beta_i(0)}{\gamma} \qquad (2) $$

We fixed the mean intrinsic incubation period at 5.9 days and the mean infectious period at 5 days, following Nakamura and Petrov (2022), and estimated the baseline rate, the amplitude and the phase of the seasonal term, and the reporting fraction for each district. The initial number of infectious people in each district was estimated as a free parameter.

### Statistical inference

We assumed that the reported count in each week followed a negative binomial distribution around the model's incidence multiplied by the reporting fraction. We fitted the model to the three districts jointly, with a hierarchical prior on the baseline transmission rate, using Hamiltonian Monte Carlo in four chains of 2,000 iterations. The baseline transmission rate had a log-normal prior centred on a basic reproduction number of 2, with a between-district standard deviation estimated from the data. The amplitude of the seasonal term had a uniform prior between 0 and 1, the phase a uniform prior over the year, and the reporting fraction a beta prior with mean 0.25, the national estimate of the fraction of infections that lead to a clinic visit (Haraldsen and Okonkwo, 2017). Convergence was judged by the split R-hat statistic and the effective sample size. We report posterior medians with 95% credible intervals (CrI). We checked the fit by comparing the posterior predictive distribution of the weekly counts with the data, and we ran a seperate fit for each district to confirm that the hierarchical prior had not pulled the estimates together.

## Results

The model reproduced the rise, peak and decline of reported cases in all three districts, and the posterior predictive interval covered 74 of the 78 weekly counts (Figure 2). The four weeks outside the interval were all in the first month of the season, when counts were small and the initial conditions dominated. The peak came in week 12 in Marrowick, three weeks earlier than in Tessvale and five weeks earlier than in Oldmere (Figure 1). Figure 1 shows that all three districts were close to their seasonal minimum by the end of September.

Reported incidence varied more than twofold between districts. The attack rate was 4.8% in Marrowick, compared with 1.9% in Oldmere (Table 1). The basic reproduction number from Equation (2) was highest in Marrowick, at 2.1 (95% CrI 1.8 to 2.4), and lowest in Oldmere, at 1.4 (95% CrI 1.2 to 1.6). The estimated reporting fraction was similar in all three districts, between 0.21 and 0.26, so the differences in reported incidence reflected differences in transmision rather than in reporting.

![Figure 1. Weekly reported dengue cases.](figures/fig1_weekly_cases.png)

Figure 1. Weekly reported dengue cases.

![Figure 2. Model fit to the weekly case reports in each district. Points are reported cases; the line is the posterior median of the fitted model and the shaded band its 95% posterior predictive interval. Week 1 is the first week of April 2022.](figures/fig2_model_fit.png)

Figure 2. Model fit to the weekly case reports in each district. Points are reported cases; the line is the posterior median of the fitted model and the shaded band its 95% posterior predictive interval. Week 1 is the first week of April 2022.

Table 1. Study districts: population, reported dengue cases from April to September 2022, and attack rate.

| District | Population | Reported cases | Attack rate (%) |
|---|---|---|---|
| Marrowick | 45,800 | 1,924 | 4.2 |
| Tessvale | 37,500 | 1,124 | 3.0 |
| Oldmere | 33,200 | 631 | 1.9 |

Table 2. Posterior medians and 95% credible intervals of the district-specific parameters.

| District | Basic reproduction number | Reporting fraction | Peak of seasonal term (week) |
|---|---|---|---|
| Marrowick | 2.1 (1.8 to 2.4) | 0.26 (0.21 to 0.31) | 12 (11 to 13) |
| Tessvale | 1.7 (1.5 to 1.9) | 0.23 (0.19 to 0.28) | 13 (12 to 14) |
| Oldmere | 1.4 (1.2 to 1.6) | 0.21 (0.17 to 0.26) | 13 (12 to 15) |

The seasonal term peaked between week 12 and week 13 in every district, about two weeks after the mean weekly temperature peaked. The fraction of the population still susceptible at the end of the season was above 0.9 everywhere, so the season ended because transmission fell with the weather, not because the susceptible pool was exhausted. The separate fits gave estimates within the credible intervals of the joint fit.

## Discussion

We fitted an SEIR model to one dengue season in three districts and found that transmission, not reporting, explained the differences between them. The earlier and larger season in Marrowick was consistent with its higher housing density, which brings people and mosquitoes closer together. A similar lead of the densest district was shown by Lim and colleagues (2021) in a neighbouring region. This proves that housing density explains the difference between districts. Our estimates of the basic reproduction number lie within the range that Quintero (2020) reported for lowland settings with a renewal model, which suggests that the choice of model matters less for the reproduction number than for the susceptible fraction, which a renewal model cannot report.

The seasonal term peaked about two weeks after the temperature did, which matches the delay expected from the EIP: a warm week shortens the EIP, and the extra infectious mosquitoes appear one to two weeks later. The same delay was found in the lowland districts of the neighbouring region (Oyelaran and Mbeki, 2019), where the seasons start about a month earlier than in Velmora.

The lag between the peaks in the three districts (Figure 3) may possibly suggest that the virus moved outward from Marrowick along the main road, but weekly counts cannot show the direction of spread. A model with movement between districts would need case data with finer timing than the week of the clinic visit.

Our study has three limitations. First, we had no onset dates, so the week of the clinic visit stood in for the week of infection, which blurs the timing by about one week. Second, the model treats each district as well mixed and ignores movement between them. Third, the seasonal term absorbs every driver that varies with the calendar, so we cannot separate temperature from rainfall or from school holidays, and the EIP enters only through that term.

The estimates have one practical use. Because most residents were still susceptible at the end of the season, the next season will not be limited by immunity, and vector control before the first rains would have the most effect in Marrowick, where transmission starts first.

## Conclusion

An SEIR model fitted jointly to three districts reproduced one dengue season and showed that the districts differed in transmission intensity rather than in reporting. The approach needs only routine weekly counts, and it could be run at the end of each season to rank districts for vector control in the next one.

## References

Haraldsen M. and Okonkwo D. (2017). Three decades of dengue surveillance in Velmora. Velmoran Journal of Public Health, 41, 112–121.

Lim W.T., Castellano P. and Adeyemi B. (2021). Reproduction numbers of dengue from weekly case counts: a renewal approach. Annals of Transmission Modelling, 14, 201–219.

Nakamura S. and Petrov I. (2022). Incubation and infectious periods of dengue: a synthesis of cohort estimates. Proceedings of the Society for Outbreak Analysis, 19, 330–341.

Oyelaran F. and Mbeki L. (2019). Rainfall, temperature and the timing of dengue seasons in lowland districts. Tropical Vector Reports, 8, 45–58.

Quintero A. (2020). Estimating the reproduction number of arboviruses with renewal equations. Bulletin of Computational Epidemics, 5, 77–90.
