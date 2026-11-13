# Plan — Lines and shapes, phase 2: suggestions, handing a marking on, and removing orphaned markings

**Status:** Proposed.

## Goal

Someone other than a marking's keeper can propose a change to its shape, which the keeper accepts or declines. A keeper can hand the marking on to another member. An admin can take back the shape of an orphaned marking that causes trouble. "Found by" stays the credit and never changes. This plan builds on Decisions 0005, 0028, 0029, 0032 and 0033, and replaces point 1 of Decision 0029 ("only the finder changes a shape").

## Prerequisites

- Lines and curves is live (`3958ced`, deployed 2026-11-13), and Decisions 0028 to 0031 are checked against it.
- A local PostGIS from `infra/docker-compose.yml` for the backend suite.

## What exists (2026-11-13)

Each claim was checked by reading the code on `main` on 2026-11-13, after lines and curves landed.

- **Who may change a finding.** `findings.check_finder` (`services/findings.py`) refuses anyone whose id isn't `finding.author_id` with 403 `not_finder`. `update_finding` calls it first, and so does `check_may_withdraw`. So one check today guards both editing and withdrawing.
- **How the interface asks.** `services/actions.finding_actions` runs the route's own checks and returns `edit` as `_action(lambda: findings.check_finder(finding, user))`. `FindingDetail.actions.edit` carries it. `Tools.tsx` shows "Edit" and "Change the shape" on `position.mayEdit`, which is `actions.edit.allowed` (`features/finding/describe.ts`). `ChangeShapePanel.tsx` opens the tool when `finding.actions.edit.allowed` and otherwise shows `NotYours`, whose copy says only the person who marked it can change it. `describe.ts` still works out `isFinder` by comparing handles, but uses it only for the "Your finding" heading and the "Copy a link to ask others" step.
- **Other powers tied to `author_id`.** Seeing a hidden finding (`findings.may_see_hidden`, `shown_clause`), raising its level (`sensitivity.may_change_sensitivity`), downloading a protected finding exactly (`downloads_exact`), being refused a second look on it (`review.check_may_answer`, `own_finding`), and being the finder whose class counts in the assessment (`confidence.assess`, `inputs.author_id`).
- **Applying a change of shape.** `shape_edits.change_shape(db, finding, by, *, path, outline, revision, placed)` doesn't decide who may. It checks `revision` against `shape_revision` (409 `shape_changed`), holds the shape to the limits, places the anchor, runs `looked_at.check` (422 `looked_at_moved`), writes a `finding_shape_changes` row with `user_id = by.id`, raises the revision and calls `looked_at.refresh_added`. What follows a change lives in `update_finding`, not in `change_shape`: the reassessment when `added_since_looked_m` moved, and the `shape_extended` activity for an extension or a reshape that carries a line on by 200 m or more.
- **`finding_shape_changes`** is unique on `(finding_id, revision)`, its `revision` is the revision after the change, and `kind` is checked against `ShapeChangeKind`. `path_before` is deferred and sent to nobody. `sensitivity.visible_shape` turns change rows into page entries, and gives a reader who doesn't see the finding exactly only `{"kind": "changed", "on": …}`.
- **`sensitivity.visible_shape(finding, viewer, changes, *, may_change, whole)`** decides each reader's view of a shape through `sees_exact`. `looked_at` goes only when `may_change` is true. Every signed-in member sees every finding exactly. A protected finding is a 1 km square for a signed-out visitor, and a hidden finding is seen only by its finder and moderators.
- **Deleting an account** (`auth/accounts.delete_account`) strips personal data and keeps the user row, marked deleted and named "Former member". Findings, second looks, evidence and comments stay. Follows and notifications go. Shared investigations pass to their longest-standing editor (`investigations.forget_account`). Nothing touches findings, so a deleted finder's findings stay published and nobody can change them.
- **Banning** (`moderation.ban`) ends sessions, treats the person as signed out, stops their evidence counting and drops their events from feeds. Their findings stay, and nobody can change them while the ban lasts.
- **What moderators can do to a finding.** Hide and unhide it (`moderation.set_hidden`, not their own), and lower its level (`PUT /mod/findings/{id}/sensitivity`). Nothing deletes a finding or changes its shape. `ModerationActionKind` has nine values, and `schemas/moderation.py` reads each logged action strictly with `ModerationActionKind(entry.action)`.
- **Telling people.** `activity.record` writes an `activity` row, notifies followers except the actor, and sends ids on `fieldclub_events`. `activity.notify_invitation` is the one notification-only kind, with no free text (Decision 0009). The feed and notifications keep only kinds in `_KNOWN_KINDS` (Decision 0033), and `shape_extended` is listed only to readers who see the finding exactly (`services/feed.py`). A finder follows their own finding when they make it.
- **Limits on writes.** `ratelimit.rate_limit` is an in-memory token bucket per process, keyed by user. `PATCH /findings/{id}` and `POST .../withdraw` share `findings_edit`, 120 an hour. Moderation writes share `moderation`, 600 an hour.
- **The drawing tool** doesn't know how its result is saved. `ChangeShapePanel` alone sends `PATCH` with the revision it began on, keyed by `editingKey` (`finding:<id>:<revision>`). `changeShapeId` reads `/mark/finding/<id>` and refuses any longer path.

