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
import {
  ageBandWords,
  licenceAddress,
  minimumAge,
  offersEmailLink,
  orList,
  signInProviders,
  takesUnder18s,
} from "./facts.js";

export type NoticeId = "terms" | "privacy" | "reporting" | "takedown";

export interface NoticeEntry {
  id: NoticeId;
  title: string;
  /** One line for the list on the about page. */
  summary: string;
  Body: (props: { meta: Meta }) => ReactNode;
}

/**
 * The address to write to, from `/meta` when the backend sends it. Until
 * then it is said once, on the about page, and the notices point there.
 */
export function ContactAddress({ meta }: { meta: Meta }) {
  const contact = meta.app.contact?.trim();
  if (!contact) {
    return <>the address that will be given here before OpenAntiquity opens to everyone</>;
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

/** In a notice: the address itself once `/meta` sends it, and until then the about page, which says where it will be. */
function WriteTo({ meta }: { meta: Meta }) {
  if (meta.app.contact?.trim()) return <ContactAddress meta={meta} />;
  return (
    <>
      the contact address on the <Link to="/about">about page</Link>
    </>
  );
}

/** The mark at the top of every notice that it is a draft. */
export function DraftBanner() {
  return (
    <div className="fc-about__draft" role="note">
      <FilePenLine size={18} aria-hidden />
      <div>
        <strong>Draft</strong>
        <p>
          These words haven't been settled yet. The people who run OpenAntiquity still have to check them, with legal
          advice, before OpenAntiquity opens to everyone. They describe what the site does today.
        </p>
      </div>
    </div>
  );
}

/** What matters most in a notice, first, so it can be read in under a minute. */
function InShort({ children }: { children: ReactNode }) {
  return (
    <section className="fc-about__short" aria-labelledby="notice-short">
      <h4 id="notice-short">In short</h4>
      <ul>{children}</ul>
    </section>
  );
}

/** A part of a notice that only some readers need, closed until it is opened. */
function More({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="fc-about__part">
      <summary>{title}</summary>
      <div className="fc-about__part-body">{children}</div>
    </details>
  );
}

/** The contribution licence, linked where this build knows its address. */
function Licence({ meta }: { meta: Meta }) {
  const licence = meta.app.contribution_licence;
  const address = licenceAddress(licence);
  if (!address) return <>the {licence} licence</>;
  return (
    <>
      the{" "}
      <a href={address} target="_blank" rel="noopener noreferrer">
        {licence} licence
      </a>
    </>
  );
}

function Terms({ meta }: { meta: Meta }) {
  const licence = meta.app.contribution_licence;
  return (
    <>
      <InShort>
        <li>Anyone can look. To add anything you need an account, and must be {minimumAge(meta)} or over.</li>
        <li>
          What you add is public, published under <Licence meta={meta} />, so anyone may reuse it if they credit you.
        </li>
        <li>Add only your own work, or work you may share. Nothing about people that they haven't made public.</li>
        <li>Be civil, and never use OpenAntiquity to plan digging, detecting or trespass.</li>
        <li>If you leave, your details go, and what you published stays, credited to “Former member”.</li>
      </InShort>

      <More title="What you add is public">
        <p>
          Findings, evidence, comments, links to videos and articles, photos once they've been approved, and your
          profile can be seen by anyone. Your second looks are shown, with your name on the map, to the finder and to
          other people who have answered the same finding. Nobody else learns how you answered.
        </p>
        <p>
          Where a finding's exact place is hidden to protect the site, OpenAntiquity hides it everywhere it shows the
          finding, including grid references and coordinates written in what you add.
        </p>
        <p>
          You keep the rights to what you add. By saving it you publish it under {licence}, so anyone may copy, share
          and build on it, for any purpose, as long as they credit OpenAntiquity and the name you use on the map. You
          accept these terms once, on the welcome step after your first sign-in.
        </p>
      </More>

      <More title="Only add what you may share">
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
      </More>

      <More title="How to behave">
        <ul>
          <li>Be civil. Disagree with the evidence, not the person.</li>
          <li>
            Never use OpenAntiquity to plan anything illegal: digging, metal detecting where it isn't allowed, or
            trespass.
          </li>
          <li>
            OpenAntiquity has no private messages. Don't use comments to arrange to meet people you don't know, and
            never to meet anyone under 18.
          </li>
        </ul>
      </More>

      <More title="Looking after the map">
        <p>
          Moderators can hide anything that breaks these terms, hide the exact place of a finding, and ban an account.
          An account that is banned can't sign in, and the evidence it added and the findings it verified stop counting
          towards any finding's confidence. Its second looks and votes go on counting as they were given, because a
          score that moved the moment someone was banned would show how they had answered. Everything a moderator does
          is written in a log the moderators share.
        </p>
      </More>

      <More title="If you leave">
        <p>
          You can delete your account from your account page at any time. Your personal details, your photos and your
          private investigations are deleted. What else you published stays, because it was published under an open
          licence and other people's work builds on it, but it is credited to “Former member” from then on. Your old
          name on the map no longer leads to it, and nobody else can take that name for a year.
        </p>
      </More>

      <h4>Changes</h4>
      <p>
        If these terms change, the new terms will be shown here, with the date, before they apply to anything you add
        afterwards.
      </p>
    </>
  );
}

function Privacy({ meta }: { meta: Meta }) {
  const providers = signInProviders(meta);
  const email = offersEmailLink(meta);
  return (
    <>
      <InShort>
        <li>
          No adverts, no tracking, and no cookies until you start to sign in. Looking at a page never makes your browser
          contact a sign-in provider.
        </li>
        <li>
          When you sign in we keep what you need to be recognised, and your email address if we're given it. We never
          show your email to anyone.
        </li>
        <li>We keep your age band, never your date of birth, to apply the right safety rules.</li>
        <li>What you add is public. A report you make is seen only by moderators.</li>
        <li>You can delete your account at any time, and ask to see, correct or delete what we hold.</li>
      </InShort>

      <h4>Who looks after your information</h4>
      <p>
        OpenAntiquity is a free, non-commercial project. Who runs it will be named here before it opens to everyone. To
        ask about your information, write to <WriteTo meta={meta} />.
      </p>

      <More title="Looking without an account">
        <p>
          OpenAntiquity sets no cookies until you start to sign in, and has no advertising and no tracking. Anything you
          mark or answer before you sign in stays in your browser as a draft, in its local storage, and is sent only
          when you sign in. Signing in from the same tab saves what you made there as yours, except a second look, which
          waits for you to send it. Anything else left in the browser, perhaps by someone else, is saved only if you say
          it's yours. Whoever uses the browser after you can see that a draft is there, but not what it says or where,
          so discard your drafts on a shared computer. The tab you're using also keeps, for as long as it is open, a
          random number that tells your drafts from anyone else's, when you began to sign in, the square you're scanning
          and a second look you haven't finished. When you sign in or out, the browser's storage gets a random value
          that tells your other tabs. The address bar holds the map's position so links work.
        </p>
      </More>

      <More title="When you sign in">
        <ul>
          {providers.length > 0 ? (
            <li>
              From the sign-in provider ({orList(providers)}): a number that identifies your account with them, your
              name, and, where they give it, your email address. Most providers tell us an email address. We use it to
              recognise you if you sign in another way, and never show it to anyone. We don't keep or show the picture a
              provider has of you, though Google sends it with your name, so nobody's browser contacts a provider to
              show you: people are shown by their name and initials.
            </li>
          ) : null}
          {email ? (
            <li>
              If you ask for an emailed link{providers.length > 0 ? " instead" : ""}: your email address, to send the
              link to. The link is deleted a day after it is used or runs out, fifteen minutes after it was sent.
            </li>
          ) : null}
          <li>
            Your name on the map, your display name, a short bio if you write one, and your settings. A name on the map
            you give up is held for a year, so nobody else can take it and be taken for you.
          </li>
          <li>
            Your age band ({ageBandWords(meta)}) and when you accepted the contributor terms. We keep the band, never
            your date of birth.
            {takesUnder18s(meta)
              ? " It decides whether your name from the provider is shown (for 16 and 17 year olds it never is), and adds a safety line to the reminder before a site visit."
              : null}
          </li>
        </ul>
      </More>

      <More title="While you're signed in">
        <p>
          A cookie, <code>__Host-openantiquity_session</code>, keeps you signed in. We keep a scrambled copy of it, when
          it expires, when it was last used, the name your browser gives itself, and a scrambled form of your internet
          address, made with a secret key so it can't be read back without it. A session ends after 90 days unused, and
          a year after you signed in however much you use it, and an ended session is deleted. You can end every session
          of yours, on every device, from your account page. We note when you were last seen. Two short-lived cookies
          are used only during sign-in, to check that it finishes in the browser that started it:{" "}
          <code>openantiquity_oauth</code> for ten minutes when you sign in with a provider, and{" "}
          <code>openantiquity_email_link</code> for fifteen minutes when you ask for an emailed link. After you sign in
          with an emailed link, <code>openantiquity_email_known</code> remembers for a year that this browser has signed
          in to that address, as a scrambled code made with our secret key, so that it can still ask for a link when
          strangers have asked for too many.
        </p>
      </More>

      <More title="What you add">
        <p>
          Findings, answers, evidence, votes, comments, links, photos, follows, and the squares you've scanned are kept
          with your account, along with the points you've earned and your role. Photos have their location and camera
          details removed before they are stored. A report you make, and the note you add to it, are seen only by
          moderators. Moderators' actions about you or your work are kept in their log.
        </p>
      </More>

      <More title="Other services your browser talks to">
        <p>
          The map's tiles and some records come straight from other organisations' services, such as OpenStreetMap,
          OpenFreeMap and the record holders listed under “Where the data comes from” on the about page. When you look
          at an area, your browser asks them, so they see your internet address and which area you're looking at. A
          video linked on a finding shows its picture from YouTube's or Vimeo's image servers, which see your internet
          address but not which page you're on. Your browser fetches nothing else from anywhere else: the site tells it
          not to.
          {providers.length > 0
            ? " Signing in with a provider sends you to their site, under their own privacy terms. Otherwise your browser never contacts one."
            : null}
        </p>
      </More>

      <More title="When something goes wrong">
        <p>
          The server writes a log as it works. For each request it answers there is a line with when, the address asked
          for, which can say what part of the map was being looked at, and the answer. It isn't only a list of requests:
          the server also writes lines of its own about what it is doing, and some of them name an account. Each request
          is given a random number, which goes back with the answer and on that request's lines in the log, so that a
          report of a problem can be matched to them. Our host, Fly.io, says it keeps the log for seven days. While a
          page is open, your browser also keeps in memory the last ten things that went wrong in it: when, what kind of
          address failed but never which one, the answer and that number, and the words of an error the page didn't
          catch, with anything that looks like a place, an id or a quoted value taken out. They go when you close the
          page, and are sent nowhere unless you use "Report a problem", which shows you everything it would send first.
          It adds where the map was only if you ask, and then only the one-kilometre square the map was centred on and
          how far in it was zoomed. A report you open as a GitHub issue is public, and GitHub's own privacy terms cover
          it.
        </p>
      </More>

      <More title="Why we keep it">
        <p>
          To run the map you asked to use: to keep you signed in, to credit you for what you add, to apply the safety
          rules for your age band, to stop abuse, and to let you see and delete what is yours.
        </p>
      </More>

      <More title="Deleting your account">
        <p>
          Deleting your account from your account page removes your email address, your sign-ins, your sessions, the
          sign-in links for your account, your name, your bio, your settings, your follows, your notifications, every
          photo you uploaded and your private investigations. You leave any investigation you were invited to, and one
          you shared passes to one of its editors. Your name on the map is replaced with one that says nothing about
          you, and the old one is held for a year, tied to nobody, so nobody else can take it.
        </p>
        <p>
          What you published stays under its open licence, credited to “Former member”. So do reports, the moderators'
          log, your age band, when you accepted the terms, your role and your points, because they decide how much what
          you added counts. A photo that was refused or hidden keeps a record without its file, so the same picture
          can't be uploaded again.
        </p>
      </More>

      <h4>Your rights</h4>
      <p>
        You can ask to see what we hold about you, to correct it or to have it deleted. Write to <WriteTo meta={meta} />
        . We'll reply within a month. If you're not happy with the answer, you can complain to the{" "}
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
        <li>You aren't told the outcome, because OpenAntiquity sends nothing private between members.</li>
        <li>You can report the same thing once while a report is open.</li>
      </ul>

      <h4>If you don't have an account</h4>
      <p>
        Landowners and anyone else affected can write to <WriteTo meta={meta} />. See{" "}
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
        You can delete your own comments, evidence and mentions from a finding's page, and withdraw a finding you made.
        Deleting your account removes your personal details, but not what you published (see the{" "}
        <Link to="/about/terms">contributor terms</Link>).
      </p>

      <h4>Asking us to take something down</h4>
      <p>
        If something on OpenAntiquity is about you or your land, is untrue, or shouldn't be public, write to{" "}
        <WriteTo meta={meta} />, whether or not you have an account. Please send:
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
          If a finding's exact place puts a site at risk, we can hide the finding from everyone except its finder and
          moderators.
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
    summary: "What OpenAntiquity keeps about you, and why.",
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
