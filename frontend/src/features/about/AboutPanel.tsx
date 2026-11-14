import { ChevronRight } from "lucide-react";
import { useLayoutEffect } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { GUIDE_PATH } from "../guide/GuidePanel.js";
import { NotFoundPanel, useDocumentTitle } from "../placeholders.js";
import { ReportProblemButton } from "../problem/ReportProblem.js";
import { ISSUES_URL, SOURCE_URL, shortCommit } from "../problem/repository.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { Credits } from "./Credits.js";
import { minimumAge } from "./facts.js";
import { ContactAddress, DraftBanner, findNotice, NOTICES, type NoticeEntry } from "./notices.js";
import "../guide/guide.css";
import "./about.css";

export const ABOUT_PATH = "/about";
export const NOTICE_ROUTE = `${ABOUT_PATH}/:notice`;

export function noticePath(id: NoticeEntry["id"]): string {
  return `${ABOUT_PATH}/${id}`;
}

/**
 * The contributor terms' address in `/meta` is `/about#terms` by default, and
 * a link may name any notice that way. The router still holds the hash when
 * the page first renders, before the map's permalink takes the address bar
 * back, so it is read here and the notice's own page replaces it.
 */
function useNoticeFromHash(): void {
  const { hash } = useLocation();
  const navigate = useNavigate();
  const target = findNotice(hash.replace(/^#/, ""));
  useLayoutEffect(() => {
    if (target) navigate(noticePath(target.id), { replace: true });
  }, [target, navigate]);
}

function NoticeLinks() {
  return (
    <ul className="fc-about__notices">
      {NOTICES.map((notice) => (
        <li key={notice.id}>
          <Link to={noticePath(notice.id)} className="fc-about__notice-link">
            <span>
              <strong>{notice.title}</strong>
              <span className="fc-about__muted">{notice.summary}</span>
            </span>
            <ChevronRight size={18} aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** `/about`: what OpenAntiquity is, who runs it, where its data comes from, and the notices. */
export function AboutPanel({ meta }: { meta: Meta }) {
  useNoticeFromHash();
  const name = meta.app.name;
  useDocumentTitle(`About ${name}`);
  return (
    <PanelFrame panelKey={ABOUT_PATH} title={`About ${name}`}>
      <div className="fc-guide fc-about">
        <p>
          {name} is a shared map for finding and checking archaeological earthworks in LIDAR, a laser survey of the
          height of the ground. You mark what you see. Other people check it and add evidence from old maps, aerial
          photos and heritage records, and each finding's confidence rises as independent people and sources agree.
        </p>
        <p>
          The name says what it is. An antiquity is the old word, still used on Ordnance Survey maps, for something left
          by the past that survives in the ground. “Open” is how the work is done: anyone can look at the map, and what
          people add is published under an open licence.
        </p>
        <p>
          New to it? The <Link to={GUIDE_PATH}>guide</Link> shows how to read the ground.
        </p>

        <section className="fc-guide__section" aria-labelledby="about-who">
          <h3 className="fc-guide__heading" id="about-who">
            Who runs it
          </h3>
          <p>
            {name} is run by volunteers. To get in touch, write to <ContactAddress meta={meta} />.
          </p>
          <p>
            It is free and non-commercial. There are no adverts, nothing to pay, and no data for sale. That's also why
            it can show records whose publishers allow only non-commercial use.
          </p>
        </section>

        <section className="fc-guide__section" aria-labelledby="about-sites">
          <h3 className="fc-guide__heading" id="about-sites">
            How sites are protected
          </h3>
          <p>{meta.notices.sensitivity}</p>
          <p>
            Some earthworks, such as burial mounds, could attract illegal metal detecting if their exact place were
            public, so findings of those kinds start protected, and any other finding can be made protected.
          </p>
        </section>

        <section className="fc-guide__section" aria-labelledby="about-people">
          <h3 className="fc-guide__heading" id="about-people">
            Who can join
          </h3>
          <p>
            Contributors are {minimumAge(meta)} or over. The coming rules on children online draw their line at 16, and
            {` ${name} `}sends people out to real places. Anyone of any age can look at the map.
          </p>
          <p>
            There are no private messages, because they are what most puts younger members at risk, and talk about a
            finding belongs on the finding, where everyone can see it.
          </p>
        </section>

        <section className="fc-guide__section" aria-labelledby="about-notices">
          <h3 className="fc-guide__heading" id="about-notices">
            The rules
          </h3>
          <NoticeLinks />
        </section>

        <section className="fc-guide__section" aria-labelledby="about-data">
          <h3 className="fc-guide__heading" id="about-data">
            Where the data comes from
          </h3>
          <p>
            {name} is built on other people's open data. Each source below is credited as its licence asks. What members
            add is published under {meta.app.contribution_licence}.
          </p>
          <Credits meta={meta} />
        </section>

        <section className="fc-guide__section" aria-labelledby="about-code">
          <h3 className="fc-guide__heading" id="about-code">
            The code
          </h3>
          <p>
            {name}'s code is free software under the GNU Affero General Public License, version 3. You can read{" "}
            <a href={SOURCE_URL} target="_blank" rel="noopener noreferrer">
              the source code
            </a>{" "}
            and{" "}
            <a href={ISSUES_URL} target="_blank" rel="noopener noreferrer">
              the list of known problems
            </a>{" "}
            on GitHub.
          </p>
        </section>

        <section className="fc-guide__section" aria-labelledby="about-problem">
          <h3 className="fc-guide__heading" id="about-problem">
            When something goes wrong
          </h3>
          <p>
            Tell us what you were doing. The form shows everything that goes with your report before anything is sent,
            and you choose whether it goes as a GitHub issue or another way.
          </p>
          <ReportProblemButton />
        </section>

        <p className="fc-about__muted">
          Version {meta.app.version}
          {meta.app.commit ? `, commit ${shortCommit(meta.app.commit)}` : null}
        </p>
      </div>
    </PanelFrame>
  );
}

/** `/about/:notice`: one of the notices, marked as a draft at the top. */
export function NoticePanel({ meta }: { meta: Meta }) {
  const params = useParams();
  const notice = findNotice(params.notice);
  if (!notice) return <NotFoundPanel />;
  return <NoticePage meta={meta} notice={notice} />;
}

function NoticePage({ meta, notice }: { meta: Meta; notice: NoticeEntry }) {
  useDocumentTitle(notice.title);
  const { Body } = notice;
  return (
    <PanelFrame panelKey={noticePath(notice.id)} title={notice.title} subtitle={`${meta.app.name}, draft`}>
      <div className="fc-about">
        <DraftBanner />
        <article id={notice.id} className="fc-about__notice" aria-label={notice.title}>
          <Body meta={meta} />
        </article>
        <nav className="fc-about__more" aria-label="The other notices">
          <ul>
            {NOTICES.filter((other) => other.id !== notice.id).map((other) => (
              <li key={other.id}>
                <Link to={noticePath(other.id)}>{other.title}</Link>
              </li>
            ))}
            <li>
              <Link to={ABOUT_PATH}>About {meta.app.name}</Link>
            </li>
          </ul>
        </nav>
      </div>
    </PanelFrame>
  );
}
