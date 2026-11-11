# Plan — Owner actions: permissions, letters and accounts

**Status:** Active. WS1 was done on 2026-11-10. Everything else is to do.

## Goal

Get the permissions, accounts and legal steps that only the project owner can provide, in the order the build needs them. Agents never send anything. This plan holds the drafts, and the owner sends them, signs them and records the replies here.

The plan serves [v1-england.md](v1-england.md) and the decisions on accounts ([0002](../architecture/decisions/0002-accounts-required-to-save.md)), non-commercial status ([0004](../architecture/decisions/0004-field-club-is-non-commercial.md)), terrain ([0006](../architecture/decisions/0006-terrain-tiles-are-rendered-from-raw-elevation.md)), the record index ([0007](../architecture/decisions/0007-the-record-index-stores-only-what-licences-allow.md)) and age and messaging ([0009](../architecture/decisions/0009-contributors-are-16-or-over-and-there-is-no-private-messaging.md)).

## Prerequisites

- The research pass of 2026-11-10 is complete. Every fact below comes from it, written as it was observed that day.
- Decisions 0002, 0004, 0006, 0007 and 0009 are Proposed. The letters describe Field Club as those decisions do.
- The owner has a name, role and contact address to sign with. Every draft ends with a placeholder for them.
- Field Club facts used in every draft: free, non-commercial, citizen-science, contributors aged 16 and over, no private messaging, contributions under CC BY 4.0, deployed on Google Cloud.

## Where things stand (2026-11-11)

- WS1 England LIDAR: done on 2026-11-10. Defra supplied the 2022 composite in bulk with no time limit, ticket DSP3-11967.
- WS2 Google Cloud project: the project `fieldclub-uk` exists, without billing. The v1 deployment workstream and the full LIDAR copy wait on the billing link.
- WS3 Sign-in credentials: to do. Only OpenStreetMap and Google were looked at by the research.
- WS4 Other keys and accounts: to do. None is needed for the first build.
- WS5 Archaeology Data Service: letter sent on 2026-11-11. Awaiting a reply.
- WS6 to WS8 Historic England, the Portable Antiquities Scheme and local record offices in England: to do. No letter sent.
- WS9 Scotland, Wales, Northern Ireland and the islands: the letter to Historic Environment Scotland was sent on 2026-11-11. Awaiting a reply. The other letters in the workstream aren't sent.
- WS10 to WS12: to do. No letter sent.
- WS13 Browser checklist: to do.
- WS14 to WS18 Legal steps before launch: to do. The operating entity isn't chosen yet, and several steps wait on it.
- WS19 Courtesy notices: to do.

## How to use this plan

Each workstream has a status, a contact, what a reply unblocks, what happens without one, a draft where the research supplied or implied one, and an exit criterion. Send each draft from the address you want replies at. When a reply arrives, update the status line in place and put the decision it allows in the right home: a source's reuse class and access mode change in the source catalogue, and a change of approach needs a new decision record.

Contact addresses are the ones the research recorded. "Address to find" means the research didn't record one.

Reuse classes and access modes follow Decisions 0004 and 0007. A publisher that blocks scripts or forbids harvesting stays `deeplink` whatever its licence.

## Workstreams

### WS1 — England LIDAR supply from Defra

**Status:** Done 2026-11-10. Defra supplied the data the same day.

The owner submitted Defra's Large Dataset request form for the LIDAR Composite DTM 1 m (dataset 13787b9a-26a4-4775-8523-806d13af58fc), national coverage, reference DSP3-11967. Defra acknowledged it, and seven minutes later gave access to its bulk supply over SFTP. A second email answered the request's three questions, and the owner replied to confirm that access worked.

| Question asked | Defra's answer |
|---|---|
| Can the newer composite be supplied in bulk? | The 2022 composite plus the 1 m DTM tiles is the latest available |
| May the tiles be fetched one request at a time? | Not needed. The bulk supply has no time limit and may be used to download the data the project needs |
| Is the image service meant for third-party applications? | The WMS and WCS services may be used in applications. They're tuned for live viewing, and Defra recommended the bulk supply for the core dataset |

What the supply holds, and how it behaves in transfer, is recorded in `../sources/lidar-england-bulk-supply.md`. The connection details are in the owner's email under the ticket and in the untracked `.env`.

**Deliverables:**

- Defra's reply to the three questions, recorded above.
- The England supply route: the bulk supply, mirrored as Decision 0006 describes.

**Exit criteria:**

- Met. Copying the full set into a bucket is WS8 of `v1-england.md` and waits on WS2 below.

### WS2 — Google Cloud project

**Status:** In progress. On 2026-11-11 the owner approved the project `fieldclub-uk`, the first Terraform stage, a budget alert of £75 a month and the contact address `fieldclub@shape.build`. The project was created that day. Linking it to the billing account was refused: the account already has five projects, which is its quota. The owner frees a place on the account or asks Google to raise the quota, and the first stage follows.

**Who.** The owner, in their own Google Cloud account. The research created nothing in it.

**What it unblocks.** The deployment workstream in [v1-england.md](v1-england.md), the LIDAR mirror bucket, and the place where API keys and sign-in secrets will live. The research put a YouTube Data API key in "the user's Google Cloud project".

**What the owner provides:**

- A named project with billing enabled, and who else may administer it.
- A budget alert. The research estimated about 0.5 TB for a four-nation DTM mirror with 1 cm lossy compression. It used a storage price of $0.023 per GB-month that it didn't check, and it didn't estimate egress or CDN cost, which "will likely exceed storage".
- A stable public https address for the site. OpenStreetMap only accepts https redirect addresses, apart from http://127.0.0.1 for development.
- A contact URL or address for the project User-Agent. Overpass returned 406 and Wikidata 429 to generic agents, and Nominatim's policy requires an identifying agent.

**Meanwhile.** Agents can write and check the infrastructure code against a placeholder project. Nothing is applied.

**Deliverables:**

- A Google Cloud project with billing, a budget alert and a site address

**Exit criteria:**

- The project ID, billing account, budget alert, site address and User-Agent contact are recorded in the deployment workstream of the v1 plan.

### WS3 — Sign-in provider credentials

**Status:** To do. Waiting on WS2 for the production redirect address.

**Who.** The owner registers Field Club with each provider named in Decision 0002: Google, Apple, Microsoft, Facebook and OpenStreetMap, plus a sender for the emailed one-time link. Decision 0002 offers a provider only when its credentials are configured, so each one can arrive separately.

