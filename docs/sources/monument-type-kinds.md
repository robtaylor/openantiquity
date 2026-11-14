# Monument type terms for each feature class

On 2026-11-14 the terms of the FISH Thesaurus of Monument Types were set against the 22 feature classes in `backend/src/fieldclub/vocab.py`. The owner had asked for the kinds under each class to use the terms archaeology already has, and this page is what the kinds are chosen from. [The kinds plan](../plans/kinds-of-feature.md) says what a kind is and proposes a list for each class.

The terms, identifiers and placements below are observations of someone else's vocabulary on that day. The three LIDAR columns are this project's judgement and weren't tested against data.

## What was read

- **The current release.** Version 29 of the thesaurus, as the six CSV tables in `MonumentTypeV29.zip` from heritage-standards.org.uk. Its own version table gave a release date of 24/04/2026. It held 8,010 terms, 5,105 of them preferred.
- **The live service.** The relations service at heritagedata.org was asked for each of the 22 class terms. Wherever it differed from an older copy it agreed with version 29.
- **Two older copies.** The SKOS file `FISH_Monument_Type_20200731.rdf` from heritagedata.org, and the January 2018 PDF listing. Both had drifted from version 29, so neither was used for a term.
- **Scotland and Wales.** The Historic Environment Scotland thesaurus in a file dated 2018-03-28 and the RCAHMW one in a file dated 2013-07-17, both from heritagedata.org. Either may have moved since.

43 requests went to outside services, with a wait of 1.5 seconds before each. The 456 entries of the work-list were then compared with the version 29 tables by script: every term, identifier and scope note matched.

## Licence

The thesaurus could be reused with a credit.

- **heritagedata.org's scheme page**, `https://heritagedata.org/live/schemes/eh_tmt2.html`, gave the scheme's licence as the Open Government Licence v3.0 and its attribution name as "Historic England". The scheme metadata service gave the same licence.
- **The 2020 SKOS file** gave CC BY 3.0 on each of the 5,011 records that carried a licence, again with the attribution name "Historic England". The site's footer said: "Except where otherwise noted, data content on this site is licensed by the respective attributed organisations under a Creative Commons Attribution 3.0 License".
- **FISH's download page**, `http://www.heritage-standards.org.uk/fish-vocabularies/`, said: "All the resources here are free to use and do not require FISH membership." Neither FISH page named a licence.

Both licences allow copying, adapting and commercial use with attribution. A credit that names Historic England and the thesaurus and links the Open Government Licence meets both. [Thematic and gazetteer sources](thematic-and-gazetteers.md) recorded the same position on 2026-11-10.

Historic England's own terminology page answered the one request made of it with a bot challenge, so no statement was read from Historic England's own site.

## Terms by class

Each row gives a class, the thesaurus term `vocab.py` ties it to with that term's identifier, and the candidate kinds sorted by whether one-metre LIDAR could tell them from their neighbours. A term marked † is one the thesaurus files somewhere other than directly beneath the class's own term. Terms are written in ordinary capitals. The thesaurus prints its preferred terms in capitals throughout.

The address of a term is `http://purl.org/heritagedata/schemes/eh_tmt2/concepts/` followed by its identifier. Each candidate's identifier, scope note and placement are in the work-list.

