# Changelog

All notable changes to Field Club are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/). Field Club is a deployed
service, so entries are dated, not versioned.

## [Unreleased]

### What this means for you

Nothing is live yet. When the first version opens, this is what it does for you.

- You can look at England's LIDAR as slope, sky-view, relief and other views made for spotting earthworks, and light it from any direction you like. You don't need an account to look at anything.
- Designated sites and other heritage records sit on the same map, each with who published it and under what licence. Where a record office doesn't let us keep its records, the map asks it directly or links to its own site.
- You can mark something you think is there. Other people then take a second look without seeing what you said, and the finding climbs from "Spotted" to "Seen by others" and on as people agree and add evidence.
- While you take a second look, the heritage records are hidden as well as the findings, so a record at the spot can't answer the question for you. They come back once you've answered.
- You can try marking, answering and scanning before you join. What you do is kept in your browser, and saved to your account when you sign in.
- Signing in is with Google, Apple, Microsoft, Facebook or OpenStreetMap, or an emailed link. You must be 16 or over to add anything.
- Possible burial mounds and other sites at risk from looting are shown as a one-kilometre square to anyone who isn't signed in.
- There are no private messages. Everything people say about a finding is public and attached to it.
- If you find an object, Field Club records nothing about it and tells you who to report it to in your part of the UK.
- A second look counts the moment you press your answer. You can then say what you think it is, or not, before you see what the finder and everyone else said. If you leave in between, you're offered the same choice when you come back.
- If a protected finding's title or note says where it is more closely than its one-kilometre square, the form says which one and what to take out.
- When a video, article, podcast or paper talks about a finding, you can add it to the finding's page. You see what the link is before you save it, and a video opens at the moment the finding comes up.
- A finding's page has a timeline of what has happened on the ground and on record, such as visits, surveys, digs and new heritage records, and says which of them moved it up.

### Added

- `GET /meta` says whether the development sign-in is on, which age bands the welcome step accepts, the contributor terms, each feature class's starting sensitivity and, per nation, where to report a find.
- `GET /auth/session` answers with the signed-in person or null. `GET /auth/me` carries a stable `id`, and `PATCH /auth/me` removes the picture a sign-in provider gave.
- `POST /findings` takes a `client_ref`, so a draft sent twice is saved once.
- `GET /records/{id}/findings`, the nearest settlement in `GET /geo/point`, what each context link shows, and how to read each live source.
- Explore lists the findings in view beside the map, kept in step with it, with filters for step, state and what a finding looks like. Choosing a finding in the list or on the map opens it and marks it.
- "Mark a finding": place a mark by tapping, clicking or with the keyboard, drag or nudge it, pick what it looks like and save. A title, the view you were using and the period are filled in for you. Signed out, the finding waits in your browser as a draft and is saved once you sign in.
- A finding's page shows how far it has got up the ladder and what would move it up, each with a button for what you could do about it. You can give it a second look there, add evidence of every kind, ground photos included, link a heritage record, join the discussion and follow it. It names the nearest place, and one press shows it as its finder saw it. Its finder can edit it, withdraw it and protect it more, and a moderator can lower its protection with a reason for the log. What anyone is offered is what the server says they may do. Evidence says how many people endorsed and disputed it.
- Second look: findings waiting for another pair of eyes, one at a time, in the view their finder used and with nothing about what they thought. Answer with one press, or the keys 1, 2 and 3, which sends it at once, add detail if you like, and then see the finding, how your answer compares and whether it moved it up. Nearby findings come first. Signed out, your answer waits as a draft you can still change, and is saved and revealed when you sign in.
- Mentions on a finding's page, newest first, with adding one after a look at what the address holds, and removing your own. Mentions the channel scan found are marked as found automatically. "Recent mentions" lists them across the map, with each finding as you may see it.
- The follow-up timeline on a finding's page, drawn from its site visits, surveys, digs, heritage records and designations, in date order.
- Help wanted: the next steps on everyone's findings, by the kind of work they are, such as map detectives checking old maps and sky checkers looking at aerial photos. Each finding opens with the form for that work ready. Second looks are offered only through the blind queue.
- Investigations: a notebook tied to the map for one piece of work. Start one with a title, then gather findings, heritage records, saved map views, height profiles, references and notes in it, in the order you choose, from its own page or with "Add to an investigation" on a finding, a record, a height profile or the layer panel. Notes take headings, bold, italics, lists and links. It starts private; make it unlisted or public to invite people by their handle, who join once they accept. Download it as GeoJSON, as a spreadsheet with Historic Environment Record field names, or as a printable report. Something taken out of one can be put back with “Undo” for a few seconds.
- Scan a square: one press sends you to a one-kilometre square few people have looked at, near where you are looking, framed on the map with the ground outside it shaded. Look it over in any view, mark what you see, then say "Nothing obvious" or "I marked something", or skip it, and one more press brings the next. Saving a finding you marked there brings you back to the square. An empty square counts: it shows the ground was checked. Signed out, your squares wait in your browser and are saved when you sign in. The scan coverage layer shows how many people have looked over each square in view.
- Activity: what people have been doing, newest first, in plain sentences, everywhere or in the map's view and by kind. A second look's part in it names nobody. It keeps up by itself while the page is open.
- Notifications: a quiet count on Account when a finding you follow changes, and the list on your account page, marked read as you see it.
- A finding's page shows a move up the ladder as it happens, without a reload.