**What the research recorded:**

| Provider | Observed on 2026-11-10 |
|---|---|
| OpenStreetMap | Register at https://www.openstreetmap.org/oauth2/applications/new with any OSM account. Give a name, redirect addresses, the "confidential application" flag and the scopes. For sign-in only, request `openid`. The client secret is shown once. A development sandbox is at master.apis.dev.openstreetmap.org and needs its own registration. Whether a third-party app can get the `read_email` scope and email claim wasn't confirmed |
| Google | OpenID discovery worked, with scopes `openid email profile` and an `email_verified` claim. Registration wasn't tested |
| Apple, Microsoft, Facebook | Not researched |
| Emailed one-time link | Not researched. A sending service and address are needed |

**What it unblocks.** The accounts workstream in the v1 plan. Without any credentials the site can be read but nothing can be saved.

**Meanwhile.** Development uses the OSM sandbox and the project's development login. Suggested order: OpenStreetMap and Google first, because the research tested their discovery documents.

**Deliverables:**

- Registered sign-in provider clients, with secrets in the secret store

**Exit criteria:**

- Each provider is either registered, with its client ID and secret stored in the project's secret store and never in the repository, or recorded here as deferred.
- The OSM sandbox registration exists for development.

### WS4 — Other keys and accounts

**Status:** To do. Nothing here blocks the first build.

These need a person's details, so the research didn't create them.

| Account | What the research recorded | Unblocks |
|---|---|---|
| OpenAlex key | A free key needs an email-verified account and gives $1 a day. Without one, all requests from one IP share $0.10 a day, which on shared cloud egress "may already be spent by other tenants" | Paper discovery for a monument |
| Europeana API key | Required for the REST API; not tested without one | Possible extra finds metadata; coverage untested |
| Geograph API key | "You will need to request a Geograph API key yourself for live queries." The dumps need no key | Live "photos near here" |
| YouTube Data API key | Held in the Google Cloud project for `videos.list` backfill only. Default quota 100 `search.list` calls and 10,000 units a day | Video suggestions |
| OASIS | Register as a community-group organisation, role O1a. Level 7 "Specialist Data User" access is by request to the OASIS Management Board through the OASIS Helpdesk, address to find | Reporting surveys; research reuse |
| ArcGIS Location Platform | A decision, not only a sign-up. Without an account, showing Esri World Imagery or Wayback in a third-party app was outside Esri's stated terms. The account's stated price was "2M free then $0.15 per 1,000 tiles". Whether Field Club's users may then trace findings from it was unclear | The best cropmark imagery the research found |
| MapTiler key | Only if the coloured 1:25,000 of 1937 to 1961 or the one-inch Seventh Series are wanted. Free tier 100,000 tile requests a month, non-commercial only. Never reuse the key embedded in the NLS viewer | Two historic map series |

**Meanwhile.** Every feature above has a keyless fallback or can wait.

**Deliverables:**

- Registered accounts or keys for each row, stored as secrets

**Exit criteria:**

- Each row is created and stored as a secret, or recorded here as declined.
- The ArcGIS decision is made. If the answer is yes, the tracing question goes to Esri in writing before findings may be drawn over its imagery.

### WS5 — Archaeology Data Service

**Status:** Sent on 2026-11-11. Awaiting a reply.

**Contact.** ADS Helpdesk, help@archaeologydataservice.ac.uk, the address the research found on the ADS Deposit Agreement page. The research also named a contact form at https://archaeologydataservice.ac.uk/contact/.

**What it unblocks.** Decision 0007 makes the ADS catalogue a live source and says it moves to bulk only with written permission. The research found three conflicting ADS statements on the licence of catalogue metadata: CC0 in the Metadata Policy, CC BY 4.0 in the website terms, and "ADS Terms of Use and Access" on each record. It recommended sending this letter before building anything that stores ADS-terms records.

| Source | Reuse class | Suggested access now | If ADS says yes |
|---|---|---|---|
| ADS catalogue records under ADS Terms, about 1,060,652, including NRHE sites 309,810 and Excavation Index 167,820 | `non_commercial` | `live`, from the user's browser | `bulk` |
| DataCite records for prefix 10.5284, 146,930 DOIs | `open` (CC0) | `bulk`, no letter needed | No change |
| Defence of Britain and England's Rock Art, 20,173 and 2,103 point records in the catalogue API | `non_commercial` | `live` | `bulk` |

**Meanwhile.** The browser queries ADS directly and Field Club stores only record identifiers and addresses, as Decision 0007 sets out. The research flagged that this exposes users' IP addresses and queries to ADS, which needs a line in the privacy notice in WS16.

**Draft.** Sent on 2026-11-11:

