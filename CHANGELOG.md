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
- You can try marking, answering and scanning before you join. What you do is kept in your browser, and saved to your account when you sign in.
- Signing in is with Google, Apple, Microsoft, Facebook or OpenStreetMap, or an emailed link. You must be 16 or over to add anything.
- Possible burial mounds and other sites at risk from looting are shown as a one-kilometre square to anyone who isn't signed in.
- There are no private messages. Everything people say about a finding is public and attached to it.
- If you find an object, Field Club records nothing about it and tells you who to report it to in your part of the UK.

### Added

- `GET /meta` says whether the development sign-in is on, which age bands the welcome step accepts, the contributor terms, each feature class's starting sensitivity and, per nation, where to report a find.
- `GET /auth/session` answers with the signed-in person or null. `GET /auth/me` carries a stable `id`, and `PATCH /auth/me` removes the picture a sign-in provider gave.
- `POST /findings` takes a `client_ref`, so a draft sent twice is saved once.
- `GET /records/{id}/findings`, the nearest settlement in `GET /geo/point`, what each context link shows, and how to read each live source.
- Explore lists the findings in view beside the map, kept in step with it, with filters for step, state and what a finding looks like. Choosing a finding in the list or on the map opens it and marks it.
- "Mark a finding": place a mark by tapping, clicking or with the keyboard, drag or nudge it, pick what it looks like and save. A title, the view you were using and the period are filled in for you. Signed out, the finding waits in your browser as a draft and is saved once you sign in.
