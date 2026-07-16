import { Link } from "react-router-dom";

import directoryEnvironment from "../../brand/werner/map/igloo_directory_environment_v1.webp";
import "./igloo-directory.css";

export interface DirectoryDoor {
  path: string;
  title: string;
  description: string;
  marker: string;
}

export interface DirectoryDistrict {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  doors: readonly DirectoryDoor[];
}

export const DIRECTORY_DISTRICTS: readonly DirectoryDistrict[] = [
  {
    id: "make",
    eyebrow: "The working rooms",
    title: "Make and investigate",
    description:
      "Begin with a question, gather evidence, read it as HTML, and carry the strongest thinking into notes, drafts, and conversations.",
    doors: [
      {
        path: "/",
        title: "Research workstation",
        description:
          "Interrogate evidence and chase questions with research agents.",
        marker: "01",
      },
      {
        path: "/deep-research",
        title: "Deep research",
        description:
          "Watch launched research sessions develop in one workspace.",
        marker: "02",
      },
      {
        path: "/my-research",
        title: "My research",
        description:
          "Survey running and completed investigations from one chart room.",
        marker: "03",
      },
      {
        path: "/sources",
        title: "Source intake",
        description: "Bring publications and other evidence into Antiek.",
        marker: "04",
      },
      {
        path: "/documents",
        title: "Evidence archive",
        description: "Find substrate-attached records by evidence tier.",
        marker: "05",
      },
      {
        path: "/library",
        title: "Library",
        description: "Choose an owned reading asset and open its HTML edition.",
        marker: "06",
      },
      {
        path: "/wrestle",
        title: "Reading wrestler",
        description:
          "Open a document for close reading and region-level interrogation.",
        marker: "07",
      },
      {
        path: "/readings",
        title: "Personal readings",
        description: "Return to saved reads and created information assets.",
        marker: "08",
      },
      {
        path: "/notebooks",
        title: "Notebooks",
        description: "Develop durable notes and literate analysis.",
        marker: "09",
      },
      {
        path: "/brainstorm",
        title: "Brainstorm",
        description:
          "Wrestle with parked questions and future lines of inquiry.",
        marker: "10",
      },
      {
        path: "/write",
        title: "Write",
        description: "Shape evidence into outlines, drafts, and finished work.",
        marker: "11",
      },
      {
        path: "/speak",
        title: "Speak",
        description: "Run interview projects and corroborate human testimony.",
        marker: "12",
      },
      {
        path: "/multimedia",
        title: "Multimedia",
        description: "Review local visual and audible research experiences.",
        marker: "13",
      },
    ],
  },
  {
    id: "steward",
    eyebrow: "The instrument rooms",
    title: "Review and steward",
    description:
      "Inspect quality, privacy, model behavior, budget posture, and the substrate itself without confusing observation with authority.",
    doors: [
      {
        path: "/outcomes",
        title: "Calibration observatory",
        description:
          "Review outcome history and the evidence behind calibration.",
        marker: "14",
      },
      {
        path: "/stats",
        title: "Substrate atlas",
        description:
          "Inspect known corpus cardinalities without invented relationships.",
        marker: "15",
      },
      {
        path: "/settings",
        title: "Model observatory",
        description:
          "Steward models, budgets, projections, and benchmark evidence.",
        marker: "16",
      },
      {
        path: "/privacy",
        title: "Privacy",
        description: "Review privacy budgets and account-level controls.",
        marker: "17",
      },
      {
        path: "/trust",
        title: "Trust center",
        description: "Read Antiek’s substrate-wide control posture.",
        marker: "18",
      },
      {
        path: "/billing",
        title: "Billing",
        description: "Inspect usage and account economics.",
        marker: "19",
      },
      {
        path: "/payouts",
        title: "Payout audit",
        description: "Review contributor accrual and transfer history.",
        marker: "20",
      },
      {
        path: "/coordination",
        title: "Coordination",
        description:
          "Inspect gates, sprint posture, and shared execution state.",
        marker: "21",
      },
      {
        path: "/operator",
        title: "Operator room",
        description: "Open the composite operator-facing snapshot.",
        marker: "22",
      },
    ],
  },
  {
    id: "specialist",
    eyebrow: "The side chambers",
    title: "Specialist rooms",
    description:
      "Intentional secondary surfaces for advanced composition, policy, citation, and learning-system work.",
    doors: [
      {
        path: "/home",
        title: "Antiek home",
        description: "Return to the unified branded threshold.",
        marker: "23",
      },
      {
        path: "/create",
        title: "Creation studio",
        description: "Use the lower-level block composition surface.",
        marker: "24",
      },
      {
        path: "/biography",
        title: "Biography template",
        description:
          "Start a research, writing, and interview project over one graph.",
        marker: "25",
      },
      {
        path: "/federation",
        title: "Federation",
        description: "Review cross-substrate citation policy.",
        marker: "26",
      },
      {
        path: "/cross-graph/citations",
        title: "Cross-graph citations",
        description: "Inspect citations crossing graph boundaries.",
        marker: "27",
      },
      {
        path: "/skill-rules",
        title: "Skill rules",
        description: "Review learned rules before they shape future work.",
        marker: "28",
      },
      {
        path: "/loop-3",
        title: "Learning-loop gate",
        description: "Inspect the unlock checklist for adaptive behavior.",
        marker: "29",
      },
      {
        path: "/pricing",
        title: "Pricing",
        description: "Estimate pay-as-you-go research economics.",
        marker: "30",
      },
    ],
  },
] as const;