```text
To: help@archaeologydataservice.ac.uk
Subject: Permission request: ADS Data Catalogue records in Field Club

Dear ADS team,

I run Field Club, a free, non-commercial citizen-science map. Volunteers
aged 16 and over look for earthworks in open government LIDAR, check
each other's findings and link them to existing records and reports.
It will carry no advertising, charge nothing and have no private
messaging. Members' contributions will be published under CC BY 4.0. It
will run on Google Cloud.

I'd like every finding to point back to the right ADS record, in a way
you're comfortable with. I'm interested in catalogue metadata only:
identifier, title, description, subject and period terms, location,
contributor and owner, landing page or DOI, and licence. No files,
images or report texts. The collections are chiefly the NRHE, the
Excavation Index, the Grey Literature Library, the HER and National
Trust inventories, Defence of Britain and England's Rock Art.

My questions:

a. Your Metadata Policy says ADS metadata is CC0. Your website terms say
   discovery metadata is CC BY 4.0. Each catalogue record shows the ADS
   Terms of Use and Access. Which governs catalogue records for ADS
   archives and reports, and which for third-party inventories such as
   the NRHE and the HERs?
b. May I hold a server-side copy to offer one search and one map across
   sources? Every record would show the depositor, "Archaeology Data
   Service (distributor)" and a link to the ADS record. Nothing would be
   offered for download or sale, and I'd remove any record within [N]
   working days of a request. Do I also need consent from depositors
   such as Historic England?
c. If so, would you prefer to send an export, re-enable OAI-PMH, or have
   me page through the catalogue API? I'd propose one request per
   second, overnight, with an identifying User-Agent.
d. Your terms ask that work building on the material be distributed in
   the public domain. Does publishing members' findings under CC BY 4.0
   with an open download meet that condition?
e. Until then, are you content for users' browsers to query the
   catalogue API directly, with nothing stored by Field Club?
f. Field Club may accept voluntary donations or grants solely to cover
   hosting, with no paywall, advertising or sale of data. Is that within
   "not-for-profit teaching and research"?
g. Your Archive and Library pages check each visitor before they show
   anything. A person's browser passes the check; a program is refused
   with "403 Forbidden". So a program can't confirm that Field Club's
   links to those pages still work. Is linking by DOI, through
   DataCite, the route you'd rather I used? Or could requests that
   carry Field Club's name and contact address be let through for
   that check, a handful a month, asking only for a page's headers?

I'll acknowledge ADS and the depositors on every record, and pass on
any errors members find. I'd welcome a call.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Deliverables:**

- A recorded reply from ADS to questions a, b and e
- Updated reuse classes and access modes for the ADS rows

**Exit criteria:**

- ADS has answered questions a, b and e in writing, and the answer is recorded here.
- The reuse class and access mode of each ADS collection are set from that answer.

### WS6 — Historic England

**Status:** To do. Three letters to three addresses.

**What it unblocks.** England has no open national index of undesignated sites. The research found Historic England issues NRHE terrestrial records to HERs under OGL v3 but has no public OGL release. It also found aerial photograph footprint services with empty licence fields, and service names that carry dates and will break.

| Source | Reuse class | Suggested access now | If Historic England says yes |
|---|---|---|---|
| Historic England Research Records, 354,740, on Heritage Gateway | `link_only` | `deeplink` | `open`, `bulk` from an OGL extract |
| Aerial photograph footprints | `link_only`, licence unstated | `live` | `open`, `bulk` |
| NMP hand-drawn raster tiles | `open` to confirm | none until confirmed | `bulk`, re-tiled to Web Mercator |
| SmartFrame thumbnails and Archive images | `link_only` | `deeplink` | As licensed |
| Greater London HER (GLHER) | `link_only` | `deeplink`, home page only | Record-level `deeplink` or a licensed extract |

The two reports disagreed on the NMP raster licence. The England report found it unconfirmed. The later completeness check read an ArcGIS item stating "(c) Historic England, 2023. This resource is licensed under the Open Government Licence 3.0", but read the metadata only and noted it may not be the service the first report tested. Ask anyway.

**Meanwhile.** England's undesignated sites come from the ADS catalogue live, open local HERs and deep links, as Decision 0007 sets out.

**Draft 1, open data request.** Contact: Heritage Information Partnerships or the Open Data team at Historic England, address to find.

```text
Subject: Open release of NRHE terrestrial records, aerial photo
footprint licence and stable service names

Dear Historic England,

I run Field Club, a free, non-commercial citizen-science map where
volunteers aged 16 and over look for earthworks in national LIDAR and
check them against existing records. Members' findings will be
published under CC BY 4.0. To tell someone in England whether a feature is
already known, I need a national index of undesignated records.

1. NRHE extract. Your NRHE to HERs licensing page says terrestrial NRHE
   records and their spatial data are issued under the Open Government
   Licence v3.0. Could the same extract be published on the Open Data
   Hub, or supplied to me under OGL? The fields I need are HOB UID, NMR
   number, name, monument types, periods, summary, grid reference and
   geometry, record type, accessioning status and the receiving HER's
   identifier. A release without descriptions would still help if
   third-party quotations prevent their release. Could you also tell
   me which HERs have completed the transfer?
2. Aerial photograph footprints. What licence and attribution apply to
   the footprint layers you serve publicly, and may they be cached and
   shown in a third-party map? The same question applies to the
   SmartFrame thumbnails.
3. NMP raster tiles. May I re-tile the hand-drawn NMP raster to Web
   Mercator on my own servers?
4. Stable names. Several services carry dates in their names. Could you
   provide stable addresses or redirecting aliases?
5. Could you publish a lookup from legacy HOB UIDs to the new Research
   Record references?

I'll attribute as you specify, show each dataset's date, link every
record back to Heritage Gateway or the relevant HER, and say that the
data isn't for planning use.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Draft 2, Heritage Gateway links.** Contact: heritagegateway@historicengland.org.uk.

```text
Subject: Stable links to Heritage Gateway from Field Club

Dear Heritage Gateway team,

I run Field Club, a free, non-commercial citizen-science map for
finding earthworks in LIDAR. It will link out to authoritative records
and won't copy, frame or embed Gateway content. Could you confirm:

1. that /listing/heritage-gateway/results/record/{dataset id}/{reference}
   is the permanent record address;
2. that the "View on map" address with the initialLatLong filter is
   supported for linking, and whether a radius can be set;
3. whether a feed or API exists or is planned;
4. for the Archive, that
   /images-books/archive/collections/aerial-photos/record/{reference}
   holds for oblique references such as 23786_011, and whether an index
   of references with centre points could be shared.

One more request. Your pages check each visitor before they show
anything. A person's browser passes the check; a program is refused
with "403 Forbidden". So a program can't confirm that Field Club's
links to your records still work. Could requests that carry Field
Club's name and contact address be let through for that check? It
would ask only for a page's headers, a handful of times a month.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Draft 3, Greater London HER.** Contact: glher@HistoricEngland.org.uk. The research found GLHER's terms forbid scraping, data mining and links to anything but the home page, and recommended no programmatic use until permission arrives. It also recorded that three automated requests were sent to GLHER before its terms were read.

```text
Subject: Linking to GLHER records from Field Club

Dear GLHER team,

I run Field Club, a free, non-commercial citizen-science map where
volunteers look for earthworks in LIDAR and check them against existing
records. Your terms allow links to the GLHER Online home page only.
London is the largest area with a published record that Field Club
can't point to.

May I link to individual record pages? Alternatively, could you supply
a licensed extract with record number, name, type, period, location and
record address? I won't scrape the site or call it from scripts.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Deliverables:**

- Three letters sent and their replies recorded
- Updated reuse classes and access modes for the table rows

**Exit criteria:**

- Each of the three letters has a recorded answer or has been chased once.
- The reuse class and access mode of each row in the table are set from the answers.

### WS7 — Portable Antiquities Scheme

**Status:** To do. The research suggested sending this one first among the record holders.

**Contact.** info@finds.org.uk, copied to permissions@britishmuseum.org, the licence address in the PAS terms.

**What it unblocks.** PAS terms updated 21/01/2026 license metadata as "CC-BY-NC-SA" with no version, forbid commercial use, and say "no text or data mining or web scraping is permitted" without written permission. They pre-authorise links to the home page only.

