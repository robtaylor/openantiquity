# Field Club: product design

Field Club is a shared map for finding and checking archaeological earthworks in UK LIDAR data. You open it and you're looking at terrain processed to show banks, ditches and mounds a few centimetres high. You mark what you see. Other people check it, add evidence from old maps, aerial photos and heritage records, and the finding's confidence rises as independent people and independent sources agree.

The name comes from the Victorian field clubs, societies of amateurs who went out together to look at antiquities.

## Who uses it

Someone with five minutes on a phone wants to look at something interesting and do one useful thing. A regular hobbyist wants to scan their own patch, post what they find and see what others make of it. A serious investigator, who might be an amateur writing up a parish, a Historic Environment Record officer or a YouTube presenter researching an episode, wants every relevant record, map and paper for an area in one place, and a way to keep working notes.

The tool has to serve all three without making the first one read a manual or the third one feel they're playing a game.

## Principles

1. Looking comes first. The map opens on LIDAR with no sign-up wall, and you can try marking before you join. Saving needs an account, so everything shared has a real person behind it.
2. A finding is a claim, and a claim needs evidence. The tool records who saw what, in which data, and what they think it is. It never treats a pin on a map as a discovery.
3. Every finding says what would raise its confidence next. Those open steps are the tasks offered to everyone else. Helping is always concrete and small.
4. Known sites count. Spotting a scheduled barrow you didn't know about shows your eye is good. The tool says so and links the record.
5. Credit is specific. A finding lists who spotted it, who confirmed it, and who found the 1888 map that shows it.
6. Sites come before stars. Where publishing an exact location could invite damage, the location is coarsened for most people.
7. Open data in, open data out. Everything indexed carries its licence and attribution. Everything contributed can be exported in a form a Historic Environment Record can use.

## The map

LIDAR is the base layer, drawn in visualisations made for archaeology, not the single-direction hillshade most viewers offer. See `docs/sources/lidar.md` for where the elevation comes from.

| Layer | What it's good for |
|-------|--------------------|
| Composite | The default. A blend of sky-view factor, openness, slope and hillshade that shows most earthworks without choosing a light direction |
| Local relief | Removes the hills and keeps the small stuff. Best for ploughed-down features on flat ground |
| Sky-view | Ditches and hollows go dark, banks go bright. Good for enclosures and hollow ways |
| Multi-direction shade | Three lights in red, green and blue from different directions. Nothing hides parallel to the sun |
| Slope | Sharp edges of platforms, lynchets and quarries |
| Raking light | Drawn in the browser from elevation tiles. You drag the sun round and watch faint ridges appear |

Over or beside the LIDAR you can show aerial imagery, historic Ordnance Survey maps, the OpenStreetMap standard map, and geology. An OpenStreetMap overlay draws roads, paths, water and place names as thin lines on top of the terrain, so you always know where you are. Any two layers can be compared with a swipe handle. The terrain can be tilted into 3D with exaggerated height.

The map shows the grid reference, coordinates and ground height under the pointer. A line tool draws a height profile across a bank or ditch. Every view has a link that reopens it exactly, including layer and sun position.

Records from the heritage index appear as map layers by kind: designations, monument records, finds, fieldwork and reports, community data, and antiquities labelled on old maps.

## Findings

Marking a finding takes about ten seconds. You click the feature, pick what you think it is from a short list of pictured types, and save. A note, a period guess and a drawn outline are optional. The finding stores the layer, zoom and light you were using, so the next person sees what you saw.

The feature list is short on purpose: enclosure, hillfort, round barrow or mound, long barrow, hut circle, settlement earthworks, field system, ridge and furrow, linear bank or ditch, trackway or hollow way, road, moat, motte or castle earthwork, platform, pond or water management, pit or quarry, industrial, military, ritual monument, garden earthworks, and "not sure". Each maps to a term in the national monument-type thesaurus, so exports speak the language records officers use.

As soon as you save, the tool lists heritage records near the spot and asks whether your finding is one of them. One tap links it. If it's the same thing, the finding becomes "matches a known record", which is a good result and is shown as one.

## The confidence ladder

Confidence is a ladder of named steps. Each step has a rule anyone can read. The exact thresholds are in `docs/ARCHITECTURE.md`.

| Step | Plain meaning |
|------|---------------|
| Spotted | One person has marked it |
| Seen by others | At least two other people can see it too, and few can't |
| Corroborated | It shows up in two more kinds of evidence, such as an aerial photo and an old map, and people agree what it is |
| Probable | Reviewers have ruled out modern, natural and data-processing explanations, and an experienced reviewer agrees |
| Checked on the ground | Someone has visited or surveyed it and what they found supports it |
| On record | A Historic Environment Record, a designation or a publication now includes it |

