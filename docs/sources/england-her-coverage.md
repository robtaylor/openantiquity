# England HER coverage

England has 83 Historic Environment Records (HERs). This page lists each one with the class the follow-up research gave it on 2026-11-10, the licence it found, the address of any machine-readable source, and the share of England's area it covers. The headline: three HERs were bulk-ingestable, fifteen had a public queryable service, 53 were deep link only and twelve had no public online record found. Openly licensed HER data covered 2.9% of England's area, or 7.5% if Lincolnshire's caveated licence was accepted.

The source records are in [England records](records-england.md). The research behind this table was a follow-up on England's undesignated site records. Nothing here describes what Open Antiquity's code does, because none of it is built. Classes are the research's, not Open Antiquity's decisions. The three access modes in [Decision 0007](../architecture/decisions/0007-the-record-index-stores-only-what-licences-allow.md) map onto them as `bulk`, `live` and `deeplink`.

## Totals

The follow-up summed the area of the 83 boundary polygons in Historic England's HER boundaries layer and got 132,940 km². The table below reproduces its CSV, so its rows sum to 132,939.4 km² and the shares below are each row divided by 132,940.

| Class | HERs | Area share | What the class meant |
|---|---:|---:|---|
| bulk | 3 | 7.5% | Cornwall and Isles of Scilly, City of York, Lincolnshire |
| live | 15 | 16.0% | A public queryable service of unstated or restrictive licence. Merseyside and Yorkshire Dales are in this class through the Archaeology Data Service catalogue alone |
| deep link | 53 | 68.2% | Record pages only, or Heritage Gateway links |
| none found | 12 | 8.3% | No public online record found, plus Greater London |