| Source | Reuse class | Suggested access now | If PAS says yes |
|---|---|---|---|
| PAS current records | `non_commercial` | `deeplink` | `bulk` minimal index at 1 km, through a token or export |
| 2022 ARIADNE snapshot, 945,228 records labelled CC-BY, an aggregator's copy | `open`, disputed | `deeplink` | Replaced by the current feed |

Attribution recorded by the research: "The Portable Antiquities Scheme/The Trustees of the British Museum".

**Meanwhile.** PAS stays deep-link only. Finds are never shown finer than 1 km.

**Draft:**

```text
To: info@finds.org.uk
Cc: permissions@britishmuseum.org
Subject: Linking to and referencing PAS records in Field Club

Dear PAS team,

I run Field Club, a free, non-commercial citizen-science map where
volunteers aged 16 and over look for earthworks in open LIDAR and
cross-reference them with existing records. I don't intend Field Club
to accept findspots from its members.

1. May I link to record pages at finds.org.uk/pas/recorded-find/{ID}?
   Your terms mention only the home page.
2. Could I hold a minimal index of published records: find ID, object
   type, broad period, parish and 4-figure grid reference, under your
   CC BY-NC-SA licence and attributed to "The Portable Antiquities
   Scheme/The Trustees of the British Museum"? Which version of the
   licence applies?
3. If so, which route would you prefer: an API token, the daily export,
   or a periodic file?
4. A May 2022 copy of PAS records on the ARIADNE portal carries a
   CC-BY label. Would you object if Field Club used it, as 1 km
   squares and not as findspots?

I'll never show a findspot finer than 1 km and will honour sensitive
aliases.

Separately, and in confidence: archived anonymous responses from your
record API appear to include a full-precision grid reference field
beside the parish-level location. I haven't used it and thought you'd
want to know.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Deliverables:**

- The PAS letter and private note sent
- PAS's recorded answers to questions 1 and 4

**Exit criteria:**

- PAS has answered questions 1 and 4 in writing, and the answer is recorded here.
- The private note has been sent to PAS and nowhere else.

### WS8 — Local record offices in England

**Status:** To do.

**What it unblocks.** Of England's 83 HERs, the follow-up survey found 3 bulk-ingestable, 15 with a public queryable service under an unstated or restrictive licence, 53 deep-link only and 12 with no online record found. Openly licensed HER data covered 2.9% of England's area strictly, 7.5% with Lincolnshire.

| HER | Reuse class | Suggested access now | Ask |
|---|---|---|---|
| City of York | `open` (OGL v3) | `bulk` | None |
| Cornwall and Isles of Scilly | `open` to confirm | `bulk`, flagged "licence to confirm" | A one-line OGL v3 confirmation, given non-commercial text on its ArcGIS Online item and 2020 metadata |
| Lincolnshire | `non_commercial` | `bulk`, flagged "licence to confirm" | Whether the OGL label or "should not be used in any commercial sense" governs |
| Exmoor | `open` to confirm | `live` | Whether Exmoor regards its layers as OGL, and permission to cache |
| Devon, 120,842 features | `link_only`, licence unstated | `live` | Permission to cache |
| Other Know Your Place partners: Somerset, Gloucestershire, Wiltshire, BANES, North Somerset, South Gloucestershire, Bristol, Worcester City | `link_only`, licences mixed or missing | `live` | Permission to cache or ingest |
| All others | `link_only` | `deeplink` | The standard request below |

The two England reports disagreed on Exmoor. The earlier one called it "clearly ingestible without asking". The later follow-up put it in the live, uncached group and recommended asking in writing first. This plan follows the later one.

The research found two arguments for the standard request. York, Cornwall, Lincolnshire and Stirling already publish openly. And HERs that take NRHE data under OGL can't charge for that information, and must carry the NRHE attribution when they supply it.

**Contacts.** Every HER address is to find. The research suggested sending the standard request through ALGAO if possible, address to find.

**Meanwhile.** Decision 0007's live and deep-link modes. The map shows per area whether local records are indexed, live, linked or absent.

**Draft, one-line confirmation for Cornwall or Lincolnshire:**

```text
Subject: Licence of your published HER data

Dear [HER name] team,

I run Field Club, a free, non-commercial citizen-science map where
volunteers look for earthworks in LIDAR and check them against existing
records. I'd like to show your published monument records, with your
attribution and a link to each record.

[Cornwall: your data.gov.uk record says the INSPIRE historic service is
under the Open Government Licence v3.0, but the ArcGIS Online item
carries non-commercial wording. Is the service OGL v3, and is it
current?]
[Lincolnshire: your extract carries an OGL label and also says it should
not be used in any commercial sense. Which applies? Field Club is
non-commercial either way.]

A one-line reply would be enough.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Draft, standard request to an HER:**