## Decided by the owner

- Someone else's change to a marking is a suggestion that the marking's keeper accepts or declines.
- A marking can be handed on to someone else.
- Admins can remove "orphaned markings that cause trouble".
- **Found by** is the credit and never changes. **Kept by** is who may edit, and is what transfers.
- The second phase mustn't change how the first was built.
- Joining different people's lines into one finding waits "until we actually hit the need". It isn't planned here.
- When a keeper's account is deleted, the marking is orphaned and the admins are told. Asked on 2026-11-13 whether keeping should go back to the finder instead, the owner said: "lets just orphan, and alert the admin".
- An admin can offer an orphaned marking's keeping to a volunteer: "yes".
- Removing is for admins alone: "admin - they can always pass it over to a moderator. we can adjust once we have real behaviour and issues to address".
- Keeping covers the whole edit: a new keeper changes the title, the description, the kind of feature and the period as well as the shape, and the finder keeps only withdrawing. Asked on 2026-11-13 whether the finder should keep the words, with the whole edit recommended, the owner said: "i agree with your reccomendation".

## Design

### Keeping

`findings.keeper_id`, a nullable foreign key to `users`. Null means the finder keeps it, so nothing is backfilled and a version that doesn't know the column goes on working. `findings.keeper_of(finding)` gives `keeper_id or author_id`.

`check_finder` splits in two, both in `services/findings.py`:

- `check_keeper` guards `update_finding`, `actions.edit`, accepting and declining suggestions, and handing on. Refusal is 403 `not_keeper`. `not_finder` stays as a code for what the finder alone does.
- `check_finder` keeps withdrawing. Withdrawing takes back the finder's claim that something is there, which is the credit, not the marking.

Everything else tied to `author_id` stays with the finder: seeing the finding while hidden, raising its level, exact downloads, being refused a second look, and the finder's class in the assessment. A keeper who isn't the finder sees a hidden finding no more than any member does, so they can't change it until it is shown again. That keeps the hidden-finding rule in the one clause it is in now.

**Handing on** is an offer and an acceptance, because keeping is a duty and nobody should be given it unasked. `findings.keeping_offered_to` (nullable user id) and `keeping_offered_at` hold one offer at a time, and a new offer replaces it. When the offer is taken up, `keeper_id` becomes that person, or null when it is the finder, the offer clears, and the new keeper follows the finding.

**When the keeper's account goes.** `delete_account` calls `findings.forget_keeping`. Keeping stays with the deleted account, so every marking it kept is orphaned, whether or not its finder is still a member. Offers made by or to that person are cleared, and their pending suggestions are withdrawn. Each admin gets one notification for the deletion, saying how many markings it left without a keeper. A ban changes nothing stored: the banned keeper can't act while it lasts, and lifting it gives everything back. Nobody is told of a ban's orphans, since a moderator or an admin made it.

