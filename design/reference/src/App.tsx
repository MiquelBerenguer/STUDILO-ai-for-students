import {
  useState,
  type Dispatch,
  type KeyboardEvent,
  type ReactNode,
  type SetStateAction,
} from "react"

type IconName = "spark" | "home" | "calendar" | "book" | "exam" | "chart" | "settings" | "bell" | "arrow" | "clock" | "check" | "send" | "plus" | "upload"

const paths: Record<IconName, ReactNode> = {
  spark: (
    <path d="m12 2 1.2 5.1L18 9l-4.8 1.9L12 16l-1.2-5.1L6 9l4.8-1.9L12 2ZM5 15l.7 2.3L8 18l-2.3.7L5 21l-.7-2.3L2 18l2.3-.7L5 15Zm14-2 .7 2.3 2.3.7-2.3.7L19 19l-.7-2.3L16 16l2.3-.7L19 13Z" />
  ),
  home: (
    <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1V10Z" />
  ),
  calendar: (
    <>
      <path d="M4 5h16v16H4zM8 3v4m8-4v4M4 10h16" />
      <path d="M8 14h2m4 0h2m-8 4h2" />
    </>
  ),
  book: (
    <>
      <path d="M4 4h7a3 3 0 0 1 3 3v14a3 3 0 0 0-3-3H4V4Zm16 0h-3a3 3 0 0 0-3 3v14a3 3 0 0 1 3-3h3V4Z" />
    </>
  ),
  exam: (
    <>
      <path d="M7 3h10v4h3v14H4V7h3V3Z" />
      <path d="M8 12h8m-8 4h5" />
    </>
  ),
  chart: <path d="M4 20V10m6 10V4m6 16v-7m5 7H2" />,
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" />
    </>
  ),
  bell: (
    <>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
      <path d="M10 21h4" />
    </>
  ),
  arrow: <path d="m9 18 6-6-6-6" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  send: <path d="m22 2-7 20-4-9-9-4 20-7ZM11 13 22 2" />,
  plus: <path d="M12 5v14m-7-7h14" />,
  upload: (
    <>
      <path d="M12 16V4m-5 5 5-5 5 5" />
      <path d="M5 15v5h14v-5" />
    </>
  ),
}

function Icon({ name, className = "" }: { name: IconName className?: string }) {
  return (
    <svg className={`icon ${className}`} viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}

function Action({
  children,
  className = "",
  onClick,
}: {
  children: ReactNode
  className?: string
  onClick?: () => void
}) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if ((event.key === "Enter" || event.key === " ") && onClick) {
      event.preventDefault()
      onClick()
    }
  }
  return (
    <div
      className={`action ${className}`}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={onKeyDown}
    >
      {children}
    </div>
  )
}

const nav = [
  ["home", "Overview"],
  ["spark", "Novi"],
  ["calendar", "Schedule"],
  ["book", "Courses"],
  ["exam", "Exam prep"],
  ["chart", "Progress"],
] as const

const courses = [
  { code: "CS 301", name: "Machine Learning", color: "violet", progress: 72 },
  { code: "MATH 240", name: "Linear Algebra", color: "blue", progress: 58 },
  { code: "PHYS 210", name: "Quantum Physics", color: "orange", progress: 41 },
]

type Message = {
  from: string
  text: string
}