export interface IglooDirectoryProps {
  districts?: readonly DirectoryDistrict[];
  visualFixture?: boolean;
}

export function IglooDirectory({
  districts = DIRECTORY_DISTRICTS,
  visualFixture = false,
}: IglooDirectoryProps) {
  return (
    <div
      className={`igloo-directory${visualFixture ? " igloo-directory--fixture" : ""}`}
    >
      <img
        src={directoryEnvironment}
        alt=""
        aria-hidden="true"
        draggable={false}
        decoding="async"
      />
      <div className="igloo-directory__veil" aria-hidden="true" />

      <header className="igloo-directory__masthead">
        <p className="igloo-directory__eyebrow">
          Antiek · a field guide to the igloo
        </p>
        <h1>The Igloo Directory</h1>
        <p>
          Choose a room by the work you want to do. This is a curated wayfinding
          guide—not a claim that every implementation route is a separate
          destination.
        </p>
        <div className="igloo-directory__keys" aria-label="Workspace shortcuts">
          <span>
            <kbd>⌘K</kbd> find a room
          </span>
          <span>
            <kbd>⌘J</kbd> open the thought partner
          </span>
        </div>
      </header>

      <div className="igloo-directory__districts">
        {districts.map((district) => (
          <section
            key={district.id}
            className="igloo-directory__district"
            aria-labelledby={`directory-${district.id}`}
          >
            <header>
              <p>{district.eyebrow}</p>
              <h2 id={`directory-${district.id}`}>{district.title}</h2>
              <span>{district.description}</span>
            </header>
            <ul>
              {district.doors.map((door) => (
                <li key={door.path}>
                  <Link to={door.path} className="igloo-directory__door">
                    <span
                      className="igloo-directory__marker"
                      aria-hidden="true"
                    >
                      {door.marker}
                    </span>
                    <span className="igloo-directory__door-copy">
                      <strong>{door.title}</strong>
                      <span>{door.description}</span>
                      <code>{door.path}</code>
                    </span>
                    <span className="igloo-directory__arrow" aria-hidden="true">
                      ↗
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <footer className="igloo-directory__footnote">
        <p>
          <strong>About this directory</strong> It names intentional human
          doors. Redirect aliases, invitation tokens, popout internals, and
          document-specific deep links stay out of the way.
        </p>
      </footer>
    </div>
  );
}

export default function Map() {
  return <IglooDirectory />;
}