**Orphaned** means the keeper's account is deleted or banned. An admin can offer an orphaned marking's keeping to any member, its finder included, with the same offer and acceptance a keeper uses, and finds orphaned markings in a list of their own. Removal is for orphaned markings only, as the owner put it, and for admins only. A marking whose keeper is active and causing trouble is hidden by a moderator, and if the keeper is the trouble, banning them makes it orphaned.

### Suggestions

A suggestion gets its own table, `shape_suggestions`. A row in `finding_shape_changes` with a state was weighed and rejected: that table is unique on the revision a change made, which a pending suggestion doesn't have, and every reader of it (the page's timeline, `visible_shape`, the newest 50) would need a new filter. That changes how the first phase was built.

| Column | Holds |
|---|---|
| `id`, `created_at` | |
| `finding_id` | Cascade on delete |
| `user_id` | Who suggested it. Credited on the change row if it is accepted |
| `base_revision` | The finding's `shape_revision` it was made on |
| `path` jsonb, deferred | The whole proposed path, as `shapes.Path.to_json` writes it |
| `outline_mid` Geometry, deferred | The derived shape simplified as `outline_mid` is, for drawing |
| `kind`, `length_m` | `shapes.classify_change` against the base, and the new length, for the list |
| `state` | `pending`, `accepted`, `declined` or `withdrawn` (`SuggestionState`, `enum_check`) |
| `decided_by`, `decided_at` | The keeper or admin who decided, and when |
| `applied_revision` | The revision accepting made, which names its `finding_shape_changes` row |

A partial unique index allows one pending suggestion per person per finding. A new one from the same person withdraws the old. A finding holds at most `SUGGESTIONS_MAX_PENDING = 20` pending, so 20 paths of 5,000 points bound the storage.

**Making one.** Any contributor may suggest, except the keeper, who changes the shape directly. The finding must be open, not withdrawn, and seen exactly, which every member does. The path names `path_revision`, which must equal `shape_revision`. The suggestion is held to the same limits as an edit and to `looked_at.check` when it is made, so a suggestion that couldn't be accepted is refused at once.

**Accepting.** Under the finding's lock, `suggestions.accept` checks `check_keeper`, that the suggestion is pending and its author isn't banned, and that the request's `shape_revision` equals the finding's. It then calls the new `findings.apply_shape_change(db, finding, by=suggester, path=…, revision=finding.shape_revision)`, which is today's tail of `update_finding` moved out unchanged: `change_shape`, the reassessment, and `shape_extended` with the suggester as actor. The change row credits the suggester, and the suggestion records the keeper as `decided_by`.

**A suggestion made on an older shape.** When the keeper has changed the shape since, `base_revision` is behind `shape_revision`. The keeper may still accept it, because they are shown it drawn against the shape as it is now and told that it replaces the changes since. The accept request names the revision they saw, so a change made while they looked is 409 `shape_changed`. Accepting holds it to the limits, the anchor and `looked_at.check` as they are now. A suggestion that was fine when made and breaks the rule now, because second looks since have grown `looked_at`, is refused with 422 `looked_at_moved` and stays pending. The keeper declines it, or the suggester withdraws it and makes another on the shape as it is.

**Declining** sets the state. There is no reason text, since a notification carries none (Decision 0009). Talk goes in the finding's comments.

### Removing an orphaned marking

Hiding, withdrawing and deleting were weighed. Deleting the finding would take other people's second looks, evidence and comments with it, which `delete_account` keeps on purpose because they were published under an open licence. Withdrawing is the finder's claim, not an admin's. Hiding already exists, and takes the whole finding off the map with everyone's work on it.

So removal takes back the marking alone. An admin puts the shape back to an earlier revision, or removes it so the finding is a spot at its anchor. The finding, its anchor, its tier, every answer and all evidence stay. `change_shape` gains a keyword `held_to_looked_at: bool = True`, and the admin's call passes False, because an earlier shape may lie outside ground looked at since. `looked_at` itself is kept, so the finding stays held to what was looked at. The change row names the admin, with an existing kind (`reshaped` or `removed`), and the moderation log records `remove_marking` with the reason.

### The API contract

All under `/api/v1`, with `X-OpenAntiquity-Client: web` on every mutating request. `Contributor` guards every route.

