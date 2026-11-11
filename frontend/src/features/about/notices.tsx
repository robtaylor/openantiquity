/**
 * The notices people must be able to read: the contributor terms, the privacy
 * notice, how to report something, and how to ask for something to be taken
 * down. Each is written from what the code does today (the backend's models,
 * `DELETE /auth/me`, the moderation routes), and each is a draft until the
 * owner settles it with legal advice (`docs/plans/owner-actions.md`, WS16).
 * Facts the API gives, such as the licence, the report reasons and their
 * deadlines, come from `/meta`.
 */

import { FilePenLine } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import type { Meta } from "../../api/meta.js";

export type NoticeId = "terms" | "privacy" | "reporting" | "takedown";

export interface NoticeEntry {
  id: NoticeId;
  title: string;
  /** One line for the list on the about page. */
  summary: string;
  Body: (props: { meta: Meta }) => ReactNode;
}

/** The address to write to, from `/meta` when the backend sends it. */
export function ContactAddress({ meta }: { meta: Meta }) {
  const contact = meta.app.contact?.trim();
  if (!contact) {
    return <>the address that will be given here before Field Club opens to everyone</>;
  }
  if (contact.startsWith("https://")) {
    return (
      <a href={contact} target="_blank" rel="noopener noreferrer">
        {contact}
      </a>
    );
  }
  const email = contact.replace(/^mailto:/, "");
  return <a href={`mailto:${email}`}>{email}</a>;
}

/** The mark at the top of every notice that it is a draft. */
export function DraftBanner() {
  return (
    <div className="fc-about__draft" role="note">
      <FilePenLine size={18} aria-hidden />
      <div>
        <strong>Draft</strong>
        <p>
          These words haven't been settled yet. The people who run Field Club still have to check them, with legal
          advice, before Field Club opens to everyone. They describe what the site does today.
        </p>
      </div>
    </div>
  );
}

function Terms({ meta }: { meta: Meta }) {
  const licence = meta.app.contribution_licence;
  return (
    <>
      <h4>Who can contribute</h4>
      <p>
        Anyone can look at the map without an account. To save anything you need an account, you must be 16 or over, and
        you must accept these terms. You accept them once, on the welcome step after your first sign-in.
      </p>

      <h4>What you add is public</h4>
      <p>
        Findings, evidence, comments, links to videos and articles, photos once they've been approved, and your profile
        can be seen by anyone. Your second looks are shown, with your name on the map, to the finder and to other people
        who have answered the same finding. Nobody else learns how you answered.
      </p>
      <p>
        Where a finding's exact place is hidden to protect the site, Field Club hides it everywhere it shows the
        finding, including grid references and coordinates written in what you add.
      </p>

      <h4>The licence</h4>
      <p>
        You keep the rights to what you add. By saving it you publish it under the{" "}
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">
          {licence} licence
        </a>
        , so anyone may copy, share and build on it, for any purpose, as long as they credit Field Club and the name you
        use on the map.
      </p>

      <h4>Only add what you may share</h4>
      <ul>
        <li>Add your own work, or work you have permission to share under {licence}.</li>
        <li>
          Don't trace or copy from Google or Bing imagery, Ordnance Survey mapping you hold under licence, or heritage
          records supplied to you under licence.
        </li>
        <li>Only upload photos you took, or have the photographer's permission to share.</li>
        <li>
          Don't post anything about a living person that they haven't made public: names of landowners, addresses or
          photos of people.
        </li>
        <li>This map is for earthworks. Don't record where objects were found.</li>
      </ul>

      <h4>How to behave</h4>
      <ul>
        <li>Be civil. Disagree with the evidence, not the person.</li>
        <li>
          Never use Field Club to plan anything illegal: digging, metal detecting where it isn't allowed, or trespass.
        </li>
        <li>
          Field Club has no private messages. Don't use comments to arrange to meet people you don't know, and never to
          meet anyone under 18.
        </li>
      </ul>

      <h4>Looking after the map</h4>
      <p>
        Moderators can hide anything that breaks these terms, hide the exact place of a finding, and ban an account. An
        account that is banned can't sign in, and what it added stops counting towards any finding's confidence.
        Everything a moderator does is written in a log the moderators share.
      </p>

      <h4>If you leave</h4>
      <p>
        You can delete your account from your account page at any time. Your personal details, your photos and your
        private investigations are deleted. What else you published stays, because it was published under an open
        licence and other people's work builds on it, but it is credited to “Former member” from then on. Your old name
        on the map no longer leads to it.
      </p>

      <h4>Changes</h4>
      <p>
        If these terms change, the new terms will be shown here, with the date, before they apply to anything you add
        afterwards.
      </p>
    </>
  );
}

