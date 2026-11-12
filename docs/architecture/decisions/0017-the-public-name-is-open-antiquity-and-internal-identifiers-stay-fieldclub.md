# Decision 0017 — The public name is OpenAntiquity and internal identifiers stay fieldclub

**Status:** Proposed.

**Current architecture:** [ARCHITECTURE.md, "Conventions"](../../ARCHITECTURE.md#conventions).

**TL;DR.** In the context of a product not yet public, facing a name with an unwanted second meaning whose nearest domains belonged to other people, we chose to call it OpenAntiquity everywhere a person outside can see and to leave the identifier `fieldclub` in the code and the cloud project, accepting two names for one thing in exchange for a rename that touched text and not structure.

## Context

When this was written the product was called Field Club in the interface, the API's text, its emails, the docs and two letters sent that day. The identifier `fieldclub` was the Python package, the prefix of every setting (`FIELDCLUB_*`), the command names, three cookies, a request header, the database, and the Google Cloud project `fieldclub-uk` with its buckets, secrets and service accounts. Nothing was public: the service ran held back from the public and no sign-in provider was registered.

The owner raised two problems with the name on 2026-11-11.

- It reads to many people as field sports, "rich folk shooting animals", and "club" suggests membership. The intended sense, the Victorian naturalists' and antiquarian field clubs, is the less common one.
- `fieldclub.uk`, `fieldclub.co.uk` and `fieldclub.org` belonged to other people. Only `fieldclub.org.uk` was free.

The owner chose the name, first written as two words, "Open" and "Antiquity", and settled on 2026-11-12 on one word in camel case, OpenAntiquity, to be used everywhere. They checked that trade marks were clear, and registered `openantiquity.org`, `openantiquity.com` and `openantiquity.co.uk` the same day. No project, organisation or journal of that exact name was found. The journal *Antiquity* calls its free-to-read section "Antiquity Open".

A Google Cloud project's id can never be changed, and by then the project held the database, the secrets and an elevation copy in progress.

## Decision

1. The public name was OpenAntiquity. It replaced Field Club in the interface, the API's text, emails, the `User-Agent` sent to data publishers (`OpenAntiquity/<version>`), the names of downloaded files, the id column of an export (`openantiquity_id`), the living docs and every letter not yet sent.
2. The same went for the names a visitor's browser is asked to hold and an API user has to send, because both are shown to people: the three cookies became `openantiquity_session`, `openantiquity_oauth` and `openantiquity_email_link`, which the privacy notice names, and the request header became `X-OpenAntiquity-Client`, which the API reference names. Two pairs of response models that shared a name were given names of their own, so the API reference no longer showed them with the package path.
3. The site's address was `openantiquity.org`. The `.com` and `.co.uk` were held to redirect to it.
4. The internal identifier stayed `fieldclub`: the package, the settings prefix, the command names, the CSS prefix `fc-`, the keys the interface keeps in the browser's storage, the database and its channel names, and every cloud resource name.
5. Records written before the change kept the old name: decision records 0001 to 0016, resolved spikes and archived plans. So did the two letters sent as Field Club, to Historic Environment Scotland and the Archaeology Data Service, which were recorded as sent. The new name was to be given in the reply when each answered.
6. Both names were reserved as handles and display names, so that no member could pass for the project under either.
7. The contact address stayed `fieldclub@shape.build` until a mailbox on the new domain existed.

## Alternatives considered

- **Keep Field Club and register `fieldclub.org.uk`** — rejected because of the second meaning, and because the three nearest domains would carry mistyped traffic to other people.
- **Rename the identifier too** — rejected because it would have touched over 400 files, every setting and every cloud resource for no visible gain, and the project id could not follow in any case.
- **A new cloud project under the new name** — rejected because the database, secrets and elevation copy would have had to be made again. The one place a visitor could meet the old identifier was the run.app address, which shows the service's name, and a domain hides that.
- **Other names** — Humps and Bumps, Low Sun, Fieldwalk, Lay of the Land, Read the Land and Spot Height were all free. The owner preferred OpenAntiquity, which also says how the work is done.
- **Wait until launch** — rejected because the sign-in providers' consent screens, the domain and the letters all carry the name, and each would have needed changing later.

## Consequences

- People see one name, and it has a domain in `.org`, `.com` and `.co.uk`.
- The word "open" is a promise: contributions are published under an open licence with an open download, and the name now depends on that staying true.
- The code has two names for one thing. A new contributor has to learn that `fieldclub` is OpenAntiquity.
- The cloud project id, bucket names and the run.app address still say `fieldclub`.
- Two organisations hold a letter under the old name, and Defra's supply request (ticket DSP3-11967) was made the day before the change.

## Walk-back options

- **If the journal *Antiquity* objects to the name** — the public name lives in the constant `APP_NAME`, the `User-Agent` prefix, the download names, the export's id column, the cookie and header names, and copy. Another rename of the same kind costs about as much as this one.
- **If the two names become a real source of mistakes** — rename the package and the settings prefix in one mechanical change. The cloud project id would still stay.

## Links

- Decision 0004 — the project is non-commercial, under either name.
- `infra/dns.toml` — the record sets managed for the three domains.