```text
Subject: A minimal open extract of [HER name] monument records

Dear [HER name] team,

I run Field Club, a free, non-commercial citizen-science map. Volunteers
aged 16 and over look for earthworks in LIDAR, check each other's
findings and see whether a feature is already recorded. Members'
findings will be published under CC BY 4.0, and I plan to offer an
export pack for sending them to the relevant HER.

Could you release a minimal extract under an open licence: monument
number, name, type, period, a point and the record's web address? York,
Cornwall and Stirling already publish theirs openly. Where your records
include NRHE content, that part already reached you under the Open
Government Licence.

If an extract isn't possible, may Field Club query your public map
service from users' browsers, storing nothing, and link to each record?

I'll show your name and a link on every record, and say that it isn't a
substitute for a formal HER search.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Deliverables:**

- The standard request sent to each record office
- Recorded replies, or one chase each

**Exit criteria:**

- Cornwall and Lincolnshire have answered before public launch, or are shown as `link_only`.
- Exmoor and Devon have each been asked.
- The standard request has gone to ALGAO or to each Know Your Place partner.

### WS9 — Record holders in Scotland, Wales, Northern Ireland and the islands

**Status:** In progress. The letter to Historic Environment Scotland was sent on 2026-11-11 and awaits a reply. The others aren't sent.

**What it unblocks.** All three nations' national indexes and designations are open and need no letter. The asks below cover the gaps around them.

| Holder | Contact | Ask | Reuse class and access now |
|---|---|---|---|
| Historic Environment Scotland | trove@hes.scot, cc GIEnquiries@hes.scot; c14@hes.scot for the radiocarbon index | A stable download for NRHE Areas and the Scottish Radiocarbon Index; licence wording; that trove.scot link patterns are permanent; a link-checker allow-list; whether trove.scot contributions are live | NRHE Areas `open`, `bulk` by manual browser download; trove.scot pages `deeplink` |
| Treasure Trove Unit | treasuretrove@nms.ac.uk | Licence for catalogue text and images, an export, and whether object-detail addresses are stable | `link_only`, `deeplink` |
| Heneb, Welsh HER | her@heneb.org.uk | A data-sharing licence for HER points: name, type and link at least | `link_only`, `deeplink` |
| Improvement Service and ALGAO Scotland | Address to find | The same, for Scottish council HERs | `link_only`, `deeplink`. Stirling is `open`, `bulk`, no ask |
| Manx National Heritage | Address to find | The same | `link_only`, `deeplink` |
| Jersey Heritage | Address to find | The same | `link_only`, `deeplink` |
| Cadw or Welsh Government | Address to find | Confirm OGL for the conservation area, World Heritage Site and guardianship layers on DataMapWales | `open` to confirm, `bulk` |
| Historic Environment Division, Northern Ireland | Address to find | A licence for the Archaeological Investigations layer, 3,271 excavation records, which HED said isn't released as open data | `link_only`, not used until licensed |
| Guernsey | Island Archives appeared to be the contact, address to find | Whether any online SMR or HER exists | None found |

On NRHE Areas, the research found the spatialdata.gov.scot download link was a genuine 404 and the licence wording was inconsistent: OGL v3 on the page, OGL v1.0 wording in the catalogue. It recommended using the stricter attribution until HES confirms.

**Meanwhile.** Deep links, and a manual browser download of NRHE Areas and the radiocarbon index through the checklist in WS13.

**Draft, Historic Environment Scotland.** Sent on 2026-11-11 with small changes by the owner, so the sent text differs a little from this draft:

```text
To: trove@hes.scot
Cc: GIEnquiries@hes.scot
Subject: Downloading NRHE Areas and the Scottish Radiocarbon Index for Field Club

Dear HES team,

I run Field Club, a free, non-commercial citizen-science map where
volunteers look for earthworks in LIDAR and compare what they see with
existing records. To show your records beside the LIDAR, a program
downloads each dataset you publish, keeps a copy with your attribution,
and fetches it again from time to time so the copy stays current. For
the site index I plan to use Canmore_Points.zip from inspire.hes.scot.
Thank you for publishing it there.

Two datasets are published only on trove.scot, and a program can't
download them from it:

- NRHE Areas ("Defining Scotland's Places"), nrhe_areas.zip
- the Scottish Radiocarbon Index spreadsheet

trove.scot checks each visitor before it shows a page or sends a file.
A person's web browser passes the check without the person noticing. A
program that asks for a file can't pass it, and gets the answer "403
Forbidden". On 10 and 11 November 2026 I got that answer from every
address I tried, including both downloads and robots.txt. For whoever
looks after the site: it is the JavaScript challenge from the Azure
web application firewall. I haven't tried to get round the check and
won't. I take it to be deliberate, and clause 7.1 of your terms
forbids scraping.

The other address I know of for NRHE Areas no longer works. The
catalogue record on spatialdata.gov.scot links to
https://www.historicenvironment.scot/media/e04lsbyn/nrhe_areas.zip,
which answers "404 Not Found".

I'd be grateful for your help with five things.

1. Could NRHE Areas and the Radiocarbon Index be published on
   inspire.hes.scot beside Canmore_Points.zip, or at any address that
   sends the file without the browser check? Until then I'll download
   each by hand in a browser and load that copy. Please tell me if
   you'd rather I didn't.
2. Which licence and attribution apply to the two datasets? The
   trove.scot download page says OGL v3. The catalogue record quotes
   the attribution wording of OGL v1.0.
3. Field Club will link to trove.scot pages, and won't frame or copy
   them. Are these addresses meant to be permanent?
   - a place, such as https://www.trove.scot/place/100342
   - the map at a point, such as
     https://www.trove.scot/search/map?q=*&page_type=Places&coords=228100,640290,5
   - old Canmore addresses of the form canmore.org.uk/site/[number],
     which redirect to trove.scot
4. I'd like a program to check now and then that links like those
   still lead to a page. It would ask only for a page's headers, a
   handful of times a month, and the same check refuses it. Could
   requests that carry Field Club's name and contact address be let
   through for that, or is there a way you'd prefer?
5. When a volunteer's finding in Scotland looks worth recording, where
   should they send it? Does trove.scot take contributions from the
   public yet?

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Draft, Treasure Trove Unit:**

```text
To: treasuretrove@nms.ac.uk
Subject: Linking to the Treasure Trove database from Field Club

Dear Treasure Trove Unit,

I run Field Club, a free, non-commercial citizen-science map for
finding earthworks in LIDAR. I'd like to link to object pages on your
database. Is there a licence for the catalogue text and images? Is an
export available with reference, type, period, parish and council? May
I rely on the object-detail address staying stable? Field Club would
show nothing finer than parish, and I don't intend it to accept
findspots from its members.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Draft, data-sharing request to an HER outside England.** Use for Heneb, the Improvement Service, Manx National Heritage and Jersey Heritage.

```text
Subject: Linking Field Club findings to [HER name] records

Dear [HER name] team,

I run Field Club, a free, non-commercial citizen-science map where
volunteers aged 16 and over look for earthworks in LIDAR and check them
against existing records. Your terms don't allow reuse without written
consent, so I'm asking first.

Would you grant a licence for a minimal set of HER points: record
number, name, type and the record's web address? If not, may I link to
individual record pages? I won't scrape or harvest your site.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Deliverables:**

- Letters to HES and the other record holders in the nations
- Recorded replies

**Exit criteria:**

- HES has answered questions 1 and 2, and the NRHE Areas attribution is settled.
- Each other row has a recorded answer or has been chased once.

### WS10 — LIDAR licence wording for Wales and Scotland

**Status:** To do.

**What it unblocks.** The attribution line on the map for the two nations Decision 0006 mirrors next.

**Wales.** Contact: data@gov.wales, the address on the Welsh Government LIDAR map page. The two DataMapWales pages that publish the national file said "Open Government Licence for Public Sector Information (OGL)". The tile catalogue layer and its catalogue record said "Not Specified: The original author did not specify a licence". No attribution string was given anywhere.