| Class | Its thesaurus term | Could be told apart in LIDAR | Sometimes | Not from above |
|---|---|---|---|---|
| Enclosure | Enclosure, 70354 | Banjo enclosure, Curvilinear enclosure, Rectangular enclosure, Rectilinear enclosure, Ring enclosure, Subrectangular enclosure | Causewayed enclosure, Defended enclosure, Ditched enclosure, Tor enclosure | 2 |
| Hillfort | Hillfort, 68855 | Bivallate hillfort, Multiple enclosure fort, Multivallate hillfort, Univallate hillfort, Promontory fort† | Hillslope enclosure†, Hilltop enclosure†, Round† | 1 |
| Round barrow or mound | Round barrow, 70010 | Bell barrow, Bowl barrow, Disc barrow, Saucer barrow, Pond barrow†, Ring barrow†, Barrow cemetery†, Mound† | Bell disc barrow, Platform barrow, Square barrow†, Ring ditch†, Round cairn†, Ring cairn† | 1 |
| Long barrow | Long barrow, 70006 | Oval barrow, Bank barrow†, Long mound† | Long cairn† | 2 |
| Hut circle | Hut circle, 68964 | Hut circle settlement†, Enclosed hut circle settlement†, Unenclosed hut circle settlement†, Hut platform†, Ring bank† | Ring ditch†, Ring cairn† | 1 |
| Settlement earthworks | Settlement, 68977 | Deserted settlement, Hut circle settlement, Linear settlement, Scooped settlement, Toft†, House platform† | Crannog, Enclosed settlement, Homestead, Planned settlement, Unenclosed settlement, Shrunken village†, Croft†, Longhouse† | 24 |
| Building or ruin | Building, 70336 | Toft† | Outbuilding, Longhouse†, Farmstead† | 18 |
| Field system | Field system, 68633 | Aggregate field system, Celtic field system, Coaxial field system, Water meadow, Lynchet†, Strip lynchet†, Cultivation terrace†, Lazy beds†, Cord rig†, Field boundary†, Strip field†, Cairnfield† | Centuriated area, Darland field system, Enclosed field system, Open field, Clearance cairn† | 0 |
| Ridge and furrow | Ridge and furrow, 68628 | Broad ridge and furrow, Narrow ridge and furrow, Cord rig†, Plough headland†, Lazy beds† | Steam ploughed rig | 0 |
| Linear bank or ditch | Linear earthwork, 68890 | Multiple ditch system, Cross dyke†, Boundary bank†, Boundary ditch†, Bank (earthwork)†, Ditch†, Linear feature† | Dyke (defence)†, Ranch boundary†, Reave†, Park pale†, Wood bank†, Interrupted ditch system† | 1 |
| Trackway or hollow way | Trackway, 70270 | Hollow way†, Causeway† | Peatway, Rutway, Drove road†, Packhorse road† | 2 |
| Road | Road, 70264 | Hollow way, Embankment†, Causeway† | Approach road, Drove road, Packhorse road, Trackway | 8 |
| Moat | Moat, 68973 | Ha ha† | Fishpond† | 1 |
| Motte or castle earthwork | Motte, 68841 | Motte and bailey†, Ringwork†, Ringwork and bailey†, Bailey† | Windmill mound†, Prospect mound† | 0 |
| Platform | Building platform, 70337 | House platform, Hut platform, Platform†, Circular platform†, Charcoal burning platform† | none | 1 |
| Pond or water management | Pond, 70449 | Decoy pond, Dewpond, Water meadow†, Catchwork system†, Leat†, Water channel†, Dam† | Fishpond, Hammer pond, Mill pond, Mill dam†, Pond bay†, Drainage ditch†, Reservoir† | 13 |
| Pit or quarry | Extractive pit, 69101 | Claying trench, Quarry†, Bell pit†, Shaft mound†, Spoil heap† | Chalk pit, Dene hole, Gravel pit, Marl pit, Sand pit, Shode working, Stone quarry†, Clay pit†, Mine shaft†, Scowle† | 8 |
| Industrial | Industrial site, 69201 | Spoil heap†, Shaft mound†, Bell pit†, Hush†, Streamwork†, Charcoal burning platform†, Peat cutting†, Tramway†, Inclined plane†, Leat† | Adit†, Lime kiln†, Saw pit†, Saltern†, Mineral railway† | 3 |
| Military | Military installation, 133660 | Trench†, Anti aircraft battery†, Anti tank ditch†, Firing range†, Butts†, Military airfield†, Sconce†, Rampart†, Fortlet†, Temporary camp†, Bomb crater† | Military airfield site, Practice trench†, Slit trench†, Communication trench†, Weapons pit†, Rifle pit†, Breastwork†, Siegework†, Gun emplacement†, Battery†, Heavy anti aircraft battery†, Searchlight battery†, Bombing range†, Redoubt† | 8 |
| Ritual monument | Religious ritual and funerary, 99962 | Amphitheatre, Cursus, Henge, Hill figure, Monumental mound, Avenue (landscape feature)† | Causewayed ring ditch, Maze, Monastic precinct, Plain an gwarry, Religious house, Standing stone, Stone alignment, Stone circle, Stone setting, Tor cairn, Viereckschanzen, Hengiform monument†, Henge enclosure†, Causewayed enclosure† | 71 |
| Garden earthworks | Garden, 68641 | Sunken garden, Terraced garden, Tree enclosure ring†, Ha ha† | Formal garden, Parterre, Walled garden, Water garden, Garden terrace†, Terraced walk†, Prospect mound†, Artificial mound†, Tree mound†, Ornamental canal†, Ornamental lake†, Garden path†, Walk†, Bowling green†, Park†, Landscape park†, Deer park† | 45 |
| Not sure | Site, 70412 | Earthwork†, Mound†, Enclosure†, Linear feature†, Linear system†, Bank (earthwork)†, Ditch†, Platform†, Hollow†, Feature† | Ring ditch† | 2 |

The last column counts the candidates that need excavation, standing fabric, finds or documents to tell apart. They are named in the work-list.

## Where the classes and the thesaurus part

The thesaurus sorts by what a monument was for, with one class of terms by form. The feature classes are mostly by form. These are the places the two met badly.