function NoviWorkspace({
  messages,
  draft,
  setDraft,
  sendMessage,
}: {
  messages: Message[]
  draft: string
  setDraft: Dispatch<SetStateAction<string>>
  sendMessage: (text?: string) => void
}) {
  const [autonomous, setAutonomous] = useState(true)
  const [approval, setApproval] = useState(true)

  return (
    <div className="novi-workspace">
      <section className="novi-command">
        <div className="novi-hero">
          <div className="novi-orbit">
            <span />
            <div className="novi-core">
              <Icon name="spark" />
            </div>
          </div>
          <div className="novi-hero-copy">
            <div className="status-pill dark">
              <span className="pulse-dot" />
              ACTIVE NOW
            </div>
            <div className="novi-hero-title">I’m running your semester.</div>
            <div className="novi-hero-text">
              I’m watching your schedule, processing your notes, and adapting
              exam prep in the background. You only step in when you want to.
            </div>
          </div>
          <div className="autonomy-control">
            <div>
              <div className="autonomy-label">AUTONOMY MODE</div>
              <div className="autonomy-value">
                {autonomous ? "Autonomous" : "Guided"}
              </div>
            </div>
            <Action
              className={`switch ${autonomous ? "is-on" : ""}`}
              onClick={() => setAutonomous(!autonomous)}
            >
              <span />
            </Action>
          </div>
        </div>

        <div className="novi-columns">
          <div className="novi-stack">
            <div className="novi-section-head">
              <div>
                <div className="section-title">Current objectives</div>
                <div className="section-subtitle">
                  What Novi is handling for you
                </div>
              </div>
              <div className="live-label">
                <span />3 running
              </div>
            </div>

            <div className="objective-list">
              <div className="objective-card active-objective">
                <div className="objective-status">
                  <div className="objective-icon">
                    <Icon name="exam" />
                  </div>
                  <span className="activity-pulse" />
                </div>
                <div className="objective-copy">
                  <div className="objective-kicker">WORKING NOW</div>
                  <div className="objective-title">
                    Building your Machine Learning exam plan
                  </div>
                  <div className="objective-meta">
                    Comparing 6 lectures · Finding weak concepts
                  </div>
                  <div className="agent-progress">
                    <span />
                  </div>
                </div>
                <div className="objective-time">68%</div>
              </div>
              <div className="objective-card">
                <div className="objective-status">
                  <div className="objective-icon soft-blue">
                    <Icon name="book" />
                  </div>
                  <Icon name="check" className="objective-check" />
                </div>
                <div className="objective-copy">
                  <div className="objective-kicker">COMPLETED 12 MIN AGO</div>
                  <div className="objective-title">
                    Organized Linear Algebra lecture 07
                  </div>
                  <div className="objective-meta">
                    Summary · 18 cards · 8 practice questions
                  </div>
                </div>
                <Action className="objective-action">
                  Review <Icon name="arrow" />
                </Action>
              </div>
              <div className="objective-card">
                <div className="objective-status">
                  <div className="objective-icon soft-warm">
                    <Icon name="calendar" />
                  </div>
                  <span className="waiting-dot" />
                </div>
                <div className="objective-copy">
                  <div className="objective-kicker">WAITING FOR 2:30 PM</div>
                  <div className="objective-title">
                    Capture Quantum Physics notes
                  </div>
                  <div className="objective-meta">
                    I’ll remind you when the lecture ends
                  </div>
                </div>
                <div className="objective-time">Queued</div>
              </div>
            </div>

            <div className="memory-grid">
              <div className="memory-card">
                <div className="memory-icon">
                  <Icon name="chart" />
                </div>
                <div>
                  <div className="memory-label">Novi learned</div>
                  <div className="memory-title">
                    You retain more with shorter, frequent reviews
                  </div>
                  <div className="memory-copy">
                    I now schedule 15-minute sessions instead of long blocks.
                  </div>
                </div>
              </div>
              <div className="memory-card control-card">
                <div className="control-top">
                  <div>
                    <div className="memory-label">Your guardrail</div>
                    <div className="memory-title">
                      Ask before moving lectures
                    </div>
                  </div>
                  <Action
                    className={`switch small ${approval ? "is-on" : ""}`}
                    onClick={() => setApproval(!approval)}
                  >
                    <span />
                  </Action>
                </div>
                <div className="memory-copy">
                  Novi can optimize study blocks freely, but schedule changes
                  need your approval.
                </div>
              </div>
            </div>
          </div>

          <aside className="novi-conversation">
            <div className="conversation-head">
              <div className="agent-identity">
                <div className="agent-mark">
                  <Icon name="spark" />
                </div>
                <div>
                  <div className="agent-title">Talk to Novi</div>
                  <div className="agent-status">
                    <span />
                    Has full context
                  </div>
                </div>
              </div>
              <div className="context-chip">12 sources</div>
            </div>

            <div className="conversation-body">
              <div className="conversation-date">TODAY</div>
              <div className="novi-message">
                <div className="message-avatar">
                  <Icon name="spark" />
                </div>
                <div>
                  <div className="message-name">Novi</div>
                  <div className="message-bubble">
                    I noticed your Machine Learning exam is now your highest
                    priority. I’ve already shifted two review blocks and I’m
                    building a diagnostic quiz from your notes.
                  </div>
                  <div className="decision-card">
                    <div className="decision-top">
                      <Icon name="calendar" />
                      <div>
                        <div className="decision-label">PLAN CHANGED</div>
                        <div className="decision-title">
                          +45 min for neural networks
                        </div>
                      </div>
                    </div>
                    <div className="decision-reason">
                      Because your last two practice sets showed lower
                      confidence here.
                    </div>
                    <div className="decision-actions">
                      <Action>Keep change</Action>
                      <Action
                        onClick={() =>
                          sendMessage(
                            "Undo the neural networks schedule change",
                          )
                        }
                      >
                        Undo
                      </Action>
                    </div>
                  </div>
                </div>
              </div>

              {messages.slice(1).map((message, index) => (
                <div
                  className={`message conversation-message ${message.from}`}
                  key={`${message.from}-${index}`}
                >
                  {message.text}
                </div>
              ))}
            </div>

            <div className="conversation-prompts">
              <Action
                onClick={() => sendMessage("Why did you change my plan?")}
              >
                Why did you change my plan?
              </Action>
              <Action onClick={() => sendMessage("Make this week lighter")}>
                Make this week lighter
              </Action>
              <Action onClick={() => sendMessage("What are you working on?")}>
                What are you working on?
              </Action>
            </div>
            <div className="novi-composer">
              <div
                className="composer-input"
                contentEditable
                role="textbox"
                aria-label="Tell Novi what to change"
                data-placeholder="Tell Novi what to change..."
                onInput={(event) =>
                  setDraft(event.currentTarget.textContent ?? "")
                }
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault()
                    sendMessage(event.currentTarget.textContent ?? "")
                    event.currentTarget.textContent = ""
                  }
                }}
              />
              <Action
                className="send-action"
                onClick={() => sendMessage(draft)}
              >
                <Icon name="send" />
              </Action>
            </div>
            <div className="agent-footnote">
              Novi explains every decision and lets you change anything.
            </div>
          </aside>
        </div>
      </section>
    </div>
  )
}