| Route | Body | Answer | Refused with |
|---|---|---|---|
| `POST /findings/{id}/suggestions` | `{path, path_revision}` | 201 `Suggestion` | 404 `finding_not_found`, 409 `finding_withdrawn`, 409 `shape_changed`, 422 `path_revision_required`, 422 `own_marking` (the keeper), 422 `suggestion_unchanged`, 409 `too_many_suggestions`, the path limits, 422 `looked_at_moved`, 429 |
| `DELETE /findings/{id}/suggestions/{sid}` | | 204 | 403 `not_suggester`, 409 `suggestion_decided` |
| `POST /findings/{id}/suggestions/{sid}/accept` | `{shape_revision}` | 200 `FindingDetail` | 403 `not_keeper`, 409 `suggestion_decided`, 409 `suggester_banned`, 409 `shape_changed`, 422 `looked_at_moved`, 422 `outline_too_far`, the path limits |
| `POST /findings/{id}/suggestions/{sid}/decline` | | 200 `Suggestion` | 403 `not_keeper`, 409 `suggestion_decided` |
| `PUT /findings/{id}/keeping/offer` | `{handle}` | 200 `FindingDetail` | 403 `not_keeper` (an admin may offer an orphaned marking), 404 `user_not_found`, 409 `user_banned`, 422 `already_keeper`, 409 `finding_hidden` |
| `DELETE /findings/{id}/keeping/offer` | | 204 | 403 `not_offered` (only the keeper or the person offered) |
| `POST /findings/{id}/keeping/accept` | | 200 `FindingDetail` | 403 `not_offered`, 409 `finding_hidden` |
| `GET /mod/markings/orphaned` | | 200 a page of findings whose keeper is deleted or banned, newest first | 403 `admins_only` |
| `GET /mod/findings/{id}/shapes` | | 200 each revision with `path_before`, newest first, 50 a page | 403 `admins_only` |
| `PUT /mod/findings/{id}/marking` | `{to_revision: int \| null, shape_revision, reason}` | 200 `FindingDetail` | 403 `admins_only`, 409 `not_orphaned`, 409 `shape_changed`, 422 `no_such_revision` |

`Suggestion` is `{id, by: PublicUser, created_at, base_revision, behind: bool, kind, length_m, path, outline, state, decided_at}`. `PATCH /findings/{id}` and `actions.edit` answer 403 `not_keeper` in place of `not_finder`. `review.check_shape_seen`'s message says "the keeper" in place of "the finder".

`FindingDetail` gains:

- `keeper: PublicUser`, the same as `author` until it is handed on.
- `keeping: {offered_to: PublicUser, offered_at}` or null, sent only to the keeper, the person offered and moderators.
- `location.shape.suggestions`: the pending ones, newest first, and `changes[].suggested_by` for an accepted one.
- `actions.suggest`, `actions.decide_suggestions`, `actions.hand_on`, `actions.take_keeping` and `actions.remove_marking`, each from the route's own checks, as `actions` does now. `actions.edit` asks `check_keeper`. `shape.looked_at` goes to anyone with `edit` or `suggest` allowed, so a suggester sees what has to stay.

### What each reader is sent

`sensitivity.visible_shape` gains a `suggestions` argument and returns them inside the same `sees_exact` test, so one place still decides.

| What | A reader who sees the finding exactly | A signed-out reader of a protected finding | A reader of a hidden finding |
|---|---|---|---|
| A suggested path, its outline, kind and length | Sent | Nothing, not even a count | The finder and moderators only, as exact readers |
| Who suggested | Sent with the suggestion and on the accepted change | Nothing | As exact readers |
| An accepted suggestion | A timeline change with `suggested_by` | `{"kind": "changed", "on": …}`, as for any change | As exact readers |
| `keeper` | Sent | Sent: a name says nothing of a place | The finder and moderators only |
| A hand-over offer | The keeper, the person offered and moderators | Nothing | Refused while hidden |
| `GET /mod/markings/orphaned`, `GET /mod/findings/{id}/shapes` | Admins only | | |