Two rules keep the ladder honest. Agreement is weighted, so a trusted regular counts for one and a half members and a recognised archaeologist counts for three. And the evidence has to be independent: a finder can't corroborate their own finding by attaching five screenshots.

A finding can also leave the ladder. If most people can't see it, or agree it's a modern drain, a golf bunker or a processing stripe, it's marked as explained, with the reason. That's a useful result. It stays visible so the next person doesn't mark the same thing.

The finding page shows a meter, the current step, and a checklist of what's missing for the next one. "One more person needs to confirm they can see it." "Nobody has checked the 1888 map yet." Each line is a button that takes you to do exactly that.

When a finding moves up, everyone who helped gets told, by name. That moment is the reward the product is built around.

## Five minutes at a time

Three modes need no preparation.

Second look shows you findings waiting for another pair of eyes, one at a time, in the view the finder used. You answer "I see it", "not sure" or "can't see it", and optionally say what you think it is. Findings that are one answer away from moving up come first, so your answer often tips one over while you watch.

Scan a square sends you to a one-kilometre grid square that few people have looked at. You look it over, mark anything you see, or press "nothing obvious". The map keeps a coverage layer showing how many people have scanned each square. Empty squares matter: they're how we know an area was checked and not just ignored.

Help wanted lists open steps by kind, so you can do the sort of work you like. Map detectives check old maps. Sky checkers look for cropmarks. Record matchers link findings to the index.

## Serious work

An investigation is a shared notebook tied to the map. It collects findings, records, saved map views, height profiles, references and written notes, in an order you choose. A private investigation has one member, you. To invite collaborators, make it public or unlisted first. Publish it when you're ready. It exports as GeoJSON, as a spreadsheet using Historic Environment Record field names, and as a printable report.

The record index is searchable by name, type, period, source and area. A record page shows its source, licence, and a link to the original. For any spot on the map, "open elsewhere" offers one-click links to the same place in external viewers that we can't embed.

## Mentions and follow-ups

Finds get talked about. Anyone can attach a mention to a finding: a YouTube video at a timestamp, an article, a podcast, a paper. The tool fetches the title, channel and thumbnail. The finder and everyone who helped are told that their find was discussed. A feed shows recent mentions across the whole map.

Presenters who link to a finding's page in a video description don't need to do anything else. The tool watches a list of channels and adds those mentions itself.

What happens on the ground is recorded the same way. A site visit, a geophysics survey, an excavation, a new Historic Environment Record entry or a scheduling each becomes a dated entry on the finding's timeline with who did it and a link. These entries are also evidence, and they drive the top two steps of the ladder.

## Credit and reputation

People earn points when their findings climb, when their second looks match the eventual outcome, and when others endorse evidence they added. Every point is itemised. Points do one thing: at fifty, a member can be made "trusted" by a moderator, which gives their reviews more weight and lets them see restricted locations. A moderator makes the call because a few accounts working together could otherwise earn their way to restricted locations. There are no penalties for findings that get explained away, because marking doubtful things is how the doubtful things get checked.

There's no global leaderboard. Profiles show what someone has found and helped with.

## Protecting sites

Most earthworks visible in public LIDAR are at little extra risk from a pin on a public map, because the data is already public. Some are not: anything suggesting burials, hoards or rich Roman occupation could attract illegal metal detecting. Every finding has one of three levels. An open finding shows its exact position to everyone. A protected finding shows its exact position to people who've signed in. A restricted finding shows it only to its finder, trusted members, archaeologists and moderators. Anyone who may not see a position exactly sees a one-kilometre square instead. Some kinds of finding, such as round barrows, start at protected. A finder, a trusted member or a moderator can raise a level, and only a moderator can lower one.

Before logging a site visit, the tool reminds people of the rules that apply where the finding is: get the landowner's permission, never dig, never use a metal detector on a scheduled monument, and report finds to the Portable Antiquities Scheme or Treasure Trove.

Every finding, comment and piece of evidence has a report button. Moderators can hide content and restrict locations.

## Joining

You can explore everything without an account. You can also mark a finding, answer a second look or scan a square. That work is kept in your browser as a draft, labelled "not saved yet", and nobody else sees it.

Saving needs an account. Anonymous contributions would fill the map with marks nobody stands behind, and regular users would have to wade through them. An account also means your findings, your credit and your notifications follow you between devices.

Joining takes one tap: Google, Apple, Microsoft or Facebook, with OpenStreetMap for people who already map there and an emailed link for anyone who uses none of them. There are no passwords. After sign-in your drafts are saved as they were, without re-entering anything. You get a generated name such as "QuietBarrow42", which you can keep or change.

## Left out of the first version

Automatic feature detection by machine learning is out. So are private messaging, mobile apps, and editing of third-party records. Local Historic Environment Records that aren't published as open data are linked, not indexed.