| Measure | Value |
|---|---|
| Strictly open: Cornwall and Isles of Scilly 3,636 km², City of York 272 km² | 3,908 km², 2.94% |
| Adding Lincolnshire (OGL label, no-commercial-use sentence), 6,067 km² | 9,975 km², 7.50% |
| Adding Exmoor (OGL only per Bristol's catalogue), 693 km² | 10,668 km², 8.02% |
| HERs with any full-coverage machine-readable source, whatever the licence | 18 HERs, 31,190 km², 23.5% |
| The same, leaving out the two that are only in the Archaeology Data Service catalogue | 21.2% |
| HERs on the new Heritage Gateway on 2026-11-10 | 39 of 83, 66,847 km², 50.3% |
| HERs listed as pending on the new Heritage Gateway | 24, 35.0% |

The Heritage Gateway held 1,299,728 records across its datasets on 2026-11-10, including 354,740 Historic England research records and 70,805 National Trust records. The per-HER counts in the table are not summed here because Devon and Dartmoor share one dataset of 114,577 and Worcestershire and Worcester City share one of 43,717.

## The table

Columns: Class is the follow-up's class, with `none found` standing for its `closed`. Licence is the licence as found. Address and records is the follow-up's `machine_readable` field. Heritage Gateway is the count on the new Heritage Gateway, `pending` where the follow-up flagged the HER as awaiting onboarding, and `none` where it found neither. Note is the follow-up's own note column, unchanged.

| HER | Class | Licence as found | Address and records | km² | Share | Heritage Gateway | Note |
|---|---|---|---|---:|---:|---|---|
| Bath and North East Somerset HER | live | unstated (KYP) | KYP banes_hist_2024/4 9,008 polys (PRN, NAME) | 351.1 | 0.26% | 9,006 |  |
| Bedford Borough Council HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 476.4 | 0.36% | 8,774 |  |
| Berkshire Archaeology HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 559.7 | 0.42% | pending | weak |
| Birmingham HER | none found | no public online record found | enquiry to HER only | 267.8 | 0.20% | none | not on Heritage Gateway lists |
| Bristol City Council HER | live | 'GIS User Agreement for external use' (catalogue); 2011 CSV on data.gov.uk has no open licence | KYP her_2026/34 3,733 pts; CSV 3,626 rows (2011) | 235.3 | 0.18% | none |  |
| Buckinghamshire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages; heritageportal.buckinghamshire.gov.uk | 1,564.9 | 1.18% | 24,099 |  |
| Cambridgeshire HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 3,054.0 | 2.30% | pending | weak |
| Central Bedfordshire & Luton HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 759.0 | 0.57% | 14,180 |  |
| Cheshire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 2,380.3 | 1.79% | 12,194 |  |
| Chichester District HER | none found | no public online record found | enquiry to HER only | 811.9 | 0.61% | none | not on Heritage Gateway lists |
| City of Lincoln Council HER | live | unstated (ARCADE Arches) | arcade.lincoln.gov.uk /search/resources JSON: 18,539 resources | 35.7 | 0.03% | none |  |
| City of York HER | bulk | OGL v3 | maps.york.gov.uk LV_LeisureCulture MapServer 0-5 + Hub GeoJSON: monuments 3,555/3,648/2,459; events 7,850/121/1,336 | 272.0 | 0.20% | pending |  |
| Colchester HER | deep link | site terms (all rights reserved) | colchesterheritage.co.uk; pending on new Heritage Gateway | 346.7 | 0.26% | pending |  |
| Cornwall and Isles of Scilly HER | bulk | OGL v3 (INSPIRE metadata); conflicting NC view-only text on AGOL item | map.cornwall.gov.uk inspire_historic MapServer/WFS: 78,387 pts + 2,909 lines + 50,804 polys; events 9,706 | 3,636.2 | 2.74% | 80,196 |  |
| Coventry City Council HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 98.6 | 0.07% | pending | weak |
| Cumbria HER | none found | no public online record found | enquiry to HER only | 4,214.1 | 3.17% | none | not on Heritage Gateway lists |
| Dartmoor National Park HER | live | unstated | DNPA AGOL Heritage_Environment_Record: 6,904 pts + 25,391 polys (Aug 2026) | 955.7 | 0.72% | 114,577 |  |
| Derbyshire HER | deep link | unstated | her.derbyshire.gov.uk; Peak District PDNPA_HBSMR_Layers survey layers overlap (licence unstated) | 2,628.8 | 1.98% | pending |  |
| Devon (including Torbay) HER | live | unstated (KYP) | KYP devon_hist_2021_v2/4,5: 49,473 pts + 71,369 polys (Oct 2023) | 5,594.6 | 4.21% | 114,577 |  |
| Dorset HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages; heritage.dorsetcouncil.gov.uk | 2,694.8 | 2.03% | 46,008 |  |
| Dudley HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 98.0 | 0.07% | pending | weak |
| Durham County Council HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages; keystothepast.info ?PRN=Dnnn | 2,430.2 | 1.83% | 30,185 |  |
| East Riding and Hull HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 2,578.2 | 1.94% | pending | weak |
| East Sussex HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 1,810.5 | 1.36% | pending | weak |
| Essex HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 3,532.4 | 2.66% | 15,206; pending |  |
| Exeter City HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 4.0 | <0.01% | pending | weak |
| Exmoor National Park HER | live | OGL per Bristol KYP catalogue metadata; not stated on exmoorher.co.uk | KYP devon_hist_2021_v2/7 12,322 polys; ENPA AGOL MonPoint/Line/Poly020525 3,369/399/8,337 | 693.2 | 0.52% | 10,146 |  |
| Gloucestershire HER (including City of Gloucester) | live | unstated (KYP) | KYP glo_hist_2021/4 27,362 polys (2017 snapshot, 'update not planned') | 2,704.5 | 2.03% | none |  |
| Greater London HER | none found | GLHER Online terms: no text/data mining or scraping, no commercial use, links to home page only | Arches JSON exists (184,086 resources) but terms prohibit automated use | 1,594.7 | 1.20% | pending |  |
| Greater Manchester HER | deep link | unstated | partial only: Salford AGOL 1,665/16/280 | 1,276.0 | 0.96% | 21,686 | partial live |
| Hampshire HER | deep link | unverified | maps.hants.gov.uk historic environment viewer ('Access denied' to curl) | 3,076.8 | 2.31% | none | unverified |
| Herefordshire HER | deep link | site terms (all rights reserved) | htt.herefordshire.gov.uk; pending on new Heritage Gateway | 2,179.7 | 1.64% | pending |  |
| Hertfordshire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 1,643.1 | 1.24% | 18,290 |  |
| Isle of Wight HER | none found | no public online record found | enquiry to HER only | 394.9 | 0.30% | none | not on Heritage Gateway lists |
| Kent County Council HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 3,908.3 | 2.94% | pending | weak |
| Lake District HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 2,362.7 | 1.78% | 16,942 |  |
| Lancashire HER | none found | no public online record found | enquiry to HER only | 3,240.4 | 2.44% | none | not on Heritage Gateway lists |
| Leicester City HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 73.3 | 0.06% | pending | weak |
| Leicestershire and Rutland HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 2,477.5 | 1.86% | 26,994 |  |
| Lincolnshire HER | bulk | OGL v3 label; description says no commercial use | data.lincolnshire.gov.uk CSV 42,927 rows (MonUID, Name, Easting, Northing), quarterly | 6,066.9 | 4.56% | 42,641 |  |
| Merseyside HER | live | ADS Terms of Use and Access (research/teaching) | ADS data-catalogue API: 20,707 records | 817.6 | 0.62% | 20,674 | partial/stale |
| Middlesbrough HER | none found | no public online record found | enquiry to HER only | 54.6 | 0.04% | none | not on Heritage Gateway lists |
| Milton Keynes HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 308.6 | 0.23% | pending | weak |
| Norfolk HER | deep link | site terms (all rights reserved) | heritage.norfolk.gov.uk/record-details?MNFnnn; pending on new Heritage Gateway | 5,498.3 | 4.14% | pending |  |
| North East Lincolnshire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 203.6 | 0.15% | 4,065 |  |
| North Lincolnshire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 875.7 | 0.66% | 10,865 |  |
| North Somerset HER | live | Public Sector End User Licence (KYP metadata) - not open | KYP nsom_hist_2022_v2/4-6: 7,948/50/2,122 | 390.8 | 0.29% | 10,172 |  |
| North York Moors National Park Authority HER | deep link | unstated | partial only: NYMNPA AGOL HER_Monuments 483 features | 1,441.2 | 1.08% | none | partial live |
| North Yorkshire Council HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 5,119.5 | 3.85% | pending | weak |
| Northamptonshire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 2,367.0 | 1.78% | 52,439 |  |
| Northumberland HER | deep link | site terms (all rights reserved) | keystothepast.info ?PRN=Nnnn; pending on new Heritage Gateway | 5,078.3 | 3.82% | pending |  |
| Nottingham City HER | none found | no public online record found | enquiry to HER only | 74.6 | 0.06% | none | not on Heritage Gateway lists |
| Nottinghamshire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages; her.nottinghamshire.gov.uk | 2,086.9 | 1.57% | 19,740 |  |
| Oxford City HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 45.6 | 0.03% | 3,583 |  |
| Oxfordshire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 2,560.3 | 1.93% | 23,226 |  |
| Peterborough City Council HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 343.4 | 0.26% | 6,210 |  |
| Plymouth HER | none found | no public online record found | enquiry to HER only | 84.4 | 0.06% | none | not on Heritage Gateway lists |
| Portsmouth HER | none found | no public online record found | enquiry to HER only | 60.1 | 0.05% | none | not on Heritage Gateway lists |
| Redcar and Cleveland HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 191.6 | 0.14% | 2,847 |  |
| Sandwell HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 85.6 | 0.06% | 1,421 |  |
| Shropshire Council HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 3,487.6 | 2.62% | 40,729 |  |
| Solihull HER | none found | no public online record found | enquiry to HER only | 178.3 | 0.13% | none | not on Heritage Gateway lists |
| Somerset HER | live | unstated (KYP); ADS copy under ADS terms | KYP som_hist_2022/4 37,380 polys (PRN, NAME only); ADS catalogue 29,142 | 3,022.3 | 2.27% | 38,039 |  |
| South Gloucestershire HER | live | unstated (KYP) | KYP sgc_hist_2020_v2/4 6,400 pts | 536.6 | 0.40% | none |  |
| South Yorkshire HER | deep link | site terms (all rights reserved) | sytimescapes.org.uk (HEC only); pending on new Heritage Gateway | 1,552.1 | 1.17% | pending |  |
| Southampton HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 56.4 | 0.04% | 4,709 |  |
| Southend-on-Sea HER | deep link | PSEUL-INSPIRE (not open) | 2013 WMS only (essex.astuntechnology.com) | 67.8 | 0.05% | none | stale WMS |
| Staffordshire HER | deep link | unstated | partial only: Stafford BC AGOL 3,880 pts (2026); Lichfield DC AGOL 12,704 features (2018) | 2,623.3 | 1.97% | 21,806 | partial live |
| Stoke-on-Trent City Council HER | none found | no public online record found | enquiry to HER only | 93.4 | 0.07% | none | not on Heritage Gateway lists |
| Suffolk HER | deep link | site terms (all rights reserved) | heritage.suffolk.gov.uk/Monument/MSFnnn; pending on new Heritage Gateway | 3,853.6 | 2.90% | pending |  |
| Surrey HER | deep link | unverified | exploringsurreyspast.org.uk (HTTP 403 Cloudflare challenge to curl; browser only) | 1,670.1 | 1.26% | none | unverified |
| Tees Archaeology HER | deep link | site terms (all rights reserved) | teesarchaeology.com | 308.2 | 0.23% | none |  |
| Tyne and Wear HER | deep link | site terms (all rights reserved) | twsitelines.info/SMR/nnn; pending on new Heritage Gateway | 551.2 | 0.41% | pending |  |
| Warwickshire HER | deep link | ADS terms for ADS copy | ADS catalogue 9,042 (partial); heritage.warwickshire.gov.uk | 1,977.5 | 1.49% | pending | partial |
| West Berkshire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 704.2 | 0.53% | 11,834 |  |
| West Sussex County Council HER | deep link | legacy Heritage Gateway links redirect; dataset not yet reloaded | pending on new Heritage Gateway (not searchable today) | 1,211.7 | 0.91% | pending | weak |
| West Yorkshire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 2,029.3 | 1.53% | 15,962 |  |
| Wiltshire and Swindon HER | live | unstated | maps.wiltshire.gov.uk Website/Monuments MapServer: 21,134 lines/25,432 pts/23,959 polys (daily); KYP wilts_her_2022_v2 | 3,485.4 | 2.62% | 39,144 |  |
| Winchester HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 661.1 | 0.50% | 7,090 |  |
| Wolverhampton and Walsall HER | live | unstated (AGOL); data.gov.uk record says PSEUL-INSPIRE | AGOL HER_points/lines/polys_260121: 755/119/1,971 (Sep 2026) | 173.4 | 0.13% | 4,787 |  |
| Worcester City HER | live | unstated (KYP) | KYP worcester_city/4,6: 2,614 pts + 534 polys | 33.3 | 0.03% | 43,717 |  |
| Worcestershire HER | deep link | Heritage Gateway: 'not authorised for commercial reuse' | new Heritage Gateway record pages | 1,707.2 | 1.28% | 43,717 |  |
| Yorkshire Dales National Park Authority HER | live | ADS Terms of Use and Access (research/teaching) | ADS data-catalogue API: 30,791 records (age unknown) | 2,184.8 | 1.64% | pending | partial/stale |

## Reading the table

- **Greater London** is `none found` in the CSV although it has an online record system. Its terms prohibit text or data mining, scraping, commercial use and links to any page except the home page. Its Arches JSON existed with 184,086 resources on 2026-11-10, but the terms prohibit automated use.
- **The 11 other `none found` rows** were classed on absence. The follow-up found them neither among the 37 HER datasets on the new Heritage Gateway nor on its "not currently available" list, and its data.gov.uk and ArcGIS Online searches found nothing. It did not open each HER's Heritage Gateway profile page or council website, so some may have a viewer it missed.
- **Hampshire and Surrey** are `deep link` but unverified. Their sites refused curl.
- **The 12 rows noted `weak`** are the 12 whose licence column reads "legacy Heritage Gateway links redirect; dataset not yet reloaded". Their deep links work through old redirects, and the record may not load until the dataset is added to the new gateway. The CSV does not define `weak`.
- **Partial sources.** Staffordshire, Greater Manchester, North York Moors and Warwickshire have record counts that cover only part of the HER. Their rows read `partial live` or `partial`.
- **Pending count.** 25 rows carry the pending flag in the CSV, 24 are in the follow-up's totals, and the Heritage Gateway FAQ listed 25 HERs missing from the new site. Essex has 15,206 records in the site's dataset facet while the FAQ listed it as not yet available, and the follow-up did not explain that. The counts differ and the CSV is reproduced as it stands.
- **Heritage Gateway counts that repeat.** Devon (including Torbay) and Dartmoor both show 114,577 because the gateway holds them as "Devon and Dartmoor". Worcester City and Worcestershire both show 43,717 for the same reason.
- **Class and licence disagree in places.** Cornwall and Lincolnshire are `bulk` although each has a licence conflict. Cornwall's INSPIRE metadata says OGL v3 while its ArcGIS Online item says a revocable non-commercial view licence. Lincolnshire's label is OGL while its description bars commercial use. The research asked for a one-line written confirmation from each HER.
- **Know Your Place** carries ten of the `live` rows on one server. See [England records](records-england.md) for its address and limits.

## Open questions

- Whether Birmingham, Chichester, Cumbria, Isle of Wight, Lancashire, Middlesbrough, Nottingham City, Plymouth, Portsmouth, Solihull and Stoke-on-Trent have any public online record. Their Heritage Gateway profile pages were not opened.
- Which 13 HERs had completed the transfer of National Record of the Historic Environment records and which 12 were in progress. The portal's progress pages need a login.
- Why Essex appears on the new Heritage Gateway while the FAQ listed it as not yet available.
- Whether the Know Your Place partners would allow caching or bulk ingest of the layers they already expose.
- Historic England said on its help page that it expected to add more than 20 datasets during the financial year current in 2026 and aimed for 95% coverage of HER monument records in 2027. The research recommended repeating this survey in spring 2027.