function Privacy({ meta }: { meta: Meta }) {
  return (
    <>
      <h4>Who looks after your information</h4>
      <p>
        Field Club is a free, non-commercial project. Who runs it will be named here before it opens to everyone. To ask
        about your information, write to <ContactAddress meta={meta} />.
      </p>

      <h4>Looking without an account</h4>
      <p>
        Field Club sets no cookies until you start to sign in, and has no advertising and no tracking. Anything you mark
        or answer before you sign in stays in your browser as a draft, and is sent only if you sign in and save it. The
        address bar holds the map's position so links work.
      </p>

      <h4>When you sign in</h4>
      <ul>
        <li>
          From the sign-in provider (Google, Apple, Microsoft, Facebook or OpenStreetMap): a number that identifies your
          account with them, your name and picture, and, where they give it, your email address. Most providers tell us
          an email address. We use it to recognise you if you sign in another way, and never show it to anyone.
        </li>
        <li>If you ask for an emailed link instead: your email address, to send the link to.</li>
        <li>Your name on the map, your display name, a short bio if you write one, and your settings.</li>
        <li>
          Your age band, 16 or 17, or 18 and over, and when you accepted the contributor terms. We keep the band, never
          your date of birth. It decides whether your name and picture from the provider are shown (for 16 and 17 year
          olds they never are), and adds a safety line to the reminder before a site visit.
        </li>
      </ul>

      <h4>While you're signed in</h4>
      <p>
        A cookie, <code>fieldclub_session</code>, keeps you signed in. We keep a scrambled copy of it, when it expires
        (up to a year after you last used it), when it was last used, the name your browser gives itself, and a
        scrambled form of your internet address that can't be turned back into the address. We note when you were last
        seen. Two short-lived cookies are used only during sign-in, to check that the sign-in finishes in the browser
        that started it.
      </p>

      <h4>What you add</h4>
      <p>
        Findings, answers, evidence, votes, comments, links, photos, follows, and the squares you've scanned are kept
        with your account, along with the points you've earned and your role. Photos have their location and camera
        details removed before they are stored. A report you make, and the note you add to it, are seen only by
        moderators. Moderators' actions about you or your work are kept in their log.
      </p>

      <h4>Other services your browser talks to</h4>
      <p>
        The map's tiles and some records come straight from other organisations' services, such as OpenStreetMap,
        OpenFreeMap and the record holders listed under “Where the data comes from” on the about page. When you look at
        an area, your browser asks them, so they see your internet address and which area you're looking at. Signing in
        with a provider sends you to their site, under their own privacy terms.
      </p>

      <h4>Why we keep it</h4>
      <p>
        To run the map you asked to use: to keep you signed in, to credit you for what you add, to apply the safety
        rules for your age band, to stop abuse, and to let you see and delete what is yours.
      </p>

      <h4>Deleting your account</h4>
      <p>
        Deleting your account from your account page removes your email address, your sign-ins, your sessions, any
        unused sign-in links, your name and picture, your bio, your settings, your follows, your notifications, every
        photo you uploaded and your private investigations. You leave any investigation you were invited to, and one you
        shared passes to one of its editors. Your name on the map is replaced with one that says nothing about you. What
        you published stays under its open licence, credited to “Former member”. So do reports, the moderators' log,
        your age band, when you accepted the terms, your role and your points, because they decide how much what you
        added counts. A photo that was refused or hidden keeps a record without its file, so the same picture can't be
        uploaded again.
      </p>

      <h4>Your rights</h4>
      <p>
        You can ask to see what we hold about you, to correct it or to have it deleted. Write to{" "}
        <ContactAddress meta={meta} />. We'll reply within a month. If you're not happy with the answer, you can
        complain to the{" "}
        <a href="https://ico.org.uk/make-a-complaint/" target="_blank" rel="noopener noreferrer">
          Information Commissioner's Office
        </a>
        .
      </p>
    </>
  );
}