**Scotland.** Contact: GI-SAT, address to find. Phases 4 to 6 and Orkney 2023 gave only "Open Government Licence v3". The research suggested a generic "Contains Scottish Government LiDAR data, OGL v3" line until GI-SAT confirms. Four HES collections are under the Non-Commercial Government Licence with Fugro retaining ownership. Decision 0004 admits them. The research left open whether that restriction reaches derived hillshades in a free public tool, and whether HES would grant wider permission.

| Source | Reuse class | Suggested access |
|---|---|---|
| Welsh Government LiDAR 2020-23 | `open` to confirm | `bulk` |
| Scottish phases 1 to 6, Orkney, Outer Hebrides, coastal, national programme | `open` | `bulk` |
| HES 2010, HES 2010 S10, HES 2016-2017, Luing | `non_commercial` | `bulk`, separate prefix |

**Meanwhile.** Use the wording the publishers did give, and the generic Scottish line.

**Draft, Welsh Government:**

```text
To: data@gov.wales
Subject: Licence and attribution for the Welsh Government LiDAR 2020-23

Hello,

I run Field Club, a free, non-commercial citizen-science map where
volunteers look for earthworks in LIDAR. I'd like to use the national
1 m DTM from DataMapWales.

The map pages that publish the file say it's under the Open Government
Licence, but the tile catalogue layer says "Not Specified". Could you
confirm it's OGL v3, and tell me the attribution wording you'd like?

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Draft, GI-SAT:**

```text
Subject: Attribution for Scottish LiDAR phases 4 to 6 and Orkney 2023

Hello,

I run Field Club, a free, non-commercial citizen-science map where
volunteers look for earthworks in LIDAR, using data from the Scottish
Remote Sensing Portal.

1. For phases 4, 5, 6 and Orkney 2023 the catalogue gives only "Open
   Government Licence v3". What attribution wording would you like?
2. For the four HES collections under the Non-Commercial Government
   Licence, is showing derived hillshades in a free public tool within
   the licence?
3. Is there a release schedule for the rest of the National LiDAR
   Programme?

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Deliverables:**

- Letters to the Welsh Government and the Scottish Government
- Settled attribution lines

**Exit criteria:**

- The Welsh licence is confirmed in writing, or the Welsh layer launches with the wording on the publishing pages and a note that confirmation is pending.
- The Scottish attribution lines are settled.

### WS11 — National Library of Scotland tiles

**Status:** To do.

**Contact.** NLS, address to find.

**What it unblocks.** Historic map layers, and the comparison layer in Decision 0006. The NLS copyright page showed CC BY 4.0 for "commercial, non-commercial, educational and private purposes", with the credit "Reproduced with the permission of the National Library of Scotland". The old non-commercial exception for OS maps was still in the page source inside an HTML comment. The S3 tilesets are the viewer's internal addresses and not a published API. The research recommended asking before launch.

| Tiles | Reuse class | Suggested access now | Ask |
|---|---|---|---|
| Historic map S3 tilesets, including the 25-inch county sets | `open` (CC-BY) | `live` | Hot-linking from a public app, or a mirror to Google Cloud |
| LIDAR multi-direction hillshade sets | `open` | `live` comparison layer | None; NLS offers these for reuse |
| Combined VAT, terrarium and RVT LIDAR tiles | `link_only` | `deeplink` | Not on the NLS reuse list; ask before hot-linking |
| Roy Military Survey | `link_only` | `deeplink` | British Library permission, address to find |

**Meanwhile.** Hot-link only the sets NLS lists for reuse, at modest volume.

**Where the code stands (2026-11-11).** The England hillshade set is offered as the comparison layer. Seven NLS layers are defined and held back in `backend/src/fieldclub/layers.py` (`AWAITING_NLS`): the air photo mosaics of 1944 to 1950, the six-inch of 1888 to 1913, the 1:25,000 of 1945 to 1965, the one-inch of the 1920s to 1940s, both Bartholomew half-inch sets and the ten-mile general map. The historic maps group in the layer panel is empty until NLS answers. To release a layer, take it out of `AWAITING_NLS` and mark it `clean` in `docs/sources/worklists/map-layers.json` with the reason. Until then a finding's "open elsewhere" links lead to the NLS viewer for the same place.

**Draft:**

```text
Subject: Using NLS map tiles in Field Club

Dear NLS Maps team,

I run Field Club, a free, non-commercial citizen-science map where
volunteers look for earthworks in LIDAR and compare them with historic
maps. I'd credit every layer "Reproduced with the permission of the
National Library of Scotland" with a link to maps.nls.uk.

1. May a public app load your mapseries-tilesets S3 layers directly,
   including the 25-inch county sets? If you'd prefer, I'll mirror them
   to my own storage under CC-BY, or use MapTiler.
2. Your copyright page now shows CC-BY by default. Could you confirm in
   writing that this covers the OS six-inch and 25-inch maps of England
   and Wales?
3. May I hot-link the Combined VAT and terrarium LIDAR tiles, which
   aren't on your reuse list? If not, I'll render my own.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Deliverables:**

- A letter to NLS
- An access mode set for each tileset

**Exit criteria:**

- NLS has answered questions 1 and 3, and each tileset's access mode is set from the answer.

### WS12 — Northern Ireland LIDAR

**Status:** To do.

**Contact.** DAERA or AFBI, address to find.

**What it unblocks.** Open LIDAR covered about 16.6% of Northern Ireland. DAERA announced on 9 February 2022 "A LiDAR survey covering all of Northern Ireland" for the Soil Nutrient Health Scheme. AFBI said on 20 August 2024 it had been applied across Zones 1 and 2, 48% of Northern Ireland. OpenDataNI returned no dataset for it. The research called it "the only route found to whole-NI coverage".

**Meanwhile.** Northern Ireland uses the open river-basin, Belfast, Lough Neagh and HED surveys, with the coverage layer showing the rest as uncovered. It sits outside the v1 England plan.

**Draft:**

```text
Subject: Open release of the Soil Nutrient Health Scheme LIDAR

Hello,

I run Field Club, a free, non-commercial citizen-science map where
volunteers look for archaeological earthworks in LIDAR. Open LIDAR
covers about a sixth of Northern Ireland, so most of its monuments
can't be seen.

Your announcements describe a LIDAR survey covering all of Northern
Ireland for the Soil Nutrient Health Scheme. Is there a plan to release
the bare-earth terrain model under the Open Government Licence? Has
capture for Zones 3 and 4 finished? Is the 2021 coastal survey
available as raw GeoTIFF anywhere?

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Deliverables:**

- A letter to the Northern Ireland LIDAR holders
- A recorded reply or one chase