export default function App() {
  const [activeNav, setActiveNav] = useState(
    new URLSearchParams(window.location.search).get("view") === "novi"
      ? "Novi"
      : "Overview",
  )
  const [taskDone, setTaskDone] = useState(false)
  const [lectureDone, setLectureDone] = useState(false)
  const [messages, setMessages] = useState([
    {
      from: "agent",
      text: "Good morning, Alex. I organized yesterday’s Linear Algebra notes and added 18 study cards.",
    },
  ])
  const [draft, setDraft] = useState("")

  const sendMessage = (text = draft) => {
    const clean = text.trim()
    if (!clean) return
    setMessages((current) => [
      ...current,
      { from: "you", text: clean },
      {
        from: "agent",
        text: clean.toLowerCase().includes("exam")
          ? "I’ll adjust your exam plan. I can generate a new practice set from your latest notes and focus it on weaker topics."
          : "Got it. I’ll update your learning plan and keep the rest of your schedule balanced.",
      },
    ])
    setDraft("")
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="spark" />
          </div>
          <div className="brand-name">Novi</div>
        </div>

        <nav className="nav-list" aria-label="Main navigation">
          {nav.map(([icon, label]) => (
            <Action
              key={label}
              className={`nav-item ${activeNav === label ? "nav-active" : ""}`}
              onClick={() => setActiveNav(label)}
            >
              <Icon name={icon} />
              <span>{label}</span>
            </Action>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <Action className="nav-item">
            <Icon name="settings" />
            <span>Settings</span>
          </Action>
          <div className="profile">
            <div className="avatar">AM</div>
            <div className="profile-copy">
              <div className="profile-name">Alex Morgan</div>
              <div className="profile-meta">Computer Science</div>
            </div>
            <Icon name="arrow" />
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">MONDAY, OCTOBER 14</div>
            <div className="page-title">
              {activeNav === "Overview" ? "Good morning, Alex" : activeNav}
            </div>
          </div>
          <div className="top-actions">
            <Action className="icon-action">
              <Icon name="bell" />
              <span className="notification-dot" />
            </Action>
            <Action
              className="primary-action"
              onClick={() =>
                activeNav === "Novi"
                  ? sendMessage("I have a new instruction for you")
                  : sendMessage("Add a new course to my schedule")
              }
            >
              <Icon name={activeNav === "Novi" ? "spark" : "plus"} />
              <span>
                {activeNav === "Novi" ? "New instruction" : "Add course"}
              </span>
            </Action>
          </div>
        </header>

        {activeNav === "Novi" ? (
          <NoviWorkspace
            messages={messages}
            draft={draft}
            setDraft={setDraft}
            sendMessage={sendMessage}
          />
        ) : (
          <div className="content-grid">
            <section className="workspace">
              <div className="hero-card">
                <div className="hero-glow" />
                <div className="hero-content">
                  <div className="status-pill">
                    <span className="pulse-dot" />
                    YOUR NEXT MOVE
                  </div>
                  <div className="hero-title">
                    {lectureDone
                      ? "Upload your lecture notes"
                      : "Machine Learning starts in 28 min"}
                  </div>
                  <div className="hero-subtitle">
                    {lectureDone
                      ? "I’ll organize, summarize, and turn them into a study plan."
                      : "Lecture 08 · Neural Networks · Engineering Hall 204"}
                  </div>
                  <div className="hero-footer">
                    <div className="instructor">
                      <div className="mini-avatar">DK</div>
                      <div>
                        <div className="small-label">WITH</div>
                        <div className="instructor-name">Dr. Kim</div>
                      </div>
                    </div>
                    <Action
                      className="light-action"
                      onClick={() => setLectureDone(!lectureDone)}
                    >
                      <Icon name={lectureDone ? "upload" : "check"} />
                      <span>
                        {lectureDone ? "Upload notes" : "Mark class done"}
                      </span>
                    </Action>
                  </div>
                </div>
              </div>

              <div className="section-heading">
                <div>
                  <div className="section-title">Today’s flow</div>
                  <div className="section-subtitle">
                    Your plan adjusts as you go
                  </div>
                </div>
                <Action className="text-action">
                  View schedule <Icon name="arrow" />
                </Action>
              </div>

              <div className="timeline-card">
                <div className="timeline-row is-past">
                  <div className="timeline-time">9:00</div>
                  <div className="timeline-track">
                    <span className="timeline-dot done">
                      <Icon name="check" />
                    </span>
                    <span className="timeline-line" />
                  </div>
                  <div className="timeline-copy">
                    <div className="timeline-title">Linear Algebra</div>
                    <div className="timeline-meta">
                      Eigenvalues & eigenvectors · Completed
                    </div>
                  </div>
                  <div className="timeline-badge success">Notes processed</div>
                </div>
                <div className="timeline-row is-current">
                  <div className="timeline-time">11:00</div>
                  <div className="timeline-track">
                    <span className="timeline-dot current" />
                    <span className="timeline-line" />
                  </div>
                  <div className="timeline-copy">
                    <div className="timeline-title">Machine Learning</div>
                    <div className="timeline-meta">
                      Neural Networks · Engineering Hall 204
                    </div>
                  </div>
                  <div className="timeline-badge current-badge">Up next</div>
                </div>
                <div className="timeline-row">
                  <div className="timeline-time">2:30</div>
                  <div className="timeline-track">
                    <span className="timeline-dot" />
                  </div>
                  <div className="timeline-copy">
                    <div className="timeline-title">Quantum Physics</div>
                    <div className="timeline-meta">
                      Wave functions · Science Center 12
                    </div>
                  </div>
                  <div className="timeline-badge">Lecture</div>
                </div>
              </div>

              <div className="bottom-grid">
                <div className="panel">
                  <div className="panel-top">
                    <div>
                      <div className="section-title">Courses</div>
                      <div className="section-subtitle">
                        3 active this semester
                      </div>
                    </div>
                    <Action className="round-action">
                      <Icon name="arrow" />
                    </Action>
                  </div>
                  <div className="course-list">
                    {courses.map((course) => (
                      <div className="course-row" key={course.code}>
                        <div className={`course-icon ${course.color}`}>
                          <Icon name="book" />
                        </div>
                        <div className="course-copy">
                          <div className="course-code">{course.code}</div>
                          <div className="course-name">{course.name}</div>
                        </div>
                        <div className="progress-wrap">
                          <div className="progress-label">
                            {course.progress}% ready
                          </div>
                          <div className="progress-track">
                            <span style={{ width: `${course.progress}%` }} />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="panel exam-panel">
                  <div className="panel-top">
                    <div>
                      <div className="section-title">Next exam</div>
                      <div className="section-subtitle">18 days away</div>
                    </div>
                    <div className="date-box">
                      <span>01</span>
                      <small>NOV</small>
                    </div>
                  </div>
                  <div className="exam-title">Machine Learning</div>
                  <div className="exam-detail">
                    <Icon name="clock" />
                    Friday · 9:00 AM · 90 minutes
                  </div>
                  <div className="readiness-row">
                    <div>
                      <div className="small-label">READINESS</div>
                      <div className="readiness-value">72%</div>
                    </div>
                    <div className="readiness-ring">
                      <span>72</span>
                    </div>
                  </div>
                  <Action
                    className="secondary-action"
                    onClick={() =>
                      sendMessage(
                        "Generate a practice exam for Machine Learning",
                      )
                    }
                  >
                    Generate practice exam <Icon name="arrow" />
                  </Action>
                </div>
              </div>
            </section>

            <aside className="agent-panel">
              <div className="agent-header">
                <div className="agent-identity">
                  <div className="agent-mark">
                    <Icon name="spark" />
                  </div>
                  <div>
                    <div className="agent-title">Novi Agent</div>
                    <div className="agent-status">
                      <span />
                      Always working for you
                    </div>
                  </div>
                </div>
                <Action className="round-action">
                  <Icon name="settings" />
                </Action>
              </div>

              <div className="agent-body">
                <div className="briefing-label">DAILY BRIEFING</div>
                <div className="messages">
                  {messages.map((message, index) => (
                    <div
                      className={`message ${message.from}`}
                      key={`${message.from}-${index}`}
                    >
                      {message.text}
                    </div>
                  ))}
                </div>

                <div className="agent-task">
                  <div className="task-top">
                    <div className="task-icon">
                      <Icon name="book" />
                    </div>
                    <div>
                      <div className="task-kicker">PREPARED FOR YOU</div>
                      <div className="task-title">Linear Algebra study set</div>
                    </div>
                  </div>
                  <div className="task-stats">
                    <div>
                      <strong>12 min</strong>
                      <span>Summary</span>
                    </div>
                    <div>
                      <strong>18</strong>
                      <span>Study cards</span>
                    </div>
                    <div>
                      <strong>8</strong>
                      <span>Practice Qs</span>
                    </div>
                  </div>
                  <Action
                    className={`task-action ${taskDone ? "completed" : ""}`}
                    onClick={() => setTaskDone(!taskDone)}
                  >
                    <Icon name={taskDone ? "check" : "arrow"} />
                    {taskDone ? "Added to today’s plan" : "Start review"}
                  </Action>
                </div>

                <div className="agent-note">
                  <Icon name="spark" />
                  <div>
                    <div className="note-title">I adjusted your plan</div>
                    <div className="note-copy">
                      You seemed confident in eigenvalues, so I shortened that
                      review and added more time for neural networks.
                    </div>
                  </div>
                </div>
              </div>

              <div className="quick-prompts">
                <Action
                  onClick={() => sendMessage("What should I focus on today?")}
                >
                  What should I focus on?
                </Action>
                <Action onClick={() => sendMessage("Change my exam plan")}>
                  Change my exam plan
                </Action>
              </div>
              <div className="composer">
                <div
                  className="composer-input"
                  contentEditable
                  role="textbox"
                  aria-label="Ask Novi anything"
                  data-placeholder="Ask Novi anything..."
                  onInput={(event) =>
                    setDraft(event.currentTarget.textContent ?? "")
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault()
                      sendMessage(event.currentTarget.textContent ?? "")
                      event.currentTarget.textContent = ""
                    }
                  }}
                />
                <Action className="send-action" onClick={() => sendMessage()}>
                  <Icon name="send" />
                </Action>
              </div>
              <div className="agent-footnote">
                Novi can make mistakes. Review important exam details.
              </div>
            </aside>
          </div>
        )}
      </main>
    </div>
  )
}