- **Building or ruin** was tied to Building, which had 13 narrower terms, nearly all of them functions such as Office and Storehouse. The kinds people mean were spread across other parts of the thesaurus: House under Dwelling, Barn under Farm building, Chapel under Place of worship. There was no term for a ruin, and Cottage was not a preferred term.
- **Ritual monument** was tied to the top of a whole class, Religious ritual and funerary. It had 86 narrower terms, most of them churches, fittings and objects, and both barrow classes sat inside it. Causewayed enclosure was under Enclosure.
- **Military** was tied to Military installation, whose narrower terms were airfields, bases and depots. Trenches, batteries, gun emplacements and Roman camps were under other Defence terms, and Bomb crater was unassigned.
- **Industrial** was tied to Industrial site, a term for use only when nothing more specific is known, with one narrower term. The useful kinds came from the top of the Industrial class and from Transport.
- **Garden earthworks** was tied to Garden, whose 50 narrower terms were styles and uses of planting such as Dutch garden and Herb garden. Terraces, mounds, canals and walks were filed beside Garden.
- **Trackway or hollow way** names the hollow way, and the thesaurus filed Hollow way beside Trackway, both under Road.
- **Round barrow or mound** says "or mound". Mound was a separate term of form, with Pillow mound and Windmill mound beneath it.
- **Motte or castle earthwork** was tied to Motte alone. Motte and bailey, Ringwork and Ringwork and bailey were filed beside it under Castle.
- **Linear bank or ditch** was tied to Linear earthwork, whose scope note keeps it to major land boundaries, mostly of the Bronze and Iron Ages. The general terms were Linear feature, Boundary bank and Boundary ditch.
- **Field system** left out what a LIDAR reader most often sees of one. Lynchet, Strip lynchet, Cultivation terrace and Clearance cairn were filed elsewhere in the English thesaurus. The Scottish one put them beneath Field system.
- **Enclosure** had two kinds of narrower term, by shape and by boundary. The scope note of Ditched enclosure asks for a second term to give the shape, so one list of kinds mixes two things a recorder would say separately.

## Names in common use that the thesaurus lacked

Searched by exact label, preferred and not, in version 29 and the 2020 file. A name under another spelling would have been missed.

| Common name | In the English thesaurus | Note |
|---|---|---|
| Ruin, ruined building | Not a term | Condition isn't a monument type |
| Moated site | Not a term. Moat is used | Preferred in Scotland |
| Roman road | Not preferred. Road is used | Period is recorded apart from type |
| Agger | Not preferred. Road is used | Embankment was the nearest term of form |
| Holloway, sunken lane | Not terms. Hollow way is the spelling | |
| Dyke | Not a term | A wall in Scotland. Dyke (defence) was a term in England |
| Deserted medieval village | Not preferred. Deserted settlement is used | |
| Marching camp | Not preferred. Temporary camp is used | |
| Roman fort | Not preferred. Fort is used | |
| Spoil tip, mine dump | Not terms. Spoil heap is used | |
| Duck decoy | Not a term. Decoy pond is used | |
| Roundhouse | Round house (domestic), defined by post holes and gullies | Roundhouse is preferred in Scotland |
| Shell crater | Not a term | Bomb crater was the nearest |

## Scotland and Wales

- **Round barrow kinds were English only.** Neither the Scottish nor the Welsh thesaurus gave Round barrow any narrower terms. The Scottish one listed Bell barrow, Bell disc barrow, Bowl barrow and Disc barrow as other names for Round barrow, so a record there says Round barrow whichever kind it is.
- **Hillfort.** Scotland used Fort, not Hillfort. Wales had Hillfort with Univallate hillfort alone beneath it.
- **Different preferred names.** Scotland preferred Rig and furrow, Track and Moated site.
- **Dyke** meant a stone or turf wall in Scotland, with six kinds beneath it.
- **Buildings** had kinds by form in Scotland, such as Round ended building and Sunken floored building, which suit LIDAR better than the English terms.
- **Settlement.** Scotland had no Deserted settlement and used Township for a joint-tenancy farm cluster. Wales had Deserted rural settlement.

## Changes between releases

Version 29 was the one to use. Against the 2018 listing and the 2020 file it had added Peatway under Trackway and Catchwork system under Water meadow, moved Oppidum and Palisaded enclosure under Enclosed settlement, renamed Streamworks to Streamwork, and shortened many lists of related terms. Round barrow no longer listed Pond barrow as related.

Three scope notes in the version 29 tables carried damaged characters: Railway workers temporary settlement, Religious ritual and funerary, and Peatway. The work-list gives them as the tables had them.

## Not read

- Historic England's terminology page, which answered with a bot challenge. `thesaurus.historicengland.org.uk` answered HTTP 530.
- The SPARQL endpoint at heritagedata.org, which answered HTTP 500 to both queries tried.
- A 2026 SKOS file for monument types. None was linked.
- Any Scottish or Welsh release later than the 2018 and 2013 files.

## Work-list

`worklists/monument-type-kinds.json` holds every candidate for every class: the term, its identifier, scope note, thesaurus classes, broader and narrower terms as version 29 gave them, and this project's LIDAR flag with its reason. It also holds the kinds proposed to the owner in the plan. It is an input for building the kinds, and once they are built `vocab.py` is the record of what was chosen.

Contains public sector information licensed under the Open Government Licence v3.0. The terms and scope notes are from the FISH Thesaurus of Monument Types, © Historic England.