**Exit criteria:**

- A recorded answer, or one chase sent.

### WS13 — Browser checklist

**Status:** To do.

**Who.** The owner, in an ordinary browser. These publishers block scripts, and the research didn't work around their challenges. Open each page and copy the facts back into this plan.

**What it unblocks.** The deep-link templates. The research asked for this before the templates are frozen in code.

The checklist from the follow-up on blocked publishers:

1. finds.org.uk/pas/recorded-find/OXON-CDA4F5: does it load, and what location is shown, parish or map shape?
2. finds.org.uk/database/artefacts/record/id/1064818: where do you land?
3. finds.org.uk/terms-of-service: the "most recently updated" date, and is a CC BY-NC-SA version given?
4. finds.org.uk/pas/recorded-find/search: is there a map or radius filter when logged out, and what are the distance options?
5. trove.scot/explore/download-our-data/national-record-of-the-historic-environment-data-for-download: the current nrhe_areas.zip link, file size and date. Download it.
6. The same for the scottish-radiocarbon-index page, xlsx and zip.
7. trove.scot/c14index/58574/: where does it land?
8. trove.scot/terms-and-conditions: the "last updated" date and the clause 6.1 licence link.
9. The Heritage Gateway lat/long link for 50.667761,-4.759080: does it centre the map, is there a radius control, and what are the Fetch/XHR calls? Open developer tools on the Network tab, filter to Fetch/XHR, pan and zoom once, and record each request's address, method, payload, content type, any token header, page size and total.
10. heritagegateway.org.uk/Gateway/Results_Single.aspx?uid=431862&resourceID=19191: does the search return exactly one record?
11. historicengland.org.uk/images-books/archive/collections/aerial-photos/record/23786_011: loads or 404?
12. Does the Aerial Photo Explorer or the NHLE map search address change with location, and what is the pattern?

Further checks other reports asked for:

13. On a Heritage Gateway results page, what does the "Download" button export: format, row limit and licence text?
14. Do the Web AppBuilder `center` and `level` parameters position the Aerial Photo Explorer and Mapping Explorer correctly?
15. Does archaeologydataservice.ac.uk/data-catalogue/?titleId=N open the matching record?
16. On the ADS pages for Defence of Britain and England's Rock Art, what download formats and licence are shown?
17. Do NISMR detail links work directly after the disclaimer is accepted once, or does each new session land on the disclaimer?
18. Do these deep-link patterns open at the right place: NLS viewer hash, Britain from Above, NCAP, Know Your Place, Google Earth and Old Maps Online? The research derived them from source code or memory.
19. Logged in, where do UK hobbyists talk today? Look at Reddit, the "LiDAR and Aerial Archaeology" Facebook group, and any Discord or Patreon communities around the YouTube channels.

**Meanwhile.** Deep links use the templates the research confirmed from archived copies.

**Deliverables:**

- Answers to the checklist items, pasted into this plan
- Dated copies of NRHE Areas and the radiocarbon index

**Exit criteria:**

- Answers to items 1 to 12 are pasted into this plan.
- NRHE Areas and the radiocarbon index are downloaded, with their date and size recorded.

### WS14 — Operating entity and a named responsible person

**Status:** To do. WS15 to WS17 wait on it.

**Who.** The owner decides who operates Field Club: an individual, a company or a charity. The research said this "decides the Online Safety Act provider, the data controller, ICO fee liability and who carries defamation risk".

**What it unblocks.** Ofcom's expectations for a small low-risk service include "a specific individual responsible for compliance". The terms, privacy notice and assessments all name the operator.

**Meanwhile.** Nothing launches publicly. Decision 0004 also asks that any grant or donation be checked against each non-commercial licence before it's accepted. No grant was pending on 2026-11-10.

**Deliverables:**

- A named operator and responsible person

**Exit criteria:**

- The operator and the named responsible person are recorded here.

### WS15 — Online Safety Act assessments

**Status:** To do. Waiting on WS14.

**What the research recorded.** Field Club is a regulated user-to-user service. The limited-functionality exemption covers only comments on provider content, and members' findings, photos and comments fall outside it. Ofcom gives three months after launch to complete an illegal content risk assessment, with a written record reviewed at least annually. Every in-scope service must also do a children's access assessment within three months of becoming available to UK users. An age limit in the terms doesn't count as keeping children out; only highly effective age assurance does. A child is anyone under 18.

Decision 0009 admits 16 and 17 year olds and accepts the children's risk assessment and safety duties that follow. The owner's actions:

- Complete and keep a written illegal content risk assessment, considering each kind of priority illegal content separately. Ofcom provides templates and a digital toolkit.
- Complete the children's access assessment and the children's risk assessment.
- Watch for the under-16 regulations. A gov.uk fact sheet of 18 September 2026 said "The first set of Regulations will be laid before the end of the year". Decision 0009 reviews the minimum age when they're published. Whether a citizen-science map counts as social media wasn't defined.

**Suggested use.** Complete all three assessments before public launch rather than in the three months after.

**Deliverables:**

- Three dated Online Safety Act assessments
- A review date

**Exit criteria:**

- The three assessments are written, dated and stored where the operator can produce them.
- A review date is set.

### WS16 — Terms, privacy notice, complaints route and contributor terms

**Status:** To do. Waiting on WS14. Agents can draft the texts; the owner adopts and publishes them.

| Item | Requirement the research recorded |
|---|---|
| Terms of service | Easy to find and understandable; say how users are protected; describe the complaints procedure (Online Safety Act s.10 and s.21) |
| Reporting and complaints | Easy reporting for users and affected non-users such as landowners (s.20); an accessible complaints procedure (s.21) |
| Intimate-image reports | Take down "as soon as reasonably practicable, and no later than 48 hours" after a report, with an expedited complaints route (s.10(3A) to (3B) and s.21(2A), inserted 29 June 2026). Any service that takes photos needs it |
| Defamation complaints | The 2013 Regulations: within 48 hours send the complaint to the poster and acknowledge the complainant; the poster has 5 days to respond |
| Privacy notice | Required. Must say that the browser queries ADS directly, which shows users' IP addresses and queries to ADS |
| Data-protection complaints | A way to complain, such as an electronic form; acknowledge within 30 days and respond without undue delay (Data Protection Act 2018 s.164A, in force 19 June 2026) |
| Cookies | A strictly necessary session cookie needs no consent; first-party statistics are allowed without consent with clear information and a simple way to object (PECR Schedule A1, from 5 February 2026) |
| Contributor terms | Contributions under CC BY 4.0, the `contribution_licence` in `docs/ARCHITECTURE.md`. Decision 0004 requires only an open licence that permits commercial reuse. The research suggested OSM-style terms: the member keeps ownership and grants Field Club a non-exclusive, perpetual, sublicensable licence, with an extra permission for use in OpenStreetMap. Members confirm they didn't copy from Google imagery, Ordnance Survey licensed mapping or HER data supplied under licence |
| Conduct agreement | The research pointed to the Kent LiDAR Portal's terms: no trespass without the landowner's permission, the Countryside Code, and no metal-detecting, excavation or survey without consent |