function Reporting({ meta }: { meta: Meta }) {
  const reasons = meta.vocab.report_reasons;
  return (
    <>
      <h4>How to report something</h4>
      <p>
        Every finding, comment, piece of evidence, photo and person has a Report button. Choose the reason that fits,
        and add a note for the moderators if it helps. You need to be signed in, so reports have a real person behind
        them.
      </p>
      {reasons.length > 0 ? (
        <ul>
          {reasons.map((reason) => (
            <li key={reason.id}>
              <strong>{reason.label}.</strong> {reason.hint}
              {reason.due_hours ? ` A moderator deals with it within ${reason.due_hours} hours.` : null}
            </li>
          ))}
        </ul>
      ) : null}

      <h4>What happens then</h4>
      <ul>
        <li>A moderator looks at it. Reports with a deadline in law go to the top of their queue.</li>
        <li>
          If it breaks the contributor terms, they hide it, hide the exact place of a finding, or ban the account. If it
          doesn't, they close the report. Either way they write down why.
        </li>
        <li>The person who posted it isn't told who reported it.</li>
        <li>You aren't told the outcome, because Field Club sends nothing private between members.</li>
        <li>You can report the same thing once while a report is open.</li>
      </ul>

      <h4>If you don't have an account</h4>
      <p>
        Landowners and anyone else affected can write to <ContactAddress meta={meta} />. See{" "}
        <Link to="/about/takedown">asking for something to be taken down</Link>.
      </p>
    </>
  );
}

function Takedown({ meta }: { meta: Meta }) {
  return (
    <>
      <h4>Removing your own work</h4>
      <p>
        You can delete your own comments, evidence and links from a finding's page, and withdraw a finding you made.
        Deleting your account removes your personal details, but not what you published (see the{" "}
        <Link to="/about/terms">contributor terms</Link>).
      </p>

      <h4>Asking us to take something down</h4>
      <p>
        If something on Field Club is about you or your land, is untrue, or shouldn't be public, write to{" "}
        <ContactAddress meta={meta} />, whether or not you have an account. Please send:
      </p>
      <ul>
        <li>a link to the page, and which part of it you mean</li>
        <li>what is wrong with it, and how it concerns you, for example as the landowner or the person shown</li>
        <li>how we can reach you about it</li>
      </ul>

      <h4>What we do</h4>
      <ul>
        <li>We reply to say we've received it.</li>
        <li>
          An intimate image shared without consent is taken down as soon as we can, and within 48 hours of the report.
        </li>
        <li>
          If you say something is untrue about you, we pass your complaint to the person who posted it within 48 hours
          and give them five days to reply. If we can't reach them, we take it down.
        </li>
        <li>
          If a finding's exact place puts a site at risk, we can hide the place from everyone except its finder, trusted
          members, archaeologists and moderators.
        </li>
        <li>Anything else that breaks the contributor terms is hidden, and we tell you what we did.</li>
      </ul>
      <p>
        Members can also use the Report button: see <Link to="/about/reporting">how to report something</Link>.
      </p>
    </>
  );
}

export const NOTICES: readonly NoticeEntry[] = [
  {
    id: "terms",
    title: "Contributor terms",
    summary: "What you add is public, under an open licence, and stays if you leave.",
    Body: Terms,
  },
  {
    id: "privacy",
    title: "Privacy notice",
    summary: "What Field Club keeps about you, and why.",
    Body: Privacy,
  },
  {
    id: "reporting",
    title: "Reporting something",
    summary: "How to tell the moderators, and what happens then.",
    Body: Reporting,
  },
  {
    id: "takedown",
    title: "Asking for something to be taken down",
    summary: "For anyone, with an account or without.",
    Body: Takedown,
  },
];

export function findNotice(id: string | undefined): NoticeEntry | undefined {
  return NOTICES.find((notice) => notice.id === id);
}