The feed and the event stream list `keeper_changed` to anyone who may list the finding, since it names a person and no shape. Notification-only kinds go to one person, who is a member and sees the finding exactly. Each new route names a leak test in `tests/test_routes.py`, built on a protected line read signed out.

### How people are told

- `shape_suggested`, notification only, to the keeper.
- `suggestion_decided`, notification only, to the suggester, with `data: {"accepted": bool}`.
- `keeping_offered`, notification only, to the person offered.
- `keeper_changed`, an activity row, to the finding's followers.
- `keeper_gone`, notification only, to each admin when an account that kept markings is deleted, with `data: {"markings": n}` and no free text. It opens the list of orphaned markings.
- An accepted extension records `shape_extended` as today, with the suggester as actor.

Each new activity kind is passed over by the version before it (Decision 0033, already live). `moderation_actions.action` gains `remove_marking`, which `schemas/moderation.py` reads strictly, so the passing-over for moderation action kinds ships in a deploy of its own first (Decision 0033, point 3). `SuggestionState` belongs to a new table that no earlier version reads.

### Limits

- `suggestions`, 30 an hour per member, on making one. Accepting, declining and offers share `findings_edit`.
- 20 pending per finding, one per person per finding, 5,000 points per path, as an edit.
- `remove_marking` shares the `moderation` bucket.

## Workstreams

Build in this order. Each step is test first, against real PostGIS.

### WS-A — Backend

**Status:** Not started.

1. **Moderation action kinds passed over.** The log list leaves out a kind it doesn't know. Deployed alone, before step 6. Test: a row with an unknown action doesn't break `GET /mod/actions`.
2. **Moving the tail of an edit.** `findings.apply_shape_change` takes today's shape code out of `update_finding` unchanged. Exit: the whole existing suite passes with no test edited.
3. **Keeping.** `keeper_id`, `keeping_offered_to`, `keeping_offered_at` in `create_all` and `extras.sql`. `check_keeper`, `keeper_of`, `actions.edit`, the offer routes, `forget_keeping` in `delete_account`, `keeper_changed`, `keeping_offered` and `keeper_gone`. Tests: the finder edits until they hand on and not after; the keeper edits and can't withdraw; an offer to a banned or deleted account is refused; deleting a keeper leaves each marking it kept orphaned, whether or not the finder is active, and tells each admin once; an admin can offer an orphaned marking and nobody else's; a keeper can't act while the finding is hidden.
4. **Suggestions.** `services/suggestions.py`, the table, `shape_suggested` and `suggestion_decided`. Tests for every code in the contract; an accepted extension credits the suggester and tells followers; a suggestion behind the shape is accepted when the keeper names the current revision; one that `looked_at` has since outgrown is refused and stays pending; 20 pending is the cap.
5. **What readers are sent.** `visible_shape` with suggestions, `FindingDetail` fields, the new actions. Leak tests for every new route with a protected line read signed out.
6. **Removing an orphaned marking.** `held_to_looked_at`, the three `/mod` routes, `remove_marking` in the log. Tests: refused while the keeper is active; puts back an earlier revision outside `looked_at`; the finding's answers, tier and evidence are unchanged.

**Exit criteria:** `uv run pytest`, `uv run ruff check . && uv run ruff format --check .` and `uv run pyright` pass, and `tests/test_routes.py` names a leak test for each new route.

### WS-B — Frontend

**Status:** Not started.

1. `pnpm gen:api` once WS-A step 5 lands.
2. **Byline.** `FindingHead.tsx` reads "Found by X on date" and adds "Kept by Y" when they differ. `NotYours` says only the keeper changes the shape and offers "Suggest a change".
3. **Suggesting.** The drawing tool opens at `/mark/suggest/:publicId` for `actions.suggest`, with its own editing key so a suggestion and an edit never share a path. A panel beside `ChangeShapePanel` sends `POST …/suggestions`. The tool itself is untouched.
4. **Deciding.** A "Suggested changes" section for the keeper: each with who, when, what it does, "behind the current shape" when it is, "Show on the map" drawing it dashed over the shape, Accept and Decline. A refusal is said beside the suggestion.
5. **Handing on.** "Hand it on" in `Tools.tsx`, a handle field, the offer shown to the person offered with "Take it on" and "No thanks", and notification copy for the four new kinds.
6. **Admin.** A list of markings without a keeper, opened from the `keeper_gone` notification. On an orphaned finding, "Offer it to someone" and "Remove the marking", the second listing earlier revisions drawn on the map, with a reason.

