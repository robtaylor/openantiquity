# Spike — How much volunteer agreement makes a LIDAR identification reliable?

**Status:** Resolved (2026-11-10) — PARTIAL; one field-checked study gave precision by agreement count for Dutch barrows only, so the ladder's thresholds stayed judgement calls and needed a UK calibration set

## Question

Does published evidence say how many agreeing volunteers make a LIDAR identification reliable enough to set the thresholds of a confidence ladder?

## Why this is in question

[Decision 0003](../0003-confidence-ladder.md) sets tier rules built on how many other people can see a feature and whether they agree what it is. [Decision 0008](../0008-second-looks-are-blind.md) hides earlier answers from reviewers and raises the weight needed for "probable" from 5.0 to 7.0 without a trusted reviewer. Both rest on a belief that agreement among a few volunteers is weak evidence. The belief needed a measured number, and it needed a check that the evidence behind it was cited correctly.

## Approach

A research pass on 2026-11-10 read the published accuracy studies and the stated rules of platforms that turn many opinions into one answer.

- **Q1.** Is there a field-checked accuracy study of volunteer LIDAR classification?
  - Read Bourgeois, Kaptijn, Verschoof-van der Vaart and Lambers 2024 (Antiquity) for the Heritage Quest project.
  - Checked the two citations in the research brief against Crossref.
  - Searched for a peer-reviewed evaluation of Deep Time (DigVentures).
- **Q2.** What consensus rules do other platforms publish?
  - Read the stated rules of iNaturalist, Zooniverse, Galaxy Zoo 2 and eBird, and the review flows of MapRoulette, Chilterns Beacons of the Past and the Kent LiDAR Portal.
- **Q3.** Is there evidence on blind review, on participation and on retention?
  - Read Lin et al. 2014, Sauermann and Franzoni 2015, Eveleigh et al. 2014 and the Chilterns participation report.

## Decision matrix

| Outcome | Means | Action |
|---|---|---|
| No field-checked study exists | Thresholds can only be guessed | Decision 0003 accepted with a warning that every number is untested |
| A study exists and transfers to UK features | Its thresholds can be copied | Decision 0003 accepted with those thresholds, spike resolves YES |
| A study exists but covers one feature class in one country | Its shape is informative and its numbers are not portable | Decision 0003 accepted with thresholds as judgement calls, a calibration set planned, spike resolves PARTIAL |

## Findings