ADS question d in WS5 asks whether CC BY 4.0 meets its "public domain" condition. Hold the contributor terms until ADS answers, or publish them and revisit if ADS disagrees.

**Deliverables:**

- Published terms, privacy notice, complaints route and contributor terms

**Exit criteria:**

- The terms, privacy notice, complaints route and contributor terms are published at stable addresses before public launch.

### WS17 — Data-protection fee check

**Status:** To do. Waiting on WS14.

**What the research recorded.** "Organisations using personal data must pay the ICO data protection fee unless exempt." The ICO page was fetched, but the fee tiers and exemption test weren't re-read on 2026-11-10. The research recommended checking the position once the operating entity is decided.

**Deliverables:**

- A recorded fee payment or exemption check

**Exit criteria:**

- The fee is paid, or the exemption that applies is recorded here with the date it was checked.

### WS18 — Sector agreement on sensitive locations and HER export

**Status:** To do.

**What the research recorded.** It found no published rule from Historic England, ALGAO, Cadw or HES on citizen platforms publishing coordinates of unrecorded sites. It recommended agreeing the policy with ALGAO and the national bodies directly, and settling who sees unreviewed findings with HER and police heritage-crime advice before launch. It also found curator involvement at the planning stage was the key to HER transfer in the Kent and Cranborne portals.

The owner's asks, all addresses to find:

- ALGAO, Historic England, Cadw, HES and the Department for Communities: which monument types they regard as sensitive, and whether they endorse the tiers in Decision 0005.
- Police heritage-crime advice on the public precision of unreviewed findings.
- Two or three English HERs and HES: whether they'll accept an export pack built on the Heneb V4 field list, and which identifiers they want before submission.
- A county HER or society to arrange field checks of findings.

**Meanwhile.** Decision 0005 applies as written.

**Deliverables:**

- Comments from a national body and from HERs
- An agreed export field list

**Exit criteria:**

- At least one national body and one HER have commented on the sensitivity tiers, and their comments are recorded.
- The export field list is agreed with at least two HERs.

### WS19 — Courtesy notices

**Status:** To do.

**Peak District National Park Authority.** Contact: address to find. The research couldn't read peakdistrict.gov.uk because it returned a challenge. This is a private security notice to the service's owner. Don't publish or discuss it anywhere else, and don't describe it in more detail than below.

The follow-up survey found that the authority's public ArcGIS service `PDNPA_HBSMR_Layers` advertised Create, Update and Delete to anonymous users and exposed internal file paths. Only read-only queries were issued. Whether writes succeed wasn't tested. The research recommended not building on the service and asking instead for a read-only extract of "Digitised Peak Archaeology" and "Eastern Moors Monument" under a stated licence. Suggested use: send the notice on its own, and make the extract request later in a separate message.

| Source | Reuse class | Suggested access now |
|---|---|---|
| PDNPA HBSMR reference layers | `link_only`, licence unstated | `deeplink`; the service is not queried |

**Draft, security notice:**

```text
Subject: Your ArcGIS service PDNPA_HBSMR_Layers

Dear Peak District National Park Authority,

While surveying public heritage data services for Field Club, a free,
non-commercial citizen-science map, I noticed that your ArcGIS service
PDNPA_HBSMR_Layers appears to advertise create, update and delete
operations to anonymous users, and that some attributes show internal
file paths.

I haven't tried to change anything and only read from the service. I'm
telling you privately in case it's unintended. I won't build anything
on the service.

Kind regards,
[Name]
[Role, Field Club]
[Contact address]
```

**Draft, extract request, to send later:**

```text
Subject: A read-only extract of Peak District archaeology layers

Dear Peak District National Park Authority,

I run Field Club, a free, non-commercial citizen-science map where
volunteers look for earthworks in LIDAR and check them against existing
records. Could you supply a read-only extract of "Digitised Peak
Archaeology" and "Eastern Moors Monument" under a stated licence? I'd
show your attribution and a link on every record.

With thanks,
[Name]
[Role, Field Club]
[Contact address]
```

**Portable Antiquities Scheme.** The private note about a field in PAS's API responses goes in the WS7 letter. The research said to tell PAS privately rather than publicly.

**Deliverables:**

- The Peak District notice, sent

**Exit criteria:**

- The Peak District notice is sent and its date recorded here.

## Phase exit criteria

When all of these are true, this plan closes:

- [ ] Defra has answered DSP3-11967 and the England supply route is chosen.
- [ ] The Google Cloud project is named and at least two sign-in providers are registered.
- [ ] ADS, Historic England, PAS, HES and NLS have each answered or been chased once, and every affected source has a reuse class and access mode set from the answer.
- [ ] Items 1 to 12 of the browser checklist are answered.
- [ ] The operator and responsible person are named, the three Online Safety Act assessments are written, and the terms, privacy notice, complaints route and contributor terms are published.
- [ ] The data-protection fee position is recorded.
- [ ] The Peak District notice is sent.
- [ ] All workstreams are done or explicitly deferred to a successor plan.

## References

- [Decision 0002](../architecture/decisions/0002-accounts-required-to-save.md) — accounts and sign-in providers
- [Decision 0004](../architecture/decisions/0004-field-club-is-non-commercial.md) — non-commercial status and reuse classes
- [Decision 0006](../architecture/decisions/0006-terrain-tiles-are-rendered-from-raw-elevation.md) — terrain, mirroring and the on-demand path
- [Decision 0007](../architecture/decisions/0007-the-record-index-stores-only-what-licences-allow.md) — access modes for records
- [Decision 0009](../architecture/decisions/0009-contributors-are-16-or-over-and-there-is-no-private-messaging.md) — minimum age and no private messaging
- [v1-england.md](v1-england.md) — the build plan these actions unblock
- `architecture/decisions/spikes/` — the evidence from the research pass of 2026-11-10