**Exit criteria:** `pnpm test && pnpm typecheck && pnpm lint` and `pnpm build` pass. Every new control is reachable by keyboard with a visible focus ring.

### WS-C — End-to-end checks and documents

**Status:** Not started.

1. `frontend/e2e-full/suggestions.spec.ts`: a second member suggests an extension, the keeper accepts it, the timeline names the suggester; a hand-over is offered and taken up; a signed-out reader of a protected line sees no suggestion.
2. Documents: the findings area doc ("Changing a shape", "Constraints", "Implementation status"), `docs/ARCHITECTURE.md` routes and codes, `docs/UI.md`, `CHANGELOG.md` `[Unreleased]`, and the records below. `uv run docs/scripts/doctool.py lint` passes.

**Exit criteria:** `pnpm e2e` passes on the desktop and phone projects, and every present-tense sentence added is true of the merged code.

## Phase exit criteria

- [ ] A member who isn't the keeper can suggest a change, and only the keeper can accept or decline it.
- [ ] A marking can be handed on, and "found by" never changes.
- [ ] An admin can take back an orphaned marking's shape, and nothing else on the finding changes.
- [ ] No suggested path reaches a signed-out reader of a protected finding.
- [ ] All workstreams shipped or deferred to a successor plan.

## Decisions to write

- **Found by is the credit, kept by is who may change a finding, and keeping passes by offer and acceptance.** `keeper_id`, `check_keeper` against `check_finder`, what stays with the finder, and that a deleted keeper's markings are orphaned and the admins told. Replaces point 1 of Decision 0029.
- **Other people's changes are suggestions the keeper accepts or declines, held to the looked-at rule when accepted.** The separate table, the base revision, accepting behind the shape, credit to the suggester, the limits, and what each reader is sent.
- **An admin takes back an orphaned marking's shape and never deletes the finding.** What orphaned means, why not hide, withdraw or delete, and why the looked-at rule is set aside for it.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| A suggested path reaches a signed-out reader of a protected finding | High | One gate in `visible_shape`, and a leak test per new route |
| A keeper accepts an old suggestion and undoes their own extension | Medium | "Behind the current shape" on the card and in the confirmation, and the change keeps `path_before` |
| Moving the tail of `update_finding` changes what an edit does | Medium | Step 2 lands alone and passes the suite unedited |
| Suggestion spam fills a keeper's notifications | Medium | 30 an hour, one pending per person, 20 per finding, the report button |
| A keeper hands a marking to a throwaway account to dodge moderation | Low | A ban still orphans it, and admins can take back its shape |
| Deploy order: an old version meets `remove_marking` | Medium | WS-A step 1 ships first, alone |

## Left out

- Joining or merging different people's lines, as the owner decided.
- Suggestions to the title, description, class or period. Comments carry those.
- Changing a suggestion, or merging two. The suggester makes a new one.
- A keeper seeing a hidden finding they don't hold the credit for.
- Several keepers, and keeping passed on for inactivity.
- Undoing a change from the finding page.

## Open questions for the owner

None. The four that were open were answered on 2026-11-13 and are under "Decided by the owner".

## References

- [Findings](../architecture/findings.md) — shapes, changing a shape, what each reader is sent
- [Plan: lines and curves](archive/lines-and-curves.md) — "Left out of the first version"
- [Decision 0029](../architecture/decisions/0029-only-the-finder-changes-a-shape-a-change-keeps-the-second-looks-and-most-of-what-was-looked-at-stays.md) — only the finder changes a shape, which this plan's first record replaces in part
- [Decision 0032](../architecture/decisions/0032-findings-are-open-or-protected-and-the-restricted-level-is-dropped.md) — two levels, so every member sees every finding exactly
- [Decision 0033](../architecture/decisions/0033-a-version-passes-over-stored-values-a-later-one-added.md) — adding an activity kind safely, and what other vocabularies need