- 2026-11-10: Bourgeois et al. 2024 hand-cored at least three cores at each of 380 consensus locations. 226 were barrows, giving precision 0.59 overall. Evidence: <https://www.cambridge.org/core/product/AD514BA3713EFC518038EC9232C3B5AD/core-reader>.
- 2026-11-10: Below 7 agreeing volunteers, precision "fluctuates between 0.21 and 0.41". It was 0.75 at 10, about 0.82 at 12 or more, and 0.85 at 15 or more. The conclusion says "Even a lower consensus of 7 or higher still has a precision of 0.7 on average". Same evidence address.
- 2026-11-10: A single mark had a 35% chance of being a barrow. The authors call that inflated by one urnfield. About 1,000 potential new barrows had over 50% probability. Same address.
- 2026-11-10: The study covered Dutch barrows on tiles seen by at least 15 users in the Veluwe and 60 in the Utrechtse Heuvelrug. 2,063 and 4,572 users classified 396,552 and 300,971 tiles. The research report called the thresholds uncalibrated for any other class, country or viewing depth. Same address.
- 2026-11-10: A dozen urnfield mounds only 0.2 to 0.3 m high were missed by most volunteers and marked by one user who had classified more than 20,000 images. The tutorial had left that class out. Majority vote suppressed the subtle class. Same address.
- 2026-11-10: Heritage Quest ran on Zooniverse with 300 x 300 m tiles, two visualisations side by side, an always-available field guide with positive and negative examples, and a dedicated staff member running the forum. The Zooniverse API showed project 8112 as "finished" with 56,847 classifications and 3,560 classifiers, lower than the paper's Dutch totals. The reason was not established. Evidence: <https://www.zooniverse.org/api/workflows?project_id=8112&page_size=20>.
- 2026-11-10: Two citations in the research brief were wrong. "Stewart et al. 2020" is Remote Sensing 12(17):2795, a PyBossa pilot on Bing Bird's Eye cropmarks near Rome, not Deep Time. Of 18,765 completed tasks, positive detections were recorded once for 1,447, twice for 57 and three or more times for 10. Evidence: <https://api.crossref.org/works/10.3390/rs12172795>.
- 2026-11-10: "Lambers et al. 2019" (Remote Sensing 11(7):794, published 3 April 2019) described the planned Heritage Quest workflow and predates any results. The accuracy figures are in Bourgeois et al. 2024, Antiquity 98(402):1662-1678, doi 10.15184/aqy.2024.127. MDPI returned 403, so only the Crossref abstract of the 2019 paper was read. Evidence: <https://api.crossref.org/works/10.3390/rs11070794>.
- 2026-11-10: No peer-reviewed evaluation of Deep Time was found in Crossref or a web search. The evidence was a Nesta write-up, DigVentures' case studies and two ECSA 2026 conference abstracts. Evidence: <https://digventures.com/projects/deep-time/>.
- 2026-11-10: Deep Time's accuracy claims were self-reported. The Brightwater pilot (220 km2) scored the HER at 88% and the combined data at 94% on a random 5% sample. The case-study PDF gave 94.32% and 88.71%. Other missions reported 84% (Peak District, up from 63%), 87.3% (Purbeck) and 92.7% (Wallington). The FAQ claim that participant data "matched or outperformed machine-learning baselines in 88% of cases" named no assessor and linked no report. Evidence: <https://digventures.com/wp-content/uploads/2025/08/Deep-Time-Case-Studies.pdf>.
- 2026-11-10: Per a Nesta summary as extracted, a model trained on Deep Time crowd labels "didn't work at all" for most classes. Ridge and furrow made up over 90% of labels. Burial mounds were drawn over 100 m wide where experts expect 10 to 15 m. The crowd was good at rejecting AI false positives. Confidence was "likely", not verified. Evidence: <https://www.nesta.org.uk/project-updates/using-crowdsourcing-ai-to-generate-new-archaeological-discoveries/>.
- 2026-11-10: Casana 2020 reported students with some training found under 5% of looted sites while flagging looting at 20 to 30% of other sites. The TerraWatchers pilot found 7% correct, rising to a reported 39% with more training. In Lin et al. 2014, 55 of 100 top-ranked crowd locations were confirmed on the ground. Evidence: <https://par.nsf.gov/servlets/purl/10190315>.
- 2026-11-10: iNaturalist's community taxon score is "cumulative count / (cumulative count + disagreement count + ancestor disagreements)". It chooses the finest-ranked taxon with a score over 2/3 and at least 2 identifications. Research Grade also needs a passing Data Quality Assessment, and votes can demote a record to Casual. Evidence: <https://help.inaturalist.org/en/support/solutions/articles/151000173076-what-is-the-community-taxon-id-and-how-is-it-calculated->.
- 2026-11-10: Zooniverse retirement is a per-workflow classification count. Its help text says "We suggest starting out high, between 10 and 20". Point answers cluster with DBSCAN or HDBSCAN. Question answers reduce to most_likely, num_votes and agreement. Gold-standard subjects can give immediate feedback. Evidence: <https://aggregation-caesar.zooniverse.org/reducers.html>.
- 2026-11-10: Galaxy Zoo 2 weighted each user by consistency, w = min(1.0, (k/0.6)^8.5). That gave w = 1 for about 95% of classifiers and w < 0.01 for about 1%, with "no up-weighting of the most consistent classifiers". The study had 16,340,298 classifications by 83,943 volunteers, median 44 per galaxy. Evidence: <https://arxiv.org/pdf/1308.3496>.
- 2026-11-10: eBird held flagged records out of public output until a volunteer reviewer had evaluated them, and asked observers to say how look-alikes were ruled out. "Simply writing seen well, yes, etc. is insufficient." Confidence was "likely". Evidence: <https://support.ebird.org/en/support/solutions/articles/48000795278-the-ebird-review-process>.
- 2026-11-10: Chilterns used two portals. Anyone recorded in a Citizen Portal. Trained reviewers decided which records were accepted. By December 2020 there were over 10,000 citizen records, more than 40 trained reviewers and "nigh on 4500 records processed". Evidence: <https://chilternsbeacons.org/wp/2020/12/17/2020-in-review/>.
- 2026-11-10: Chilterns chose not to show citizen finds to other users, to avoid early records being "taken as a model ... assumed to be gospel truth", to avoid drawing attention to sites at risk of looting, and to avoid clutter. Evidence: <https://chilternsbeacons.org/wp/2020/06/08/where-to-look/>.
- 2026-11-10: Lin et al. 2014 reported that participants who saw earlier tags only after committing their own had median accuracy 23.6%, against 16.6% working in isolation, a reported 42% increase. The authors cautioned that copying bias may explain part. Confidence was "likely". Evidence: <https://doi.org/10.1371/journal.pone.0114046>.
- 2026-11-10: Chilterns nine months after launch had over 2,000 registrants. Just over 300 completed a tutorial and 166 created at least one feature. The top 5 recorders made about 4,500 of 8,336 records. Evidence: <https://chilternsbeacons.org/wp/2020/05/07/citizen-science-and-lidar-apparently-mostly-on-wednesdays/>.
- 2026-11-10: Sauermann and Franzoni 2015 covered seven Zooniverse projects and 100,386 users. The top 10% supplied 71 to 88% of contributions (mean 79%). Only 17 to 40% of users returned (mean 27%). Time per active day was 7 to 26 minutes. Evidence: <https://pmc.ncbi.nlm.nih.gov/articles/PMC4311847>.
- 2026-11-10: Eveleigh et al. 2014 (Old Weather, 299 matched respondents) tied dropping out to "an anxiety about the quality of contribution". Segal et al. found that only a message about the individual's helpfulness, sent at predicted times of disengagement, raised contributions. The venue of Segal et al. was recalled as IJCAI 2016 and not confirmed. Evidence: <https://discovery.ucl.ac.uk/id/eprint/1418573/1/p2985-eveleigh.pdf> and <https://www.erichorvitz.com/engagement_intervention.pdf>.
- 2026-11-10: MapRoulette scored "Not an Issue" 3 points against 5 for "Fixed", so declaring a false positive was rewarded. Reviewers could approve, approve with fixes or reject with a comment. Evidence: <https://learn.maproulette.org/en-US/documentation/point-scoring/>.
- 2026-11-10: The research pass named data artefacts and look-alikes behind false positives. Examples were wavy swath interference that looks like ridge and furrow, 1 m height steps that look like lynchets, a covered reservoir that "gives every appearance of being a burial mound", roundabouts, dunes and saw pits. Historic England's test was "Any feature that visibly crosses a modern road or hedge is not of archaeological origin". Evidence: <https://archaeologydataservice.ac.uk/catalogue/adsdata/arch-4637-1/dissemination/pdf/nmr1-516675_212455.pdf>.
- 2026-11-10: The research pass did not examine Reddit, Facebook groups, X, Bluesky or Discord. Deep Time's app was login-gated and its other hostname returned 500.

## Outcome

One field-checked study existed. It showed precision rising with agreement and sitting between 0.21 and 0.41 below 7 agreeing volunteers, which supports treating a few agreeing volunteers as weak evidence. It covered Dutch barrows seen by 15 to 60 people per tile, so its numbers could not be carried over to UK feature classes or to a map where a few people look at each spot. The research brief's two citations for accuracy were wrong and were corrected above. The ladder's thresholds therefore stayed judgement calls, and the research recommended seeding gold-standard subjects from known scheduled monuments and arranging field checks with a county HER or society to calibrate them.
